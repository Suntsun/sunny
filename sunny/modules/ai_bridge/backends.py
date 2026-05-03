from __future__ import annotations

from abc import ABC, abstractmethod


class AIBackend(ABC):
    """Interfaz abstracta para un backend de IA externa."""

    @abstractmethod
    def ask(self, prompt: str) -> str:
        """Envía un prompt al backend y devuelve la respuesta como texto."""
        ...


class StubBackend(AIBackend):
    """
    Backend stub para v1.

    La implementación real queda como tech debt.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def ask(self, prompt: str) -> str:
        raise NotImplementedError(
            f"Backend para '{self.provider}' no implementado en v1. "
            f"Requiere integración con Playwright + selectors específicos "
            f"o UI automation sobre la app desktop oficial."
        )
