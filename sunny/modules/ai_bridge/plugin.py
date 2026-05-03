from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from sunny.core.logging.logger import get_logger
from sunny.core.plugins.base import PluginBase, PluginResult
from sunny.modules.ai_bridge.backends import AIBackend, StubBackend

log = get_logger("sunny.modules.ai_bridge")

SUPPORTED_PROVIDERS = ("chatgpt", "deepseek", "gemini")


class AIBridgePlugin(PluginBase):
    """Plugin de comunicación con IAs externas."""

    name: str = "ai_bridge"

    def __init__(self, backends: Optional[Dict[str, AIBackend]] = None) -> None:
        if backends is None:
            backends = {p: StubBackend(p) for p in SUPPORTED_PROVIDERS}
        self._backends: Dict[str, AIBackend] = backends
        self._actions: Dict[str, Callable[..., Any]] = {
            "ask_external": self._ask_external,
        }

    def execute(self, action, params, context, timeout_sec=30) -> PluginResult:
        if action not in self._actions:
            return PluginResult(
                success=False,
                error=f"action '{action}' no soportada por ai_bridge",
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
        log.info("ai_bridge_action_done", action=action, success=res.success)
        return res

    def _ask_external(self, provider: str, prompt: str) -> Dict[str, Any]:
        if provider not in self._backends:
            raise ValueError(
                f"provider '{provider}' no soportado. "
                f"Usa uno de: {', '.join(self._backends.keys())}"
            )
        response = self._backends[provider].ask(prompt)
        return {"provider": provider, "response": response}
