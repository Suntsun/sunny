"""Tests core de sunny.core.execution.agent_loop (flujo principal)."""
from typing import List

from sunny.core.execution.agent_loop import (
    AgentLoopResult,
    LoopDecision,
    run_agent_loop,
)
from sunny.core.plugins.base import PluginBase, PluginResult
from sunny.core.plugins.registry import PluginRegistry


class _FakeStats:
    tokens_in = 1
    tokens_out = 1
    latency_ms = 1
    retries_used = 0


class _VisionStub(PluginBase):
    name = "vision"

    def __init__(self, screen_text: str = "[top] PLAY"):
        self.screen_text = screen_text
        self.calls: List[str] = []

    def execute(self, action, params, context, timeout_sec=30):
        self.calls.append(action)
        return PluginResult(success=True, data={
            "screen_text": self.screen_text,
            "screenshot_path": "/tmp/x.png",
            "latency_ms": 5,
        })


class _GuiStub(PluginBase):
    name = "gui"

    def __init__(self):
        self.calls: List[tuple] = []

    def execute(self, action, params, context, timeout_sec=30):
        self.calls.append((action, dict(params)))
        return PluginResult(success=True, data={"action": action, "params": params})


def _registry(screen_text="[top] PLAY"):
    reg = PluginRegistry()
    reg.register(_VisionStub(screen_text))
    reg.register(_GuiStub())
    return reg


def _decision(plugin="gui", action="click_on_text", params=None, goal_reached=False, reason="r"):
    return LoopDecision(
        plugin=plugin, action=action,
        params=params or {"text": "PLAY"},
        reason=reason, goal_reached=goal_reached,
    )


def _patch_llm(monkeypatch, decisions: List[LoopDecision]):
    state = {"i": 0}

    def fake(**kwargs):
        i = state["i"]
        state["i"] = i + 1
        if i >= len(decisions):
            return _decision(goal_reached=True, reason="fin"), _FakeStats()
        return decisions[i], _FakeStats()

    class _FakeProvider:
        def call_validated(self, **kwargs):
            return fake(**kwargs)

    monkeypatch.setattr(
        "sunny.core.execution.agent_loop.get_provider_for_role",
        lambda role: _FakeProvider(),
    )
    monkeypatch.setattr(
        "sunny.core.execution.agent_loop.summarize_screen_state",
        lambda raw, goal: raw,
    )


def test_run_agent_loop_reaches_goal_in_one_step(monkeypatch):
    _patch_llm(monkeypatch, [_decision(goal_reached=True, reason="ya está")])
    res = run_agent_loop(goal="abrir factorio", registry=_registry(), max_steps=5)
    assert isinstance(res, AgentLoopResult)
    assert res.success is True
    assert res.stopped_reason == "goal_reached"
    assert len(res.steps_executed) == 0


def test_run_agent_loop_reaches_goal_after_multiple_steps(monkeypatch):
    decisions = [
        _decision(action="click_on_text", params={"text": "PLAY"}),
        _decision(action="click_on_text", params={"text": "New Game"}),
        _decision(goal_reached=True, reason="estamos en partida"),
    ]
    _patch_llm(monkeypatch, decisions)
    res = run_agent_loop(goal="iniciar partida", registry=_registry(), max_steps=5)
    assert res.success is True
    assert res.stopped_reason == "goal_reached"
    assert len(res.steps_executed) == 2


def test_run_agent_loop_stops_at_max_steps(monkeypatch):
    forever = [_decision(action="click_on_text", params={"text": "X"})] * 5
    _patch_llm(monkeypatch, forever)
    res = run_agent_loop(goal="loop forever", registry=_registry(), max_steps=3)
    assert res.stopped_reason == "max_steps"
    assert res.success is False
    assert len(res.steps_executed) == 3


def test_run_agent_loop_stops_on_error(monkeypatch):
    from sunny.brain.ollama_client import LLMError

    class _BoomProvider:
        def call_validated(self, **kwargs):
            raise LLMError("modelo caído")

    monkeypatch.setattr(
        "sunny.core.execution.agent_loop.get_provider_for_role",
        lambda role: _BoomProvider(),
    )
    monkeypatch.setattr(
        "sunny.core.execution.agent_loop.summarize_screen_state",
        lambda raw, goal: raw,
    )
    res = run_agent_loop(goal="x", registry=_registry(), max_steps=3)
    assert res.stopped_reason == "error"
    assert res.success is False


def test_run_agent_loop_returns_all_executed_steps(monkeypatch):
    decisions = [
        _decision(action="click_on_text", params={"text": "A"}),
        _decision(action="click_on_text", params={"text": "B"}),
        _decision(goal_reached=True, reason="ok"),
    ]
    _patch_llm(monkeypatch, decisions)
    res = run_agent_loop(goal="g", registry=_registry(), max_steps=10)
    assert [s.plugin for s in res.steps_executed] == ["gui", "gui"]
    assert [s.action for s in res.steps_executed] == ["click_on_text", "click_on_text"]


def test_agent_loop_result_has_stopped_reason(monkeypatch):
    _patch_llm(monkeypatch, [_decision(goal_reached=True, reason="ok")])
    res = run_agent_loop(goal="g", registry=_registry(), max_steps=2)
    assert res.stopped_reason in {"goal_reached", "max_steps", "error", "user_cancelled", "timeout"}
