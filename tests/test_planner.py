import json
import pytest
from sunny.core.models.plan import ComprehensionResult
from sunny.core.orchestrator import planner
def _ok_plan_response():
    return {
        "message": {"content": json.dumps({
            "intent": "files",
            "confidence": 0.92,
            "needs_clarification": False,
            "requires_confirmation": False,
            "steps": [{
                "step_id": "s1",
                "plugin": "files",
                "action": "read_file",
                "params": {"path": "C:\\test.txt"},
                "timeout_sec": 30,
                "continue_on_error": False,
                "depends_on": [],
            }],
        })},
        "prompt_eval_count": 50,
        "eval_count": 100,
    }
def _comp(intent="files"):
    return ComprehensionResult(
        comprehension="x",
        intent=intent,
        assumptions=[],
        confidence=0.9,
        needs_clarification=False,
    )
def test_build_prompt_basic_no_context():
    prompt = planner.build_planning_user_prompt("hola", _comp(), None)
    assert planner.PHASE_TAG in prompt
    assert planner.COMPREHENSION_TAG in prompt
    assert "Usuario: hola" in prompt
    assert planner.CONTEXT_TAG not in prompt
def test_build_prompt_with_context_includes_section():
    ctx = [{"turn": 1, "user_msg": "a", "assistant_msg": "b"}]
    prompt = planner.build_planning_user_prompt("hola", _comp(), ctx)
    assert planner.CONTEXT_TAG in prompt
    assert "a" in prompt and "b" in prompt
def test_build_prompt_includes_comprehension_json():
    comp = _comp()
    prompt = planner.build_planning_user_prompt("hola", comp, None)
    assert '"comprehension": "x"' in prompt
    assert f'"intent": "{comp.intent}"' in prompt
def test_build_prompt_section_order():
    ctx = [{"turn": 1, "user_msg": "a", "assistant_msg": "b"}]
    prompt = planner.build_planning_user_prompt("hola", _comp(), ctx)
    i_phase = prompt.find(planner.PHASE_TAG)
    i_ctx = prompt.find(planner.CONTEXT_TAG)
    i_comp = prompt.find(planner.COMPREHENSION_TAG)
    i_user = prompt.find("Usuario:")
    assert i_phase < i_ctx < i_comp < i_user
def test_build_prompt_unicode_preserved():
    prompt = planner.build_planning_user_prompt("ábrelo", _comp(), None)
    assert "ábrelo" in prompt
def test_plan_returns_validated_planv2(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **kwargs: _ok_plan_response(),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    result, stats = planner.plan("x", _comp())
    assert result.intent == "files"
    assert len(result.steps) == 1
    assert stats.retries_used == 0
def test_plan_uses_v1_system_prompt(monkeypatch):
    captured = {}
    def fake_chat(self, **kwargs):
        captured["system"] = kwargs["messages"][0]["content"]
        return _ok_plan_response()
    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    planner.plan("x", _comp())
    assert "# ROL Y MISIÓN" in captured["system"]
    assert "FASE PLANIFICACIÓN" in captured["system"]
def test_plan_user_prompt_has_phase_tag(monkeypatch):
    captured = {}
    def fake_chat(self, **kwargs):
        captured["user"] = kwargs["messages"][1]["content"]
        return _ok_plan_response()
    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    planner.plan("x", _comp())
    assert planner.PHASE_TAG in captured["user"]
def test_plan_user_prompt_includes_comprehension_block(monkeypatch):
    captured = {}
    def fake_chat(self, **kwargs):
        captured["user"] = kwargs["messages"][1]["content"]
        return _ok_plan_response()
    comp = _comp()
    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    planner.plan("x", comp)
    assert planner.COMPREHENSION_TAG in captured["user"]
    assert "x" in captured["user"]
def test_plan_uses_session_context_when_present(monkeypatch):
    captured = {}
    def fake_chat(self, **kwargs):
        captured["user"] = kwargs["messages"][1]["content"]
        return _ok_plan_response()
    ctx = [{"turn": 1, "user_msg": "leer notas", "assistant_msg": "ok"}]
    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: ctx)
    planner.plan("x", _comp())
    assert planner.CONTEXT_TAG in captured["user"]
    assert "leer notas" in captured["user"]
def test_plan_no_context_section_when_empty_session(monkeypatch):
    captured = {}
    def fake_chat(self, **kwargs):
        captured["user"] = kwargs["messages"][1]["content"]
        return _ok_plan_response()
    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    planner.plan("x", _comp())
    assert planner.CONTEXT_TAG not in captured["user"]
def test_plan_propagates_validation_error(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **kwargs: {"message": {"content": "bad"}},
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    from sunny.brain.ollama_client import LLMValidationError
    with pytest.raises(LLMValidationError):
        planner.plan("x", _comp())
def test_plan_propagates_timeout_error(monkeypatch):
    def fake_chat(self, **kwargs):
        raise Exception("timeout")
    monkeypatch.setattr("ollama.Client.chat", fake_chat)
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    from sunny.brain.ollama_client import LLMTimeoutError
    with pytest.raises(LLMTimeoutError):
        planner.plan("x", _comp())
def test_plan_returns_stats(monkeypatch):
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **kwargs: _ok_plan_response(),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    _, stats = planner.plan("x", _comp())
    assert stats.tokens_in == 50
    assert stats.tokens_out == 100
    assert stats.latency_ms >= 0
def test_plan_logs_start_and_done(monkeypatch):
    events = []
    def fake_info(**kwargs):
        events.append(kwargs.get("event"))
    monkeypatch.setattr(planner.log, "info", fake_info)
    monkeypatch.setattr(
        "ollama.Client.chat",
        lambda self, **kwargs: _ok_plan_response(),
    )
    monkeypatch.setattr("sunny.core.session.manager.get_context", lambda: [])
    planner.plan("x", _comp())
    assert "planning_start" in events
    assert "planning_done" in events
def test_plan_short_circuits_on_conversation_intent(monkeypatch):
    def fail_chat(self, **kwargs):
        raise AssertionError("LLM no debería llamarse")
    monkeypatch.setattr("ollama.Client.chat", fail_chat)
    result, _ = planner.plan("x", _comp(intent="conversation"))
    assert result.intent == "conversation"
    assert result.steps == []
def test_plan_conversation_returns_zero_stats():
    _, stats = planner.plan("x", _comp(intent="conversation"))
    assert stats.tokens_in == 0
    assert stats.tokens_out == 0
    assert stats.latency_ms == 0
    assert stats.retries_used == 0
def test_plan_conversation_logs_short_circuit(monkeypatch):
    events = []
    def fake_info(**kwargs):
        events.append(kwargs.get("event"))
    monkeypatch.setattr(planner.log, "info", fake_info)
    planner.plan("x", _comp(intent="conversation"))
    assert "planning_short_circuit" in events