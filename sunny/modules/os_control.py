from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

import psutil

from sunny.core.logging.logger import get_logger
from sunny.core.plugins.base import PluginBase, PluginResult

log = get_logger("sunny.modules.os_control")


class OSControlPlugin(PluginBase):
    """Plugin de control del sistema operativo."""

    name: str = "os_control"

    def __init__(self) -> None:
        self._actions: Dict[str, Callable[..., Any]] = {
            "open_app": self._open_app,
            "close_app": self._close_app,
            "list_processes": self._list_processes,
            "kill_process": self._kill_process,
            "set_volume": self._set_volume,
            "mute": self._mute,
            "lock_screen": self._lock_screen,
            "shutdown": self._shutdown,
            "restart": self._restart,
            "get_system_info": self._get_system_info,
            "sleep_seconds": self._sleep_seconds,
        }

    def execute(self, action, params, context, timeout_sec=30) -> PluginResult:
        if action not in self._actions:
            return PluginResult(
                success=False,
                error=f"action '{action}' no soportada por os_control",
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
        log.info("os_control_action_done", action=action, success=res.success)
        return res

    @staticmethod
    def _find_in_registry(app: str) -> Optional[str]:
        """Busca el ejecutable en el registro de Windows (App Paths)."""
        try:
            import winreg
            exe = app if app.lower().endswith(".exe") else app + ".exe"
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
                    with winreg.OpenKey(hive, key_path) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        if value and os.path.isfile(value):
                            return value
                except (FileNotFoundError, OSError):
                    continue
        except ImportError:
            pass
        return None

    @staticmethod
    def _find_in_common_dirs(app: str) -> Optional[str]:
        """Busca el ejecutable en directorios comunes de instalación de Windows.

        Estrategia en dos pasadas:
        1. Carpetas cuyo nombre contiene el app name (rápido, mayoría de casos).
        2. Búsqueda exhaustiva del .exe en hasta 3 niveles de profundidad (Chrome, etc.).
        """
        name = app.lower()
        exe = name if name.endswith(".exe") else name + ".exe"

        roots = [
            os.path.expandvars(r"%LOCALAPPDATA%"),
            os.path.expandvars(r"%APPDATA%"),
            os.path.expandvars(r"%PROGRAMFILES%"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%"),
        ]

        def _search_dir(directory: str, depth: int) -> Optional[str]:
            """Busca exe recursivamente hasta depth niveles."""
            if depth < 0:
                return None
            try:
                entries = sorted(os.listdir(directory), reverse=True)
            except PermissionError:
                return None
            # Primero buscar el exe directamente en este nivel
            candidate = os.path.join(directory, exe)
            if os.path.isfile(candidate):
                return candidate
            # Luego bajar a subdirectorios
            for entry in entries:
                entry_path = os.path.join(directory, entry)
                if os.path.isdir(entry_path):
                    found = _search_dir(entry_path, depth - 1)
                    if found:
                        return found
            return None

        # Pasada 1: solo carpetas cuyo nombre contiene el app name
        for root in roots:
            if not os.path.isdir(root):
                continue
            try:
                entries = os.listdir(root)
            except PermissionError:
                continue
            for entry in entries:
                if name not in entry.lower():
                    continue
                entry_path = os.path.join(root, entry)
                if not os.path.isdir(entry_path):
                    continue
                found = _search_dir(entry_path, depth=2)
                if found:
                    return found

        # Pasada 2: búsqueda exhaustiva hasta 3 niveles (captura Chrome, etc.)
        for root in roots:
            if not os.path.isdir(root):
                continue
            found = _search_dir(root, depth=3)
            if found:
                return found

        return None

    def _open_app(self, app: str) -> Dict[str, Any]:
        """Abre una aplicación por nombre, ejecutable en PATH, registro, dirs comunes o URI."""
        # DETACHED_PROCESS desvincula el hijo de la consola de sunny
        # evitando que apps Electron (Discord, Chrome…) escriban ruido al terminal
        popen_kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        try:
            popen_kwargs["creationflags"] = subprocess.DETACHED_PROCESS
        except AttributeError:
            pass  # No-Windows: ignorar

        # 1. Ruta completa existente
        if os.path.isfile(app):
            subprocess.Popen([app], **popen_kwargs)
            return {"app": app, "launched": True}

        # 2. Ejecutable en PATH (con o sin .exe)
        found = shutil.which(app) or shutil.which(app + ".exe")
        if found:
            subprocess.Popen([found], **popen_kwargs)
            return {"app": found, "launched": True}

        # 3. Registro de Windows (App Paths) — apps que se auto-registran
        reg_path = self._find_in_registry(app)
        if reg_path:
            subprocess.Popen([reg_path], **popen_kwargs)
            return {"app": reg_path, "launched": True}

        # 4. Directorios comunes de instalación (Discord, Spotify, Steam games…)
        common_path = self._find_in_common_dirs(app)
        if common_path:
            subprocess.Popen([common_path], **popen_kwargs)
            return {"app": common_path, "launched": True}

        # 5. os.startfile — URIs (steam://), UWP, asociaciones de Windows
        try:
            os.startfile(app)
            return {"app": app, "launched": True}
        except OSError:
            raise FileNotFoundError(
                f"No se encontró la aplicación '{app}'. "
                "Usa el nombre del ejecutable (ej. 'notepad'), la ruta completa, o una URI de Windows (ej. 'steam://rungameid/427520')."
            )

    def _close_app(self, app: str) -> Dict[str, Any]:
        count = 0
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info.get("name", "") or ""
                if app.lower() in name.lower():
                    proc.terminate()
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if count == 0:
            raise FileNotFoundError(f"no se encontró ningún proceso con nombre '{app}'")
        return {"app": app, "closed": count}

    def _list_processes(self) -> List[Dict[str, Any]]:
        res = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                res.append({"pid": proc.info["pid"], "name": proc.info["name"]})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return res

    def _kill_process(self, pid: int) -> Dict[str, Any]:
        p = psutil.Process(pid)
        p.terminate()
        return {"pid": pid, "terminated": True}

    def _set_volume(self, level: int) -> Dict[str, Any]:
        raise NotImplementedError(
            "set_volume no implementado en v1; requiere integración con pycaw / Audio Endpoint Volume API"
        )

    def _mute(self, state: bool) -> Dict[str, Any]:
        raise NotImplementedError(
            "mute no implementado en v1; requiere integración con pycaw"
        )

    def _lock_screen(self) -> Dict[str, Any]:
        res = ctypes.windll.user32.LockWorkStation()
        if res == 0:
            raise RuntimeError("LockWorkStation falló")
        return {"locked": True}

    def _shutdown(self, delay_sec: int) -> Dict[str, Any]:
        subprocess.run(
            ["shutdown", "/s", "/t", str(delay_sec)],
            check=True,
            capture_output=True,
        )
        return {"action": "shutdown", "delay_sec": delay_sec}

    def _restart(self, delay_sec: int) -> Dict[str, Any]:
        subprocess.run(
            ["shutdown", "/r", "/t", str(delay_sec)],
            check=True,
            capture_output=True,
        )
        return {"action": "restart", "delay_sec": delay_sec}

    def _get_system_info(self) -> Dict[str, Any]:
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        return {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "architecture": platform.machine(),
            "cpu_count": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_total_gb": round(vm.total / (1024**3), 2),
            "memory_used_gb": round(vm.used / (1024**3), 2),
            "memory_percent": vm.percent,
            "disk_total_gb": round(du.total / (1024**3), 2),
            "disk_used_gb": round(du.used / (1024**3), 2),
            "boot_time": psutil.boot_time(),
        }

    def _sleep_seconds(self, seconds: int) -> None:
        """Pausa la ejecución durante el número de segundos indicado."""
        time.sleep(seconds)
