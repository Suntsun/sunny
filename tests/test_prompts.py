import re
import pytest
from sunny.core.prompts import loader
from sunny.core.models.plan import PlanV2, ComprehensionResult


def test_load_v1_returns_non_empty_string():
    c = loader.load_system_prompt("v1")
    assert isinstance(c, str)
    assert len(c) > 200


def test_load_caches_by_version():
    a = loader.load_system_prompt("v1")
    b = loader.load_system_prompt("v1")
    assert a is b


def test_load_invalid_version_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        loader.load_system_prompt("v999")


def test_reset_cache_forces_reread(tmp_path, monkeypatch):
    p = tmp_path / "system_v1.txt"
    p.write_text("uno", encoding="utf-8")
    monkeypatch.setattr(loader, "_PROMPTS_DIR", tmp_path)
    loader._reset_cache()
    assert loader.load_system_prompt("v1") == "uno"
    p.write_text("dos", encoding="utf-8")
    loader._reset_cache()
    assert loader.load_system_prompt("v1") == "dos"


def test_v1_contains_role_section():
    assert "# ROL Y MISIÓN" in loader.load_system_prompt("v1")


def test_v1_contains_comprehension_schema():
    assert "FASE COMPRENSIÓN" in loader.load_system_prompt("v1")


def test_v1_contains_planning_schema():
    assert "FASE PLANIFICACIÓN" in loader.load_system_prompt("v1")


def test_v1_contains_security_rules():
    assert "SEGURIDAD" in loader.load_system_prompt("v1")


def test_v1_contains_three_few_shot_examples():
    assert loader.load_system_prompt("v1").count("---") >= 2


def test_v1_lists_all_six_intents():
    c = loader.load_system_prompt("v1")
    for i in ["os_control", "files", "vision", "gui", "ai_bridge", "conversation"]:
        assert i in c


def test_v1_no_elipsis_in_examples():
    assert "..." not in loader.load_system_prompt("v1")


def test_v1_contains_plugin_catalog():
    c = loader.load_system_prompt("v1")
    assert "CATÁLOGO DE PLUGINS" in c
    for p in ["files", "os_control", "vision", "gui", "ai_bridge"]:
        assert p in c


def test_v1_lists_known_actions():
    c = loader.load_system_prompt("v1")
    for a in ["read_file", "write_file", "delete", "open_app", "screenshot", "click", "type_text", "ask_external"]:
        assert a in c


def test_v1_contains_security_tiers():
    c = loader.load_system_prompt("v1")
    assert "PROHIBIDO" in c
    assert "CONFIRMACIÓN OBLIGATORIA" in c
    assert "LIBRE" in c


def test_v1_contains_confidence_calibration():
    c = loader.load_system_prompt("v1")
    assert "CALIBRACIÓN DE CONFIDENCE" in c
    assert "0.95" in c


def test_v1_contains_session_context_section():
    assert "CONTEXTO DE SESIÓN" in loader.load_system_prompt("v1")


def test_v1_contains_eight_few_shot_examples():
    assert loader.load_system_prompt("v1").count("---") >= 7


def test_v1_forbids_markdown_fences():
    c = loader.load_system_prompt("v1")
    assert "Prohibido" in c and "markdown" in c.lower()


def test_v1_few_shot_jsons_parse_to_pydantic():
    """
    Solo valida los JSON dentro de la sección # EJEMPLOS FEW-SHOT.
    Solo captura líneas que son JSON compacto completo (empiezan con `{"` y terminan con `}`).
    """
    c = loader.load_system_prompt("v1")
    assert "# EJEMPLOS FEW-SHOT" in c, "Falta sección de few-shot"
    few_shot = c.split("# EJEMPLOS FEW-SHOT", 1)[1]

    json_lines = re.findall(r'^\{".*\}$', few_shot, re.MULTILINE)

    assert len(json_lines) >= 16, (
        f"Esperaba >= 16 JSONs (8 ejemplos x 2 fases), "
        f"encontrados {len(json_lines)}"
    )

    for j in json_lines:
        ok = False
        try:
            ComprehensionResult.model_validate_json(j)
            ok = True
        except Exception:
            try:
                PlanV2.model_validate_json(j)
                ok = True
            except Exception:
                pass
        assert ok, f"JSON inválido en few-shot: {j}"


# ---------------------------------------------------------------------------
# Tests para system_v2 (visión multimodal)
# ---------------------------------------------------------------------------


def test_load_system_prompt_v2_loads():
    c = loader.load_system_prompt("v2")
    assert isinstance(c, str)
    assert len(c) > 200


def test_load_system_prompt_v2_contains_describe_screen():
    c = loader.load_system_prompt("v2")
    assert "describe_screen" in c


def test_load_system_prompt_v2_contains_analyze_screen():
    c = loader.load_system_prompt("v2")
    assert "analyze_screen" in c


def test_load_system_prompt_v2_keeps_v1_actions():
    c = loader.load_system_prompt("v2")
    for a in [
        "read_file", "write_file", "delete", "open_app",
        "screenshot", "click", "type_text", "ask_external",
    ]:
        assert a in c


def test_default_version_is_v3():
    """El default de load_system_prompt debe ser v3 tras la fase de visión reactiva."""
    default_content = loader.load_system_prompt()
    v3_content = loader.load_system_prompt("v3")
    assert default_content == v3_content


def test_system_v3_default_prompt():
    """Verifica explícitamente que cargar sin argumentos devuelve v3."""
    assert loader.load_system_prompt() == loader.load_system_prompt("v3")


def test_system_v3_contains_wait_for_screen_text():
    c = loader.load_system_prompt("v3")
    assert "wait_for_screen_text" in c


def test_system_v3_contains_get_screen_state():
    c = loader.load_system_prompt("v3")
    assert "get_screen_state" in c


def test_system_v3_contains_agent_loop_section():
    c = loader.load_system_prompt("v3")
    assert "## agent_loop" in c
    assert "agent_loop" in c
    assert '"intent":"agent_loop"' in c


def test_v2_unchanged_after_v3_creation():
    """v2 debe seguir cargando exactamente igual; las acciones nuevas NO aparecen en v2."""
    c2 = loader.load_system_prompt("v2")
    assert "wait_for_screen_text" not in c2
    assert "get_screen_state" not in c2
    assert "## agent_loop" not in c2
    assert "# ROL Y MISIÓN" in c2
    assert "describe_screen" in c2
    assert "analyze_screen" in c2


def test_v3_keeps_all_v2_actions():
    c = loader.load_system_prompt("v3")
    for a in [
        "read_file", "write_file", "delete", "open_app",
        "screenshot", "click", "type_text", "ask_external",
        "describe_screen", "analyze_screen",
    ]:
        assert a in c


def test_system_v1_unchanged():
    """v1 debe seguir cargando exactamente igual; describe_screen/analyze_screen NO aparecen en v1."""
    c1 = loader.load_system_prompt("v1")
    assert "describe_screen" not in c1
    assert "analyze_screen" not in c1
    # Sigue conteniendo las secciones obligatorias originales
    assert "# ROL Y MISIÓN" in c1
    assert "FASE COMPRENSIÓN" in c1
    assert "FASE PLANIFICACIÓN" in c1


def test_v2_few_shot_describe_screen_example():
    c = loader.load_system_prompt("v2")
    assert "# EJEMPLOS FEW-SHOT" in c
    few_shot = c.split("# EJEMPLOS FEW-SHOT", 1)[1]
    # Debe haber al menos un ejemplo con describe_screen y otro con analyze_screen
    assert '"action":"describe_screen"' in few_shot
    assert '"action":"analyze_screen"' in few_shot


def test_v2_few_shot_jsons_parse_to_pydantic():
    c = loader.load_system_prompt("v2")
    assert "# EJEMPLOS FEW-SHOT" in c
    few_shot = c.split("# EJEMPLOS FEW-SHOT", 1)[1]

    json_lines = re.findall(r'^\{".*\}$', few_shot, re.MULTILINE)
    assert len(json_lines) >= 18, (
        f"Esperaba >= 18 JSONs en v2 (v1 tenía 16; v2 añade 2 ejemplos x 2 fases), "
        f"encontrados {len(json_lines)}"
    )

    for j in json_lines:
        ok = False
        try:
            ComprehensionResult.model_validate_json(j)
            ok = True
        except Exception:
            try:
                PlanV2.model_validate_json(j)
                ok = True
            except Exception:
                pass
        assert ok, f"JSON inválido en few-shot v2: {j}"


def test_v2_intent_consistency_in_examples():
    c = loader.load_system_prompt("v2")
    assert "# EJEMPLOS FEW-SHOT" in c
    few_shot = c.split("# EJEMPLOS FEW-SHOT", 1)[1]

    blocks = few_shot.split("---")
    pairs = 0
    for b in blocks:
        json_lines = re.findall(r'^\{".*\}$', b, re.MULTILINE)
        if len(json_lines) >= 2:
            cr = ComprehensionResult.model_validate_json(json_lines[0])
            pl = PlanV2.model_validate_json(json_lines[1])
            assert cr.intent == pl.intent, (
                f"intent inconsistente en v2: comprensión={cr.intent}, plan={pl.intent}"
            )
            pairs += 1
    assert pairs >= 9, f"Esperaba >= 9 pares en v2, encontrados {pairs}"


def test_v1_intent_consistency_in_examples():
    """
    Para cada bloque de few-shot, el intent de Comprensión debe coincidir
    con el de Planificación.
    """
    c = loader.load_system_prompt("v1")
    assert "# EJEMPLOS FEW-SHOT" in c
    few_shot = c.split("# EJEMPLOS FEW-SHOT", 1)[1]

    blocks = few_shot.split("---")
    pairs = 0
    for b in blocks:
        json_lines = re.findall(r'^\{".*\}$', b, re.MULTILINE)
        if len(json_lines) >= 2:
            cr = ComprehensionResult.model_validate_json(json_lines[0])
            pl = PlanV2.model_validate_json(json_lines[1])
            assert cr.intent == pl.intent, (
                f"intent inconsistente: comprensión={cr.intent}, plan={pl.intent}"
            )
            pairs += 1

    assert pairs >= 7, f"Esperaba >= 7 pares válidos, encontrados {pairs}"
