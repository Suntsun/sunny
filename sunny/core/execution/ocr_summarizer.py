from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, Field, field_validator

from sunny.brain.factory import BrainRole, get_provider_for_role
from sunny.core.logging.logger import get_logger
from sunny.core.prompts.loader import load_system_prompt

log = get_logger("sunny.core.execution.ocr_summarizer")


def _coerce_to_string(item: Any) -> str:
    """Convierte un item heterogéneo a la representación string canónica.

    Los modelos pequeños tienden a devolver objetos {type, text} en vez de
    strings aunque el prompt los pida. En vez de fallar validación, los
    normalizamos: '{type}: {text}' si vienen los dos campos, o el primer
    campo string disponible, o str(item) como último recurso.
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        text = (
            item.get("text")
            or item.get("label")
            or item.get("name")
            or item.get("value")
            or item.get("content")
        )
        kind = item.get("type") or item.get("role")
        if text and kind:
            return f"{kind}: {text}"
        if text:
            return str(text)
        return str(item)
    return str(item)


class ScreenSummary(BaseModel):
    """Resumen estructurado del estado visual de la pantalla."""

    app: str = ""
    view: str = ""
    visible_text: List[Any] = Field(default_factory=list)
    interactive: List[Any] = Field(default_factory=list)
    target_visible: bool = False
    summary: str = ""

    @field_validator("visible_text", "interactive", mode="after")
    @classmethod
    def _normalize_string_list(cls, value: list) -> list:
        return [_coerce_to_string(item) for item in value]


def _format_summary(summary: ScreenSummary) -> str:
    visible = ", ".join(summary.visible_text) if summary.visible_text else "(nada)"
    interactive = ", ".join(summary.interactive) if summary.interactive else "(nada)"
    target = "SÍ" if summary.target_visible else "NO"
    return (
        "[PANTALLA]\n"
        f"App: {summary.app or '(desconocida)'} | Vista: {summary.view or '(desconocida)'}\n"
        f"Texto visible: {visible}\n"
        f"Interactivos: {interactive}\n"
        f"Objetivo visible: {target}\n"
        f"Estado: {summary.summary or '(sin estado)'}"
    )


def summarize_screen_state(raw_ocr: str, goal: str) -> str:
    """Limpia y estructura el OCR crudo en una descripción accionable.

    Si m4 falla por cualquier motivo (provider no disponible, timeout,
    validación) devuelve ``raw_ocr`` sin modificar para no bloquear el
    pipeline. El agente visual seguirá funcionando con OCR crudo en el peor
    caso, igual que antes de esta capa.
    """
    if not raw_ocr:
        return raw_ocr

    try:
        provider = get_provider_for_role(BrainRole.OCR_SUMMARIZER)
        system_prompt = load_system_prompt("ocr_summarizer_v2")
        user_prompt = (
            f"OBJETIVO:\n{goal}\n\n"
            f"OCR CRUDO:\n{raw_ocr}\n\n"
            "Devuelve únicamente el JSON con los campos exactos del esquema."
        )
        summary, _stats = provider.call_validated(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            schema=ScreenSummary,
            max_retries=1,
        )
        if not isinstance(summary, ScreenSummary):
            raise TypeError(
                f"OCR summarizer devolvió tipo inesperado: {type(summary).__name__}"
            )
        log.info(
            "ocr_summarizer_done",
            app=summary.app,
            view=summary.view,
            target_visible=summary.target_visible,
            visible_count=len(summary.visible_text),
        )
        return _format_summary(summary)
    except Exception as e:
        log.warning(
            "ocr_summarizer_failed",
            error_type=type(e).__name__,
            error_msg=str(e),
        )
        return raw_ocr
