from __future__ import annotations

import os
from enum import Enum
from typing import List, Optional, Tuple

from sunny.brain.fallback import FallbackChainProvider, ProviderSpec
from sunny.brain.providers.base import BrainProvider
from sunny.core.logging.logger import get_logger

log = get_logger("sunny.brain.factory")

PROVIDER_ENV: str = "SUNNY_BRAIN_PROVIDER"
DEFAULT_PROVIDER: str = "ollama"
SUPPORTED_PROVIDERS = ("ollama", "groq", "cerebras")


class BrainRole(str, Enum):
    """Roles cognitivos del pipeline (arquitectura minibrains).

    Cada rol resuelve a un provider/modelo independiente, configurable por
    variables de entorno ``SUNNY_M{1..4}_PROVIDER`` y ``SUNNY_M{1..4}_MODEL``.
    """

    COMPREHENSION = "comprehension"      # m1 — clasificador rápido
    PLANNING = "planning"                # m2 — planificador capaz
    GUI_AGENT = "gui_agent"              # m3 — agente visual GUI
    OCR_SUMMARIZER = "ocr_summarizer"    # m4 — limpieza/estructura OCR


_ROLE_CONFIG: dict = {
    BrainRole.COMPREHENSION: {
        "slot": "M1",
        "provider_env": "SUNNY_M1_PROVIDER",
        "model_env": "SUNNY_M1_MODEL",
        "default_provider": "ollama",
        "default_model": "qwen2.5:3b",
    },
    BrainRole.PLANNING: {
        "slot": "M2",
        "provider_env": "SUNNY_M2_PROVIDER",
        "model_env": "SUNNY_M2_MODEL",
        "default_provider": "cerebras",
        "default_model": "llama3.1-8b",
    },
    BrainRole.GUI_AGENT: {
        "slot": "M3",
        "provider_env": "SUNNY_M3_PROVIDER",
        "model_env": "SUNNY_M3_MODEL",
        "default_provider": "cerebras",
        "default_model": "llama3.1-8b",
    },
    BrainRole.OCR_SUMMARIZER: {
        "slot": "M4",
        "provider_env": "SUNNY_M4_PROVIDER",
        "model_env": "SUNNY_M4_MODEL",
        "default_provider": "ollama",
        "default_model": "qwen2.5:3b",
    },
}


def get_brain_provider() -> BrainProvider:
    """Devuelve la instancia de BrainProvider seleccionada por entorno.

    Lee ``SUNNY_BRAIN_PROVIDER`` (default: ``ollama``). Importa el módulo
    del provider concreto de forma perezosa para que dependencias
    opcionales (p.ej. el paquete ``groq``) sólo se carguen cuando se usan.
    """
    name = (os.environ.get(PROVIDER_ENV) or DEFAULT_PROVIDER).strip().lower()
    if not name:
        name = DEFAULT_PROVIDER

    if name == "ollama":
        from sunny.brain.providers.ollama_provider import OllamaProvider
        log.info("brain_provider_selected", provider="ollama")
        return OllamaProvider()

    if name == "groq":
        from sunny.brain.providers.groq_provider import GroqProvider
        log.info("brain_provider_selected", provider="groq")
        return GroqProvider()

    if name == "cerebras":
        from sunny.brain.providers.cerebras_provider import CerebrasProvider
        log.info("brain_provider_selected", provider="cerebras")
        return CerebrasProvider()

    raise ValueError(
        f"{PROVIDER_ENV}='{name}' no reconocido. "
        f"Valores soportados: {', '.join(SUPPORTED_PROVIDERS)}."
    )


def _instantiate_provider(provider_name: str, model: Optional[str]) -> BrainProvider:
    provider_name = provider_name.strip().lower()

    if provider_name == "ollama":
        from sunny.brain.providers.ollama_provider import OllamaProvider
        if model:
            return OllamaProvider(model=model)
        return OllamaProvider()

    if provider_name == "groq":
        from sunny.brain.providers.groq_provider import GroqProvider
        return GroqProvider(model=model) if model else GroqProvider()

    if provider_name == "cerebras":
        from sunny.brain.providers.cerebras_provider import CerebrasProvider
        return CerebrasProvider(model=model) if model else CerebrasProvider()

    raise ValueError(
        f"Provider '{provider_name}' no reconocido. "
        f"Valores soportados: {', '.join(SUPPORTED_PROVIDERS)}."
    )


def _try_instantiate(provider_name: str, model: str) -> Optional[BrainProvider]:
    """Instancia un provider o devuelve None si falta la API key.

    Otras excepciones (ImportError, ValueError de provider desconocido)
    se propagan — esas son errores de configuración del usuario.
    """
    try:
        return _instantiate_provider(provider_name, model)
    except EnvironmentError as e:
        log.warning(
            "fallback_skipped_missing_key",
            provider=provider_name,
            model=model,
            reason=str(e),
        )
        return None


def _read_chain_specs_from_env(slot: str, cfg: dict) -> List[Tuple[str, str]]:
    """Lee la cadena (primary + fallbacks) desde env vars para un rol.

    Variables consultadas:
      SUNNY_{slot}_PROVIDER / SUNNY_{slot}_MODEL           — primary
      SUNNY_{slot}_FALLBACK_PROVIDER / _FALLBACK_MODEL     — fallback 1
      SUNNY_{slot}_FALLBACK2_PROVIDER / _FALLBACK2_MODEL   — fallback 2

    Devuelve la lista de (provider_name, model) en orden, sin duplicados
    consecutivos contra el primary.
    """
    primary_provider = (
        os.environ.get(cfg["provider_env"]) or cfg["default_provider"]
    ).strip().lower()
    primary_model = os.environ.get(cfg["model_env"]) or cfg["default_model"]
    specs: List[Tuple[str, str]] = [(primary_provider, primary_model)]

    for suffix in ("FALLBACK", "FALLBACK2"):
        fb_provider_env = f"SUNNY_{slot}_{suffix}_PROVIDER"
        fb_model_env = f"SUNNY_{slot}_{suffix}_MODEL"
        fb_provider = os.environ.get(fb_provider_env)
        if not fb_provider:
            continue
        fb_provider = fb_provider.strip().lower()
        fb_model = (os.environ.get(fb_model_env) or "").strip()
        if not fb_model:
            log.warning(
                "fallback_missing_model",
                provider_env=fb_provider_env,
                model_env=fb_model_env,
            )
            continue
        if (fb_provider, fb_model) in specs:
            continue
        specs.append((fb_provider, fb_model))

    return specs


def get_provider_for_role(role: BrainRole) -> BrainProvider:
    """Devuelve el provider asociado al rol cognitivo.

    Lee las env vars del rol (``SUNNY_M{1..4}_PROVIDER`` / ``_MODEL``); si no
    están definidas cae a los defaults del rol. Si hay ``_FALLBACK_*`` o
    ``_FALLBACK2_*`` definidas, envuelve en ``FallbackChainProvider`` para
    saltar automáticamente al siguiente provider ante errores transitorios
    (rate-limit, CUDA, conexión, validación).
    """
    if role not in _ROLE_CONFIG:
        raise ValueError(f"BrainRole desconocido: {role!r}")

    cfg = _ROLE_CONFIG[role]
    slot: str = cfg["slot"]
    specs = _read_chain_specs_from_env(slot, cfg)

    chain: List[Tuple[ProviderSpec, BrainProvider]] = []
    for provider_name, model in specs:
        instance = _try_instantiate(provider_name, model)
        if instance is None:
            continue
        chain.append((ProviderSpec(provider=provider_name, model=model), instance))

    if not chain:
        # Ni siquiera el primary se pudo instanciar (típicamente falta API key
        # y no hay fallbacks). Levanta el error original instanciando otra vez.
        primary_provider, primary_model = specs[0]
        return _instantiate_provider(primary_provider, primary_model)

    log.info(
        "brain_chain_selected_for_role",
        role=role.value,
        primary_provider=chain[0][0].provider,
        primary_model=chain[0][0].model,
        chain_size=len(chain),
        chain=[f"{s.provider}/{s.model}" for s, _ in chain],
    )

    if len(chain) == 1:
        return chain[0][1]
    return FallbackChainProvider(chain)
