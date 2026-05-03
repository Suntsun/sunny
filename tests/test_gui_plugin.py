import pytest
from unittest.mock import MagicMock

from sunny.modules.gui import GuiPlugin
from sunny.core.plugins.base import PluginResult


@pytest.fixture
def plugin():
    return GuiPlugin()


def test_unsupported_action_returns_error(plugin):
    r = plugin.execute("foo", {}, {})
    assert not r.success and r.error_type == "UnsupportedAction"


def test_plugin_name(plugin):
    assert plugin.name == "gui"


def test_click_calls_pyautogui(monkeypatch, plugin):
    called = {}
    monkeypatch.setattr("sunny.modules.gui.pyautogui.click", lambda x, y: called.update({"x": x, "y": y}))
    plugin.execute("click", {"x": 100, "y": 200}, {})
    assert called == {"x": 100, "y": 200}


def test_type_text_calls_pyautogui(monkeypatch, plugin):
    called = {}
    monkeypatch.setattr("sunny.modules.gui.pyautogui.write", lambda t, interval=0.02: called.update({"t": t}))
    r = plugin.execute("type_text", {"text": "hola"}, {})
    assert called["t"] == "hola" and r.data["length"] == 4


def test_press_key_single(monkeypatch, plugin):
    called = {}
    monkeypatch.setattr("sunny.modules.gui.pyautogui.press", lambda k: called.update({"k": k}))
    plugin.execute("press_key", {"key": "enter"}, {})
    assert called["k"] == "enter"


def test_press_key_combo(monkeypatch, plugin):
    called = {}
    monkeypatch.setattr("sunny.modules.gui.pyautogui.hotkey", lambda *k: called.update({"k": k}))
    plugin.execute("press_key", {"key": "ctrl+c"}, {})
    assert called["k"] == ("ctrl", "c")


def test_move_mouse_calls_pyautogui(monkeypatch, plugin):
    called = {}
    monkeypatch.setattr("sunny.modules.gui.pyautogui.moveTo", lambda x, y: called.update({"x": x, "y": y}))
    plugin.execute("move_mouse", {"x": 50, "y": 60}, {})
    assert called == {"x": 50, "y": 60}


def test_scroll_up(monkeypatch, plugin):
    called = {}
    monkeypatch.setattr("sunny.modules.gui.pyautogui.scroll", lambda a: called.update({"a": a}))
    plugin.execute("scroll", {"direction": "up", "amount": 5}, {})
    assert called["a"] == 5


def test_scroll_down(monkeypatch, plugin):
    called = {}
    monkeypatch.setattr("sunny.modules.gui.pyautogui.scroll", lambda a: called.update({"a": a}))
    plugin.execute("scroll", {"direction": "down", "amount": 5}, {})
    assert called["a"] == -5


def test_scroll_invalid_direction_raises(monkeypatch, plugin):
    monkeypatch.setattr("sunny.modules.gui.pyautogui.scroll", lambda a: None)
    r = plugin.execute("scroll", {"direction": "sideways", "amount": 5}, {})
    assert not r.success and r.error_type == "ValueError"


def test_drag_calls_pyautogui(monkeypatch, plugin):
    called = {}
    monkeypatch.setattr("sunny.modules.gui.pyautogui.moveTo", lambda x, y: called.update({"from": (x, y)}))
    monkeypatch.setattr("sunny.modules.gui.pyautogui.dragTo", lambda x, y, button="left": called.update({"to": (x, y)}))
    plugin.execute("drag", {"from_x": 0, "from_y": 0, "to_x": 100, "to_y": 100}, {})
    assert called["from"] == (0, 0) and called["to"] == (100, 100)


class _FakeVision:
    def __init__(self, result):
        self._r = result

    def execute(self, action, params, context, timeout_sec=30):
        return self._r


def test_click_on_text_found(monkeypatch):
    vision = _FakeVision(PluginResult(success=True, data={"found": True, "center": {"x": 50, "y": 60}}))
    plugin = GuiPlugin(vision=vision)

    called = {}
    monkeypatch.setattr("sunny.modules.gui.pyautogui.click", lambda x, y: called.update({"x": x, "y": y}))

    r = plugin.execute("click_on_text", {"text": "Aceptar"}, {})
    assert r.success and called == {"x": 50, "y": 60}


def test_click_on_text_not_found_raises(monkeypatch):
    vision = _FakeVision(PluginResult(success=True, data={"found": False}))
    plugin = GuiPlugin(vision=vision)

    r = plugin.execute("click_on_text", {"text": "x"}, {})
    assert not r.success and r.error_type == "RuntimeError"


def test_execute_logs_action(monkeypatch, plugin):
    monkeypatch.setattr("sunny.modules.gui.pyautogui.click", lambda x, y: None)
    calls = []
    monkeypatch.setattr("sunny.modules.gui.log.info", lambda e, **k: calls.append(e))

    plugin.execute("click", {"x": 1, "y": 1}, {})
    assert "gui_action_done" in calls
