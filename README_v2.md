# Sunny

> Asistente de automatización de escritorio con IA para Windows 11 — 100% local, sin datos en la nube.

![Tests](https://img.shields.io/badge/tests-534%20passing-brightgreen) ![Python](https://img.shields.io/badge/python-3.14-blue) ![Platform](https://img.shields.io/badge/platform-Windows%2011-lightgrey) ![Estado](https://img.shields.io/badge/estado-alpha%20funcional-orange)

---

## Qué es

Sunny traduce órdenes en lenguaje natural a acciones concretas sobre el sistema operativo. El usuario escribe en consola lo que quiere hacer — mover un archivo, buscar documentos vacíos, abrir una aplicación, consultar procesos — y Sunny lo interpreta, planifica y ejecuta paso a paso, pidiendo confirmación antes de cualquier operación destructiva.

El cerebro del sistema es un LLM que corre **completamente en local** mediante [Ollama](https://ollama.com/). Ningún dato abandona el equipo. El modelo por defecto es `llama3.1:8b-instruct-q5_K_M`, elegido por su equilibrio entre velocidad y calidad en la generación de JSON estructurado.

El proyecto está en **alpha funcional**: el flujo completo opera sin errores, hay 534 tests passing (incluyendo 106 smoke tests de pipeline) y los 5 plugins principales están implementados. No es software de producción; es una herramienta personal en desarrollo activo.

---

## Demo rápida

```
(.venv) PS C:\Proyectos\sunny> sunny --new-session "elimina los archivos vacíos de la carpeta pruebas del escritorio"

╭──────────────────────────── Comprensión ─────────────────────────────╮
│ He entendido: Eliminar archivos vacíos dentro de Desktop\pruebas     │
│ Intención: files  │  Confianza: 95%                                  │
╰──────────────────────────────────────────────────────────────────────╯
¿Es correcto? [S/n]: s

╭──────────────────────────── Plan (1 paso) ───────────────────────────╮
│   1. files.delete_matching                                           │
│      params: {'directory': '%USERPROFILE%\Desktop\pruebas',          │
│               'pattern': '*', 'type': 'file', 'empty_only': True}   │
╰──────────────────────────────────────────────────────────────────────╯
¿Ejecutar? [s/N]: s

                    Ejecución completada
┏━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┓
┃ # ┃ Paso                 ┃ Resultado ┃ Latencia ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━┩
│ 1 │ files.delete_matching│ ✔         │ 12 ms    │
└───┴──────────────────────┴───────────┴──────────┘
Total: 12 ms — 1 ok / 0 fallos / 0 omitidos
```

---

## Requisitos

- Windows 11
- Python 3.14
- [Ollama](https://ollama.com/) instalado y en ejecución local
- Modelo descargado: `ollama pull llama3.1:8b-instruct-q5_K_M`
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) — requerido para `vision.describe_screen`, `vision.analyze_screen` y `vision.read_screen_text`

---

## Instalación

```powershell
git clone https://github.com/usuario/sunny.git
cd sunny
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

Las dependencias se instalan automáticamente: `typer`, `rich`, `pydantic`, `ollama`, `send2trash`, `pyautogui`, `pywinauto`, `pillow`, `pytesseract`, `mss`, `structlog`.

---

## Uso

```powershell
# Nueva sesión
sunny --new-session "lista los archivos de mi escritorio"

# Continuar sesión existente
sunny --session <id> "mueve el archivo informe.pdf a Documentos"

# Ver logs INFO en consola
sunny --verbose --new-session "abre el bloc de notas"

# Ayuda
sunny --help
```

### Ejemplos de órdenes

```
"lista los archivos de mi escritorio"
"muestra el árbol de carpetas de Documentos"
"busca todos los archivos .log en C:\temp de forma recursiva"
"busca las carpetas vacías dentro de MUSICA en el escritorio"
"elimina los archivos vacíos de la carpeta pruebas"
"crea un archivo resumen.txt en el escritorio con el texto 'pendiente'"
"mueve el archivo informe.pdf de Descargas a Documentos"
"copia el archivo config.json de Documentos a Descargas"
"dime la información del archivo config.json"
"abre el bloc de notas"
"ponme el volumen al 40"
"dime qué procesos están corriendo"
```

Cuando se detecta un conflicto (el destino ya existe en `move` o `copy`), Sunny pregunta qué hacer:

```
Ya existe: nota.txt
  1  Sobreescribir
  2  Renombrar automáticamente  (ej. nota(1).txt)
  3  Cancelar
Elige [1/2/3]:
```

---

## Arquitectura

```
sunny/
├── cli.py                     # Entrypoint Typer
├── brain/
│   └── ollama_client.py       # Cliente Ollama — llama3.1, num_ctx=16384
├── core/
│   ├── execution/
│   │   └── engine.py          # Motor de ejecución por steps con timeout y threading
│   ├── logging/
│   │   └── logger.py          # structlog + stdlib; JSON a fichero, consola con --verbose
│   ├── memory/
│   │   └── sqlite.py          # Historial de sesiones en SQLite
│   ├── models/
│   │   └── plan.py            # Pydantic: ComprehensionResult, PlanV2, Step
│   ├── orchestrator/
│   │   ├── confirmation.py    # Confirmaciones interactivas (sí/no, conflictos de fichero)
│   │   ├── reporter.py        # Salida Rich: tablas, árboles, paneles por acción
│   │   └── validator.py       # Validación de planes contra catálogo de plugins
│   ├── plugins/
│   │   ├── base.py            # PluginBase + PluginResult
│   │   └── registry.py        # Registro de plugins
│   ├── prompts/
│   │   ├── system_v1.txt      # System prompt original (no editar)
│   │   └── system_v2.txt      # System prompt activo — incluye describe_screen y analyze_screen
│   └── session/
│       └── manager.py         # Gestión de sesiones, contexto de 3 turnos
└── modules/
    ├── files.py               # Plugin de archivos
    ├── os_control.py          # Plugin de control del SO
    ├── vision.py              # Plugin de visión por pantalla
    ├── gui.py                 # Plugin de automatización de GUI
    └── ai_bridge.py           # Plugin de llamadas a IAs externas
```

### Flujo de ejecución

```
Orden del usuario
       │
       ▼
[COMPRENSIÓN] — LLM genera ComprehensionResult (JSON)
       │  confirmación del usuario
       ▼
[PLANIFICACIÓN] — LLM genera PlanV2 (lista de steps con plugin + acción + params)
       │
       ▼
[VALIDACIÓN] — comprueba catálogo, firmas de parámetros y reglas de seguridad
       │  si requiere confirmación → muestra plan y espera aprobación
       ▼
[EJECUCIÓN] — steps en serie, timeout individual, early-stop en fallo
       │
       ▼
[REPORTE] — salida Rich enriquecida según el tipo de acción ejecutada
```

---

## Plugins

### `files` — Gestión de archivos

| Acción | Parámetros principales | Confirmar |
|---|---|:---:|
| `read_file` | `path` | — |
| `write_file` | `path`, `content` | ✔ |
| `list_directory` | `path` | — |
| `create_directory` | `path` | — |
| `tree_directory` | `path`, `max_depth` | — |
| `move` | `src`, `dst` | ✔ |
| `copy` | `src`, `dst` | ✔ |
| `delete` | `path` | ✔ |
| `search` | `directory`, `pattern`, `recursive`, `type`, `empty_only` | — |
| `delete_matching` | `directory`, `pattern`, `recursive`, `type`, `empty_only` | ✔ |
| `get_info` | `path` | — |
| `empty_recycle_bin` | — | ✔ |

Los paths aceptan variables de entorno Windows: `%USERPROFILE%`, `%TEMP%`, `%APPDATA%`, etc.
La eliminación siempre va a la papelera de reciclaje (`send2trash`), nunca es permanente.
Cada acción tiene su propio render en consola: tablas para listados, árbol Rich para `tree_directory`, panel para `read_file`, tabla de metadatos para `get_info`, confirmación con tamaño para `write_file`, tabla de eliminados para `delete_matching`.

### `os_control` — Control del sistema operativo

| Acción | Parámetros | Confirmar |
|---|---|:---:|
| `open_app` | `app` | — |
| `close_app` | `app` | — |
| `list_processes` | — | — |
| `kill_process` | `pid` | ✔ |
| `set_volume` | `level` (0–100) | — |
| `mute` | `state` | — |
| `lock_screen` | — | — |
| `shutdown` | `delay_sec` | ✔ |
| `restart` | `delay_sec` | ✔ |
| `get_system_info` | — | — |
| `sleep_seconds` | `seconds` | — |

### `vision` — Visión por pantalla

| Acción | Parámetros | Descripción |
|---|---|---|
| `screenshot` | `region` *(opcional)* | Captura pantalla o región |
| `read_screen_text` | `region` *(opcional)* | OCR directo, devuelve texto crudo |
| `find_on_screen` | `target` | Localiza texto en pantalla y devuelve coordenadas |
| `describe_screen` | `region` *(opcional)* | OCR + llama3.1: describe qué hay en pantalla |
| `analyze_screen` | `question`, `region` *(opcional)* | OCR + llama3.1: responde una pregunta sobre la pantalla |

`describe_screen` y `analyze_screen` usan un enfoque híbrido: Tesseract extrae el texto real de la pantalla dividido en zonas (top/middle/bottom), y llama3.1 lo interpreta. Este enfoque elimina las alucinaciones de los modelos de visión puros y reduce la latencia a ~3-4 segundos frente a los ~15-20s de LLaVA.

### `gui` — Automatización de GUI

| Acción | Parámetros |
|---|---|
| `click` | `x`, `y` |
| `click_on_text` | `text` |
| `type_text` | `text` |
| `press_key` | `key` |
| `move_mouse` | `x`, `y` |
| `scroll` | `direction`, `amount` |
| `drag` | `from_x`, `from_y`, `to_x`, `to_y` |

### `ai_bridge` — Llamadas a IAs externas

| Acción | Parámetros |
|---|---|
| `ask_external` | `provider`, `prompt` |

---

## Seguridad

- Las acciones destructivas (escritura, movimiento, borrado, apagado…) siempre piden confirmación explícita antes de ejecutarse.
- Los planes con más de 5 pasos también requieren confirmación, independientemente del tipo de acción.
- El validador rechaza cualquier plugin o acción que no esté en el catálogo registrado.
- La eliminación de archivos siempre usa la papelera de reciclaje; nunca se borra de forma permanente.
- El LLM corre en local vía Ollama: ningún dato del usuario abandona el equipo.
- El stdin se drena antes de cada confirmación para evitar que comandos pegados en el REPL contaminen los prompts interactivos.

---

## Tests

```powershell
pytest --tb=short -q      # 534 tests, ~26 s
```

```
tests/
├── modules/              # Plugins: files, os_control, vision, gui, ai_bridge
├── test_comprehension.py # Fase de comprensión
├── test_planner.py       # Fase de planificación
├── test_validator.py     # Validación de planes
├── test_engine.py        # Motor de ejecución
├── test_memory.py        # Historial SQLite
├── test_session.py       # Gestión de sesiones
├── test_cli.py           # CLI end-to-end (mocks)
└── test_smoke_100.py     # 106 smoke tests de pipeline completo
```

Los smoke tests cubren los 10 componentes principales del pipeline (modelos, cliente LLM, comprensión, planificación, validador, engine, plugins, memoria) y validan el comportamiento end-to-end con mocks de Ollama.

---

## Roadmap / Issues conocidos

Los DEPs resueltos se mantienen como referencia histórica.

| ID | Descripción | Módulo | Prioridad | Estado |
|---|---|---|---|---|
| DEP-1 | Adapters explícitos `datetime↔TIMESTAMP` para silenciar warnings Python 3.12+ | Memory | Baja | ✅ Resuelto |
| DEP-2 | Log condicional en `end_session` cuando no hay sesión activa | SessionManager | Cosmético | Abierto |
| DEP-3 | Bug structlog `cache_logger_on_first_use` en pytest | Logger | — | ✅ Resuelto |
| DEP-4 | 2 tests `test_session_*_event_logged` fallaban por interacción structlog↔pytest | Tests | — | ✅ Resuelto |
| DEP-5 | Inconsistencia estilística `log.info` event posicional vs kwarg | Engines | Cosmético | Abierto |
| DEP-6 | Cancelación cooperativa de threads en timeout del engine (el thread sigue vivo en background) | Execution Engine | Media | Abierto |
| DEP-7 | `restore_from_recycle_bin` requiere integración COM/pywin32 | Files plugin | Baja | Abierto |
| DEP-8 | `set_volume` y `mute` requieren `pycaw` (no instalado por defecto) | OS Control | Media | Abierto |
| DEP-9 | Política de retención de screenshots (actualmente sin límite) | Vision plugin | Baja | Abierto |
| DEP-10 | `type_text` no soporta caracteres unicode (solo ASCII) | GUI plugin | Media | ✅ Resuelto |
| DEP-11 | Backends reales para AI Bridge (ChatGPT, DeepSeek, Gemini vía Playwright) | AI Bridge | Alta | Abierto |
| DEP-22 | Retry LLM incluye nombres de campos del schema para guiar la corrección | Brain | Baja | ✅ Resuelto |
| DEP-23 | `health_check` usaba `str(resp)` frágil en vez de parsear `resp.models` | Brain | Baja | ✅ Resuelto |
| DEP-24 | Reporter no renderizaba `write_file`, `create_directory` ni `delete_matching` | Reporter | Media | ✅ Resuelto |
| DEP-17 | Variables entre steps — el LLM no puede referenciar resultados de pasos anteriores en tiempo de planificación | Planner / Engine | Alta *(futura)* | Abierto |
| DEP-19 | `create_directory` recursivo genera N steps en lugar de 1 (falta few-shot) | Planner | Media | Abierto |
| DEP-20 | Ambigüedad de path cuando el usuario no especifica la ubicación de una carpeta | Planner | Media | Abierto |
| DEP-21 | Listado recursivo de directorio no implementado como acción nativa | Files plugin | Baja | Abierto |
| DEP-25 | Steam library scanner para abrir juegos por nombre (`_find_in_steam` via `libraryfolders.vdf`) | OS Control | Media | Abierto |
| DEP-26 | OpenCode como backend de `ai_bridge` para tareas de código y automatización avanzada | AI Bridge | Alta | Abierto |
| DEP-27 | Bucle de visión reactivo Fase 2: replanificación mid-ejecución basada en screenshot tras cada step | Engine / Vision | Alta | Abierto |
| DEP-28 | Inyección automática de contexto visual al inicio de comandos GUI (screenshot antes de planificar) | Planner / Vision | Alta | Abierto |
| DEP-29 | Política de retención de screenshots con límite configurable y limpieza automática | Vision | Baja | Abierto |

---

## Línea de trabajo activa — Próximos tests y mejoras

Este apartado recoge la dirección de desarrollo en curso. El flujo de trabajo establecido es:

- **Esta sesión (Sonnet/Cowork):** análisis, diagnóstico, fixes puntuales, bugs
- **BigOrquestator (Opus):** implementaciones arquitectónicas grandes
- **OpenCode:** ejecución en disco, pytest, comandos de terminal

### Bucle de visión reactivo (prioridad alta)

El objetivo central es que Sunny pueda ver la pantalla, entender qué hay, y tomar decisiones basadas en ello. La Fase 1 (OCR + llama3.1) ya está implementada. Las siguientes fases:

**Fase 2 — Contexto visual antes de planificar:**
Antes de generar un plan que involucre GUI, inyectar automáticamente un `describe_screen` para que el LLM vea el estado actual de la pantalla. El planner recibe: orden del usuario + descripción de pantalla → genera un plan informado.

Test a escribir: `test_planner_injects_screen_context_for_gui_intent` — verificar que cuando `intent=gui`, el planner llama a `describe_screen` e incluye el resultado en el prompt.

**Fase 3 — Replanificación mid-ejecución:**
Tras cada step, tomar screenshot y comparar con el resultado esperado. Si hay divergencia (botón no encontrado, app no abrió, estado incorrecto), el engine pide al LLM un nuevo step para corregir.

Test a escribir: `test_engine_replans_when_step_fails_with_screen_context` — verificar que tras un fallo con `continue_on_error=False`, si hay contexto de pantalla disponible, se intenta replanificar antes de early-stop.

**Fase 4 — Loop completo:**
`screenshot → LLM decide acción → ejecuta → screenshot → compara → corrige`. Esto convierte a Sunny en un agente visual real capaz de navegar interfaces sin conocer su estructura de antemano.

### OpenCode como backend (prioridad alta)

Integrar OpenCode como un backend de `ai_bridge` que permite delegar tareas de código, análisis técnico y automatización compleja. OpenCode (v1.14.33) corre localmente, es rápido y fiable en su dominio.

Investigar: cómo expone OpenCode su API (endpoint HTTP, stdin/stdout, socket). Una vez conocida, implementar `OpenCodeBackend(AIBackend)` en `sunny/modules/ai_bridge/backends.py`.

Test a escribir: `test_ai_bridge_opencode_backend_delegates_task` — verificar que `ask_external(provider="opencode", prompt="...")` llama al backend correcto y devuelve respuesta.

### Steam library scanner (prioridad media)

Implementar `_find_in_steam(app)` en `os_control.py` que lee `libraryfolders.vdf` de Steam, localiza bibliotecas y busca el ejecutable del juego por nombre. Integrar como paso 4.5 en la cadena de `_open_app`.

Test a escribir: `test_open_app_finds_steam_game_via_library_scanner` — mock de `libraryfolders.vdf` con estructura real, verificar que el exe del juego se localiza correctamente.

### Mejoras de calidad en vision

- `test_describe_screen_returns_spatial_zones` — verificar que el mapa OCR incluye zonas top/middle/bottom cuando hay texto en cada zona
- `test_build_spatial_map_filters_low_confidence_words` — verificar que palabras con confianza < 30 se descartan
- `test_build_spatial_map_empty_screen` — verificar que pantalla sin texto devuelve `[no text detected on screen]`
- `test_analyze_screen_includes_question_in_prompt` — verificar que la pregunta aparece en el user_prompt enviado al LLM

### Smoke tests de vision y gui en producción

Secuencia de escalado pendiente (SKILL-08):
1. `sunny --yes "mira la pantalla y dime qué ves"` — describe_screen con OCR *(siguiente)*
2. `sunny --yes "¿qué aplicaciones están abiertas ahora mismo?"` — analyze_screen
3. `sunny --yes "abre el bloc de notas y escribe hola"` — os_control + gui encadenados
4. `sunny --yes "abre discord y ve al canal general"` — flujo GUI con contexto visual

---

## Desarrollo

El proyecto sigue un modelo multi-IA:
- **Claude** — orquestador principal, decisiones de arquitectura y code review
- **ChatGPT** — diseño de interfaces y esquemas
- **OpenCode** — implementación de fixes e integración de tests

---

*Sunny v0.1.0 — mayo 2026 · 534 tests · visión OCR+LLM implementada · bucle reactivo en progreso*
