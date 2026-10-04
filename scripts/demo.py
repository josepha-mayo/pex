"""One-command judge demo: demo bridge + vite dev UI.

Run from the repository root:

    uv run python scripts/demo.py          # or: python scripts/demo.py

Starts the test-scoped demo bridge on http://127.0.0.1:7420 and the vite dev
server on http://127.0.0.1:1420 (which proxies /v1 to the bridge), then prints
the URL to open. Ctrl+C stops both. No agent install is required — the setup
card offers recorded-replay fixtures immediately.

This launches the same two processes the demo runbook lists separately; it
adds no behavior of its own. Environment variables documented in
``demo_bridge.py`` pass straight through.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIDGE_PORT = int(os.environ.get("PEX_DEMO_PORT", "7420"))
VITE_PORT = int(os.environ.get("PEX_VITE_PORT", "1420"))


def _npm() -> str:
    # Windows resolves npm via npm.cmd; POSIX via the npm shim.
    for name in ("npm.cmd", "npm"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit("npm is required for the UI dev server (install Node.js first).")


def _wait_http(url: str, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            # /health runs the bounded adapter probes (tasklist + loopback
            # checks), which takes a few seconds on Windows — not instant.
            with urllib.request.urlopen(url, timeout=10) as response:
                return response.status == 200
        except Exception:
            time.sleep(0.25)
    return False


def _terminate_tree(child: subprocess.Popen) -> None:
    """Stop a child and its grandchildren.

    npm/vite spawn real workers beneath the wrapper process, so signalling the
    direct child alone leaks the dev server. POSIX children get their own
    process group for killpg; Windows uses taskkill /T.
    """
    if child.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(child.pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        child.terminate()


def main() -> int:
    if not (ROOT / "apps" / "desktop" / "node_modules").is_dir():
        sys.exit("apps/desktop dependencies are missing — run `npm install` there first.")

    children = [
        subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "demo_bridge.py")],
            cwd=ROOT,
            start_new_session=(os.name != "nt"),
        ),
        subprocess.Popen(
            [
                _npm(),
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(VITE_PORT),
                "--strictPort",
            ],
            cwd=ROOT / "apps" / "desktop",
            start_new_session=(os.name != "nt"),
        ),
    ]
    try:
        bridge_ok = _wait_http(f"http://127.0.0.1:{BRIDGE_PORT}/health")
        vite_ok = _wait_http(f"http://127.0.0.1:{VITE_PORT}")
        if not bridge_ok:
            print(f"demo bridge never answered :{BRIDGE_PORT}/health", flush=True)
        if not vite_ok:
            print(f"vite dev server never answered :{VITE_PORT}", flush=True)
        if not (bridge_ok and vite_ok):
            for child in children:
                if child.poll() is not None:
                    print(f"child {child.pid} exited with {child.returncode}", flush=True)
            print("A demo process did not come up; see the logs above.", flush=True)
            return 1
        print()
        print(f"  PEX demo ready:  http://127.0.0.1:{VITE_PORT}", flush=True)
        print(f"  bridge API:      http://127.0.0.1:{BRIDGE_PORT}/v1", flush=True)
        print("  Open the demo URL - Recorded replay fixtures need no agent install.", flush=True)
        print("  Ctrl+C to stop.", flush=True)
        while True:
            time.sleep(1)
            for child in children:
                if child.poll() is not None:
                    print(
                        f"demo process exited ({child.returncode}); shutting down",
                        flush=True,
                    )
                    return child.returncode if child.returncode and child.returncode > 0 else 1
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            _terminate_tree(child)
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    sys.exit(main())
