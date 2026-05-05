"""
Módulo de logging estructurado para Sunny v3.

Implementa rotación combinada (diaria + por tamaño), ofuscación de rutas y
campos sensibles, contexto thread-local para session_id, y exporta API limpia.
"""

import contextvars
import logging
import logging.handlers
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog
from structlog.types import EventDict

# -----------------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------------

DEFAULT_LOG_DIR = Path("%LOCALAPPDATA%\\sunny\\logs").expanduser().resolve()
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 7

_USER_PATH_RE = re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/]+[\\/]", re.IGNORECASE)
_SENSITIVE_FIELDS = {"password", "token", "api_key", "secret"}

_LOGGER_CONFIGURED = False
_CONFIG_LOCK = threading.Lock()

_SESSION_ID_VAR = contextvars.ContextVar("session_id", default=None)

# Configuración mínima de structlog al importar el módulo.
# Garantiza que get_logger() siempre usa stdlib (nunca PrintLogger),
# incluso antes de que configure_logging() añada los handlers.
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=False,
)

# -----------------------------------------------------------------------------
# Sanitización
# -----------------------------------------------------------------------------

def _obfuscate_value(value: Any) -> Any:
    if isinstance(value, str):
        return _USER_PATH_RE.sub("~\\\\", value)
    if isinstance(value, dict):
        return {k: _obfuscate_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_obfuscate_value(v) for v in value]
    return value


def _redact_sensitive_fields(data: Any) -> Any:
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if any(s in k.lower() for s in _SENSITIVE_FIELDS):
                result[k] = "***REDACTED***"
            else:
                result[k] = _redact_sensitive_fields(v)
        return result
    if isinstance(data, list):
        return [_redact_sensitive_fields(v) for v in data]
    return data


def _sanitize_event_dict(_, __, event_dict: EventDict) -> EventDict:
    event_dict = _obfuscate_value(event_dict)
    event_dict = _redact_sensitive_fields(event_dict)
    return event_dict


# -----------------------------------------------------------------------------
# Procesadores
# -----------------------------------------------------------------------------

def _add_timestamp_utc(_, __, event_dict: EventDict) -> EventDict:
    if "timestamp" not in event_dict:
        event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


def _add_session_id(_, __, event_dict: EventDict) -> EventDict:
    sid = _SESSION_ID_VAR.get()
    if sid:
        event_dict["session_id"] = sid
    return event_dict


# -----------------------------------------------------------------------------
# Handler
# -----------------------------------------------------------------------------

class DateAwareRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    Rotación por tamaño + rotación diaria.
    """

    # TODO concurrencia: RotatingFileHandler usa un lock por instancia, suficiente
    # para v1. En el futuro, si múltiples plugins escriben en paralelo bajo carga
    # alta, evaluar QueueHandler + QueueListener con un solo worker thread, o un
    # ConcurrentRotatingFileHandler externo.

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.current_date = datetime.now().date()
        filename = self._compute_filename()
        super().__init__(filename, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")

    def _compute_filename(self) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        return str(self.base_dir / f"sunny-{date_str}.jsonl")

    def emit(self, record: logging.LogRecord) -> None:
        if datetime.now().date() != self.current_date:
            self.current_date = datetime.now().date()
            self.baseFilename = self._compute_filename()
            if self.stream:
                self.stream.close()
            self.stream = self._open()
        super().emit(record)
        self.flush()


# -----------------------------------------------------------------------------
# Configuración
# -----------------------------------------------------------------------------

def _reset_logging() -> None:
    global _LOGGER_CONFIGURED
    with _CONFIG_LOCK:
        _LOGGER_CONFIGURED = False
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)
            h.close()
        structlog.reset_defaults()
        _SESSION_ID_VAR.set(None)


def configure_logging(log_dir: Optional[Path] = None, level: str = "INFO", verbose: bool = False) -> None:
    global _LOGGER_CONFIGURED

    lvl = getattr(logging, level.upper(), None)
    if not isinstance(lvl, int):
        raise ValueError(f"Nivel de log inválido: '{level}'.")

    if _LOGGER_CONFIGURED:
        return

    with _CONFIG_LOCK:
        if _LOGGER_CONFIGURED:
            return

        path = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        path.mkdir(parents=True, exist_ok=True)

        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            _add_timestamp_utc,
            _add_session_id,
            _sanitize_event_dict,
        ]

        console_processors = shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter
        ]

        structlog.configure(
            processors=console_processors,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=False,
        )

        json_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )

        # Handler archivo: siempre INFO, JSON
        file_handler = DateAwareRotatingFileHandler(path)
        file_handler.setLevel(lvl)
        file_handler.setFormatter(json_formatter)

        root = logging.getLogger()
        root.setLevel(lvl)
        root.addHandler(file_handler)

        # Handler consola: solo si --verbose
        if verbose:
            console_formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.dev.ConsoleRenderer(colors=True),
                foreign_pre_chain=shared_processors,
            )
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setLevel(logging.INFO)
            stream_handler.setFormatter(console_formatter)
            root.addHandler(stream_handler)

        _LOGGER_CONFIGURED = True


# -----------------------------------------------------------------------------
# API pública
# -----------------------------------------------------------------------------

def get_logger(module_name: str) -> structlog.stdlib.BoundLogger:
    """Retorna un logger nombrado y bindeado al módulo."""
    return structlog.get_logger(module_name).bind(module=module_name)


def bind_session(session_id: str) -> None:
    _SESSION_ID_VAR.set(session_id)


def unbind_session() -> None:
    _SESSION_ID_VAR.set(None)