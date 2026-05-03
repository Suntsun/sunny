from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

from sunny.core.logging.logger import get_logger

log = get_logger("sunny.core.memory.sqlite")

_DB_CONN: Optional[sqlite3.Connection] = None
_DB_PATH: Optional[Path] = None
_WRITE_LOCK = threading.Lock()

CURRENT_SCHEMA_VERSION = 1


def _get_default_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA", ".")) / "sunny"
    base.mkdir(parents=True, exist_ok=True)
    return base / "sunny.db"


def _migrate(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA user_version")
    version = cur.fetchone()[0]

    if version < 1:
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                started_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                step_id TEXT,
                input TEXT,
                intent TEXT,
                plan TEXT,
                result TEXT,
                timestamp TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn INTEGER NOT NULL,
                user_msg TEXT NOT NULL,
                assistant_msg TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_history_session
            ON conversation_history(session_id);

            CREATE INDEX IF NOT EXISTS idx_commands_session
            ON commands(session_id);

            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        cur.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        conn.commit()


def init_db(db_path: Optional[Path] = None) -> None:
    global _DB_CONN, _DB_PATH

    if _DB_CONN:
        return

    try:
        _DB_PATH = db_path or _get_default_path()
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            _DB_PATH,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )

        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        _migrate(conn)

        _DB_CONN = conn

    except sqlite3.Error as e:
        log.error("init_db failed", error_type=type(e).__name__)
        raise


def close_db() -> None:
    global _DB_CONN
    if _DB_CONN:
        _DB_CONN.close()
        _DB_CONN = None


def _reset_db() -> None:
    global _DB_CONN
    if _DB_CONN:
        _DB_CONN.close()
        _DB_CONN = None


# -----------------------------------------------------------------------------
# Sessions
# -----------------------------------------------------------------------------

def create_session(session_id: str, started_at: Optional[datetime] = None) -> None:
    ts = started_at or datetime.now(timezone.utc)
    try:
        with _WRITE_LOCK:
            _DB_CONN.execute(
                "INSERT INTO sessions (id, started_at) VALUES (?, ?)",
                (session_id, ts),
            )
            _DB_CONN.commit()
    except sqlite3.Error as e:
        log.error("create_session failed", error_type=type(e).__name__)
        raise


def session_exists(session_id: str) -> bool:
    cur = _DB_CONN.execute(
        "SELECT 1 FROM sessions WHERE id = ? LIMIT 1", (session_id,)
    )
    return cur.fetchone() is not None


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------

def record_command(
    command_id: str,
    session_id: str,
    input_text: str,
    intent: str,
    plan: str,
    result: str,
    step_id: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> None:
    ts = timestamp or datetime.now(timezone.utc)
    try:
        with _WRITE_LOCK:
            _DB_CONN.execute(
                """
                INSERT INTO commands
                (id, session_id, step_id, input, intent, plan, result, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (command_id, session_id, step_id, input_text, intent, plan, result, ts),
            )
            _DB_CONN.commit()
    except sqlite3.Error as e:
        log.error("record_command failed", error_type=type(e).__name__)
        raise


def get_command(command_id: str) -> Optional[dict]:
    cur = _DB_CONN.execute(
        "SELECT * FROM commands WHERE id = ?", (command_id,)
    )
    row = cur.fetchone()
    if not row:
        return None
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))


def list_commands(session_id: str, limit: Optional[int] = None) -> List[dict]:
    q = "SELECT * FROM commands WHERE session_id = ? ORDER BY timestamp ASC"
    if limit:
        q += f" LIMIT {int(limit)}"

    cur = _DB_CONN.execute(q, (session_id,))
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in rows]


# -----------------------------------------------------------------------------
# Conversation history
# -----------------------------------------------------------------------------

def append_turn(session_id: str, user_msg: str, assistant_msg: str) -> int:
    try:
        with _WRITE_LOCK:
            cur = _DB_CONN.execute(
                "SELECT COALESCE(MAX(turn), 0) FROM conversation_history WHERE session_id = ?",
                (session_id,),
            )
            next_turn = cur.fetchone()[0] + 1

            _DB_CONN.execute(
                """
                INSERT INTO conversation_history (session_id, turn, user_msg, assistant_msg)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, next_turn, user_msg, assistant_msg),
            )
            _DB_CONN.commit()
            return next_turn
    except sqlite3.Error as e:
        log.error("append_turn failed", error_type=type(e).__name__)
        raise


def get_recent_turns(session_id: str, n: int = 5) -> List[dict]:
    cur = _DB_CONN.execute(
        """
        SELECT turn, user_msg, assistant_msg
        FROM conversation_history
        WHERE session_id = ?
        ORDER BY turn DESC
        LIMIT ?
        """,
        (session_id, n),
    )
    rows = cur.fetchall()
    rows.reverse()
    return [{"turn": r[0], "user_msg": r[1], "assistant_msg": r[2]} for r in rows]


def get_turn_count(session_id: str) -> int:
    cur = _DB_CONN.execute(
        "SELECT COUNT(*) FROM conversation_history WHERE session_id = ?",
        (session_id,),
    )
    return cur.fetchone()[0]


def trim_history(session_id: str, keep_last: int) -> int:
    try:
        with _WRITE_LOCK:
            cur = _DB_CONN.execute(
                "SELECT COUNT(*) FROM conversation_history WHERE session_id = ?",
                (session_id,),
            )
            total = cur.fetchone()[0]

            if total <= keep_last:
                return 0

            to_delete = total - keep_last

            _DB_CONN.execute(
                """
                DELETE FROM conversation_history
                WHERE id IN (
                    SELECT id FROM conversation_history
                    WHERE session_id = ?
                    ORDER BY turn ASC
                    LIMIT ?
                )
                """,
                (session_id, to_delete),
            )
            _DB_CONN.commit()
            return to_delete
    except sqlite3.Error as e:
        log.error("trim_history failed", error_type=type(e).__name__)
        raise


# -----------------------------------------------------------------------------
# Preferences
# -----------------------------------------------------------------------------

def set_preference(key: str, value: str) -> None:
    try:
        with _WRITE_LOCK:
            _DB_CONN.execute(
                """
                INSERT INTO preferences (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, value),
            )
            _DB_CONN.commit()
    except sqlite3.Error as e:
        log.error("set_preference failed", error_type=type(e).__name__)
        raise


def get_preference(key: str) -> Optional[str]:
    cur = _DB_CONN.execute(
        "SELECT value FROM preferences WHERE key = ?", (key,)
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_all_preferences() -> Dict[str, str]:
    cur = _DB_CONN.execute("SELECT key, value FROM preferences")
    return {k: v for k, v in cur.fetchall()}


def delete_preference(key: str) -> None:
    try:
        with _WRITE_LOCK:
            _DB_CONN.execute(
                "DELETE FROM preferences WHERE key = ?", (key,)
            )
            _DB_CONN.commit()
    except sqlite3.Error as e:
        log.error("delete_preference failed", error_type=type(e).__name__)
        raise