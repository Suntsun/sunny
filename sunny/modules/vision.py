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
            "describe_screen": self._describe_screen,
            "analyze_screen": self._analyze_screen,
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

    @staticmethod
    def _build_spatial_map(img: "Image.Image", ocr_data: dict) -> str:
        """Construye un mapa textual espacial de la pantalla dividida en 3 zonas verticales."""
        width, height = img.width, img.height
        zones: Dict[str, list] = {"top": [], "middle": [], "bottom": []}
        for i, word in enumerate(ocr_data["text"]):
            if not word or not word.strip():
                continue
            conf_raw = str(ocr_data["conf"][i])
            try:
                conf = float(conf_raw)
            except ValueError:
                conf = 0.0
            if conf < 30:
                continue
            y = ocr_data["top"][i]
            if y < height / 3:
                zones["top"].append(word.strip())
            elif y < 2 * height / 3:
                zones["middle"].append(word.strip())
            else:
                zones["bottom"].append(word.strip())
        lines = []
        for zone, words in zones.items():
            if words:
                lines.append(f"[{zone}] {' '.join(words)}")
        return "\n".join(lines) if lines else "[no text detected on screen]"

    def _describe_screen(
        self, region: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """Captura la pantalla, extrae texto con OCR y lo interpreta con llama3.1."""
        import time
        from sunny.brain.ollama_client import call_llm, DEFAULT_MODEL

        t0 = time.perf_counter()
        screenshot_data = self._screenshot(region)
        img = Image.open(screenshot_data["path"])
        ocr_data = pytesseract.image_to_data(img, lang="spa+eng", output_type=pytesseract.Output.DICT)
        spatial_map = self._build_spatial_map(img, ocr_data)

        system = (
            "You are a screen reader assistant. "
            "You receive OCR text extracted from a screenshot, organized by screen zones (top/middle/bottom). "
            "Describe clearly what application and UI state is visible. "
            "List open windows, visible buttons, menus, and any important text. "
            "Be factual — only use what the OCR text provides."
        )
        user_prompt = (
            f"OCR text extracted from the screen:\n\n{spatial_map}\n\n"
            "Describe what is visible on the screen based on this text."
        )
        description, stats = call_llm(
            user_prompt=user_prompt,
            system_prompt=system,
            json_mode=False,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "description": description,
            "screenshot_path": screenshot_data["path"],
            "model_used": f"ocr+{DEFAULT_MODEL}",
            "latency_ms": latency_ms,
        }

    def _analyze_screen(
        self,
        question: str,
        region: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Captura la pantalla, extrae texto con OCR y responde una pregunta con llama3.1."""
        if not isinstance(question, str) or not question.strip():
            raise ValueError("'question' es obligatorio y no puede estar vacío")

        import time
        from sunny.brain.ollama_client import call_llm, DEFAULT_MODEL

        t0 = time.perf_counter()
        screenshot_data = self._screenshot(region)
        img = Image.open(screenshot_data["path"])
        ocr_data = pytesseract.image_to_data(img, lang="spa+eng", output_type=pytesseract.Output.DICT)
        spatial_map = self._build_spatial_map(img, ocr_data)

        system = (
            "You are a screen reader assistant. "
            "You receive OCR text extracted from a screenshot and answer questions about what is on screen. "
            "Be factual — only use what the OCR text provides. Do not invent UI elements."
        )
        user_prompt = (
            f"OCR text extracted from the screen:\n\n{spatial_map}\n\n"
            f"Question: {question}"
        )
        answer, stats = call_llm(
            user_prompt=user_prompt,
            system_prompt=system,
            json_mode=False,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "answer": answer,
            "question": question,
            "screenshot_path": screenshot_data["path"],
            "model_used": f"ocr+{DEFAULT_MODEL}",
            "latency_ms": latency_ms,
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
