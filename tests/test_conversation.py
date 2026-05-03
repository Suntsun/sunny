import pytest
import json

from sunny.core.orchestrator import conversation


def _ok_text_response(text="hola, soy sunny."):
    return {
        "message": {"content": text},
        "prompt_eval_count": 30,
        "eval_count": 20,
    }


def test_build_prompt_basic_no_context():
    p = conversation.build_conversation_user_prompt("hola", None)
    assert "Usuario: hola" in p
    assert conversation.CONTEXT_TAG not in p


def test_build_prompt_with_context_includes_section():
    ctx = [{"turn": 1, "user_msg": "a", "assistant_msg": "b"}]
    p = conversation.build_conversation_user_prompt("hola", ctx)
    assert conversation.CONTEXT_TAG in p
    assert "a" in p


def test_build_prompt_no_phase_tag():
    p = conversation.build_conversation_user_prompt("hola", None)
    assert "[FASE:" not in p


def test_build_prompt_unicode_preserved():
    p = conversation.build_conversation_user_prompt("qué hora es", None)
    assert "qué hora es" in p


def test_converse_returns_text_and_stats(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **kw: _ok_text_response(),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    text, stats = conversation.converse("hola")
    assert isinstance(text, str)
    assert stats.tokens_in == 30


def test_converse_uses_conversation_system_prompt(monkeypatch):
    captured = {}

    def fake(self, **kw):
        captured["sys"] = kw["messages"][0]["content"]
        return _ok_text_response()

    monkeypatch.setattr("ollama.Client.chat", fake)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    conversation.converse("hola")

    assert "# ROL" in captured["sys"]
    assert "sunny" in captured["sys"]
    assert "PLANIFICACIÓN" not in captured["sys"]


def test_converse_passes_json_mode_false(monkeypatch):
    captured = {}

    def fake(self, **kw):
        captured.update(kw)
        return _ok_text_response()

    monkeypatch.setattr("ollama.Client.chat", fake)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    conversation.converse("hola")

    assert not captured.get("format")


def test_converse_passes_higher_temperature(monkeypatch):
    captured = {}

    def fake(self, **kw):
        captured["temp"] = kw["options"]["temperature"]
        return _ok_text_response()

    monkeypatch.setattr("ollama.Client.chat", fake)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    conversation.converse("hola")

    assert captured["temp"] == 0.5


def test_converse_uses_session_context_when_present(monkeypatch):
    captured = {}

    def fake(self, **kw):
        captured["user"] = kw["messages"][1]["content"]
        return _ok_text_response()

    ctx = [{"turn": 1, "user_msg": "leer notas", "assistant_msg": "ok"}]
    monkeypatch.setattr("ollama.Client.chat", fake)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: ctx)

    conversation.converse("hola")

    assert conversation.CONTEXT_TAG in captured["user"]
    assert "leer notas" in captured["user"]


def test_converse_no_context_section_when_empty(monkeypatch):
    captured = {}

    def fake(self, **kw):
        captured["user"] = kw["messages"][1]["content"]
        return _ok_text_response()

    monkeypatch.setattr("ollama.Client.chat", fake)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    conversation.converse("hola")

    assert conversation.CONTEXT_TAG not in captured["user"]


def test_converse_propagates_timeout_error(monkeypatch):
    def fake(self, **kw):
        raise Exception("timeout")

    monkeypatch.setattr("ollama.Client.chat", fake)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    from sunny.brain.ollama_client import LLMTimeoutError

    with pytest.raises(LLMTimeoutError):
        conversation.converse("hola")


def test_converse_logs_start_and_done(monkeypatch):
    events = []

    def fake_info(**kw):
        events.append(kw.get("event"))

    monkeypatch.setattr(conversation.log, "info", fake_info)
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **kw: _ok_text_response(),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])

    conversation.converse("hola")

    assert "conversation_start" in events
    assert "conversation_done" in events


def test_conversation_prompt_loadable():
    from sunny.core.prompts.loader import load_system_prompt

    txt = load_system_prompt("conversation_v1")
    assert isinstance(txt, str)
    assert len(txt) > 200
