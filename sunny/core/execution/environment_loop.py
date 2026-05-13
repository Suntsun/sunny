"""Bucle continuo perception → reasoner → controller.

Estructura paralela a ``agent_loop.run_agent_loop`` pero pensada para
entornos vivos (productividad reactiva, monitorización, eventualmente
juegos) donde el estado cambia mientras el agente trabaja, en vez de
para tareas de un solo turno.

Reparto de roles:
- PERCEPTION  (M5) — RESERVADO. En este esqueleto la observación se
  construye por código puro (sin LLM) a partir del plugin ``vision``.
  El slot existe en factory para cuando alguien quiera percepción
  LLM/visión.
- REASONER    (M6) — decide el siguiente PASO ESTRATÉGICO de alto nivel
  dado el objetivo + observación + último paso.
- CONTROLLER  (M7) — traduce el paso estratégico a una ``ConcreteAction``
  ejecutable por un plugin (``gui`` / ``vision`` / ``os_control``).

PERCEPTION lee texto OCR, no píxeles. Soporte de modelo de visión es
un refactor posterior cuando un provider exponga ese path.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from sunny.brain.factory import BrainRole, get_provider_for_role
from sunny.brain.ollama_client import (
    LLMError,
    LLMTimeoutError,
    LLMValidationError,
)
from sunny.core.execution.engine import StepExecutionResult, _execute_step
from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import Step
from sunny.core.plugins.registry import PluginRegistry
from sunny.core.prompts.loader import load_system_prompt

log = get_logger("sunny.core.execution.environment_loop")

MAX_ENV_LOOP_STEPS: int = 60
DEFAULT_TICK_INTERVAL_SEC: float = 0.5
DEFAULT_STEP_TIMEOUT_SEC: int = 30
ALLOWED_PLUGINS: tuple = ("gui", "vision", "os_control")


class Observation(BaseModel):
    """Estado del entorno construido por la fase de percepción."""

    tick: int = 0
    timestamp: float = 0.0
    window_title: str = ""
    screen_text: str = ""
    screen_hash: str = ""
    changed_since_last: bool = True


class StrategicStep(BaseModel):
    """Decisión de alto nivel del reasoner."""

    intent: str = ""
    target: str = ""
    done: bool = False
    reason: str = ""


class ConcreteAction(BaseModel):
    """Acción concreta producida por el controller, ejecutable por un plugin."""

    plugin: str = ""
    action: str = ""
    params: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


@dataclass
class EnvironmentLoopResult:
    goal: str
    success: bool
    ticks_executed: int = 0
    steps_executed: List[StepExecutionResult] = field(default_factory=list)
    total_latency_ms: int = 0
    stopped_reason: str = "max_steps"
    final_observation: Optional[Observation] = None


def _build_observation(
    registry: PluginRegistry,
    context: Dict[str, Any],
    tick: int,
    prev_hash: str,
) -> Observation:
    """Construye un ``Observation`` desde el plugin vision (sin LLM).

    Si vision no está disponible o falla, devuelve una observación vacía
    para que el reasoner razone sobre "no veo nada" en lugar de cascar.
    """
    now = time.perf_counter()
    vision = registry.get("vision")
    if vision is None:
        return Observation(tick=tick, timestamp=now, changed_since_last=tick == 0)

    try:
        result = vision.execute("get_screen_state", {}, context, 30)
    except Exception as e:
        log.warning("environment_loop_vision_error", error=str(e))
        return Observation(tick=tick, timestamp=now, changed_since_last=tick == 0)

    if not result.success:
        return Observation(tick=tick, timestamp=now, changed_since_last=tick == 0)

    data = result.data or {}
    screen_text = (data.get("screen_text") or "").strip()
    window_title = (data.get("window_title") or "").strip()
    screen_hash = hashlib.sha1(
        f"{window_title}\n{screen_text}".encode("utf-8", errors="ignore")
    ).hexdigest()[:16]

    return Observation(
        tick=tick,
        timestamp=now,
        window_title=window_title,
        screen_text=screen_text,
        screen_hash=screen_hash,
        changed_since_last=(screen_hash != prev_hash),
    )


def _should_consult_reasoner(
    prev_obs: Optional[Observation],
    new_obs: Observation,
    tick: int,
) -> bool:
    """Decide si llamar al reasoner en este tick.

    TODO: política de gating real (p.ej. saltar reasoner si la observación
    no ha cambiado y el último step seguía siendo válido). En el esqueleto
    consultamos cada tick para mantener determinismo en tests.
    """
    return True


def _build_reasoner_prompt(
    goal: str,
    observation: Observation,
    prev_step: Optional[StrategicStep],
) -> str:
    prev_block = "(ninguno)" if prev_step is None else (
        f"intent={prev_step.intent!r}, target={prev_step.target!r}, "
        f"reason={prev_step.reason!r}"
    )
    return (
        f"OBJETIVO:\n{goal}\n\n"
        f"OBSERVACIÓN (tick {observation.tick}):\n"
        f"- window_title: {observation.window_title or '(sin título)'}\n"
        f"- screen_text:\n{observation.screen_text or '(sin OCR)'}\n"
        f"- cambió desde último tick: {observation.changed_since_last}\n\n"
        f"ÚLTIMO PASO ESTRATÉGICO:\n{prev_block}\n\n"
        f"Devuelve el JSON del siguiente paso estratégico."
    )


def _build_controller_prompt(
    strategic_step: StrategicStep,
    observation: Observation,
) -> str:
    return (
        f"PASO ESTRATÉGICO:\n"
        f"- intent: {strategic_step.intent}\n"
        f"- target: {strategic_step.target}\n"
        f"- reason: {strategic_step.reason}\n\n"
        f"OBSERVACIÓN (tick {observation.tick}):\n"
        f"- window_title: {observation.window_title or '(sin título)'}\n"
        f"- screen_text:\n{observation.screen_text or '(sin OCR)'}\n\n"
        f"Devuelve el JSON de la acción concreta."
    )


def _consult_reasoner(
    goal: str,
    observation: Observation,
    prev_step: Optional[StrategicStep],
    system_prompt: str,
) -> Tuple[StrategicStep, bool]:
    """Llama al REASONER. Devuelve (step, llm_ok)."""
    provider = get_provider_for_role(BrainRole.REASONER)
    user_prompt = _build_reasoner_prompt(goal, observation, prev_step)
    try:
        step, _stats = provider.call_validated(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            schema=StrategicStep,
            max_retries=2,
        )
        return step, True
    except (LLMValidationError, LLMTimeoutError, LLMError) as e:
        log.error(
            "environment_loop_reasoner_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return StrategicStep(), False


def _consult_controller(
    strategic_step: StrategicStep,
    observation: Observation,
    system_prompt: str,
) -> Tuple[ConcreteAction, bool]:
    """Llama al CONTROLLER. Devuelve (action, llm_ok)."""
    provider = get_provider_for_role(BrainRole.CONTROLLER)
    user_prompt = _build_controller_prompt(strategic_step, observation)
    try:
        action, _stats = provider.call_validated(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            schema=ConcreteAction,
            max_retries=2,
        )
        return action, True
    except (LLMValidationError, LLMTimeoutError, LLMError) as e:
        log.error(
            "environment_loop_controller_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return ConcreteAction(), False


def _action_to_step(action: ConcreteAction, tick: int) -> Step:
    return Step(
        step_id=f"env_{tick}",
        plugin=action.plugin,
        action=action.action,
        params=action.params or {},
        timeout_sec=DEFAULT_STEP_TIMEOUT_SEC,
        continue_on_error=True,
        depends_on=[],
    )


def _is_action_valid(action: ConcreteAction) -> Tuple[bool, str]:
    if action.plugin not in ALLOWED_PLUGINS:
        return False, f"plugin '{action.plugin}' no permitido"
    if not action.action:
        return False, "action vacía"
    return True, ""


def run_environment_loop(
    goal: str,
    registry: PluginRegistry,
    context: Optional[Dict[str, Any]] = None,
    max_steps: int = MAX_ENV_LOOP_STEPS,
    tick_interval_sec: float = DEFAULT_TICK_INTERVAL_SEC,
    deadline_sec: Optional[float] = None,
) -> EnvironmentLoopResult:
    """Ejecuta el bucle de entorno continuo hasta cumplir objetivo o cortar.

    ``stopped_reason`` ∈ {goal_reached, max_steps, timeout, error,
    user_cancelled}.

    NO consume PERCEPTION (slot reservado); la observación se construye
    por código puro desde el plugin ``vision``.
    """
    if context is None:
        context = {}
    if max_steps is None or max_steps <= 0:
        max_steps = MAX_ENV_LOOP_STEPS
    max_steps = min(max_steps, MAX_ENV_LOOP_STEPS)

    reasoner_prompt = load_system_prompt("reasoner_v1")
    controller_prompt = load_system_prompt("controller_v1")
    log.info("environment_loop_start", goal=goal, max_steps=max_steps)

    steps_executed: List[StepExecutionResult] = []
    stopped_reason = "max_steps"
    success = False
    final_obs: Optional[Observation] = None
    prev_obs: Optional[Observation] = None
    prev_step: Optional[StrategicStep] = None
    prev_hash = ""

    t0 = time.perf_counter()
    abs_deadline = (t0 + deadline_sec) if deadline_sec else None

    ticks_executed = 0
    for tick in range(1, max_steps + 1):
        if abs_deadline is not None and time.perf_counter() >= abs_deadline:
            stopped_reason = "timeout"
            break

        obs = _build_observation(registry, context, tick, prev_hash)
        final_obs = obs
        ticks_executed = tick

        if _should_consult_reasoner(prev_obs, obs, tick):
            step, ok = _consult_reasoner(goal, obs, prev_step, reasoner_prompt)
            if not ok:
                stopped_reason = "error"
                break
        else:
            step = prev_step or StrategicStep()

        log.info(
            "environment_loop_reasoner_step",
            tick=tick,
            intent=step.intent,
            target=step.target,
            done=step.done,
        )

        if step.done:
            stopped_reason = "goal_reached"
            success = True
            break

        action, ok = _consult_controller(step, obs, controller_prompt)
        if not ok:
            stopped_reason = "error"
            break

        valid, reason = _is_action_valid(action)
        if not valid:
            log.warning(
                "environment_loop_invalid_action",
                tick=tick,
                reason=reason,
                plugin=action.plugin,
                action=action.action,
            )
            stopped_reason = "error"
            break

        executable = _action_to_step(action, tick)
        result = _execute_step(executable, registry, context)
        steps_executed.append(result)

        log.info(
            "environment_loop_action",
            tick=tick,
            plugin=action.plugin,
            action=action.action,
            success=result.success,
        )

        prev_obs = obs
        prev_step = step
        prev_hash = obs.screen_hash

        if tick_interval_sec > 0 and tick < max_steps:
            # Respeta el ritmo configurado entre ticks. En tests se pasa 0.
            time.sleep(tick_interval_sec)

    total_latency_ms = int((time.perf_counter() - t0) * 1000)
    log.info(
        "environment_loop_done",
        goal=goal,
        success=success,
        stopped_reason=stopped_reason,
        ticks_executed=ticks_executed,
        steps_count=len(steps_executed),
        total_latency_ms=total_latency_ms,
    )

    return EnvironmentLoopResult(
        goal=goal,
        success=success,
        ticks_executed=ticks_executed,
        steps_executed=steps_executed,
        total_latency_ms=total_latency_ms,
        stopped_reason=stopped_reason,
        final_observation=final_obs,
    )
