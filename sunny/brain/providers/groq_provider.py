from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel, ValidationError

from sunny.brain.ollama_client import (
    LLMCallStats,
    LLMConnectionError,
    LLMError,
    LLMTimeoutError,
    LLMValidationError,
)
from sunny.brain.providers.base import BrainProvider
from sunny.core.logging.logger import get_logger

log = get_logger("sunny.brain.providers.groq")

DEFAULT_GROQ_MODEL: str = "llama-3.3-70b-versatile"
GROQ_API_KEY_ENV: str = "GROQ_API_KEY"
GROQ_MODEL_ENV: str = "SUNNY_GROQ_MODEL"

T = TypeVar("T", bound=BaseModel)


def _load_groq_module() -> Any:
    try:
        import groq  # type: ignore
        return groq
    except ImportError as e:
        raise ImportError(
            "El paquete 'groq' no está instalado. Instálalo con "
            "`pip install groq` o `pip install -e .[groq]` para activar el "
            "provider Groq."
        ) from e


class GroqProvider(BrainProvider):
    """BrainProvider que llama a la API de Groq (OpenAI-compatible).

    Usa JSON mode (``response_format={"type": "json_object"}``) y el mismo
    patrón de retries con hint de campos requeridos que ``ollama_client``.
    El parámetro ``num_ctx`` se ignora — la API de Groq no lo expone.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Any = None,
    ) -> None:
        self._model = model or os.environ.get(GROQ_MODEL_ENV, DEFAULT_GROQ_MODEL)

        if client is not None:
            self._client = client
            return

        api_key = api_key or os.environ.get(GROQ_API_KEY_ENV)
        if not api_key:
            raise EnvironmentError(
                f"Variable de entorno {GROQ_API_KEY_ENV} no definida. "
                f"Establécela con tu API key de Groq antes de usar "
                f"SUNNY_BRAIN_PROVIDER=groq."
            )

        groq_module = _load_groq_module()
        self._client = groq_module.Groq(api_key=api_key)

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
        attempt = 0
        last_raw = ""
        last_errors: list = []

        while attempt <= max_retries:
            raw, stats = self._chat_once(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                timeout_sec=timeout_sec,
            )

            last_raw = raw
            cleaned = _strip_code_fences(raw)
            cleaned = _extract_json_object(cleaned)

            try:
                instance = schema.model_validate_json(cleaned)
                stats.retries_used = attempt
                return instance, stats
            except (ValidationError, json.JSONDecodeError) as e:
                last_errors = [str(e)]

                if attempt == max_retries:
                    log.error(
                        "groq_validation_exhausted",
                        error_type=type(e).__name__,
                        error_msg=str(e),
                    )
                    raise LLMValidationError(
                        "Validación fallida tras reintentos (groq)",
                        last_raw=last_raw,
                        last_errors=last_errors,
                    )

                log.warning(
                    "groq_retry",
                    attempt=attempt + 1,
                    error_type=type(e).__name__,
                    error_msg=str(e),
                )

                required_fields = list(schema.model_fields.keys())
                user_prompt = (
                    f"{user_prompt}\n\n[ERROR PREVIO]\n"
                    f"La respuesta anterior falló validación: {str(e)}\n"
                    f"El raw fue: {raw[:500]}\n"
                    f"Campos requeridos por el esquema: {required_fields}\n"
                    f"Reintenta produciendo JSON válido con exactamente esos campos."
                )

            attempt += 1

        raise LLMValidationError("Unexpected failure (groq)", last_raw, last_errors)

    def _chat_once(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float,
        timeout_sec: int,
    ) -> Tuple[str, LLMCallStats]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        t0 = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                timeout=timeout_sec,
            )
        except Exception as e:
            haystack = f"{type(e).__name__.lower()} {str(e).lower()}"
            if "timeout" in haystack:
                raise LLMTimeoutError(str(e))
            if "connect" in haystack or "request" in haystack or "network" in haystack:
                raise LLMConnectionError(str(e))
            raise LLMError(str(e))
        t1 = time.perf_counter()

        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
        tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0

        stats = LLMCallStats(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=int((t1 - t0) * 1000),
            retries_used=0,
        )

        log.info(
            "groq_call",
            model=self._model,
            tokens_in=stats.tokens_in,
            tokens_out=stats.tokens_out,
            latency_ms=stats.latency_ms,
        )

        return content, stats

    def health_check(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception as e:
            log.warning(
                "groq_health_check_failed",
                error_type=type(e).__name__,
                error_msg=str(e),
            )
            return False


def _strip_code_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text.strip())
    return text.strip()


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]
