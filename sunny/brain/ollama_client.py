from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple, Type, TypeVar

import ollama
from pydantic import BaseModel, ValidationError

from sunny.core.logging.logger import get_logger

log = get_logger("sunny.brain.ollama_client")

# Constantes (exportables)
DEFAULT_MODEL: str = "llama3.1:8b-instruct-q5_K_M"
DEFAULT_TEMPERATURE: float = 0.2
DEFAULT_TIMEOUT_SEC: int = 120
MAX_RETRIES: int = 3
DEFAULT_NUM_CTX: int = 16384
CONTEXT_WARN_RATIO: float = 0.80

T = TypeVar("T", bound=BaseModel)


# Excepciones tipadas
class LLMError(Exception):
    pass


class LLMConnectionError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMValidationError(LLMError):
    """Validación falló tras agotar reintentos."""

    def __init__(self, message: str, last_raw: str, last_errors: list):
        super().__init__(message)
        self.last_raw = last_raw
        self.last_errors = last_errors


@dataclass
class LLMCallStats:
    tokens_in: int
    tokens_out: int
    latency_ms: int
    retries_used: int


def call_llm(
    user_prompt: str,
    system_prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    json_mode: bool = True,
) -> Tuple[str, LLMCallStats]:
    """Realiza una llamada al LLM vía Ollama."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    client = ollama.Client(timeout=timeout_sec)

    kwargs = {
        "model": model,
        "messages": messages,
        "options": {"temperature": temperature, "num_predict": 2048, "num_ctx": DEFAULT_NUM_CTX},
    }
    if json_mode:
        kwargs["format"] = "json"

    t0 = time.perf_counter()
    try:
        response = client.chat(**kwargs)
    except Exception as e:
        name = type(e).__name__.lower()
        msg = str(e).lower()
        haystack = f"{name} {msg}"
        if "timeout" in haystack:
            raise LLMTimeoutError(str(e))
        if "connect" in haystack or "request" in haystack:
            raise LLMConnectionError(str(e))
        raise LLMError(str(e))
    t1 = time.perf_counter()

    content = response["message"]["content"]

    stats = LLMCallStats(
        tokens_in=response.get("prompt_eval_count", 0),
        tokens_out=response.get("eval_count", 0),
        latency_ms=int((t1 - t0) * 1000),
        retries_used=0,
    )

    log.info(
        "llm_call",
        model=model,
        tokens_in=stats.tokens_in,
        tokens_out=stats.tokens_out,
        latency_ms=stats.latency_ms,
        json_mode=json_mode,
    )

    if stats.tokens_in >= int(DEFAULT_NUM_CTX * CONTEXT_WARN_RATIO):
        log.warning(
            "context_limit_approaching",
            tokens_in=stats.tokens_in,
            num_ctx=DEFAULT_NUM_CTX,
            usage_pct=round(stats.tokens_in / DEFAULT_NUM_CTX * 100, 1),
        )

    return content, stats


def call_llm_validated(
    user_prompt: str,
    system_prompt: str,
    schema: Type[T],
    max_retries: int = MAX_RETRIES,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> Tuple[T, LLMCallStats]:
    """Llama al LLM y valida contra un schema Pydantic."""
    attempt = 0
    last_raw = ""
    last_errors: list = []

    while attempt <= max_retries:
        raw, stats = call_llm(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            timeout_sec=timeout_sec,
            json_mode=True,
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
                    "llm_validation_exhausted",
                    error_type=type(e).__name__,
                    error_msg=str(e),
                )
                raise LLMValidationError(
                    "Validación fallida tras reintentos",
                    last_raw=last_raw,
                    last_errors=last_errors,
                )

            log.warning(
                "llm_retry",
                attempt=attempt + 1,
                error_type=type(e).__name__,
                error_msg=str(e),
            )

            user_prompt = (
                f"{user_prompt}\n\n[ERROR PREVIO]\n"
                f"La respuesta anterior falló validación: {str(e)}\n"
                f"El raw fue: {raw[:500]}\n"
                f"Reintenta produciendo JSON válido conforme al esquema."
            )

        attempt += 1

    raise LLMValidationError("Unexpected failure", last_raw, last_errors)


def health_check(model: str = DEFAULT_MODEL) -> bool:
    """Verifica si el modelo está disponible."""
    try:
        resp = ollama.list()
        text = str(resp)
        return model in text
    except Exception as e:
        log.warning("health_check_failed", error_type=type(e).__name__, error_msg=str(e))
        return False


def _strip_code_fences(text: str) -> str:
    """Elimina code fences markdown."""
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text.strip())
    return text.strip()


def _extract_json_object(text: str) -> str:
    """Extrae el primer objeto JSON del texto."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]
