import pytest

from sunny.core.plugins.base import PluginBase, PluginResult
from sunny.core.plugins.registry import PluginRegistry


class _DummyPlugin(PluginBase):
    name = "dummy"

    def execute(self, action, params, context, timeout_sec=30):
        return PluginResult(success=True, data=action)


class _AnotherPlugin(PluginBase):
    name = "another"

    def execute(self, action, params, context, timeout_sec=30):
        return PluginResult(success=True, data="other")


def test_plugin_result_default_values():
    r = PluginResult(success=True)
    assert r.data is None and r.error is None and r.error_type is None


def test_plugin_result_success_fields():
    r = PluginResult(success=True, data={"k": "v"})
    assert r.success and r.data == {"k": "v"}


def test_plugin_result_error_fields():
    r = PluginResult(success=False, error="boom", error_type="ValueError")
    assert not r.success and r.error == "boom" and r.error_type == "ValueError"


def test_plugin_base_is_abstract():
    with pytest.raises(TypeError):
        PluginBase()


def test_concrete_subclass_can_be_instantiated():
    _DummyPlugin()


def test_concrete_subclass_executes():
    p = _DummyPlugin()
    res = p.execute("a", {}, {})
    assert res.success and res.data == "a"


def test_subclass_without_execute_raises():
    class Bad(PluginBase):
        name = "bad"
    with pytest.raises(TypeError):
        Bad()


def test_registry_starts_empty():
    r = PluginRegistry()
    assert r.list_plugins() == []


def test_register_and_get_plugin():
    r = PluginRegistry()
    p = _DummyPlugin()
    r.register(p)
    assert r.get("dummy") is p


def test_register_empty_name_raises():
    class Bad(PluginBase):
        name = ""
        def execute(self, action, params, context, timeout_sec=30):
            return PluginResult(True)
    r = PluginRegistry()
    with pytest.raises(ValueError):
        r.register(Bad())


def test_register_duplicate_raises():
    r = PluginRegistry()
    p = _DummyPlugin()
    r.register(p)
    with pytest.raises(ValueError):
        r.register(p)


def test_register_two_different_plugins():
    r = PluginRegistry()
    r.register(_DummyPlugin())
    r.register(_AnotherPlugin())
    assert r.list_plugins() == ["another", "dummy"]


def test_get_unregistered_returns_none():
    r = PluginRegistry()
    assert r.get("nope") is None


def test_is_registered_true():
    r = PluginRegistry()
    r.register(_DummyPlugin())
    assert r.is_registered("dummy")


def test_is_registered_false():
    r = PluginRegistry()
    assert not r.is_registered("dummy")


def test_list_plugins_sorted():
    r = PluginRegistry()
    r.register(_DummyPlugin())
    r.register(_AnotherPlugin())
    assert r.list_plugins() == ["another", "dummy"]


def test_unregister_removes_plugin():
    r = PluginRegistry()
    r.register(_DummyPlugin())
    r.unregister("dummy")
    assert not r.is_registered("dummy")


def test_unregister_unknown_raises():
    r = PluginRegistry()
    with pytest.raises(KeyError):
        r.unregister("nope")


def test_clear_removes_all():
    r = PluginRegistry()
    r.register(_DummyPlugin())
    r.register(_AnotherPlugin())
    r.clear()
    assert r.list_plugins() == []


def test_register_logs_event(monkeypatch):
    r = PluginRegistry()
    calls = []
    monkeypatch.setattr("sunny.core.plugins.registry.log.info", lambda event, **k: calls.append(event))
    r.register(_DummyPlugin())
    assert "plugin_registered" in calls


def test_unregister_logs_event(monkeypatch):
    r = PluginRegistry()
    p = _DummyPlugin()
    r.register(p)
    calls = []
    monkeypatch.setattr("sunny.core.plugins.registry.log.info", lambda event, **k: calls.append(event))
    r.unregister("dummy")
    assert "plugin_unregistered" in calls
