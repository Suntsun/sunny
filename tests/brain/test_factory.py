import pytest

from sunny.brain.factory import (
    DEFAULT_PROVIDER,
    PROVIDER_ENV,
    SUPPORTED_PROVIDERS,
    get_brain_provider,
)
from sunny.brain.providers.base import BrainProvider
from sunny.brain.providers.ollama_provider import OllamaProvider


def test_default_is_ollama_when_env_unset(monkeypatch):
    monkeypatch.delenv(PROVIDER_ENV, raising=False)
    p = get_brain_provider()
    assert isinstance(p, OllamaProvider)


def test_explicit_ollama(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "ollama")
    p = get_brain_provider()
    assert isinstance(p, OllamaProvider)


def test_groq_selection_returns_groq_provider(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "groq")
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")

    fake_groq_client = object()

    def fake_init(self, api_key=None, model=None, client=None):
        self._client = fake_groq_client
        self._model = "test-model"

    monkeypatch.setattr(
        "sunny.brain.providers.groq_provider.GroqProvider.__init__", fake_init
    )

    p = get_brain_provider()
    from sunny.brain.providers.groq_provider import GroqProvider
    assert isinstance(p, GroqProvider)


def test_unknown_provider_raises_valueerror(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "anthropic")
    with pytest.raises(ValueError) as excinfo:
        get_brain_provider()
    msg = str(excinfo.value)
    assert "anthropic" in msg
    assert "ollama" in msg and "groq" in msg


def test_empty_provider_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "")
    p = get_brain_provider()
    assert isinstance(p, OllamaProvider)


def test_provider_value_is_case_insensitive(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "OLLAMA")
    p = get_brain_provider()
    assert isinstance(p, OllamaProvider)


def test_provider_value_is_trimmed(monkeypatch):
    monkeypatch.setenv(PROVIDER_ENV, "  ollama  ")
    p = get_brain_provider()
    assert isinstance(p, OllamaProvider)


def test_returns_instance_of_brainprovider(monkeypatch):
    monkeypatch.delenv(PROVIDER_ENV, raising=False)
    p = get_brain_provider()
    assert isinstance(p, BrainProvider)


def test_default_constant_is_ollama():
    assert DEFAULT_PROVIDER == "ollama"


def test_supported_providers_includes_ollama_and_groq():
    assert "ollama" in SUPPORTED_PROVIDERS
    assert "groq" in SUPPORTED_PROVIDERS
