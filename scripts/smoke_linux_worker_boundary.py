"""Exercise the writable Linux worker primitive without a model or coding harness."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    source = Path(__file__).resolve().parents[1] / "benchmarks/linux_sandbox.py"
    spec = importlib.util.spec_from_file_location("worker_boundary", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TemporaryDirectory(prefix="pex-worker-boundary-") as directory:
        root = Path(directory)
        workspace = root / "task"
        workspace.mkdir()
        oracle = root / "private-oracle.txt"
        oracle.write_text("CONTROLLER_ONLY")
        (workspace / "input.txt").write_text("public task")
        program = (
            "import os,socket; from pathlib import Path; "
            "assert Path('input.txt').read_text() == 'public task'; "
            f"assert not Path({str(oracle)!r}).exists(); "
            f"assert not Path({str(source)!r}).exists(); "
            "assert 'PEX_BOUNDARY_CONTROLLER_SENTINEL' not in os.environ; "
            "assert socket.if_nameindex() == [(1, 'lo')]; "
            "Path('result.txt').write_text('worker wrote only the task')"
        )
        environment = {**os.environ, "PEX_BOUNDARY_CONTROLLER_SENTINEL": "test-only"}
        completed = subprocess.run(
            module.worker_command(workspace, ["/usr/bin/python3", "-I", "-c", program]),
            env=environment, capture_output=True, text=True, timeout=20, check=True,
        )
        assert completed.stdout == ""
        assert (workspace / "result.txt").read_text() == "worker wrote only the task"
        assert oracle.read_text() == "CONTROLLER_ONLY"
        print(json.dumps({
            "boundary_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "smoke_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "task_read_and_write": True, "private_oracle_unavailable": True,
            "controller_source_unavailable": True, "controller_environment_unavailable": True,
            "network_interfaces": "loopback_only", "coding_harness_verified": False,
            "pex_process_isolated": False, "model_calls": 0,
        }))


if __name__ == "__main__":
    main()
