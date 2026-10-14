"""Prove the worker-facing MCP round trip end-to-end.

``scripts/demo.py --live`` mounts this bridge's ``/mcp`` server into the
seeded worker's ``opencode.json`` through the stdio shim
(``scripts/pex_mcp_stdio.py``), because ``opencode serve`` connects remote
MCP servers without registering their tools into sessions (verified on
1.18.32 and 1.19.0) while local servers register fine. This script instead
exercises the direct remote path through ``opencode run`` — which does
register remote tools — so both transports are covered by a checkable
proof:

1. find a goal-bound session on a running demo bridge,
2. write a throwaway workspace whose ``opencode.json`` mounts that bridge's
   ``/mcp`` endpoint (anonymous read-only scope — no credential),
3. run ``opencode run`` asking the worker to call ``pex_pex_get_goal`` for
   that exact session,
4. report PASS only if the tool was invoked and returned the goal title.

Usage (demo bridge running, at least one replay/worker session run):

    uv run python scripts/probe_worker_mcp.py

Exit code 0 on PASS, 1 otherwise. No secrets are read or written.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from demo_live import _call, resolve_opencode  # noqa: E402

from benchmarks.opencode_proof_route import proof_worker_config  # noqa: E402

PROMPT = (
    'Call the tool pex_pex_get_goal with session_id "{session_id}" '
    "and report the goal title it returns. Do not write any files."
)


def _find_goal_bound_session(bridge: str) -> tuple[str, str]:
    """Return (session_id, goal_title) for a session with an attached goal."""
    for session in _call("GET", f"{bridge}/v1/sessions") or []:
        detail = _call("GET", f"{bridge}/v1/sessions/{urllib.parse.quote(session['id'], safe='')}")
        goal_id = (detail or {}).get("goal_id")
        if not goal_id:
            continue
        goal = _call("GET", f"{bridge}/v1/goals/{urllib.parse.quote(goal_id, safe='')}") or {}
        title = goal.get("title") or goal.get("goal", {}).get("title")
        if title:
            return session["id"], str(title)
    raise SystemExit(
        "no goal-bound session on the bridge — run `python scripts/demo.py`, "
        "click any replay fixture (or start --live), then re-run this probe"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bridge", default="http://127.0.0.1:7420")
    parser.add_argument("--opencode", default=None, help="opencode binary override")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    executable = Path(args.opencode) if args.opencode else resolve_opencode()
    if executable is None:
        raise SystemExit("opencode not found — set PATH or pass --opencode")

    session_id, goal_title = _find_goal_bound_session(args.bridge)
    print(f"bridge:   {args.bridge}")
    print(f"session:  {session_id}")
    print(f"goal:     {goal_title}")

    with tempfile.TemporaryDirectory(prefix="pex-mcp-probe-") as tmp:
        root = Path(tmp)
        # Same free worker route + credential-free homes as scripts/demo.py --live,
        # plus the MCP mount (anonymous read-only — no credential is written).
        config = proof_worker_config(
            "opencode", "nemotron-3-ultra-free", "OpenCode Zen", native_free=True
        )
        config["mcp"] = {"pex": {"type": "remote", "url": f"{args.bridge}/mcp/", "enabled": True}}
        (root / "opencode.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        # `opencode run` is headless CLI usage: the Zen free tier refuses it
        # without a signed-in OpenCode profile, so this probe deliberately
        # inherits the caller's environment (unlike demo.py's scrubbed
        # serve-mode worker homes).
        env = dict(os.environ)
        result = subprocess.run(
            [
                str(executable),
                "run",
                "--print-logs",
                "--dir",
                str(root),
                PROMPT.format(session_id=session_id),
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    output = (result.stdout or "") + (result.stderr or "")

    invoked = "pex_pex_get_goal" in output
    answered = f"{session_id}" in output and "session not found" not in output
    returned_goal = goal_title.lower() in output.lower()
    for line in output.splitlines():
        if "pex_pex_get_goal" in line or goal_title in line:
            print(f"  evidence: {line.strip()[:200]}")
    if not (invoked and returned_goal):
        if "free tier" in output.lower() or "Forbidden" in output:
            print(
                "  worker model unavailable: `opencode run` needs a signed-in "
                "OpenCode profile or provider key — the Zen free tier only "
                "serves app-mode traffic"
            )
        print("  --- opencode output (tail) ---")
        for line in output.splitlines()[-12:]:
            print(f"  {line[:200]}")
    print(
        f"RESULT: {'PASS' if invoked and returned_goal else 'FAIL'} "
        f"(tool invoked: {invoked}, goal title returned: {returned_goal}, "
        f"session resolved: {answered})"
    )
    return 0 if invoked and returned_goal else 1


if __name__ == "__main__":
    raise SystemExit(main())
