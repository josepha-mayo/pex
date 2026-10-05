"""One-command judge demo: demo bridge + vite dev UI.

Run from the repository root:

    uv run python scripts/demo.py          # or: python scripts/demo.py
    uv run python scripts/demo.py --live   # plus a real OpenCode worker

Starts the test-scoped demo bridge on http://127.0.0.1:7420 and the vite dev
server on http://127.0.0.1:1420 (which proxies /v1 to the bridge), then prints
the URL to open. Ctrl+C stops everything. No agent install is required — the
setup card offers recorded-replay fixtures immediately.

``--live`` additionally starts ``opencode serve`` on a free OpenCode Zen model
(no API key, fresh credential-free homes), seeds a throwaway false-test-claim
workspace, attaches a persistent goal, and sends the task: a live worker under
live supervision. Needs the ``opencode`` CLI on PATH (``npm i opencode-ai``)
or ``PEX_OPENCODE_BIN``.

This launches the same processes the demo runbook lists separately; it adds
no supervision behavior of its own. Environment variables documented in
``demo_bridge.py`` pass straight through.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BRIDGE_PORT = int(os.environ.get("PEX_DEMO_PORT", "7420"))
VITE_PORT = int(os.environ.get("PEX_VITE_PORT", "1420"))
OPENCODE_PORT = int(os.environ.get("PEX_OPENCODE_PORT", "4096"))


def _npm() -> str:
    # Windows resolves npm via npm.cmd; POSIX via the npm shim.
    for name in ("npm.cmd", "npm"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit("npm is required for the UI dev server (install Node.js first).")


def _wait_http(url: str, timeout: float = 45.0, child=None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child is not None and child.poll() is not None:
            return False
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


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PEX one-command demo")
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run a real OpenCode worker on a free model under live supervision",
    )
    parser.add_argument("--worker-model", default=None, help="free OpenCode Zen model id")
    parser.add_argument(
        "--scenario",
        choices=("false-claim", "tamper"),
        default="false-claim",
        help="live scenario: a false test claim, or a controlled acceptance-test tamper",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    if not (ROOT / "apps" / "desktop" / "node_modules").is_dir():
        sys.exit("apps/desktop dependencies are missing — run `npm install` there first.")

    live = None
    bridge_env = os.environ.copy()
    children: list[subprocess.Popen] = []
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if "PEX_DEMO_HOME" not in os.environ:
        # Every launch gets a pristine stage: replays and live workers re-create
        # their sessions, so sharing build/demo/pex-home across launches would
        # pile up stale (and zombie "working") workers from older runs.
        # Set PEX_DEMO_HOME yourself to keep a stable home between runs.
        bridge_env["PEX_DEMO_HOME"] = str(ROOT / "build" / "demo" / f"home-{stamp}")
    if args.live:
        from scripts import demo_live

        executable = demo_live.resolve_opencode()
        if executable is None:
            sys.exit(
                "--live needs the OpenCode CLI: `npm i opencode-ai` (any directory on PATH) "
                "or set PEX_OPENCODE_BIN to the opencode executable."
            )
        run_root = ROOT / "build" / "demo" / f"live-{stamp}"
        model = args.worker_model or demo_live.DEFAULT_WORKER_MODEL
        try:
            workspace, worker_env = demo_live.prepare_run(run_root, model, args.scenario)
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            sys.exit(f"could not prepare the live workspace: {exc}")
        live = (workspace, model)
        bridge_env["PEX_OPENCODE_URL"] = f"http://127.0.0.1:{OPENCODE_PORT}"
        children.append(
            subprocess.Popen(
                demo_live.opencode_command(executable, OPENCODE_PORT),
                cwd=run_root,
                env=worker_env,
                stdout=(run_root / "opencode.log").open("w", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                start_new_session=(os.name != "nt"),
            )
        )

    children += [
        subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "demo_bridge.py")],
            cwd=ROOT,
            env=bridge_env,
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
    bridge, vite = children[-2], children[-1]
    try:
        checks = [
            (f"http://127.0.0.1:{BRIDGE_PORT}/health", bridge, "demo bridge"),
            (f"http://127.0.0.1:{VITE_PORT}", vite, "vite dev server"),
        ]
        if live:
            checks.insert(
                0,
                (f"http://127.0.0.1:{OPENCODE_PORT}/global/health", children[0], "opencode serve"),
            )
        failed = [name for url, child, name in checks if not _wait_http(url, child=child)]
        for name in failed:
            print(f"{name} never became ready", flush=True)
        if failed:
            for child in children:
                if child.poll() is not None:
                    print(f"child {child.pid} exited with {child.returncode}", flush=True)
            print("A demo process did not come up; see the logs above.", flush=True)
            return 1
        print()
        print(f"  PEX demo ready:  http://127.0.0.1:{VITE_PORT}", flush=True)
        print(f"  bridge API:      http://127.0.0.1:{BRIDGE_PORT}/v1", flush=True)
        if "PEX_DEMO_HOME" in bridge_env:
            print(f"  demo home:       {bridge_env['PEX_DEMO_HOME']}", flush=True)
        live_receipt: tuple[Path, str] | None = None
        if live:
            from scripts import demo_live

            workspace, model = live
            try:
                ids = demo_live.start_supervised_session(
                    workspace,
                    bridge=f"http://127.0.0.1:{BRIDGE_PORT}",
                    opencode=f"http://127.0.0.1:{OPENCODE_PORT}",
                    scenario=args.scenario,
                )
            except Exception as exc:  # noqa: BLE001 - reported, then torn down
                print(f"  live session setup failed: {exc}", flush=True)
                return 1
            print(f"  live worker:     opencode/{model} in {workspace}", flush=True)
            print(f"  session:         {ids['session_id']} (goal {ids['goal_id']})", flush=True)
            if ids.get("sibling_id"):
                print(
                    f"  handoff target:  {ids['sibling_id']} (idle sibling, same goal)",
                    flush=True,
                )
            live_receipt = (run_root, ids["goal_id"])
            print("  Select the OpenCode worker and open the Inspector to watch PEX", flush=True)
            print(
                "  catch the edited acceptance test behind a green claim."
                if args.scenario == "tamper"
                else "  contradict the false 'All tests passed' claim with real pytest.",
                flush=True,
            )
        else:
            print(
                "  Open the demo URL - Recorded replay fixtures need no agent install.",
                flush=True,
            )
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
        if live_receipt is not None:
            run_root, goal_id = live_receipt
            try:
                report = demo_live.goal_report(f"http://127.0.0.1:{BRIDGE_PORT}", goal_id)
                receipt = run_root / "pex-receipt.json"
                receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                print(f"  receipt saved:   {receipt}", flush=True)
            except Exception as exc:  # noqa: BLE001 - best-effort evidence
                print(f"  receipt fetch failed: {exc}", flush=True)
            try:
                pack = demo_live.goal_evidence_pack(
                    f"http://127.0.0.1:{BRIDGE_PORT}", goal_id
                )
                pack_path = run_root / "pex-evidence-pack.json"
                pack_path.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
                print(f"  evidence pack:   {pack_path}", flush=True)
                print("  verify offline:  uv run python scripts/verify_pack.py "
                      f"{pack_path}", flush=True)
            except Exception as exc:  # noqa: BLE001 - best-effort evidence
                print(f"  evidence pack fetch failed: {exc}", flush=True)
        for child in children:
            _terminate_tree(child)
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    sys.exit(main())
