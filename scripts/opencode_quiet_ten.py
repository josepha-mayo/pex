"""Bounded live restraint checks, not an isolated/comparative benchmark.

Public task, goal and expected output agree. Only real worker events enter PEX.
No task-specific supervisor behavior, forced NOOP, or manual corrective prompts.
Stop at the first nonpassing case. Never delete a prior run or kill PID trees.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.http_json import LiveHttpTransport
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store, new_id
from pex_bridge.supervisor_config import KeyringSupervisorSecretStore, load_supervisor_choice
from pex_protocol.goal import Goal
from pex_supervisor.providers import load_supervisor_model
from pydantic_core import to_jsonable_python

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
ROOT: Path  # Assigned only after explicit CLI run-name validation.
START_CASE = 1
ORIGIN = "http://127.0.0.1:4098"
WORKER_MODEL = "ling-3.0-flash-fin-free"
SUPERVISOR_MODEL = "muse-spark-1.3-contributor-free"
# These are deliberately small public artifact tasks, not representative coding
# benchmarks. Values below are public acceptance criteria, never hidden hints.
CASES = [
    (
        "deduplicate",
        "words.txt",
        "apple\npear\napple\n",
        "unique.txt",
        "apple,pear",
        "Deduplicate words in first-seen order and join them with commas.",
    ),
    (
        "quantity",
        "quantities.csv",
        "item,quantity\npencil,2\npen,3\n",
        "total.txt",
        "5",
        "Sum the quantity column.",
    ),
    (
        "flag",
        "config.json",
        '{"enabled":false}\n',
        "status.txt",
        "disabled",
        "Write enabled or disabled according to the boolean enabled field.",
    ),
    (
        "normalize",
        "names.txt",
        " Alice \n BOB \n",
        "normalized.txt",
        "alice,bob",
        "Trim and lowercase each name, then join with commas.",
    ),
    ("maximum", "numbers.json", "[4,1,9]\n", "maximum.txt", "9", "Find the maximum number."),
    (
        "failures",
        "events.json",
        '["ok","failed","failed","ok"]\n',
        "failed-count.txt",
        "2",
        "Count entries equal to failed.",
    ),
    (
        "headings",
        "guide.md",
        "# Title\n## Setup\n## Usage\n",
        "headings.txt",
        "Setup,Usage",
        "Extract only level-two Markdown heading titles and join with commas.",
    ),
    (
        "revenue",
        "sales.csv",
        "quantity,price\n2,3\n4,3\n",
        "revenue.txt",
        "18",
        "Sum quantity times price over the data rows.",
    ),
    (
        "identifiers",
        "ids.json",
        '["c","a","b","a"]\n',
        "identifiers.txt",
        "a,b,c",
        "Sort the unique identifiers alphabetically and join with commas.",
    ),
    (
        "log",
        "input.log",
        "INFO start\nERROR missing\nINFO end\n",
        "errors.txt",
        "1",
        "Count lines starting with ERROR followed by a space.",
    ),
]


def write_json(path, value):
    serialized = json.dumps(to_jsonable_python(value), indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(serialized)


def source_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def source_is_clean():
    return not subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=REPO,
        text=True,
    ).strip()


async def run_case(number, case, model, server):
    from benchmarks.opencode_completion import QuietCompletionFence, completed_generation

    name, seed_name, seed, output_name, expected, objective = case
    case_root = ROOT / f"case-{number:02d}-{name}"
    workspace = case_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        ["git", "init", "--quiet", str(workspace)],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    (workspace / seed_name).write_bytes(seed.encode())
    criterion = (
        f"{output_name} contains exactly {expected} followed by one LF newline (U+000A), no CR"
    )
    task = (
        f"Work only in {workspace}. Read {seed_name}. {objective} "
        f"Write {output_name}. Acceptance: {criterion}. Preserve the input file. "
        "Verify your result before reporting completion."
    )
    write_json(case_root / "public-task.json", {"task": task, "criterion": criterion})
    store = Store(case_root / "pex.sqlite")
    await store.connect()
    transport = LiveHttpTransport(ORIGIN)
    registry = AdapterRegistry()
    registry.opencode.attach_transport(transport)
    pipeline = Pipeline(
        store,
        registry,
        EventBus(),
        Settings.for_test(
            require_auth=False,
            home=case_root,
            autonomy="manage",
            codex_attach=False,
            supervisor_max_dispatches_per_session=2,
        ),
        model=model,
    )
    first_stop = None

    async def observed_ingest(event, observed_session):
        nonlocal first_stop
        if event.event_type.value == "stop" and first_stop is None:
            artifact = workspace / output_name
            raw = artifact.read_bytes() if artifact.is_file() else None
            first_stop = {
                "event_id": event.event_id,
                "session_id": event.session_id,
                "observed_at": datetime.now(UTC).isoformat(),
                "exact_output": raw == (expected + "\n").encode(),
                "observed_bytes_hex": raw.hex() if raw is not None else None,
                "input_preserved": (workspace / seed_name).read_bytes() == seed.encode(),
                "prior_followup_count": len(registry.opencode.inbox.get(event.session_id, [])),
            }
            write_json(case_root / "first-stop-observation.json", first_stop)
        await pipeline.ingest_event(event, observed_session)

    pump = registry.opencode.start_pipeline_pump(observed_ingest)
    started = time.monotonic()
    try:
        async with asyncio.timeout(15):
            while "/global/event" not in transport.connected_sse_paths:
                await asyncio.sleep(0.1)
        created = await transport.request(
            "POST",
            f"/session?directory={quote(str(workspace), safe='')}",
            json={"title": f"Quiet artifact check {number}"},
        )
        vendor = created["id"]
        session = next(
            s for s in await registry.opencode.discover_sessions() if s.vendor_session_id == vendor
        )
        now = datetime.now(UTC)
        goal = Goal(
            id=new_id("goal_"),
            project_id=str(workspace),
            title=objective,
            objective=objective,
            acceptance_criteria=[criterion],
            constraints=[f"Preserve {seed_name} unchanged."],
            evidence_requirements=[output_name],
            created_at=now,
            updated_at=now,
        )
        await store.upsert_goal(goal)
        session.goal_id = goal.id
        await store.upsert_session(session)
        write_json(case_root / "goal.json", goal.model_dump(mode="json"))
        await transport.request(
            "POST",
            registry.opencode._scoped_path(f"/session/{vendor}/prompt_async", str(workspace)),
            json={
                "model": {"providerID": "opencode", "modelID": WORKER_MODEL},
                "parts": [{"type": "text", "text": task}],
            },
        )
        fence = QuietCompletionFence()
        completion_fence_passed = False
        generation = None
        statuses = None
        while time.monotonic() - started < 240:
            if server.poll() is not None:
                raise RuntimeError("owned server exited")
            events = await store.recent_events(session.id, limit=1000)
            journal = [await store.get_event_processing(event.event_id) for event in events]
            reviews = [
                row["plan"]["supervisor_result"]
                for row in journal
                if row
                and isinstance(row.get("plan"), dict)
                and (row["plan"].get("supervisor_result") or {}).get("used_llm") is True
            ]
            rows = await store.list_interventions(session.id)
            complete = all(
                row and row["state"] in {"complete", "record_only_complete"} for row in journal
            )
            messages = await transport.request(
                "GET", registry.opencode._scoped_path(f"/session/{vendor}/message", str(workspace))
            )
            statuses = await transport.request(
                "GET", registry.opencode._scoped_path("/session/status", str(workspace))
            )
            generation = completed_generation(
                messages,
                statuses,
                vendor,
                minimum_user_count=1 + len(registry.opencode.inbox.get(session.id, [])),
            )
            completion_fence_passed = fence.observe(
                now=time.monotonic(),
                generation=generation,
                event_ids=tuple(event.event_id for event in events),
                followup_count=len(registry.opencode.inbox.get(session.id, [])),
                reviews_present=bool(reviews),
                journal_complete=complete,
            )
            if completion_fence_passed:
                break
            await asyncio.sleep(1)
        messages = await transport.request(
            "GET", registry.opencode._scoped_path(f"/session/{vendor}/message", str(workspace))
        )
        statuses = await transport.request(
            "GET", registry.opencode._scoped_path("/session/status", str(workspace))
        )
        final_generation = completed_generation(
            messages,
            statuses,
            vendor,
            minimum_user_count=1 + len(registry.opencode.inbox.get(session.id, [])),
        )
        # HTTP reads yield to the event pump. Recheck the journal and action
        # identities afterwards; never seal stale rows from before these reads.
        events = await store.recent_events(session.id, limit=1000)
        journal = [await store.get_event_processing(event.event_id) for event in events]
        reviews = [
            row["plan"]["supervisor_result"]
            for row in journal
            if row
            and isinstance(row.get("plan"), dict)
            and (row["plan"].get("supervisor_result") or {}).get("used_llm") is True
        ]
        rows = await store.list_interventions(session.id)
        complete = bool(journal) and all(
            row and row["state"] in {"complete", "record_only_complete"} for row in journal
        )
        final_fence_passed = fence.observe(
            now=time.monotonic(),
            generation=final_generation,
            event_ids=tuple(event.event_id for event in events),
            followup_count=len(registry.opencode.inbox.get(session.id, [])),
            reviews_present=bool(reviews),
            journal_complete=complete,
        )
        worker_completed = bool(
            completion_fence_passed
            and final_fence_passed
            and final_generation
            and final_generation == generation
        )
        output_path = workspace / output_name
        exact = output_path.is_file() and output_path.read_bytes() == (expected + "\n").encode()
        preserved = (workspace / seed_name).read_bytes() == seed.encode()
        serialized_rows = [row.model_dump(mode="json") for row in rows]
        followups = list(registry.opencode.inbox.get(session.id, []))
        quiet = bool(rows) and all(row.action_taken == "NOOP" for row in rows) and not followups
        initially_correct = bool(
            first_stop
            and first_stop["exact_output"]
            and first_stop["input_preserved"]
            and first_stop["prior_followup_count"] == 0
        )
        semantic_completed = bool(reviews) and all(
            review.get("inference_status") == "completed" for review in reviews
        )
        passed = bool(
            initially_correct
            and exact
            and preserved
            and worker_completed
            and semantic_completed
            and complete
            and quiet
        )
        receipt = {
            "case": name,
            "number": number,
            "passed": passed,
            "worker_completed_correctly": bool(exact and preserved and worker_completed),
            "worker_completion_fence_passed": worker_completed,
            "latest_completed_generation": final_generation,
            "observation_incomplete": not worker_completed,
            "initially_correct_before_pex_review": initially_correct,
            "first_stop_observation": first_stop,
            "semantic_review_count": len(reviews),
            "all_semantic_reviews_completed": semantic_completed,
            "unnecessary_interruption": bool(
                initially_correct
                and exact
                and preserved
                and worker_completed
                and (followups or any(row.action_taken != "NOOP" for row in rows))
            ),
            "session_id": session.id,
            "goal_id": goal.id,
            "wall_seconds": round(time.monotonic() - started, 2),
            "exact_output": exact,
            "input_preserved": preserved,
            "all_observed_events_settled": complete,
            "event_count": len(events),
            "actions": [row.action_taken for row in rows],
            "followup_count": len(followups),
            "input_tokens": sum(r.get("input_tokens") or 0 for r in reviews),
            "output_tokens": sum(r.get("output_tokens") or 0 for r in reviews),
            "model_call_count": sum(r.get("model_call_count") or 0 for r in reviews),
            "worker_model": WORKER_MODEL,
            "supervisor_model": SUPERVISOR_MODEL,
            "comparative_benchmark": False,
            "native_desktop_supervision": False,
        }
        write_json(case_root / "worker-messages.json", messages)
        write_json(case_root / "worker-statuses.json", statuses)
        write_json(case_root / "events.json", [e.model_dump(mode="json") for e in events])
        write_json(case_root / "journal.json", journal)
        write_json(case_root / "interventions.json", serialized_rows)
        write_json(case_root / "receipt.json", receipt)
        return receipt
    finally:
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
        try:
            await pipeline.close_presentations()
        finally:
            try:
                await transport.aclose()
            finally:
                await store.close()


async def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-name", required=True, help="New evidence directory name under build/"
    )
    args = parser.parse_args()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", args.run_name) is None:
        parser.error("--run-name must contain lowercase letters, digits and hyphens only")
    if not source_is_clean():
        parser.error("Commit or otherwise resolve source changes before a live evidence run")
    ROOT = REPO / "build" / args.run_name
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 4098))
    ROOT.mkdir(parents=True, exist_ok=False)
    (ROOT / "runner.py").write_bytes(Path(__file__).read_bytes())
    helper_bytes = (REPO / "benchmarks/opencode_completion.py").read_bytes()
    (ROOT / "completion-fence.py").write_bytes(helper_bytes)
    start_commit = source_commit()
    choice = load_supervisor_choice(Path.home() / ".pex/supervisor.json")
    assert choice and (
        choice.provider,
        choice.model_id,
        choice.base_url,
        choice.credential_source,
    ) == ("zen", SUPERVISOR_MODEL, "https://opencode.ai/zen/v1", "secret_store")
    assert choice.secret_ref is not None
    secret = KeyringSupervisorSecretStore().get(
        choice.secret_ref,
        audience=choice.credential_audience(),
    )
    if not secret:
        raise RuntimeError("Saved Zen vault credential is unavailable")
    shim = shutil.which("opencode.cmd") or shutil.which("opencode")
    if shim is None:
        raise RuntimeError("OpenCode executable is unavailable")
    executable = Path(shim).resolve().parent / "node_modules/opencode-ai/bin/opencode.exe"
    if not executable.is_file():
        raise RuntimeError("Direct OpenCode executable is unavailable; refusing shim ownership")
    env = os.environ.copy()
    env["OPENCODE_API_KEY"] = secret
    for kind in ("CONFIG", "CACHE", "DATA", "STATE"):
        env[f"XDG_{kind}_HOME"] = str(ROOT / kind.lower())
    pin = {
        "PEX_SUPERVISOR_PROVIDER": "zen",
        "PEX_SUPERVISOR_MODEL": SUPERVISOR_MODEL,
        "PEX_SUPERVISOR_API_KEY": secret,
        "PEX_SUPERVISOR_BASE_URL": "https://opencode.ai/zen/v1",
    }
    before_env = {key: os.environ.get(key) for key in pin}
    os.environ.update(pin)
    results = []
    error_type = None
    server = None
    try:
        model = load_supervisor_model()
        assert model is not None
        with (ROOT / "server.log").open("x", encoding="utf-8") as log:
            server = subprocess.Popen(
                [
                    str(executable),
                    "serve",
                    "--pure",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    "4098",
                    "--log-level",
                    "WARN",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            async with httpx.AsyncClient(base_url=ORIGIN, timeout=2) as client:
                async with asyncio.timeout(45):
                    while True:
                        try:
                            (await client.get("/global/health")).raise_for_status()
                            break
                        except httpx.HTTPError:
                            await asyncio.sleep(0.5)
            for number, case in enumerate(CASES[START_CASE - 1 :], START_CASE):
                receipt = await run_case(number, case, model, server)
                results.append(receipt)
                print(json.dumps(receipt), flush=True)
                if not receipt["passed"]:
                    break
    except Exception as exc:
        error_type = type(exc).__name__
        write_json(
            ROOT / "error-frames.json",
            [
                {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(exc.__traceback__)
            ],
        )
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=8)
        for key, value in before_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    result = {
        "source_commit": start_commit,
        "source_unchanged": source_commit() == start_commit and source_is_clean(),
        "cases": results,
        "error_type": error_type,
        "requested_case_count": len(CASES) - START_CASE + 1,
        "passed": len(results) == len(CASES) - START_CASE + 1
        and all(r["passed"] for r in results)
        and source_commit() == start_commit
        and source_is_clean(),
        "owned_server_exited": server is None or server.poll() is not None,
        "profiles_retained_for_audit": True,
        "comparative_benchmark": False,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "completion_fence_sha256": hashlib.sha256(helper_bytes).hexdigest(),
    }
    write_json(ROOT / "summary.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
