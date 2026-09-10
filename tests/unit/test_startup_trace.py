import json

from pex_bridge import startup_trace as trace


def test_trace_is_opt_in_and_records_only_fixed_phases(tmp_path, monkeypatch):
    monkeypatch.setattr(trace, "_path", None)
    trace.mark_startup_phase("ready")
    assert not list(tmp_path.iterdir())
    trace.start_startup_trace(tmp_path)
    trace.mark_startup_phase("store_begin")
    trace.mark_startup_phase("store_begin")
    trace.mark_startup_phase("secret or private path")
    trace.mark_startup_phase("ready")
    files = list((tmp_path / "startup-traces").glob("*.jsonl"))
    assert len(files) == 1
    rows = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert [row["phase"] for row in rows] == ["python_entry", "store_begin", "ready"]
    assert all(set(row) == {"schema", "phase", "elapsed_seconds"} for row in rows)
    assert all(row["elapsed_seconds"] >= 0 for row in rows)
    assert [row["elapsed_seconds"] for row in rows] == sorted(
        row["elapsed_seconds"] for row in rows
    )
    trace.start_startup_trace(tmp_path)
    assert len(list((tmp_path / "startup-traces").glob("*.jsonl"))) == 2


def test_unwritable_trace_never_blocks_startup(tmp_path):
    occupied = tmp_path / "file"
    occupied.write_text("keep")
    trace.start_startup_trace(occupied)
    trace.mark_startup_phase("ready")
    assert trace._path is None
    assert occupied.read_text() == "keep"
