from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import mss
import pytesseract
from PIL import Image

from sunny.core.logging.logger import get_logger
from sunny.core.plugins.base import PluginBase, PluginResult

log = get_logger("sunny.modules.vision")

SCREENSHOTS_DIR = Path(os.getenv("LOCALAPPDATA", ".")) / "sunny" / "screenshots"


class VisionPlugin(PluginBase):
    """Plugin de captura y OCR de pantalla."""

    name: str = "vision"

    def __init__(self) -> None:
        self._actions: Dict[str, Callable[..., Any]] = {
            "screenshot": self._screenshot,
            "read_screen_text": self._read_screen_text,
            "find_on_screen": self._find_on_screen,
        }

    def execute(self, action, params, context, timeout_sec=30) -> PluginResult:
        if action not in self._actions:
            return PluginResult(
                success=False,
                error=f"action '{action}' no soportada por vision",
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
        log.info("vision_action_done", action=action, success=res.success)
        return res

    def _screenshot(self, region: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"sshot_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        path = SCREENSHOTS_DIR / filename

        with mss.mss() as sct:
            if region is None:
                monitor = sct.monitors[1]
            else:
                monitor = {
                    "left": region["x"],
                    "top": region["y"],
                    "width": region["width"],
                    "height": region["height"],
                }

            screenshot = sct.grab(monitor)
            img = Image.frombytes(
                "RGB", screenshot.size, screenshot.bgra, "raw", "BGRX"
            )
            img.save(str(path))

        return {
            "path": str(path),
            "width": img.width,
            "height": img.height,
            "region": region,
        }

    def _read_screen_text(self, region: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        data = self._screenshot(region)
        img = Image.open(data["path"])
        text = pytesseract.image_to_string(img, lang="spa+eng")
        return {
            "text": text.strip(),
            "screenshot_path": data["path"],
        }

    def _find_on_screen(self, target: str) -> Dict[str, Any]:
        data = self._screenshot(None)
        img = Image.open(data["path"])
        ocr = pytesseract.image_to_data(
            img, lang="spa+eng", output_type=pytesseract.Output.DICT
        )

        for i, word in enumerate(ocr["text"]):
            if word and target.lower() in word.lower():
                left = ocr["left"][i]
                top = ocr["top"][i]
                width = ocr["width"][i]
                height = ocr["height"][i]

                conf_raw = str(ocr["conf"][i])
                conf = (
                    float(conf_raw)
                    if conf_raw.replace("-", "").replace(".", "").isdigit()
                    else 0.0
                )

                return {
                    "found": True,
                    "target": target,
                    "bbox": {
                        "x": left,
                        "y": top,
                        "width": width,
                        "height": height,
                    },
                    "center": {
                        "x": left + width // 2,
                        "y": top + height // 2,
                    },
                    "confidence": conf,
                }

        return {"found": False, "target": target}
