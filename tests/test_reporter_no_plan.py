from __future__ import annotations

from sunny.core.models.plan import PlanV2
from sunny.core.orchestrator import reporter


def _plan(needs_clarification=False):
    return PlanV2(
        intent="ai_bridge",
        confidence=0.95,
        needs_clarification=needs_clarification or True,  # steps=[] requiere needs_clarification
        steps=[],
    )


def _capture_print(monkeypatch):
    """Captura args de console.print y devuelve función que aplana Panels."""
    calls = []
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: calls.append(a))

    def flatten() -> str:
        parts = []
        for args in calls:
            for arg in args:
                renderable = getattr(arg, "renderable", None)
                title = getattr(arg, "title", None)
                if renderable is not None:
                    parts.append(str(renderable))
                if title:
                    parts.append(str(title))
                if renderable is None and title is None:
                    parts.append(str(arg))
        return " ".join(parts)

    return flatten


def test_report_no_plan_clarification_branch(monkeypatch):
    flatten = _capture_print(monkeypatch)

    plan = _plan(needs_clarification=True)
    reporter.report_no_plan(plan, "una orden ambigua")

    rendered = flatten().lower()
    assert "aclaración" in rendered
    assert "ai_bridge" in rendered


def test_report_no_plan_unsupported_branch(monkeypatch):
    flatten = _capture_print(monkeypatch)

    plan = _plan(needs_clarification=True)
    # Forzamos el otro branch mutando post-construcción para verificar el
    # mensaje "Sin plan ejecutable" sin que pydantic se queje de steps=[].
    plan.needs_clarification = False

    reporter.report_no_plan(plan, "envía un mensaje por discord")

    rendered = flatten()
    assert "Sin plan ejecutable" in rendered
    assert "discord" in rendered.lower()
    assert "ai_bridge" in rendered


def test_report_no_plan_does_not_raise_on_zero_confidence(monkeypatch):
    monkeypatch.setattr(reporter.console, "print", lambda *a, **k: None)
    plan = PlanV2(
        intent="files",
        confidence=0.0,
        needs_clarification=True,
        steps=[],
    )
    reporter.report_no_plan(plan, "orden")
