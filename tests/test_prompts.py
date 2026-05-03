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
