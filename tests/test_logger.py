import json
import threading
from pathlib import Path

import pytest
from freezegun import freeze_time

from sunny.core.logging import logger as L


@pytest.fixture
def temp_log_dir(tmp_path):
    return tmp_path / "logs"


def read_lines(p: Path):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def test_json_valid_each_line(temp_log_dir):
    L.configure_logging(log_dir=temp_log_dir)
    log = L.get_logger("test")
    log.info("a")
    log.warning("b")

    file = list(temp_log_dir.glob("*.jsonl"))[0]
    for line in file.read_text().splitlines():
        obj = json.loads(line)
        assert "timestamp" in obj
        assert "level" in obj


def test_module_field_present(temp_log_dir):
    L.configure_logging(log_dir=temp_log_dir)
    log = L.get_logger("sunny.core.test")
    log.info("msg")

    obj = read_lines(list(temp_log_dir.glob("*.jsonl"))[0])[0]
    assert obj["module"] == "sunny.core.test"


def test_session_id_injection(temp_log_dir):
    L.configure_logging(log_dir=temp_log_dir)
    L.bind_session("s1")
    L.get_logger("x").info("msg")

    obj = read_lines(list(temp_log_dir.glob("*.jsonl"))[0])[0]
    assert obj["session_id"] == "s1"


def test_unbind_session_preserves_other_context(temp_log_dir):
    from structlog.contextvars import bind_contextvars, unbind_contextvars

    L.configure_logging(log_dir=temp_log_dir)
    L.bind_session("s1")
    bind_contextvars(other="x")

    log = L.get_logger("test")
    log.info("before unbind")
    L.unbind_session()
    log.info("after unbind")

    lines = read_lines(list(temp_log_dir.glob("*.jsonl"))[0])
    before, after = lines[0], lines[1]

    assert before["session_id"] == "s1"
    assert before["other"] == "x"
    assert "session_id" not in after
    assert after["other"] == "x"

    unbind_contextvars("other")


def test_bind_session_thread_isolated(temp_log_dir):
    L.configure_logging(log_dir=temp_log_dir, level="DEBUG")

    barrier = threading.Barrier(2)

    def worker(sess):
        L.bind_session(sess)
        barrier.wait()
        L.get_logger("worker").info(f"hi from {sess}")

    t1 = threading.Thread(target=worker, args=("sess-A",))
    t2 = threading.Thread(target=worker, args=("sess-B",))
    t1.start(); t2.start(); t1.join(); t2.join()

    lines = read_lines(list(temp_log_dir.glob("*.jsonl"))[0])
    line_a = next(l for l in lines if "sess-A" in l.get("event", ""))
    line_b = next(l for l in lines if "sess-B" in l.get("event", ""))

    assert line_a["session_id"] == "sess-A"
    assert line_b["session_id"] == "sess-B"


def test_daily_rotation_crosses_midnight(temp_log_dir):
    with freeze_time("2026-01-01 23:59:00"):
        L.configure_logging(log_dir=temp_log_dir)
        log = L.get_logger("test")
        log.info("antes")

    with freeze_time("2026-01-02 00:00:01"):
        log.info("despues")

    files = list(temp_log_dir.glob("*.jsonl"))
    names = [f.name for f in files]
    assert any("2026-01-01" in n for n in names)
    assert any("2026-01-02" in n for n in names)


def test_redact_sensitive_fields(temp_log_dir):
    L.configure_logging(log_dir=temp_log_dir)
    L.get_logger("x").info("msg", api_key="123")

    obj = read_lines(list(temp_log_dir.glob("*.jsonl"))[0])[0]
    assert obj["api_key"] == "***REDACTED***"


def test_obfuscate_user_paths(temp_log_dir):
    L.configure_logging(log_dir=temp_log_dir)
    L.get_logger("x").info("msg", path=r"C:\Users\John\file.txt")

    obj = read_lines(list(temp_log_dir.glob("*.jsonl"))[0])[0]
    assert "~\\file.txt" in obj["path"]


def test_obfuscation_recursive_in_list(temp_log_dir):
    L.configure_logging(log_dir=temp_log_dir)
    log = L.get_logger("test")
    log.info(
        "complex",
        paths=[r"C:\Users\Jane\file1.txt", r"C:\Users\John\file2.txt"],
        items=[{"path": r"C:\Users\Admin\config.ini"}],
    )
    obj = read_lines(list(temp_log_dir.glob("*.jsonl"))[0])[0]
    assert "~\\file1.txt" in obj["paths"][0]
    assert "~\\file2.txt" in obj["paths"][1]
    assert "~\\config.ini" in obj["items"][0]["path"]


def test_rotation_by_size(temp_log_dir):
    L.configure_logging(log_dir=temp_log_dir, level="DEBUG")
    log = L.get_logger("test")
    big = "x" * 5000
    written = 0
    while written < L.MAX_BYTES * 2:
        log.info(big)
        written += len(big) + 100

    files = sorted(temp_log_dir.glob("*.jsonl*"))
    assert len(files) >= 2

    active = [f for f in files if f.suffix == ".jsonl"]
    assert len(active) == 1
    assert active[0].stat().st_size <= L.MAX_BYTES * 1.1


def test_invalid_log_level():
    with pytest.raises(ValueError, match="Nivel de log inválido"):
        L.configure_logging(level="INVALID")