from __future__ import annotations

import json
from typing import List, Optional, Tuple

from sunny.brain.factory import BrainRole, get_provider_for_role
from sunny.brain.ollama_client import LLMCallStats
from sunny.core.logging.logger import get_logger
from sunny.core.prompts.loader import load_system_prompt
from sunny.core.session import manager as session

log = get_logger("sunny.core.orchestrator.conversation")

CONTEXT_TAG: str = "[CONTEXTO PREVIO]"
CONVERSATION_TEMPERATURE: float = 0.5


def build_conversation_user_prompt(
    user_input: str,
    context: Optional[List[dict]] = None,
) -> str:
    """Construye el prompt de usuario para modo conversacional."""
    parts: List[str] = []

    if context:
        parts.append(CONTEXT_TAG)
        parts.append(json.dumps(context, indent=2, ensure_ascii=False))
        parts.append("")

    parts.append(f"Usuario: {user_input}")
    return "\n".join(parts)


def converse(user_input: str) -> Tuple[str, LLMCallStats]:
    """Orquesta la conversación con el LLM."""
    system_prompt = load_system_prompt("conversation_v1")
    context = session.get_context()
    user_prompt = build_conversation_user_prompt(user_input, context)

    log.info(
        event="conversation_start",
        input_length=len(user_input),
        context_turns=len(context),
    )

    provider = get_provider_for_role(BrainRole.COMPREHENSION)
    response, stats = provider.call_text(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=CONVERSATION_TEMPERATURE,
    )

    log.info(
        event="conversation_done",
        response_length=len(response),
        latency_ms=stats.latency_ms,
        tokens_in=stats.tokens_in,
        tokens_out=stats.tokens_out,
    )

    return response, stats
