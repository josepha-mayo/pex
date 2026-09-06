import subprocess
import sys
import time
from pathlib import Path

import pytest
from pex_supervisor.workspace import artifact_tails, git_snapshot, read_visible, snapshot


def test_workspace_process_tree_termination_is_bounded_with_inherited_stdout():
    import os

    import pex_supervisor.workspace as workspace_module

    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
                "print('ready', flush=True); "
                "time.sleep(30)"
            ),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
        start_new_session=os.name != "nt",
        bufsize=0,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == b"ready"
    started = time.monotonic()
    try:
        workspace_module._terminate_process_tree(process)
        process.wait(timeout=3)
    finally:
        if process.stdout is not None:
            process.stdout.close()

    assert time.monotonic() - started < 6


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


def test_snapshot_prunes_dependency_trees_before_inventory_cap(tmp_path: Path):
    dependency = tmp_path / "node_modules" / "package"
    dependency.mkdir(parents=True)
    for index in range(450):
        (dependency / f"generated-{index:03}.js").write_text("vendor\n", encoding="utf-8")
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.py").write_text("print('visible')\n", encoding="utf-8")

    seen = snapshot(tmp_path, run_pytest=False)

    assert seen["files"] == ["src/main.py"]
    assert seen["files_truncated"] is False
    assert all(not path.startswith("node_modules/") for path in seen["files"])


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


def test_workspace_previews_use_bounded_prefix_and_tail_reads(tmp_path: Path):
    payload = "START-" + ("x" * 80) + "-END"
    (tmp_path / "large.txt").write_text(payload, encoding="utf-8")
    (tmp_path / "results.jsonl").write_text(payload, encoding="utf-8")

    visible = read_visible(tmp_path, "large.txt", limit=10)
    artifacts = artifact_tails(tmp_path, limit=10)

    assert visible["text"] == payload[:10]
    assert artifacts[0]["tail"] == payload[-10:]
    assert artifacts[0]["bytes"] == len(payload.encode("utf-8"))


def test_workspace_preview_limits_cannot_turn_negative_or_huge_reads_unbounded(tmp_path: Path):
    payload = "x" * 100
    (tmp_path / "large.txt").write_text(payload, encoding="utf-8")
    (tmp_path / "results.jsonl").write_text(payload, encoding="utf-8")

    assert read_visible(tmp_path, "large.txt", limit=-1)["text"] == ""
    assert artifact_tails(tmp_path, limit=-1)[0]["tail"] == ""
    assert read_visible(tmp_path, "large.txt", limit="not-a-number")["text"] == ""
    assert artifact_tails(tmp_path, limit="not-a-number")[0]["tail"] == ""


def test_oversized_jsonl_is_not_scanned_end_to_end_for_a_row_claim(tmp_path: Path):
    (tmp_path / "results.jsonl").write_bytes(b'{"row":1}\n' * 410_000)

    artifact = artifact_tails(tmp_path)[0]

    assert artifact["row_count"] is None
    assert artifact["row_count_complete"] is False


def test_malformed_jsonl_does_not_produce_a_complete_row_receipt(tmp_path: Path):
    (tmp_path / "results.jsonl").write_text("not-json\n" * 30, encoding="utf-8")

    artifact = artifact_tails(tmp_path)[0]

    assert artifact["row_count"] is None
    assert artifact["row_count_complete"] is False


def test_nonfinite_jsonl_does_not_produce_a_complete_row_receipt(tmp_path: Path):
    (tmp_path / "results.jsonl").write_text(
        '{"score": NaN}\n{"score": Infinity}\n',
        encoding="utf-8",
    )

    artifact = snapshot(tmp_path)["artifacts"][0]

    assert artifact["row_count"] is None
    assert artifact["row_count_complete"] is False


def test_duplicate_json_keys_do_not_produce_a_complete_row_receipt(tmp_path: Path):
    (tmp_path / "results.jsonl").write_text(
        '{"passed":false,"passed":true}\n',
        encoding="utf-8",
    )

    artifact = snapshot(tmp_path)["artifacts"][0]

    assert artifact["row_count"] is None
    assert artifact["row_count_complete"] is False


def test_workspace_artifact_symlink_cannot_read_outside_root(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside-secret.jsonl"
    outside.write_text('{"secret":"never expose"}\n', encoding="utf-8")
    link = workspace / "results.jsonl"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("filesystem does not permit symlink creation")

    seen = snapshot(workspace, run_pytest=False)

    assert "results.jsonl" not in seen["files"]
    assert seen["artifacts"] == []


def test_git_diff_omits_entire_hidden_file_section(tmp_path: Path):
    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

    git("init", "-q")
    git("config", "user.email", "pex@example.invalid")
    git("config", "user.name", "PEX Test")
    (tmp_path / "ok.py").write_text("safe = 1\n", encoding="utf-8")
    (tmp_path / "stressor.yaml").write_text("secret: OLD\n", encoding="utf-8")
    git("add", "ok.py", "stressor.yaml")
    git("commit", "-qm", "seed")
    (tmp_path / "ok.py").write_text("safe = 2\n", encoding="utf-8")
    (tmp_path / "stressor.yaml").write_text("secret: NEVER_SEND_THIS\n", encoding="utf-8")

    seen = git_snapshot(tmp_path)

    assert "safe = 2" in seen["diff"]
    assert "NEVER_SEND_THIS" not in seen["diff"]
    assert "stressor.yaml" not in seen["diff"]


def test_git_snapshot_disables_repository_textconv_commands(tmp_path: Path):
    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

    git("init", "-q")
    git("config", "user.email", "pex@example.invalid")
    git("config", "user.name", "PEX Test")
    marker = tmp_path / "TEXTCONV_MUST_NOT_RUN"
    helper = tmp_path / "textconv.py"
    helper.write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran')\nprint('x')\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" "{helper}" "{marker}"'
    git("config", "diff.pexunsafe.textconv", command)
    (tmp_path / ".gitattributes").write_text("*.txt diff=pexunsafe\n", encoding="utf-8")
    (tmp_path / "visible.txt").write_text("before\n", encoding="utf-8")
    git("add", ".gitattributes", "visible.txt")
    git("commit", "-qm", "seed")
    (tmp_path / "visible.txt").write_text("after\n", encoding="utf-8")

    seen = git_snapshot(tmp_path)

    assert marker.exists() is False
    assert "after" in seen["diff"]


def test_git_snapshot_rejects_workspace_shadow_executable(tmp_path: Path, monkeypatch):
    (tmp_path / ".git").mkdir()
    fake_git = tmp_path / "git.exe"
    fake_git.write_bytes(b"must never execute")
    monkeypatch.setattr("pex_supervisor.workspace.shutil.which", lambda _name: str(fake_git))

    seen = git_snapshot(tmp_path)

    assert seen == {"available": False, "error": "workspace git executable rejected"}


def test_git_snapshot_output_is_bounded_before_process_capture(tmp_path: Path):
    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

    git("init", "-q")
    git("config", "user.email", "pex@example.invalid")
    git("config", "user.name", "PEX Test")
    target = tmp_path / "large.txt"
    target.write_text("before\n", encoding="utf-8")
    git("add", "large.txt")
    git("commit", "-qm", "seed")
    target.write_text("".join(f"changed-{index:05}\n" for index in range(10_000)), encoding="utf-8")

    seen = git_snapshot(tmp_path)

    assert seen["available"] is True
    assert len(seen["diff"].encode("utf-8")) <= 8000
