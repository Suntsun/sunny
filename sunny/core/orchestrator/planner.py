from __future__ import annotations

import json
from typing import List, Optional, Tuple

from sunny.brain.ollama_client import call_llm_validated, LLMCallStats
from sunny.core.logging.logger import get_logger
from sunny.core.models.plan import ComprehensionResult, PlanV2
from sunny.core.prompts.loader import load_system_prompt
from sunny.core.session import manager as session

log = get_logger("sunny.core.orchestrator.planner")

PHASE_TAG: str = "[FASE: PLANIFICACIÓN]"
CONTEXT_TAG: str = "[CONTEXTO PREVIO]"
COMPREHENSION_TAG: str = "[COMPRENSIÓN PREVIA]"


def build_planning_user_prompt(
    user_input: str,
    comprehension: ComprehensionResult,
    context: Optional[List[dict]] = None,
) -> str:
    """Construye el prompt de usuario para la fase de planificación."""
    parts: List[str] = [PHASE_TAG]

    if context:
        parts.append("")
        parts.append(CONTEXT_TAG)
        parts.append(json.dumps(context, indent=2, ensure_ascii=False))

    parts.append("")
    parts.append(COMPREHENSION_TAG)
    parts.append(json.dumps(comprehension.model_dump(), indent=2, ensure_ascii=False))

    parts.append("")
    parts.append(f"Usuario: {user_input}")

    return "\n".join(parts)


def plan(
    user_input: str,
    comprehension: ComprehensionResult,
) -> Tuple[PlanV2, LLMCallStats]:
    """Orquesta la fase de planificación."""
    if comprehension.intent == "conversation":
        plan_obj = PlanV2(
            intent="conversation",
            confidence=comprehension.confidence,
            steps=[],
        )
        stats = LLMCallStats(tokens_in=0, tokens_out=0, latency_ms=0, retries_used=0)
        log.info(event="planning_short_circuit", intent="conversation")
        return plan_obj, stats

    system_prompt = load_system_prompt("v2")
    context = session.get_context()
    user_prompt = build_planning_user_prompt(user_input, comprehension, context)

    log.info(
        event="planning_start",
        intent=comprehension.intent,
        input_length=len(user_input),
        context_turns=len(context),
    )

    result, stats = call_llm_validated(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        schema=PlanV2,
    )

    log.info(
        event="planning_done",
        intent=result.intent,
        confidence=result.confidence,
        steps_count=len(result.steps),
        requires_confirmation=result.requires_confirmation,
        needs_clarification=result.needs_clarification,
        retries_used=stats.retries_used,
        latency_ms=stats.latency_ms,
        tokens_in=stats.tokens_in,
        tokens_out=stats.tokens_out,
    )

    return result, stats
