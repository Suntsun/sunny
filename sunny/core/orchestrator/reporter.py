from __future__ import annotations

from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sunny.core.execution.engine import ExecutionResult
from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import ComprehensionResult

log = get_logger("sunny.core.orchestrator.reporter")
console = Console()


def report_execution(
    result: ExecutionResult,
    conversation_text: Optional[str] = None,
) -> None:
    if result.plan_intent == "conversation":
        if conversation_text:
            console.print(conversation_text)
        log.info("report_conversation", length=len(conversation_text or ""))
        return

    # 1. Render semántico
    _render_semantic_output(result)

    # 2. Crear tabla (ESTO FALTA EN TU CÓDIGO)
    title = "[green]Ejecución completada[/green]" if result.success else "[red]Ejecución fallida[/red]"
    table = Table(title=title)

    table.add_column("#", style="dim", width=3)
    table.add_column("Paso")
    table.add_column("Resultado")
    table.add_column("Latencia")

    # 3. Poblar tabla
    for i, step in enumerate(result.steps, start=1):
        if step.skipped:
            table.add_row("—", f"{step.plugin}.{step.action}", "[yellow]omitido[/yellow]", "—")
        elif step.success:
            table.add_row(str(i), f"{step.plugin}.{step.action}", "[green]✔[/green]", f"{step.latency_ms} ms")
        else:
            table.add_row(str(i), f"{step.plugin}.{step.action}", f"[red]✗ {step.error}[/red]", f"{step.latency_ms} ms")

    # 4. Mostrar tabla
    console.print(table)

    ok = len([s for s in result.steps if s.success])
    fail = len([s for s in result.steps if not s.success and not s.skipped])
    skipped = len([s for s in result.steps if s.skipped])

    console.print(
        f"[dim]Total: {result.total_latency_ms} ms — {ok} ok / {fail} fallos / {skipped} omitidos[/dim]"
    )

    log.info(
        "report_execution",
        success=result.success,
        early_stopped=result.early_stopped,
        steps_count=len(result.steps),
        latency_ms=result.total_latency_ms,
    )


def report_clarification(comprehension: ComprehensionResult) -> None:
    """Muestra solicitud de aclaración."""
    console.print(Panel(comprehension.comprehension, title="[yellow]Necesito aclaración[/yellow]"))
    log.info("report_clarification", intent=comprehension.intent)


def report_user_cancelled(reason: str = "operación cancelada") -> None:
    """Muestra cancelación por el usuario."""
    console.print(f"[yellow]Operación cancelada por el usuario ({reason}).[/yellow]")
    log.info("report_user_cancelled", reason=reason)


def report_validation_errors(errors: List[str]) -> None:
    """Muestra errores de validación."""
    body = "\n".join(f"  - {e}" for e in errors)
    console.print(Panel(body, title="[red]Plan inválido[/red]"))
    log.warning("report_validation_errors", errors_count=len(errors))

def _render_semantic_output(result: ExecutionResult) -> None:
    for step in result.steps:
        if step.skipped or not step.success:
            continue

        plugin = step.plugin
        action = step.action

        data = getattr(step, "data", None)
        if not data:
            continue

        if step.plugin == "files" and step.action == "list_directory":
            _render_list_directory(data)
        
def _render_list_directory(data: dict) -> None:
    directories = data.get("directories", [])
    files = data.get("files", [])

    console.print("\n[bold]Tu escritorio tiene:[/bold]\n")

    if directories:
        table_dirs = Table(title=f"Carpetas ({len(directories)})")
        table_dirs.add_column("Nombre")

        for d in directories:
            table_dirs.add_row(d["name"])

        console.print(table_dirs)

    if files:
        table_files = Table(title=f"Archivos ({len(files)})")
        table_files.add_column("Nombre")
        table_files.add_column("Tamaño", justify="right")

        for f in files:
            size = _format_size(f.get("size", 0))
            table_files.add_row(f["name"], size)

        console.print(table_files)
        
def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024**2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024**3:
        return f"{size / (1024**2):.1f} MB"
    else:
        return f"{size / (1024**3):.1f} GB"
        