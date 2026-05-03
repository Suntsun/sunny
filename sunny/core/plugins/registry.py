from __future__ import annotations

from typing import Dict, List, Optional

from sunny.core.logging.logger import get_logger
from sunny.core.plugins.base import PluginBase

log = get_logger("sunny.core.plugins.registry")


class PluginRegistry:
    """Registro central de plugins disponibles en sunny."""

    def __init__(self) -> None:
        self._plugins: Dict[str, PluginBase] = {}

    def register(self, plugin: PluginBase) -> None:
        name = getattr(plugin, "name", None)
        if not name:
            raise ValueError("plugin.name no puede estar vacío")
        if name in self._plugins:
            raise ValueError(f"plugin '{name}' ya registrado")
        self._plugins[name] = plugin
        log.info("plugin_registered", name=name, class_=type(plugin).__name__)

    def unregister(self, name: str) -> None:
        if name not in self._plugins:
            raise KeyError(f"plugin '{name}' no registrado")
        del self._plugins[name]
        log.info("plugin_unregistered", name=name)

    def get(self, name: str) -> Optional[PluginBase]:
        return self._plugins.get(name)

    def is_registered(self, name: str) -> bool:
        return name in self._plugins

    def list_plugins(self) -> List[str]:
        return sorted(list(self._plugins.keys()))

    def clear(self) -> None:
        """Vacía el registro. SOLO PARA USO EN TESTS."""
        self._plugins.clear()
