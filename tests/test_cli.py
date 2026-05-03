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

    monkeypatch.setattr(cli._reporter, "report_execution", lambda r, conversation_text=None: calls["reports"].append(("execution", r, conversation_text)))
    monkeypatch.setattr(cli._reporter, "report_clarification", lambda c: calls["reports"].append(("clarification", c)))
    monkeypatch.setattr(cli._reporter, "report_user_cancelled", lambda r="...": calls["reports"].append(("cancelled", r)))
    monkeypatch.setattr(cli._reporter, "report_validation_errors", lambda e: calls["reports"].append(("validation_errors", e)))

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

    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli.session, "get_or_create_active_session", lambda: "sid")
    monkeypatch.setattr(cli, "_build_registry", lambda: None)

    called = []
    monkeypatch.setattr(cli, "_process_one", lambda u, r: called.append(u))

    cli.main(ctx=ctx, order="hola", new_session=False, end_session=False)

    assert "hola" in called


def test_main_end_session_calls_session_end(monkeypatch):
    ctx = MagicMock()
    ctx.invoked_subcommand = None

    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(cli, "init_db", lambda: None)

    called = []
    monkeypatch.setattr(cli.session, "end_session", lambda: called.append(True))

    cli.main(ctx=ctx, order=None, new_session=False, end_session=True)

    assert called


def test_main_new_session_forces_new(monkeypatch):
    ctx = MagicMock()
    ctx.invoked_subcommand = None

    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli.session, "force_new_session", lambda: "new-id")
    monkeypatch.setattr(cli, "_build_registry", lambda: None)
    monkeypatch.setattr(cli, "_process_one", lambda u, r: None)

    cli.main(ctx=ctx, order="hi", new_session=True, end_session=False)
