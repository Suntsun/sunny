# BRIEFING OPUS — Bucle de Visión Reactivo para sunny

**Fecha:** 2026-05-06  
**Contexto:** Sesión de implementación — Claude Sonnet orquesta, Opus diseña e implementa

---

## CONTEXTO DEL PROYECTO

`sunny` es un orquestador de automatización de escritorio para Windows 11. El usuario escribe órdenes en lenguaje natural, un LLM local (llama3.1:8b via Ollama) las convierte en un plan JSON con pasos, y el sistema los ejecuta mediante plugins.

**Stack:** Python 3.11+, Ollama (local), Rich para UI, Pydantic para schemas, pytest para tests.

**Plugins activos:** `files`, `os_control`, `vision`, `gui`, `ai_bridge` (stub).

**Convención crítica de 4 sitios:** cada acción de un plugin debe estar sincronizada en:
1. `sunny/modules/<plugin>.py` — implementación
2. `sunny/core/orchestrator/validator.py` — catálogo de acciones válidas
3. `sunny/core/prompts/system_v1.txt` — catálogo para el LLM
4. `sunny/core/orchestrator/reporter.py` — renderer semántico del output

---

## PROBLEMA A RESOLVER

Hoy sunny planifica **a ciegas**: el LLM decide qué hacer sin saber qué hay en pantalla.

Ejemplo fallido:
```
sunny "abre factorio y abre una partida"
→ Paso 1: open_app("factorio") → FALLA (no es ejecutable estándar)
→ Paso 2: gui.click_on_text("Play") → OMITIDO
```

Incluso si abriera el juego, el LLM no puede saber qué aparece en pantalla para decidir qué hacer.

**Lo que necesita:** un bucle de visión reactivo.

```
Usuario → [captura pantalla] → LLM VE la pantalla → planifica → ejecuta → [captura] → replantea
```

---

## SOLUCIÓN A IMPLEMENTAR (Fase 1 — esta sesión)

### Capacidad nueva: `vision.describe_screen` y `vision.analyze_screen`

Dos nuevas acciones en el plugin `vision` que usan un modelo **multimodal** (llava via Ollama) para entender visualmente la pantalla.

#### `describe_screen(region=None)`
- Toma screenshot
- Envía la imagen a llava con prompt: "Describe detalladamente qué ves en esta pantalla. Lista los elementos de UI visibles, textos, botones, menús y el estado general de la aplicación."
- Devuelve `{"description": "...", "screenshot_path": "..."}`

#### `analyze_screen(question: str, region=None)`
- Toma screenshot
- Envía la imagen a llava con la pregunta específica del usuario
- Devuelve `{"answer": "...", "question": "...", "screenshot_path": "..."}`

---

## ARCHIVOS A MODIFICAR

### 1. `sunny/brain/ollama_client.py`

Añadir función `call_llm_vision` que:
- Recibe: `image_path: str`, `prompt: str`, `model: str = "llava"`, `timeout_sec: int = 60`
- Codifica la imagen en base64
- Llama a `ollama.Client.chat` con `images=[base64_string]` en el mensaje (Ollama multimodal API)
- Devuelve `Tuple[str, LLMCallStats]` — igual que `call_llm`
- Si el modelo no soporta imágenes o falla, lanza `LLMError` descriptivo

```python
# Ollama multimodal API:
response = client.chat(
    model=model,
    messages=[{
        "role": "user",
        "content": prompt,
        "images": [base64_image_string]  # sin prefijo data:image/...
    }],
    options={"temperature": 0.1, "num_predict": 1024}
)
```

La imagen debe codificarse como base64 puro (sin data URI prefix).

### 2. `sunny/modules/vision.py`

Añadir dos métodos al `VisionPlugin`:

```python
def _describe_screen(self, region=None) -> Dict[str, Any]:
    screenshot_data = self._screenshot(region)
    from sunny.brain.ollama_client import call_llm_vision
    prompt = (
        "Describe detalladamente qué ves en esta pantalla. "
        "Lista los elementos de UI visibles, textos, botones, menús "
        "y el estado general de la aplicación en pantalla."
    )
    description, stats = call_llm_vision(
        image_path=screenshot_data["path"],
        prompt=prompt,
    )
    return {
        "description": description,
        "screenshot_path": screenshot_data["path"],
        "model_used": "llava",
        "tokens_out": stats.tokens_out,
        "latency_ms": stats.latency_ms,
    }

def _analyze_screen(self, question: str, region=None) -> Dict[str, Any]:
    screenshot_data = self._screenshot(region)
    from sunny.brain.ollama_client import call_llm_vision
    answer, stats = call_llm_vision(
        image_path=screenshot_data["path"],
        prompt=question,
    )
    return {
        "answer": answer,
        "question": question,
        "screenshot_path": screenshot_data["path"],
        "model_used": "llava",
        "tokens_out": stats.tokens_out,
        "latency_ms": stats.latency_ms,
    }
```

Registrar ambos en `self._actions`:
```python
"describe_screen": self._describe_screen,
"analyze_screen": self._analyze_screen,
```

### 3. `sunny/core/orchestrator/validator.py`

Localizar el catálogo del plugin `vision` y añadir las dos acciones nuevas:
```python
"vision": {
    "screenshot": ...,
    "read_screen_text": ...,
    "find_on_screen": ...,
    "describe_screen": [...],   # nuevo — sin params obligatorios, region opcional
    "analyze_screen": ["question"],  # nuevo — question obligatorio
}
```

Examina el formato exacto del validator antes de editar para respetar la estructura.

### 4. `sunny/core/prompts/system_v1.txt`

En la sección `## vision` del CATÁLOGO DE PLUGINS, añadir:
```
- describe_screen(region: object | null) — LIBRE (toma screenshot y describe con IA qué hay en pantalla)
- analyze_screen(question: str, region: object | null) — LIBRE (toma screenshot y responde una pregunta específica sobre lo que hay en pantalla)
```

Añadir al final de la sección FEW-SHOT un ejemplo:
```
---
Usuario: "mira la pantalla y dime qué aplicación está abierta"
[FASE: COMPRENSIÓN]
{"comprehension":"Capturar pantalla y describir qué aplicación o contenido está visible","intent":"vision","assumptions":[],"confidence":0.95,"needs_clarification":false}
[FASE: PLANIFICACIÓN]
{"intent":"vision","confidence":0.95,"needs_clarification":false,"requires_confirmation":false,"steps":[{"step_id":"s1","plugin":"vision","action":"describe_screen","params":{"region":null},"timeout_sec":60,"continue_on_error":false,"depends_on":[]}]}
---
Usuario: "¿qué botones hay en la pantalla ahora mismo?"
[FASE: COMPRENSIÓN]
{"comprehension":"Analizar pantalla actual e identificar botones visibles","intent":"vision","assumptions":[],"confidence":0.95,"needs_clarification":false}
[FASE: PLANIFICACIÓN]
{"intent":"vision","confidence":0.95,"needs_clarification":false,"requires_confirmation":false,"steps":[{"step_id":"s1","plugin":"vision","action":"analyze_screen","params":{"question":"¿Qué botones son visibles en esta pantalla?","region":null},"timeout_sec":60,"continue_on_error":false,"depends_on":[]}]}
```

**IMPORTANTE:** system_v1.txt está versionado. NO editar el archivo existente. Crear `system_v2.txt` basado en v1 con las adiciones. Actualizar `sunny/core/prompts/loader.py` para que `load_system_prompt("v2")` sea la versión activa y `"v1"` siga cargando el original. Actualizar `sunny/cli.py` si hardcodea la versión.

### 5. `sunny/core/orchestrator/reporter.py`

Añadir renderers para las dos acciones nuevas:

```python
elif plugin == "vision" and action == "describe_screen":
    _render_describe_screen(data)
elif plugin == "vision" and action == "analyze_screen":
    _render_analyze_screen(data)
```

Implementar `_render_describe_screen(data)`: panel Rich con la descripción y path del screenshot.
Implementar `_render_analyze_screen(data)`: panel Rich con pregunta + respuesta y path del screenshot.

---

## ESTRUCTURA DE ARCHIVOS CLAVE (rutas reales)

```
sunny/
├── brain/
│   └── ollama_client.py          ← añadir call_llm_vision()
├── modules/
│   └── vision.py                 ← añadir describe_screen, analyze_screen
├── core/
│   ├── orchestrator/
│   │   ├── validator.py          ← añadir acciones al catálogo vision
│   │   └── reporter.py          ← añadir renderers
│   └── prompts/
│       ├── loader.py            ← actualizar para v2
│       ├── system_v1.txt        ← NO TOCAR
│       └── system_v2.txt        ← CREAR (basado en v1 + nuevas acciones)
```

---

## CONVENCIONES OBLIGATORIAS

1. **Versionado de system prompts:** NUNCA editar `system_v1.txt`. Crear `system_v2.txt` y actualizarlo en `loader.py`.

2. **4 sitios sincronizados:** cualquier acción nueva en `vision.py` debe aparecer también en `validator.py`, `system_v2.txt` y `reporter.py`.

3. **No añadir dependencias nuevas sin aprobar.** `llava` es un modelo de Ollama, no una librería Python. No se necesitan paquetes nuevos — `ollama` ya está instalado (v0.6.1). El `base64` de la stdlib es suficiente.

4. **Timeout de visión:** las llamadas a llava son lentas. Usar `timeout_sec=60` para `describe_screen` y `analyze_screen` en los steps del planner, no 30.

5. **Tests:** mantener bloques ≤ 200 líneas. Si los tests de vision superan ese límite, dividir en `tests/modules/test_vision.py` (ya existe) y `tests/modules/test_vision_llava.py`.

---

## TESTS REQUERIDOS

Para cada función nueva, tests con monkeypatch que eviten llamadas reales a Ollama/llava:

### `call_llm_vision` (en `ollama_client.py`):
- `test_call_llm_vision_encodes_image_as_base64` — mock del client, verificar que el mensaje tiene `images`
- `test_call_llm_vision_returns_content_and_stats`
- `test_call_llm_vision_raises_on_timeout`

### `describe_screen` (en `vision.py`):
- `test_describe_screen_calls_screenshot_and_vision_llm` — mock `_screenshot` + `call_llm_vision`
- `test_describe_screen_returns_description_and_path`
- `test_describe_screen_plugin_result_success`

### `analyze_screen`:
- `test_analyze_screen_sends_question_to_llm`
- `test_analyze_screen_returns_answer_and_question`
- `test_analyze_screen_missing_question_raises`

### Reporter:
- `test_render_describe_screen_shows_description`
- `test_render_analyze_screen_shows_question_and_answer`

### system_v2.txt:
- `test_load_system_prompt_v2_contains_describe_screen`
- `test_load_system_prompt_v2_contains_analyze_screen`
- `test_system_v1_unchanged` — verificar que v1 sigue cargando igual que antes

---

## ESTADO ACTUAL DE LA SUITE

**500 tests, 0 fallos** antes de esta sesión.

El modelo llava puede no estar instalado en Ollama del usuario. Los tests deben mockear las llamadas. En producción, si llava no está disponible, `describe_screen` debe devolver un error descriptivo: "Modelo llava no disponible. Instálalo con: `ollama pull llava`".

---

## MODELO LLAVA — NOTA TÉCNICA

Ollama soporta modelos multimodales. La API de chat acepta imágenes así:

```python
import base64

with open(image_path, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode("utf-8")

response = client.chat(
    model="llava",
    messages=[{
        "role": "user",
        "content": prompt,
        "images": [img_b64]
    }],
    options={"temperature": 0.1, "num_predict": 1024}
)
content = response["message"]["content"]
```

Modelos alternativos si llava no está disponible: `llava:7b`, `moondream`, `bakllava`.

---

## CHECKLIST DE ENTREGA

- [ ] `call_llm_vision` en `ollama_client.py` — funciona con mock y con llava real
- [ ] `describe_screen` y `analyze_screen` en `vision.py`
- [ ] `validator.py` actualizado con las 2 nuevas acciones
- [ ] `system_v2.txt` creado con catálogo actualizado + few-shots nuevos
- [ ] `loader.py` actualizado para usar v2 por defecto
- [ ] `reporter.py` con renderers para ambas acciones
- [ ] Tests escritos y verdes
- [ ] `pytest --tb=short -q` → 0 fallos
- [ ] Smoke test manual: `sunny "mira la pantalla y dime qué ves"` → descripción de llava visible en terminal

---

## LO QUE NO ESTÁ EN SCOPE HOY (Fase 2)

- Replanificación mid-ejecución basada en screen state
- Inyección automática de screenshot al inicio de cada comando
- Steam library scanner para juegos
- Loop reactivo completo (screenshot → decide → actúa → screenshot → replantea)

Eso queda como DEP para la siguiente sesión.
