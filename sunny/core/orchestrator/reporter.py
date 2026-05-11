from __future__ import annotations

from typing import List, Optional

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sunny.core.execution.engine import ExecutionResult
from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import ComprehensionResult, PlanV2

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


def report_no_plan(plan: PlanV2, user_input: str) -> None:
    """Informa al usuario de que la planificación no produjo pasos ejecutables.

    Cubre dos casos: el planificador pidió aclaración (needs_clarification),
    o devolvió un plan vacío para una intención no conversacional —
    típicamente porque no existe ningún plugin que pueda cumplir la orden
    (p. ej. enviar mensaje por Discord cuando no hay plugin de Discord).
    """
    if plan.needs_clarification:
        body = (
            f"El planificador necesita aclaración para esta orden.\n"
            f"Intención detectada: [bold]{plan.intent}[/bold] "
            f"(confianza {plan.confidence:.0%}).\n\n"
            f"Reformula tu orden con más detalle o concreta qué quieres hacer."
        )
        title = "[yellow]Necesito aclaración[/yellow]"
    else:
        body = (
            f"No hay ninguna acción disponible para la intención "
            f"[bold]{plan.intent}[/bold] a partir de tu orden:\n"
            f"  '{user_input}'\n\n"
            f"Probablemente ningún plugin instalado puede cumplir esta tarea "
            f"(no existe un plugin para esa app, canal o servicio).\n"
            f"Reformúlala con un objetivo que algún plugin pueda ejecutar, "
            f"o registra uno nuevo en sunny/modules/."
        )
        title = "[red]Sin plan ejecutable[/red]"

    console.print(Panel(body, title=title, expand=False))
    log.warning(
        "report_no_plan",
        intent=plan.intent,
        needs_clarification=plan.needs_clarification,
        confidence=plan.confidence,
    )

def _render_semantic_output(result: ExecutionResult) -> None:
    for step in result.steps:
        if step.skipped or not step.success:
            continue

        plugin = step.plugin
        action = step.action

        data = getattr(step, "data", None)
        if data is None:
            continue

        if step.plugin == "files" and step.action == "list_directory":
            _render_list_directory(data)
        elif plugin == "files" and action == "search":
            _render_search(data)
        elif plugin == "files" and action == "read_file":
            _render_read_file(data, step)
        elif plugin == "files" and action == "tree_directory":
            _render_tree_directory(data)
        elif plugin == "files" and action == "get_info":
            _render_get_info(data)
        elif plugin == "files" and action == "write_file":
            _render_write_file(data)
        elif plugin == "files" and action == "create_directory":
            _render_create_directory(data)
        elif plugin == "files" and action == "delete_matching":
            _render_delete_matching(data)
        elif plugin == "os_control" and action == "get_system_info":
            _render_get_system_info(data)
        elif plugin == "os_control" and action == "list_processes":
            _render_list_processes(data)
        elif plugin == "vision" and action == "describe_screen":
            _render_describe_screen(data)
        elif plugin == "vision" and action == "analyze_screen":
            _render_analyze_screen(data)
        elif plugin == "vision" and action == "wait_for_screen_text":
            _render_wait_for_screen_text(data)
        elif plugin == "vision" and action == "get_screen_state":
            _render_get_screen_state(data)
        elif plugin == "agent_loop" and action == "run":
            _render_agent_loop_result(data)

def _render_get_info(data: dict) -> None:
    """Renderiza información de un archivo o carpeta."""
    import datetime
    exists = data.get("exists", False)
    path = data.get("path", "")

    if not exists:
        console.print(f"\n[yellow]No existe:[/yellow] {path}")
        return

    is_dir = data.get("is_dir", False)
    kind = "Carpeta" if is_dir else "Archivo"
    size = _format_size(data.get("size", 0))
    ts = data.get("modified_ts")
    modified = (
        datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")
        if ts else "—"
    )

    table = Table(title=f"Información de {kind}")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")
    table.add_row("Ruta", path)
    table.add_row("Tipo", kind)
    if not is_dir:
        table.add_row("Tamaño", size)
    table.add_row("Modificado", modified)
    console.print(table)

def _render_list_directory(data: dict) -> None:
    directories = data.get("directories", [])
    files = data.get("files", [])

    folder = Path(data.get("path", "")).name or data.get("path", "directorio")
    console.print(f"\n[bold]{folder} contiene:[/bold]\n")

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
        
def _render_search(data) -> None:
    """Renderiza resultados de búsqueda de archivos."""
    if not data:
        console.print("\n[yellow]No se encontraron archivos.[/yellow]")
        return
    table = Table(title=f"Archivos encontrados ({len(data)})")
    table.add_column("Nombre")
    table.add_column("Ruta", style="dim")
    for p in data:
        path_obj = Path(p)
        table.add_row(path_obj.name, str(path_obj))
    console.print(table)

def _render_tree_directory(data: dict) -> None:
    """Renderiza árbol de directorios con Rich Tree."""
    from rich.tree import Tree

    def _build_tree(node: dict, tree) -> None:
        for child in node.get("children") or []:
            if child.get("children") is None:
                size = _format_size(child.get("size", 0))
                tree.add(f"[dim]{child['name']}[/dim] [italic dim]{size}[/italic dim]")
            else:
                branch = tree.add(f"[bold blue]{child['name']}[/bold blue]")
                _build_tree(child, branch)

    root_tree = Tree(f"[bold]{data['name']}[/bold]")
    _build_tree(data, root_tree)
    console.print(root_tree)

def _render_read_file(data: str, step) -> None:
    """Renderiza el contenido de un archivo leído."""
    console.print(Panel(data, title="[bold]Contenido del archivo[/bold]", expand=False))

def _render_list_processes(data: list) -> None:
    """Renderiza lista de procesos en ejecución."""
    table = Table(title=f"Procesos en ejecución ({len(data)})")
    table.add_column("PID", style="dim", justify="right", width=7)
    table.add_column("Nombre")

    # Ordenar por nombre, mostrar todos
    for proc in sorted(data, key=lambda p: (p.get("name") or "").lower()):
        table.add_row(str(proc.get("pid", "")), proc.get("name") or "—")

    console.print(table)


def _render_get_system_info(data: dict) -> None:
    """Renderiza información del sistema."""
    import datetime
    table = Table(title="Información del sistema")
    table.add_column("Campo", style="bold")
    table.add_column("Valor")

    cpu_bar = "█" * int(data.get("cpu_percent", 0) / 5) + "░" * (20 - int(data.get("cpu_percent", 0) / 5))
    mem_bar = "█" * int(data.get("memory_percent", 0) / 5) + "░" * (20 - int(data.get("memory_percent", 0) / 5))

    boot_ts = data.get("boot_time")
    boot_str = datetime.datetime.fromtimestamp(boot_ts).strftime("%d/%m/%Y %H:%M") if boot_ts else "—"

    table.add_row("Sistema", f"{data.get('platform', '—')} {data.get('platform_release', '')}")
    table.add_row("Arquitectura", data.get("architecture", "—"))
    table.add_row("CPUs", str(data.get("cpu_count", "—")))
    table.add_row("CPU uso", f"{data.get('cpu_percent', 0):.1f}%  {cpu_bar}")
    table.add_row(
        "RAM",
        f"{data.get('memory_used_gb', 0):.1f} / {data.get('memory_total_gb', 0):.1f} GB  "
        f"({data.get('memory_percent', 0):.0f}%)  {mem_bar}",
    )
    table.add_row(
        "Disco",
        f"{data.get('disk_used_gb', 0):.1f} / {data.get('disk_total_gb', 0):.1f} GB",
    )
    table.add_row("Encendido desde", boot_str)
    console.print(table)


def _render_write_file(data: dict) -> None:
    path = data.get("path", "")
    size = _format_size(data.get("bytes_written", 0))
    console.print(f"\n[green]Archivo guardado:[/green] {path} ({size})")


def _render_create_directory(data: dict) -> None:
    path = data.get("created", "")
    console.print(f"\n[green]Carpeta creada:[/green] {path}")


def _render_delete_matching(data: dict) -> None:
    deleted = data.get("deleted", [])
    errors = data.get("errors", [])
    count = data.get("count", len(deleted))

    if count == 0:
        console.print("\n[yellow]No se encontraron archivos que coincidieran con el patrón.[/yellow]")
        return

    table = Table(title=f"[green]Eliminados ({count})[/green]")
    table.add_column("Ruta")
    for p in deleted:
        table.add_row(p)
    console.print(table)

    if errors:
        console.print(f"[red]{len(errors)} error(es) al eliminar:[/red]")
        for err in errors:
            console.print(f"  [dim]{err['path']}[/dim]: {err['error']}")


def _render_describe_screen(data: dict) -> None:
    """Renderiza la descripción visual de la pantalla generada por el LLM multimodal."""
    description = data.get("description", "") or ""
    screenshot_path = data.get("screenshot_path", "")
    model_used = data.get("model_used", "llava")

    body = description.strip() if description else "[dim]Sin descripción.[/dim]"

    console.print(
        Panel(
            body,
            title=f"[bold]Descripción de pantalla[/bold] [dim]({model_used})[/dim]",
            expand=False,
        )
    )
    if screenshot_path:
        console.print(f"[dim]Captura: {screenshot_path}[/dim]")


def _render_analyze_screen(data: dict) -> None:
    """Renderiza pregunta y respuesta del análisis visual de la pantalla."""
    question = data.get("question", "") or ""
    answer = data.get("answer", "") or ""
    screenshot_path = data.get("screenshot_path", "")
    model_used = data.get("model_used", "llava")

    body_parts = []
    if question:
        body_parts.append(f"[bold]Pregunta:[/bold] {question}")
    body_parts.append("")
    body_parts.append(
        f"[bold]Respuesta:[/bold] {answer.strip() if answer else '[dim]Sin respuesta.[/dim]'}"
    )

    console.print(
        Panel(
            "\n".join(body_parts),
            title=f"[bold]Análisis de pantalla[/bold] [dim]({model_used})[/dim]",
            expand=False,
        )
    )
    if screenshot_path:
        console.print(f"[dim]Captura: {screenshot_path}[/dim]")


def _render_wait_for_screen_text(data: dict) -> None:
    """Renderiza resultado de espera por texto en pantalla."""
    found = bool(data.get("found", False))
    text = data.get("text", "")
    elapsed = data.get("elapsed_sec", 0)
    attempts = data.get("attempts", 0)

    if found:
        body = f'[green]✔[/green] Texto encontrado: "{text}" — {elapsed}s / {attempts} intentos'
    else:
        body = f'[yellow]⚠[/yellow] Texto "{text}" no apareció en {elapsed}s ({attempts} intentos)'
    console.print(Panel(body, title="[bold]Esperando texto[/bold]", expand=False))


def _render_get_screen_state(data: dict) -> None:
    """Renderiza el estado raw OCR de la pantalla."""
    screen_text = data.get("screen_text", "") or "[dim]Sin texto detectado.[/dim]"
    latency = data.get("latency_ms", 0)
    console.print(
        Panel(
            screen_text,
            title=f"[bold]Estado de pantalla[/bold] [dim]({latency} ms)[/dim]",
            expand=False,
        )
    )


def _render_agent_loop_result(data: dict) -> None:
    """Renderiza tabla de pasos ejecutados por el bucle agente."""
    goal = data.get("goal", "")
    success = bool(data.get("success", False))
    stopped_reason = data.get("stopped_reason", "")
    steps = data.get("steps_executed", []) or []
    total_latency = data.get("total_latency_ms", 0)

    title_color = "green" if success else "yellow"
    title = f"[{title_color}]Bucle agente — {stopped_reason}[/{title_color}]"
    table = Table(title=title)
    table.add_column("#", style="dim", width=3)
    table.add_column("Acción")
    table.add_column("Resultado")
    table.add_column("Latencia")

    for i, step in enumerate(steps, start=1):
        plugin = step.get("plugin", "")
        action = step.get("action", "")
        ok = bool(step.get("success", False))
        err = step.get("error") or ""
        latency = step.get("latency_ms", 0)
        if ok:
            table.add_row(str(i), f"{plugin}.{action}", "[green]✔[/green]", f"{latency} ms")
        else:
            table.add_row(str(i), f"{plugin}.{action}", f"[red]✗ {err}[/red]", f"{latency} ms")

    console.print(Panel(f"Objetivo: {goal}", expand=False))
    if steps:
        console.print(table)
    else:
        console.print("[dim]Sin acciones ejecutadas en el bucle.[/dim]")
    console.print(f"[dim]Total bucle: {total_latency} ms[/dim]")


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024**2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024**3:
        return f"{size / (1024**2):.1f} MB"
    else:
        return f"{size / (1024**3):.1f} GB"
