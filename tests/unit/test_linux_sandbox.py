from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from benchmarks import linux_sandbox


@pytest.mark.skipif(
    sys.platform != "linux" or not Path("/usr/bin/bwrap").is_file(),
    reason="Linux bwrap required",
)
def test_worker_relay_socket_preserves_host_files_and_network_boundary(tmp_path):
    workspace = tmp_path / "worker"
    workspace.mkdir()
    private = tmp_path / "private.txt"
    private.write_text("private controller value", encoding="utf-8")
    received = []
    with TemporaryDirectory(prefix="pex-relay-") as relay_root:
        endpoint = Path(relay_root) / "relay.sock"
        with socket.socket(socket.AF_UNIX) as relay, socket.socket() as host_network:
            relay.bind(str(endpoint))
            endpoint.chmod(0o600)
            relay.listen()
            relay.settimeout(5)
            host_network.bind(("127.0.0.1", 0))
            host_network.listen()
            port = host_network.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass

            def exchange():
                with relay.accept()[0] as connection:
                    connection.settimeout(2)
                    received.append(connection.recv(64))
                    connection.sendall(b"echo")

            server = threading.Thread(target=exchange)
            server.start()
            script = (
                "import json,os,socket; from pathlib import Path; "
                "s=socket.socket(socket.AF_UNIX); s.settimeout(2); "
                "s.connect(os.environ['PEX_MODEL_RELAY_SOCKET']); "
                "s.sendall(b'bounded probe'); reply=s.recv(64).decode(); s.close(); "
                "Path('/workspace/result.txt').write_text(reply); "
                "network=False\n"
                f"try:\n socket.create_connection(('127.0.0.1',{port}),timeout=.2); "
                "network=True\nexcept OSError:\n pass\n"
                f"print(json.dumps({{'reply':reply,'network':network,"
                f"'private_visible':Path({str(private)!r}).exists()}}))"
            )
            try:
                completed = subprocess.run(
                    linux_sandbox.worker_relay_command(
                        workspace, ["/usr/bin/python3", "-I", "-c", script], endpoint,
                    ), capture_output=True, text=True, timeout=10, check=True,
                )
            finally:
                server.join(timeout=6)
            assert not server.is_alive()
            assert received == [b"bounded probe"]
            assert json.loads(completed.stdout) == {
                "reply": "echo", "network": False, "private_visible": False,
            }
            assert (workspace / "result.txt").read_text() == "echo"
            endpoint.chmod(0o644)
            with pytest.raises(ValueError, match="owner-only"):
                linux_sandbox.worker_relay_command(workspace, ["/usr/bin/true"], endpoint)
            endpoint.chmod(0o600)
            alias = Path(relay_root) / "alias.sock"
            alias.symlink_to(endpoint)
            with pytest.raises(ValueError, match="unlinked"):
                linux_sandbox.worker_relay_command(workspace, ["/usr/bin/true"], alias)
            with pytest.raises(ValueError, match="Unix socket"):
                linux_sandbox.worker_relay_command(workspace, ["/usr/bin/true"], private)


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
def test_public_pytest_disables_external_plugin_autoload(tmp_path: Path) -> None:
    workspace = tmp_path / "worker"
    workspace.mkdir()
    (workspace / "test_public.py").write_text(
        "import os\n"
        "def test_runtime_environment():\n"
        "    assert os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD') == '1'\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        linux_sandbox.public_pytest_command(workspace, ["test_public.py"]),
        capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(
    sys.platform != "linux" or not Path("/usr/bin/bwrap").is_file(),
    reason="Linux bwrap required",
)
def test_public_pytest_failure_names_the_actual_workspace_test(tmp_path: Path) -> None:
    workspace = tmp_path / "worker"
    workspace.mkdir()
    (workspace / "test_public.py").write_text(
        "def test_failure():\n    assert False\n", encoding="utf-8",
    )
    completed = subprocess.run(
        linux_sandbox.public_pytest_command(workspace, ["test_public.py"]),
        capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 1
    assert "FAILED test_public.py::test_failure" in completed.stdout


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


@pytest.mark.skipif(
    sys.platform != "linux" or not Path("/usr/bin/bwrap").is_file(),
    reason="Linux bwrap required",
)
def test_supervisor_boundary_excludes_controller_and_protects_public_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, runtime, control = [tmp_path / name for name in ("worker", "runtime", "control")]
    for directory in (workspace, runtime, control):
        directory.mkdir()
    (workspace / "TASK.md").write_text("Public task", encoding="utf-8")
    private = tmp_path / "oracle.txt"
    private.write_text("private expected answer", encoding="utf-8")
    monkeypatch.setenv("PEX_BOUNDARY_PRIVATE_MARKER", "private controller environment")
    entry = runtime / "pex_supervisor_process.py"
    entry.write_text(
        "import json, os, socket, sys\n"
        "from pathlib import Path\n"
        "payload = json.loads(Path(sys.argv[1]).read_text())\n"
        "def can_write(path):\n"
        "    try:\n"
        "        Path(path).write_text('changed')\n"
        "        return True\n"
        "    except OSError:\n"
        "        return False\n"
        "try:\n"
        "    connection = socket.create_connection(('127.0.0.1', payload['port']), timeout=.2)\n"
        "    connection.close()\n"
        "    network = True\n"
        "except OSError:\n"
        "    network = False\n"
        "result = {'private_exists': Path(payload['private']).exists(),\n"
        "          'private_env': 'PEX_BOUNDARY_PRIVATE_MARKER' in os.environ,\n"
        "          'network': network, 'public_task': Path('/workspace/TASK.md').read_text(),\n"
        "          'workspace_write': can_write('/workspace/TASK.md'),\n"
        "          'runtime_write': can_write('/runtime/pex_supervisor_process.py'),\n"
        "          'request_write': can_write('/control/request.json'),\n"
        "          'model_disabled': os.environ.get('PEX_SUPERVISOR_DISABLE') == '1'}\n"
        "Path(sys.argv[2]).write_text(json.dumps(result))\n",
        encoding="utf-8",
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
        request = control / "request.json"
        request.write_text(json.dumps({"private": str(private), "port": port}), encoding="utf-8")
        original_request = request.read_bytes()
        original_entry = entry.read_bytes()
        subprocess.run(
            linux_sandbox.supervisor_command(workspace, runtime, control),
            capture_output=True, text=True, timeout=10, check=True,
        )
    assert json.loads((control / "response.json").read_text()) == {
        "private_exists": False, "private_env": False, "network": False,
        "public_task": "Public task", "workspace_write": False, "runtime_write": False,
        "request_write": False, "model_disabled": True,
    }
    assert request.read_bytes() == original_request
    assert entry.read_bytes() == original_entry
    assert (workspace / "TASK.md").read_text() == "Public task"
    with pytest.raises(ValueError, match="fresh request"):
        linux_sandbox.supervisor_command(workspace, runtime, control)
