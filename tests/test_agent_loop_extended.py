"""Tests extendidos de agent_loop: prompts, validación, edge cases."""
from typing import List

from sunny.core.execution.agent_loop import (
    LoopDecision,
    MAX_LOOP_STEPS,
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

    def __init__(self, screen_text="[top] PLAY"):
        self.screen_text = screen_text

    def execute(self, action, params, context, timeout_sec=30):
        return PluginResult(success=True, data={
            "screen_text": self.screen_text,
            "screenshot_path": "/tmp/x.png",
            "latency_ms": 5,
        })


class _GuiStub(PluginBase):
    name = "gui"

    def execute(self, action, params, context, timeout_sec=30):
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


def test_run_agent_loop_sends_screen_state_to_llm(monkeypatch):
    captured = {}

    def fake(**kwargs):
        captured["user_prompt"] = kwargs.get("user_prompt", "")
        return _decision(goal_reached=True, reason="ok"), _FakeStats()

    monkeypatch.setattr("sunny.core.execution.agent_loop.call_llm_validated", fake)
    reg = _registry(screen_text="[top] PLAY SETTINGS QUIT")
    run_agent_loop(goal="abrir factorio", registry=reg, max_steps=2)
    assert "PLAY SETTINGS QUIT" in captured["user_prompt"]
    assert "PANTALLA_ACTUAL" in captured["user_prompt"]


def test_run_agent_loop_sends_executed_steps_to_llm(monkeypatch):
    captured: List[str] = []

    def fake(**kwargs):
        captured.append(kwargs.get("user_prompt", ""))
        i = len(captured) - 1
        if i == 0:
            return _decision(action="click_on_text", params={"text": "PLAY"}), _FakeStats()
        return _decision(goal_reached=True, reason="ok"), _FakeStats()

    monkeypatch.setattr("sunny.core.execution.agent_loop.call_llm_validated", fake)
    run_agent_loop(goal="g", registry=_registry(), max_steps=5)
    assert "HISTORIAL" in captured[1]
    assert "click_on_text" in captured[1]


def test_agent_loop_system_prompt_contains_goal(monkeypatch):
    captured = {}

    def fake(**kwargs):
        captured["user_prompt"] = kwargs.get("user_prompt", "")
        captured["system_prompt"] = kwargs.get("system_prompt", "")
        return _decision(goal_reached=True, reason="ok"), _FakeStats()

    monkeypatch.setattr("sunny.core.execution.agent_loop.call_llm_validated", fake)
    run_agent_loop(goal="MI_OBJETIVO_UNICO", registry=_registry(), max_steps=2)
    assert "MI_OBJETIVO_UNICO" in captured["user_prompt"]
    sys_lower = captured["system_prompt"].lower()
    assert "agente" in sys_lower and "visual" in sys_lower


def test_agent_loop_handles_llm_timeout_gracefully(monkeypatch):
    from sunny.brain.ollama_client import LLMTimeoutError

    def boom(**kwargs):
        raise LLMTimeoutError("timeout")

    monkeypatch.setattr("sunny.core.execution.agent_loop.call_llm_validated", boom)
    res = run_agent_loop(goal="g", registry=_registry(), max_steps=3)
    assert res.success is False
    assert res.stopped_reason == "error"


def test_agent_loop_max_steps_clamped_to_global_limit(monkeypatch):
    forever = [_decision(action="click_on_text", params={"text": "X"})] * 50
    state = {"i": 0}

    def fake(**kwargs):
        i = state["i"]
        state["i"] = i + 1
        return forever[min(i, len(forever) - 1)], _FakeStats()

    monkeypatch.setattr("sunny.core.execution.agent_loop.call_llm_validated", fake)
    res = run_agent_loop(goal="g", registry=_registry(), max_steps=999)
    assert len(res.steps_executed) <= MAX_LOOP_STEPS


def test_agent_loop_rejects_disallowed_plugin(monkeypatch):
    def fake(**kwargs):
        return _decision(plugin="files", action="delete", params={"path": "/x"}), _FakeStats()

    monkeypatch.setattr("sunny.core.execution.agent_loop.call_llm_validated", fake)
    res = run_agent_loop(goal="g", registry=_registry(), max_steps=3)
    assert res.stopped_reason == "error"
    assert res.success is False
