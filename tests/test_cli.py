import typer
import pytest
from unittest.mock import MagicMock

from sunny import cli
from sunny.core.execution.engine import ExecutionResult, StepExecutionResult
from sunny.core.models.plan import ComprehensionResult, PlanV2, Step
from sunny.core.orchestrator.validator import ValidationResult


def _comp(intent="files", needs_clarification=False):
    return ComprehensionResult(comprehension="x", intent=intent, assumptions=[], confidence=0.9, needs_clarification=needs_clarification)


def _plan(intent="files"):
    steps = [] if intent == "conversation" else [
        Step(step_id="s1", plugin="files", action="read_file", params={"path": "x"})
    ]
    return PlanV2(intent=intent, confidence=0.9, steps=steps)


def _exec_result(success=True):
    return ExecutionResult(
        plan_intent="files",
        success=success,
        steps=[StepExecutionResult(step_id="s1", plugin="files", action="read_file", success=success, latency_ms=10)],
        total_latency_ms=10,
        early_stopped=not success,
    )


@pytest.fixture
def mocked(monkeypatch):
    state = {
        "comprehend": (_comp(), None),
        "plan": (_plan(), None),
        "converse": ("respuesta natural", None),
        "validate": ValidationResult(True, [], [], False),
        "execute": _exec_result(),
        "confirm_comp": True,
        "confirm_plan": True,
    }
    calls = {"reports": [], "session": []}

    monkeypatch.setattr(cli._comprehension, "comprehend", lambda u: state["comprehend"])
    monkeypatch.setattr(cli._planner, "plan", lambda u, c: state["plan"])
    monkeypatch.setattr(cli._conversation, "converse", lambda u: state["converse"])
    monkeypatch.setattr(cli._validator, "validate_plan", lambda p: state["validate"])
    monkeypatch.setattr(cli._engine, "execute_plan", lambda p, r, context=None: state["execute"])
    monkeypatch.setattr(cli._confirmation, "confirm_comprehension", lambda c: state["confirm_comp"])
    monkeypatch.setattr(cli._confirmation, "confirm_plan", lambda p: state["confirm_plan"])
    # Por defecto, simulamos TTY para preservar la semántica de los tests previos a DEP-38.
    # Los tests que requieran non-TTY deben re-monkeypatchear este helper.
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: True)

    monkeypatch.setattr(cli._reporter, "report_execution", lambda r, conversation_text=None: calls["reports"].append(("execution", r, conversation_text)))
    monkeypatch.setattr(cli._reporter, "report_clarification", lambda c: calls["reports"].append(("clarification", c)))
    monkeypatch.setattr(cli._reporter, "report_user_cancelled", lambda r="...": calls["reports"].append(("cancelled", r)))
    monkeypatch.setattr(cli._reporter, "report_validation_errors", lambda e: calls["reports"].append(("validation_errors", e)))
    monkeypatch.setattr(cli._reporter, "report_no_plan", lambda p, u: calls["reports"].append(("no_plan", p, u)))

    monkeypatch.setattr(cli.session, "append_turn", lambda u, a: calls["session"].append((u, a)))

    return state, calls


def test_build_registry_has_all_five_plugins():
    r = cli._build_registry()
    assert sorted(r.list_plugins()) == ["ai_bridge", "files", "gui", "os_control", "vision"]


def test_process_one_files_success_no_confirmation(mocked):
    state, calls = mocked
    cli._process_one("x", None)
    assert calls["reports"][-1][0] == "execution"
    assert calls["session"]


def test_process_one_files_success_with_confirmation(mocked):
    state, calls = mocked
    state["validate"] = ValidationResult(True, [], [], True)
    cli._process_one("x", None)
    assert any(r[0] == "execution" for r in calls["reports"])


def test_process_one_user_rejects_comprehension(mocked):
    state, calls = mocked
    state["confirm_comp"] = False
    cli._process_one("x", None)
    assert any(r[0] == "cancelled" for r in calls["reports"])


def test_process_one_clarification_needed(mocked):
    state, calls = mocked
    state["confirm_comp"] = False
    state["comprehend"] = (_comp(needs_clarification=True), None)
    cli._process_one("x", None)
    assert any(r[0] == "clarification" for r in calls["reports"])


def test_process_one_validation_errors(mocked):
    state, calls = mocked
    state["validate"] = ValidationResult(False, ["e1"], [], False)
    cli._process_one("x", None)
    assert any(r[0] == "validation_errors" for r in calls["reports"])


def test_process_one_user_rejects_plan(mocked):
    state, calls = mocked
    state["validate"] = ValidationResult(True, [], [], True)
    state["confirm_plan"] = False
    cli._process_one("x", None)
    assert any(r[0] == "cancelled" for r in calls["reports"])


def test_process_one_plan_needs_clarification_reports_no_plan(mocked):
    state, calls = mocked
    state["plan"] = (
        PlanV2(
            intent="ai_bridge",
            confidence=0.9,
            needs_clarification=True,
            steps=[],
        ),
        None,
    )
    cli._process_one("escribe a aafturo por discord", None)
    no_plan = [r for r in calls["reports"] if r[0] == "no_plan"]
    assert len(no_plan) == 1
    assert no_plan[0][2] == "escribe a aafturo por discord"
    assert not any(r[0] == "execution" for r in calls["reports"])
    assert calls["session"]


def test_process_one_conversation_path(mocked):
    state, calls = mocked
    state["plan"] = (_plan(intent="conversation"), None)
    state["comprehend"] = (_comp(intent="conversation"), None)
    cli._process_one("x", None)
    assert any(r[0] == "execution" and r[2] == "respuesta natural" for r in calls["reports"])
    assert calls["session"]


def test_process_one_handles_llm_error(mocked, monkeypatch):
    monkeypatch.setattr(cli._comprehension, "comprehend", lambda u: (_ for _ in ()).throw(cli.LLMError("fail")))
    cli._process_one("x", None)


def test_process_one_handles_unexpected_error(mocked, monkeypatch):
    monkeypatch.setattr(cli._engine, "execute_plan", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    cli._process_one("x", None)


def test_main_with_order_calls_process_one(monkeypatch):
    ctx = MagicMock()
    ctx.invoked_subcommand = None

    monkeypatch.setattr(cli, "configure_logging", lambda **kw: None)
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli.session, "get_or_create_active_session", lambda: "sid")
    monkeypatch.setattr(cli, "_build_registry", lambda: None)

    called = []
    monkeypatch.setattr(cli, "_process_one", lambda u, r, yes=False: called.append(u))

    cli.main(ctx=ctx, order="hola", new_session=False, end_session=False, verbose=False, yes=False)

    assert "hola" in called


def test_main_end_session_calls_session_end(monkeypatch):
    ctx = MagicMock()
    ctx.invoked_subcommand = None

    monkeypatch.setattr(cli, "configure_logging", lambda **kw: None)
    monkeypatch.setattr(cli, "init_db", lambda: None)

    called = []
    monkeypatch.setattr(cli.session, "end_session", lambda: called.append(True))

    cli.main(ctx=ctx, order=None, new_session=False, end_session=True, verbose=False)

    assert called


def test_main_new_session_forces_new(monkeypatch):
    ctx = MagicMock()
    ctx.invoked_subcommand = None

    monkeypatch.setattr(cli, "configure_logging", lambda **kw: None)
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli.session, "force_new_session", lambda: "new-id")
    monkeypatch.setattr(cli, "_build_registry", lambda: None)
    monkeypatch.setattr(cli, "_process_one", lambda u, r, yes=False: None)

    cli.main(ctx=ctx, order="hi", new_session=True, end_session=False, verbose=False, yes=False)


# --- DEP-38: --yes + plan destructivo + non-TTY → typer.Exit limpio ----------

def _destructive_plan() -> PlanV2:
    return PlanV2(
        intent="files",
        confidence=0.95,
        steps=[Step(step_id="s1", plugin="files", action="delete", params={"path": "x.txt"})],
    )


def test_yes_flag_aborts_cleanly_when_plan_is_destructive_in_non_tty(mocked, monkeypatch):
    """DEP-38: stdin no-TTY + plan destructivo debe abortar con typer.Exit(2), no EOFError."""
    state, calls = mocked
    state["validate"] = ValidationResult(True, [], [], True)
    state["plan"] = (_destructive_plan(), None)
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: False)

    with pytest.raises(typer.Exit) as exc_info:
        cli._process_one("borra x.txt", None, yes=True)

    assert exc_info.value.exit_code == 2
    assert not any(r[0] == "execution" for r in calls["reports"])
    assert not any(r[0] == "cancelled" for r in calls["reports"])


def test_destructive_plan_with_tty_still_asks_confirmation(mocked, monkeypatch):
    """En TTY el flujo destructivo sigue pidiendo confirmación interactiva (sin regresión)."""
    state, calls = mocked
    state["validate"] = ValidationResult(True, [], [], True)
    state["plan"] = (_destructive_plan(), None)
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: True)
    state["confirm_plan"] = True
    cli._process_one("borra x.txt", None, yes=True)
    assert any(r[0] == "execution" for r in calls["reports"])


def test_destructive_plan_non_tty_without_yes_also_aborts(mocked, monkeypatch):
    """Sin --yes, non-TTY + destructivo también aborta limpio (no es exclusivo de --yes)."""
    state, calls = mocked
    state["validate"] = ValidationResult(True, [], [], True)
    state["plan"] = (_destructive_plan(), None)
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: False)

    with pytest.raises(typer.Exit) as exc_info:
        cli._process_one("borra x.txt", None, yes=False)

    assert exc_info.value.exit_code == 2


def test_can_confirm_interactively_returns_bool():
    """El helper debe devolver bool sin lanzar."""
    from sunny.core.orchestrator import confirmation
    result = confirmation.can_confirm_interactively()
    assert isinstance(result, bool)


# --- DEP-43: confirm_comprehension non-TTY -----------------------------------

def _comp_low_conf(intent="files"):
    return ComprehensionResult(
        comprehension="x", intent=intent, assumptions=[],
        confidence=0.6, needs_clarification=False,
    )


def test_yes_in_non_tty_auto_confirms_comprehension_regardless_of_confidence(mocked, monkeypatch):
    """DEP-43: --yes + non-TTY + baja confianza → auto-confirma (no abort, no input)."""
    state, calls = mocked
    state["comprehend"] = (_comp_low_conf(), None)
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: False)

    confirm_called = {"v": False}
    monkeypatch.setattr(
        cli._confirmation, "confirm_comprehension",
        lambda c: confirm_called.__setitem__("v", True) or True,
    )

    cli._process_one("x", None, yes=True)

    assert confirm_called["v"] is False  # no se intentó pedir input
    assert any(r[0] == "execution" for r in calls["reports"])


def test_low_confidence_in_non_tty_without_yes_aborts(mocked, monkeypatch):
    """DEP-43: sin --yes + non-TTY + comprensión no-trivial → typer.Exit(2) limpio."""
    state, calls = mocked
    state["comprehend"] = (_comp_low_conf(), None)
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: False)

    with pytest.raises(typer.Exit) as exc_info:
        cli._process_one("x", None, yes=False)

    assert exc_info.value.exit_code == 2
    assert not any(r[0] == "execution" for r in calls["reports"])


def test_needs_clarification_in_non_tty_reports_normally(mocked, monkeypatch):
    """DEP-43: needs_clarification es siempre safe (no input), report_clarification debe llegar."""
    state, calls = mocked
    state["comprehend"] = (_comp(needs_clarification=True), None)
    state["confirm_comp"] = False  # confirm_comprehension retorna False por needs_clarification
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: False)

    cli._process_one("ambiguo", None, yes=True)

    assert any(r[0] == "clarification" for r in calls["reports"])
    assert not any(r[0] == "execution" for r in calls["reports"])


def test_low_confidence_in_tty_with_yes_still_asks(mocked, monkeypatch):
    """En TTY el path conservador (preguntar si confianza < 0.9) se mantiene (sin regresión)."""
    state, calls = mocked
    state["comprehend"] = (_comp_low_conf(), None)
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: True)

    confirm_called = {"v": False}
    monkeypatch.setattr(
        cli._confirmation, "confirm_comprehension",
        lambda c: confirm_called.__setitem__("v", True) or True,
    )

    cli._process_one("x", None, yes=True)

    assert confirm_called["v"] is True  # SÍ se llamó a confirm_comprehension


# --- SUNNY_AUTO_CONFIRM_DESTRUCTIVE override (option 3 del handoff DEP-38) ----

def test_destructive_plan_auto_confirms_when_env_var_set_with_yes_in_non_tty(mocked, monkeypatch):
    """yes=True + non-TTY + SUNNY_AUTO_CONFIRM_DESTRUCTIVE=1 → ejecuta sin abort."""
    state, calls = mocked
    state["validate"] = ValidationResult(True, [], [], True)
    state["plan"] = (_destructive_plan(), None)
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: False)
    monkeypatch.setenv("SUNNY_AUTO_CONFIRM_DESTRUCTIVE", "1")

    cli._process_one("borra x.txt", None, yes=True)

    assert any(r[0] == "execution" for r in calls["reports"])
    assert not any(r[0] == "cancelled" for r in calls["reports"])


def test_destructive_plan_aborts_when_env_var_set_but_no_yes(mocked, monkeypatch):
    """SUNNY_AUTO_CONFIRM_DESTRUCTIVE=1 sin --yes → aborta (requiere ambos signals)."""
    state, calls = mocked
    state["validate"] = ValidationResult(True, [], [], True)
    state["plan"] = (_destructive_plan(), None)
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: False)
    monkeypatch.setenv("SUNNY_AUTO_CONFIRM_DESTRUCTIVE", "1")

    with pytest.raises(typer.Exit) as exc_info:
        cli._process_one("borra x.txt", None, yes=False)

    assert exc_info.value.exit_code == 2


def test_destructive_plan_in_tty_ignores_env_var(mocked, monkeypatch):
    """En TTY el env var no relaja nada: sigue pidiendo confirmación interactiva."""
    state, calls = mocked
    state["validate"] = ValidationResult(True, [], [], True)
    state["plan"] = (_destructive_plan(), None)
    monkeypatch.setattr(cli._confirmation, "can_confirm_interactively", lambda: True)
    monkeypatch.setenv("SUNNY_AUTO_CONFIRM_DESTRUCTIVE", "1")

    confirm_called = {"v": False}
    monkeypatch.setattr(
        cli._confirmation, "confirm_plan",
        lambda p: confirm_called.__setitem__("v", True) or True,
    )

    cli._process_one("borra x.txt", None, yes=True)

    assert confirm_called["v"] is True  # confirm_plan SÍ se llamó


def test_auto_confirm_destructive_helper_truthy_values(monkeypatch):
    """El helper acepta '1', 'true', 'yes', 'on' (case-insensitive, trimmed)."""
    from sunny.core.orchestrator import confirmation
    for val in ("1", "true", "True", "yes", "ON", " 1 "):
        monkeypatch.setenv("SUNNY_AUTO_CONFIRM_DESTRUCTIVE", val)
        assert confirmation.auto_confirm_destructive_enabled() is True, f"Fallo con {val!r}"
    for val in ("0", "false", "no", "off", "", "random"):
        monkeypatch.setenv("SUNNY_AUTO_CONFIRM_DESTRUCTIVE", val)
        assert confirmation.auto_confirm_destructive_enabled() is False, f"Fallo con {val!r}"
