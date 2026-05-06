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


def test_report_execution_renders_search(monkeypatch):
    import io
    buf = io.StringIO()
    fake_console = reporter.Console(file=buf, force_terminal=True, width=200)
    monkeypatch.setattr(reporter, "console", fake_console)

    step = StepExecutionResult(
        step_id="s1", plugin="files", action="search",
        success=True, data=["C:\\Users\\Mahes\\Desktop\\saludo.txt"],
        latency_ms=5,
    )
    result = ExecutionResult(
        plan_intent="files", success=True, steps=[step],
        total_latency_ms=5, early_stopped=False,
    )
    reporter.report_execution(result)
    output = buf.getvalue()
    assert "saludo.txt" in output


def test_report_execution_renders_get_info_existing_file(monkeypatch):
    import io
    buf = io.StringIO()
    fake_console = reporter.Console(file=buf, force_terminal=True, width=200)
    monkeypatch.setattr(reporter, "console", fake_console)

    step = StepExecutionResult(
        step_id="s1", plugin="files", action="get_info",
        success=True,
        data={
            "path": "C:\\Users\\Mahes\\Desktop\\nota.txt",
            "exists": True,
            "is_file": True,
            "is_dir": False,
            "size": 1024,
            "modified_ts": 1700000000.0,
        },
        latency_ms=1,
    )
    result = ExecutionResult(
        plan_intent="files", success=True, steps=[step],
        total_latency_ms=1, early_stopped=False,
    )
    reporter.report_execution(result)
    output = buf.getvalue()
    assert "nota.txt" in output
    assert "1.0 KB" in output


def test_report_execution_renders_get_info_missing(monkeypatch):
    import io
    buf = io.StringIO()
    fake_console = reporter.Console(file=buf, force_terminal=True, width=200)
    monkeypatch.setattr(reporter, "console", fake_console)

    step = StepExecutionResult(
        step_id="s1", plugin="files", action="get_info",
        success=True,
        data={
            "path": "C:\\no\\existe.txt",
            "exists": False,
            "is_file": False,
            "is_dir": False,
            "size": 0,
            "modified_ts": None,
        },
        latency_ms=1,
    )
    result = ExecutionResult(
        plan_intent="files", success=True, steps=[step],
        total_latency_ms=1, early_stopped=False,
    )
    reporter.report_execution(result)
    output = buf.getvalue()
    assert "No existe" in output


# ---------------------------------------------------------------------------
# Tests para describe_screen y analyze_screen renderers
# ---------------------------------------------------------------------------


def test_render_describe_screen_shows_description(monkeypatch):
    import io
    buf = io.StringIO()
    fake_console = reporter.Console(file=buf, force_terminal=True, width=200)
    monkeypatch.setattr(reporter, "console", fake_console)

    step = StepExecutionResult(
        step_id="s1",
        plugin="vision",
        action="describe_screen",
        success=True,
        data={
            "description": "Ventana del editor con un menú lateral",
            "screenshot_path": "C:\\tmp\\shot.png",
            "model_used": "llava",
            "tokens_out": 42,
            "latency_ms": 1234,
        },
        latency_ms=1234,
    )
    result = ExecutionResult(
        plan_intent="vision", success=True, steps=[step],
        total_latency_ms=1234, early_stopped=False,
    )
    reporter.report_execution(result)
    output = buf.getvalue()
    assert "Ventana del editor" in output
    assert "shot.png" in output
    assert "llava" in output


def test_render_analyze_screen_shows_question_and_answer(monkeypatch):
    import io
    buf = io.StringIO()
    fake_console = reporter.Console(file=buf, force_terminal=True, width=200)
    monkeypatch.setattr(reporter, "console", fake_console)

    step = StepExecutionResult(
        step_id="s1",
        plugin="vision",
        action="analyze_screen",
        success=True,
        data={
            "question": "¿Cuántos botones hay?",
            "answer": "Veo tres botones en la barra superior",
            "screenshot_path": "C:\\tmp\\shot.png",
            "model_used": "llava",
            "tokens_out": 30,
            "latency_ms": 999,
        },
        latency_ms=999,
    )
    result = ExecutionResult(
        plan_intent="vision", success=True, steps=[step],
        total_latency_ms=999, early_stopped=False,
    )
    reporter.report_execution(result)
    output = buf.getvalue()
    assert "Cuántos botones" in output
    assert "tres botones" in output.lower() or "Veo tres" in output
    assert "shot.png" in output


def test_render_describe_screen_handles_empty_description(monkeypatch):
    import io
    buf = io.StringIO()
    fake_console = reporter.Console(file=buf, force_terminal=True, width=200)
    monkeypatch.setattr(reporter, "console", fake_console)

    step = StepExecutionResult(
        step_id="s1",
        plugin="vision",
        action="describe_screen",
        success=True,
        data={
            "description": "",
            "screenshot_path": "C:\\tmp\\empty.png",
            "model_used": "llava",
            "tokens_out": 0,
            "latency_ms": 50,
        },
        latency_ms=50,
    )
    result = ExecutionResult(
        plan_intent="vision", success=True, steps=[step],
        total_latency_ms=50, early_stopped=False,
    )
    reporter.report_execution(result)
    output = buf.getvalue()
    assert "Sin descripción" in output
