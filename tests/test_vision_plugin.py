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
