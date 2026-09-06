from __future__ import annotations

import json
import time

import pytest
from pex_bridge.observe import snapshot


def test_public_workspace_tests_are_never_executed_by_default(tmp_path):
    marker = tmp_path / "executed.txt"
    (tmp_path / "test_untrusted.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )

    observed = snapshot(tmp_path)

    assert observed["pytest"] is None
    assert not marker.exists()


def test_public_pytest_receives_no_parent_secret_and_redacts_output(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abcdefghijklmnopqrstuvwxyz123456")
    (tmp_path / "test_public.py").write_text(
        "import os\n\n"
        "def test_environment_is_minimal():\n"
        "    assert os.getenv('OPENAI_API_KEY') is None\n",
        encoding="utf-8",
    )

    observed = snapshot(tmp_path, run_pytest=True)

    assert observed["pytest"]["ok"] is True
    assert "sk-" not in json.dumps(observed)


def test_public_pytest_timeout_kills_stdout_inheriting_descendants(tmp_path, monkeypatch):
    import pex_bridge.observe as observe

    monkeypatch.setattr(observe, "_PYTEST_TIMEOUT_SECONDS", 0.25)
    (tmp_path / "test_descendant.py").write_text(
        "import subprocess, sys, time\n\n"
        "def test_stall():\n"
        "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "    time.sleep(30)\n",
        encoding="utf-8",
    )

    started = time.monotonic()
    observed = snapshot(tmp_path, run_pytest=True)

    assert time.monotonic() - started < 6
    assert observed["pytest"]["timed_out"] is True


def test_manifest_skips_common_local_credential_files(tmp_path):
    (tmp_path / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("TOKEN=do-not-read\n", encoding="utf-8")
    (tmp_path / "auth.json").write_text('{"token":"do-not-read"}', encoding="utf-8")

    observed = snapshot(tmp_path, run_pytest=False)

    assert observed["files"] == ["answer.py"]
    assert "do-not-read" not in json.dumps(observed)


def test_manifest_fails_closed_when_file_count_bound_is_exceeded(tmp_path, monkeypatch):
    import pex_bridge.observe as observe

    monkeypatch.setattr(observe, "_MAX_MANIFEST_FILES", 1)
    (tmp_path / "first.py").write_text("1", encoding="utf-8")
    (tmp_path / "second.py").write_text("2", encoding="utf-8")

    with pytest.raises(ValueError, match="file observation bound"):
        snapshot(tmp_path, run_pytest=False)
