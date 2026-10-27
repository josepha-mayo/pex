"""Bounded separate interpreter for trusted authored preflight, never candidates."""

import argparse
import json
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path


def run(python: Path, transport: Path, pex: Path):
    own = Path(__file__).resolve().parent
    roots = [
        own,
        transport,
        transport / "tests",
        pex / "packages/protocol/src",
        pex / "services/supervisor/src",
        pex / "services/bridge/src",
    ]
    if any(not p.is_absolute() or not p.is_dir() or p.resolve() != p for p in roots):
        raise ValueError("explicit unlinked trusted source roots required")
    # Fixed script only: no request/credential/provider/runtime-code input.
    bootstrap = 'import sys,runpy,json; sys.path[:0]=json.loads(sys.argv[1]); runpy.run_path(sys.argv[2],run_name="__main__")'
    process = subprocess.Popen(
        [
            str(python),
            "-I",
            "-c",
            bootstrap,
            json.dumps([str(p) for p in roots]),
            str(own / "run_authored.py"),
        ],
        cwd=own,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTEST_PLUGINS": "pytest_asyncio.plugin",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        buffers = {process.stdout: bytearray(), process.stderr: bytearray()}
        deadline = time.monotonic() + 30
        total = 0
        with selectors.DefaultSelector() as selector:
            for pipe in buffers:
                selector.register(pipe, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("authored process deadline exceeded")
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), min(4096, 65537 - total))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > 65536:
                        raise RuntimeError("authored output bound exceeded")
                    buffers[key.fileobj].extend(chunk)
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
        out, err = bytes(buffers[process.stdout]), bytes(buffers[process.stderr])
        return {
            "exit_code": process.returncode,
            "stdout": out.decode(),
            "stderr": err.decode(),
            "mode": "authored-fixture-only",
            "real_inference_calls": 0,
        }
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--transport", type=Path, required=True)
    parser.add_argument("--pex", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.python, args.transport, args.pex)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(result["exit_code"])
