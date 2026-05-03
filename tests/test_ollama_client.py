import json
import pytest

from sunny.brain.ollama_client import (
    call_llm,
    call_llm_validated,
    health_check,
    _strip_code_fences,
    _extract_json_object,
    LLMTimeoutError,
    LLMConnectionError,
    LLMValidationError,
)
from sunny.core.models.plan import ComprehensionResult


def _make_response(content: str, prompt_eval_count: int = 100, eval_count: int = 50):
    return {
        "message": {"content": content},
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
    }


def test_call_llm_success_first_try(monkeypatch):
    def fake_chat(self, **kwargs):
        return _make_response('{"ok": true}')

    monkeypatch.setattr("ollama.Client.chat", fake_chat)

    content, stats = call_llm("u", "s")
    assert content == '{"ok": true}'
    assert stats.retries_used == 0


def test_call_llm_stats_populated(monkeypatch):
    def fake_chat(self, **kwargs):
        return _make_response('{"ok": true}', 10, 5)

    monkeypatch.setattr("ollama.Client.chat", fake_chat)

    _, stats = call_llm("u", "s")
    assert stats.tokens_in == 10
    assert stats.tokens_out == 5
    assert stats.latency_ms >= 0


def test_call_llm_passes_model_and_temperature(monkeypatch):
    captured = {}

    def fake_chat(self, **kwargs):
        captured.update(kwargs)
        return _make_response("{}")

    monkeypatch.setattr("ollama.Client.chat", fake_chat)

    call_llm("u", "s", model="x", temperature=0.7)
    assert captured["model"] == "x"
    assert captured["options"]["temperature"] == 0.7


def test_call_llm_json_mode_passes_format(monkeypatch):
    captured = {}

    def fake_chat(self, **kwargs):
        captured.update(kwargs)
        return _make_response("{}")

    monkeypatch.setattr("ollama.Client.chat", fake_chat)

    call_llm("u", "s", json_mode=True)
    assert captured["format"] == "json"


def test_call_llm_text_mode_no_format(monkeypatch):
    captured = {}

    def fake_chat(self, **kwargs):
        captured.update(kwargs)
        return _make_response("{}")

    monkeypatch.setattr("ollama.Client.chat", fake_chat)

    call_llm("u", "s", json_mode=False)
    assert "format" not in captured or captured["format"] == ""


def test_call_llm_messages_structure(monkeypatch):
    captured = {}

    def fake_chat(self, **kwargs):
        captured.update(kwargs)
        return _make_response("{}")

    monkeypatch.setattr("ollama.Client.chat", fake_chat)

    call_llm("user", "system")
    msgs = captured["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[0]["content"] == "system"
    assert msgs[1]["content"] == "user"


def test_call_llm_timeout_raises_llmtimeout(monkeypatch):
    def fake_chat(*args, **kwargs):
        raise Exception("timeout")

    monkeypatch.setattr("ollama.Client.chat", fake_chat)

    with pytest.raises(LLMTimeoutError):
        call_llm("u", "s")


def test_call_llm_connection_error_raises_llmconnection(monkeypatch):
    def fake_chat(*args, **kwargs):
        raise Exception("connect")

    monkeypatch.setattr("ollama.Client.chat", fake_chat)

    with pytest.raises(LLMConnectionError):
        call_llm("u", "s")


def test_call_llm_validated_success_first_try(monkeypatch):
    valid = json.dumps({
        "comprehension": "x",
        "intent": "files",
        "assumptions": [],
        "confidence": 0.9,
        "needs_clarification": False,
    })

    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _make_response(valid))

    res, stats = call_llm_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"
    assert stats.retries_used == 0


def test_call_llm_validated_invalid_json_then_valid(monkeypatch):
    calls = iter([
        _make_response("no json"),
        _make_response(json.dumps({
            "comprehension": "x",
            "intent": "files",
            "assumptions": [],
            "confidence": 0.9,
            "needs_clarification": False,
        })),
    ])

    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: next(calls))

    res, stats = call_llm_validated("u", "s", ComprehensionResult)
    assert stats.retries_used == 1


def test_call_llm_validated_validation_error_then_valid(monkeypatch):
    calls = iter([
        _make_response(json.dumps({"intent": "bad"})),
        _make_response(json.dumps({
            "comprehension": "x",
            "intent": "files",
            "assumptions": [],
            "confidence": 0.9,
            "needs_clarification": False,
        })),
    ])

    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: next(calls))

    res, stats = call_llm_validated("u", "s", ComprehensionResult)
    assert stats.retries_used == 1


def test_call_llm_validated_max_retries_exhausted_raises(monkeypatch):
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _make_response("bad"))

    with pytest.raises(LLMValidationError) as e:
        call_llm_validated("u", "s", ComprehensionResult)

    assert e.value.last_raw
    assert e.value.last_errors


def test_call_llm_validated_zero_retries_immediate_raise(monkeypatch):
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _make_response("bad"))

    with pytest.raises(LLMValidationError):
        call_llm_validated("u", "s", ComprehensionResult, max_retries=0)


def test_call_llm_validated_re_prompt_includes_error(monkeypatch):
    captured = []

    def fake_chat(self, **kwargs):
        captured.append(kwargs["messages"][1]["content"])
        if len(captured) == 1:
            return _make_response("bad")
        return _make_response(json.dumps({
            "comprehension": "x",
            "intent": "files",
            "assumptions": [],
            "confidence": 0.9,
            "needs_clarification": False,
        }))

    monkeypatch.setattr("ollama.Client.chat", fake_chat)

    call_llm_validated("u", "s", ComprehensionResult)
    assert "[ERROR PREVIO]" in captured[1]


def test_call_llm_validated_strips_code_fences(monkeypatch):
    content = "```json\n" + json.dumps({
        "comprehension": "x",
        "intent": "files",
        "assumptions": [],
        "confidence": 0.9,
        "needs_clarification": False,
    }) + "\n```"

    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _make_response(content))

    res, _ = call_llm_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"


def test_call_llm_validated_extracts_json_object(monkeypatch):
    content = "texto " + json.dumps({
        "comprehension": "x",
        "intent": "files",
        "assumptions": [],
        "confidence": 0.9,
        "needs_clarification": False,
    }) + " fin"

    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _make_response(content))

    res, _ = call_llm_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"


def test_health_check_model_present(monkeypatch):
    monkeypatch.setattr("ollama.list", lambda: {"models": [{"name": "llama3.1:8b-instruct-q5_K_M"}]})
    assert health_check()


def test_health_check_model_absent(monkeypatch):
    monkeypatch.setattr("ollama.list", lambda: {"models": [{"name": "other"}]})
    assert not health_check()


def test_health_check_connection_error_returns_false(monkeypatch):
    def boom():
        raise Exception("fail")
    monkeypatch.setattr("ollama.list", boom)
    assert not health_check()


def test_strip_code_fences_with_json_marker():
    assert _strip_code_fences("```json\n{}\n```") == "{}"


def test_strip_code_fences_without_marker():
    assert _strip_code_fences("```\n{}\n```") == "{}"


def test_strip_code_fences_no_fences_passthrough():
    assert _strip_code_fences("{}") == "{}"


def test_extract_json_object_clean():
    assert _extract_json_object("foo {a:1} bar") == "{a:1}"


def test_extract_json_object_no_braces_passthrough():
    assert _extract_json_object("foo") == "foo"
