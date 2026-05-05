def test_resolve_path_expands_cd(monkeypatch):
    from sunny.modules.files import FilesPlugin
    plugin = FilesPlugin()
    monkeypatch.setenv("CD", r"C:\fake\dir")
    p = plugin._resolve_path(r"%CD%\saludo.txt")
    assert str(p) == r"C:\fake\dir\saludo.txt"


def test_resolve_path_expands_temp(monkeypatch):
    from sunny.modules.files import FilesPlugin
    plugin = FilesPlugin()
    monkeypatch.setenv("TEMP", r"C:\fake\temp")
    p = plugin._resolve_path(r"%TEMP%\foo.txt")
    assert str(p) == r"C:\fake\temp\foo.txt"


def test_search_non_recursive_excludes_subdirs(tmp_path):
    from pathlib import Path
    from sunny.modules.files import FilesPlugin
    (tmp_path / "root.txt").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("x")

    plugin = FilesPlugin()
    results = plugin._search(str(tmp_path), "*.txt", recursive=False)

    names = [Path(r).name for r in results]
    assert "root.txt" in names
    assert "nested.txt" not in names
