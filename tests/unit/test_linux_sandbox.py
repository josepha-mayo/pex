from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks import linux_sandbox


def test_sandbox_mode_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEX_BENCH_EVALUATOR_SANDBOX", "unsafe")
    with pytest.raises(ValueError, match="linux-bwrap or unset"):
        linux_sandbox.enabled()


def test_public_test_path_must_be_a_basename(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="basenames"):
        linux_sandbox.public_pytest_command(tmp_path, ["../private.py"])


@pytest.mark.skipif(
    sys.platform != "linux" or not Path("/usr/bin/bwrap").is_file(),
    reason="Linux bwrap required",
)
def test_hidden_candidate_cannot_read_host_or_write_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "worker"
    workspace.mkdir()
    (workspace / "answer.py").write_text("def answer(): return 'ok'\n", encoding="utf-8")
    outside = tmp_path / "private.txt"
    outside.write_text("private marker", encoding="utf-8")
    checker = tmp_path / "checker.py"
    checker.write_text(
        "from pathlib import Path\n"
        "import json, socket, sys\n"
        "outside = Path(sys.argv[2]).exists()\n"
        "try:\n"
        "    Path('/workspace/created.txt').write_text('x')\n"
        "    wrote = True\n"
        "except OSError:\n"
        "    wrote = False\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', 9), timeout=0.2)\n"
        "    connected = True\n"
        "except OSError:\n"
        "    connected = False\n"
        "print(json.dumps({'outside': outside, 'wrote': wrote, 'connected': connected}))\n",
        encoding="utf-8",
    )
    command = linux_sandbox.hidden_command(workspace, checker, str(outside), "unused")
    completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True)
    assert completed.stdout.strip() == '{"outside": false, "wrote": false, "connected": false}'
    assert not (workspace / "created.txt").exists()


@pytest.mark.skipif(
    sys.platform != "linux" or not Path("/usr/bin/bwrap").is_file(),
    reason="Linux bwrap required",
)
def test_sandbox_refuses_linked_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "worker"
    workspace.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(workspace, target_is_directory=True)
    with pytest.raises(RuntimeError, match="real, unlinked"):
        linux_sandbox.hidden_command(link, workspace / "answer.py", "answer", "answer")


@pytest.mark.skipif(
    sys.platform != "linux" or not Path("/usr/bin/bwrap").is_file(),
    reason="Linux bwrap required",
)
def test_sandbox_refuses_hardlink_into_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "worker"
    workspace.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_text("private", encoding="utf-8")
    (workspace / "linked.txt").hardlink_to(outside)
    with pytest.raises(RuntimeError, match="hard-linked"):
        linux_sandbox.public_pytest_command(workspace, ["test_public.py"])


@pytest.mark.skipif(
    sys.platform != "linux" or not Path("/usr/bin/bwrap").is_file(),
    reason="Linux bwrap required",
)
def test_sandbox_refuses_fifo_in_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "worker"
    workspace.mkdir()
    os.mkfifo(workspace / "pipe")
    with pytest.raises(RuntimeError, match="special file"):
        linux_sandbox.public_pytest_command(workspace, ["test_public.py"])
