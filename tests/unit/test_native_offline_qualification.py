"""Plan/negative-path tests only, not actual kernel/runtime qualification."""

from pathlib import Path

import pytest

from scripts import qualify_native_offline as qualification


def test_wrong_binary_is_rejected_before_launch(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "opencode").write_bytes(b"not the pinned executable")
    monkeypatch.setattr(qualification.subprocess, "Popen", lambda *a, **k: pytest.fail("launched"))
    (tmp_path / "task").mkdir()
    with pytest.raises(ValueError, match="hash mismatch"):
        qualification.invoke(tmp_path / "task", runtime, ["/native/opencode", "--version"])


def test_namespace_construction_has_no_model_relay_or_network_sharing(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    binary = runtime / "opencode"
    binary.write_bytes(b"synthetic fixture")
    monkeypatch.setattr(
        qualification, "DIGEST", qualification.hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(
        qualification,
        "worker_command",
        lambda task, argv: [
            "/usr/bin/bwrap",
            "--unshare-all",
            "--clearenv",
            "--",
            *argv,
        ],
    )
    (tmp_path / "task").mkdir()
    args = qualification.command(
        tmp_path / "task", runtime, ["/native/opencode", "debug", "config"]
    )
    assert args[0] == "/usr/bin/bwrap"
    assert "--unshare-all" in args
    assert "--share-net" not in args
    assert not any("relay" in arg for arg in args)
    assert args[args.index("--") + 1 :] == ["/native/opencode", "debug", "config"]


def test_workflow_is_unpublished_draft_and_branch_scoped():
    root = Path(__file__).resolve().parents[2]
    draft = root / "docs/qualification/native-offline-actions.yml"
    text = draft.read_text()
    assert not (root / ".github/workflows/native-offline-actions.yml").exists()
    assert "workflow_dispatch:" not in text
    assert "pull_request:" not in text and "push:" in text
    assert "branches: [review/native-offline-qualification-20261021]" in text
    assert "paths: [.github/workflows/native-offline-qualification.yml]" in text
    assert "ref: REPLACE_WITH_VERIFIED_PUBLIC_SOURCE_COMMIT_SHA" in text
    assert "persist-credentials: false" in text
    assert "runs-on: ubuntu-24.04" in text
    assert "upload-artifact@" not in text
    assert "secrets." not in text
    assert "sudo " not in text
    assert "npm install" not in text
    assert "11bd71901bbe5b1630ceea73d27597364c9af683" in text


def test_timeout_diagnoses_possible_install_without_claiming_cause(monkeypatch):
    monkeypatch.setattr(qualification, "command", lambda *a: ["synthetic"])

    def timeout(*args, **kwargs):
        raise qualification.subprocess.TimeoutExpired("synthetic", 90, stderr=b"fixture stderr")

    monkeypatch.setattr(qualification, "_run_bounded", timeout)
    with pytest.raises(RuntimeError, match="possible, not established"):
        qualification.invoke(None, None, [])


def test_background_dependency_failure_is_not_silently_successful(monkeypatch):
    monkeypatch.setattr(qualification, "command", lambda *a: ["synthetic"])
    monkeypatch.setattr(
        qualification,
        "_run_bounded",
        lambda *a, **k: qualification.subprocess.CompletedProcess(
            "synthetic", 0, b"{}", b"background dependency install failed"
        ),
    )
    with pytest.raises(RuntimeError, match="network remains disabled"):
        qualification.invoke(None, None, [])


def test_runtime_under_writable_task_is_rejected(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "opencode").write_bytes(b"fixture")
    with pytest.raises(ValueError, match="disjoint"):
        qualification.command(tmp_path, runtime, ["/native/opencode", "--version"])


@pytest.mark.parametrize("mode", ["overflow", "timeout", "success", "survivor"])
def test_bounded_capture_reaps_group_without_launching(mode, monkeypatch):
    class Pipe:
        closed = False

        def fileno(self):
            return 42

        def close(self):
            self.closed = True

    class Process:
        pid, returncode = 123456, 0
        stdout, stderr = Pipe(), Pipe()
        waits = []

        def wait(self, timeout):
            self.waits.append(timeout)

    proc = Process()
    monkeypatch.setattr(qualification.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(qualification.os, "set_blocking", lambda *a: None)
    signals = []

    def killpg(pid, sig):
        signals.append(sig)
        if sig == 0 and mode != "survivor":
            raise ProcessLookupError

    monkeypatch.setattr(qualification.os, "killpg", killpg)

    class Selector:
        def __init__(self):
            self.entries = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def register(self, pipe, event, label):
            self.entries.append((pipe, label))

        def unregister(self, pipe):
            self.entries = [x for x in self.entries if x[0] is not pipe]

        def get_map(self):
            return self.entries

        def select(self, timeout):
            from types import SimpleNamespace

            return [(SimpleNamespace(fileobj=p, data=label), 1) for p, label in list(self.entries)]

    monkeypatch.setattr(qualification.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(
        qualification.os, "read", lambda *a: b"x" * 5 if mode == "overflow" else b""
    )
    monkeypatch.setattr(qualification, "MAX_OUTPUT", 4)
    times = iter([0, 100] if mode == "timeout" else [0] * 10)
    monkeypatch.setattr(qualification.time, "monotonic", lambda: next(times))
    if mode == "success":
        assert qualification._run_bounded(["synthetic"]).stdout == b""
    else:
        with pytest.raises((RuntimeError, qualification.subprocess.TimeoutExpired)):
            qualification._run_bounded(["synthetic"])
    assert qualification.signal.SIGKILL in signals
    assert proc.stdout.closed and proc.stderr.closed
    assert 5 in proc.waits
