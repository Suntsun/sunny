"""
100 smoke tests para Sunny — cobertura del pipeline completo.

Grupos:
  A. Modelos (plan.py)              – 15 tests
  B. Ollama client helpers           –  8 tests
  C. Comprensión (prompts/LLM)       –  6 tests
  D. Planificación (prompts/LLM)     –  5 tests
  E. Validador                       – 15 tests
  F. Motor de ejecución (engine)     – 14 tests
  G. Plugin files                    – 10 tests
  H. Plugin os_control               –  8 tests
  I. Plugin gui                      –  7 tests
  J. Memoria SQLite                  – 12 tests
  K. Mejoras aplicadas               –  3 tests
Total: 103 tests nominales (+ 3 parametrized de C-03 = 106 colectados)
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict

import pytest

# ─────────────────────────── FACTORIES COMPARTIDOS ───────────────────────────

def _comp_llm_response(intent="files", confidence=0.9, needs_clarification=False):
    return {
        "message": {"content": json.dumps({
            "comprehension": "Entendido",
            "intent": intent,
            "assumptions": [],
            "confidence": confidence,
            "needs_clarification": needs_clarification,
        })},
        "prompt_eval_count": 10,
        "eval_count": 5,
    }


def _plan_llm_response(
    intent="files",
    plugin="files",
    action="read_file",
    params=None,
    requires_confirmation=False,
    needs_clarification=False,
):
    if params is None:
        params = {"path": "C:\\test.txt"}
    body = {
        "intent": intent,
        "confidence": 0.95,
        "needs_clarification": needs_clarification,
        "requires_confirmation": requires_confirmation,
        "steps": [] if needs_clarification else [{
            "step_id": "s1",
            "plugin": plugin,
            "action": action,
            "params": params,
            "timeout_sec": 30,
            "continue_on_error": False,
            "depends_on": [],
        }],
    }
    return {"message": {"content": json.dumps(body)}, "prompt_eval_count": 50, "eval_count": 100}


def _make_plugin(name, succeed=True, data=None, error=None, raise_exc=None, delay=0.0):
    """Crea un plugin fake inyectable en el registry."""
    from sunny.core.plugins.base import PluginBase, PluginResult

    _succeed = succeed
    _data = data
    _error = error
    _raise_exc = raise_exc
    _delay = delay

    class _Fake(PluginBase):
        def execute(self, action, params, context, timeout_sec=30):
            if _delay:
                time.sleep(_delay)
            if _raise_exc:
                raise _raise_exc
            if _succeed:
                return PluginResult(success=True, data=_data or {"ok": True})
            return PluginResult(success=False, error=_error or "fake error", error_type="FakeError")

    _Fake.name = name
    return _Fake()


# ─────────────────────────── GRUPO A: MODELOS ────────────────────────────────
# 15 tests

from sunny.core.models.plan import Step, PlanV2, ComprehensionResult


# A-01
def test_step_valid_creation():
    s = Step(step_id="s1", plugin="files", action="read_file", params={"path": "x"})
    assert s.step_id == "s1" and s.timeout_sec == 30


# A-02
def test_step_hyphen_and_underscore_in_id():
    s = Step(step_id="step-1_ok", plugin="files", action="read_file", params={})
    assert s.step_id == "step-1_ok"


# A-03
def test_step_empty_id_raises():
    with pytest.raises(Exception):
        Step(step_id="", plugin="files", action="read_file", params={})


# A-04
def test_step_space_in_id_raises():
    with pytest.raises(Exception):
        Step(step_id="bad id", plugin="files", action="read_file", params={})


# A-05
def test_step_timeout_lower_bound():
    s = Step(step_id="s1", plugin="files", action="read_file", params={}, timeout_sec=1)
    assert s.timeout_sec == 1


# A-06
def test_step_timeout_upper_bound():
    s = Step(step_id="s1", plugin="files", action="read_file", params={}, timeout_sec=600)
    assert s.timeout_sec == 600


# A-07
def test_step_timeout_zero_raises():
    with pytest.raises(Exception):
        Step(step_id="s1", plugin="files", action="read_file", params={}, timeout_sec=0)


# A-08
def test_step_timeout_over_max_raises():
    with pytest.raises(Exception):
        Step(step_id="s1", plugin="files", action="read_file", params={}, timeout_sec=601)


# A-09
def test_planv2_conversation_no_steps():
    p = PlanV2(intent="conversation", confidence=0.8, steps=[])
    assert p.intent == "conversation" and p.steps == []


# A-10
def test_planv2_conversation_with_steps_raises():
    with pytest.raises(Exception):
        PlanV2(intent="conversation", confidence=0.8, steps=[
            Step(step_id="s1", plugin="files", action="read_file", params={})
        ])


# A-11
def test_planv2_non_conversation_empty_steps_no_clarification_raises():
    with pytest.raises(Exception):
        PlanV2(intent="files", confidence=0.8, steps=[], needs_clarification=False)


# A-12
def test_planv2_non_conversation_empty_steps_with_clarification_ok():
    p = PlanV2(intent="files", confidence=0.5, steps=[], needs_clarification=True)
    assert p.needs_clarification is True


# A-13
def test_planv2_duplicate_step_ids_raises():
    s = lambda sid: Step(step_id=sid, plugin="files", action="read_file", params={})
    with pytest.raises(Exception):
        PlanV2(intent="files", confidence=0.9, steps=[s("s1"), s("s1")])


# A-14
def test_planv2_self_dependency_raises():
    with pytest.raises(Exception):
        PlanV2(intent="files", confidence=0.9, steps=[
            Step(step_id="s1", plugin="files", action="read_file", params={}, depends_on=["s1"])
        ])


# A-15
def test_comprehension_confidence_out_of_range_raises():
    with pytest.raises(Exception):
        ComprehensionResult(
            comprehension="x", intent="files", assumptions=[], confidence=1.5,
            needs_clarification=False,
        )


# ──────────────── GRUPO B: OLLAMA CLIENT HELPERS ─────────────────────────────
# 8 tests

from sunny.brain.ollama_client import (
    _strip_code_fences,
    _extract_json_object,
    call_llm,
    call_llm_validated,
    LLMValidationError,
    LLMConnectionError,
    LLMTimeoutError,
    health_check,
)


# B-01
def test_strip_code_fences_json_block():
    raw = "```json\n{\"a\": 1}\n```"
    assert _strip_code_fences(raw) == '{"a": 1}'


# B-02
def test_strip_code_fences_plain_block():
    raw = "```\n{\"a\": 1}\n```"
    assert _strip_code_fences(raw) == '{"a": 1}'


# B-03
def test_strip_code_fences_no_fences():
    raw = '{"a": 1}'
    assert _strip_code_fences(raw) == '{"a": 1}'


# B-04
def test_extract_json_object_clean():
    assert _extract_json_object('{"x": 1}') == '{"x": 1}'


# B-05
def test_extract_json_object_with_prefix():
    raw = 'Aquí tienes: {"x": 1} fin'
    assert _extract_json_object(raw) == '{"x": 1}'


# B-06
def test_extract_json_object_no_braces():
    raw = "texto sin JSON"
    assert _extract_json_object(raw) == raw


# B-07
def test_call_llm_validated_success(monkeypatch):
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _comp_llm_response())
    result, stats = call_llm_validated(
        user_prompt="hola", system_prompt="sistema", schema=ComprehensionResult
    )
    assert result.intent == "files" and stats.retries_used == 0


# B-08
def test_call_llm_validated_exhausts_retries_raises(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **k: {"message": {"content": "not valid json"}, "prompt_eval_count": 0, "eval_count": 0},
    )
    with pytest.raises(LLMValidationError) as exc:
        call_llm_validated(user_prompt="x", system_prompt="y", schema=ComprehensionResult, max_retries=1)
    assert exc.value.last_raw != ""


# ──────────────── GRUPO C: COMPRENSIÓN ───────────────────────────────────────
# 6 tests

from sunny.core.orchestrator.comprehension import build_comprehension_user_prompt, comprehend, PHASE_TAG


# C-01
def test_comprehend_low_confidence_still_returns(monkeypatch):
    monkeypatch.setattr("ollama.Client.chat", lambda self, **k: _comp_llm_response(confidence=0.3))
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    result, _ = comprehend("algo")
    assert result.confidence == pytest.approx(0.3)


# C-02
def test_comprehend_needs_clarification_flag(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **k: _comp_llm_response(needs_clarification=True),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    result, _ = comprehend("¿qué quieres decir?")
    assert result.needs_clarification is True


# C-03
@pytest.mark.parametrize("intent", ["os_control", "gui", "vision", "ai_bridge"])
def test_comprehend_all_intents(monkeypatch, intent):
    def fake_chat(self, **k):
        return _comp_llm_response(intent=intent)
    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    result, _ = comprehend("test")
    assert result.intent == intent


# C-04
def test_comprehend_retry_appends_error_to_prompt(monkeypatch):
    calls = []
    responses = [
        {"message": {"content": "bad"}, "prompt_eval_count": 0, "eval_count": 0},
        _comp_llm_response(),
    ]

    def fake_chat(self, **kwargs):
        calls.append(kwargs["messages"][1]["content"])
        return responses[len(calls) - 1]

    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    comprehend("hola")
    assert len(calls) == 2
    assert "[ERROR PREVIO]" in calls[1]


# C-05
def test_comprehend_connection_error_propagates(monkeypatch):
    def fake_chat(self, **kwargs):
        raise Exception("Connection refused")

    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    with pytest.raises(LLMConnectionError):
        comprehend("hola")


# C-06
def test_build_comprehension_prompt_includes_user_input():
    p = build_comprehension_user_prompt("mueve el archivo")
    assert "mueve el archivo" in p
    assert PHASE_TAG in p


# ──────────────── GRUPO D: PLANIFICACIÓN ─────────────────────────────────────
# 5 tests

from sunny.core.orchestrator.planner import build_planning_user_prompt, plan, PHASE_TAG as PLAN_PHASE_TAG
from sunny.core.models.plan import ComprehensionResult as CR


def _comp(intent="files"):
    return CR(comprehension="x", intent=intent, assumptions=[], confidence=0.9, needs_clarification=False)


# D-01
def test_plan_os_control_intent(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **k: _plan_llm_response(intent="os_control", plugin="os_control", action="list_processes", params={}),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    result, _ = plan("lista los procesos", _comp(intent="os_control"))
    assert result.intent == "os_control"


# D-02
def test_plan_needs_clarification_returns_empty_steps(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **k: _plan_llm_response(needs_clarification=True),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    result, _ = plan("haz algo", _comp())
    assert result.needs_clarification is True
    assert result.steps == []


# D-03
def test_plan_requires_confirmation_flag(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **k: _plan_llm_response(requires_confirmation=True),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    result, _ = plan("borra algo", _comp())
    assert result.requires_confirmation is True


# D-04
def test_build_planning_prompt_empty_context_no_context_tag():
    from sunny.core.orchestrator.planner import CONTEXT_TAG
    p = build_planning_user_prompt("hola", _comp(), [])
    assert CONTEXT_TAG not in p


# D-05
def test_plan_stats_tokens_populated(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **k: _plan_llm_response(),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    _, stats = plan("leer archivo", _comp())
    assert stats.tokens_in == 50 and stats.tokens_out == 100


# ──────────────── GRUPO E: VALIDADOR ─────────────────────────────────────────
# 15 tests

from sunny.core.orchestrator.validator import validate_plan, PLUGIN_CATALOG, BULK_THRESHOLD


def _make_plan(plugin="files", action="read_file", params=None, intent="files",
               needs_clarification=False, requires_confirmation=False, extra_steps=None):
    if params is None:
        params = {"path": "x"}
    steps = [] if needs_clarification else [
        Step(step_id="s1", plugin=plugin, action=action, params=params)
    ]
    if extra_steps:
        steps.extend(extra_steps)
    return PlanV2(
        intent=intent,
        confidence=0.9,
        needs_clarification=needs_clarification,
        requires_confirmation=requires_confirmation,
        steps=steps,
    )


# E-01
def test_validator_conversation_always_valid():
    p = PlanV2(intent="conversation", confidence=0.8, steps=[])
    r = validate_plan(p)
    assert r.valid and not r.errors


# E-02
def test_validator_files_read_file_valid():
    r = validate_plan(_make_plan())
    assert r.valid


# E-03
def test_validator_unknown_plugin_error():
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="phantom", action="do_thing", params={})
    ])
    r = validate_plan(p)
    assert not r.valid and any("plugin desconocido" in e for e in r.errors)


# E-04
def test_validator_unknown_action_error():
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="teleport", params={})
    ])
    r = validate_plan(p)
    assert not r.valid and any("teleport" in e for e in r.errors)


# E-05
def test_validator_missing_required_params():
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="read_file", params={})
    ])
    r = validate_plan(p)
    assert not r.valid and any("path" in e for e in r.errors)


# E-06
def test_validator_files_write_file_missing_content():
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="write_file", params={"path": "x"})
    ])
    r = validate_plan(p)
    assert not r.valid and any("content" in e for e in r.errors)


# E-07
def test_validator_destructive_forces_confirmation():
    p = _make_plan(action="delete")
    r = validate_plan(p)
    assert r.effective_requires_confirmation is True


# E-08
def test_validator_non_destructive_no_confirmation():
    p = _make_plan(action="read_file")
    r = validate_plan(p)
    assert r.effective_requires_confirmation is False


# E-09
def test_validator_bulk_threshold_forces_confirmation():
    steps = [
        Step(step_id=f"s{i}", plugin="files", action="read_file", params={"path": f"x{i}"})
        for i in range(BULK_THRESHOLD + 1)
    ]
    p = PlanV2(intent="files", confidence=0.9, steps=steps)
    r = validate_plan(p)
    assert r.effective_requires_confirmation is True


# E-10
def test_validator_warning_when_llm_missed_confirmation():
    p = _make_plan(action="delete", requires_confirmation=False)
    r = validate_plan(p)
    assert r.warnings


# E-11
def test_validator_os_control_kill_process_destructive():
    p = PlanV2(intent="os_control", confidence=0.9, steps=[
        Step(step_id="s1", plugin="os_control", action="kill_process", params={"pid": 1})
    ])
    r = validate_plan(p)
    assert r.effective_requires_confirmation is True


# E-12
def test_validator_os_control_list_processes_not_destructive():
    p = PlanV2(intent="os_control", confidence=0.9, steps=[
        Step(step_id="s1", plugin="os_control", action="list_processes", params={})
    ])
    r = validate_plan(p)
    assert r.effective_requires_confirmation is False


# E-13
def test_validator_gui_click_valid():
    p = PlanV2(intent="gui", confidence=0.9, steps=[
        Step(step_id="s1", plugin="gui", action="click", params={"x": 10, "y": 20})
    ])
    r = validate_plan(p)
    assert r.valid


# E-14
def test_validator_vision_screenshot_no_params_valid():
    p = PlanV2(intent="vision", confidence=0.9, steps=[
        Step(step_id="s1", plugin="vision", action="screenshot", params={})
    ])
    r = validate_plan(p)
    assert r.valid


# E-15
def test_validator_multiple_errors_reported():
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="phantom", action="a", params={}),
        Step(step_id="s2", plugin="files", action="teleport", params={}),
    ])
    r = validate_plan(p)
    assert len(r.errors) >= 2


# ──────────────── GRUPO F: MOTOR DE EJECUCIÓN ────────────────────────────────
# 14 tests

from sunny.core.execution.engine import execute_plan, StepExecutionResult, ExecutionResult
from sunny.core.plugins.registry import PluginRegistry


def _registry(*plugins):
    reg = PluginRegistry()
    for p in plugins:
        reg.register(p)
    return reg


# F-01
def test_engine_conversation_plan_returns_success():
    p = PlanV2(intent="conversation", confidence=0.8, steps=[])
    r = execute_plan(p, _registry())
    assert r.success and r.plan_intent == "conversation" and r.steps == []


# F-02
def test_engine_single_step_success():
    plugin = _make_plugin("files")
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="read_file", params={"path": "x"})
    ])
    r = execute_plan(p, _registry(plugin))
    assert r.success and len(r.steps) == 1 and r.steps[0].success


# F-03
def test_engine_plugin_not_registered_fails():
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="missing", action="read_file", params={})
    ])
    r = execute_plan(p, _registry())
    assert not r.success and r.steps[0].error_type == "PluginNotRegistered"


# F-04
def test_engine_step_failure_stops_pipeline():
    bad = _make_plugin("files", succeed=False)
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="read_file", params={}),
        Step(step_id="s2", plugin="files", action="write_file", params={}),
    ])
    r = execute_plan(p, _registry(bad))
    assert not r.success
    assert r.steps[0].success is False
    assert r.steps[1].skipped is True


# F-05
def test_engine_continue_on_error_executes_next():
    bad = _make_plugin("files", succeed=False)
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="a", params={}, continue_on_error=True),
        Step(step_id="s2", plugin="files", action="b", params={}),
    ])
    r = execute_plan(p, _registry(bad))
    assert not r.steps[0].success
    assert not r.steps[1].skipped


# F-06
def test_engine_step_data_propagated():
    plugin = _make_plugin("files", data={"content": "hola"})
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="read_file", params={})
    ])
    r = execute_plan(p, _registry(plugin))
    assert r.steps[0].data == {"content": "hola"}


# F-07
def test_engine_latency_recorded():
    plugin = _make_plugin("files")
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="read_file", params={})
    ])
    r = execute_plan(p, _registry(plugin))
    assert r.total_latency_ms >= 0
    assert r.steps[0].latency_ms >= 0


# F-08
def test_engine_early_stopped_flag():
    bad = _make_plugin("files", succeed=False)
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="a", params={}),
        Step(step_id="s2", plugin="files", action="b", params={}),
    ])
    r = execute_plan(p, _registry(bad))
    assert r.early_stopped is True


# F-09
def test_engine_all_steps_succeed_no_early_stop():
    plugin = _make_plugin("files")
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="a", params={}),
        Step(step_id="s2", plugin="files", action="b", params={}),
    ])
    r = execute_plan(p, _registry(plugin))
    assert r.early_stopped is False


# F-10
def test_engine_logs_execution_start(monkeypatch):
    events = []
    import sunny.core.execution.engine as eng_mod
    monkeypatch.setattr(eng_mod.log, "info", lambda e, **k: events.append(e))
    plugin = _make_plugin("files")
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="a", params={})
    ])
    execute_plan(p, _registry(plugin))
    assert "execution_start" in events and "execution_done" in events


# F-11
def test_engine_step_exception_captured_as_failure():
    from sunny.core.plugins.base import PluginBase, PluginResult

    class ExcPlugin(PluginBase):
        name = "files"
        def execute(self, action, params, context, timeout_sec=30):
            raise RuntimeError("boom")

    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="a", params={})
    ])
    r = execute_plan(p, _registry(ExcPlugin()))
    assert not r.steps[0].success
    assert r.steps[0].error_type == "RuntimeError"


# F-12
def test_engine_context_passed_to_plugin():
    received = {}

    from sunny.core.plugins.base import PluginBase, PluginResult

    class CtxPlugin(PluginBase):
        name = "files"
        def execute(self, action, params, context, timeout_sec=30):
            received.update(context)
            return PluginResult(success=True)

    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="a", params={})
    ])
    execute_plan(p, _registry(CtxPlugin()), context={"key": "val"})
    assert received.get("key") == "val"


# F-13
def test_engine_two_different_plugins():
    p1 = _make_plugin("files")
    p2 = _make_plugin("os_control")
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="a", params={}),
        Step(step_id="s2", plugin="os_control", action="b", params={}),
    ])
    r = execute_plan(p, _registry(p1, p2))
    assert r.success and len(r.steps) == 2


# F-14
def test_engine_step_error_message_preserved():
    bad = _make_plugin("files", succeed=False, error="ruta no encontrada")
    p = PlanV2(intent="files", confidence=0.9, steps=[
        Step(step_id="s1", plugin="files", action="a", params={})
    ])
    r = execute_plan(p, _registry(bad))
    assert "ruta no encontrada" in r.steps[0].error


# ──────────────── GRUPO G: PLUGIN FILES ──────────────────────────────────────
# 10 tests

from sunny.modules.files import FilesPlugin


@pytest.fixture
def fp():
    return FilesPlugin()


# G-01
def test_files_write_and_read_roundtrip(tmp_path, fp):
    p = tmp_path / "roundtrip.txt"
    fp.execute("write_file", {"path": str(p), "content": "sunny"}, {})
    r = fp.execute("read_file", {"path": str(p)}, {})
    assert r.data == "sunny"


# G-02
def test_files_search_empty_only_flag(tmp_path, fp):
    (tmp_path / "empty.txt").write_text("")
    (tmp_path / "nonempty.txt").write_text("x")
    r = fp.execute("search", {"directory": str(tmp_path), "pattern": "*.txt", "empty_only": True}, {})
    assert len(r.data) == 1 and "empty.txt" in r.data[0]


# G-03
def test_files_tree_directory_basic(tmp_path, fp):
    (tmp_path / "a.txt").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y")
    r = fp.execute("tree_directory", {"path": str(tmp_path)}, {})
    assert r.success
    assert r.data["name"] == tmp_path.name


# G-04
def test_files_get_info_modified_ts(tmp_path, fp):
    p = tmp_path / "ts.txt"
    p.write_text("x")
    r = fp.execute("get_info", {"path": str(p)}, {})
    assert r.data["modified_ts"] is not None


# G-05
def test_files_move_overwrite_true(tmp_path, fp):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("nuevo")
    dst.write_text("viejo")
    r = fp.execute("move", {"src": str(src), "dst": str(dst), "overwrite": True}, {})
    assert r.success and dst.read_text() == "nuevo"


# G-06
def test_files_copy_overwrite_true(tmp_path, fp):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("copia")
    dst.write_text("viejo")
    r = fp.execute("copy", {"src": str(src), "dst": str(dst), "overwrite": True}, {})
    assert r.success and dst.read_text() == "copia" and src.exists()


# G-07
def test_files_delete_matching_returns_count(tmp_path, fp, monkeypatch):
    monkeypatch.setattr("sunny.modules.files.send2trash", lambda p: None)
    (tmp_path / "a.tmp").write_text("")
    (tmp_path / "b.tmp").write_text("")
    r = fp.execute("delete_matching", {"directory": str(tmp_path), "pattern": "*.tmp"}, {})
    assert r.success and r.data["count"] == 2


# G-08
def test_files_list_directory_empty_dir(tmp_path, fp):
    d = tmp_path / "empty"
    d.mkdir()
    r = fp.execute("list_directory", {"path": str(d)}, {})
    assert r.success and r.data["total_entries"] == 0


# G-09
def test_files_write_file_nested_dirs_created(tmp_path, fp):
    p = tmp_path / "a" / "b" / "c" / "deep.txt"
    r = fp.execute("write_file", {"path": str(p), "content": "deep"}, {})
    assert r.success and p.exists()


# G-10
def test_files_find_free_name(tmp_path, fp):
    existing = tmp_path / "file.txt"
    existing.write_text("x")
    free = fp._find_free_name(existing)
    assert "file(1)" in free.name and not free.exists()


# ──────────────── GRUPO H: PLUGIN OS_CONTROL ─────────────────────────────────
# 8 tests

from sunny.modules.os_control import OSControlPlugin
import psutil


@pytest.fixture
def osp():
    return OSControlPlugin()


# H-01
def test_os_control_unsupported_action(osp):
    r = osp.execute("explode", {}, {})
    assert not r.success and r.error_type == "UnsupportedAction"


# H-02
def test_os_control_plugin_name(osp):
    assert osp.name == "os_control"


# H-03
def test_os_control_get_system_info_fields(osp):
    info = osp._get_system_info()
    assert "cpu_count" in info and "memory_total_gb" in info


# H-04
def test_os_control_get_system_info_memory_positive(osp):
    info = osp._get_system_info()
    assert info["memory_total_gb"] > 0


# H-05
def test_os_control_close_app_no_match_raises(monkeypatch, osp):
    monkeypatch.setattr("sunny.modules.os_control.psutil.process_iter", lambda _: iter([]))
    r = osp.execute("close_app", {"app": "inexistente"}, {})
    assert not r.success and r.error_type == "FileNotFoundError"


# H-06
def test_os_control_list_processes_returns_list(monkeypatch, osp):
    class FP:
        info = {"pid": 1, "name": "x.exe"}
    monkeypatch.setattr("sunny.modules.os_control.psutil.process_iter", lambda _: iter([FP()]))
    r = osp.execute("list_processes", {}, {})
    assert r.success and isinstance(r.data, list)


# H-07
def test_os_control_shutdown_calls_subprocess(monkeypatch, osp):
    cmds = []
    monkeypatch.setattr(
        "sunny.modules.os_control.subprocess.run",
        lambda args, **k: cmds.append(args),
    )
    osp.execute("shutdown", {"delay_sec": 60}, {})
    assert any("/s" in " ".join(c) for c in cmds)


# H-08
def test_os_control_sleep_seconds_via_execute(monkeypatch, osp):
    slept = {}
    monkeypatch.setattr("sunny.modules.os_control.time.sleep", lambda s: slept.update({"s": s}))
    r = osp.execute("sleep_seconds", {"seconds": 2}, {})
    assert r.success and slept.get("s") == 2


# ──────────────── GRUPO I: PLUGIN GUI ────────────────────────────────────────
# 7 tests

from sunny.modules.gui import GuiPlugin
from sunny.core.plugins.base import PluginResult as PR


@pytest.fixture
def gp(monkeypatch):
    monkeypatch.setattr("sunny.modules.gui.pyautogui.click", lambda *a, **k: None)
    monkeypatch.setattr("sunny.modules.gui.pyautogui.write", lambda *a, **k: None)
    monkeypatch.setattr("sunny.modules.gui.pyautogui.press", lambda *a, **k: None)
    monkeypatch.setattr("sunny.modules.gui.pyautogui.hotkey", lambda *a, **k: None)
    monkeypatch.setattr("sunny.modules.gui.pyautogui.moveTo", lambda *a, **k: None)
    monkeypatch.setattr("sunny.modules.gui.pyautogui.scroll", lambda *a, **k: None)
    monkeypatch.setattr("sunny.modules.gui.pyautogui.dragTo", lambda *a, **k: None)
    return GuiPlugin()


# I-01
def test_gui_plugin_name(gp):
    assert gp.name == "gui"


# I-02
def test_gui_click_returns_coords(gp):
    r = gp.execute("click", {"x": 5, "y": 10}, {})
    assert r.success and r.data == {"x": 5, "y": 10, "clicked": True}


# I-03
def test_gui_type_text_ascii_length(gp):
    r = gp.execute("type_text", {"text": "hello"}, {})
    assert r.success and r.data["length"] == 5


# I-04
def test_gui_press_key_combo_hotkey(monkeypatch):
    keys_called = []
    monkeypatch.setattr("sunny.modules.gui.pyautogui.hotkey", lambda *k: keys_called.extend(k))
    gp_local = GuiPlugin()
    gp_local.execute("press_key", {"key": "alt+F4"}, {})
    assert "alt" in keys_called and "F4" in keys_called


# I-05
def test_gui_scroll_up_positive(monkeypatch):
    amounts = []
    monkeypatch.setattr("sunny.modules.gui.pyautogui.scroll", lambda a: amounts.append(a))
    GuiPlugin().execute("scroll", {"direction": "up", "amount": 3}, {})
    assert amounts == [3]


# I-06
def test_gui_scroll_invalid_direction(monkeypatch):
    monkeypatch.setattr("sunny.modules.gui.pyautogui.scroll", lambda a: None)
    r = GuiPlugin().execute("scroll", {"direction": "left", "amount": 1}, {})
    assert not r.success and r.error_type == "ValueError"


# I-07
def test_gui_click_on_text_vision_failure():
    class BadVision:
        def execute(self, action, params, context, timeout_sec=30):
            return PR(success=False, error="screen error")

    gp_bad = GuiPlugin(vision=BadVision())
    r = gp_bad.execute("click_on_text", {"text": "Guardar"}, {})
    assert not r.success and r.error_type == "RuntimeError"


# ──────────────── GRUPO J: MEMORIA SQLITE ────────────────────────────────────
# 12 tests

import sunny.core.memory.sqlite as db_mod


@pytest.fixture
def db(tmp_path):
    db_mod._reset_db()
    db_path = tmp_path / "test.db"
    db_mod.init_db(db_path)
    yield db_mod
    db_mod._reset_db()


# J-01
def test_db_create_and_check_session(db):
    db.create_session("sess-1")
    assert db.session_exists("sess-1")


# J-02
def test_db_session_not_exists(db):
    assert not db.session_exists("ghost")


# J-03
def test_db_record_and_get_command(db):
    db.create_session("s1")
    db.record_command("cmd-1", "s1", "leer archivo", "files", "{}", "ok")
    row = db.get_command("cmd-1")
    assert row and row["input"] == "leer archivo"


# J-04
def test_db_get_command_not_found_returns_none(db):
    assert db.get_command("nope") is None


# J-05
def test_db_list_commands_ordered(db):
    db.create_session("s1")
    db.record_command("c1", "s1", "a", "files", "{}", "ok",
                      timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
    db.record_command("c2", "s1", "b", "files", "{}", "ok",
                      timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc))
    cmds = db.list_commands("s1")
    assert [c["id"] for c in cmds] == ["c1", "c2"]


# J-06
def test_db_list_commands_limit(db):
    db.create_session("s1")
    for i in range(5):
        db.record_command(f"c{i}", "s1", f"x{i}", "files", "{}", "ok")
    cmds = db.list_commands("s1", limit=2)
    assert len(cmds) == 2


# J-07
def test_db_append_turn_increments(db):
    db.create_session("s1")
    t1 = db.append_turn("s1", "hola", "hi")
    t2 = db.append_turn("s1", "qué tal", "bien")
    assert t1 == 1 and t2 == 2


# J-08
def test_db_get_recent_turns_order(db):
    db.create_session("s1")
    for i in range(4):
        db.append_turn("s1", f"u{i}", f"a{i}")
    turns = db.get_recent_turns("s1", n=2)
    assert len(turns) == 2
    assert turns[0]["turn"] < turns[1]["turn"]


# J-09
def test_db_trim_history_removes_oldest(db):
    db.create_session("s1")
    for i in range(5):
        db.append_turn("s1", f"u{i}", f"a{i}")
    removed = db.trim_history("s1", keep_last=3)
    assert removed == 2
    assert db.get_turn_count("s1") == 3


# J-10
def test_db_trim_history_noop_when_under_limit(db):
    db.create_session("s1")
    db.append_turn("s1", "u1", "a1")
    removed = db.trim_history("s1", keep_last=5)
    assert removed == 0


# J-11
def test_db_preferences_crud(db):
    db.set_preference("theme", "dark")
    assert db.get_preference("theme") == "dark"
    db.set_preference("theme", "light")
    assert db.get_preference("theme") == "light"
    db.delete_preference("theme")
    assert db.get_preference("theme") is None


# J-12
def test_db_get_all_preferences(db):
    db.set_preference("k1", "v1")
    db.set_preference("k2", "v2")
    prefs = db.get_all_preferences()
    assert prefs == {"k1": "v1", "k2": "v2"}


# ──────────────── GRUPO K: MEJORAS APLICADAS ─────────────────────────────────
# 3 tests que validan las mejoras introducidas tras análisis

# K-01: retry prompt ahora incluye nombres de campos del schema
def test_retry_prompt_includes_schema_field_names(monkeypatch):
    calls = []
    responses = [
        {"message": {"content": "bad"}, "prompt_eval_count": 0, "eval_count": 0},
        _comp_llm_response(),
    ]

    def fake_chat(self, **kwargs):
        calls.append(kwargs["messages"][1]["content"])
        return responses[len(calls) - 1]

    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    comprehend("hola")
    assert "comprehension" in calls[1]
    assert "intent" in calls[1]
    assert "confidence" in calls[1]


# K-02: health_check usa la lista de modelos si está disponible
def test_health_check_uses_model_list(monkeypatch):
    from sunny.brain.ollama_client import health_check, DEFAULT_MODEL

    class FakeModel:
        model = DEFAULT_MODEL

    class FakeResp:
        models = [FakeModel()]

    monkeypatch.setattr("ollama.list", lambda: FakeResp())
    assert health_check() is True


# K-03: reporter renderiza delete_matching con recuento correcto
def test_reporter_renders_delete_matching(monkeypatch):
    import sunny.core.orchestrator.reporter as rep_mod
    from rich.console import Console

    printed = []
    fake_console = Console(file=__import__("io").StringIO())
    original_print = fake_console.print
    fake_console.print = lambda x, **k: printed.append(str(x))

    monkeypatch.setattr(rep_mod, "console", fake_console)
    rep_mod._render_delete_matching({"deleted": ["/a/b.txt", "/a/c.txt"], "errors": [], "count": 2})
    assert any("2" in p for p in printed)
