from __future__ import annotations

from typing import Set

from rich.console import Console
from rich.panel import Panel

from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import ComprehensionResult, PlanV2

log = get_logger("sunny.core.orchestrator.confirmation")
console = Console()

YES_VALUES: Set[str] = {"s", "si", "sí", "y", "yes"}
NO_VALUES: Set[str] = {"n", "no"}


def ask_yes_no(message: str, default: bool = False) -> bool:
    """Solicita confirmación sí/no al usuario."""
    suffix = "[S/n]" if default else "[s/N]"
    while True:
        resp = input(f"{message} {suffix}: ").strip().lower()
        if resp == "":
            return default
        if resp in YES_VALUES:
            return True
        if resp in NO_VALUES:
            return False


def confirm_comprehension(comprehension: ComprehensionResult) -> bool:
    """Muestra comprensión y pide confirmación."""
    lines = [
        f"[bold]He entendido:[/bold] {comprehension.comprehension}",
        "",
        f"Intención: {comprehension.intent}",
        f"Confianza: {comprehension.confidence:.0%}",
    ]

    if comprehension.assumptions:
        lines.append("Suposiciones:")
        for a in comprehension.assumptions:
            lines.append(f"  - {a}")

    if comprehension.needs_clarification:
        lines.append("[yellow]Necesito aclaración antes de continuar.[/yellow]")

    body = "\n".join(lines)
    console.print(Panel(body, title="Comprensión"))

    if comprehension.needs_clarification:
        log.info("comprehension_clarification_needed", intent=comprehension.intent)
        return False

    ok = ask_yes_no("¿Es correcto?", default=True)
    if ok:
        log.info("comprehension_confirmed", intent=comprehension.intent)
    else:
        log.info("comprehension_rejected", intent=comprehension.intent)
    return ok


def confirm_plan(plan: PlanV2) -> bool:
    """Muestra plan y pide confirmación."""
    lines = ["Voy a ejecutar:", ""]

    for i, step in enumerate(plan.steps, start=1):
        lines.append(f"  {i}. [bold]{step.plugin}.{step.action}[/bold]")
        if step.params:
            lines.append(f"     params: {step.params}")
        if step.depends_on:
            lines.append(f"     depende de: {', '.join(step.depends_on)}")

    body = "\n".join(lines)
    console.print(Panel(body, title=f"Plan ({len(plan.steps)} pasos)"))

    ok = ask_yes_no("¿Ejecutar?", default=False)
    if ok:
        log.info("plan_confirmed", steps_count=len(plan.steps))
    else:
        log.info("plan_rejected", steps_count=len(plan.steps))
    return ok
