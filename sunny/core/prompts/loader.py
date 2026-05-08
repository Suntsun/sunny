from pathlib import Path
from typing import Dict

_PROMPTS_DIR = Path(__file__).parent
_CACHE: Dict[str, str] = {}


def load_system_prompt(version: str = "v3") -> str:
    """Carga el system prompt por versión con caché.

    La versión activa por defecto es "v3" (incluye visión reactiva:
    get_screen_state, wait_for_screen_text y agent_loop).
    "v1" y "v2" siguen disponibles para regresión y carga de los
    archivos originales sin cambios.
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
