import json
from types import SimpleNamespace

import pytest

from sunny.brain.ollama_client import LLMValidationError
from sunny.brain.providers.groq_provider import (
    DEFAULT_GROQ_MODEL,
    GroqProvider,
)
from sunny.core.models.plan import ComprehensionResult


def _comp_json() -> str:
    return json.dumps({
        "comprehension": "x",
        "intent": "files",
        "assumptions": [],
        "confidence": 0.9,
        "needs_clarification": False,
    })


def _make_response(content: str, prompt_tokens: int = 12, completion_tokens: int = 8):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )


class _FakeClient:
    def __init__(self, responses, models_ok=True):
        self._responses = list(responses)
        self.calls = []
        self._models_ok = models_ok
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.models = SimpleNamespace(list=self._models_list)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def _models_list(self):
        if not self._models_ok:
            raise RuntimeError("models down")
        return SimpleNamespace(data=[])


def test_missing_api_key_raises_environment_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(EnvironmentError) as excinfo:
        GroqProvider()
    assert "GROQ_API_KEY" in str(excinfo.value)


def test_explicit_api_key_accepted(monkeypatch):
    captured = {}

    class _FakeGroqModule:
        @staticmethod
        def Groq(api_key):
            captured["api_key"] = api_key
            return _FakeClient([])

    monkeypatch.setattr(
        "sunny.brain.providers.groq_provider._load_groq_module",
        lambda: _FakeGroqModule,
    )
    p = GroqProvider(api_key="explicit-key")
    assert captured["api_key"] == "explicit-key"
    assert p._model == DEFAULT_GROQ_MODEL


def test_model_from_env_overrides_default(monkeypatch):
    monkeypatch.setenv("SUNNY_GROQ_MODEL", "llama-3.1-8b-instant")
    p = GroqProvider(client=_FakeClient([]))
    assert p._model == "llama-3.1-8b-instant"


def test_call_validated_success_first_try():
    client = _FakeClient([_make_response(_comp_json())])
    p = GroqProvider(client=client, model="m")

    res, stats = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"
    assert stats.retries_used == 0
    assert stats.tokens_in == 12
    assert stats.tokens_out == 8


def test_call_validated_uses_json_mode():
    client = _FakeClient([_make_response(_comp_json())])
    p = GroqProvider(client=client, model="m")
    p.call_validated("u", "s", ComprehensionResult)

    kwargs = client.calls[0]
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["model"] == "m"
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1]["role"] == "user"


def test_call_validated_retries_on_invalid_json_then_succeeds():
    client = _FakeClient([
        _make_response("no es json válido"),
        _make_response(_comp_json()),
    ])
    p = GroqProvider(client=client, model="m")

    res, stats = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"
    assert stats.retries_used == 1


def test_retry_includes_required_fields_hint():
    client = _FakeClient([
        _make_response('{"intent": "bad"}'),
        _make_response(_comp_json()),
    ])
    p = GroqProvider(client=client, model="m")

    p.call_validated("orig prompt", "s", ComprehensionResult)

    second_user_prompt = client.calls[1]["messages"][1]["content"]
    assert "[ERROR PREVIO]" in second_user_prompt
    assert "Campos requeridos" in second_user_prompt
    assert "intent" in second_user_prompt


def test_call_validated_exhausts_retries_raises():
    client = _FakeClient([_make_response("bad")] * 5)
    p = GroqProvider(client=client, model="m")

    with pytest.raises(LLMValidationError) as excinfo:
        p.call_validated("u", "s", ComprehensionResult, max_retries=2)
    assert excinfo.value.last_raw == "bad"


def test_call_validated_strips_code_fences():
    client = _FakeClient([_make_response(f"```json\n{_comp_json()}\n```")])
    p = GroqProvider(client=client, model="m")

    res, _ = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"


def test_health_check_returns_true_when_models_ok():
    p = GroqProvider(client=_FakeClient([], models_ok=True))
    assert p.health_check() is True


def test_health_check_returns_false_when_client_fails():
    p = GroqProvider(client=_FakeClient([], models_ok=False))
    assert p.health_check() is False


def test_call_validated_ignores_num_ctx_silently():
    client = _FakeClient([_make_response(_comp_json())])
    p = GroqProvider(client=client, model="m")
    p.call_validated("u", "s", ComprehensionResult, num_ctx=99999)
    assert "num_ctx" not in client.calls[0]


def test_temperature_and_timeout_forwarded():
    client = _FakeClient([_make_response(_comp_json())])
    p = GroqProvider(client=client, model="m")
    p.call_validated("u", "s", ComprehensionResult, temperature=0.7, timeout_sec=45)

    kw = client.calls[0]
    assert kw["temperature"] == 0.7
    assert kw["timeout"] == 45
