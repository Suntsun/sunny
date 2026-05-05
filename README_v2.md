# Sunny

> Asistente de automatización de escritorio con IA para Windows 11 — 100% local, sin datos en la nube.

![Tests](https://img.shields.io/badge/tests-365%20passing-brightgreen) ![Python](https://img.shields.io/badge/python-3.14-blue) ![Platform](https://img.shields.io/badge/platform-Windows%2011-lightgrey) ![Estado](https://img.shields.io/badge/estado-alpha%20funcional-orange)

---

## Qué es

Sunny traduce órdenes en lenguaje natural a acciones concretas sobre el sistema operativo. El usuario escribe en consola lo que quiere hacer — mover un archivo, buscar documentos vacíos, abrir una aplicación, consultar procesos — y Sunny lo interpreta, planifica y ejecuta paso a paso, pidiendo confirmación antes de cualquier operación destructiva.

El cerebro del sistema es un LLM que corre **completamente en local** mediante [Ollama](https://ollama.com/). Ningún dato abandona el equipo. El modelo por defecto es `llama3.1:8b-instruct-q5_K_M`, elegido por su equilibrio entre velocidad y calidad en la generación de JSON estructurado.

El proyecto está en **alpha funcional**: el flujo completo opera sin errores, hay 365 tests passing y los 5 plugins principales están implementados y smoke-testeados. No es software de producción; es una herramienta personal en desarrollo activo.

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
- *(Opcional)* [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) — necesario solo para `vision.read_screen_text`

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
│   │   └── system_v1.txt      # System prompt con catálogo completo y few-shots
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
Cada acción tiene su propio render en consola: tablas para listados, árbol Rich para `tree_directory`, panel para `read_file`, tabla de metadatos para `get_info`.

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

| Acción | Parámetros |
|---|---|
| `screenshot` | `region` *(opcional)* |
| `read_screen_text` | `region` *(opcional)* |
| `find_on_screen` | `target` |

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
pytest --tb=short -q      # 365 tests, ~16 s
```

```
tests/
├── brain/           # Cliente Ollama (mocks)
├── modules/         # Plugins: files, os_control, vision, gui, ai_bridge
├── orchestrator/    # Validator, reporter, confirmation
└── test_cli.py      # CLI end-to-end (mocks de brain y plugins)
    test_memory.py   # Historial SQLite
    test_session.py  # Gestión de sesiones
```

---

## Roadmap / Issues conocidos

Los DEPs resueltos se mantienen como referencia histórica.

| ID | Descripción | Módulo | Prioridad | Estado |
|---|---|---|---|---|
| DEP-1 | Adapters explícitos `datetime↔TIMESTAMP` para silenciar warnings Python 3.12+ | Memory | Baja | Abierto |
| DEP-2 | Log condicional en `end_session` cuando no hay sesión activa | SessionManager | Cosmético | Abierto |
| DEP-3 | Bug structlog `cache_logger_on_first_use` en pytest | Logger | — | ✅ Resuelto |
| DEP-4 | 2 tests `test_session_*_event_logged` fallaban por interacción structlog↔pytest | Tests | — | ✅ Resuelto |
| DEP-5 | Inconsistencia estilística `log.info` event posicional vs kwarg | Engines | Cosmético | Abierto |
| DEP-6 | Cancelación cooperativa de threads en timeout del engine (el thread sigue vivo en background) | Execution Engine | Media | Abierto |
| DEP-7 | `restore_from_recycle_bin` requiere integración COM/pywin32 | Files plugin | Baja | Abierto |
| DEP-8 | `set_volume` y `mute` requieren `pycaw` (no instalado por defecto) | OS Control | Media | Abierto |
| DEP-9 | Política de retención de screenshots (actualmente sin límite) | Vision plugin | Baja | Abierto |
| DEP-10 | `type_text` no soporta caracteres unicode (solo ASCII) | GUI plugin | Media | Abierto |
| DEP-11 | Backends reales para AI Bridge (ChatGPT, DeepSeek, Gemini vía Playwright) | AI Bridge | Alta | Abierto |
| DEP-17 | Variables entre steps — el LLM no puede referenciar resultados de pasos anteriores en tiempo de planificación | Planner / Engine | Alta *(futura)* | Abierto |
| DEP-19 | `create_directory` recursivo genera N steps en lugar de 1 (falta few-shot) | Planner | Media | Abierto |
| DEP-20 | Ambigüedad de path cuando el usuario no especifica la ubicación de una carpeta | Planner | Media | Abierto |
| DEP-21 | Listado recursivo de directorio no implementado como acción nativa | Files plugin | Baja | Abierto |

---

## Desarrollo

El proyecto sigue un modelo multi-IA:
- **Claude** — orquestador principal, decisiones de arquitectura y code review
- **ChatGPT** — diseño de interfaces y esquemas
- **OpenCode** — implementación de fixes e integración de tests

---

*Sunny v0.1.0 — mayo 2026*
