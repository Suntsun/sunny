import time
import pytest

from sunny.core.execution.engine import execute_plan
from sunny.core.models.plan import PlanV2, Step
from sunny.core.plugins.base import PluginBase, PluginResult
from sunny.core.plugins.registry import PluginRegistry


class _OkPlugin(PluginBase):
    name = "ok"
    def execute(self, action, params, context, timeout_sec=30):
        return PluginResult(success=True, data={"action": action, "params": params, "ctx": context, "t": timeout_sec})


class _FailPlugin(PluginBase):
    name = "fail"
    def execute(self, action, params, context, timeout_sec=30):
        return PluginResult(success=False, error="boom", error_type="MockError")


class _RaisePlugin(PluginBase):
    name = "raise"
    def execute(self, action, params, context, timeout_sec=30):
        raise RuntimeError("explode")


class _SlowPlugin(PluginBase):
    name = "slow"
    def execute(self, action, params, context, timeout_sec=30):
        time.sleep(2)
        return PluginResult(success=True)


def _step(step_id="s1", plugin="ok", action="do", params=None, continue_on_error=False, timeout_sec=30):
    return Step(step_id=step_id, plugin=plugin, action=action, params=params or {}, continue_on_error=continue_on_error, timeout_sec=timeout_sec, depends_on=[])


def _plan(steps, intent="files"):
    return PlanV2(intent=intent, confidence=0.9, steps=steps)


def test_execute_conversation_plan_returns_success_no_steps():
    r = execute_plan(_plan([], intent="conversation"), PluginRegistry())
    assert r.success and r.steps == [] and not r.early_stopped


def test_execute_simple_ok_plan_returns_success():
    reg = PluginRegistry(); reg.register(_OkPlugin())
    r = execute_plan(_plan([_step()]), reg)
    assert r.success and len(r.steps) == 1 and not r.early_stopped


def test_execute_passes_action_and_params_to_plugin():
    reg = PluginRegistry(); reg.register(_OkPlugin())
    r = execute_plan(_plan([_step(action="my_action", params={"k": "v"})]), reg)
    d = r.steps[0].data
    assert d["action"] == "my_action" and d["params"] == {"k": "v"}


def test_execute_unknown_plugin_returns_error():
    r = execute_plan(_plan([_step(plugin="nope")]), PluginRegistry())
    assert not r.success and r.early_stopped
    assert r.steps[0].error_type == "PluginNotRegistered"


def test_execute_failed_step_triggers_early_stop():
    reg = PluginRegistry(); reg.register(_FailPlugin())
    r = execute_plan(_plan([_step(plugin="fail")]), reg)
    assert not r.success and r.early_stopped
    assert r.steps[0].error == "boom"


def test_execute_failed_with_continue_on_error_no_early_stop():
    reg = PluginRegistry(); reg.register(_FailPlugin()); reg.register(_OkPlugin())
    steps = [_step(plugin="fail", continue_on_error=True), _step(step_id="s2")]
    r = execute_plan(_plan(steps), reg)
    assert r.success and not r.early_stopped
    assert not r.steps[0].success and r.steps[1].success


def test_execute_remaining_skipped_after_early_stop():
    reg = PluginRegistry(); reg.register(_OkPlugin()); reg.register(_FailPlugin())
    steps = [_step(), _step(step_id="s2", plugin="fail"), _step(step_id="s3")]
    r = execute_plan(_plan(steps), reg)
    assert r.early_stopped and not r.success
    assert r.steps[2].skipped and r.steps[2].skip_reason == "early_stop"


def test_execute_step_exception_caught():
    reg = PluginRegistry(); reg.register(_RaisePlugin())
    r = execute_plan(_plan([_step(plugin="raise")]), reg)
    assert not r.success
    assert r.steps[0].error_type == "RuntimeError"


def test_execute_step_timeout():
    reg = PluginRegistry(); reg.register(_SlowPlugin())
    r = execute_plan(_plan([_step(plugin="slow", timeout_sec=1)]), reg)
    assert not r.steps[0].success and r.steps[0].error_type == "TimeoutError"


def test_execute_returns_step_results_in_order():
    reg = PluginRegistry(); reg.register(_OkPlugin())
    steps = [_step("s1"), _step("s2"), _step("s3")]
    r = execute_plan(_plan(steps), reg)
    assert [s.step_id for s in r.steps] == ["s1", "s2", "s3"]


def test_execute_returns_total_latency():
    reg = PluginRegistry(); reg.register(_OkPlugin())
    r = execute_plan(_plan([_step()]), reg)
    assert r.total_latency_ms >= 0


def test_execute_passes_context_to_plugin():
    reg = PluginRegistry(); reg.register(_OkPlugin())
    r = execute_plan(_plan([_step()]), reg, context={"key": "v"})
    assert r.steps[0].data["ctx"] == {"key": "v"}


def test_execute_passes_timeout_sec_to_plugin():
    reg = PluginRegistry(); reg.register(_OkPlugin())
    r = execute_plan(_plan([_step(timeout_sec=7)]), reg)
    assert r.steps[0].data["t"] == 7


def test_execute_step_result_has_step_metadata():
    reg = PluginRegistry(); reg.register(_OkPlugin())
    s = _step("sx")
    r = execute_plan(_plan([s]), reg)
    sr = r.steps[0]
    assert sr.step_id == "sx" and sr.plugin == "ok" and sr.action == "do"


def test_execute_logs_start_and_done(monkeypatch):
    reg = PluginRegistry(); reg.register(_OkPlugin())
    calls = []
    monkeypatch.setattr("sunny.core.execution.engine.log.info", lambda e, **k: calls.append(e))
    execute_plan(_plan([_step()]), reg)
    assert "execution_start" in calls and "execution_done" in calls


def test_execute_logs_early_stop_warning(monkeypatch):
    reg = PluginRegistry(); reg.register(_FailPlugin())
    calls = []
    monkeypatch.setattr("sunny.core.execution.engine.log.warning", lambda e, **k: calls.append(e))
    execute_plan(_plan([_step(plugin="fail")]), reg)
    assert "execution_early_stop" in calls


def test_execute_default_context_is_empty_dict():
    class CtxPlugin(PluginBase):
        name = "ctx"
        def execute(self, action, params, context, timeout_sec=30):
            return PluginResult(True, data=context)

    reg = PluginRegistry(); reg.register(CtxPlugin())
    r = execute_plan(_plan([_step(plugin="ctx")]), reg)
    assert r.steps[0].data == {}
