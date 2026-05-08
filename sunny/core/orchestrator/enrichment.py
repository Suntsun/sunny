from __future__ import annotations

import os
import time
from typing import Optional

from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import ComprehensionResult

log = get_logger("sunny.core.orchestrator.enrichment")

_GROQ_API_KEY_ENV = "GROQ_API_KEY"
_GROQ_MODEL_ENV = "SUNNY_GROQ_MODEL"
_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

ENRICHMENT_SYSTEM_PROMPT = (
    "Eres un experto en interfaces de escritorio Windows 11. "
    "Cuando recibas una tarea sobre una aplicación, responde con 3-5 pasos de UI concretos "
    "y accionables. Solo pasos de interacción: clics, texto a escribir, atajos de teclado. "
    "Sin explicaciones adicionales. Si hay varias formas, elige la más directa. "
    "Máximo 80 palabras."
)


def enrich(comprehension: ComprehensionResult, user_input: str) -> Optional[str]:
    """Consulta Groq para obtener guía de UI cuando intent=agent_loop.

    Devuelve texto con pasos de UI o None si Groq no está disponible o falla.
    El enriquecimiento es siempre opcional — nunca bloquea el pipeline.
    """
    if comprehension.intent != "agent_loop":
        return None

    api_key = os.environ.get(_GROQ_API_KEY_ENV)
    if not api_key:
        log.debug(event="enrichment_skipped", reason="GROQ_API_KEY not set")
        return None

    try:
        import groq as _groq  # lazy import — solo si se usa

        model = os.environ.get(_GROQ_MODEL_ENV, _DEFAULT_GROQ_MODEL)
        client = _groq.Groq(api_key=api_key)

        user_prompt = (
            f"Tarea: {comprehension.comprehension}\n\n"
            "¿Cuáles son los pasos exactos de UI para completar esta tarea en Windows 11?"
        )

        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=200,
            timeout=15,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        guidance = (response.choices[0].message.content or "").strip()
        if not guidance:
            return None

        usage = getattr(response, "usage", None)
        log.info(
            event="enrichment_done",
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "prompt_tokens", 0) if usage else 0,
            tokens_out=getattr(usage, "completion_tokens", 0) if usage else 0,
            guidance_length=len(guidance),
        )
        return guidance

    except Exception as e:
        log.warning(
            event="enrichment_failed",
            error_type=type(e).__name__,
            error_msg=str(e),
        )
        return None
