from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple, Type, TypeVar

from pydantic import BaseModel

from sunny.brain.ollama_client import LLMCallStats

T = TypeVar("T", bound=BaseModel)


class BrainProvider(ABC):
    """Interfaz abstracta del cerebro de Sunny.

    Encapsula la llamada al LLM con validación contra schema Pydantic y
    reintentos, de forma que el orquestador (comprehension/planner) sea
    independiente del backend concreto (Ollama local, Groq cloud, ...).
    """

    @abstractmethod
    def call_validated(
        self,
        user_prompt: str,
        system_prompt: str,
        schema: Type[T],
        max_retries: int = 3,
        temperature: float = 0.2,
        timeout_sec: int = 120,
        num_ctx: int = 16384,
    ) -> Tuple[T, LLMCallStats]:
        """Llama al LLM y valida el output contra ``schema``.

        Si la validación falla, reintenta hasta ``max_retries`` veces
        añadiendo al prompt los nombres de los campos requeridos del schema
        como hint de corrección. Devuelve la instancia validada y stats de
        la última llamada (con ``retries_used`` reflejando el coste).

        ``num_ctx`` es respetado por backends locales (Ollama) e ignorado
        por backends cloud (Groq) que no exponen ese parámetro.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Devuelve True si el backend está disponible y operativo."""
        ...
