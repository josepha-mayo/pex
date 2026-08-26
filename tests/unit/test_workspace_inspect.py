from pathlib import Path

from pex_supervisor.workspace import git_snapshot, read_visible, snapshot


def test_snapshot_lists_visible_files_and_skips_hidden(tmp_path: Path):
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "evaluator.py").write_text("SECRET = 1\n", encoding="utf-8")
    (tmp_path / "metadata.yaml").write_text("hidden: true\n", encoding="utf-8")
    seen = snapshot(tmp_path, run_pytest=False)
    assert "ok.py" in seen["files"]
    assert "evaluator.py" not in seen["files"]
    assert "metadata.yaml" not in seen["files"]
    assert seen["pytest"] is None
    assert seen["git"]["available"] is False


def test_git_snapshot_does_not_walk_parent_repo(tmp_path: Path):
    nested = tmp_path / "worker"
    nested.mkdir()
    (nested / "app.py").write_text("print(1)\n", encoding="utf-8")
    assert git_snapshot(nested)["available"] is False


def test_read_visible_blocks_hidden_and_escape(tmp_path: Path):
    (tmp_path / "ok.py").write_text("hello\n", encoding="utf-8")
    (tmp_path / "evaluator.py").write_text("nope\n", encoding="utf-8")
    ok = read_visible(tmp_path, "ok.py")
    assert ok.get("text", "").replace("\r\n", "\n") == "hello\n"
    hidden = read_visible(tmp_path, "evaluator.py")
    assert hidden.get("error") == "hidden"
    escaped = read_visible(tmp_path, "../outside.py")
    assert escaped.get("error") == "path escapes workspace"
