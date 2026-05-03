from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from sunny.brain.ollama_client import LLMError
from sunny.core.execution import engine as _engine
from sunny.core.execution.engine import ExecutionResult
from sunny.core.logging.logger import configure_logging, get_logger
from sunny.core.memory.sqlite import init_db
from sunny.core.orchestrator import (
    comprehension as _comprehension,
    confirmation as _confirmation,
    conversation as _conversation,
    planner as _planner,
    reporter as _reporter,
    validator as _validator,
)
from sunny.core.plugins.registry import PluginRegistry
from sunny.core.session import manager as session
from sunny.modules.ai_bridge.plugin import AIBridgePlugin
from sunny.modules.files import FilesPlugin
from sunny.modules.gui import GuiPlugin
from sunny.modules.os_control import OSControlPlugin
from sunny.modules.vision import VisionPlugin

log = get_logger("sunny.cli")
console = Console()
app = typer.Typer(help="sunny — orquestador personal de escritorio")


def _build_registry() -> PluginRegistry:
    """Construye el registro de plugins."""
    registry = PluginRegistry()
    registry.register(FilesPlugin())
    registry.register(OSControlPlugin())
    registry.register(VisionPlugin())
    registry.register(GuiPlugin())
    registry.register(AIBridgePlugin())
    return registry


def _process_one(user_input: str, registry: PluginRegistry) -> None:
    """Procesa un turno completo."""
    try:
        comp_result, _ = _comprehension.comprehend(user_input)

        if not _confirmation.confirm_comprehension(comp_result):
            if comp_result.needs_clarification:
                _reporter.report_clarification(comp_result)
            else:
                _reporter.report_user_cancelled("comprensión rechazada")
            return

        plan_result, _ = _planner.plan(user_input, comp_result)

        if plan_result.intent == "conversation":
            text, _ = _conversation.converse(user_input)
            conv_exec = ExecutionResult(
                plan_intent="conversation",
                success=True,
                steps=[],
                total_latency_ms=0,
                early_stopped=False,
            )
            _reporter.report_execution(conv_exec, conversation_text=text)
            session.append_turn(user_input, text)
            return

        validation = _validator.validate_plan(plan_result)
        if not validation.valid:
            _reporter.report_validation_errors(validation.errors)
            return

        if validation.effective_requires_confirmation:
            if not _confirmation.confirm_plan(plan_result):
                _reporter.report_user_cancelled("plan rechazado")
                return

        result = _engine.execute_plan(plan_result, registry)

        _reporter.report_execution(result)

        summary = f"ejecutado: {len(result.steps)} steps, success={result.success}"
        session.append_turn(user_input, summary)

    except LLMError as e:
        console.print(f"[red]Error LLM: {e}[/red]")
        log.error("cli_llm_error", error_type=type(e).__name__, error_msg=str(e))
    except Exception as e:
        console.print(f"[red]Error inesperado: {e}[/red]")
        log.error("cli_unexpected_error", error_type=type(e).__name__, error_msg=str(e))


def _repl(registry: PluginRegistry) -> None:
    """Modo interactivo."""
    console.print("[green]sunny REPL[/green] — escribe tu orden. 'exit' / 'quit' / 'salir' / Ctrl+C para salir.")
    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Adiós.[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "salir"):
            console.print("[dim]Adiós.[/dim]")
            break

        _process_one(user_input, registry)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    order: Optional[str] = typer.Argument(None),
    new_session: bool = typer.Option(False, "--new-session"),
    end_session: bool = typer.Option(False, "--end-session"),
) -> None:
    """Entrada principal CLI."""
    if ctx.invoked_subcommand is not None:
        return

    configure_logging()
    init_db()

    if end_session:
        session.end_session()
        console.print("[yellow]Sesión finalizada.[/yellow]")
        return

    if new_session:
        sid = session.force_new_session()
        console.print(f"[green]Nueva sesión iniciada: {sid}[/green]")
    else:
        session.get_or_create_active_session()

    registry = _build_registry()

    if order:
        _process_one(order, registry)
    else:
        _repl(registry)


if __name__ == "__main__":
    app()
