import pytest
from sunny.modules.os_control import OSControlPlugin


@pytest.fixture
def plugin():
    return OSControlPlugin()


def test_unsupported_action_returns_error(plugin):
    r = plugin.execute("foo", {}, {})
    assert not r.success and r.error_type == "UnsupportedAction"


def test_plugin_name(plugin):
    assert plugin.name == "os_control"


def test_open_app_found_via_which(monkeypatch, plugin):
    """open_app tiene éxito si el ejecutable está en PATH."""
    called = {}
    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: "/usr/bin/chrome" if "chrome" in name else None)
    monkeypatch.setattr("sunny.modules.os_control.subprocess.Popen", lambda args, **kw: called.update({"args": args}))
    monkeypatch.setattr(OSControlPlugin, "_find_in_registry", staticmethod(lambda app: None))
    monkeypatch.setattr(OSControlPlugin, "_find_in_common_dirs", staticmethod(lambda app: None))
    r = plugin.execute("open_app", {"app": "chrome"}, {})
    assert r.success
    assert called["args"] == ["/usr/bin/chrome"]


def test_open_app_not_found_returns_error(monkeypatch, plugin):
    """open_app devuelve error si la app no existe en ningún lugar."""
    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: None)
    monkeypatch.setattr("sunny.modules.os_control.os.startfile", lambda name: (_ for _ in ()).throw(OSError()))
    r = plugin.execute("open_app", {"app": "appquenoeexiste"}, {})
    assert not r.success
    assert r.error_type == "FileNotFoundError"


def test_close_app_terminates_matching(monkeypatch, plugin):
    class P:
        def __init__(self, name):
            self.info = {"pid": 1, "name": name}
            self.terminated = False
        def terminate(self):
            self.terminated = True

    procs = [P("chrome.exe"), P("firefox.exe")]
    monkeypatch.setattr("sunny.modules.os_control.psutil.process_iter", lambda _: procs)

    r = plugin.execute("close_app", {"app": "chrome"}, {})
    assert r.success and r.data["closed"] == 1
    assert procs[0].terminated and not procs[1].terminated


def test_close_app_not_found_returns_error(monkeypatch, plugin):
    class P:
        def __init__(self):
            self.info = {"pid": 1, "name": "firefox.exe"}
        def terminate(self): pass

    monkeypatch.setattr("sunny.modules.os_control.psutil.process_iter", lambda _: [P()])
    r = plugin.execute("close_app", {"app": "chrome"}, {})
    assert not r.success and r.error_type == "FileNotFoundError"


def test_list_processes_returns_list(monkeypatch, plugin):
    class P:
        def __init__(self, pid, name):
            self.info = {"pid": pid, "name": name}

    monkeypatch.setattr(
        "sunny.modules.os_control.psutil.process_iter",
        lambda _: [P(1, "a"), P(2, "b")],
    )
    r = plugin.execute("list_processes", {}, {})
    assert r.success and len(r.data) == 2


def test_kill_process_calls_terminate(monkeypatch, plugin):
    called = []
    class P:
        def __init__(self, pid): self.pid = pid
        def terminate(self): called.append(self.pid)

    monkeypatch.setattr("sunny.modules.os_control.psutil.Process", P)
    r = plugin.execute("kill_process", {"pid": 123}, {})
    assert r.success and 123 in called


def test_kill_process_pid_not_found(monkeypatch, plugin):
    def bad(pid):
        raise Exception("nope")
    monkeypatch.setattr("sunny.modules.os_control.psutil.Process", bad)
    r = plugin.execute("kill_process", {"pid": 1}, {})
    assert not r.success


def test_set_volume_not_implemented(plugin):
    r = plugin.execute("set_volume", {"level": 10}, {})
    assert not r.success and r.error_type == "NotImplementedError"


def test_mute_not_implemented(plugin):
    r = plugin.execute("mute", {"state": True}, {})
    assert not r.success and r.error_type == "NotImplementedError"


def test_lock_screen_success(monkeypatch, plugin):
    class U:
        def LockWorkStation(self): return 1
    monkeypatch.setattr("sunny.modules.os_control.ctypes.windll", type("W", (), {"user32": U()})())
    r = plugin.execute("lock_screen", {}, {})
    assert r.success and r.data["locked"]


def test_lock_screen_failure(monkeypatch, plugin):
    class U:
        def LockWorkStation(self): return 0
    monkeypatch.setattr("sunny.modules.os_control.ctypes.windll", type("W", (), {"user32": U()})())
    r = plugin.execute("lock_screen", {}, {})
    assert not r.success and r.error_type == "RuntimeError"


def test_shutdown_calls_subprocess(monkeypatch, plugin):
    called = {}
    def fake_run(args, check, capture_output):
        called["args"] = args
    monkeypatch.setattr("sunny.modules.os_control.subprocess.run", fake_run)
    r = plugin.execute("shutdown", {"delay_sec": 60}, {})
    assert r.success and called["args"] == ["shutdown", "/s", "/t", "60"]


def test_restart_calls_subprocess(monkeypatch, plugin):
    called = {}
    def fake_run(args, check, capture_output):
        called["args"] = args
    monkeypatch.setattr("sunny.modules.os_control.subprocess.run", fake_run)
    r = plugin.execute("restart", {"delay_sec": 30}, {})
    assert r.success and called["args"] == ["shutdown", "/r", "/t", "30"]


def test_get_system_info_returns_dict(plugin):
    r = plugin.execute("get_system_info", {}, {})
    assert r.success and "platform" in r.data and "cpu_count" in r.data


def test_execute_logs_action(monkeypatch, plugin):
    events = []
    monkeypatch.setattr("sunny.modules.os_control.log.info", lambda *a, **k: events.append(a[0]))
    plugin.execute("set_volume", {"level": 1}, {})
    assert "os_control_action_done" in events
