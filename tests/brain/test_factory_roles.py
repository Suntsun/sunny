import pytest

from sunny.brain.factory import BrainRole, get_provider_for_role
from sunny.brain.fallback import FallbackChainProvider
from sunny.brain.providers.base import BrainProvider
from sunny.brain.providers.ollama_provider import OllamaProvider


_ROLE_ENVS = (
    "SUNNY_M1_PROVIDER", "SUNNY_M1_MODEL",
    "SUNNY_M2_PROVIDER", "SUNNY_M2_MODEL",
    "SUNNY_M3_PROVIDER", "SUNNY_M3_MODEL",
    "SUNNY_M4_PROVIDER", "SUNNY_M4_MODEL",
)


@pytest.fixture(autouse=True)
def _clean_role_env(monkeypatch):
    for var in _ROLE_ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


def _stub_cerebras(monkeypatch):
    """Evita que CerebrasProvider exija CEREBRAS_API_KEY al instanciar."""

    def fake_init(self, api_key=None, model=None, client=None):
        self._model = model or "stub-model"
        self._client = object()

    monkeypatch.setattr(
        "sunny.brain.providers.cerebras_provider.CerebrasProvider.__init__",
        fake_init,
    )


def test_brain_role_enum_has_four_values():
    assert len(list(BrainRole)) == 4
    names = {r.name for r in BrainRole}
    assert names == {"COMPREHENSION", "PLANNING", "GUI_AGENT", "OCR_SUMMARIZER"}


def test_get_provider_for_role_comprehension_default_is_ollama():
    p = get_provider_for_role(BrainRole.COMPREHENSION)
    assert isinstance(p, OllamaProvider)
    assert p._model == "qwen2.5:3b"


def test_get_provider_for_role_ocr_summarizer_default_is_ollama():
    p = get_provider_for_role(BrainRole.OCR_SUMMARIZER)
    assert isinstance(p, OllamaProvider)
    assert p._model == "qwen2.5:3b"


def test_get_provider_for_role_planning_default_is_cerebras(monkeypatch):
    _stub_cerebras(monkeypatch)
    from sunny.brain.providers.cerebras_provider import CerebrasProvider

    p = get_provider_for_role(BrainRole.PLANNING)
    assert isinstance(p, CerebrasProvider)
    assert p._model == "llama3.1-8b"


def test_get_provider_for_role_gui_agent_default_is_cerebras(monkeypatch):
    _stub_cerebras(monkeypatch)
    from sunny.brain.providers.cerebras_provider import CerebrasProvider

    p = get_provider_for_role(BrainRole.GUI_AGENT)
    assert isinstance(p, CerebrasProvider)
    assert p._model == "llama3.1-8b"


def test_get_provider_for_role_respects_provider_override(monkeypatch):
    monkeypatch.setenv("SUNNY_M2_PROVIDER", "ollama")
    p = get_provider_for_role(BrainRole.PLANNING)
    assert isinstance(p, OllamaProvider)


def test_get_provider_for_role_respects_model_override(monkeypatch):
    monkeypatch.setenv("SUNNY_M1_MODEL", "qwen2.5:14b-instruct-q4_K_M")
    p = get_provider_for_role(BrainRole.COMPREHENSION)
    assert isinstance(p, OllamaProvider)
    assert p._model == "qwen2.5:14b-instruct-q4_K_M"


def test_get_provider_for_role_returns_brainprovider_instance():
    p = get_provider_for_role(BrainRole.COMPREHENSION)
    assert isinstance(p, BrainProvider)


def test_get_provider_for_role_unknown_role_raises():
    with pytest.raises(ValueError):
        get_provider_for_role("invalid")  # type: ignore[arg-type]


def test_get_provider_for_role_provider_value_is_trimmed_and_case_insensitive(monkeypatch):
    monkeypatch.setenv("SUNNY_M2_PROVIDER", "  OLLAMA  ")
    monkeypatch.setenv("SUNNY_M2_MODEL", "qwen2.5:3b")
    p = get_provider_for_role(BrainRole.PLANNING)
    assert isinstance(p, OllamaProvider)
    assert p._model == "qwen2.5:3b"


# --- Cadena de fallback -----------------------------------------------------

def test_no_fallback_env_returns_primary_unwrapped(monkeypatch):
    monkeypatch.setenv("SUNNY_M1_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_MODEL", "qwen2.5:3b")
    p = get_provider_for_role(BrainRole.COMPREHENSION)
    assert isinstance(p, OllamaProvider)
    assert not isinstance(p, FallbackChainProvider)


def test_fallback_env_wraps_in_chain(monkeypatch):
    monkeypatch.setenv("SUNNY_M1_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("SUNNY_M1_FALLBACK_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_FALLBACK_MODEL", "qwen2.5:14b-instruct-q4_K_M")
    p = get_provider_for_role(BrainRole.COMPREHENSION)
    assert isinstance(p, FallbackChainProvider)
    specs = p.chain_specs
    assert len(specs) == 2
    assert (specs[0].provider, specs[0].model) == ("ollama", "qwen2.5:3b")
    assert (specs[1].provider, specs[1].model) == ("ollama", "qwen2.5:14b-instruct-q4_K_M")


def test_fallback2_appended_after_fallback(monkeypatch):
    monkeypatch.setenv("SUNNY_M1_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("SUNNY_M1_FALLBACK_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_FALLBACK_MODEL", "llama3.1:8b-instruct-q5_K_M")
    monkeypatch.setenv("SUNNY_M1_FALLBACK2_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_FALLBACK2_MODEL", "qwen2.5:14b-instruct-q4_K_M")
    p = get_provider_for_role(BrainRole.COMPREHENSION)
    assert isinstance(p, FallbackChainProvider)
    specs = p.chain_specs
    assert len(specs) == 3
    assert specs[2].model == "qwen2.5:14b-instruct-q4_K_M"


def test_fallback_duplicate_of_primary_is_skipped(monkeypatch):
    monkeypatch.setenv("SUNNY_M1_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("SUNNY_M1_FALLBACK_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_FALLBACK_MODEL", "qwen2.5:3b")
    p = get_provider_for_role(BrainRole.COMPREHENSION)
    assert isinstance(p, OllamaProvider)
    assert not isinstance(p, FallbackChainProvider)


def test_fallback_missing_api_key_is_skipped(monkeypatch):
    monkeypatch.setenv("SUNNY_M1_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("SUNNY_M1_FALLBACK_PROVIDER", "groq")
    monkeypatch.setenv("SUNNY_M1_FALLBACK_MODEL", "llama-3.3-70b-versatile")
    # GROQ_API_KEY no está → groq no se instancia → fallback se omite
    p = get_provider_for_role(BrainRole.COMPREHENSION)
    assert isinstance(p, OllamaProvider)
    assert not isinstance(p, FallbackChainProvider)


def test_fallback_without_model_is_skipped(monkeypatch):
    monkeypatch.setenv("SUNNY_M1_PROVIDER", "ollama")
    monkeypatch.setenv("SUNNY_M1_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("SUNNY_M1_FALLBACK_PROVIDER", "ollama")
    # SUNNY_M1_FALLBACK_MODEL no definida → se ignora
    p = get_provider_for_role(BrainRole.COMPREHENSION)
    assert isinstance(p, OllamaProvider)
    assert not isinstance(p, FallbackChainProvider)
