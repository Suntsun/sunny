"""Tests para los roles del bucle de entorno (M5/M6/M7)."""
import pytest

from sunny.brain.factory import BrainRole, get_provider_for_role
from sunny.brain.fallback import FallbackChainProvider
from sunny.brain.providers.base import BrainProvider
from sunny.brain.providers.ollama_provider import OllamaProvider


_ROLE_ENVS = (
    "SUNNY_M5_PROVIDER", "SUNNY_M5_MODEL",
    "SUNNY_M6_PROVIDER", "SUNNY_M6_MODEL",
    "SUNNY_M7_PROVIDER", "SUNNY_M7_MODEL",
    "SUNNY_M5_FALLBACK_PROVIDER", "SUNNY_M5_FALLBACK_MODEL",
    "SUNNY_M6_FALLBACK_PROVIDER", "SUNNY_M6_FALLBACK_MODEL",
    "SUNNY_M7_FALLBACK_PROVIDER", "SUNNY_M7_FALLBACK_MODEL",
)


@pytest.fixture(autouse=True)
def _clean_role_env(monkeypatch):
    for var in _ROLE_ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _stub_cerebras(monkeypatch):
    """Evita que CerebrasProvider exija CEREBRAS_API_KEY al instanciar."""

    def fake_init(self, api_key=None, model=None, client=None):
        self._model = model or "stub-model"
        self._client = object()

    monkeypatch.setattr(
        "sunny.brain.providers.cerebras_provider.CerebrasProvider.__init__",
        fake_init,
    )


def _stub_anthropic(monkeypatch):
    """Evita que AnthropicProvider exija ANTHROPIC_API_KEY al instanciar."""

    def fake_init(self, api_key=None, model=None, client=None, thinking=None):
        self._model = model or "stub-model"
        self._client = object()
        self._thinking_enabled = True

    monkeypatch.setattr(
        "sunny.brain.providers.anthropic_provider.AnthropicProvider.__init__",
        fake_init,
    )


def test_brain_role_enum_includes_environment_loop_roles():
    names = {r.name for r in BrainRole}
    assert {"PERCEPTION", "REASONER", "CONTROLLER"}.issubset(names)


def test_perception_default_is_ollama_qwen():
    p = get_provider_for_role(BrainRole.PERCEPTION)
    assert isinstance(p, OllamaProvider)
    assert p._model == "qwen2.5:3b"


def test_reasoner_default_is_anthropic_sonnet(monkeypatch):
    _stub_anthropic(monkeypatch)
    from sunny.brain.providers.anthropic_provider import AnthropicProvider

    p = get_provider_for_role(BrainRole.REASONER)
    assert isinstance(p, AnthropicProvider)
    assert p._model == "claude-sonnet-4-6"


def test_controller_default_is_ollama_qwen():
    p = get_provider_for_role(BrainRole.CONTROLLER)
    assert isinstance(p, OllamaProvider)
    assert p._model == "qwen2.5:3b"


def test_environment_roles_return_brainprovider_instances():
    assert isinstance(get_provider_for_role(BrainRole.PERCEPTION), BrainProvider)
    assert isinstance(get_provider_for_role(BrainRole.CONTROLLER), BrainProvider)


def test_perception_respects_provider_override(monkeypatch):
    _stub_cerebras(monkeypatch)
    from sunny.brain.providers.cerebras_provider import CerebrasProvider

    monkeypatch.setenv("SUNNY_M5_PROVIDER", "cerebras")
    monkeypatch.setenv("SUNNY_M5_MODEL", "llama3.1-8b")
    p = get_provider_for_role(BrainRole.PERCEPTION)
    assert isinstance(p, CerebrasProvider)
    assert p._model == "llama3.1-8b"


def test_reasoner_respects_model_override(monkeypatch):
    _stub_anthropic(monkeypatch)
    from sunny.brain.providers.anthropic_provider import AnthropicProvider

    monkeypatch.setenv("SUNNY_M6_MODEL", "claude-opus-4-7")
    p = get_provider_for_role(BrainRole.REASONER)
    assert isinstance(p, AnthropicProvider)
    assert p._model == "claude-opus-4-7"


def test_controller_respects_provider_override(monkeypatch):
    monkeypatch.setenv("SUNNY_M7_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M7_MODEL", "llama3.1:8b-instruct-q5_K_M")
    p = get_provider_for_role(BrainRole.CONTROLLER)
    assert isinstance(p, OllamaProvider)
    assert p._model == "llama3.1:8b-instruct-q5_K_M"


def test_reasoner_fallback_chain_wraps_when_env_present(monkeypatch):
    _stub_cerebras(monkeypatch)
    monkeypatch.setenv("SUNNY_M6_PROVIDER", "cerebras")
    monkeypatch.setenv("SUNNY_M6_MODEL", "llama3.1-8b")
    monkeypatch.setenv("SUNNY_M6_FALLBACK_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M6_FALLBACK_MODEL", "qwen2.5:3b")
    p = get_provider_for_role(BrainRole.REASONER)
    assert isinstance(p, FallbackChainProvider)
    specs = p.chain_specs
    assert len(specs) == 2
    assert (specs[0].provider, specs[0].model) == ("cerebras", "llama3.1-8b")
    assert (specs[1].provider, specs[1].model) == ("ollama", "qwen2.5:3b")


def test_perception_unset_env_uses_defaults():
    """Sanity: sin env vars, el slot M5 cae a su default sin error."""
    p = get_provider_for_role(BrainRole.PERCEPTION)
    assert isinstance(p, OllamaProvider)
