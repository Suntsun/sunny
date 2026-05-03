import pytest
from sunny.modules.os_control import OSControlPlugin


def test_sleep_seconds_calls_time_sleep(monkeypatch):
    plugin = OSControlPlugin()
    called = {}
    def fake_sleep(seconds):
        called["seconds"] = seconds
    monkeypatch.setattr("sunny.modules.os_control.time.sleep", fake_sleep)
    plugin._sleep_seconds(3)
    assert called["seconds"] == 3


def test_sleep_seconds_zero_does_not_fail(monkeypatch):
    plugin = OSControlPlugin()
    monkeypatch.setattr("sunny.modules.os_control.time.sleep", lambda x: None)
    plugin._sleep_seconds(0)
