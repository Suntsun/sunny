import pytest
from unittest.mock import MagicMock

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


def test_unsupported_action_returns_error(plugin):
    r = plugin.execute("foo", {}, {})
    assert not r.success and r.error_type == "UnsupportedAction"


def test_plugin_name(plugin):
    assert plugin.name == "vision"


def test_screenshot_full_screen(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v

    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path / "shots")
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)

    img = MagicMock()
    img.width, img.height = 1920, 1080
    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: img)

    r = plugin.execute("screenshot", {"region": None}, {})
    assert r.success
    assert str(tmp_path) in r.data["path"]
    assert r.data["width"] == 1920


def test_screenshot_with_region(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v

    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path)
    ctx, sct = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)

    img = MagicMock()
    img.width, img.height = 1, 1
    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: img)

    region = {"x": 1, "y": 2, "width": 3, "height": 4}
    plugin.execute("screenshot", {"region": region}, {})
    sct.grab.assert_called_once()


def test_screenshot_creates_directory(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v

    shots = tmp_path / "new"
    monkeypatch.setattr(v, "SCREENSHOTS_DIR", shots)
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)

    img = MagicMock()
    img.width, img.height = 1, 1
    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: img)

    plugin.execute("screenshot", {"region": None}, {})
    assert shots.exists()


def test_read_screen_text_calls_tesseract(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v

    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path)
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)

    img = MagicMock()
    img.width, img.height = 1, 1
    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: img)
    monkeypatch.setattr(v.Image, "open", lambda p: MagicMock())
    monkeypatch.setattr(v.pytesseract, "image_to_string", lambda i, lang: "hola mundo")

    r = plugin.execute("read_screen_text", {"region": None}, {})
    assert r.success and r.data["text"] == "hola mundo"


def test_find_on_screen_found(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v

    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path)
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)

    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: MagicMock())
    monkeypatch.setattr(v.Image, "open", lambda p: MagicMock())

    monkeypatch.setattr(
        v.pytesseract,
        "image_to_data",
        lambda *a, **k: {
            "text": ["", "Aceptar"],
            "left": [0, 10],
            "top": [0, 20],
            "width": [0, 30],
            "height": [0, 40],
            "conf": [-1, 90],
        },
    )

    r = plugin.execute("find_on_screen", {"target": "Aceptar"}, {})
    assert r.success and r.data["found"]


def test_find_on_screen_not_found(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v

    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path)
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)

    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: MagicMock())
    monkeypatch.setattr(v.Image, "open", lambda p: MagicMock())
    monkeypatch.setattr(
        v.pytesseract,
        "image_to_data",
        lambda *a, **k: {
            "text": ["hola"],
            "left": [0],
            "top": [0],
            "width": [0],
            "height": [0],
            "conf": [0],
        },
    )

    r = plugin.execute("find_on_screen", {"target": "x"}, {})
    assert not r.data["found"]


def test_find_on_screen_case_insensitive(monkeypatch, tmp_path, plugin):
    import sunny.modules.vision as v

    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path)
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)

    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: MagicMock())
    monkeypatch.setattr(v.Image, "open", lambda p: MagicMock())
    monkeypatch.setattr(
        v.pytesseract,
        "image_to_data",
        lambda *a, **k: {
            "text": ["aceptar"],
            "left": [1],
            "top": [1],
            "width": [1],
            "height": [1],
            "conf": [90],
        },
    )

    r = plugin.execute("find_on_screen", {"target": "ACEPTAR"}, {})
    assert r.data["found"]


def test_execute_logs_action(monkeypatch, plugin, tmp_path):
    import sunny.modules.vision as v

    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path)
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)

    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: MagicMock())
    calls = []
    monkeypatch.setattr(v.log, "info", lambda *a, **k: calls.append(a[0]))

    plugin.execute("screenshot", {"region": None}, {})
    assert "vision_action_done" in calls


# ---------------------------------------------------------------------------
# Tests para describe_screen y analyze_screen (visión multimodal)
# ---------------------------------------------------------------------------


class _FakeStats:
    def __init__(self, tokens_out=42, latency_ms=123):
        self.tokens_in = 10
        self.tokens_out = tokens_out
        self.latency_ms = latency_ms
        self.retries_used = 0


def _patch_screenshot(monkeypatch, tmp_path):
    """Stub _screenshot para evitar mss real."""
    import sunny.modules.vision as v

    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path)
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)
    img = MagicMock()
    img.width, img.height = 1920, 1080
    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: img)


def _fake_ocr_data():
    """OCR data simulado con palabras en 3 zonas."""
    return {
        "text": ["File", "Edit", "View", "", "Discord", "", "General", "", "Escribe", "aquí"],
        "conf": ["90", "90", "90", "-1", "85", "-1", "88", "-1", "80", "80"],
        "top":  [10,    10,    10,    0,   350,   0,    600,   0,    900,   900],
        "left": [10,    60,    110,   0,   100,   0,    100,   0,    100,   200],
        "width":[40,    40,    40,    0,   80,    0,    70,    0,    60,    40],
        "height":[20,   20,    20,    0,   20,    0,    20,    0,    20,    20],
    }


def _patch_screenshot_with_ocr(monkeypatch, tmp_path):
    """Stub _screenshot + Image.open + pytesseract para evitar hardware real."""
    import sunny.modules.vision as v

    monkeypatch.setattr(v, "SCREENSHOTS_DIR", tmp_path)
    ctx, _ = _fake_mss()
    monkeypatch.setattr(v.mss, "mss", lambda: ctx)
    img = MagicMock()
    img.width, img.height = 1920, 1080
    monkeypatch.setattr(v.Image, "frombytes", lambda *a, **k: img)
    monkeypatch.setattr(v.Image, "open", lambda path: img)
    monkeypatch.setattr(v.pytesseract, "image_to_data", lambda im, lang, output_type: _fake_ocr_data())


class _FakeProvider:
    """Provider de mentira con call_text controlable."""
    _model = "fake-model"

    def __init__(self, response="(respuesta vacía)", error=None):
        self._response = response
        self._error = error
        self.last_user_prompt = None
        self.last_system_prompt = None

    def call_text(self, user_prompt, system_prompt, **kw):
        self.last_user_prompt = user_prompt
        self.last_system_prompt = system_prompt
        if self._error is not None:
            raise self._error
        return (self._response, _FakeStats())


def _patch_provider(monkeypatch, provider):
    """Sustituye get_provider_for_role en vision.py por uno que devuelve provider."""
    monkeypatch.setattr(
        "sunny.modules.vision.get_provider_for_role",
        lambda role: provider,
    )


def test_describe_screen_calls_ocr_and_llm(monkeypatch, tmp_path, plugin):
    _patch_screenshot_with_ocr(monkeypatch, tmp_path)
    provider = _FakeProvider("Hay una ventana de Discord abierta con un canal General.")
    _patch_provider(monkeypatch, provider)

    r = plugin.execute("describe_screen", {"region": None}, {})
    assert r.success
    assert "ocr" in provider.last_user_prompt.lower() or "screen" in provider.last_user_prompt.lower()


def test_describe_screen_returns_description_and_path(monkeypatch, tmp_path, plugin):
    _patch_screenshot_with_ocr(monkeypatch, tmp_path)
    _patch_provider(monkeypatch, _FakeProvider("Hay un editor de texto abierto"))

    r = plugin.execute("describe_screen", {"region": None}, {})
    assert r.success
    assert r.data["description"] == "Hay un editor de texto abierto"
    assert "screenshot_path" in r.data
    assert r.data["screenshot_path"].endswith(".png")
    assert "ocr" in r.data["model_used"].lower()


def test_describe_screen_plugin_result_success(monkeypatch, tmp_path, plugin):
    _patch_screenshot_with_ocr(monkeypatch, tmp_path)
    _patch_provider(monkeypatch, _FakeProvider("ok"))
    r = plugin.execute("describe_screen", {}, {})
    assert r.success and r.error is None


def test_describe_screen_propagates_llm_error(monkeypatch, tmp_path, plugin):
    _patch_screenshot_with_ocr(monkeypatch, tmp_path)
    from sunny.brain.ollama_client import LLMError

    _patch_provider(monkeypatch, _FakeProvider(error=LLMError("llm no disponible")))

    r = plugin.execute("describe_screen", {}, {})
    assert not r.success
    assert "llm" in r.error.lower()


def test_analyze_screen_sends_question_to_llm(monkeypatch, tmp_path, plugin):
    _patch_screenshot_with_ocr(monkeypatch, tmp_path)
    provider = _FakeProvider("Sí, hay tres botones")
    _patch_provider(monkeypatch, provider)

    r = plugin.execute(
        "analyze_screen",
        {"question": "¿Cuántos botones hay?", "region": None},
        {},
    )
    assert r.success
    assert "¿Cuántos botones hay?" in provider.last_user_prompt


def test_analyze_screen_returns_answer_and_question(monkeypatch, tmp_path, plugin):
    _patch_screenshot_with_ocr(monkeypatch, tmp_path)
    _patch_provider(monkeypatch, _FakeProvider("Tres botones grandes"))

    r = plugin.execute(
        "analyze_screen", {"question": "¿Cuántos botones hay?"}, {}
    )
    assert r.success
    assert r.data["answer"] == "Tres botones grandes"
    assert r.data["question"] == "¿Cuántos botones hay?"
    assert "ocr" in r.data["model_used"].lower()
    assert r.data["screenshot_path"].endswith(".png")


def test_analyze_screen_missing_question_raises(monkeypatch, tmp_path, plugin):
    _patch_screenshot_with_ocr(monkeypatch, tmp_path)
    _patch_provider(monkeypatch, _FakeProvider("no debería llegar"))

    r = plugin.execute("analyze_screen", {"question": ""}, {})
    assert not r.success
    assert r.error_type == "ValueError"


def test_vision_actions_route_through_ocr_summarizer_role(monkeypatch, tmp_path, plugin):
    """Verifica el fix del bypass: vision.describe/analyze pasan por el factory
    con BrainRole.OCR_SUMMARIZER, no por call_llm directo a Ollama."""
    _patch_screenshot_with_ocr(monkeypatch, tmp_path)
    captured_roles = []
    provider = _FakeProvider("ok")

    def fake_get(role):
        captured_roles.append(role)
        return provider

    monkeypatch.setattr("sunny.modules.vision.get_provider_for_role", fake_get)

    plugin.execute("describe_screen", {}, {})
    plugin.execute("analyze_screen", {"question": "x"}, {})

    from sunny.brain.factory import BrainRole
    assert captured_roles == [BrainRole.OCR_SUMMARIZER, BrainRole.OCR_SUMMARIZER]


def test_describe_and_analyze_registered_in_actions(plugin):
    assert "describe_screen" in plugin._actions
    assert "analyze_screen" in plugin._actions
