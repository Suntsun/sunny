from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import pyautogui

from sunny.core.logging.logger import get_logger
from sunny.core.plugins.base import PluginBase, PluginResult
from sunny.modules.vision import VisionPlugin

log = get_logger("sunny.modules.gui")


class GuiPlugin(PluginBase):
    """Plugin de control GUI: clicks, teclado, scroll, drag."""

    name: str = "gui"

    def __init__(self, vision: Optional[VisionPlugin] = None) -> None:
        self._vision = vision or VisionPlugin()
        self._actions: Dict[str, Callable[..., Any]] = {
            "click": self._click,
            "click_on_text": self._click_on_text,
            "type_text": self._type_text,
            "press_key": self._press_key,
            "move_mouse": self._move_mouse,
            "scroll": self._scroll,
            "drag": self._drag,
        }

    def execute(self, action, params, context, timeout_sec=30) -> PluginResult:
        if action not in self._actions:
            return PluginResult(
                success=False,
                error=f"action '{action}' no soportada por gui",
                error_type="UnsupportedAction",
            )
        try:
            data = self._actions[action](**params)
            res = PluginResult(success=True, data=data)
        except Exception as e:
            res = PluginResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )
        log.info("gui_action_done", action=action, success=res.success)
        return res

    def _click(self, x: int, y: int) -> Dict[str, Any]:
        pyautogui.click(x, y)
        return {"x": x, "y": y, "clicked": True}

    def _click_on_text(self, text: str) -> Dict[str, Any]:
        res = self._vision.execute("find_on_screen", {"target": text}, {})
        if not res.success:
            raise RuntimeError(res.error or "find_on_screen falló")
        if not res.data.get("found"):
            raise RuntimeError(f"No se encontró texto '{text}' en pantalla")
        center = res.data["center"]
        pyautogui.click(center["x"], center["y"])
        return {"text": text, "clicked_at": center}

    def _type_text(self, text: str) -> Dict[str, Any]:
        pyautogui.write(text, interval=0.02)
        return {"text": text, "length": len(text)}

    def _press_key(self, key: str) -> Dict[str, Any]:
        if "+" in key:
            keys = [k.strip() for k in key.split("+")]
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(key)
        return {"key": key}

    def _move_mouse(self, x: int, y: int) -> Dict[str, Any]:
        pyautogui.moveTo(x, y)
        return {"x": x, "y": y}

    def _scroll(self, direction: str, amount: int) -> Dict[str, Any]:
        if direction == "up":
            pyautogui.scroll(amount)
        elif direction == "down":
            pyautogui.scroll(-amount)
        else:
            raise ValueError(f"direction inválida: '{direction}', debe ser 'up' o 'down'")
        return {"direction": direction, "amount": amount}

    def _drag(self, from_x: int, from_y: int, to_x: int, to_y: int) -> Dict[str, Any]:
        pyautogui.moveTo(from_x, from_y)
        pyautogui.dragTo(to_x, to_y, button="left")
        return {"from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}}
