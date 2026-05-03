import threading
from pathlib import Path

import pytest

from sunny.core.memory import sqlite as M


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    M._reset_db()
    M.init_db(db_path)
    yield db_path
    M._reset_db()


def test_init_creates_all_tables(db):
    cur = M._DB_CONN.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    assert {"sessions", "commands", "conversation_history", "preferences"} <= tables


def test_init_creates_indexes(db):
    cur = M._DB_CONN.execute("SELECT name FROM sqlite_master WHERE type='index'")
    idx = {r[0] for r in cur.fetchall()}
    assert "idx_history_session" in idx
    assert "idx_commands_session" in idx


def test_init_idempotent(db):
    M.init_db(db)


def test_wal_mode_enabled(db):
    cur = M._DB_CONN.execute("PRAGMA journal_mode")
    assert cur.fetchone()[0].lower() == "wal"


def test_foreign_keys_enabled(db):
    cur = M._DB_CONN.execute("PRAGMA foreign_keys")
    assert cur.fetchone()[0] == 1


def test_user_version_set(db):
    cur = M._DB_CONN.execute("PRAGMA user_version")
    assert cur.fetchone()[0] == 1


def test_create_session_and_exists(db):
    M.create_session("s1")
    assert M.session_exists("s1")


def test_record_command_and_get(db):
    M.create_session("s1")
    M.record_command("c1", "s1", "in", "intent", "{}", "{}")
    cmd = M.get_command("c1")
    assert cmd["id"] == "c1"


def test_list_commands_for_session(db):
    M.create_session("s1")
    M.record_command("c1", "s1", "a", "i", "{}", "{}")
    M.record_command("c2", "s1", "b", "i", "{}", "{}")
    res = M.list_commands("s1")
    assert len(res) == 2


def test_append_turn_increments(db):
    M.create_session("s")
    assert M.append_turn("s", "u1", "a1") == 1
    assert M.append_turn("s", "u2", "a2") == 2
    assert M.append_turn("s", "u3", "a3") == 3


def test_get_recent_turns_returns_chronological(db):
    M.create_session("s")
    for i in range(6):
        M.append_turn("s", str(i), str(i))
    res = M.get_recent_turns("s", 3)
    assert [r["turn"] for r in res] == [4, 5, 6]


def test_get_recent_turns_n_larger_than_existing(db):
    M.create_session("s")
    for i in range(3):
        M.append_turn("s", str(i), str(i))
    res = M.get_recent_turns("s", 10)
    assert len(res) == 3


def test_get_turn_count(db):
    M.create_session("s")
    for _ in range(4):
        M.append_turn("s", "u", "a")
    assert M.get_turn_count("s") == 4


def test_trim_history_keeps_last_n(db):
    M.create_session("s")
    for i in range(10):
        M.append_turn("s", str(i), str(i))
    deleted = M.trim_history("s", 3)
    assert deleted == 7
    assert M.get_turn_count("s") == 3


def test_set_get_preference(db):
    M.set_preference("k", "v")
    assert M.get_preference("k") == "v"


def test_set_preference_overwrites_existing(db):
    M.set_preference("k", "v1")
    M.set_preference("k", "v2")
    assert M.get_preference("k") == "v2"


def test_get_all_preferences_returns_dict(db):
    M.set_preference("a", "1")
    M.set_preference("b", "2")
    d = M.get_all_preferences()
    assert d["a"] == "1" and d["b"] == "2"


def test_delete_preference(db):
    M.set_preference("k", "v")
    M.delete_preference("k")
    assert M.get_preference("k") is None


def test_get_missing_preference_returns_none(db):
    assert M.get_preference("missing") is None


def test_concurrent_writes_serialized(db):
    M.create_session("s")

    barrier = threading.Barrier(50)

    def worker(i):
        barrier.wait()
        M.append_turn("s", f"u{i}", f"a{i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert M.get_turn_count("s") == 50


def test_concurrent_reads_during_write(db):
    M.create_session("s")

    def writer():
        for i in range(50):
            M.append_turn("s", str(i), str(i))

    def reader():
        for _ in range(50):
            M.get_recent_turns("s", 5)

    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=reader)

    t1.start()
    t2.start()
    t1.join()
    t2.join()


def test_close_then_reinit(db):
    M.close_db()
    M.init_db(db)
    M.create_session("s2")
    assert M.session_exists("s2")