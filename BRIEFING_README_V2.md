# Briefing para README_v2 — Sunny

## Contexto

El `README.md` actual (v1) tiene solo 10 líneas y es puramente placeholder. Tu misión es escribir un `README_v2` completo, profesional y honesto que refleje el estado real del proyecto a mayo 2026.

El proyecto lo desarrolla un desarrollador individual en Windows 11, usando un sistema multi-IA: Claude como orquestador principal, ChatGPT para diseño/arquitectura, y OpenCode para implementación e integración. La automatización de escritorio está pensada para uso personal.

---

## Qué es Sunny

**Sunny** es un asistente de automatización de escritorio con IA para Windows 11. Permite al usuario dar órdenes en lenguaje natural por consola y el sistema las traduce a acciones concretas sobre el sistema operativo: gestión de archivos, control de procesos, automatización de GUI, visión por pantalla, y llamadas a IAs externas.

El LLM que interpreta las órdenes corre **completamente en local** mediante [Ollama](https://ollama.com/), sin enviar datos a servidores externos. Modelo actual: `llama3.1:8b-instruct-q5_K_M`.

---

## Estado actual: v0.1.0 (alpha funcional)

- **365 tests passing, 0 failing**
- CLI funcional con sesiones persistentes
- 5 plugins implementados (ver abajo)
- Flujo completo: comprensión → validación → confirmación → ejecución → reporte

---

## Arquitectura

```
sunny/
├── cli.py                          # Entrypoint Typer (sunny --help)
├── brain/
│   └── ollama_client.py            # Cliente Ollama (llama3.1, num_ctx=16384)
├── core/
│   ├── execution/
│   │   └── engine.py               # Motor de ejecución por pasos con timeout y threading
│   ├── logging/
│   │   └── logger.py               # structlog + stdlib, JSON a fichero, consola opcional
│   ├── memory/
│   │   └── sqlite.py               # Historial de sesiones en SQLite
│   ├── models/
│   │   └── plan.py                 # Modelos Pydantic: ComprehensionResult, PlanV2, Step
│   ├── orchestrator/
│   │   ├── confirmation.py         # Confirmaciones interactivas (sí/no, conflictos)
│   │   ├── reporter.py             # Reportes Rich (tablas, árboles, paneles)
│   │   └── validator.py            # Validación de planes contra catálogo
│   ├── plugins/
│   │   ├── base.py                 # PluginBase + PluginResult
│   │   └── registry.py             # Registro de plugins
│   ├── prompts/
│   │   └── system_v1.txt           # System prompt con catálogo y few-shots
│   └── session/
│       └── manager.py              # Gestión de sesiones con contexto de 3 turnos
└── modules/
    ├── files.py                    # Plugin de archivos
    ├── os_control.py               # Plugin de control del SO
    ├── vision.py                   # Plugin de visión por pantalla
    ├── gui.py                      # Plugin de automatización de GUI
    └── ai_bridge.py                # Plugin de llamadas a IAs externas
```

### Flujo de ejecución

```
Entrada usuario
    │
    ▼
[FASE: COMPRENSIÓN] → LLM genera ComprehensionResult (JSON)
    │  ¿correcto? → confirmación usuario
    ▼
[FASE: PLANIFICACIÓN] → LLM genera PlanV2 (JSON con steps)
    │
    ▼
Validación (validator.py) → catálogo de plugins, firmas, reglas destructivas
    │  ¿requiere confirmación? → muestra plan al usuario
    ▼
Ejecución (engine.py) → steps en serie, timeout por step, early-stop en fallo
    │
    ▼
Reporte (reporter.py) → tablas Rich, renders semánticos por acción
```

---

## Plugins y acciones

### `files` — Gestión de archivos
| Acción | Parámetros | Confirmar |
|---|---|---|
| `read_file` | `path` | No |
| `write_file` | `path`, `content` | Sí |
| `list_directory` | `path` | No |
| `create_directory` | `path` | No |
| `tree_directory` | `path`, `max_depth` | No |
| `move` | `src`, `dst` | Sí |
| `copy` | `src`, `dst` | Sí |
| `delete` | `path` | Sí |
| `search` | `directory`, `pattern`, `recursive`, `type`, `empty_only` | No |
| `delete_matching` | `directory`, `pattern`, `recursive`, `type`, `empty_only` | Sí |
| `get_info` | `path` | No |
| `empty_recycle_bin` | — | Sí |
| `restore_from_recycle_bin` | `filename` | No (no implementado) |

Características:
- Resolución de variables de entorno en paths (`%USERPROFILE%`, `%TEMP%`, etc.)
- Eliminación segura vía papelera de reciclaje (`send2trash`)
- Conflicto en move/copy → menú interactivo: sobreescribir / renombrar (nota(1).txt) / cancelar
- `delete_matching` permite buscar y eliminar en un solo paso atómico (solución a DEP-17)

**Renders semánticos por acción** (salida en consola enriquecida con Rich):
- `list_directory` → dos tablas: carpetas y archivos con tamaño
- `search` → tabla con nombre y ruta de cada resultado
- `read_file` → Panel con el contenido del archivo
- `tree_directory` → árbol Rich con carpetas en azul y archivos en gris con tamaño
- `get_info` → tabla con ruta, tipo (Archivo/Carpeta), tamaño y fecha de modificación

### `os_control` — Control del sistema operativo
| Acción | Parámetros | Confirmar |
|---|---|---|
| `open_app` | `app` | No |
| `close_app` | `app` | No |
| `list_processes` | — | No |
| `kill_process` | `pid` | Sí |
| `set_volume` | `level` (0–100) | No |
| `mute` | `state` | No |
| `lock_screen` | — | No |
| `shutdown` | `delay_sec` | Sí |
| `restart` | `delay_sec` | Sí |
| `get_system_info` | — | No |
| `sleep_seconds` | `seconds` | No |

### `vision` — Visión por pantalla
| Acción | Parámetros |
|---|---|
| `screenshot` | `region` (opcional) |
| `read_screen_text` | `region` (opcional) |
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

## Instalación

**Requisitos:**
- Windows 11
- Python 3.11+
- [Ollama](https://ollama.com/) instalado y en ejecución
- Modelo descargado: `ollama pull llama3.1:8b-instruct-q5_K_M`
- (Opcional) [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) para `vision.read_screen_text`

Dependencias Python principales: `typer`, `rich`, `pydantic`, `ollama`, `send2trash`, `pyautogui`, `pywinauto`, `pillow`, `pytesseract`, `mss`, `structlog`. Se instalan automáticamente con `pip install -e .`.

```powershell
git clone https://github.com/usuario/sunny.git
cd sunny
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

---

## Uso

```powershell
# Nueva sesión
sunny --new-session "lista los archivos de mi escritorio"

# Continuar sesión existente
sunny --session <id> "mueve el archivo informe.pdf a Documentos"

# Ver logs en consola
sunny --verbose --new-session "abre el bloc de notas"

# Ayuda
sunny --help
```

### Ejemplos de órdenes

```
"lista los archivos de mi escritorio"
"muestra el árbol de carpetas de Documentos"
"busca todos los archivos .log en C:\temp de forma recursiva"
"elimina los archivos vacíos de la carpeta pruebas"
"crea un archivo resumen.txt en el escritorio con el texto 'pendiente'"
"mueve el archivo informe.pdf de Descargas a Documentos"
"dime la información del archivo config.json"
"abre el bloc de notas"
"ponme el volumen al 40"
"dime qué procesos están corriendo"
```

---

## Seguridad

- Las acciones destructivas (delete, move, write, shutdown, etc.) **siempre piden confirmación** antes de ejecutarse.
- Los planes con más de 5 pasos también requieren confirmación.
- El validador rechaza cualquier acción que no esté en el catálogo.
- La eliminación siempre va a la papelera de reciclaje, nunca es permanente.
- El LLM corre en local: ningún dato sale del equipo.

---

## Desarrollo y tests

```powershell
pytest --tb=short -q          # 365 tests, ~16s
pytest --tb=short -q -v       # verbose
```

Estructura de tests:
```
tests/
├── brain/
├── modules/
├── orchestrator/
└── test_cli.py, test_memory.py, test_session.py, ...
```

---

## Issues conocidos (backlog)

| ID | Descripción | Prioridad |
|---|---|---|
| DEP-1 | Warnings de sqlite3 datetime adapter (Python 3.12+) | Baja |
| DEP-17 | Variables entre steps — el LLM no puede referenciar resultados de pasos anteriores | Alta (futura) |
| DEP-19 | `create_directory` recursivo genera N steps en vez de 1 | Media |
| DEP-20 | Ambigüedad de path cuando el usuario no especifica ubicación | Media |
| DEP-21 | Listado recursivo de directorio no implementado | Baja |

---

## Instrucciones para Opus — qué escribir en README_v2

1. **Tono**: técnico pero accesible. El proyecto es personal/experimental pero con calidad de producción en tests y arquitectura.
2. **Longitud**: completo pero sin padding. Cada sección debe aportar valor real.
3. **No inventar**: no añadir features que no existen. El proyecto está en alpha — decirlo con honestidad.
4. **Estructura sugerida**:
   - Header con badge de tests (365 passing)
   - Qué es / para qué sirve (2-3 párrafos)
   - Demo rápida (gif o bloque de terminal con ejemplo)
   - Requisitos e instalación
   - Uso y ejemplos
   - Arquitectura (diagrama ASCII simplificado)
   - Plugins (tabla compacta)
   - Seguridad
   - Tests
   - Roadmap (issues conocidos)
   - Licencia / créditos si procede
5. **Idioma**: español, igual que el proyecto. Los nombres técnicos (plugin, step, etc.) en inglés.
6. **El README_v2 debe guardarse como `README_v2.md`** en la raíz del proyecto (`C:\Proyectos\sunny\`).
