import builtins

from sunny.core.models.plan import ComprehensionResult, PlanV2, Step
from sunny.core.orchestrator import confirmation as c


def _comp(intent="files", needs_clarification=False, assumptions=None):
    return ComprehensionResult(
        comprehension="x",
        intent=intent,
        assumptions=assumptions or [],
        confidence=0.9,
        needs_clarification=needs_clarification,
    )


def _plan(n_steps=1):
    steps = [
        Step(step_id=f"s{i}", plugin="files", action="read_file", params={"path": f"f{i}.txt"})
        for i in range(n_steps)
    ]
    return PlanV2(intent="files", confidence=0.9, steps=steps)


def test_ask_yes_no_responds_yes(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _: "s")
    assert c.ask_yes_no("?", False)


def test_ask_yes_no_responds_yes_acentuada(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _: "sí")
    assert c.ask_yes_no("?", False)


def test_ask_yes_no_responds_y_english(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _: "yes")
    assert c.ask_yes_no("?", False)


def test_ask_yes_no_responds_no(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _: "n")
    assert not c.ask_yes_no("?", True)


def test_ask_yes_no_empty_uses_default_true(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _: "")
    assert c.ask_yes_no("?", True)


def test_ask_yes_no_empty_uses_default_false(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _: "")
    assert not c.ask_yes_no("?", False)


def test_ask_yes_no_case_insensitive(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _: "YES")
    assert c.ask_yes_no("?", False)


def test_ask_yes_no_invalid_input_loops(monkeypatch):
    inputs = iter(["foo", "bar", "n"])
    monkeypatch.setattr(builtins, "input", lambda _: next(inputs))
    assert not c.ask_yes_no("?", True)


def test_confirm_comprehension_yes(monkeypatch):
    monkeypatch.setattr(c, "ask_yes_no", lambda *a, **k: True)
    assert c.confirm_comprehension(_comp())


def test_confirm_comprehension_no(monkeypatch):
    monkeypatch.setattr(c, "ask_yes_no", lambda *a, **k: False)
    assert not c.confirm_comprehension(_comp())


def test_confirm_comprehension_clarification_short_circuits(monkeypatch):
    called = {"v": False}

    def fake(*a, **k):
        called["v"] = True
        return True

    monkeypatch.setattr(c, "ask_yes_no", fake)
    assert not c.confirm_comprehension(_comp(needs_clarification=True))
    assert not called["v"]


def test_confirm_comprehension_logs_confirmed(monkeypatch):
    events = []
    monkeypatch.setattr(c, "ask_yes_no", lambda *a, **k: True)
    monkeypatch.setattr(c.log, "info", lambda e, **k: events.append(e))
    c.confirm_comprehension(_comp())
    assert "comprehension_confirmed" in events


def test_confirm_comprehension_logs_rejected(monkeypatch):
    events = []
    monkeypatch.setattr(c, "ask_yes_no", lambda *a, **k: False)
    monkeypatch.setattr(c.log, "info", lambda e, **k: events.append(e))
    c.confirm_comprehension(_comp())
    assert "comprehension_rejected" in events


def test_confirm_comprehension_logs_clarification_needed(monkeypatch):
    events = []
    monkeypatch.setattr(c.log, "info", lambda e, **k: events.append(e))
    c.confirm_comprehension(_comp(needs_clarification=True))
    assert "comprehension_clarification_needed" in events


def test_confirm_plan_yes(monkeypatch):
    monkeypatch.setattr(c, "ask_yes_no", lambda *a, **k: True)
    assert c.confirm_plan(_plan())


def test_confirm_plan_no(monkeypatch):
    monkeypatch.setattr(c, "ask_yes_no", lambda *a, **k: False)
    assert not c.confirm_plan(_plan())


def test_confirm_plan_logs_confirmed(monkeypatch):
    events = []
    monkeypatch.setattr(c, "ask_yes_no", lambda *a, **k: True)
    monkeypatch.setattr(c.log, "info", lambda e, **k: events.append(e))
    c.confirm_plan(_plan())
    assert "plan_confirmed" in events


def test_confirm_plan_logs_rejected(monkeypatch):
    events = []
    monkeypatch.setattr(c, "ask_yes_no", lambda *a, **k: False)
    monkeypatch.setattr(c.log, "info", lambda e, **k: events.append(e))
    c.confirm_plan(_plan())
    assert "plan_rejected" in events


def test_confirm_plan_default_is_false(monkeypatch):
    captured = {}

    def fake(msg, default=False):
        captured["default"] = default
        return False

    monkeypatch.setattr(c, "ask_yes_no", fake)
    c.confirm_plan(_plan())
    assert captured["default"] is False


def test_confirm_comprehension_default_is_true(monkeypatch):
    captured = {}

    def fake(msg, default=False):
        captured["default"] = default
        return True

    monkeypatch.setattr(c, "ask_yes_no", fake)
    c.confirm_comprehension(_comp())
    assert captured["default"] is True
