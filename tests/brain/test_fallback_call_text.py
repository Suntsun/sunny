from __future__ import annotations

import pytest

from sunny.brain.fallback import FallbackChainProvider, ProviderSpec
from sunny.brain.ollama_client import LLMCallStats, LLMError
from sunny.brain.providers.base import BrainProvider


class _StubProvider(BrainProvider):
    """Stub minimal con call_text/call_validated controlables."""

    def __init__(self, *, text=None, exc=None, healthy=True):
        self._text = text
        self._exc = exc
        self._healthy = healthy
        self.text_calls = 0

    def call_validated(self, user_prompt, system_prompt, schema, **kwargs):
        raise NotImplementedError

    def call_text(self, user_prompt, system_prompt, **kwargs):
        self.text_calls += 1
        if self._exc is not None:
            raise self._exc
        return self._text or "", LLMCallStats(0, 0, 0, 0)

    def health_check(self) -> bool:
        return self._healthy


def _spec(name="prov", model="m"):
    return ProviderSpec(provider=name, model=model)


def test_chain_call_text_primary_success_no_fallback_used():
    primary = _StubProvider(text="hola desde primary")
    secondary = _StubProvider(text="hola desde secondary")
    chain = FallbackChainProvider([
        (_spec("a"), primary), (_spec("b"), secondary),
    ])
    out, _ = chain.call_text("u", "s")
    assert out == "hola desde primary"
    assert primary.text_calls == 1
    assert secondary.text_calls == 0


def test_chain_call_text_falls_back_on_rate_limit():
    primary = _StubProvider(exc=LLMError("rate_limit exceeded"))
    secondary = _StubProvider(text="respuesta de respaldo")
    chain = FallbackChainProvider([
        (_spec("groq"), primary), (_spec("ollama"), secondary),
    ])
    out, _ = chain.call_text("u", "s")
    assert out == "respuesta de respaldo"
    assert primary.text_calls == 1
    assert secondary.text_calls == 1


def test_chain_call_text_falls_back_on_cuda():
    primary = _StubProvider(exc=LLMError("CUDA error: init failed"))
    secondary = _StubProvider(text="cloud salvador")
    chain = FallbackChainProvider([
        (_spec("ollama"), primary), (_spec("groq"), secondary),
    ])
    out, _ = chain.call_text("u", "s")
    assert out == "cloud salvador"


def test_chain_call_text_propagates_non_transient():
    primary = _StubProvider(exc=ValueError("config rota"))
    secondary = _StubProvider(text="never reached")
    chain = FallbackChainProvider([
        (_spec("a"), primary), (_spec("b"), secondary),
    ])
    with pytest.raises(ValueError):
        chain.call_text("u", "s")
    assert secondary.text_calls == 0


def test_chain_call_text_all_transient_raises_last():
    p1 = _StubProvider(exc=LLMError("CUDA error"))
    p2 = _StubProvider(exc=LLMError("rate_limit hit"))
    chain = FallbackChainProvider([
        (_spec("a"), p1), (_spec("b"), p2),
    ])
    with pytest.raises(LLMError, match="rate_limit"):
        chain.call_text("u", "s")
    assert p1.text_calls == 1
    assert p2.text_calls == 1
