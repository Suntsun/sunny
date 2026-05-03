from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import PlanV2, Step

log = get_logger("sunny.core.orchestrator.validator")

PLUGIN_CATALOG: Dict[str, Set[str]] = {
    "files": {
        "read_file", "write_file", "list_directory", "move", "copy",
        "delete", "search", "get_info", "empty_recycle_bin",
        "restore_from_recycle_bin", "create_directory",
    },
    "os_control": {
        "open_app", "close_app", "list_processes", "kill_process",
        "set_volume", "mute", "lock_screen", "shutdown", "restart",
        "get_system_info", "sleep_seconds",
    },
    "vision": {
        "screenshot", "read_screen_text", "find_on_screen",
    },
    "gui": {
        "click", "click_on_text", "type_text", "press_key",
        "move_mouse", "scroll", "drag",
    },
    "ai_bridge": {
        "ask_external",
    },
}

CONFIRM_REQUIRED_ACTIONS: Dict[str, Set[str]] = {
    "files": {"write_file", "move", "copy", "delete", "empty_recycle_bin"},
    "os_control": {"kill_process", "shutdown", "restart"},
}

ACTION_SIGNATURES: Dict[str, Dict[str, List[str]]] = {
    "files": {
        "read_file": ["path"],
        "write_file": ["path", "content"],
        "list_directory": ["path"],
        "move": ["src", "dst"],
        "copy": ["src", "dst"],
        "delete": ["path"],
        "search": ["directory", "pattern"],
        "get_info": ["path"],
        "empty_recycle_bin": [],
        "restore_from_recycle_bin": ["filename"],
        "create_directory": ["path"],
    },
    "os_control": {
        "open_app": ["app"],
        "close_app": ["app"],
        "list_processes": [],
        "kill_process": ["pid"],
        "set_volume": ["level"],
        "mute": ["state"],
        "lock_screen": [],
        "shutdown": ["delay_sec"],
        "restart": ["delay_sec"],
        "get_system_info": [],
        "sleep_seconds": ["seconds"],
    },
    "vision": {
        "screenshot": [],
        "read_screen_text": [],
        "find_on_screen": ["target"],
    },
    "gui": {
        "click": ["x", "y"],
        "click_on_text": ["text"],
        "type_text": ["text"],
        "press_key": ["key"],
        "move_mouse": ["x", "y"],
        "scroll": ["direction", "amount"],
        "drag": ["from_x", "from_y", "to_x", "to_y"],
    },
    "ai_bridge": {
        "ask_external": ["provider", "prompt"],
    },
}

BULK_THRESHOLD: int = 5


@dataclass
class ValidationResult:
    """Resultado de validación de un plan."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    effective_requires_confirmation: bool = False


def validate_plan(plan: PlanV2) -> ValidationResult:
    """Valida un plan contra catálogo y reglas de seguridad."""
    if plan.intent == "conversation":
        return ValidationResult(valid=True)

    errors: List[str] = []
    warnings: List[str] = []

    for step in plan.steps:
        if step.plugin not in PLUGIN_CATALOG:
            errors.append(
                f"step '{step.step_id}': plugin desconocido '{step.plugin}'"
            )
            continue

        if step.action not in PLUGIN_CATALOG[step.plugin]:
            errors.append(
                f"step '{step.step_id}': action '{step.action}' no existe en plugin '{step.plugin}'"
            )
            continue

        required = ACTION_SIGNATURES.get(step.plugin, {}).get(step.action, [])
        missing = [p for p in required if p not in step.params]
        if missing:
            errors.append(
                f"step '{step.step_id}': params requeridos faltantes en "
                f"'{step.plugin}.{step.action}': {missing}"
            )

    effective_requires_confirmation = False

    if any(_is_destructive(s) for s in plan.steps):
        effective_requires_confirmation = True

    if len(plan.steps) > BULK_THRESHOLD:
        effective_requires_confirmation = True

    if effective_requires_confirmation and not plan.requires_confirmation:
        warnings.append(
            "plan contiene acciones destructivas o lote masivo, pero el LLM marcó requires_confirmation=False; se forzará a True"
        )

    result = ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        effective_requires_confirmation=effective_requires_confirmation,
    )

    log.info(
        "plan_validated",
        valid=result.valid,
        errors_count=len(errors),
        warnings_count=len(warnings),
        effective_requires_confirmation=effective_requires_confirmation,
        intent=plan.intent,
        steps_count=len(plan.steps),
    )

    return result


def _is_destructive(step: Step) -> bool:
    """Determina si un step es destructivo."""
    return (
        step.plugin in CONFIRM_REQUIRED_ACTIONS
        and step.action in CONFIRM_REQUIRED_ACTIONS[step.plugin]
    )
