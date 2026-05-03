import pytest

from sunny.core.plugins.base import PluginResult
from sunny.modules.ai_bridge.backends import AIBackend, StubBackend
from sunny.modules.ai_bridge.plugin import AIBridgePlugin, SUPPORTED_PROVIDERS


@pytest.fixture
def plugin():
    return AIBridgePlugin()


class _FakeBackend(AIBackend):
    def __init__(self, response="fake response"):
        self._response = response

    def ask(self, prompt):
        return f"{self._response}: {prompt}"


def test_unsupported_action_returns_error(plugin):
    r = plugin.execute("foo", {}, {})
    assert not r.success and r.error_type == "UnsupportedAction"


def test_plugin_name(plugin):
    assert plugin.name == "ai_bridge"


def test_supported_providers_constant():
    assert SUPPORTED_PROVIDERS == ("chatgpt", "deepseek", "gemini")


def test_default_backends_are_stubs(plugin):
    for p in SUPPORTED_PROVIDERS:
        assert isinstance(plugin._backends[p], StubBackend)


def test_ask_external_unknown_provider_raises(plugin):
    r = plugin.execute("ask_external", {"provider": "nope", "prompt": "x"}, {})
    assert not r.success and r.error_type == "ValueError"


def test_ask_external_chatgpt_not_implemented_in_v1(plugin):
    r = plugin.execute("ask_external", {"provider": "chatgpt", "prompt": "x"}, {})
    assert not r.success and r.error_type == "NotImplementedError"


def test_ask_external_deepseek_not_implemented_in_v1(plugin):
    r = plugin.execute("ask_external", {"provider": "deepseek", "prompt": "x"}, {})
    assert not r.success and r.error_type == "NotImplementedError"


def test_ask_external_gemini_not_implemented_in_v1(plugin):
    r = plugin.execute("ask_external", {"provider": "gemini", "prompt": "x"}, {})
    assert not r.success and r.error_type == "NotImplementedError"


def test_ask_external_with_custom_backend_works():
    plugin = AIBridgePlugin(backends={"fake": _FakeBackend()})
    r = plugin.execute("ask_external", {"provider": "fake", "prompt": "hola"}, {})
    assert r.success
    assert r.data["provider"] == "fake"
    assert "hola" in r.data["response"]


def test_aibackend_is_abstract():
    with pytest.raises(TypeError):
        AIBackend()


def test_stub_backend_raises_not_implemented_with_provider_name():
    b = StubBackend("foo")
    with pytest.raises(NotImplementedError) as e:
        b.ask("x")
    assert "foo" in str(e.value)


def test_execute_logs_action(monkeypatch, plugin):
    calls = []
    monkeypatch.setattr("sunny.modules.ai_bridge.plugin.log.info", lambda e, **k: calls.append(e))
    plugin.execute("ask_external", {"provider": "chatgpt", "prompt": "x"}, {})
    assert "ai_bridge_action_done" in calls
