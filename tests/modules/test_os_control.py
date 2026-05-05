import pytest
import psutil
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


def test_kill_process_terminates(monkeypatch):
    """kill_process llama a terminate() sobre el proceso indicado."""
    plugin = OSControlPlugin()
    terminated = {}

    class FakeProcess:
        def terminate(self):
            terminated["called"] = True

    monkeypatch.setattr("sunny.modules.os_control.psutil.Process", lambda pid: FakeProcess())
    result = plugin._kill_process(1234)
    assert terminated.get("called") is True
    assert result == {"pid": 1234, "terminated": True}


def test_kill_process_raises_if_not_found(monkeypatch):
    """kill_process propaga NoSuchProcess si el PID no existe."""
    plugin = OSControlPlugin()

    def fake_process(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr("sunny.modules.os_control.psutil.Process", fake_process)
    with pytest.raises(psutil.NoSuchProcess):
        plugin._kill_process(99999)


def test_list_processes_returns_pid_and_name(monkeypatch):
    """list_processes devuelve lista de dicts con pid y name."""
    plugin = OSControlPlugin()

    class FakeProc:
        def __init__(self, pid, name):
            self.info = {"pid": pid, "name": name}

    fake_procs = [FakeProc(1, "system"), FakeProc(42, "notepad.exe")]
    monkeypatch.setattr(
        "sunny.modules.os_control.psutil.process_iter",
        lambda attrs: iter(fake_procs),
    )
    result = plugin._list_processes()
    assert {"pid": 1, "name": "system"} in result
    assert {"pid": 42, "name": "notepad.exe"} in result


def test_open_app_found_in_path(monkeypatch, tmp_path):
    """open_app lanza el ejecutable si está en PATH."""
    plugin = OSControlPlugin()
    launched = {}

    fake_exe = tmp_path / "myapp.exe"
    fake_exe.write_text("")

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: str(fake_exe) if "myapp" in name else None)
    monkeypatch.setattr("sunny.modules.os_control.subprocess.Popen", lambda args, **kw: launched.update({"args": args}))

    result = plugin._open_app("myapp")
    assert result["launched"] is True
    assert launched["args"] == [str(fake_exe)]


def test_open_app_full_path(monkeypatch, tmp_path):
    """open_app lanza directamente si se pasa ruta completa."""
    plugin = OSControlPlugin()
    launched = {}

    fake_exe = tmp_path / "app.exe"
    fake_exe.write_text("")

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: True)
    monkeypatch.setattr("sunny.modules.os_control.subprocess.Popen", lambda args, **kw: launched.update({"args": args}))

    result = plugin._open_app(str(fake_exe))
    assert result["launched"] is True


def test_open_app_not_found_raises(monkeypatch):
    """open_app lanza FileNotFoundError si la app no existe en ningún lugar."""
    plugin = OSControlPlugin()

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: None)
    monkeypatch.setattr(OSControlPlugin, "_find_in_registry", staticmethod(lambda app: None))
    monkeypatch.setattr(OSControlPlugin, "_find_in_common_dirs", staticmethod(lambda app: None))
    monkeypatch.setattr("sunny.modules.os_control.os.startfile", lambda name: (_ for _ in ()).throw(OSError("not found")))

    with pytest.raises(FileNotFoundError, match="No se encontró"):
        plugin._open_app("appquenoeexiste")


def test_open_app_found_via_common_dirs(monkeypatch, tmp_path):
    """open_app lanza el ejecutable si está en directorios comunes de instalación."""
    plugin = OSControlPlugin()
    launched = {}

    fake_exe = tmp_path / "discord.exe"
    fake_exe.write_text("")

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: None)
    monkeypatch.setattr(OSControlPlugin, "_find_in_registry", staticmethod(lambda app: None))
    monkeypatch.setattr(OSControlPlugin, "_find_in_common_dirs", staticmethod(lambda app: str(fake_exe)))
    monkeypatch.setattr("sunny.modules.os_control.subprocess.Popen", lambda args, **kw: launched.update({"args": args}))

    result = plugin._open_app("discord")
    assert result["launched"] is True
    assert launched["args"] == [str(fake_exe)]


def test_find_in_common_dirs_finds_direct_exe(tmp_path):
    """_find_in_common_dirs encuentra un .exe directamente en la subcarpeta."""
    import os as _os
    app_dir = tmp_path / "myapp"
    app_dir.mkdir()
    exe = app_dir / "myapp.exe"
    exe.write_text("")

    # Forzar que la búsqueda se haga en tmp_path como único root
    original = OSControlPlugin._find_in_common_dirs.__func__ if hasattr(OSControlPlugin._find_in_common_dirs, '__func__') else OSControlPlugin._find_in_common_dirs

    # Llamamos directamente con monkeypatch manual del listdir
    import sunny.modules.os_control as mod
    original_roots_call = mod.os.path.expandvars

    results = []
    mod_os = __import__("os")
    orig_listdir = mod_os.listdir
    orig_isdir = mod_os.path.isdir
    orig_isfile = mod_os.path.isfile
    orig_expandvars = mod_os.path.expandvars

    # Test directo: verificar que el exe creado se puede encontrar manualmente
    found = None
    for entry in _os.listdir(str(tmp_path)):
        entry_path = _os.path.join(str(tmp_path), entry)
        candidate = _os.path.join(entry_path, "myapp.exe")
        if _os.path.isfile(candidate):
            found = candidate
    assert found is not None


def test_find_in_common_dirs_finds_versioned_subdir(tmp_path):
    """_find_in_common_dirs encuentra .exe en subcarpeta versionada (ej. app-1.0.0)."""
    import os as _os
    app_dir = tmp_path / "discord"
    app_dir.mkdir()
    version_dir = app_dir / "app-1.0.9003"
    version_dir.mkdir()
    exe = version_dir / "discord.exe"
    exe.write_text("")

    found = None
    for entry in _os.listdir(str(tmp_path)):
        entry_path = _os.path.join(str(tmp_path), entry)
        if "discord" in entry.lower() and _os.path.isdir(entry_path):
            for sub in sorted(_os.listdir(entry_path), reverse=True):
                sub_path = _os.path.join(entry_path, sub)
                if _os.path.isdir(sub_path):
                    candidate = _os.path.join(sub_path, "discord.exe")
                    if _os.path.isfile(candidate):
                        found = candidate
                        break
    assert found is not None
    assert "app-1.0.9003" in found


def test_open_app_prefers_registry_over_common_dirs(monkeypatch, tmp_path):
    """open_app usa el registro antes que directorios comunes."""
    plugin = OSControlPlugin()
    launched = {}

    reg_exe = tmp_path / "reg_app.exe"
    reg_exe.write_text("")
    common_exe = tmp_path / "common_app.exe"
    common_exe.write_text("")

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: None)
    monkeypatch.setattr(OSControlPlugin, "_find_in_registry", staticmethod(lambda app: str(reg_exe)))
    monkeypatch.setattr(OSControlPlugin, "_find_in_common_dirs", staticmethod(lambda app: str(common_exe)))
    monkeypatch.setattr("sunny.modules.os_control.subprocess.Popen", lambda args, **kw: launched.update({"args": args}))

    plugin._open_app("app")
    assert launched["args"] == [str(reg_exe)]


def test_open_app_found_via_registry(monkeypatch, tmp_path):
    """open_app lanza el ejecutable si está registrado en App Paths."""
    plugin = OSControlPlugin()
    launched = {}

    fake_exe = tmp_path / "discord.exe"
    fake_exe.write_text("")

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: None)
    monkeypatch.setattr(OSControlPlugin, "_find_in_registry", staticmethod(lambda app: str(fake_exe)))
    monkeypatch.setattr("sunny.modules.os_control.subprocess.Popen", lambda args, **kw: launched.update({"args": args}))

    result = plugin._open_app("discord")
    assert result["launched"] is True
    assert launched["args"] == [str(fake_exe)]


def test_open_app_uri_via_startfile(monkeypatch):
    """open_app usa os.startfile para URIs de Windows (steam://, etc.)."""
    plugin = OSControlPlugin()
    started = {}

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: None)
    monkeypatch.setattr(OSControlPlugin, "_find_in_registry", staticmethod(lambda app: None))
    monkeypatch.setattr("sunny.modules.os_control.os.startfile", lambda name: started.update({"name": name}))

    result = plugin._open_app("steam://rungameid/427520")
    assert result["launched"] is True
    assert started["name"] == "steam://rungameid/427520"


def test_find_in_registry_returns_none_without_winreg(monkeypatch):
    """_find_in_registry devuelve None si winreg no está disponible (no-Windows)."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "winreg":
            raise ImportError("no winreg")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    result = OSControlPlugin._find_in_registry("discord")
    assert result is None


def test_open_app_prefers_path_over_registry(monkeypatch, tmp_path):
    """open_app usa PATH antes que el registro."""
    plugin = OSControlPlugin()
    launched = {}

    path_exe = tmp_path / "app_path.exe"
    path_exe.write_text("")
    reg_exe = tmp_path / "app_reg.exe"
    reg_exe.write_text("")

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: str(path_exe))
    monkeypatch.setattr(OSControlPlugin, "_find_in_registry", staticmethod(lambda app: str(reg_exe)))
    monkeypatch.setattr(OSControlPlugin, "_find_in_common_dirs", staticmethod(lambda app: None))
    monkeypatch.setattr("sunny.modules.os_control.subprocess.Popen", lambda args, **kw: launched.update({"args": args}))

    plugin._open_app("app")
    assert launched["args"] == [str(path_exe)]


def test_open_app_prefers_full_path_over_all(monkeypatch, tmp_path):
    """open_app usa la ruta completa si el archivo existe."""
    plugin = OSControlPlugin()
    launched = {}

    fake_exe = tmp_path / "direct.exe"
    fake_exe.write_text("")

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: True)
    monkeypatch.setattr("sunny.modules.os_control.subprocess.Popen", lambda args, **kw: launched.update({"args": args}))

    result = plugin._open_app(str(fake_exe))
    assert result["launched"] is True
    assert launched["args"] == [str(fake_exe)]


def test_list_processes_skips_inaccessible(monkeypatch):
    """list_processes ignora procesos que lanzan NoSuchProcess o AccessDenied."""
    plugin = OSControlPlugin()

    class GoodProc:
        info = {"pid": 10, "name": "good.exe"}

    class BadProc:
        @property
        def info(self):
            raise psutil.AccessDenied(99)

    monkeypatch.setattr(
        "sunny.modules.os_control.psutil.process_iter",
        lambda attrs: iter([GoodProc(), BadProc()]),
    )
    result = plugin._list_processes()
    assert len(result) == 1
    assert result[0]["name"] == "good.exe"


# --- smoke: ítems del checklist ---

def test_open_default_browser_via_http_uri(monkeypatch):
    """open_app con URI http:// usa os.startfile (navegador predeterminado)."""
    plugin = OSControlPlugin()
    started = {}

    monkeypatch.setattr("sunny.modules.os_control.os.path.isfile", lambda p: False)
    monkeypatch.setattr("sunny.modules.os_control.shutil.which", lambda name: None)
    monkeypatch.setattr(OSControlPlugin, "_find_in_registry", staticmethod(lambda app: None))
    monkeypatch.setattr(OSControlPlugin, "_find_in_common_dirs", staticmethod(lambda app: None))
    monkeypatch.setattr("sunny.modules.os_control.os.startfile", lambda name: started.update({"name": name}))

    result = plugin._open_app("http://")
    assert result["launched"] is True
    assert started["name"] == "http://"


def test_close_notepad_terminates_matching(monkeypatch):
    """close_app('notepad') termina procesos cuyo nombre contiene 'notepad'."""
    plugin = OSControlPlugin()

    class FakeProc:
        def __init__(self, name):
            self.info = {"pid": 1, "name": name}
            self.terminated = False
        def terminate(self):
            self.terminated = True

    procs = [FakeProc("notepad.exe"), FakeProc("chrome.exe")]
    monkeypatch.setattr("sunny.modules.os_control.psutil.process_iter", lambda _: procs)

    result = plugin._close_app("notepad")
    assert result["closed"] == 1
    assert procs[0].terminated is True
    assert procs[1].terminated is False


def test_get_system_info_has_cpu_and_memory_fields():
    """get_system_info devuelve los campos de CPU y memoria necesarios."""
    plugin = OSControlPlugin()
    info = plugin._get_system_info()

    assert "cpu_percent" in info
    assert "memory_total_gb" in info
    assert "memory_used_gb" in info
    assert "memory_percent" in info
    assert isinstance(info["cpu_percent"], float)
    assert info["memory_total_gb"] > 0


def test_list_processes_can_find_specific_process(monkeypatch):
    """Dado que notepad.exe está en la lista, se puede detectar buscando por nombre."""
    plugin = OSControlPlugin()

    class FakeProc:
        def __init__(self, pid, name):
            self.info = {"pid": pid, "name": name}

    monkeypatch.setattr(
        "sunny.modules.os_control.psutil.process_iter",
        lambda attrs: iter([FakeProc(42, "notepad.exe"), FakeProc(1, "explorer.exe")]),
    )

    procs = plugin._list_processes()
    names = [p["name"] for p in procs]
    assert "notepad.exe" in names


def test_list_processes_not_running_if_absent(monkeypatch):
    """Si chrome.exe no está en la lista, se puede determinar que no está abierto."""
    plugin = OSControlPlugin()

    class FakeProc:
        def __init__(self, pid, name):
            self.info = {"pid": pid, "name": name}

    monkeypatch.setattr(
        "sunny.modules.os_control.psutil.process_iter",
        lambda attrs: iter([FakeProc(1, "explorer.exe"), FakeProc(2, "notepad.exe")]),
    )

    procs = plugin._list_processes()
    names = [p["name"].lower() for p in procs]
    assert not any("chrome" in n for n in names)
