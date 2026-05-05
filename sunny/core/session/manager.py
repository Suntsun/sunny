from __future__ import annotations

from typing import Optional, List, Dict
from uuid import uuid4

from sunny.core.memory import sqlite as memory
from sunny.core.logging.logger import get_logger, bind_session, unbind_session

CONTEXT_WINDOW: int = 3
MAX_TURNS: int = 100
ACTIVE_SESSION_KEY: str = "active_session_id"


def _logger():
    return get_logger("sunny.core.session.manager")


def get_active_session_id() -> Optional[str]:
    return memory.get_preference(ACTIVE_SESSION_KEY)


def get_or_create_active_session() -> str:
    sid = memory.get_preference(ACTIVE_SESSION_KEY)

    if sid and memory.session_exists(sid):
        bind_session(sid)
        _logger().info("session_resumed", extra={"session_id": sid})
        return sid

    new_id = str(uuid4())
    memory.create_session(new_id)
    memory.set_preference(ACTIVE_SESSION_KEY, new_id)

    bind_session(new_id)
    _logger().info("session_created", extra={"session_id": new_id})

    return new_id


def force_new_session() -> str:
    new_id = str(uuid4())
    memory.create_session(new_id)
    memory.set_preference(ACTIVE_SESSION_KEY, new_id)

    bind_session(new_id)
    _logger().info("session_forced_new", extra={"session_id": new_id})

    return new_id


def end_session() -> None:
    sid = memory.get_preference(ACTIVE_SESSION_KEY)

    memory.delete_preference(ACTIVE_SESSION_KEY)
    unbind_session()

    _logger().info("session_ended", extra={"session_id": sid})


def append_turn(user_msg: str, assistant_msg: str) -> dict:
    sid = memory.get_preference(ACTIVE_SESSION_KEY)
    if not sid:
        raise RuntimeError("No active session")

    turn = memory.append_turn(sid, user_msg, assistant_msg)

    if turn >= MAX_TURNS:
        new_id = str(uuid4())
        memory.create_session(new_id)
        memory.set_preference(ACTIVE_SESSION_KEY, new_id)

        bind_session(new_id)

        _logger().warning(
            "session_rotated",
            extra={
                "old_session_id": sid,
                "new_session_id": new_id,
                "reason": "max_turns_reached",
            },
        )

        return {
            "turn": turn,
            "rotated": True,
            "old_session_id": sid,
            "new_session_id": new_id,
        }

    return {
        "turn": turn,
        "rotated": False,
        "old_session_id": None,
        "new_session_id": None,
    }


def get_context(n: int = CONTEXT_WINDOW) -> List[Dict]:
    sid = memory.get_preference(ACTIVE_SESSION_KEY)
    if not sid:
        return []

    return memory.get_recent_turns(sid, n)