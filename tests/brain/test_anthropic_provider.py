import json
from types import SimpleNamespace

import pytest

from sunny.brain.ollama_client import (
    LLMConnectionError,
    LLMTimeoutError,
    LLMValidationError,
)
from sunny.brain.providers.anthropic_provider import (
    DEFAULT_ANTHROPIC_MODEL,
    AnthropicProvider,
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


def _make_response(content: str, input_tokens: int = 12, output_tokens: int = 8):
    """Construye una respuesta tipo Anthropic Messages API.

    El response.content es una lista de bloques; sólo los de type='text' deben
    ser extraídos. Incluimos un bloque thinking para verificar que se ignora.
    """
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="razonando..."),
            SimpleNamespace(type="text", text=content),
        ],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        stop_reason="end_turn",
    )


class _FakeClient:
    def __init__(self, responses, models_ok=True):
        self._responses = list(responses)
        self.calls = []
        self._models_ok = models_ok
        self.messages = SimpleNamespace(create=self._create)
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


# --- Inicialización ---------------------------------------------------------

def test_missing_api_key_raises_environment_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(EnvironmentError) as excinfo:
        AnthropicProvider()
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)


def test_explicit_api_key_accepted(monkeypatch):
    captured = {}

    class _FakeAnthropicModule:
        @staticmethod
        def Anthropic(api_key):
            captured["api_key"] = api_key
            return _FakeClient([])

    monkeypatch.setattr(
        "sunny.brain.providers.anthropic_provider._load_anthropic_module",
        lambda: _FakeAnthropicModule,
    )
    p = AnthropicProvider(api_key="explicit-key")
    assert captured["api_key"] == "explicit-key"
    assert p._model == DEFAULT_ANTHROPIC_MODEL


def test_model_from_env_overrides_default(monkeypatch):
    monkeypatch.setenv("SUNNY_ANTHROPIC_MODEL", "claude-opus-4-7")
    p = AnthropicProvider(client=_FakeClient([]))
    assert p._model == "claude-opus-4-7"


def test_thinking_default_on():
    p = AnthropicProvider(client=_FakeClient([]))
    assert p._thinking_enabled is True


def test_thinking_env_off_disables(monkeypatch):
    monkeypatch.setenv("SUNNY_ANTHROPIC_THINKING", "off")
    p = AnthropicProvider(client=_FakeClient([]))
    assert p._thinking_enabled is False


def test_thinking_explicit_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("SUNNY_ANTHROPIC_THINKING", "off")
    p = AnthropicProvider(client=_FakeClient([]), thinking=True)
    assert p._thinking_enabled is True


# --- call_validated ---------------------------------------------------------

def test_call_validated_success_first_try():
    client = _FakeClient([_make_response(_comp_json())])
    p = AnthropicProvider(client=client, model="m")

    res, stats = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"
    assert stats.retries_used == 0
    assert stats.tokens_in == 12
    assert stats.tokens_out == 8


def test_call_validated_sets_system_and_user_message():
    client = _FakeClient([_make_response(_comp_json())])
    p = AnthropicProvider(client=client, model="m")
    p.call_validated("user prompt", "system prompt", ComprehensionResult)

    kwargs = client.calls[0]
    assert kwargs["model"] == "m"
    # System contiene refuerzo JSON
    assert "system prompt" in kwargs["system"]
    assert "JSON" in kwargs["system"]
    # Solo mensaje user (no embeddings de system en messages)
    assert kwargs["messages"] == [{"role": "user", "content": "user prompt"}]
    # max_tokens es obligatorio en Anthropic
    assert kwargs["max_tokens"] > 0


def test_call_validated_uses_adaptive_thinking_by_default():
    client = _FakeClient([_make_response(_comp_json())])
    p = AnthropicProvider(client=client, model="m")
    p.call_validated("u", "s", ComprehensionResult)

    kwargs = client.calls[0]
    assert kwargs.get("thinking") == {"type": "adaptive"}
    # Con thinking on, temperature no se envía
    assert "temperature" not in kwargs


def test_call_validated_with_thinking_off_sends_temperature():
    client = _FakeClient([_make_response(_comp_json())])
    p = AnthropicProvider(client=client, model="m", thinking=False)
    p.call_validated("u", "s", ComprehensionResult, temperature=0.3)

    kwargs = client.calls[0]
    assert "thinking" not in kwargs
    assert kwargs["temperature"] == 0.3


def test_call_validated_retries_on_invalid_json_then_succeeds():
    client = _FakeClient([
        _make_response("no es json válido"),
        _make_response(_comp_json()),
    ])
    p = AnthropicProvider(client=client, model="m")

    res, stats = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"
    assert stats.retries_used == 1


def test_retry_includes_required_fields_hint():
    client = _FakeClient([
        _make_response('{"intent": "bad"}'),
        _make_response(_comp_json()),
    ])
    p = AnthropicProvider(client=client, model="m")

    p.call_validated("orig prompt", "s", ComprehensionResult)

    second_user_prompt = client.calls[1]["messages"][0]["content"]
    assert "[ERROR PREVIO]" in second_user_prompt
    assert "Campos requeridos" in second_user_prompt
    assert "intent" in second_user_prompt


def test_call_validated_exhausts_retries_raises():
    client = _FakeClient([_make_response("bad")] * 5)
    p = AnthropicProvider(client=client, model="m")

    with pytest.raises(LLMValidationError) as excinfo:
        p.call_validated("u", "s", ComprehensionResult, max_retries=2)
    assert excinfo.value.last_raw == "bad"


def test_call_validated_strips_code_fences():
    client = _FakeClient([_make_response(f"```json\n{_comp_json()}\n```")])
    p = AnthropicProvider(client=client, model="m")

    res, _ = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"


def test_call_validated_extracts_json_from_surrounding_text():
    """Sanity: si el modelo añade texto antes/después del JSON, se extrae el objeto."""
    wrapped = f"Aquí tienes la respuesta:\n{_comp_json()}\nEspero que sirva."
    client = _FakeClient([_make_response(wrapped)])
    p = AnthropicProvider(client=client, model="m")

    res, _ = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"


def test_call_validated_ignores_thinking_blocks():
    """Sólo los bloques type='text' se concatenan; thinking se ignora."""
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="esto no debería aparecer"),
            SimpleNamespace(type="text", text=_comp_json()),
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )
    client = _FakeClient([response])
    p = AnthropicProvider(client=client, model="m")

    res, _ = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"


def test_call_validated_ignores_num_ctx_silently():
    client = _FakeClient([_make_response(_comp_json())])
    p = AnthropicProvider(client=client, model="m")
    p.call_validated("u", "s", ComprehensionResult, num_ctx=99999)
    assert "num_ctx" not in client.calls[0]


# --- call_text --------------------------------------------------------------

def test_call_text_returns_concatenated_text():
    client = _FakeClient([_make_response("hola mundo")])
    p = AnthropicProvider(client=client, model="m")

    text, stats = p.call_text("u", "s")
    assert text == "hola mundo"
    assert stats.tokens_in == 12
    assert stats.tokens_out == 8


def test_call_text_does_not_add_json_reinforcement():
    """call_text no debe contaminar el system con instrucciones JSON."""
    client = _FakeClient([_make_response("respuesta libre")])
    p = AnthropicProvider(client=client, model="m")
    p.call_text("u", "sistema base")

    kwargs = client.calls[0]
    assert kwargs["system"] == "sistema base"


def test_timeout_forwarded():
    client = _FakeClient([_make_response(_comp_json())])
    p = AnthropicProvider(client=client, model="m")
    p.call_validated("u", "s", ComprehensionResult, timeout_sec=45)
    assert client.calls[0]["timeout"] == 45


# --- Mapeo de excepciones ---------------------------------------------------

def test_timeout_exception_mapped():
    class APITimeoutError(Exception):
        pass

    client = _FakeClient([APITimeoutError("read timeout")])
    p = AnthropicProvider(client=client, model="m")
    with pytest.raises(LLMTimeoutError):
        p.call_text("u", "s")


def test_connection_error_mapped():
    class APIConnectionError(Exception):
        pass

    client = _FakeClient([APIConnectionError("connection refused")])
    p = AnthropicProvider(client=client, model="m")
    with pytest.raises(LLMConnectionError):
        p.call_text("u", "s")


def test_rate_limit_mapped_to_connection_error():
    """Rate limits son transitorios → LLMConnectionError para que el fallback los considere retryables."""

    class RateLimitError(Exception):
        pass

    client = _FakeClient([RateLimitError("rate_limit exceeded 429")])
    p = AnthropicProvider(client=client, model="m")
    with pytest.raises(LLMConnectionError):
        p.call_text("u", "s")


# --- health_check -----------------------------------------------------------

def test_health_check_returns_true_when_models_ok():
    p = AnthropicProvider(client=_FakeClient([], models_ok=True))
    assert p.health_check() is True


def test_health_check_returns_false_when_client_fails():
    p = AnthropicProvider(client=_FakeClient([], models_ok=False))
    assert p.health_check() is False
