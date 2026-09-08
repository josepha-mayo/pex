from __future__ import annotations

import json
import os
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


def test_manifest_rejects_hardlink_to_file_outside_workspace(tmp_path):
    outside = tmp_path.parent / "outside-observation-secret.txt"
    outside.write_text("fixture secret", encoding="utf-8")
    try:
        os.link(outside, tmp_path / "report.txt")
    except OSError as exc:
        pytest.skip(f"host cannot create hardlinks: {type(exc).__name__}")

    with pytest.raises(ValueError, match="linked|outside"):
        snapshot(tmp_path, run_pytest=False)


def test_manifest_rejects_file_replaced_with_hardlink_after_containment_check(
    tmp_path, monkeypatch
):
    import pex_bridge.observe as observe

    outside = tmp_path.parent / "outside-race-secret.txt"
    outside.write_text("fixture secret", encoding="utf-8")
    visible = tmp_path / "report.txt"
    visible.write_text("public", encoding="utf-8")
    original_assert_readable = observe.assert_readable

    def replace_after_check(root, target):
        safe = original_assert_readable(root, target)
        if target == visible:
            visible.unlink()
            try:
                os.link(outside, visible)
            except OSError as exc:
                pytest.skip(f"host cannot create hardlinks: {type(exc).__name__}")
        return safe

    monkeypatch.setattr(observe, "assert_readable", replace_after_check)

    with pytest.raises(ValueError, match="linked|changed|outside"):
        snapshot(tmp_path, run_pytest=False)


def test_manifest_rejects_non_regular_file_before_digest(tmp_path, monkeypatch):
    if not hasattr(os, "mkfifo"):
        pytest.skip("host does not support FIFO fixtures")
    import pex_bridge.observe as observe

    os.mkfifo(tmp_path / "untrusted.pipe")
    monkeypatch.setattr(
        observe,
        "_file_digest",
        lambda _path: pytest.fail("non-regular file reached the digest reader"),
    )

    with pytest.raises(ValueError, match="regular"):
        snapshot(tmp_path, run_pytest=False)


def test_digest_rejects_non_regular_path_before_opening_it(tmp_path, monkeypatch):
    from pathlib import Path

    import pex_bridge.observe as observe

    def forbidden_open(*_args, **_kwargs):
        pytest.fail("non-regular path was opened")

    monkeypatch.setattr(Path, "open", forbidden_open)
    with pytest.raises(ValueError, match="regular"):
        observe._file_digest(tmp_path)


def test_digest_validates_opened_identity_before_reading_replaced_file(tmp_path, monkeypatch):
    from pathlib import Path

    outside = tmp_path / "private-fixture.txt"
    outside.write_text("fixture secret", encoding="utf-8")
    root = tmp_path / "workspace"
    root.mkdir()
    visible = root / "report.txt"
    visible.write_text("public", encoding="utf-8")
    original_open = Path.open

    class NoSecretReads:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def read(self, *_args):
            pytest.fail("outside fixture bytes were read")

    def replace_at_open(path, *args, **kwargs):
        if path != visible:
            return original_open(path, *args, **kwargs)
        visible.unlink()
        try:
            os.link(outside, visible)
        except OSError as exc:
            pytest.skip(f"host cannot create hardlinks: {type(exc).__name__}")
        return NoSecretReads(original_open(path, *args, **kwargs))

    monkeypatch.setattr(Path, "open", replace_at_open)
    with pytest.raises(ValueError, match="linked|changed"):
        snapshot(root)


def test_digest_rejects_content_growth_during_hashing(tmp_path, monkeypatch):
    from pathlib import Path

    import pex_bridge.observe as observe

    visible = tmp_path / "report.txt"
    visible.write_bytes(b"before")
    original_open = Path.open

    class ChangedWhileReading:
        def __init__(self, handle):
            self.handle = handle
            self.changed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def read(self, count):
            data = self.handle.read(count)
            if not self.changed:
                self.changed = True
                with original_open(visible, "ab") as output:
                    output.write(b"after")
            return data

    def changed_open(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        return ChangedWhileReading(handle) if path == visible else handle

    monkeypatch.setattr(Path, "open", changed_open)
    with pytest.raises(ValueError, match="changed"):
        observe._file_digest(visible)


def test_manifest_excludes_case_variants_of_credential_and_private_directory_names(tmp_path):
    (tmp_path / "Auth.JSON").write_text('{"token":"fixture secret"}', encoding="utf-8")
    private = tmp_path / ".AWS"
    private.mkdir()
    (private / "credentials").write_text("fixture secret", encoding="utf-8")
    (tmp_path / "answer.txt").write_text("public", encoding="utf-8")
    assert snapshot(tmp_path)["files"] == ["answer.txt"]
