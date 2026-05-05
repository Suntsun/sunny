from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import PlanV2, Step
from sunny.core.plugins.base import PluginResult
from sunny.core.plugins.registry import PluginRegistry

log = get_logger("sunny.core.execution.engine")


@dataclass
class StepExecutionResult:
    step_id: str
    plugin: str
    action: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    latency_ms: int = 0
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class ExecutionResult:
    plan_intent: str
    success: bool
    steps: List[StepExecutionResult] = field(default_factory=list)
    total_latency_ms: int = 0
    early_stopped: bool = False


def execute_plan(
    plan: PlanV2,
    registry: PluginRegistry,
    context: Optional[Dict[str, Any]] = None,
) -> ExecutionResult:
    """Ejecuta un plan contra el registry de plugins."""
    if context is None:
        context = {}

    if plan.intent == "conversation":
        return ExecutionResult(
            plan_intent="conversation",
            success=True,
            steps=[],
            total_latency_ms=0,
            early_stopped=False,
        )

    log.info("execution_start", intent=plan.intent, steps_count=len(plan.steps))

    results: List[StepExecutionResult] = []
    early_stopped = False
    t0 = time.perf_counter()

    for step in plan.steps:
        if early_stopped:
            results.append(
                StepExecutionResult(
                    step_id=step.step_id,
                    plugin=step.plugin,
                    action=step.action,
                    success=False,
                    skipped=True,
                    skip_reason="early_stop",
                )
            )
            continue

        step_result = _execute_step(step, registry, context)
        results.append(step_result)

        if not step_result.success and not step.continue_on_error:
            early_stopped = True
            log.warning(
                "execution_early_stop",
                step_id=step.step_id,
                error=step_result.error,
                error_type=step_result.error_type,
            )

    total_latency_ms = int((time.perf_counter() - t0) * 1000)
    success = not early_stopped

    log.info(
        "execution_done",
        success=success,
        early_stopped=early_stopped,
        total_latency_ms=total_latency_ms,
        steps_executed=len([s for s in results if not s.skipped]),
        steps_skipped=len([s for s in results if s.skipped]),
    )

    return ExecutionResult(
        plan_intent=plan.intent,
        success=success,
        steps=results,
        total_latency_ms=total_latency_ms,
        early_stopped=early_stopped,
    )


def _execute_step(
    step: Step,
    registry: PluginRegistry,
    context: Dict[str, Any],
) -> StepExecutionResult:
    """Ejecuta un step individual con control de timeout."""
    start = time.perf_counter()
    plugin = registry.get(step.plugin)

    if plugin is None:
        elapsed = int((time.perf_counter() - start) * 1000)
        return StepExecutionResult(
            step_id=step.step_id,
            plugin=step.plugin,
            action=step.action,
            success=False,
            error=f"plugin '{step.plugin}' no registrado",
            error_type="PluginNotRegistered",
            latency_ms=elapsed,
        )

    holder: Dict[str, Any] = {"result": None, "error": None}

    def run():
        try:
            holder["result"] = plugin.execute(
                step.action, step.params, context, step.timeout_sec
            )
        except Exception as e:
            holder["error"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=step.timeout_sec)

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    if t.is_alive():
        return StepExecutionResult(
            step_id=step.step_id,
            plugin=step.plugin,
            action=step.action,
            success=False,
            error=f"timeout tras {step.timeout_sec}s",
            error_type="TimeoutError",
            latency_ms=elapsed_ms,
        )

    if holder["error"] is not None:
        err = holder["error"]
        return StepExecutionResult(
            step_id=step.step_id,
            plugin=step.plugin,
            action=step.action,
            success=False,
            error=str(err),
            error_type=type(err).__name__,
            latency_ms=elapsed_ms,
        )

    pr: PluginResult = holder["result"]

    # Conflicto de destino en move/copy: PluginBase captura la excepción antes que nosotros
    if (
        not pr.success
        and pr.error_type == "FileExistsError"
        and step.plugin == "files"
        and step.action in ("move", "copy")
    ):
        from sunny.core.orchestrator.confirmation import ask_conflict_resolution
        from sunny.modules.files import FilesPlugin
        dst = pr.error  # el error es el path del destino
        resolution = ask_conflict_resolution(dst)
        if resolution == "cancel":
            return StepExecutionResult(
                step_id=step.step_id,
                plugin=step.plugin,
                action=step.action,
                success=False,
                error="operación cancelada por el usuario",
                error_type="UserCancelled",
                latency_ms=elapsed_ms,
            )
        new_params = dict(step.params)
        if resolution == "overwrite":
            new_params["overwrite"] = True
        elif resolution == "rename":
            from pathlib import Path
            fp = FilesPlugin()
            new_dst = fp._find_free_name(Path(dst))
            new_params["dst"] = str(new_dst)
        pr2 = plugin.execute(step.action, new_params, context, step.timeout_sec)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return StepExecutionResult(
            step_id=step.step_id,
            plugin=step.plugin,
            action=step.action,
            success=pr2.success,
            data=pr2.data,
            error=pr2.error,
            error_type=pr2.error_type,
            latency_ms=elapsed_ms,
        )

    return StepExecutionResult(
        step_id=step.step_id,
        plugin=step.plugin,
        action=step.action,
        success=pr.success,
        data=pr.data,
        error=pr.error,
        error_type=pr.error_type,
        latency_ms=elapsed_ms,
    )
