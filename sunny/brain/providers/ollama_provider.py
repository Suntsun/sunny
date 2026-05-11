from __future__ import annotations

from typing import Tuple, Type, TypeVar

from pydantic import BaseModel

from sunny.brain import ollama_client
from sunny.brain.ollama_client import LLMCallStats
from sunny.brain.providers.base import BrainProvider
from sunny.core.logging.logger import get_logger

log = get_logger("sunny.brain.providers.ollama")

T = TypeVar("T", bound=BaseModel)


class OllamaProvider(BrainProvider):
    """BrainProvider que delega en el cliente Ollama local existente.

    No reimplementa la lógica de retries/validación: reusa
    ``ollama_client.call_llm_validated`` para que los tests existentes que
    mockean ``ollama.Client.chat`` sigan funcionando sin cambios.
    """

    def __init__(self, model: str = ollama_client.DEFAULT_MODEL) -> None:
        self._model = model

    def call_validated(
        self,
        user_prompt: str,
        system_prompt: str,
        schema: Type[T],
        max_retries: int = ollama_client.MAX_RETRIES,
        temperature: float = ollama_client.DEFAULT_TEMPERATURE,
        timeout_sec: int = ollama_client.DEFAULT_TIMEOUT_SEC,
        num_ctx: int = ollama_client.DEFAULT_NUM_CTX,
    ) -> Tuple[T, LLMCallStats]:
        return ollama_client.call_llm_validated(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            schema=schema,
            max_retries=max_retries,
            model=self._model,
            temperature=temperature,
            timeout_sec=timeout_sec,
            num_ctx=num_ctx,
        )

    def call_text(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = 0.5,
        timeout_sec: int = ollama_client.DEFAULT_TIMEOUT_SEC,
        num_ctx: int = ollama_client.DEFAULT_NUM_CTX,
    ) -> Tuple[str, LLMCallStats]:
        return ollama_client.call_llm(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            model=self._model,
            temperature=temperature,
            timeout_sec=timeout_sec,
            json_mode=False,
            num_ctx=num_ctx,
        )

    def health_check(self) -> bool:
        return ollama_client.health_check(model=self._model)
