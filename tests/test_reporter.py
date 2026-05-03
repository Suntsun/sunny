import pytest

from sunny.core.execution.engine import ExecutionResult, StepExecutionResult
from sunny.core.models.plan import ComprehensionResult
from sunny.core.orchestrator import reporter


def _step(step_id="s1", success=True, skipped=False, error=None):
    return StepExecutionResult(
        step_id=step_id,
        plugin="files",
        action="read_file",
        success=success,
        skipped=skipped,
        skip_reason="early_stop" if skipped else None,
        error=error,
        error_type=None if success else "MockError",
        latency_ms=42,
    )


def _comp(intent="files", needs_clarification=False):
    return ComprehensionResult(
        comprehension="el usuario quiere X",
        intent=intent,
        assumptions=[],
        confidence=0.9,
        needs_clarification=needs_clarification,
    )


def test_report_conversation_prints_text(monkeypatch):
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    result = ExecutionResult("conversation", True, [], 0, False)
    reporter.report_execution(result, conversation_text="hola usuario")

    assert any("hola usuario" in str(c) for c in calls)


def test_report_conversation_without_text_no_print(monkeypatch):
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    result = ExecutionResult("conversation", True, [], 0, False)
    reporter.report_execution(result, conversation_text=None)

    assert calls == []


def test_report_execution_success(monkeypatch):
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    result = ExecutionResult("files", True, [_step("s1"), _step("s2")], 100, False)
    reporter.report_execution(result)

    assert len(calls) >= 1


def test_report_execution_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    result = ExecutionResult("files", False, [_step("s1"), _step("s2", success=False, error="boom")], 100, True)
    reporter.report_execution(result)

    assert len(calls) >= 1


def test_report_execution_with_skipped(monkeypatch):
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    result = ExecutionResult(
        "files",
        False,
        [_step("s1"), _step("s2", success=False, error="boom"), _step("s3", skipped=True)],
        100,
        True,
    )
    reporter.report_execution(result)

    assert len(calls) >= 1


def test_report_clarification(monkeypatch):
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    reporter.report_clarification(_comp())

    assert len(calls) == 1


def test_report_user_cancelled_default_reason(monkeypatch):
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    reporter.report_user_cancelled()

    assert any("cancelada" in str(c) for c in calls)


def test_report_user_cancelled_custom_reason(monkeypatch):
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    reporter.report_user_cancelled("usuario rechazó plan")

    assert any("usuario rechazó plan" in str(c) for c in calls)


def test_report_validation_errors(monkeypatch):
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    reporter.report_validation_errors(["error 1", "error 2"])

    assert len(calls) == 1


def test_report_execution_logs_event(monkeypatch):
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: None)
    events = []
    monkeypatch.setattr(reporter.log, "info", lambda e, **k: events.append(e))

    result = ExecutionResult("files", True, [_step()], 10, False)
    reporter.report_execution(result)

    assert "report_execution" in events


def test_report_clarification_logs_event(monkeypatch):
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: None)
    events = []
    monkeypatch.setattr(reporter.log, "info", lambda e, **k: events.append(e))

    reporter.report_clarification(_comp())

    assert "report_clarification" in events


def test_report_user_cancelled_logs_event(monkeypatch):
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: None)
    events = []
    monkeypatch.setattr(reporter.log, "info", lambda e, **k: events.append(e))

    reporter.report_user_cancelled()

    assert "report_user_cancelled" in events


def test_report_validation_errors_logs_event(monkeypatch):
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: None)
    events = []
    monkeypatch.setattr(reporter.log, "warning", lambda e, **k: events.append(e))

    reporter.report_validation_errors(["x"])

    assert "report_validation_errors" in events


def test_report_conversation_logs_event(monkeypatch):
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: None)
    events = []
    monkeypatch.setattr(reporter.log, "info", lambda e, **k: events.append(e))

    result = ExecutionResult("conversation", True, [], 0, False)
    reporter.report_execution(result, "hola")

    assert "report_conversation" in events


def test_report_execution_renders_semantic_for_list_directory(monkeypatch):
    import io
    buf = io.StringIO()
    fake_console = reporter.Console(file=buf, force_terminal=True, width=200)
    monkeypatch.setattr(reporter, "console", fake_console)

    step = StepExecutionResult(
        step_id="s1",
        plugin="files",
        action="list_directory",
        success=True,
        data={
            "path": "C:\\test",
            "directories": [{"name": "carpeta_x"}],
            "files": [{"name": "archivo_y.txt", "size": 100}],
            "total_entries": 2,
        },
        latency_ms=5,
    )
    result = ExecutionResult(
        plan_intent="files",
        success=True,
        steps=[step],
        total_latency_ms=5,
        early_stopped=False,
    )
    reporter.report_execution(result)

    output = buf.getvalue()
    assert "carpeta_x" in output
    assert "archivo_y.txt" in output
