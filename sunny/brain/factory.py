from __future__ import annotations

import os

from sunny.brain.providers.base import BrainProvider
from sunny.core.logging.logger import get_logger

log = get_logger("sunny.brain.factory")

PROVIDER_ENV: str = "SUNNY_BRAIN_PROVIDER"
DEFAULT_PROVIDER: str = "ollama"
SUPPORTED_PROVIDERS = ("ollama", "groq")


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

    raise ValueError(
        f"{PROVIDER_ENV}='{name}' no reconocido. "
        f"Valores soportados: {', '.join(SUPPORTED_PROVIDERS)}."
    )
