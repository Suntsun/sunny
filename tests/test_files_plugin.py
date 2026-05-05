import pytest
from pathlib import Path

from sunny.modules.files import FilesPlugin


@pytest.fixture
def plugin():
    return FilesPlugin()


def test_unsupported_action_returns_error(plugin):
    r = plugin.execute("foo", {}, {})
    assert not r.success and r.error_type == "UnsupportedAction"


def test_read_file_existing(tmp_path, plugin):
    p = tmp_path / "a.txt"
    p.write_text("hola", encoding="utf-8")
    r = plugin.execute("read_file", {"path": str(p)}, {})
    assert r.success and r.data == "hola"


def test_read_file_nonexistent_returns_error(tmp_path, plugin):
    r = plugin.execute("read_file", {"path": str(tmp_path / "x.txt")}, {})
    assert not r.success and r.error_type == "FileNotFoundError"


def test_write_file_creates_parent_dirs(tmp_path, plugin):
    p = tmp_path / "a" / "b.txt"
    r = plugin.execute("write_file", {"path": str(p), "content": "x"}, {})
    assert p.exists() and r.success


def test_write_file_overwrites(tmp_path, plugin):
    p = tmp_path / "a.txt"
    plugin.execute("write_file", {"path": str(p), "content": "1"}, {})
    plugin.execute("write_file", {"path": str(p), "content": "2"}, {})
    assert p.read_text() == "2"


def test_write_file_returns_bytes_count(tmp_path, plugin):
    p = tmp_path / "a.txt"
    r = plugin.execute("write_file", {"path": str(p), "content": "á"}, {})
    assert r.data["bytes_written"] == len("á".encode("utf-8"))


def test_list_directory_basic(tmp_path, plugin):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    (tmp_path / "d").mkdir()
    r = plugin.execute("list_directory", {"path": str(tmp_path)}, {})
    assert r.success
    assert r.data["total_entries"] == 3
    assert len(r.data["files"]) == 2
    assert len(r.data["directories"]) == 1


def test_list_directory_nonexistent_returns_error(tmp_path, plugin):
    r = plugin.execute("list_directory", {"path": str(tmp_path / "x")}, {})
    assert not r.success


def test_move_file(tmp_path, plugin):
    src = tmp_path / "a.txt"
    dst = tmp_path / "b.txt"
    src.write_text("x")
    plugin.execute("move", {"src": str(src), "dst": str(dst)}, {})
    assert dst.exists() and not src.exists()


def test_copy_file(tmp_path, plugin):
    src = tmp_path / "a.txt"
    dst = tmp_path / "b.txt"
    src.write_text("x")
    plugin.execute("copy", {"src": str(src), "dst": str(dst)}, {})
    assert src.exists() and dst.exists()


def test_copy_directory(tmp_path, plugin):
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.txt").write_text("x")
    dst = tmp_path / "d2"
    plugin.execute("copy", {"src": str(d), "dst": str(dst)}, {})
    assert (dst / "a.txt").exists()


def test_delete_calls_send2trash(monkeypatch, plugin):
    called = {}
    monkeypatch.setattr("sunny.modules.files.send2trash", lambda p: called.setdefault("p", p))
    plugin.execute("delete", {"path": "/tmp/x"}, {})
    assert called["p"] == str(Path("/tmp/x"))


def test_search_finds_files(tmp_path, plugin):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    (tmp_path / "c.log").write_text("z")
    r = plugin.execute("search", {"directory": str(tmp_path), "pattern": "*.txt"}, {})
    assert len(r.data) == 2


def test_search_recursive(tmp_path, plugin):
    d = tmp_path / "sub"
    d.mkdir()
    (d / "a.txt").write_text("x")
    r = plugin.execute("search", {"directory": str(tmp_path), "pattern": "*.txt", "recursive": True}, {})
    assert len(r.data) == 1


def test_get_info_existing_file(tmp_path, plugin):
    p = tmp_path / "a.txt"
    p.write_text("x")
    r = plugin.execute("get_info", {"path": str(p)}, {})
    assert r.data["exists"] and r.data["is_file"]


def test_get_info_directory(tmp_path, plugin):
    r = plugin.execute("get_info", {"path": str(tmp_path)}, {})
    assert r.data["is_dir"]


def test_get_info_nonexistent(tmp_path, plugin):
    r = plugin.execute("get_info", {"path": str(tmp_path / "x")}, {})
    assert not r.data["exists"] and r.data["size"] == 0


def test_empty_recycle_bin_calls_shell32(monkeypatch, plugin):
    class S:
        def SHEmptyRecycleBinW(self, a, b, c): return 0
    monkeypatch.setattr("sunny.modules.files.ctypes.windll", type("W", (), {"shell32": S()})())
    r = plugin.execute("empty_recycle_bin", {}, {})
    assert r.success


def test_empty_recycle_bin_error_propagates(monkeypatch, plugin):
    class S:
        def SHEmptyRecycleBinW(self, a, b, c): return 1
    monkeypatch.setattr("sunny.modules.files.ctypes.windll", type("W", (), {"shell32": S()})())
    r = plugin.execute("empty_recycle_bin", {}, {})
    assert not r.success and r.error_type == "RuntimeError"


def test_restore_from_recycle_bin_returns_not_implemented(plugin):
    r = plugin.execute("restore_from_recycle_bin", {"filename": "x"}, {})
    assert not r.success and r.error_type == "NotImplementedError"


def test_execute_logs_action(monkeypatch, plugin, tmp_path):
    calls = []
    monkeypatch.setattr("sunny.modules.files.log.info", lambda e, **k: calls.append(e))
    p = tmp_path / "a.txt"
    plugin.execute("write_file", {"path": str(p), "content": "x"}, {})
    assert "files_action_done" in calls


def test_plugin_name_is_files(plugin):
    assert plugin.name == "files"


def test_list_directory_expands_env_vars(monkeypatch, tmp_path, plugin):
    monkeypatch.setenv("MYSUNNYTEST", str(tmp_path))
    (tmp_path / "a.txt").write_text("x")
    r = plugin.execute("list_directory", {"path": "%MYSUNNYTEST%"}, {})
    assert r.success
    assert any(f["name"] == "a.txt" for f in r.data["files"])


def test_read_file_expands_env_vars(monkeypatch, tmp_path, plugin):
    monkeypatch.setenv("MYSUNNYFILE", str(tmp_path / "b.txt"))
    (tmp_path / "b.txt").write_text("hola", encoding="utf-8")
    r = plugin.execute("read_file", {"path": "%MYSUNNYFILE%"}, {})
    assert r.success and r.data == "hola"


def test_write_file_resolves_path_in_returned_dict(monkeypatch, tmp_path, plugin):
    monkeypatch.setenv("MYSUNNYWRITE", str(tmp_path / "c.txt"))
    r = plugin.execute("write_file", {"path": "%MYSUNNYWRITE%", "content": "x"}, {})
    assert r.success
    assert "%" not in r.data["path"]


def test_get_info_expands_env_vars(monkeypatch, tmp_path, plugin):
    monkeypatch.setenv("MYSUNNYINFO", str(tmp_path))
    r = plugin.execute("get_info", {"path": "%MYSUNNYINFO%"}, {})
    assert r.success and r.data["is_dir"]


def test_create_directory_creates_path(tmp_path, plugin):
    target = tmp_path / "newdir"
    r = plugin.execute("create_directory", {"path": str(target)}, {})
    assert r.success
    assert target.exists() and target.is_dir()


def test_create_directory_idempotent(tmp_path, plugin):
    target = tmp_path / "exists"
    target.mkdir()
    r = plugin.execute("create_directory", {"path": str(target)}, {})
    assert r.success


def test_create_directory_expands_env_vars(monkeypatch, tmp_path, plugin):
    monkeypatch.setenv("MYSUNNYDIR", str(tmp_path / "envdir"))
    r = plugin.execute("create_directory", {"path": "%MYSUNNYDIR%"}, {})
    assert r.success
    assert (tmp_path / "envdir").exists()
