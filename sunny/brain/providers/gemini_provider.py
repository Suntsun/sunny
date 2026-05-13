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

log = get_logger("sunny.brain.providers.gemini")

DEFAULT_GEMINI_MODEL: str = "gemini-2.5-flash"
GEMINI_API_KEY_ENV: str = "GEMINI_API_KEY"
GEMINI_MODEL_ENV: str = "SUNNY_GEMINI_MODEL"
GEMINI_THINKING_ENV: str = "SUNNY_GEMINI_THINKING"
DEFAULT_MAX_TOKENS: int = 16000

T = TypeVar("T", bound=BaseModel)


def _load_genai_module() -> Any:
    try:
        from google import genai  # type: ignore
        return genai
    except ImportError as e:
        raise ImportError(
            "El paquete 'google-genai' no está instalado. Instálalo con "
            "`pip install google-genai` o `pip install -e .[gemini]` para activar "
            "el provider Gemini."
        ) from e


class GeminiProvider(BrainProvider):
    """BrainProvider que llama a la API de Google Gemini.

    Usa el SDK nuevo ``google-genai`` (no el legacy ``google-generativeai``)
    con ``client.models.generate_content()``. Soporta thinking dinámico
    (``thinking_budget=-1``), configurable vía ``SUNNY_GEMINI_THINKING=off``.
    El JSON mode se enforza por prompt engineering (consistente con
    ``AnthropicProvider``). El parámetro ``num_ctx`` se ignora — Gemini no lo
    expone. ``timeout_sec`` también se ignora a nivel de llamada — el SDK lo
    configura solo a nivel de cliente.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Any = None,
        thinking: Optional[bool] = None,
    ) -> None:
        self._model = model or os.environ.get(GEMINI_MODEL_ENV, DEFAULT_GEMINI_MODEL)
        self._thinking_enabled = _resolve_thinking_flag(thinking)

        if client is not None:
            self._client = client
            return

        api_key = api_key or os.environ.get(GEMINI_API_KEY_ENV)
        if not api_key:
            raise EnvironmentError(
                f"Variable de entorno {GEMINI_API_KEY_ENV} no definida. "
                f"Establécela con tu API key de Google AI Studio antes de usar el "
                f"provider gemini."
            )

        genai_module = _load_genai_module()
        self._client = genai_module.Client(api_key=api_key)

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

        json_system = (
            f"{system_prompt}\n\nIMPORTANTE: Responde EXCLUSIVAMENTE con un objeto "
            f"JSON válido que cumpla el esquema solicitado. No incluyas texto antes "
            f"o después del JSON, ni envoltorios markdown."
        )

        while attempt <= max_retries:
            raw, stats = self._chat_once(
                user_prompt=user_prompt,
                system_prompt=json_system,
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
                        "gemini_validation_exhausted",
                        error_type=type(e).__name__,
                        error_msg=str(e),
                    )
                    raise LLMValidationError(
                        "Validación fallida tras reintentos (gemini)",
                        last_raw=last_raw,
                        last_errors=last_errors,
                    )

                log.warning(
                    "gemini_retry",
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

        raise LLMValidationError("Unexpected failure (gemini)", last_raw, last_errors)

    def call_text(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = 0.5,
        timeout_sec: int = 120,
        num_ctx: int = 16384,
    ) -> Tuple[str, LLMCallStats]:
        return self._chat_once(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            timeout_sec=timeout_sec,
        )

    def _chat_once(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float,
        timeout_sec: int,
    ) -> Tuple[str, LLMCallStats]:
        # google-genai admite dict como ``config`` y lo normaliza a
        # GenerateContentConfig internamente. Evita importar ``types`` aquí
        # para no acoplar el módulo al SDK opcional.
        config: dict = {
            "system_instruction": system_prompt,
            "max_output_tokens": DEFAULT_MAX_TOKENS,
        }

        if self._thinking_enabled:
            # thinking_budget=-1 → dynamic thinking (el modelo decide).
            # thinking+temperature pueden coexistir, pero por consistencia con
            # AnthropicProvider omitimos temperature cuando thinking está on.
            config["thinking_config"] = {"thinking_budget": -1}
        else:
            # En modelos como gemini-2.5-flash, thinking_budget=0 lo desactiva.
            config["thinking_config"] = {"thinking_budget": 0}
            config["temperature"] = temperature

        kwargs: dict = {
            "model": self._model,
            "contents": user_prompt,
            "config": config,
        }

        t0 = time.perf_counter()
        try:
            response = self._client.models.generate_content(**kwargs)
        except Exception as e:
            mapped = _map_gemini_error(e)
            raise mapped
        t1 = time.perf_counter()

        content = _extract_text_content(response)
        usage = getattr(response, "usage_metadata", None)
        tokens_in = getattr(usage, "prompt_token_count", 0) if usage else 0
        tokens_out = getattr(usage, "candidates_token_count", 0) if usage else 0

        stats = LLMCallStats(
            tokens_in=tokens_in or 0,
            tokens_out=tokens_out or 0,
            latency_ms=int((t1 - t0) * 1000),
            retries_used=0,
        )

        log.info(
            "gemini_call",
            model=self._model,
            tokens_in=stats.tokens_in,
            tokens_out=stats.tokens_out,
            latency_ms=stats.latency_ms,
            thinking=self._thinking_enabled,
        )

        return content, stats

    def health_check(self) -> bool:
        try:
            # Consume el pager para forzar la llamada HTTP.
            list(self._client.models.list())
            return True
        except Exception as e:
            log.warning(
                "gemini_health_check_failed",
                error_type=type(e).__name__,
                error_msg=str(e),
            )
            return False


def _resolve_thinking_flag(explicit: Optional[bool]) -> bool:
    """Decide si activar thinking dinámico.

    Orden de precedencia:
    1. Argumento explícito en el constructor (si no es None)
    2. Variable de entorno SUNNY_GEMINI_THINKING (off/false/0/no → False; resto → True)
    3. Default: True
    """
    if explicit is not None:
        return explicit
    raw = os.environ.get(GEMINI_THINKING_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in ("off", "false", "0", "no", "")


def _extract_text_content(response: Any) -> str:
    """Extrae texto del response de Gemini.

    Prefiere el accessor ``response.text`` (que concatena las partes type=text
    automáticamente). Si no está disponible (mock antiguo o response con
    estructura distinta) cae a iterar ``candidates[*].content.parts``,
    ignorando partes marcadas como ``thought``.
    """
    text = getattr(response, "text", None)
    if text:
        return text

    pieces: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            text_piece = getattr(part, "text", None)
            if text_piece:
                pieces.append(text_piece)
    return "".join(pieces)


def _map_gemini_error(e: Exception) -> Exception:
    """Mapea excepciones del SDK google-genai a las excepciones tipadas del proyecto.

    Detecta por nombre de clase y mensaje para no acoplar al SDK (permite
    instalación opcional y mocks en tests sin importar el SDK real).
    """
    cls_name = type(e).__name__.lower()
    msg_lower = str(e).lower()
    haystack = f"{cls_name} {msg_lower}"

    if "timeout" in haystack or "deadline" in haystack:
        return LLMTimeoutError(str(e))
    if (
        "ratelimit" in cls_name
        or "rate_limit" in msg_lower
        or "resource_exhausted" in msg_lower
        or "429" in msg_lower
    ):
        # Rate limits son transitorios — se mapean a conexión para que el
        # FallbackChainProvider los considere retryables.
        return LLMConnectionError(str(e))
    if (
        "connection" in haystack
        or "connect" in haystack
        or "network" in haystack
        or "unavailable" in haystack
    ):
        return LLMConnectionError(str(e))
    if "servererror" in cls_name or "5" in str(getattr(e, "code", "")):
        # 5xx → mapeo conservador a LLMError (no necesariamente retryable;
        # el SDK ya hace retries internos para 5xx idempotentes).
        return LLMError(str(e))
    return LLMError(str(e))


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
