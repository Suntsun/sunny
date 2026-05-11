from __future__ import annotations

import pytest
from pydantic import BaseModel

from sunny.brain.fallback import (
    FallbackChainProvider,
    ProviderSpec,
    is_transient_error,
)
from sunny.brain.ollama_client import (
    LLMCallStats,
    LLMConnectionError,
    LLMError,
    LLMTimeoutError,
    LLMValidationError,
)
from sunny.brain.providers.base import BrainProvider


class _Schema(BaseModel):
    x: int


class _StubProvider(BrainProvider):
    """Provider de prueba: o devuelve un valor o lanza una excepción dada."""

    def __init__(self, *, result=None, text=None, exc=None, healthy=True):
        self._result = result
        self._text = text
        self._exc = exc
        self._healthy = healthy
        self.calls = 0
        self.text_calls = 0

    def call_validated(self, user_prompt, system_prompt, schema, **kwargs):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._result, LLMCallStats(0, 0, 0, 0)

    def call_text(self, user_prompt, system_prompt, **kwargs):
        self.text_calls += 1
        if self._exc is not None:
            raise self._exc
        return self._text or "", LLMCallStats(0, 0, 0, 0)

    def health_check(self) -> bool:
        return self._healthy


def _spec(name="prov", model="m"):
    return ProviderSpec(provider=name, model=model)


def test_transient_connection_error():
    assert is_transient_error(LLMConnectionError("net down"))


def test_transient_timeout_error():
    assert is_transient_error(LLMTimeoutError("slow"))


def test_transient_validation_error():
    err = LLMValidationError("bad", last_raw="{", last_errors=["e"])
    assert is_transient_error(err)


@pytest.mark.parametrize("msg", [
    "Rate limit exceeded",
    "Request too large for model",
    "429 Too Many Requests",
    "413 payload too big",
    "CUDA error: shared object initialization failed",
    "tokens per minute",
    "service unavailable",
    "context window exceeded",
    "model_not_found",
    "out of memory loading qwen",
])
def test_transient_llm_error_substrings(msg):
    assert is_transient_error(LLMError(msg)), msg


def test_non_transient_llm_error():
    assert not is_transient_error(LLMError("schema mismatch in response"))


def test_non_transient_value_error():
    assert not is_transient_error(ValueError("bad config"))


def test_non_transient_environment_error():
    assert not is_transient_error(EnvironmentError("API key missing"))


def test_chain_empty_raises():
    with pytest.raises(ValueError):
        FallbackChainProvider([])


def test_chain_primary_success_no_fallback_used():
    primary = _StubProvider(result=_Schema(x=1))
    secondary = _StubProvider(result=_Schema(x=2))
    chain = FallbackChainProvider([
        (_spec("a"), primary),
        (_spec("b"), secondary),
    ])
    result, _ = chain.call_validated("u", "s", _Schema)
    assert result.x == 1
    assert primary.calls == 1
    assert secondary.calls == 0


def test_chain_falls_back_on_transient_error():
    primary = _StubProvider(exc=LLMError("Rate limit exceeded"))
    secondary = _StubProvider(result=_Schema(x=42))
    chain = FallbackChainProvider([
        (_spec("groq"), primary),
        (_spec("ollama"), secondary),
    ])
    result, _ = chain.call_validated("u", "s", _Schema)
    assert result.x == 42
    assert primary.calls == 1
    assert secondary.calls == 1


def test_chain_falls_back_on_cuda_error():
    primary = _StubProvider(exc=LLMError("CUDA error: shared object init failed"))
    secondary = _StubProvider(result=_Schema(x=7))
    chain = FallbackChainProvider([
        (_spec("ollama", "qwen2.5:14b"), primary),
        (_spec("groq", "llama-3.3-70b-versatile"), secondary),
    ])
    result, _ = chain.call_validated("u", "s", _Schema)
    assert result.x == 7


def test_chain_propagates_non_transient_immediately():
    primary = _StubProvider(exc=ValueError("config rota"))
    secondary = _StubProvider(result=_Schema(x=1))
    chain = FallbackChainProvider([
        (_spec("a"), primary),
        (_spec("b"), secondary),
    ])
    with pytest.raises(ValueError, match="config rota"):
        chain.call_validated("u", "s", _Schema)
    assert primary.calls == 1
    assert secondary.calls == 0


def test_chain_raises_last_error_when_all_fail():
    primary = _StubProvider(exc=LLMConnectionError("net1"))
    secondary = _StubProvider(exc=LLMError("Rate limit hit"))
    chain = FallbackChainProvider([
        (_spec("a"), primary),
        (_spec("b"), secondary),
    ])
    with pytest.raises(LLMError, match="Rate limit hit"):
        chain.call_validated("u", "s", _Schema)
    assert primary.calls == 1
    assert secondary.calls == 1


def test_chain_three_providers_skips_two():
    p1 = _StubProvider(exc=LLMConnectionError("down"))
    p2 = _StubProvider(exc=LLMError("429 rate limit"))
    p3 = _StubProvider(result=_Schema(x=99))
    chain = FallbackChainProvider([
        (_spec("a"), p1), (_spec("b"), p2), (_spec("c"), p3),
    ])
    result, _ = chain.call_validated("u", "s", _Schema)
    assert result.x == 99
    assert (p1.calls, p2.calls, p3.calls) == (1, 1, 1)


def test_chain_health_check_any_healthy():
    chain = FallbackChainProvider([
        (_spec("a"), _StubProvider(healthy=False)),
        (_spec("b"), _StubProvider(healthy=True)),
    ])
    assert chain.health_check() is True


def test_chain_health_check_none_healthy():
    chain = FallbackChainProvider([
        (_spec("a"), _StubProvider(healthy=False)),
        (_spec("b"), _StubProvider(healthy=False)),
    ])
    assert chain.health_check() is False


def test_chain_specs_property_exposes_order():
    chain = FallbackChainProvider([
        (_spec("groq", "x"), _StubProvider(result=_Schema(x=1))),
        (_spec("ollama", "y"), _StubProvider(result=_Schema(x=2))),
    ])
    names = [(s.provider, s.model) for s in chain.chain_specs]
    assert names == [("groq", "x"), ("ollama", "y")]
