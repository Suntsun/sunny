"""Limpieza profesional de cachés y artefactos regenerables del proyecto Sunny."""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGET_DIRS = [
    "__pycache__",
    ".pytest_cache",
    ".eggs",
    "build",
    "dist",
    "sunny.egg-info",
    "%LOCALAPPDATA%",  # Bug de ruta: carpeta literal
]

EXT_PATTERNS = ["*.pyc", "*.pyo"]

deleted = 0
failed = []


def _safe_remove_dir(p: Path) -> None:
    global deleted
    try:
        shutil.rmtree(p, ignore_errors=True)
        if not p.exists():
            print(f"[ELIMINADO] {p.relative_to(ROOT)}")
            deleted += 1
        else:
            failed.append(str(p))
    except Exception as e:
        failed.append(f"{p}: {e}")


def _safe_remove_file(p: Path) -> None:
    global deleted
    try:
        p.unlink(missing_ok=True)
        print(f"[ELIMINADO] {p.relative_to(ROOT)}")
        deleted += 1
    except Exception as e:
        failed.append(f"{p}: {e}")


if __name__ == "__main__":
    print(f"--- Iniciando limpieza en: {ROOT} ---\n")

    for name in TARGET_DIRS:
        for p in ROOT.rglob(name):
            if p.is_dir():
                _safe_remove_dir(p)

    for pattern in EXT_PATTERNS:
        for p in ROOT.rglob(pattern):
            _safe_remove_file(p)

    print(f"\n{'='*40}")
    print(f"Limpieza completada: {deleted} elementos eliminados.")
    if failed:
        print(f"\n{len(failed)} elemento(s) no pudieron eliminarse (en uso o bloqueados):")
        for f in failed:
            print(f"  - {f}")
        print("Cierra terminales/IDEs y re-ejecuta si es necesario.")
    print("\nSi borraste .venv o .egg-info, regenera con:")
    print("   pip install -e .")
