from pathlib import Path
from typing import Dict

_PROMPTS_DIR = Path(__file__).parent
_CACHE: Dict[str, str] = {}


def load_system_prompt(version: str = "v2") -> str:
    """Carga el system prompt por versión con caché.

    La versión activa por defecto es "v2" (incluye describe_screen y
    analyze_screen). "v1" sigue disponible para regresión y para usos
    que no necesiten visión multimodal.
    """
    if version in _CACHE:
        return _CACHE[version]

    file_path = _PROMPTS_DIR / f"system_{version}.txt"
    if not file_path.exists():
        raise FileNotFoundError(f"System prompt no encontrado: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    _CACHE[version] = content
    return content


def _reset_cache() -> None:
    """Limpia el caché interno (solo tests)."""
    _CACHE.clear()
