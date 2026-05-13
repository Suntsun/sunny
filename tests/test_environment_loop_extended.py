"""Tests extendidos: edge cases del bucle de entorno (timeout, invalid action, sin vision)."""
from typing import List

from sunny.core.execution.environment_loop import (
    ConcreteAction,
    StrategicStep,
    run_environment_loop,
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

    def __init__(self, frames=None):
        self.frames = frames or [{"screen_text": "x", "window_title": "x"}]
        self.idx = 0

    def execute(self, action, params, context, timeout_sec=30):
        if self.idx < len(self.frames):
            frame = self.frames[self.idx]
            self.idx += 1
        else:
            frame = self.frames[-1]
        return PluginResult(success=True, data={
            "screen_text": frame.get("screen_text", ""),
            "window_title": frame.get("window_title", ""),
            "screenshot_path": "/tmp/x.png",
        })


class _GuiStub(PluginBase):
    name = "gui"

    def execute(self, action, params, context, timeout_sec=30):
        return PluginResult(success=True, data={"action": action, "params": params})


def _registry(frames=None):
    reg = PluginRegistry()
    reg.register(_VisionStub(frames))
    reg.register(_GuiStub())
    return reg


def _patch_brains(monkeypatch, reasoner_steps, controller_actions):
    r_state = {"i": 0}; c_state = {"i": 0}

    class _ReasonerProvider:
        def call_validated(self, **kwargs):
            i = r_state["i"]; r_state["i"] = i + 1
            step = reasoner_steps[i] if i < len(reasoner_steps) else StrategicStep(done=True, reason="fin")
            return step, _FakeStats()

    class _ControllerProvider:
        def call_validated(self, **kwargs):
            i = c_state["i"]; c_state["i"] = i + 1
            action = controller_actions[i] if i < len(controller_actions) else ConcreteAction(
                plugin="gui", action="press_key", params={"key": "esc"}, reason="fallback"
            )
            return action, _FakeStats()

    from sunny.brain.factory import BrainRole as _BR

    def fake_get(role):
        if role is _BR.REASONER:
            return _ReasonerProvider()
        if role is _BR.CONTROLLER:
            return _ControllerProvider()
        raise AssertionError(role)

    monkeypatch.setattr(
        "sunny.core.execution.environment_loop.get_provider_for_role",
        fake_get,
    )


def test_run_environment_loop_rejects_invalid_plugin(monkeypatch):
    _patch_brains(
        monkeypatch,
        reasoner_steps=[StrategicStep(intent="hacer cosa", target="x", reason="r")],
        controller_actions=[
            ConcreteAction(plugin="not_a_plugin", action="x", params={}, reason="r"),
        ],
    )
    res = run_environment_loop(
        goal="x", registry=_registry(), max_steps=3, tick_interval_sec=0,
    )
    assert res.stopped_reason == "error"
    assert res.success is False


def test_run_environment_loop_rejects_empty_action(monkeypatch):
    _patch_brains(
        monkeypatch,
        reasoner_steps=[StrategicStep(intent="x", target="x", reason="r")],
        controller_actions=[ConcreteAction(plugin="gui", action="", params={}, reason="r")],
    )
    res = run_environment_loop(
        goal="x", registry=_registry(), max_steps=3, tick_interval_sec=0,
    )
    assert res.stopped_reason == "error"


def test_run_environment_loop_observation_carries_title_and_text(monkeypatch):
    frames = [{"screen_text": "PLAY", "window_title": "Mi Juego"}]
    _patch_brains(
        monkeypatch,
        reasoner_steps=[StrategicStep(done=True, reason="ya")],
        controller_actions=[],
    )
    res = run_environment_loop(
        goal="x", registry=_registry(frames=frames),
        max_steps=2, tick_interval_sec=0,
    )
    assert res.final_observation is not None
    assert res.final_observation.window_title == "Mi Juego"
    assert res.final_observation.screen_text == "PLAY"
    assert res.final_observation.screen_hash != ""


def test_run_environment_loop_detects_screen_change_between_ticks(monkeypatch):
    frames = [
        {"screen_text": "estado A", "window_title": "w"},
        {"screen_text": "estado B", "window_title": "w"},
    ]
    _patch_brains(
        monkeypatch,
        reasoner_steps=[
            StrategicStep(intent="esperar", target="", reason="r"),
            StrategicStep(done=True, reason="cambió"),
        ],
        controller_actions=[
            ConcreteAction(plugin="vision", action="wait_for_screen_text",
                           params={"text": "B", "timeout_sec": 5}, reason="r"),
        ],
    )
    res = run_environment_loop(
        goal="x", registry=_registry(frames=frames),
        max_steps=3, tick_interval_sec=0,
    )
    assert res.success is True
    assert res.ticks_executed == 2
    assert res.final_observation is not None
    assert res.final_observation.screen_text == "estado B"


def test_run_environment_loop_stops_on_negative_deadline(monkeypatch):
    _patch_brains(
        monkeypatch,
        reasoner_steps=[StrategicStep(intent="esperar", target="", reason="r")] * 10,
        controller_actions=[
            ConcreteAction(plugin="vision", action="wait_for_screen_text",
                           params={"text": "X", "timeout_sec": 5}, reason="r")
        ] * 10,
    )
    res = run_environment_loop(
        goal="x", registry=_registry(), max_steps=10,
        tick_interval_sec=0, deadline_sec=-1.0,
    )
    assert res.stopped_reason == "timeout"
    assert res.success is False


def test_run_environment_loop_survives_missing_vision_plugin(monkeypatch):
    _patch_brains(
        monkeypatch,
        reasoner_steps=[StrategicStep(done=True, reason="ya")],
        controller_actions=[],
    )
    reg = PluginRegistry()
    reg.register(_GuiStub())  # sin vision
    res = run_environment_loop(goal="x", registry=reg, max_steps=2, tick_interval_sec=0)
    assert res.success is True
    assert res.final_observation is not None
    assert res.final_observation.screen_text == ""
