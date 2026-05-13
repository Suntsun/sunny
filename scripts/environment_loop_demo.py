"""Demo runnable del bucle de entorno (perception/reasoner/controller).

Objetivo demostrado:
  - Esperar hasta que aparezca el texto "TARGET" en la pantalla.
  - Cuando aparezca, escribir una línea de confirmación.
  - Parar.

Cómo usarlo:
  1. Abrir Notepad.
  2. NO escribir todavía. Mantener Notepad activo en primer plano.
  3. Lanzar este script:
       .venv\\Scripts\\python.exe scripts\\environment_loop_demo.py
  4. Escribir manualmente la palabra "TARGET" en Notepad mientras el script
     hace ticks. El bucle debe detectar el texto, escribir la confirmación,
     y parar con stopped_reason='goal_reached'.

El bucle hace max 30 ticks y se corta a 60s. No toca CLI, no se integra a
producción — es un consumidor mínimo para validar la infraestructura.

Para swap del razonador (sin código nuevo):
    $env:SUNNY_M6_PROVIDER = "cerebras"      # ya es default
    $env:SUNNY_M6_MODEL    = "llama-3.3-70b" # o cualquier otro

Requisitos: tesseract OCR en PATH, providers configurados según .env.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permite ejecutar el script desde la raíz del repo sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sunny.core.execution.environment_loop import run_environment_loop  # noqa: E402
from sunny.core.plugins.registry import PluginRegistry  # noqa: E402
from sunny.modules.gui import GuiPlugin  # noqa: E402
from sunny.modules.os_control import OSControlPlugin  # noqa: E402
from sunny.modules.vision import VisionPlugin  # noqa: E402


GOAL = (
    "Detectar la palabra 'TARGET' en pantalla y, cuando aparezca, "
    "escribir el texto 'objetivo detectado' y dar por completado el objetivo."
)


def _build_registry() -> PluginRegistry:
    reg = PluginRegistry()
    reg.register(VisionPlugin())
    reg.register(GuiPlugin())
    reg.register(OSControlPlugin())
    return reg


def main() -> int:
    print(f"[demo] Goal: {GOAL}")
    print("[demo] Asegúrate de tener Notepad abierto y enfocado.")
    print("[demo] El bucle empezará en 3s. Escribe 'TARGET' en Notepad para activar.\n")
    import time as _t
    _t.sleep(3)

    result = run_environment_loop(
        goal=GOAL,
        registry=_build_registry(),
        max_steps=30,
        tick_interval_sec=1.5,
        deadline_sec=60.0,
    )

    print("\n[demo] === Resultado ===")
    print(f"  success         : {result.success}")
    print(f"  stopped_reason  : {result.stopped_reason}")
    print(f"  ticks_executed  : {result.ticks_executed}")
    print(f"  steps_executed  : {len(result.steps_executed)}")
    print(f"  total_latency_ms: {result.total_latency_ms}")
    if result.final_observation is not None:
        snippet = (result.final_observation.screen_text or "")[:200]
        print(f"  final_text[:200]: {snippet!r}")

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
