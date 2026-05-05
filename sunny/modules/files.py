from __future__ import annotations

import ctypes
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

from send2trash import send2trash

from sunny.core.logging.logger import get_logger
from sunny.core.plugins.base import PluginBase, PluginResult

log = get_logger("sunny.modules.files")


class FilesPlugin(PluginBase):
    """Plugin de gestión de archivos."""

    name: str = "files"

    def __init__(self) -> None:
        self._actions: Dict[str, Callable[..., Any]] = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_directory": self._list_directory,
            "create_directory": self._create_directory,
            "tree_directory": self._tree_directory,
            "move": self._move,
            "copy": self._copy,
            "delete": self._delete,
            "search": self._search,
            "delete_matching": self._delete_matching,
            "get_info": self._get_info,
            "empty_recycle_bin": self._empty_recycle_bin,
            "restore_from_recycle_bin": self._restore_from_recycle_bin,
        }

    def execute(self, action, params, context, timeout_sec=30) -> PluginResult:
        if action not in self._actions:
            return PluginResult(
                success=False,
                error=f"action '{action}' no soportada por files",
                error_type="UnsupportedAction",
            )
        try:
            data = self._actions[action](**params)
            res = PluginResult(success=True, data=data)
        except Exception as e:
            res = PluginResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )
        log.info("files_action_done", action=action, success=res.success)
        return res

    def _resolve_path(self, path: str) -> Path:
        """Resuelve rutas expandiendo variables de entorno y usuario."""
        expanded = os.path.expandvars(path)
        expanded = os.path.expanduser(expanded)
        return Path(expanded)

    def _read_file(self, path: str) -> str:
        p = self._resolve_path(path)
        return p.read_text(encoding="utf-8")

    def _write_file(self, path: str, content: str) -> Dict[str, Any]:
        p = self._resolve_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"path": str(p), "bytes_written": len(content.encode("utf-8"))}
    
    def _create_directory(self, path: str):
        p = self._resolve_path(path)
        p.mkdir(parents=True, exist_ok=True)

        return {
         "created": str(p)
    }

    def _list_directory(self, path: str) -> Dict[str, Any]:
        p = self._resolve_path(path)

        directories = []
        files = []

        for entry in p.iterdir():
            if entry.is_dir():
                directories.append({
                    "name": entry.name,
                    "path": str(entry),
                })
            else:
                files.append({
                    "name": entry.name,
                    "path": str(entry),
                    "size": entry.stat().st_size,
                })

        return {
            "path": str(p),
            "directories": directories,
            "files": files,
            "total_entries": len(directories) + len(files),
        }

    def _find_free_name(self, dst: Path) -> Path:
        """Devuelve un path libre añadiendo (1), (2)... antes de la extensión."""
        stem = dst.stem
        suffix = dst.suffix
        parent = dst.parent
        counter = 1
        candidate = parent / f"{stem}({counter}){suffix}"
        while candidate.exists():
            counter += 1
            candidate = parent / f"{stem}({counter}){suffix}"
        return candidate

    def _move(self, src: str, dst: str, overwrite: bool = False) -> Dict[str, Any]:
        src_p = self._resolve_path(src)
        dst_p = self._resolve_path(dst)
        if dst_p.exists() and not overwrite:
            raise FileExistsError(str(dst_p))
        if dst_p.exists() and overwrite:
            if dst_p.is_dir():
                shutil.rmtree(dst_p)
            else:
                dst_p.unlink()
        shutil.move(str(src_p), str(dst_p))
        return {"src": str(src_p), "dst": str(dst_p)}

    def _copy(self, src: str, dst: str, overwrite: bool = False) -> Dict[str, Any]:
        src_p = self._resolve_path(src)
        dst_p = self._resolve_path(dst)
        if dst_p.exists() and not overwrite:
            raise FileExistsError(str(dst_p))
        if dst_p.exists() and overwrite:
            if dst_p.is_dir():
                shutil.rmtree(dst_p)
            else:
                dst_p.unlink()
        if src_p.is_dir():
            shutil.copytree(src_p, dst_p)
        else:
            shutil.copy2(src_p, dst_p)
        return {"src": str(src_p), "dst": str(dst_p)}

    def _delete(self, path: str) -> Dict[str, Any]:
        p = self._resolve_path(path)
        send2trash(str(p))
        return {"path": str(p), "trashed": True}

    def _tree_directory(self, path: str, max_depth: int = 3) -> Dict[str, Any]:
        p = self._resolve_path(path)

        def _build(current: Path, depth: int) -> Dict[str, Any]:
            node: Dict[str, Any] = {"name": current.name, "path": str(current), "children": []}
            if depth == 0:
                return node
            try:
                entries = sorted(current.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
                for entry in entries:
                    if entry.is_dir():
                        node["children"].append(_build(entry, depth - 1))
                    else:
                        node["children"].append({
                            "name": entry.name,
                            "path": str(entry),
                            "size": entry.stat().st_size,
                            "children": None,
                        })
            except PermissionError:
                pass
            return node

        return _build(p, max_depth)

    def _search(self, directory: str, pattern: str, recursive: bool = False, type: str = "file", empty_only: bool = False) -> List[str]:
        d = self._resolve_path(directory)
        matches = d.rglob(pattern) if recursive else d.glob(pattern)
        if type == "directory":
            dirs = [p for p in matches if p.is_dir()]
            if empty_only:
                dirs = [p for p in dirs if not any(p.iterdir())]
            return [str(p.absolute()) for p in dirs]
        files = [p for p in matches if p.is_file()]
        if empty_only:
            files = [p for p in files if p.stat().st_size == 0]
        return [str(p.absolute()) for p in files]

    def _delete_matching(self, directory: str, pattern: str, recursive: bool = False, type: str = "file", empty_only: bool = False) -> Dict[str, Any]:
        """Busca y elimina (papelera) entradas que coinciden con el patrón."""
        paths = self._search(directory, pattern, recursive=recursive, type=type, empty_only=empty_only)
        deleted = []
        errors = []
        for p in paths:
            try:
                send2trash(p)
                deleted.append(p)
            except Exception as e:
                errors.append({"path": p, "error": str(e)})
        return {"deleted": deleted, "errors": errors, "count": len(deleted)}

    def _get_info(self, path: str) -> Dict[str, Any]:
        p = self._resolve_path(path)
        if not p.exists():
            return {
                "path": str(p.absolute()),
                "exists": False,
                "is_file": False,
                "is_dir": False,
                "size": 0,
                "modified_ts": None,
            }
        stat = p.stat()
        return {
            "path": str(p.absolute()),
            "exists": True,
            "is_file": p.is_file(),
            "is_dir": p.is_dir(),
            "size": stat.st_size,
            "modified_ts": stat.st_mtime,
        }

    def _empty_recycle_bin(self) -> Dict[str, Any]:
        res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0)
        if res != 0:
            raise RuntimeError(f"SHEmptyRecycleBinW returned {res}")
        return {"emptied": True}

    def _restore_from_recycle_bin(self, filename: str) -> Dict[str, Any]:
        raise NotImplementedError(
            "restore_from_recycle_bin no implementado en v1; requiere integración COM con Shell32"
        )
   