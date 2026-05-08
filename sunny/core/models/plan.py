from __future__ import annotations

import re
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

IntentType = Literal[
    "os_control",
    "files",
    "vision",
    "gui",
    "ai_bridge",
    "conversation",
    "agent_loop",
]


_STEP_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class Step(BaseModel):
    """Representa un paso ejecutable dentro de un plan."""

    step_id: str
    plugin: str
    action: str
    params: Dict[str, Any]
    timeout_sec: int = 30
    continue_on_error: bool = False
    depends_on: List[str] = Field(default_factory=list)

    @field_validator("step_id")
    @classmethod
    def validate_step_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("step_id no puede estar vacío")
        if not _STEP_ID_PATTERN.match(v):
            raise ValueError("step_id contiene caracteres inválidos")
        return v

    @field_validator("timeout_sec")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if not (1 <= v <= 600):
            raise ValueError("timeout_sec debe estar entre 1 y 600")
        return v


class PlanV2(BaseModel):
    """Plan ejecutable generado por el LLM."""

    intent: IntentType
    confidence: float
    needs_clarification: bool = False
    requires_confirmation: bool = False
    steps: List[Step] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence debe estar entre 0.0 y 1.0")
        return v

    @model_validator(mode="after")
    def validate_plan(self) -> "PlanV2":
        if self.intent == "conversation":
            if self.steps:
                raise ValueError("intent=conversation requiere steps vacío")
        else:
            if not self.needs_clarification and len(self.steps) == 0:
                raise ValueError(
                    "steps debe contener al menos un elemento cuando no hay needs_clarification"
                )

        step_ids = [s.step_id for s in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("step_id duplicado en steps")

        step_id_set = set(step_ids)

        for step in self.steps:
            for dep in step.depends_on:
                if dep == step.step_id:
                    raise ValueError(
                        f"step_id '{step.step_id}' no puede depender de sí mismo"
                    )
                if dep not in step_id_set:
                    raise ValueError(
                        f"depends_on referencia step_id inexistente: '{dep}'"
                    )

        return self


class ComprehensionResult(BaseModel):
    """Resultado de la fase de comprensión del LLM."""

    comprehension: str
    intent: IntentType
    assumptions: List[str] = Field(default_factory=list)
    confidence: float
    needs_clarification: bool = False

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence debe estar entre 0.0 y 1.0")
        return v
