# Sunny

> Asistente de automatización de escritorio con IA para Windows 11 — 100% local, sin datos en la nube.

![Tests](https://img.shields.io/badge/tests-786%20passing-brightgreen) ![Python](https://img.shields.io/badge/python-3.14-blue) ![Platform](https://img.shields.io/badge/platform-Windows%2011-lightgrey) ![Estado](https://img.shields.io/badge/estado-alpha%20funcional-orange)

---

## Qué es

Sunny traduce órdenes en lenguaje natural a acciones concretas sobre el sistema operativo. El usuario escribe en consola lo que quiere hacer — mover un archivo, buscar documentos vacíos, abrir una aplicación, consultar procesos — y Sunny lo interpreta, planifica y ejecuta paso a paso, pidiendo confirmación antes de cualquier operación destructiva.

El cerebro del sistema es un LLM que corre **completamente en local** mediante [Ollama](https://ollama.com/). Ningún dato abandona el equipo. El modelo local por defecto es `qwen2.5:14b-instruct-q4_K_M`, elegido por su calidad en razonamiento y generación de JSON estructurado. Como alternativa cloud está disponible Groq (`llama-3.3-70b-versatile`).

El proyecto está en **alpha funcional**: el flujo completo opera sin errores, hay 656 tests passing (incluyendo 106 smoke tests de pipeline, 31 tests de la abstracción `BrainProvider`, 13 tests de `CerebrasProvider`, 10 tests del sistema de roles minibrains, 8 tests del OCR summarizer, 9 tests de la capa de enriquecimiento y 6 tests de prompts del agente visual) y los 5 plugins principales están implementados, más el motor de bucle agente visual con arquitectura multimodelo. No es software de producción; es una herramienta personal en desarrollo activo.

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
- Modelos descargados:
  - `ollama pull qwen2.5:14b-instruct-q4_K_M` — fallback local general
  - `ollama pull qwen2.5:3b` — modelo local rápido para los roles m1 (Comprensión) y m4 (OCR Summarizer) de la arquitectura minibrains
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

Para activar el provider Groq como cerebro alternativo, instalar el extra:

```powershell
pip install -e .[groq]
```

Para activar el provider Cerebras (cloud, API OpenAI-compatible):

```powershell
pip install -e ".[cerebras]"
```

Para activar el provider Anthropic Claude (cloud, SDK oficial, adaptive thinking):

```powershell
pip install -e ".[anthropic]"
```

Para activar el provider Google Gemini (cloud, SDK `google-genai`, dynamic thinking):

```powershell
pip install -e ".[gemini]"
```

> **Quoting en PowerShell:** los corchetes `[gemini]` son sintaxis especial. **Hay que usar comillas dobles** alrededor del path-con-extras o pip fallará silenciosamente con `ERROR: You must give at least one requirement to install`.

---

## Configuración

Sunny lee variables de entorno en arranque para seleccionar el cerebro y otros ajustes.

| Variable | Default | Descripción |
|---|---|---|
| `SUNNY_BRAIN_PROVIDER` | `ollama` | Provider del LLM del cerebro (legacy, solo para `get_brain_provider()` y retrocompat). Valores: `ollama`, `groq`, `cerebras`, `anthropic`, `gemini`. |
| `GROQ_API_KEY` | — | API key de Groq. **Obligatoria** si se usa `groq` como provider. También activa la capa de enriquecimiento (guía de UI para `agent_loop`) si está presente. |
| `SUNNY_GROQ_MODEL` | `llama-3.3-70b-versatile` | Modelo de Groq usado por el provider y por la capa de enriquecimiento. |
| `CEREBRAS_API_KEY` | — | API key de Cerebras. **Obligatoria** si algún rol usa `cerebras`. |
| `SUNNY_CEREBRAS_MODEL` | `gpt-oss-120b` | Modelo de Cerebras usado por defecto si un rol selecciona `cerebras` sin `SUNNY_M{n}_MODEL`. Modelos disponibles: `gpt-oss-120b` (120B, producción), `llama3.1-8b` (8B, producción). |
| `ANTHROPIC_API_KEY` | — | API key de Anthropic. **Obligatoria** si algún rol usa `anthropic`. |
| `SUNNY_ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Modelo Anthropic por defecto si un rol selecciona `anthropic` sin `SUNNY_M{n}_MODEL`. |
| `SUNNY_ANTHROPIC_THINKING` | `on` | Adaptive thinking. `off`/`0`/`false` lo desactiva (más barato, menos profundo). |
| `GEMINI_API_KEY` | — | API key de Google AI Studio. **Obligatoria** si algún rol usa `gemini`. Se obtiene en https://aistudio.google.com/apikey. |
| `SUNNY_GEMINI_MODEL` | `gemini-2.5-flash` | Modelo Gemini por defecto si un rol selecciona `gemini` sin `SUNNY_M{n}_MODEL`. Disponibles: `gemini-2.5-pro` (capable, thinking obligatorio), `gemini-2.5-flash` (rápido + thinking dinámico), `gemini-2.5-flash-lite` (ultra rápido, sin thinking). |
| `SUNNY_GEMINI_THINKING` | `on` | Thinking dinámico (`thinking_budget=-1`). `off`/`0`/`false` lo fija a `0`. |
| `SUNNY_AUTO_CONFIRM_DESTRUCTIVE` | — | Override para automatización: en non-TTY, combinado con `--yes`, auto-confirma planes destructivos sin pedir input. En TTY se ignora (el humano siempre es preguntado). **Footgun**: si se setea globalmente, scripts que pasen `--yes` borrarán archivos sin pedir nada. Aceptable: `1`, `true`, `yes`, `on`. |

> **Nota Gemini free tier:** la cuota real medida en producción (mayo 2026) son **20 requests/día por modelo y proyecto** en Google AI Studio gratuito — no los 1500 que algunas referencias documentan. Para uso intensivo, usar Gemini como fallback secundario en lugar de primario. Ver DEP-40.

> **Carga de `.env`:** desde mayo 2026, `cli.py` invoca `load_dotenv()` al arrancar — por tanto las variables `SUNNY_*`, `*_API_KEY` y `SUNNY_M{n}_*` pueden ponerse en `.env` en la raíz del repo y se leen automáticamente desde cualquier shell. Antes el archivo se ignoraba silenciosamente (DEP-37, resuelto).

#### Arquitectura multimodelo — minibrains

Cada rol cognitivo del pipeline se resuelve a un provider y modelo independientes mediante las variables `SUNNY_M{1..4}_PROVIDER` y `SUNNY_M{1..4}_MODEL`. Los defaults reparten carga entre local (rápido) y cloud (capaz):

| Rol | Código | Provider default | Modelo default | Variables override |
|---|---|---|---|---|
| m1 Clasificador | `COMPREHENSION` | `ollama` | `qwen2.5:3b` | `SUNNY_M1_PROVIDER` / `SUNNY_M1_MODEL` |
| m2 Planificador | `PLANNING` | `cerebras` | `gpt-oss-120b` | `SUNNY_M2_PROVIDER` / `SUNNY_M2_MODEL` |
| m3 Agente visual | `GUI_AGENT` | `cerebras` | `gpt-oss-120b` | `SUNNY_M3_PROVIDER` / `SUNNY_M3_MODEL` |
| m4 OCR Summarizer | `OCR_SUMMARIZER` | `ollama` | `qwen2.5:3b` | `SUNNY_M4_PROVIDER` / `SUNNY_M4_MODEL` |

El código (no un LLM) orquesta qué modelo resuelve cada fase. Cloud nunca controla el equipo directamente: razona y devuelve JSON, el código local ejecuta las acciones. Esto reparte la capacidad cognitiva efectiva por token entre modelos pequeños/locales para tareas rápidas (clasificación, limpieza de OCR) y modelos grandes/cloud para razonamiento complejo (planificación, decisión visual).

El comportamiento por defecto (sin variables) es idéntico al de versiones previas: 100% local vía Ollama. Para usar Groq:

```powershell
$env:SUNNY_BRAIN_PROVIDER = "groq"
$env:GROQ_API_KEY = "gsk_..."
sunny --new-session "lista los archivos de mi escritorio"
```

> Aviso: con `SUNNY_BRAIN_PROVIDER=groq` los prompts del usuario salen del equipo hacia la API de Groq. Solo activarlo si esa concesión es aceptable para el caso de uso.

### System prompts por fase

Sunny usa un prompt distinto en cada fase del pipeline para mantener el coste por llamada bajo, especialmente con providers cloud que tienen cuotas diarias estrictas (p.ej. el free tier de Groq con 100k tokens/día).

| Fase | Prompt | Propósito |
|---|---|---|
| Comprensión | `system_comprehension_v1.txt` | Prompt ligero (~5.9 KB / ~1500 tokens). Solo contiene rol, intents, esquema de `ComprehensionResult`, calibración de confidence, regla de seguridad resumida y few-shots de comprensión. No incluye catálogo de plugins ni esquema de planificación. |
| Planificación | `system_v3.txt` | Prompt completo con catálogo de plugins, parámetros de cada acción, reglas de confirmación y few-shots completos (comprensión + plan). |
| Agente visual | `system_agent_loop_v1.txt` | Prompt interno usado en cada iteración del bucle agente. |

Esta separación reduce de forma significativa los tokens consumidos por la fase de comprensión, que es la más frecuente en el pipeline.

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
│   ├── ollama_client.py       # Cliente Ollama — llama3.1, num_ctx=16384
│   ├── factory.py             # get_brain_provider() (legacy) + BrainRole / get_provider_for_role (minibrains)
│   └── providers/
│       ├── base.py            # BrainProvider (ABC)
│       ├── ollama_provider.py # Wrapper sobre ollama_client (default local)
│       ├── groq_provider.py   # Provider Groq (cloud, OpenAI-compatible)
│       ├── cerebras_provider.py # Provider Cerebras (cloud, OpenAI SDK + base_url custom)
│       ├── anthropic_provider.py # Provider Anthropic Claude (SDK anthropic, adaptive thinking)
│       └── gemini_provider.py # Provider Google Gemini (SDK google-genai, dynamic thinking)
├── core/
│   ├── execution/
│   │   ├── engine.py          # Motor de ejecución por steps con timeout y threading
│   │   ├── agent_loop.py      # Bucle agente visual (usa rol GUI_AGENT + OCR Summarizer)
│   │   └── ocr_summarizer.py  # m4: estructura el OCR crudo antes de cada iteración (fail-safe)
│   ├── logging/
│   │   └── logger.py          # structlog + stdlib; JSON a fichero, consola con --verbose
│   ├── memory/
│   │   └── sqlite.py          # Historial de sesiones en SQLite
│   ├── models/
│   │   └── plan.py            # Pydantic: ComprehensionResult, PlanV2, Step
│   ├── orchestrator/
│   │   ├── confirmation.py    # Confirmaciones interactivas (sí/no, conflictos de fichero)
│   │   ├── enrichment.py      # Capa opcional Groq: guía de UI antes de planificar agent_loop
│   │   ├── reporter.py        # Salida Rich: tablas, árboles, paneles por acción
│   │   └── validator.py       # Validación de planes contra catálogo de plugins
│   ├── plugins/
│   │   ├── base.py            # PluginBase + PluginResult
│   │   └── registry.py        # Registro de plugins
│   ├── prompts/
│   │   ├── system_v1.txt                  # System prompt original (no editar)
│   │   ├── system_v2.txt                  # v2 — describe_screen y analyze_screen (no editar)
│   │   ├── system_v3.txt                  # System prompt completo — usado por planificación
│   │   ├── system_comprehension_v1.txt    # Prompt ligero solo para la fase de comprensión
│   │   ├── system_agent_loop_v1.txt       # Prompt interno del agente visual (iteraciones del bucle)
│   │   └── system_ocr_summarizer_v1.txt   # Prompt del rol m4 (extracción estructurada de pantalla)
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

**Modo estático (tareas directas):**
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
  │  si el step es GUI → inyecta contexto de pantalla (OCR) antes de ejecutar
       │
       ▼
[REPORTE] — salida Rich enriquecida según el tipo de acción ejecutada
```

**Modo agente visual (tareas con interfaz dinámica):**
```
Orden del usuario
       │
       ▼
[COMPRENSIÓN] — intent: agent_loop
       │
       ▼
[ENRIQUECIMIENTO]  (opcional, fail-safe)
  Si GROQ_API_KEY está definida → consulta Groq por pasos de UI concretos
  El resultado se inyecta como [GUÍA PREVIA] en el prompt del planner.
  Si Groq no está disponible o falla, el pipeline continúa sin guía.
       │
       ▼
[PLANIFICACIÓN] — genera PlanV2 con intent=agent_loop
       │
       ▼
[BUCLE AGENTE]  ←──────────────────────────────┐
  1. get_screen_state (OCR ~1-2s)              │
  2. LLM decide siguiente acción               │
  3. ejecuta (click, espera, tecla...)         │
  4. ¿goal_reached? → SÍ: termina             │
                    → NO: vuelve al paso 1 ───┘
  Límite: MAX_LOOP_STEPS=20 / timeout configurable
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
| `describe_screen` | `region` *(opcional)*, `raw: bool` | OCR + llama3.1: describe qué hay en pantalla. Con `raw=True` devuelve el mapa OCR directo (~1-2s) |
| `analyze_screen` | `question`, `region` *(opcional)* | OCR + llama3.1: responde una pregunta sobre la pantalla |
| `get_screen_state` | `region` *(opcional)* | OCR rápido sin LLM (~1-2s) — devuelve texto por zonas para uso del agente |
| `wait_for_screen_text` | `text`, `timeout_sec`, `interval_sec` | Polling de pantalla hasta que el texto aparece o se agota el timeout |

`describe_screen`, `analyze_screen` y `get_screen_state` usan un enfoque híbrido: Tesseract extrae el texto real de la pantalla dividido en zonas (top/middle/bottom). Sin alucinaciones. `wait_for_screen_text` es la pieza clave para sincronizar automatizaciones con el estado real de las aplicaciones.

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

### `agent_loop` — Bucle agente visual

| Acción | Parámetros | Descripción |
|---|---|---|
| `run` | `goal`, `max_steps` | Bucle reactivo: observa pantalla → decide → ejecuta → repite |

El motor `agent_loop` es el componente que permite a Sunny automatizar interfaces dinámicas cuyo estado no se conoce de antemano. En cada iteración: captura pantalla con OCR, el LLM decide la siguiente acción (click, tecla, espera...), la ejecuta, y evalúa si el objetivo está conseguido. Se detiene cuando el LLM declara `goal_reached: true`, cuando se alcanzan `max_steps`, o por timeout.

### Capa de enriquecimiento — Guía de UI previa a la planificación

Componente opcional que mejora la calidad de los planes `agent_loop` consultando Groq antes de planificar. Solo se activa cuando `intent=agent_loop` y existe `GROQ_API_KEY`.

| Propiedad | Valor |
|---|---|
| Entrada | `ComprehensionResult` con `intent=agent_loop` |
| Salida | Texto con 3-5 pasos concretos de UI (clics, escritura, atajos), inyectado como `[GUÍA PREVIA]` en el prompt del planner |
| Modelo | `SUNNY_GROQ_MODEL` (default `llama-3.3-70b-versatile`) |
| Timeout | 15 s, `temperature=0.1`, `max_tokens=200` |
| Tolerancia a fallos | Si Groq no está disponible, falla, devuelve vacío o tarda demasiado, se devuelve `None` y el pipeline continúa sin guía |
| Independiente del cerebro | Funciona con `SUNNY_BRAIN_PROVIDER=ollama` o `groq` por igual |

El planner añade la guía en el bloque `[GUÍA PREVIA]` antes de `[COMPRENSIÓN PREVIA]`, y `system_v3.txt` instruye al LLM para usar esos pasos como orientación al construir el `goal` de `agent_loop.run`, manteniendo flexibilidad si la UI difiere de lo esperado.

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
- Por defecto (sin variables de entorno) el LLM corre en local vía Ollama: ningún dato abandona el equipo. Los roles m2 y m3 usan Cerebras por defecto (cloud); se pueden redirigir a Ollama con `SUNNY_M2_PROVIDER=ollama` y `SUNNY_M3_PROVIDER=ollama` para modo 100% local.
- El stdin se drena antes de cada confirmación para evitar que comandos pegados en el REPL contaminen los prompts interactivos.
- En non-TTY (CI, pipes, redirección): los planes destructivos abortan limpio con código 2 a menos que `SUNNY_AUTO_CONFIRM_DESTRUCTIVE=1` esté activo junto con `--yes`. El check de TTY requiere stdin **y** stdout (descubierto en producción: Bash-on-Windows reporta `stdin.isatty()=True` aunque sea contexto scripted; el chequeo conjunto elimina ese falso positivo). Ver DEP-38, DEP-43.

---

## Tests

```powershell
pytest --tb=short -q      # 786 tests passing, ~31 s
```

```
tests/
├── brain/
│   ├── test_factory.py            # Selección de provider vía SUNNY_BRAIN_PROVIDER (10 tests)
│   ├── test_factory_roles.py      # BrainRole + get_provider_for_role, defaults y overrides (10 tests)
│   ├── test_ollama_provider.py    # Delegación a ollama_client (8 tests)
│   ├── test_groq_provider.py      # JSON mode, retries con hint, health_check (13 tests)
│   └── test_cerebras_provider.py  # Igual que Groq pero con Cerebras SDK (13 tests)
├── modules/
│   ├── test_files.py              # Plugin files
│   ├── test_os_control.py         # Plugin os_control
│   ├── test_vision_reactive.py    # wait_for_screen_text, get_screen_state (11 tests)
├── test_comprehension.py          # Fase de comprensión
├── test_planner.py                # Fase de planificación
├── test_enrichment.py             # Capa de enriquecimiento Groq + integración con planner (9 tests)
├── test_validator.py              # Validación de planes (incluye agent_loop)
├── test_engine.py                 # Motor + inyección de screen context
├── test_agent_loop.py             # Bucle agente (núcleo)
├── test_agent_loop_extended.py    # Bucle agente (casos extendidos)
├── test_memory.py                 # Historial SQLite
├── test_session.py                # Gestión de sesiones
├── test_cli.py                    # CLI end-to-end (mocks)
├── test_ocr_summarizer.py         # m4: formato de salida, fail-safe, propagación de goal/ocr (8 tests)
├── test_prompts.py                # system_v1/v2/v3 + agent_loop prompt + reglas (6 tests)
└── test_smoke_100.py              # 106 smoke tests de pipeline completo
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
| DEP-27 | Bucle de visión reactivo Fase 2: replanificación mid-ejecución basada en screenshot tras cada step | Engine / Vision | Alta | ✅ Resuelto |
| DEP-28 | Inyección automática de contexto visual al inicio de comandos GUI (screenshot antes de planificar) | Planner / Vision | Alta | ✅ Resuelto |
| DEP-29 | Política de retención de screenshots con límite configurable y limpieza automática | Vision | Baja | Abierto |
| DEP-30 | Abstracción `BrainProvider` con factory y backends Ollama/Groq vía `SUNNY_BRAIN_PROVIDER` | Brain | Alta | ✅ Resuelto |
| DEP-31 | Capa de enriquecimiento opcional: consulta Groq por pasos de UI antes de planificar `agent_loop`, fail-safe (nunca bloquea el pipeline) | Orchestrator | Alta | ✅ Resuelto |
| DEP-32 | `test_health_check_model_present` falla en aislamiento: el monkeypatch parchea `ollama.list` pero `health_check()` puede estar usando `Client().list()` internamente, ignorando el patch | Brain / Tests | Baja | Abierto |
| DEP-33 | Suite de tests asume `SUNNY_BRAIN_PROVIDER=ollama` (o unset): con `=groq` los mocks de `ollama.Client.chat` no interceptan las llamadas y los tests fallan con 429. Documentar en CONTRIBUTING o añadir fixture `conftest.py` que fuerce `ollama` durante pytest | Tests | Media | Abierto |
| DEP-34 | Rate limiting TPM con Groq free tier durante `agent_loop`: el bucle de iteraciones rápidas consume TPM más rápido que el límite del tier; el cliente hace retry con backoff (no es fallo hard pero añade latencia, observados 2 retries por 429 en producción). Se resuelve con Dev tier de Groq o con Cerebras como provider alternativo | Brain / Provider | Baja | Abierto |
| DEP-35 | Arquitectura multimodelo de minibrains — m1 (comprensión) / m2 (planificador) / m3 (agente visual) / m4 (OCR summarizer) con roles separados, provider Cerebras (OpenAI-compatible) y capa OCR Summarizer fail-safe que estructura el OCR crudo antes de cada iteración del bucle agente | Brain / Orchestrator | Alta | ✅ Resuelto |
| DEP-36 | Provider Google Gemini (`gemini_provider.py`) con SDK `google-genai`, thinking dinámico (`thinking_budget=-1`), JSON mode por prompt engineering, mapeo `RESOURCE_EXHAUSTED`→`LLMConnectionError` para que el FallbackChainProvider lo trate como retryable. 25 tests unitarios mockeados. Fallback `gemini→ollama` validado bajo cuota agotada en producción | Brain | Alta | ✅ Resuelto |
| DEP-37 | `.env` ignorado por falta de `load_dotenv()` en `cli.py`. La chuleta afirmaba "cargado automáticamente" pero nunca se implementó. Añadido al inicio de cli.py | CLI | Media | ✅ Resuelto |
| DEP-38 | `--yes` rompía con `EOFError` en non-TTY al chocar con la confirmación del plan destructivo. Fix: helper `confirmation.can_confirm_interactively()` (requiere stdin **y** stdout TTY — Bash-on-Windows da falso positivo solo en stdin), guard antes de `confirm_plan` que aborta con `typer.Exit(2)` y mensaje claro. Override opcional para automatización: `SUNNY_AUTO_CONFIRM_DESTRUCTIVE=1` + `--yes`. El workaround viejo `printf 's\n' \| sunny ...` ya no aplica (y era frágil). | CLI | Alta | ✅ Resuelto |
| DEP-39 | `os_control.open_app`/`close_app` no resuelve alias humanos: solo acepta `calc`, falla con `calculator` o `calculadora`. El reasoner LLM tiende a traducir nombres "humanos" → falla. Falta tabla de alias o fuzzy match | OS Control | Media | Abierto |
| DEP-40 | Free tier real de `gemini-2.5-flash` en Google AI Studio es **20 RPD por proyecto** (mayo 2026), no los 1500 documentados en algunas fuentes. La chuleta `chuletasmodelo.txt` y el README quedan inservibles como recomendación para uso intensivo de Gemini como primario. Recomendar como fallback secundario | Docs | Baja | Abierto |
| DEP-41 | Planner alucina paso extra `files.move` a ruta inventada `%USERPROFILE%\Recycle Bin` después de `delete_matching` al borrar una carpeta. End-state es correcto (carpeta va a papelera por send2trash) pero el plan es no-atómico y registra 1 fallo en el reporter. Manifestado con ollama-fallback (llama3.1-8b) en T17 del chain test; falta few-shot que enseñe `delete` como acción única para carpetas | Planner | Media | Abierto |
| DEP-42 | `'charmap' codec can't encode character '✔/≥/…'` rompía stdout/stderr en Windows con cp1252. Fix: reconfigurar `sys.stdout` y `sys.stderr` a `utf-8` al inicio de `cli.py` (defensivo con try/except por si el stream no es texto). Resuelve también el traceback de `sunny --help` (que contenía ≥ en help text). | CLI | Media | ✅ Resuelto |
| DEP-43 | `confirm_comprehension` tenía el mismo riesgo non-TTY que DEP-38: `input()` lanzaba EOFError ante baja confianza. Fix: en non-TTY con `--yes` se relaja el umbral de confianza (se confía en la comprensión, ya que el path destructivo sigue gateado por DEP-38). Sin `--yes` en non-TTY aborta con `typer.Exit(2)` y mensaje claro. | CLI | Alta | ✅ Resuelto |
| DEP-44 | El LLM alucina valores reales en `intent=conversation` para queries fácticas: ej. `sunny "qué hora es"` → "La última vez que lo hice era a las . ¿Necesitas algo más?". El planner debería detectar queries del tipo hora/fecha/ubicación y enrutarlas a un plugin con tool real (`os_control.current_time`?) en lugar de a `intent=conversation`. Manifestado en producción durante test SKILL-08 Nivel 1. | Planner | Media | Abierto |

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
1. `sunny --yes "mira la pantalla y dime qué ves"` — describe_screen con OCR ✅ verificado
2. `sunny --yes "¿qué aplicaciones están abiertas ahora mismo?"` — analyze_screen *(siguiente)*
3. `sunny --yes "abre el bloc de notas y escribe hola"` — os_control + gui encadenados
4. `sunny --yes "abre discord y ve al canal general"` — flujo GUI con contexto visual
5. `sunny --yes "abre factorio y empieza una partida nueva"` — agent_loop completo *(objetivo principal)*

---

## Desarrollo

El proyecto sigue un modelo multi-IA:
- **Claude** — orquestador principal, decisiones de arquitectura y code review
- **ChatGPT** — diseño de interfaces y esquemas
- **OpenCode** — implementación de fixes e integración de tests

---

*Sunny v0.1.0 — mayo 2026 · 786 tests · visión OCR+LLM · bucle agente visual · arquitectura multimodelo de minibrains (Ollama/Groq/Cerebras/Anthropic/Gemini) · OCR summarizer fail-safe · capa de enriquecimiento de UI · agente visual Discord validado en producción · CLI saneado para automatización non-TTY*
