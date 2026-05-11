from __future__ import annotations

import json
from typing import List, Optional, Tuple

from sunny.brain.factory import BrainRole, get_provider_for_role
from sunny.brain.ollama_client import LLMCallStats
from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import ComprehensionResult
from sunny.core.prompts.loader import load_system_prompt
from sunny.core.session import manager as session

log = get_logger("sunny.core.orchestrator.comprehension")

PHASE_TAG: str = "[FASE: COMPRENSIÓN]"
CONTEXT_TAG: str = "[CONTEXTO PREVIO]"


def build_comprehension_user_prompt(
    user_input: str,
    context: Optional[List[dict]] = None,
) -> str:
    """Construye el prompt de usuario para la fase de comprensión."""
    parts: List[str] = [PHASE_TAG]

    if context:
        parts.append("")
        parts.append(CONTEXT_TAG)
        parts.append(json.dumps(context, ensure_ascii=False, indent=2))

    parts.append("")
    parts.append(f"Usuario: {user_input}")

    return "\n".join(parts)


def comprehend(user_input: str) -> Tuple[ComprehensionResult, LLMCallStats]:
    """Ejecuta la fase de comprensión end-to-end."""
    system_prompt = load_system_prompt("comprehension_v1")
    context = session.get_context()

    user_prompt = build_comprehension_user_prompt(user_input, context)

    log.info(
        "comprehension_start",
        input_length=len(user_input),
        context_turns=len(context),
    )

    result, stats = get_provider_for_role(BrainRole.COMPREHENSION).call_validated(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        schema=ComprehensionResult,
    )

    log.info(
        "comprehension_done",
        intent=result.intent,
        confidence=result.confidence,
        needs_clarification=result.needs_clarification,
        retries_used=stats.retries_used,
        latency_ms=stats.latency_ms,
        tokens_in=stats.tokens_in,
        tokens_out=stats.tokens_out,
    )

    return result, stats
