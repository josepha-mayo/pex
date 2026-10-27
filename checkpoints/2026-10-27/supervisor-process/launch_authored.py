"""Bounded separate interpreter for trusted authored preflight, never candidates."""

import argparse
import json
import os
import signal
import subprocess
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
        out, err = process.communicate(timeout=30)
        if len(out) + len(err) > 65536:
            raise RuntimeError("authored output bound exceeded")
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
