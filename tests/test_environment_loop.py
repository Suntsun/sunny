"""Tests core del bucle de entorno (perception→reasoner→controller)."""
from typing import List

from sunny.core.execution.environment_loop import (
    ConcreteAction,
    EnvironmentLoopResult,
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
        self.frames = frames or [{"screen_text": "estado A", "window_title": "Untitled - Notepad"}]
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

    def __init__(self):
        self.calls: List[tuple] = []

    def execute(self, action, params, context, timeout_sec=30):
        self.calls.append((action, dict(params)))
        return PluginResult(success=True, data={"action": action, "params": params})


def _registry(frames=None):
    reg = PluginRegistry()
    reg.register(_VisionStub(frames))
    reg.register(_GuiStub())
    return reg


def _patch_brains(monkeypatch, reasoner_steps: List[StrategicStep], controller_actions: List[ConcreteAction]):
    r_state = {"i": 0}
    c_state = {"i": 0}

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
        raise AssertionError(f"rol inesperado: {role}")

    monkeypatch.setattr(
        "sunny.core.execution.environment_loop.get_provider_for_role",
        fake_get,
    )


def test_run_environment_loop_reaches_goal_on_first_tick(monkeypatch):
    _patch_brains(
        monkeypatch,
        reasoner_steps=[StrategicStep(done=True, reason="ya cumplido")],
        controller_actions=[],
    )
    res = run_environment_loop(
        goal="abrir Notepad", registry=_registry(),
        max_steps=5, tick_interval_sec=0,
    )
    assert isinstance(res, EnvironmentLoopResult)
    assert res.success is True
    assert res.stopped_reason == "goal_reached"
    assert res.ticks_executed == 1
    assert len(res.steps_executed) == 0


def test_run_environment_loop_reaches_goal_after_action(monkeypatch):
    _patch_brains(
        monkeypatch,
        reasoner_steps=[
            StrategicStep(intent="escribir texto", target="cuerpo del documento", reason="primero"),
            StrategicStep(done=True, reason="hecho"),
        ],
        controller_actions=[
            ConcreteAction(plugin="gui", action="type_text", params={"text": "hola"}, reason="x"),
        ],
    )
    res = run_environment_loop(
        goal="escribir hola en Notepad", registry=_registry(),
        max_steps=5, tick_interval_sec=0,
    )
    assert res.success is True
    assert res.stopped_reason == "goal_reached"
    assert len(res.steps_executed) == 1
    assert res.steps_executed[0].plugin == "gui"
    assert res.steps_executed[0].action == "type_text"


def test_run_environment_loop_stops_at_max_steps(monkeypatch):
    _patch_brains(
        monkeypatch,
        reasoner_steps=[
            StrategicStep(intent="esperar", target="", reason="todavía no") for _ in range(10)
        ],
        controller_actions=[
            ConcreteAction(plugin="vision", action="wait_for_screen_text",
                           params={"text": "X", "timeout_sec": 5}, reason="x") for _ in range(10)
        ],
    )
    res = run_environment_loop(
        goal="nunca cumplible", registry=_registry(),
        max_steps=3, tick_interval_sec=0,
    )
    assert res.stopped_reason == "max_steps"
    assert res.success is False
    assert res.ticks_executed == 3
    assert len(res.steps_executed) == 3


def test_run_environment_loop_stops_on_reasoner_error(monkeypatch):
    from sunny.brain.ollama_client import LLMError

    class _BoomReasoner:
        def call_validated(self, **kwargs):
            raise LLMError("reasoner caído")

    from sunny.brain.factory import BrainRole as _BR

    def fake_get(role):
        if role is _BR.REASONER:
            return _BoomReasoner()
        raise AssertionError(role)

    monkeypatch.setattr(
        "sunny.core.execution.environment_loop.get_provider_for_role",
        fake_get,
    )
    res = run_environment_loop(
        goal="x", registry=_registry(),
        max_steps=3, tick_interval_sec=0,
    )
    assert res.stopped_reason == "error"
    assert res.success is False


def test_run_environment_loop_result_has_known_stopped_reason(monkeypatch):
    _patch_brains(
        monkeypatch,
        reasoner_steps=[StrategicStep(done=True, reason="ok")],
        controller_actions=[],
    )
    res = run_environment_loop(
        goal="x", registry=_registry(), max_steps=2, tick_interval_sec=0,
    )
    assert res.stopped_reason in {"goal_reached", "max_steps", "error", "user_cancelled", "timeout"}
