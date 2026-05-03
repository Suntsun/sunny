import json
from uuid import UUID

import pytest

from sunny.core.memory import sqlite as memory
from sunny.core.session import manager as S
from sunny.core.logging import logger as L


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "sess.db"
    memory._reset_db()
    memory.init_db(path)
    yield path
    memory._reset_db()


@pytest.fixture
def setup_logging(tmp_path):
    L._reset_logging()
    log_dir = tmp_path / "logs"
    L.configure_logging(log_dir=log_dir, level="DEBUG")
    yield log_dir
    L._reset_logging()


def test_first_call_creates_session_and_persists(db):
    sid = S.get_or_create_active_session()
    UUID(sid)
    assert memory.get_preference(S.ACTIVE_SESSION_KEY) == sid


def test_second_call_returns_same_session(db):
    sid1 = S.get_or_create_active_session()
    sid2 = S.get_or_create_active_session()
    assert sid1 == sid2


def test_persists_across_simulated_restart(db):
    sid1 = S.get_or_create_active_session()
    memory._reset_db()
    memory.init_db(db)
    sid2 = S.get_or_create_active_session()
    assert sid1 == sid2


def test_force_new_session_rotates(db):
    sid1 = S.get_or_create_active_session()
    sid2 = S.force_new_session()
    assert sid1 != sid2
    assert memory.get_preference(S.ACTIVE_SESSION_KEY) == sid2


def test_get_active_returns_none_when_no_session(db):
    assert S.get_active_session_id() is None


def test_get_active_after_creation(db):
    sid = S.get_or_create_active_session()
    assert S.get_active_session_id() == sid


def test_append_turn_without_session_raises(db):
    with pytest.raises(RuntimeError):
        S.append_turn("u", "a")


def test_append_turn_returns_turn_info(db):
    S.get_or_create_active_session()
    res = S.append_turn("u", "a")
    assert res["turn"] == 1
    assert res["rotated"] is False


def test_append_turn_rotates_at_max_turns(db, monkeypatch):
    monkeypatch.setattr(S, "MAX_TURNS", 5)
    sid = S.get_or_create_active_session()

    for i in range(4):
        S.append_turn("u", "a")

    res = S.append_turn("u", "a")
    assert res["rotated"] is True
    assert res["old_session_id"] == sid
    assert res["new_session_id"] != sid


def test_after_rotation_active_session_changed(db, monkeypatch):
    monkeypatch.setattr(S, "MAX_TURNS", 2)
    sid = S.get_or_create_active_session()
    S.append_turn("u", "a")
    S.append_turn("u", "a")

    new_sid = S.get_active_session_id()
    assert new_sid != sid


def test_get_context_empty_when_no_session(db):
    assert S.get_context() == []


def test_get_context_returns_last_n_chronological(db):
    sid = S.get_or_create_active_session()
    for i in range(8):
        S.append_turn(f"u{i}", f"a{i}")

    ctx = S.get_context(3)
    assert [t["turn"] for t in ctx] == [6, 7, 8]


def test_end_session_clears_marker(db):
    S.get_or_create_active_session()
    S.end_session()
    assert S.get_active_session_id() is None


def test_end_session_does_not_delete_history(db):
    sid = S.get_or_create_active_session()
    for _ in range(3):
        S.append_turn("u", "a")

    S.end_session()
    assert memory.get_turn_count(sid) == 3


def test_session_resumed_event_logged(db, setup_logging):
    sid = S.get_or_create_active_session()
    S.get_or_create_active_session()

    print("=== DIAGNÓSTICO ===")
    print(f"log_dir: {setup_logging}")
    print(f"archivos: {list(setup_logging.glob('*'))}")
    for f in setup_logging.glob('*.jsonl'):
        print(f"--- contenido de {f.name} ---")
        print(f.read_text())
        print(f"--- fin ---")
    print("=== FIN DIAGNÓSTICO ===")

    log_file = list(setup_logging.glob("*.jsonl"))[0]
    logs = [json.loads(l) for l in log_file.read_text().splitlines()]
    assert any(l.get("event") == "session_resumed" for l in logs)


def test_session_created_event_logged(db, setup_logging):
    S.get_or_create_active_session()

    print("=== DIAGNÓSTICO ===")
    print(f"log_dir: {setup_logging}")
    print(f"archivos: {list(setup_logging.glob('*'))}")
    for f in setup_logging.glob('*.jsonl'):
        print(f"--- contenido de {f.name} ---")
        print(f.read_text())
        print(f"--- fin ---")
    print("=== FIN DIAGNÓSTICO ===")

    log_file = list(setup_logging.glob("*.jsonl"))[0]
    logs = [json.loads(l) for l in log_file.read_text().splitlines()]
    assert any(l.get("event") == "session_created" for l in logs)