"""Tests para acciones reactivas de vision: wait_for_screen_text y get_screen_state."""
from unittest.mock import MagicMock

import pytest

from sunny.modules.vision import VisionPlugin


@pytest.fixture
def plugin():
    return VisionPlugin()


def _fake_mss():
    sct = MagicMock()
    sct.monitors = [
        {"left": 0, "top": 0, "width": 3840, "height": 1080},
        {"left": 0, "top": 0, "width": 1920, "height": 1080},
    ]
    grab = MagicMock()
    grab.size = (1920, 1080)
    grab.bgra = b"\x00" * (1920 * 1080 * 4)
    sct.grab.return_value = grab
    ctx = MagicMock()
    ctx.__enter__.return_value = sct
    ctx.__exit__.return_value = False
    return ctx, sct


def _patch_screen(monkeypatch, tmp_path):
    import sunny.modules.vision as v
    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path)
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)
    img = MagicMock()
    img.width, img.height = 1920, 1080
    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: img)
    monkeypatch.setattr(v.Image, "open", lambda path: img)


def _ocr_with(words, conf=85, top=100):
    return {
        "text": list(words),
        "conf": [str(conf)] * len(words),
        "top": [top] * len(words),
        "left": [10 * i for i in range(len(words))],
        "width": [40] * len(words),
        "height": [20] * len(words),
    }


def test_get_screen_state_returns_spatial_map_and_path(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v
    _patch_screen(monkeypatch, tmp_path)
    monkeypatch.setattr(
        v.pytesseract, "image_to_data",
        lambda im, lang, output_type: _ocr_with(["Hola", "Mundo"]),
    )
    r = plugin.execute("get_screen_state", {"region": None}, {})
    assert r.success
    assert "screen_text" in r.data
    assert r.data["screenshot_path"].endswith(".png")


def test_get_screen_state_latency_ms_present(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v
    _patch_screen(monkeypatch, tmp_path)
    monkeypatch.setattr(
        v.pytesseract, "image_to_data",
        lambda im, lang, output_type: _ocr_with(["X"]),
    )
    r = plugin.execute("get_screen_state", {}, {})
    assert r.success
    assert "latency_ms" in r.data
    assert isinstance(r.data["latency_ms"], int)


def test_get_screen_state_registered_in_actions(plugin):
    assert "get_screen_state" in plugin._actions
    assert "wait_for_screen_text" in plugin._actions


class _Stats:
    tokens_in = 1
    tokens_out = 1
    latency_ms = 1
    retries_used = 0


def test_describe_screen_raw_true_skips_llm(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v
    _patch_screen(monkeypatch, tmp_path)
    monkeypatch.setattr(v.pytesseract, "image_to_data",
                        lambda im, lang, output_type: _ocr_with(["File", "Edit"]))

    def boom(**kw):
        raise AssertionError("LLM no debe ser llamado en raw=True")
    monkeypatch.setattr("sunny.brain.ollama_client.call_llm", boom)
    r = plugin.execute("describe_screen", {"raw": True}, {})
    assert r.success and "screen_text" in r.data and "description" not in r.data


def test_describe_screen_raw_false_calls_llm_as_before(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v
    _patch_screen(monkeypatch, tmp_path)
    monkeypatch.setattr(v.pytesseract, "image_to_data",
                        lambda im, lang, output_type: _ocr_with(["Discord"]))
    monkeypatch.setattr("sunny.brain.ollama_client.call_llm",
                        lambda *a, **kw: ("Discord abierto", _Stats()))
    r = plugin.execute("describe_screen", {"raw": False}, {})
    assert r.success and r.data.get("description") == "Discord abierto"


def test_wait_for_screen_text_finds_text_immediately(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v
    _patch_screen(monkeypatch, tmp_path)
    monkeypatch.setattr(
        v.pytesseract, "image_to_data",
        lambda im, lang, output_type: _ocr_with(["PLAY", "QUIT"]),
    )
    r = plugin.execute(
        "wait_for_screen_text",
        {"text": "PLAY", "timeout_sec": 5, "interval_sec": 0.01},
        {},
    )
    assert r.success
    assert r.data["found"] is True
    assert r.data["attempts"] == 1


def test_wait_for_screen_text_finds_text_after_retries(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v
    _patch_screen(monkeypatch, tmp_path)
    state = {"calls": 0}

    def fake_ocr(im, lang, output_type):
        state["calls"] += 1
        if state["calls"] < 3:
            return _ocr_with(["loading"])
        return _ocr_with(["PLAY"])

    monkeypatch.setattr(v.pytesseract, "image_to_data", fake_ocr)
    r = plugin.execute(
        "wait_for_screen_text",
        {"text": "PLAY", "timeout_sec": 5, "interval_sec": 0.01},
        {},
    )
    assert r.success
    assert r.data["found"] is True
    assert r.data["attempts"] >= 3


def test_wait_for_screen_text_returns_not_found_on_timeout(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v
    _patch_screen(monkeypatch, tmp_path)
    monkeypatch.setattr(
        v.pytesseract, "image_to_data",
        lambda im, lang, output_type: _ocr_with(["loading"]),
    )
    r = plugin.execute(
        "wait_for_screen_text",
        {"text": "PLAY", "timeout_sec": 1, "interval_sec": 0.05},
        {},
    )
    assert r.success  # devuelve found=False sin lanzar excepción
    assert r.data["found"] is False
    assert r.data["text"] == "PLAY"


def test_wait_for_screen_text_returns_attempts_count(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v
    _patch_screen(monkeypatch, tmp_path)
    monkeypatch.setattr(
        v.pytesseract, "image_to_data",
        lambda im, lang, output_type: _ocr_with(["loading"]),
    )
    r = plugin.execute(
        "wait_for_screen_text",
        {"text": "X", "timeout_sec": 1, "interval_sec": 0.1},
        {},
    )
    assert r.success
    assert r.data["attempts"] >= 1


def test_wait_for_screen_text_does_not_raise_on_timeout(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v
    _patch_screen(monkeypatch, tmp_path)
    monkeypatch.setattr(
        v.pytesseract, "image_to_data",
        lambda im, lang, output_type: _ocr_with(["nada"]),
    )
    # Si lanzase excepción, success sería False con error_type
    r = plugin.execute(
        "wait_for_screen_text",
        {"text": "X", "timeout_sec": 1, "interval_sec": 0.05},
        {},
    )
    assert r.success
    assert r.error is None
