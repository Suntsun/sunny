from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class PluginResult:
    """Resultado de ejecutar una acción de plugin."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None


class PluginBase(ABC):
    """Clase base abstracta para todos los plugins de sunny."""

    name: str = ""  # subclases deben sobrescribir con un identificador único

    @abstractmethod
    def execute(
        self,
        action: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        timeout_sec: int = 30,
    ) -> PluginResult:
        """Ejecuta una acción con los params dados. Devuelve un PluginResult."""
        ...
