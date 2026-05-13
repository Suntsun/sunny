import json
from types import SimpleNamespace

import pytest

from sunny.brain.ollama_client import (
    LLMConnectionError,
    LLMTimeoutError,
    LLMValidationError,
)
from sunny.brain.providers.gemini_provider import (
    DEFAULT_GEMINI_MODEL,
    GeminiProvider,
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


def _make_response(text: str, prompt_tokens: int = 12, candidates_tokens: int = 8):
    """Construye una respuesta tipo google-genai.

    El SDK real expone ``response.text`` (concatenación de partes type=text) y
    ``response.usage_metadata.{prompt_token_count, candidates_token_count}``.
    Replicamos esa forma en el mock.
    """
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=candidates_tokens,
        ),
    )


class _FakeClient:
    def __init__(self, responses, models_ok=True):
        self._responses = list(responses)
        self.calls = []
        self._models_ok = models_ok
        self.models = SimpleNamespace(
            generate_content=self._generate,
            list=self._models_list,
        )

    def _generate(self, **kwargs):
        self.calls.append(kwargs)
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def _models_list(self):
        if not self._models_ok:
            raise RuntimeError("models down")
        return []


# --- Inicialización ---------------------------------------------------------

def test_missing_api_key_raises_environment_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(EnvironmentError) as excinfo:
        GeminiProvider()
    assert "GEMINI_API_KEY" in str(excinfo.value)


def test_explicit_api_key_accepted(monkeypatch):
    captured = {}

    class _FakeGenaiModule:
        @staticmethod
        def Client(api_key):
            captured["api_key"] = api_key
            return _FakeClient([])

    monkeypatch.setattr(
        "sunny.brain.providers.gemini_provider._load_genai_module",
        lambda: _FakeGenaiModule,
    )
    p = GeminiProvider(api_key="explicit-key")
    assert captured["api_key"] == "explicit-key"
    assert p._model == DEFAULT_GEMINI_MODEL


def test_model_from_env_overrides_default(monkeypatch):
    monkeypatch.setenv("SUNNY_GEMINI_MODEL", "gemini-2.5-pro")
    p = GeminiProvider(client=_FakeClient([]))
    assert p._model == "gemini-2.5-pro"


def test_thinking_default_on():
    p = GeminiProvider(client=_FakeClient([]))
    assert p._thinking_enabled is True


def test_thinking_env_off_disables(monkeypatch):
    monkeypatch.setenv("SUNNY_GEMINI_THINKING", "off")
    p = GeminiProvider(client=_FakeClient([]))
    assert p._thinking_enabled is False


def test_thinking_explicit_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("SUNNY_GEMINI_THINKING", "off")
    p = GeminiProvider(client=_FakeClient([]), thinking=True)
    assert p._thinking_enabled is True


# --- call_validated ---------------------------------------------------------

def test_call_validated_success_first_try():
    client = _FakeClient([_make_response(_comp_json())])
    p = GeminiProvider(client=client, model="m")

    res, stats = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"
    assert stats.retries_used == 0
    assert stats.tokens_in == 12
    assert stats.tokens_out == 8


def test_call_validated_sets_system_and_user_content():
    client = _FakeClient([_make_response(_comp_json())])
    p = GeminiProvider(client=client, model="m")
    p.call_validated("user prompt", "system prompt", ComprehensionResult)

    kwargs = client.calls[0]
    assert kwargs["model"] == "m"
    assert kwargs["contents"] == "user prompt"
    cfg = kwargs["config"]
    assert "system prompt" in cfg["system_instruction"]
    assert "JSON" in cfg["system_instruction"]
    assert cfg["max_output_tokens"] > 0


def test_call_validated_uses_dynamic_thinking_by_default():
    client = _FakeClient([_make_response(_comp_json())])
    p = GeminiProvider(client=client, model="m")
    p.call_validated("u", "s", ComprehensionResult)

    cfg = client.calls[0]["config"]
    assert cfg.get("thinking_config") == {"thinking_budget": -1}
    # Con thinking on, temperature no se envía
    assert "temperature" not in cfg


def test_call_validated_with_thinking_off_sends_temperature():
    client = _FakeClient([_make_response(_comp_json())])
    p = GeminiProvider(client=client, model="m", thinking=False)
    p.call_validated("u", "s", ComprehensionResult, temperature=0.3)

    cfg = client.calls[0]["config"]
    assert cfg.get("thinking_config") == {"thinking_budget": 0}
    assert cfg["temperature"] == 0.3


def test_call_validated_retries_on_invalid_json_then_succeeds():
    client = _FakeClient([
        _make_response("no es json válido"),
        _make_response(_comp_json()),
    ])
    p = GeminiProvider(client=client, model="m")

    res, stats = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"
    assert stats.retries_used == 1


def test_retry_includes_required_fields_hint():
    client = _FakeClient([
        _make_response('{"intent": "bad"}'),
        _make_response(_comp_json()),
    ])
    p = GeminiProvider(client=client, model="m")

    p.call_validated("orig prompt", "s", ComprehensionResult)

    second_user_prompt = client.calls[1]["contents"]
    assert "[ERROR PREVIO]" in second_user_prompt
    assert "Campos requeridos" in second_user_prompt
    assert "intent" in second_user_prompt


def test_call_validated_exhausts_retries_raises():
    client = _FakeClient([_make_response("bad")] * 5)
    p = GeminiProvider(client=client, model="m")

    with pytest.raises(LLMValidationError) as excinfo:
        p.call_validated("u", "s", ComprehensionResult, max_retries=2)
    assert excinfo.value.last_raw == "bad"


def test_call_validated_strips_code_fences():
    client = _FakeClient([_make_response(f"```json\n{_comp_json()}\n```")])
    p = GeminiProvider(client=client, model="m")

    res, _ = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"


def test_call_validated_extracts_json_from_surrounding_text():
    wrapped = f"Aquí tienes la respuesta:\n{_comp_json()}\nEspero que sirva."
    client = _FakeClient([_make_response(wrapped)])
    p = GeminiProvider(client=client, model="m")

    res, _ = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"


def test_call_validated_falls_back_to_candidates_parts():
    """Si response.text es None, debe iterar candidates[*].content.parts
    e ignorar partes marcadas como thought."""
    response = SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=[
                    SimpleNamespace(thought=True, text="esto no debería aparecer"),
                    SimpleNamespace(thought=False, text=_comp_json()),
                ])
            )
        ],
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=20,
        ),
    )
    client = _FakeClient([response])
    p = GeminiProvider(client=client, model="m")

    res, _ = p.call_validated("u", "s", ComprehensionResult)
    assert res.intent == "files"


def test_call_validated_ignores_num_ctx_silently():
    client = _FakeClient([_make_response(_comp_json())])
    p = GeminiProvider(client=client, model="m")
    p.call_validated("u", "s", ComprehensionResult, num_ctx=99999)
    cfg = client.calls[0]["config"]
    assert "num_ctx" not in cfg


# --- call_text --------------------------------------------------------------

def test_call_text_returns_text():
    client = _FakeClient([_make_response("hola mundo")])
    p = GeminiProvider(client=client, model="m")

    text, stats = p.call_text("u", "s")
    assert text == "hola mundo"
    assert stats.tokens_in == 12
    assert stats.tokens_out == 8


def test_call_text_does_not_add_json_reinforcement():
    """call_text no debe contaminar el system_instruction con instrucciones JSON."""
    client = _FakeClient([_make_response("respuesta libre")])
    p = GeminiProvider(client=client, model="m")
    p.call_text("u", "sistema base")

    cfg = client.calls[0]["config"]
    assert cfg["system_instruction"] == "sistema base"


# --- Mapeo de excepciones ---------------------------------------------------

def test_timeout_exception_mapped():
    class APITimeoutError(Exception):
        pass

    client = _FakeClient([APITimeoutError("deadline exceeded")])
    p = GeminiProvider(client=client, model="m")
    with pytest.raises(LLMTimeoutError):
        p.call_text("u", "s")


def test_connection_error_mapped():
    class APIConnectionError(Exception):
        pass

    client = _FakeClient([APIConnectionError("connection refused")])
    p = GeminiProvider(client=client, model="m")
    with pytest.raises(LLMConnectionError):
        p.call_text("u", "s")


def test_resource_exhausted_mapped_to_connection_error():
    """RESOURCE_EXHAUSTED (429 de Gemini) → LLMConnectionError para fallback retry."""

    class ClientError(Exception):
        pass

    client = _FakeClient([ClientError("RESOURCE_EXHAUSTED quota exceeded")])
    p = GeminiProvider(client=client, model="m")
    with pytest.raises(LLMConnectionError):
        p.call_text("u", "s")


def test_rate_limit_429_mapped_to_connection_error():
    class ClientError(Exception):
        pass

    client = _FakeClient([ClientError("rate_limit hit 429")])
    p = GeminiProvider(client=client, model="m")
    with pytest.raises(LLMConnectionError):
        p.call_text("u", "s")


# --- health_check -----------------------------------------------------------

def test_health_check_returns_true_when_models_ok():
    p = GeminiProvider(client=_FakeClient([], models_ok=True))
    assert p.health_check() is True


def test_health_check_returns_false_when_client_fails():
    p = GeminiProvider(client=_FakeClient([], models_ok=False))
    assert p.health_check() is False
