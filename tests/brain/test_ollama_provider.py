import json

import pytest

from sunny.brain.ollama_client import LLMValidationError
from sunny.brain.providers.ollama_provider import OllamaProvider
from sunny.core.models.plan import ComprehensionResult


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


def test_call_validated_delegates_to_ollama_client(monkeypatch):
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return ComprehensionResult(
            comprehension="x",
            intent="files",
            assumptions=[],
            confidence=0.9,
            needs_clarification=False,
        ), _StatsStub()

    monkeypatch.setattr("sunny.brain.ollama_client.call_llm_validated", fake_call)

    p = OllamaProvider()
    res, _ = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"
    assert captured["user_prompt"] == "u"
    assert captured["system_prompt"] == "s"
    assert captured["schema"] is ComprehensionResult


def test_call_validated_passes_through_via_ollama_chat_mock(monkeypatch):
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _ok_response())

    p = OllamaProvider()
    res, stats = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"
    assert stats.retries_used == 0


def test_call_validated_propagates_validation_error(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **k: {"message": {"content": "no json"}, "prompt_eval_count": 0, "eval_count": 0},
    )

    p = OllamaProvider()
    with pytest.raises(LLMValidationError):
        p.call_validated("u", "s", ComprehensionResult, max_retries=0)


def test_call_validated_forwards_temperature_and_timeout(monkeypatch):
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop")

    monkeypatch.setattr("sunny.brain.ollama_client.call_llm_validated", fake_call)

    p = OllamaProvider()
    with pytest.raises(RuntimeError):
        p.call_validated("u", "s", ComprehensionResult, temperature=0.7, timeout_sec=30)

    assert captured["temperature"] == 0.7
    assert captured["timeout_sec"] == 30


def test_call_validated_forwards_num_ctx(monkeypatch):
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop")

    monkeypatch.setattr("sunny.brain.ollama_client.call_llm_validated", fake_call)

    p = OllamaProvider()
    with pytest.raises(RuntimeError):
        p.call_validated("u", "s", ComprehensionResult, num_ctx=8192)

    assert captured["num_ctx"] == 8192


def test_health_check_delegates_to_module(monkeypatch):
    called = {}

    def fake_hc(model):
        called["model"] = model
        return True

    monkeypatch.setattr("sunny.brain.ollama_client.health_check", fake_hc)

    p = OllamaProvider(model="mymodel")
    assert p.health_check() is True
    assert called["model"] == "mymodel"


def test_health_check_false_when_module_returns_false(monkeypatch):
    monkeypatch.setattr("sunny.brain.ollama_client.health_check", lambda model: False)
    assert OllamaProvider().health_check() is False


def test_default_model_is_ollama_default():
    from sunny.brain.ollama_client import DEFAULT_MODEL
    p = OllamaProvider()
    assert p._model == DEFAULT_MODEL


class _StatsStub:
    tokens_in = 0
    tokens_out = 0
    latency_ms = 0
    retries_used = 0
