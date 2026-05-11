from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel

from sunny.brain.ollama_client import (
    LLMCallStats,
    LLMConnectionError,
    LLMError,
    LLMTimeoutError,
    LLMValidationError,
)
from sunny.brain.providers.base import BrainProvider
from sunny.core.logging.logger import get_logger

log = get_logger("sunny.brain.fallback")
T = TypeVar("T", bound=BaseModel)


# Substrings (en minúscula) que marcan errores transitorios del backend:
# rate-limit, capacidad, contexto excedido, CUDA/GPU, modelo caído.
# Si el haystack (tipo de excepción + mensaje) contiene alguno, saltamos
# al siguiente provider de la cadena en lugar de propagar.
_TRANSIENT_SUBSTRINGS: Tuple[str, ...] = (
    "rate_limit", "rate limit", "tokens per minute", "tpm", "rpm",
    "request too large", "context_length", "context length", "context window",
    "429", "413",
    "model_not_found", "model not found", "not available",
    "cuda", "out of memory", "oom",
    "shared object initialization",
    "service_unavailable", "service unavailable", "503", "502",
    "overloaded", "capacity",
)


@dataclass(frozen=True)
class ProviderSpec:
    """Identificación legible del provider/modelo para logging."""
    provider: str
    model: str


def is_transient_error(exc: BaseException) -> bool:
    """Decide si un error justifica saltar al siguiente provider de la cadena.

    Transitorio = problema operativo del backend (rate-limit, capacidad,
    CUDA, conexión, timeout) que no se va a resolver reintentando con el
    mismo modelo. Validación tipada también cuenta: si un modelo es
    estructuralmente incapaz de respetar el schema, probablemente otro sí.
    """
    if isinstance(exc, (LLMConnectionError, LLMTimeoutError, LLMValidationError)):
        return True
    if isinstance(exc, LLMError):
        haystack = f"{type(exc).__name__.lower()} {str(exc).lower()}"
        return any(s in haystack for s in _TRANSIENT_SUBSTRINGS)
    return False


class FallbackChainProvider(BrainProvider):
    """BrainProvider que prueba una cadena de providers en orden.

    Ante errores transitorios (rate-limit/conexión/CUDA/validación), salta
    al siguiente. Errores no transitorios (config, API key, schema corrupto)
    se propagan inmediatamente sin agotar la cadena. Si todos fallan,
    propaga el último error encontrado.
    """

    def __init__(
        self,
        chain: List[Tuple[ProviderSpec, BrainProvider]],
    ) -> None:
        if not chain:
            raise ValueError("FallbackChainProvider requiere al menos un provider")
        self._chain = chain

    @property
    def chain_specs(self) -> List[ProviderSpec]:
        return [spec for spec, _ in self._chain]

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
        last_exc: Optional[BaseException] = None

        for idx, (spec, provider) in enumerate(self._chain):
            log.info(
                "fallback_attempt",
                position=idx,
                provider=spec.provider,
                model=spec.model,
                chain_size=len(self._chain),
            )
            try:
                return provider.call_validated(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    schema=schema,
                    max_retries=max_retries,
                    temperature=temperature,
                    timeout_sec=timeout_sec,
                    num_ctx=num_ctx,
                )
            except Exception as exc:
                if not is_transient_error(exc):
                    raise
                last_exc = exc
                is_last = idx == len(self._chain) - 1
                log.warning(
                    "fallback_exhausted" if is_last else "fallback_triggered",
                    failed_provider=spec.provider,
                    failed_model=spec.model,
                    error_type=type(exc).__name__,
                    error_msg=str(exc)[:200],
                    position=idx,
                    next_position=None if is_last else idx + 1,
                )

        assert last_exc is not None
        raise last_exc

    def call_text(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = 0.5,
        timeout_sec: int = 120,
        num_ctx: int = 16384,
    ) -> Tuple[str, LLMCallStats]:
        last_exc: Optional[BaseException] = None

        for idx, (spec, provider) in enumerate(self._chain):
            log.info(
                "fallback_attempt_text",
                position=idx,
                provider=spec.provider,
                model=spec.model,
                chain_size=len(self._chain),
            )
            try:
                return provider.call_text(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    timeout_sec=timeout_sec,
                    num_ctx=num_ctx,
                )
            except Exception as exc:
                if not is_transient_error(exc):
                    raise
                last_exc = exc
                is_last = idx == len(self._chain) - 1
                log.warning(
                    "fallback_exhausted_text" if is_last else "fallback_triggered_text",
                    failed_provider=spec.provider,
                    failed_model=spec.model,
                    error_type=type(exc).__name__,
                    error_msg=str(exc)[:200],
                    position=idx,
                    next_position=None if is_last else idx + 1,
                )

        assert last_exc is not None
        raise last_exc

    def health_check(self) -> bool:
        return any(p.health_check() for _, p in self._chain)
