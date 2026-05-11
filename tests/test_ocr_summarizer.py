import pytest

from sunny.brain.ollama_client import LLMCallStats
from sunny.core.execution import ocr_summarizer
from sunny.core.execution.ocr_summarizer import (
    ScreenSummary,
    summarize_screen_state,
)


class _FakeProvider:
    def __init__(self, summary=None, exc=None):
        self._summary = summary
        self._exc = exc
        self.calls = []

    def call_validated(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        stats = LLMCallStats(tokens_in=1, tokens_out=1, latency_ms=1, retries_used=0)
        return self._summary, stats


def _patch_provider(monkeypatch, fake):
    monkeypatch.setattr(
        "sunny.core.execution.ocr_summarizer.get_provider_for_role",
        lambda role: fake,
    )
    monkeypatch.setattr(
        "sunny.core.execution.ocr_summarizer.load_system_prompt",
        lambda version: "PROMPT_OK",
    )


def _summary(**overrides) -> ScreenSummary:
    base = dict(
        app="Discord",
        view="lista de DMs",
        visible_text=["aafturo", "Inicio", "Búsqueda"],
        interactive=["aafturo", "campo de mensaje"],
        target_visible=True,
        summary="DM con aafturo visible; click en su nombre.",
    )
    base.update(overrides)
    return ScreenSummary(**base)


def test_summarize_screen_state_returns_formatted_string(monkeypatch):
    _patch_provider(monkeypatch, _FakeProvider(summary=_summary()))
    out = summarize_screen_state("ruido OCR", "escribir a aafturo")

    assert "[PANTALLA]" in out
    assert "App: Discord" in out
    assert "Vista: lista de DMs" in out
    assert "aafturo" in out
    assert "Objetivo visible: SÍ" in out
    assert "DM con aafturo visible" in out


def test_summarize_screen_state_target_visible_false_renders_no(monkeypatch):
    _patch_provider(monkeypatch, _FakeProvider(summary=_summary(target_visible=False)))
    out = summarize_screen_state("x", "g")
    assert "Objetivo visible: NO" in out


def test_summarize_screen_state_fails_gracefully_on_exception(monkeypatch):
    _patch_provider(monkeypatch, _FakeProvider(exc=RuntimeError("boom")))
    out = summarize_screen_state("OCR_CRUDO_ORIGINAL", "objetivo")
    assert out == "OCR_CRUDO_ORIGINAL"


def test_summarize_screen_state_empty_ocr_returns_empty_without_provider_call(monkeypatch):
    fake = _FakeProvider(summary=_summary())
    _patch_provider(monkeypatch, fake)
    out = summarize_screen_state("", "objetivo")
    assert out == ""
    assert fake.calls == []


def test_summarize_screen_state_passes_goal_and_ocr_to_provider(monkeypatch):
    fake = _FakeProvider(summary=_summary())
    _patch_provider(monkeypatch, fake)
    summarize_screen_state("texto OCR ruidoso", "escribir a aafturo")

    user_prompt = fake.calls[0]["user_prompt"]
    assert "OBJETIVO:" in user_prompt
    assert "escribir a aafturo" in user_prompt
    assert "OCR CRUDO:" in user_prompt
    assert "texto OCR ruidoso" in user_prompt
    assert fake.calls[0]["schema"] is ScreenSummary


def test_summarize_screen_state_rejects_wrong_type_and_returns_raw(monkeypatch):
    """Si el provider devuelve algo que no es ScreenSummary, fail-safe."""
    class _Bogus:
        pass

    _patch_provider(monkeypatch, _FakeProvider(summary=_Bogus()))
    out = summarize_screen_state("RAW_OCR", "g")
    assert out == "RAW_OCR"


def test_screen_summary_defaults_are_empty():
    s = ScreenSummary()
    assert s.app == ""
    assert s.view == ""
    assert s.visible_text == []
    assert s.interactive == []
    assert s.target_visible is False
    assert s.summary == ""


def test_summarize_screen_state_handles_long_visible_text_list(monkeypatch):
    long_list = [f"item{i}" for i in range(10)]
    _patch_provider(monkeypatch, _FakeProvider(summary=_summary(visible_text=long_list)))
    out = summarize_screen_state("x", "g")
    for it in long_list:
        assert it in out


# --- Normalizador: el LLM devuelve dicts en vez de strings ----------------

def test_screen_summary_normalizes_dicts_to_strings():
    """qwen2.5:3b devuelve interactive como objetos. El validator debe
    convertirlos a strings 'tipo: texto' en vez de fallar."""
    raw = {
        "app": "Discord",
        "view": "general",
        "visible_text": [{"type": "header", "text": "Servidor X"}, "linea suelta"],
        "interactive": [
            {"type": "clickable", "text": "General"},
            {"type": "editable", "text": "holaaa"},
            "campo de búsqueda",
        ],
        "target_visible": True,
        "summary": "ok",
    }
    s = ScreenSummary.model_validate(raw)
    assert s.interactive == [
        "clickable: General",
        "editable: holaaa",
        "campo de búsqueda",
    ]
    assert "header: Servidor X" in s.visible_text
    assert "linea suelta" in s.visible_text


def test_screen_summary_handles_object_with_label_or_name():
    raw = {
        "interactive": [
            {"label": "Aceptar"},
            {"name": "input-chat", "type": "input"},
            {"value": "raw_value"},
        ],
    }
    s = ScreenSummary.model_validate(raw)
    assert s.interactive == ["Aceptar", "input: input-chat", "raw_value"]


def test_screen_summary_uses_str_fallback_for_unknown_shapes():
    raw = {"interactive": [{"weird": "thing"}, 42]}
    s = ScreenSummary.model_validate(raw)
    # Sin text/label/name/value: fallback a str(dict). 42 → "42".
    assert any("weird" in it for it in s.interactive)
    assert "42" in s.interactive
