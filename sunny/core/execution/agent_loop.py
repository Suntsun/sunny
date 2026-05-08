from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from sunny.brain.ollama_client import (
    LLMError,
    LLMTimeoutError,
    LLMValidationError,
    call_llm_validated,
)
from sunny.core.execution.engine import StepExecutionResult, _execute_step
from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import Step
from sunny.core.plugins.registry import PluginRegistry
from sunny.core.prompts.loader import load_system_prompt

log = get_logger("sunny.core.execution.agent_loop")

MAX_LOOP_STEPS: int = 20
DEFAULT_LOOP_STEP_TIMEOUT_SEC: int = 60
ALLOWED_PLUGINS: tuple = ("gui", "vision", "os_control")


class LoopDecision(BaseModel):
    """Decisión del LLM agente para el siguiente paso del bucle."""

    plugin: str = ""
    action: str = ""
    params: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    goal_reached: bool = False


@dataclass
class AgentLoopResult:
    goal: str
    success: bool
    steps_executed: List[StepExecutionResult] = field(default_factory=list)
    total_latency_ms: int = 0
    stopped_reason: str = "goal_reached"
    final_screen_state: Optional[str] = None


def _load_loop_prompt() -> str:
    return load_system_prompt("agent_loop_v1")


def _capture_screen_state(
    registry: PluginRegistry,
    context: Dict[str, Any],
) -> tuple[str, Optional[str]]:
    """Llama a vision.get_screen_state y devuelve (screen_text, screenshot_path).

    Si vision no está registrado o falla, devuelve ("", None) y deja
    que el LLM razone sin contexto visual.
    """
    vision = registry.get("vision")
    if vision is None:
        return "", None
    try:
        result = vision.execute("get_screen_state", {}, context, 30)
    except Exception as e:
        log.warning("agent_loop_screen_state_error", error=str(e))
        return "", None
    if not result.success:
        return "", None
    data = result.data or {}
    return data.get("screen_text", "") or "", data.get("screenshot_path")


def _build_user_prompt(
    goal: str,
    screen_state: str,
    history: List[StepExecutionResult],
) -> str:
    history_lines = []
    for h in history:
        status = "ok" if h.success else f"error: {h.error}"
        params_repr = json.dumps(h.data.get("params", {})) if isinstance(h.data, dict) and "params" in (h.data or {}) else ""
        history_lines.append(
            f"- {h.plugin}.{h.action} -> {status}"
        )
    history_block = "\n".join(history_lines) if history_lines else "(sin acciones previas)"

    return (
        f"OBJETIVO:\n{goal}\n\n"
        f"PANTALLA_ACTUAL:\n{screen_state or '(sin contexto visual disponible)'}\n\n"
        f"HISTORIAL:\n{history_block}\n\n"
        f"Responde con el JSON de la siguiente acción a ejecutar (o goal_reached=true si ya está completo)."
    )


def _decision_to_step(decision: LoopDecision, step_index: int) -> Step:
    """Convierte una LoopDecision en un Step ejecutable por el engine."""
    return Step(
        step_id=f"loop_{step_index}",
        plugin=decision.plugin,
        action=decision.action,
        params=decision.params or {},
        timeout_sec=DEFAULT_LOOP_STEP_TIMEOUT_SEC,
        continue_on_error=True,
        depends_on=[],
    )


def _is_decision_valid(decision: LoopDecision) -> tuple[bool, str]:
    """Valida que la decisión apunte a un plugin/acción permitido."""
    if decision.plugin not in ALLOWED_PLUGINS:
        return False, f"plugin '{decision.plugin}' no permitido en bucle agente"
    if not decision.action:
        return False, "action vacía"
    return True, ""


def run_agent_loop(
    goal: str,
    registry: PluginRegistry,
    context: Optional[Dict[str, Any]] = None,
    max_steps: int = MAX_LOOP_STEPS,
    deadline_sec: Optional[float] = None,
) -> AgentLoopResult:
    """Ejecuta el bucle agente visual hasta alcanzar el objetivo o agotar pasos.

    Termina con stopped_reason en {goal_reached, max_steps, error,
    user_cancelled, timeout}.
    """
    if context is None:
        context = {}
    if max_steps is None or max_steps <= 0:
        max_steps = MAX_LOOP_STEPS
    max_steps = min(max_steps, MAX_LOOP_STEPS)

    system_prompt = _load_loop_prompt()
    log.info("agent_loop_start", goal=goal, max_steps=max_steps)

    steps_executed: List[StepExecutionResult] = []
    stopped_reason = "max_steps"
    success = False
    final_screen: Optional[str] = None

    t0 = time.perf_counter()
    abs_deadline = (t0 + deadline_sec) if deadline_sec else None

    for step_index in range(1, max_steps + 1):
        if abs_deadline is not None and time.perf_counter() >= abs_deadline:
            stopped_reason = "timeout"
            break

        screen_state, screenshot_path = _capture_screen_state(registry, context)
        final_screen = screen_state
        user_prompt = _build_user_prompt(goal, screen_state, steps_executed)

        try:
            decision, _stats = call_llm_validated(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                schema=LoopDecision,
                max_retries=2,
            )
        except (LLMValidationError, LLMTimeoutError, LLMError) as e:
            log.error("agent_loop_llm_error", error=str(e), error_type=type(e).__name__)
            stopped_reason = "error"
            break

        log.info(
            "agent_loop_decision",
            step_index=step_index,
            plugin=decision.plugin,
            action=decision.action,
            reason=decision.reason,
            goal_reached=decision.goal_reached,
        )

        if decision.goal_reached:
            stopped_reason = "goal_reached"
            success = True
            break

        valid, reason = _is_decision_valid(decision)
        if not valid:
            log.warning("agent_loop_invalid_decision", reason=reason)
            stopped_reason = "error"
            break

        step = _decision_to_step(decision, step_index)
        step_result = _execute_step(step, registry, context)
        steps_executed.append(step_result)

        if not step_result.success:
            log.warning(
                "agent_loop_step_failed",
                step_index=step_index,
                error=step_result.error,
                error_type=step_result.error_type,
            )

    total_latency_ms = int((time.perf_counter() - t0) * 1000)
    log.info(
        "agent_loop_done",
        goal=goal,
        success=success,
        stopped_reason=stopped_reason,
        steps_count=len(steps_executed),
        total_latency_ms=total_latency_ms,
    )

    return AgentLoopResult(
        goal=goal,
        success=success,
        steps_executed=steps_executed,
        total_latency_ms=total_latency_ms,
        stopped_reason=stopped_reason,
        final_screen_state=final_screen,
    )
