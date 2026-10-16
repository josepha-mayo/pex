"""One-command judge demo: demo bridge + web UI (vite).

Run from the repository root:

    uv run python scripts/demo.py              # bridge :7420 + web UI :1420
    uv run python scripts/demo.py --live       # plus a real OpenCode worker
    uv run python scripts/demo.py --bridge-only  # bridge only, no web UI
    uv run python scripts/demo.py --prebuilt     # bridge + prebuilt dist via preview

Starts the test-scoped demo bridge on http://127.0.0.1:7420 and the web UI
vite server on http://127.0.0.1:1420 (which proxies /v1 to the bridge), then
prints the URL to open. Ctrl+C stops everything. No agent install is required -
the setup card offers recorded-replay fixtures immediately. The packaged
Tauri desktop is frozen/optional — the default here is the web UI.

``--live`` additionally starts ``opencode serve`` on a free OpenCode Zen model
(no API key, fresh credential-free homes), seeds a throwaway false-test-claim
workspace, attaches a persistent goal, and sends the task: a live worker under
live supervision. Needs the ``opencode`` CLI on PATH (``npm i opencode-ai``)
or ``PEX_OPENCODE_BIN``.

``--bridge-only`` starts only the bridge (no web UI process).
``--prebuilt`` serves the prebuilt web UI from ``apps/desktop/dist``
(``npm run build`` once) via ``vite preview`` instead of the vite dev server.

This launches the same processes the demo runbook lists separately; it adds
no supervision behavior of its own. Environment variables documented in
``demo_bridge.py`` pass straight through. Ports: ``PEX_DEMO_PORT`` (bridge,
default 7420), ``PEX_VITE_PORT`` (web UI, default 1420), ``PEX_OPENCODE_PORT``
(``--live`` worker server, default 4096).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
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


def _pid_on_port(port: int) -> str | None:
    """Best-effort PID of a loopback listener - for an actionable error."""

    try:
        if os.name == "nt":
            out = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                if (
                    len(parts) >= 5
                    and parts[1].rsplit(":", 1)[-1] == str(port)
                    and parts[3].upper() == "LISTENING"
                ):
                    return parts[-1]
        else:
            out = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True,
                text=True,
            ).stdout
            first = out.strip().splitlines()
            return first[0] if first else None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _ensure_port_free(port: int, label: str, env_name: str) -> None:
    """Fail loudly on a stale service instead of probing someone else's health.

    A squatting process answers the readiness probe just as well as our own
    child - the run then proceeds against the wrong service (or its own child
    exits and tears the demo down). Check the port *before* spawning so the
    message can name the real culprit.
    """

    probe = socket.socket()
    try:
        occupied = probe.connect_ex(("127.0.0.1", port)) == 0
    finally:
        probe.close()
    if not occupied:
        return
    pid = _pid_on_port(port)
    owner = f" (pid {pid})" if pid else ""
    if pid and os.name == "nt":
        kill_hint = f"stop it (e.g. `taskkill /PID {pid} /F`)"
    elif pid:
        kill_hint = f"stop it (e.g. `kill {pid}`)"
    else:
        kill_hint = "stop it"
    sys.exit(
        f"{label} port 127.0.0.1:{port} is already in use{owner} - likely a stale "
        f"service from an earlier run; {kill_hint} first, or set {env_name}."
    )


def _wait_http(url: str, timeout: float = 45.0, child=None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child is not None and child.poll() is not None:
            return False
        try:
            # /health runs the bounded adapter probes (tasklist + loopback
            # checks), which takes a few seconds on Windows - not instant.
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
    parser = argparse.ArgumentParser(
        description="PEX one-command demo (bridge :7420 + web UI :1420)",
        epilog=(
            "ports: PEX_DEMO_PORT (bridge, default 7420), "
            "PEX_VITE_PORT (web UI, default 1420), "
            "PEX_OPENCODE_PORT (--live worker server, default 4096)"
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run a real OpenCode worker on a free model under live supervision",
    )
    parser.add_argument(
        "--bridge-only",
        action="store_true",
        help="start only the demo bridge on PEX_DEMO_PORT, skip the web UI",
    )
    parser.add_argument(
        "--prebuilt",
        action="store_true",
        help="serve the prebuilt web UI from apps/desktop/dist via vite preview "
        "instead of the vite dev server (run `npm run build` under apps/desktop once)",
    )
    parser.add_argument(
        "--worker-model",
        default=None,
        help=(
            "worker model id — a free OpenCode Zen model, or a Token Factory "
            "NVIDIA model (nvidia/…) when NEBIUS_API_KEY is set"
        ),
    )
    parser.add_argument(
        "--scenario",
        choices=("false-claim", "tamper"),
        default="false-claim",
        help="live scenario: a false test claim, or a controlled acceptance-test tamper",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    run_ui = not args.bridge_only
    use_prebuilt = args.prebuilt and run_ui
    if run_ui and not (ROOT / "apps" / "desktop" / "node_modules").is_dir():
        sys.exit(
            "web UI dependencies are missing under apps/desktop - run "
            "`npm install --prefix apps/desktop` once (vite only, no Rust/Tauri) first."
        )
    if use_prebuilt and not (ROOT / "apps" / "desktop" / "dist").is_dir():
        sys.exit(
            "prebuilt web UI not found at apps/desktop/dist - run "
            "`npm run build` under apps/desktop once, or drop --prebuilt for the vite dev server."
        )
    try:
        import importlib.util

        missing = [
            name for name in ("uvicorn", "pex_bridge") if importlib.util.find_spec(name) is None
        ]
    except ImportError:
        missing = ["uvicorn", "pex_bridge"]
    if missing:
        sys.exit(
            f"this interpreter is missing {', '.join(missing)} - the bridge spawns "
            "on the same Python. Use the workspace env: `uv run python scripts/demo.py` "
            "(auto-syncs dependencies) or activate `.venv` first."
        )

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
    _ensure_port_free(BRIDGE_PORT, "demo bridge", "PEX_DEMO_PORT")
    if run_ui:
        _ensure_port_free(VITE_PORT, "web UI", "PEX_VITE_PORT")
    if args.live:
        _ensure_port_free(OPENCODE_PORT, "opencode serve", "PEX_OPENCODE_PORT")
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
            workspace, worker_env = demo_live.prepare_run(
                run_root, model, args.scenario, bridge_port=BRIDGE_PORT
            )
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

    children.append(
        subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "demo_bridge.py")],
            cwd=ROOT,
            env=bridge_env,
            start_new_session=(os.name != "nt"),
        ),
    )
    bridge = children[-1]
    vite = None
    if run_ui:
        ui_script = "preview" if use_prebuilt else "dev"
        children.append(
            subprocess.Popen(
                [
                    _npm(),
                    "run",
                    ui_script,
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(VITE_PORT),
                    "--strictPort",
                ],
                cwd=ROOT / "apps" / "desktop",
                env={
                    **os.environ,
                    "PEX_BRIDGE_URL": f"http://127.0.0.1:{BRIDGE_PORT}",
                },
                start_new_session=(os.name != "nt"),
            ),
        )
        vite = children[-1]
    live_receipt: tuple[Path, str] | None = None
    try:
        checks = [
            (f"http://127.0.0.1:{BRIDGE_PORT}/health", bridge, "demo bridge"),
        ]
        if vite is not None:
            ui_name = "prebuilt web UI" if use_prebuilt else "web UI"
            checks.append((f"http://127.0.0.1:{VITE_PORT}", vite, ui_name))
        if live:
            checks.insert(
                0,
                (f"http://127.0.0.1:{OPENCODE_PORT}/global/health", children[0], "opencode serve"),
            )
        failed = []
        for url, child, name in checks:
            # A cold `opencode serve` (node startup + model catalog fetch) can
            # exceed the default readiness window on this machine.
            budget = 120.0 if name == "opencode serve" else 45.0
            print(f"waiting for {name} at {url} ...", flush=True)
            if not _wait_http(url, timeout=budget, child=child):
                failed.append(name)
        for name in failed:
            print(f"{name} never became ready", flush=True)
        if failed:
            for child in children:
                if child.poll() is not None:
                    print(f"child {child.pid} exited with {child.returncode}", flush=True)
            print("A demo process did not come up; see the logs above.", flush=True)
            return 1
        print()
        if vite is not None:
            print(f"  PEX demo ready:  http://127.0.0.1:{VITE_PORT}", flush=True)
        else:
            print("  PEX demo ready:  bridge only (no web UI)", flush=True)
        print(f"  bridge API:      http://127.0.0.1:{BRIDGE_PORT}/v1", flush=True)
        if "PEX_DEMO_HOME" in bridge_env:
            print(f"  demo home:       {bridge_env['PEX_DEMO_HOME']}", flush=True)
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
            if vite is not None:
                print(
                    "  Open the demo URL - Recorded replay fixtures need no agent install.",
                    flush=True,
                )
            else:
                print(
                    "  Bridge only - use the API at /v1 or POST /v1/demo/replay for fixtures.",
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
                pack = demo_live.goal_evidence_pack(f"http://127.0.0.1:{BRIDGE_PORT}", goal_id)
                pack_path = run_root / "pex-evidence-pack.json"
                pack_path.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
                print(f"  evidence pack:   {pack_path}", flush=True)
                print(
                    f"  verify offline:  uv run python scripts/verify_pack.py {pack_path}",
                    flush=True,
                )
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
