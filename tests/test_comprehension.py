import json
import pytest

from sunny.core.orchestrator.comprehension import (
    build_comprehension_user_prompt,
    comprehend,
    PHASE_TAG,
    CONTEXT_TAG,
)
from sunny.brain.ollama_client import LLMValidationError, LLMTimeoutError


def _ok_response():
    return {
        "message": {"content": json.dumps({
            "comprehension": "x",
            "intent": "files",
            "assumptions": [],
            "confidence": 0.9,
            "needs_clarification": False,
        })},
        "prompt_eval_count": 10,
        "eval_count": 5,
    }


def test_build_prompt_basic_no_context():
    p = build_comprehension_user_prompt("hola")
    assert PHASE_TAG in p
    assert "Usuario: hola" in p
    assert CONTEXT_TAG not in p


def test_build_prompt_empty_list_no_context_section():
    p = build_comprehension_user_prompt("hola", context=[])
    assert CONTEXT_TAG not in p


def test_build_prompt_none_no_context_section():
    p = build_comprehension_user_prompt("hola", context=None)
    assert CONTEXT_TAG not in p


def test_build_prompt_with_context_includes_section():
    ctx = [{"turn": 1, "user_msg": "a", "assistant_msg": "b"}]
    p = build_comprehension_user_prompt("hola", context=ctx)
    assert CONTEXT_TAG in p
    assert "a" in p and "b" in p


def test_build_prompt_phase_tag_first():
    ctx = [{"turn": 1, "user_msg": "a", "assistant_msg": "b"}]
    p = build_comprehension_user_prompt("hola", context=ctx)
    assert p.strip().startswith(PHASE_TAG)


def test_build_prompt_unicode_preserved():
    p = build_comprehension_user_prompt("ábrelo qué")
    assert "ábrelo" in p
    assert "qué" in p


def test_comprehend_returns_validated_result(monkeypatch):
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _ok_response())
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    res, stats = comprehend("hola")
    assert res.intent == "files"
    assert stats.retries_used == 0


def test_comprehend_uses_comprehension_v1_system_prompt(monkeypatch):
    """La comprensión debe usar el prompt ligero comprehension_v1, no v3."""
    captured = {}

    def fake_loader(version="v3"):
        captured["version"] = version
        return "stub-comprehension-prompt"

    monkeypatch.setattr(
        "sunny.core.orchestrator.comprehension.load_system_prompt",
        fake_loader,
    )
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _ok_response())
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    comprehend("hola")
    assert captured["version"] == "comprehension_v1"
    assert captured["version"] != "v3"


def test_comprehend_user_prompt_has_phase_tag(monkeypatch):
    captured = {}

    def fake_chat(self, **kwargs):
        captured.update(kwargs)
        return _ok_response()

    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    comprehend("hola")
    assert PHASE_TAG in captured["messages"][1]["content"]


def test_comprehend_uses_session_context_when_present(monkeypatch):
    captured = {}

    def fake_chat(self, **kwargs):
        captured.update(kwargs)
        return _ok_response()

    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr(
        "sunny.core.session.manager.get_context",
        lambda: [{"turn": 1, "user_msg": "leer notas", "assistant_msg": "ok"}],
    )

    comprehend("ábrelo")
    up = captured["messages"][1]["content"]
    assert CONTEXT_TAG in up
    assert "leer notas" in up


def test_comprehend_no_context_section_when_empty_session(monkeypatch):
    captured = {}

    def fake_chat(self, **kwargs):
        captured.update(kwargs)
        return _ok_response()

    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    comprehend("hola")
    assert CONTEXT_TAG not in captured["messages"][1]["content"]


def test_comprehend_propagates_validation_error(monkeypatch):
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: {"message": {"content": "bad"}})
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    with pytest.raises(LLMValidationError):
        comprehend("hola")


def test_comprehend_propagates_timeout_error(monkeypatch):
    def fake_chat(*args, **kwargs):
        raise Exception("timeout")

    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    with pytest.raises(LLMTimeoutError):
        comprehend("hola")


def test_comprehend_returns_stats(monkeypatch):
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _ok_response())
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    _, stats = comprehend("hola")
    assert stats.tokens_in == 10
    assert stats.tokens_out == 5
    assert stats.latency_ms >= 0


def test_comprehend_logs_start_and_done(monkeypatch):
    logs = []

    def fake_info(event, **kwargs):
        logs.append(event)

    monkeypatch.setattr("sunny.core.orchestrator.comprehension.log.info", fake_info)
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _ok_response())
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    comprehend("hola")
    assert "comprehension_start" in logs
    assert "comprehension_done" in logs
