from __future__ import annotations

import ctypes
import platform
import subprocess
import time
from typing import Any, Callable, Dict, List

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

    def _open_app(self, app: str) -> Dict[str, Any]:
        subprocess.Popen([app], shell=True)
        return {"app": app, "launched": True}

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
