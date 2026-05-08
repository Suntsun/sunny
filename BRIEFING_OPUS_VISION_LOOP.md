# BRIEFING OPUS — Bucle de Visión Reactivo + Automatización Visual Completa

**Proyecto:** sunny — orquestador de escritorio Windows 11 con IA local  
**Fecha:** 2026-05-07  
**Objetivo:** implementar la arquitectura que permita a Sunny ver la pantalla, razonar sobre lo que ve, actuar, y verificar el resultado — en bucle — hasta completar un objetivo complejo.

**Caso de prueba de referencia:** `sunny "abre factorio y empieza una partida"` debe funcionar sin que el usuario intervenga más.

---

## CONTEXTO DEL PROYECTO

### Stack técnico
- Python 3.11+, Windows 11
- Ollama local con `llama3.1:8b-instruct-q5_K_M`
- Rich para UI de consola, Pydantic para schemas, pytest para tests
- pyautogui para clicks/teclado, mss para capturas, pytesseract para OCR
- 534 tests passing antes de esta sesión

### Flujo actual (estático)
```
Usuario → Comprensión (LLM) → Plan JSON (LLM) → Validación → Ejecución → Reporte
```
El LLM planifica ANTES de ver la pantalla. Los pasos se ejecutan en orden fijo. Si algo no está donde se esperaba, falla sin recuperación.

### Lo que se necesita construir (flujo reactivo)
```
Usuario → Comprensión → Plan inicial → Ejecución con bucle reactivo:
  [captura pantalla] → [OCR texto real] → [LLM decide siguiente paso] → [ejecuta] → [captura] → repite
```
El LLM toma decisiones EN TIEMPO REAL basándose en lo que hay en pantalla, no en lo que supone que habrá.

---

## CONVENCIONES OBLIGATORIAS

Leer y seguir estas reglas sin excepción:

1. **4 sitios sincronizados:** cualquier acción nueva en un plugin debe estar en:
   - `sunny/modules/<plugin>.py` — implementación
   - `sunny/core/orchestrator/validator.py` — catálogo PLUGIN_CATALOG y ACTION_SIGNATURES
   - `sunny/core/prompts/system_v3.txt` — catálogo para el LLM (crear v3 basado en v2)
   - `sunny/core/orchestrator/reporter.py` — renderer del output

2. **Versionado de system prompts:** NO editar `system_v1.txt` ni `system_v2.txt`. Crear `system_v3.txt` basado en v2. Actualizar `loader.py` para que `"v3"` sea el default. `v1` y `v2` deben seguir cargando sus archivos originales.

3. **Tests ≤ 200 líneas por archivo.** Si un bloque de tests supera ese límite, crear un archivo nuevo (`test_vision_reactive.py`, `test_engine_reactive.py`, etc.).

4. **No añadir dependencias Python nuevas** sin documentarlas. Todo lo necesario ya está instalado: `pytesseract`, `mss`, `pillow`, `pyautogui`, `ollama`.

5. **delete siempre via send2trash**, nunca permanente.

6. **Doble confirmación:** comprensión + planes destructivos.

---

## ARQUITECTURA A IMPLEMENTAR

### Pieza 1: `vision.wait_for_screen_text` — nueva acción

La más importante. Permite esperar a que algo aparezca en pantalla antes de continuar.

**Archivo:** `sunny/modules/vision.py`

```python
def _wait_for_screen_text(
    self,
    text: str,
    timeout_sec: int = 30,
    interval_sec: float = 1.5,
    region: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Toma capturas periódicamente hasta que el texto aparece en pantalla o se agota el timeout.
    Devuelve cuánto tardó y si se encontró.
    """
    import time
    deadline = time.time() + timeout_sec
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        screenshot_data = self._screenshot(region)
        img = Image.open(screenshot_data["path"])
        ocr = pytesseract.image_to_data(img, lang="spa+eng", output_type=pytesseract.Output.DICT)
        found_words = [w for w in ocr["text"] if w and text.lower() in w.lower()]
        if found_words:
            return {
                "found": True,
                "text": text,
                "elapsed_sec": round(time.time() - (deadline - timeout_sec), 1),
                "attempts": attempts,
                "screenshot_path": screenshot_data["path"],
            }
        time.sleep(interval_sec)
    return {
        "found": False,
        "text": text,
        "elapsed_sec": timeout_sec,
        "attempts": attempts,
        "screenshot_path": screenshot_data["path"],
    }
```

Si `found=False` al terminar, el plugin NO lanza excepción — devuelve el resultado y el engine decide qué hacer. Esto es deliberado: permite que el plan continúe o que el agente loop decida replanificar.

Registrar en `self._actions["wait_for_screen_text"]`.

---

### Pieza 2: `vision.get_screen_state` — nueva acción (fast raw OCR)

Alias de `describe_screen(raw=True)`. Devuelve el mapa OCR por zonas sin pasar por LLM. Latencia ~1-2s. Es lo que el motor usa para inyectar contexto antes de cada step GUI.

```python
def _get_screen_state(
    self, region: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """
    OCR rápido de la pantalla dividido en zonas top/middle/bottom.
    Sin LLM. Para uso interno del engine y el planner.
    """
    import time
    t0 = time.perf_counter()
    screenshot_data = self._screenshot(region)
    img = Image.open(screenshot_data["path"])
    ocr_data = pytesseract.image_to_data(img, lang="spa+eng", output_type=pytesseract.Output.DICT)
    spatial_map = self._build_spatial_map(img, ocr_data)
    return {
        "screen_text": spatial_map,
        "screenshot_path": screenshot_data["path"],
        "latency_ms": int((time.perf_counter() - t0) * 1000),
    }
```

Registrar en `self._actions["get_screen_state"]`.

También añadir parámetro `raw: bool = False` a `_describe_screen`:
- Si `raw=True`: devolver `_get_screen_state()` directamente
- Si `raw=False`: flujo actual con LLM (comportamiento existente)

---

### Pieza 3: `AgentLoopEngine` — nuevo módulo

**Archivo nuevo:** `sunny/core/execution/agent_loop.py`

Este es el núcleo del cambio. Un segundo motor de ejecución que en lugar de ejecutar un plan estático, ejecuta un bucle agente: observa la pantalla, decide el siguiente paso, ejecuta, observa de nuevo.

```python
# sunny/core/execution/agent_loop.py

MAX_LOOP_STEPS = 20  # límite de seguridad — evita bucles infinitos

@dataclass
class AgentLoopResult:
    goal: str
    success: bool
    steps_executed: List[StepExecutionResult]
    total_latency_ms: int
    stopped_reason: str  # "goal_reached" | "max_steps" | "error" | "user_cancelled"
    final_screen_state: Optional[str] = None

def run_agent_loop(
    goal: str,
    registry: PluginRegistry,
    initial_action: Optional[Step] = None,
    context: Optional[Dict[str, Any]] = None,
    max_steps: int = MAX_LOOP_STEPS,
) -> AgentLoopResult:
    """
    Bucle agente visual:
    1. Toma screenshot → OCR
    2. Envía al LLM: goal + screen_state → decide siguiente acción
    3. Ejecuta la acción
    4. Repite hasta que el LLM declare "goal_reached" o se agote max_steps
    """
```

**System prompt del agente loop** (diferente al de planificación):
```
Eres el agente de acción de sunny. Recibes:
- OBJETIVO: lo que el usuario quiere conseguir
- ESTADO_PANTALLA: texto OCR extraído de la pantalla actual, dividido por zonas
- PASOS_EJECUTADOS: lista de lo que ya se ha hecho

Debes decidir LA PRÓXIMA ACCIÓN a ejecutar, en formato JSON:
{
  "plugin": "gui" | "vision" | "os_control" | "files",
  "action": "<nombre_de_acción>",
  "params": { ... },
  "reason": "explicación breve de por qué esta acción",
  "goal_reached": false
}

Si el objetivo ya está conseguido según el estado de pantalla, devuelve:
{
  "goal_reached": true,
  "reason": "explicación"
}

REGLAS:
- Usa SOLO acciones del catálogo. No inventes acciones.
- Si necesitas esperar a que cargue algo, usa vision.wait_for_screen_text
- Si necesitas saber dónde hacer click, primero vision.find_on_screen
- Si no ves progreso tras 3 pasos similares, declara goal_reached=false y para
- Máximo un paso por respuesta — no planifiques todo de golpe
```

**Catálogo disponible en el agente loop:**
- `gui`: click, click_on_text, type_text, press_key, scroll
- `vision`: get_screen_state, wait_for_screen_text, find_on_screen, screenshot
- `os_control`: open_app, sleep_seconds

---

### Pieza 4: integración en el engine existente

**Archivo:** `sunny/core/execution/engine.py`

Añadir inyección de screen state ANTES de cada step que involucre GUI. No es el bucle agente completo — es un enhancement del motor existente para que los steps GUI tengan contexto visual.

Añadir función `_inject_screen_context_if_needed(step, registry, context)`:
```python
def _inject_screen_context_if_needed(
    step: Step,
    registry: PluginRegistry,
    context: Dict[str, Any],
) -> None:
    """
    Si el step es de tipo gui o vision.find_on_screen,
    toma un get_screen_state y lo inyecta en context["screen_state"].
    El LLM puede usar este contexto en replanificaciones futuras.
    """
    GUI_STEPS = {"gui"}
    VISION_STEPS = {"find_on_screen", "click_on_text"}
    
    needs_context = (
        step.plugin in GUI_STEPS or
        (step.plugin == "vision" and step.action in VISION_STEPS)
    )
    if not needs_context:
        return
    
    vision_plugin = registry.get("vision")
    if vision_plugin is None:
        return
    
    result = vision_plugin.execute("get_screen_state", {}, context)
    if result.success:
        context["screen_state"] = result.data.get("screen_text", "")
        context["last_screenshot"] = result.data.get("screenshot_path", "")
```

Llamar a `_inject_screen_context_if_needed` al inicio de `_execute_step`, antes del thread.

---

### Pieza 5: nuevo intent `"agent_loop"` en el planner

**Archivo:** `sunny/core/models/plan.py`

Añadir `"agent_loop"` a `IntentType`:
```python
IntentType = Literal[
    "os_control", "files", "vision", "gui", "ai_bridge",
    "conversation", "agent_loop"  # nuevo
]
```

Un plan con `intent="agent_loop"` tiene un step especial:
```python
Step(
    step_id="loop_1",
    plugin="agent_loop",
    action="run",
    params={"goal": "abre factorio y empieza una partida", "max_steps": 15},
    timeout_sec=300,  # 5 minutos para tareas complejas
)
```

**Archivo:** `sunny/core/orchestrator/validator.py`

Añadir `"agent_loop"` a `PLUGIN_CATALOG`:
```python
"agent_loop": {"run"},
```

El engine detecta `step.plugin == "agent_loop"` y en lugar de buscar el plugin en el registry, llama directamente a `run_agent_loop()`.

---

### Pieza 6: system_v3.txt — catálogo actualizado

Crear `sunny/core/prompts/system_v3.txt` basado en v2 con:

**Nuevas acciones en `## vision`:**
```
- get_screen_state(region: object | null) — LIBRE (OCR rápido ~1-2s, devuelve texto de pantalla por zonas sin LLM)
- wait_for_screen_text(text: str, timeout_sec: int, interval_sec: float) — LIBRE (espera hasta que el texto aparece en pantalla, timeout por defecto 30s)
```

**Nuevo plugin `## agent_loop`:**
```
## agent_loop
- run(goal: str, max_steps: int) — LIBRE (bucle agente visual: observa pantalla, decide acciones, ejecuta hasta completar el objetivo)
  Usar cuando el objetivo requiere múltiples interacciones visuales con una aplicación cuyo estado
  no se conoce de antemano. Ejemplos: navegar menús de un juego, rellenar formularios complejos,
  operar aplicaciones con estados dinámicos.
```

**Few-shots nuevos a añadir:**
```
---
Usuario: "abre factorio y empieza una partida nueva"
[FASE: COMPRENSIÓN]
{"comprehension":"Abrir Factorio via Steam y navegar el menú para iniciar una partida nueva","intent":"agent_loop","assumptions":["Factorio instalado via Steam","URI steam://rungameid/427520 disponible"],"confidence":0.85,"needs_clarification":false}
[FASE: PLANIFICACIÓN]
{"intent":"agent_loop","confidence":0.85,"needs_clarification":false,"requires_confirmation":false,"steps":[{"step_id":"s1","plugin":"os_control","action":"open_app","params":{"app":"steam://rungameid/427520"},"timeout_sec":10,"continue_on_error":false,"depends_on":[]},{"step_id":"s2","plugin":"vision","action":"wait_for_screen_text","params":{"text":"PLAY","timeout_sec":60,"interval_sec":2.0},"timeout_sec":65,"continue_on_error":false,"depends_on":["s1"]},{"step_id":"s3","plugin":"agent_loop","action":"run","params":{"goal":"Iniciar una partida nueva en Factorio. Hacer click en el menú principal para empezar a jugar.","max_steps":10},"timeout_sec":120,"continue_on_error":false,"depends_on":["s2"]}]}
---
Usuario: "espera a que cargue Chrome y luego busca el tiempo en Madrid"
[FASE: COMPRENSIÓN]
{"comprehension":"Abrir Chrome, esperar a que cargue, y buscar el tiempo en Madrid","intent":"gui","assumptions":["Chrome instalado"],"confidence":0.9,"needs_clarification":false}
[FASE: PLANIFICACIÓN]
{"intent":"gui","confidence":0.9,"needs_clarification":false,"requires_confirmation":false,"steps":[{"step_id":"s1","plugin":"os_control","action":"open_app","params":{"app":"chrome"},"timeout_sec":10,"continue_on_error":false,"depends_on":[]},{"step_id":"s2","plugin":"vision","action":"wait_for_screen_text","params":{"text":"Google","timeout_sec":20,"interval_sec":1.5},"timeout_sec":25,"continue_on_error":false,"depends_on":["s1"]},{"step_id":"s3","plugin":"gui","action":"type_text","params":{"text":"tiempo en Madrid"},"timeout_sec":10,"continue_on_error":false,"depends_on":["s2"]},{"step_id":"s4","plugin":"gui","action":"press_key","params":{"key":"enter"},"timeout_sec":10,"continue_on_error":false,"depends_on":["s3"]}]}
---
Usuario: "mira la pantalla y dime qué hay de forma rápida"
[FASE: COMPRENSIÓN]
{"comprehension":"Captura rápida del estado actual de la pantalla","intent":"vision","assumptions":[],"confidence":0.98,"needs_clarification":false}
[FASE: PLANIFICACIÓN]
{"intent":"vision","confidence":0.98,"needs_clarification":false,"requires_confirmation":false,"steps":[{"step_id":"s1","plugin":"vision","action":"get_screen_state","params":{"region":null},"timeout_sec":10,"continue_on_error":false,"depends_on":[]}]}
```

---

### Pieza 7: reporter — renderers nuevos

**Archivo:** `sunny/core/orchestrator/reporter.py`

Añadir en `_render_semantic_output`:
```python
elif plugin == "vision" and action == "wait_for_screen_text":
    _render_wait_for_screen_text(data)
elif plugin == "vision" and action == "get_screen_state":
    _render_get_screen_state(data)
elif plugin == "agent_loop" and action == "run":
    _render_agent_loop_result(data)
```

Implementar:

**`_render_wait_for_screen_text(data)`:**
- Si `found=True`: panel verde `✔ Texto encontrado: "{text}" — {elapsed_sec}s / {attempts} intentos`
- Si `found=False`: panel amarillo `⚠ Texto "{text}" no apareció en {elapsed_sec}s ({attempts} intentos)`

**`_render_get_screen_state(data)`:**
- Panel simple con el `screen_text` sin cabecera elaborada (es output rápido/interno)

**`_render_agent_loop_result(data)`:**
- Tabla de pasos ejecutados en el bucle (similar a la tabla de ejecución principal)
- Razón de parada: `goal_reached` / `max_steps` / `error`

---

## ARCHIVOS A CREAR/MODIFICAR

```
CREAR:
  sunny/core/execution/agent_loop.py         ← AgentLoopEngine + run_agent_loop()
  sunny/core/prompts/system_v3.txt           ← clon de v2 + nuevas acciones + few-shots
  tests/test_agent_loop.py                   ← tests del bucle agente
  tests/modules/test_vision_reactive.py      ← tests de wait_for_screen_text y get_screen_state

MODIFICAR:
  sunny/modules/vision.py                    ← añadir wait_for_screen_text, get_screen_state, raw en describe_screen
  sunny/core/models/plan.py                  ← añadir "agent_loop" a IntentType
  sunny/core/execution/engine.py             ← screen context injection + detección de agent_loop steps
  sunny/core/orchestrator/validator.py       ← agent_loop en PLUGIN_CATALOG, vision nuevas acciones
  sunny/core/orchestrator/reporter.py        ← renderers para nuevas acciones
  sunny/core/prompts/loader.py               ← default cambia a "v3"
```

---

## TESTS REQUERIDOS

### `tests/modules/test_vision_reactive.py`

```
test_wait_for_screen_text_finds_text_immediately
test_wait_for_screen_text_finds_text_after_retries
test_wait_for_screen_text_returns_not_found_on_timeout
test_wait_for_screen_text_returns_attempts_count
test_wait_for_screen_text_does_not_raise_on_timeout
test_get_screen_state_returns_spatial_map_and_path
test_get_screen_state_latency_ms_present
test_describe_screen_raw_true_skips_llm
test_describe_screen_raw_false_calls_llm_as_before
```

### `tests/test_agent_loop.py`

```
test_run_agent_loop_reaches_goal_in_one_step
test_run_agent_loop_reaches_goal_after_multiple_steps
test_run_agent_loop_stops_at_max_steps
test_run_agent_loop_stops_on_error
test_run_agent_loop_returns_all_executed_steps
test_run_agent_loop_sends_screen_state_to_llm
test_run_agent_loop_sends_executed_steps_to_llm
test_agent_loop_system_prompt_contains_goal
test_agent_loop_result_has_stopped_reason
test_agent_loop_handles_llm_timeout_gracefully
```

### `tests/test_engine.py` (añadir al archivo existente)

```
test_engine_injects_screen_context_for_gui_steps
test_engine_skips_screen_context_for_file_steps
test_engine_executes_agent_loop_step_via_run_agent_loop
```

### Validator y prompts

```
test_validator_accepts_agent_loop_run
test_validator_accepts_wait_for_screen_text
test_validator_accepts_get_screen_state
test_system_v3_contains_wait_for_screen_text
test_system_v3_contains_get_screen_state
test_system_v3_contains_agent_loop_section
test_system_v3_default_prompt
test_v2_unchanged_after_v3_creation
```

---

## SYSTEM PROMPT DEL AGENTE LOOP (completo)

Este es el prompt que usa `run_agent_loop()` internamente para cada iteración. NO va en `system_v3.txt` (ese es para comprensión/planificación). Va hardcodeado en `agent_loop.py` o en un archivo `system_agent_loop_v1.txt` en `sunny/core/prompts/`.

```
Eres el agente de ejecución visual de sunny.

En cada turno recibes:
- OBJETIVO: lo que el usuario quiere conseguir
- PANTALLA_ACTUAL: texto OCR de la pantalla dividido en zonas (top/middle/bottom)
- HISTORIAL: lista de acciones ya ejecutadas

Tu tarea: decidir LA SIGUIENTE ACCIÓN a ejecutar. Una sola acción por respuesta.

RESPONDE SIEMPRE con este JSON (sin texto adicional):
{
  "plugin": "gui" | "vision" | "os_control",
  "action": "<acción>",
  "params": { ... },
  "reason": "<por qué esta acción>",
  "goal_reached": false
}

O si el objetivo está conseguido:
{
  "goal_reached": true,
  "reason": "<qué evidencia en pantalla confirma que el objetivo está completo>"
}

ACCIONES DISPONIBLES:
gui.click_on_text(text) — hace click en el texto visible en pantalla
gui.click(x, y) — click en coordenadas
gui.press_key(key) — presiona tecla (ej: "enter", "escape", "ctrl+c")
gui.type_text(text) — escribe texto
gui.scroll(direction, amount) — scroll "up" o "down"
vision.find_on_screen(target) — localiza texto y devuelve coordenadas
vision.get_screen_state() — captura OCR rápido del estado actual
vision.wait_for_screen_text(text, timeout_sec) — espera hasta que el texto aparezca
os_control.sleep_seconds(seconds) — pausa antes de la siguiente acción

REGLAS:
1. Solo usa acciones de la lista anterior. Nunca inventes acciones.
2. Si la pantalla muestra texto de carga o transición, usa wait_for_screen_text antes de hacer click.
3. Si el texto que buscas no está en pantalla, usa get_screen_state para actualizar tu vista antes de tomar decisiones.
4. Si llevas 3 acciones consecutivas iguales sin progreso, declara goal_reached: true y explica que no fue posible completar el objetivo.
5. Para navegar menús: haz click en el texto exacto que ves, no en lo que supones que debería estar.
6. Sé conservador: si no estás seguro de qué hacer, usa get_screen_state para ver el estado actual antes de actuar.
```

---

## CASO DE USO DE REFERENCIA — VERIFICACIÓN FINAL

Cuando todo esté implementado, este comando debe funcionar:

```
sunny --yes --new-session "abre factorio y empieza una partida nueva"
```

Flujo esperado:
1. Comprensión → intent: agent_loop
2. Plan: [open_app("steam://rungameid/427520"), wait_for_screen_text("PLAY", 60s), agent_loop.run(goal="...", max_steps=10)]
3. Step 1: abre Factorio via Steam
4. Step 2: espera hasta que el menú principal carga (texto "PLAY" visible)
5. Step 3: bucle agente
   - get_screen_state → ve "PLAY" "SETTINGS" "QUIT"
   - click_on_text("PLAY")
   - wait_for_screen_text("New Game", 15s)
   - click_on_text("New Game") o equivalente según lo que aparezca
   - wait_for_screen_text("Generate", 10s)
   - click_on_text("Generate")
   - get_screen_state → verifica que estamos en el juego → goal_reached: true
6. Reporte: tabla con todos los pasos, latencia total, confirmación de éxito

---

## LÍMITES Y CONSIDERACIONES

- **MAX_LOOP_STEPS = 20** — límite de seguridad fijo, no configurable desde el plan
- **El bucle agente NO pide confirmación** en cada step — el usuario aprobó el objetivo completo al inicio
- **Si el LLM agente genera JSON inválido**, reintentar máximo 2 veces, luego parar con `stopped_reason="error"`
- **timeout total del agente loop**: respetar el `timeout_sec` del step (default 300s para tareas complejas)
- **El agente loop no tiene acceso a `files`**: solo `gui`, `vision`, `os_control`. La manipulación de archivos sigue siendo del flujo estático normal
- **Compatibilidad hacia atrás**: el engine existente no cambia su comportamiento para planes normales (intent ≠ agent_loop). Solo añadimos la inyección de screen context como enhancement opcional

---

## RESULTADO ESPERADO DE PYTEST

```
pytest --tb=short -q
??? passed in ~30s   ← debe ser > 534, 0 failing
```

Mínimo esperado: 534 tests previos + ~35 tests nuevos = ~570 tests, todos verdes.

---

## NOTAS FINALES PARA OPUS

- Usa los archivos en `C:\Proyectos\sunny\` — el entorno virtual está en `.venv\`
- Lee `HANDOFF_20260507.md` para el estado exacto antes de empezar
- Lee `sunny/core/execution/engine.py` completo antes de modificarlo
- Lee `sunny/brain/ollama_client.py` para entender `call_llm` y `call_llm_validated`
- Lee `sunny/core/prompts/system_v2.txt` completo antes de crear v3
- La inyección de screen context en el engine es OPCIONAL por step — no añade latencia a steps que no son GUI
- El agente loop usa `call_llm_validated` con un schema Pydantic para parsear la respuesta de cada iteración
- Prioridad de implementación: (1) vision nuevas acciones, (2) agent_loop.py, (3) integración engine, (4) system_v3, (5) reporter, (6) tests
