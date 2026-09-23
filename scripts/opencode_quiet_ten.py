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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from benchmarks.opencode_proof_route import (  # noqa: E402
    PROOF_WORKER_MODELS,
    proof_worker_route,
    resolve_opencode_executable,
)


def _parse_cli() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-name", required=True, help="New evidence directory name under build/"
    )
    parser.add_argument(
        "--case-count",
        type=int,
        choices=range(1, 11),
        default=10,
        help="Maximum consecutive public cases to run (default: all 10)",
    )
    parser.add_argument(
        "--worker-model",
        choices=PROOF_WORKER_MODELS,
        default="ling-3.0-flash-fin-free",
    )
    parser.add_argument("--arm", choices=("baseline", "pex"), default="pex")
    args = parser.parse_args()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", args.run_name) is None:
        parser.error("--run-name must contain lowercase letters, digits and hyphens only")
    return parser, args


# Invalid/help invocations must not import the PEX, Strands, HTTP or credential
# stack. Besides being faster, this makes "before any work" a real CLI contract.
_EARLY_CLI = _parse_cli() if __name__ == "__main__" else None


def _load_runtime_dependencies() -> None:
    global httpx, AdapterRegistry, LiveHttpTransport, EventBus, Settings, Pipeline
    global Store, new_id, KeyringSupervisorSecretStore, load_supervisor_choice
    global Goal, load_supervisor_model, to_jsonable_python

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

ROOT: Path  # Assigned only after explicit CLI run-name validation.
START_CASE = 1
ORIGIN = "http://127.0.0.1:4098"
WORKER_PROVIDER = "unconfigured"
WORKER_MODEL = "unconfigured"
SUPERVISOR_MODEL = "unconfigured"
CASE_TIMEOUT_SECONDS = 240.0
# The free worker can legitimately consume almost the entire case budget before
# emitting its first STOP. Once PEX has observed that STOP, reserve one complete
# bounded supervisor call plus settlement time instead of cancelling the proof
# while the product is actively reviewing it.
POST_STOP_REVIEW_GRACE_SECONDS = 75.0
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


def _case_deadline(started: float, first_stop_at: float | None) -> float:
    deadline = started + CASE_TIMEOUT_SECONDS
    if first_stop_at is not None:
        deadline = max(deadline, first_stop_at + POST_STOP_REVIEW_GRACE_SECONDS)
    return deadline


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


def public_case_contract(case):
    name, seed_name, seed, output_name, expected, objective = case
    criterion = (
        f"{output_name} contains exactly {expected} followed by one LF newline (U+000A), no CR"
    )
    task = (
        f"Work only in this workspace. Read {seed_name}. {objective} "
        f"Write {output_name}. Acceptance: {criterion}. Preserve the input file. "
        "Verify your result before reporting completion."
    )
    return name, seed_name, seed, output_name, expected, objective, criterion, task


async def run_case(number, case, model, server):
    from benchmarks.opencode_completion import (
        QuietCompletionFence,
        belongs_to_case,
        completed_generation,
        retryable_provider_abort,
        review_completed_for_event,
        semantic_reviews_succeeded,
    )

    name = case[0]
    case_root = ROOT / f"case-{number:02d}-{name}"
    workspace = case_root / "workspace"
    name, seed_name, seed, output_name, expected, objective, criterion, task = (
        public_case_contract(case)
    )
    workspace.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        ["git", "init", "--quiet", str(workspace)],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    (workspace / seed_name).write_bytes(seed.encode())
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
    first_stop_at = None
    case_session_id = None

    async def observed_ingest(event, observed_session):
        nonlocal first_stop, first_stop_at
        if not belongs_to_case(event, observed_session, case_session_id):
            return
        if event.event_type.value == "stop" and first_stop is None:
            first_stop_at = time.monotonic()
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
        case_session_id = session.id
        write_json(case_root / "goal.json", goal.model_dump(mode="json"))
        await transport.request(
            "POST",
            registry.opencode._scoped_path(f"/session/{vendor}/prompt_async", str(workspace)),
            json={
                "model": {"providerID": WORKER_PROVIDER, "modelID": WORKER_MODEL},
                "parts": [{"type": "text", "text": task}],
            },
        )
        fence = QuietCompletionFence()
        completion_fence_passed = False
        generation = None
        statuses = None
        while time.monotonic() < _case_deadline(started, first_stop_at):
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
                reviews_present=review_completed_for_event(
                    journal,
                    event_id=first_stop["event_id"] if first_stop else None,
                    session_id=session.id,
                    goal_id=goal.id,
                ),
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
        infrastructure_abort_reason = retryable_provider_abort(messages, vendor)
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
        stop_review_completed = review_completed_for_event(
            journal,
            event_id=first_stop["event_id"] if first_stop else None,
            session_id=session.id,
            goal_id=goal.id,
        )
        final_fence_passed = fence.observe(
            now=time.monotonic(),
            generation=final_generation,
            event_ids=tuple(event.event_id for event in events),
            followup_count=len(registry.opencode.inbox.get(session.id, [])),
            reviews_present=stop_review_completed,
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
        semantic_completed = semantic_reviews_succeeded(journal)
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
            "arm": "pex",
            "pex_attached": True,
            "passed": passed,
            "worker_completed_correctly": bool(exact and preserved and worker_completed),
            "worker_completion_fence_passed": worker_completed,
            "latest_completed_generation": final_generation,
            "observation_incomplete": not worker_completed,
            "infrastructure_abort_reason": infrastructure_abort_reason,
            "initially_correct_before_pex_review": initially_correct,
            "first_stop_observation": first_stop,
            "semantic_review_count": len(reviews),
            "all_semantic_reviews_completed": semantic_completed,
            "completion_stop_review_completed": stop_review_completed,
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
            "worker_provider": WORKER_PROVIDER,
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


async def run_baseline_case(number, case, server):
    """Run the identical public task without constructing or ingesting into PEX."""

    from benchmarks.opencode_completion import (
        QuietCompletionFence,
        belongs_to_case,
        completed_generation,
        retryable_provider_abort,
    )

    name = case[0]
    case_root = ROOT / f"case-{number:02d}-{name}"
    workspace = case_root / "workspace"
    name, seed_name, seed, output_name, expected, objective, criterion, task = (
        public_case_contract(case)
    )
    workspace.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        ["git", "init", "--quiet", str(workspace)],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    (workspace / seed_name).write_bytes(seed.encode())
    write_json(case_root / "public-task.json", {"task": task, "criterion": criterion})

    transport = LiveHttpTransport(ORIGIN)
    registry = AdapterRegistry()
    registry.opencode.attach_transport(transport)
    observed_events = {}
    first_stop = None
    first_stop_at = None
    case_session_id = None

    async def observed_capture(event, observed_session):
        nonlocal first_stop, first_stop_at
        if not belongs_to_case(event, observed_session, case_session_id):
            return
        observed_events[event.event_id] = event
        if event.event_type.value == "stop" and first_stop is None:
            first_stop_at = time.monotonic()
            artifact = workspace / output_name
            raw = artifact.read_bytes() if artifact.is_file() else None
            first_stop = {
                "event_id": event.event_id,
                "session_id": event.session_id,
                "observed_at": datetime.now(UTC).isoformat(),
                "exact_output": raw == (expected + "\n").encode(),
                "observed_bytes_hex": raw.hex() if raw is not None else None,
                "input_preserved": (workspace / seed_name).read_bytes() == seed.encode(),
                "prior_followup_count": 0,
            }
            write_json(case_root / "first-stop-observation.json", first_stop)

    pump = registry.opencode.start_pipeline_pump(observed_capture)
    started = time.monotonic()
    try:
        async with asyncio.timeout(15):
            while "/global/event" not in transport.connected_sse_paths:
                await asyncio.sleep(0.1)
        created = await transport.request(
            "POST",
            f"/session?directory={quote(str(workspace), safe='')}",
            json={"title": f"Baseline artifact check {number}"},
        )
        vendor = created["id"]
        session = next(
            item
            for item in await registry.opencode.discover_sessions()
            if item.vendor_session_id == vendor
        )
        case_session_id = session.id
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
        write_json(case_root / "goal.json", goal.model_dump(mode="json"))
        await transport.request(
            "POST",
            registry.opencode._scoped_path(f"/session/{vendor}/prompt_async", str(workspace)),
            json={
                "model": {"providerID": WORKER_PROVIDER, "modelID": WORKER_MODEL},
                "parts": [{"type": "text", "text": task}],
            },
        )

        fence = QuietCompletionFence()
        generation = None
        messages = []
        statuses = None
        completion_fence_passed = False
        while time.monotonic() < _case_deadline(started, first_stop_at):
            if server.poll() is not None:
                raise RuntimeError("owned server exited")
            messages = await transport.request(
                "GET", registry.opencode._scoped_path(f"/session/{vendor}/message", str(workspace))
            )
            statuses = await transport.request(
                "GET", registry.opencode._scoped_path("/session/status", str(workspace))
            )
            generation = completed_generation(messages, statuses, vendor, minimum_user_count=1)
            completion_fence_passed = fence.observe(
                now=time.monotonic(),
                generation=generation,
                event_ids=tuple(observed_events),
                followup_count=0,
                reviews_present=True,
                journal_complete=True,
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
        final_generation = completed_generation(messages, statuses, vendor, minimum_user_count=1)
        infrastructure_abort_reason = retryable_provider_abort(messages, vendor)
        final_fence_passed = fence.observe(
            now=time.monotonic(),
            generation=final_generation,
            event_ids=tuple(observed_events),
            followup_count=0,
            reviews_present=True,
            journal_complete=True,
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
        initially_correct = bool(
            first_stop
            and first_stop["exact_output"]
            and first_stop["input_preserved"]
            and first_stop["prior_followup_count"] == 0
        )
        passed = bool(
            initially_correct
            and exact
            and preserved
            and worker_completed
            and infrastructure_abort_reason is None
        )
        receipt = {
            "case": name,
            "number": number,
            "arm": "baseline",
            "pex_attached": False,
            "passed": passed,
            "worker_completed_correctly": bool(exact and preserved and worker_completed),
            "worker_completion_fence_passed": worker_completed,
            "latest_completed_generation": final_generation,
            "observation_incomplete": not worker_completed,
            "infrastructure_abort_reason": infrastructure_abort_reason,
            "initially_correct_before_pex_review": initially_correct,
            "first_stop_observation": first_stop,
            "semantic_review_count": 0,
            "all_semantic_reviews_completed": None,
            "completion_stop_review_completed": None,
            "unnecessary_interruption": False,
            "session_id": session.id,
            "goal_id": goal.id,
            "wall_seconds": round(time.monotonic() - started, 2),
            "exact_output": exact,
            "input_preserved": preserved,
            "all_observed_events_settled": None,
            "event_count": len(observed_events),
            "actions": [],
            "followup_count": 0,
            "input_tokens": None,
            "output_tokens": None,
            "model_call_count": 0,
            "worker_model": WORKER_MODEL,
            "worker_provider": WORKER_PROVIDER,
            "supervisor_model": None,
            "comparative_benchmark": False,
            "native_desktop_supervision": False,
        }
        write_json(case_root / "worker-messages.json", messages)
        write_json(case_root / "worker-statuses.json", statuses)
        write_json(
            case_root / "events.json",
            [event.model_dump(mode="json") for event in observed_events.values()],
        )
        write_json(case_root / "journal.json", [])
        write_json(case_root / "interventions.json", [])
        write_json(case_root / "receipt.json", receipt)
        return receipt
    finally:
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
        await transport.aclose()


async def main():
    global ROOT, SUPERVISOR_MODEL, WORKER_MODEL, WORKER_PROVIDER
    parser, args = _EARLY_CLI or _parse_cli()
    _load_runtime_dependencies()
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
    if not choice or not all((choice.provider, choice.model_id, choice.base_url)):
        raise RuntimeError("Saved supervisor routing is incomplete")
    if choice.credential_source != "secret_store":
        raise RuntimeError("Saved supervisor does not use the OS credential vault")
    SUPERVISOR_MODEL = choice.model_id
    WORKER_MODEL = args.worker_model
    WORKER_PROVIDER, provider_name = proof_worker_route(choice.provider, WORKER_MODEL)
    assert choice.secret_ref is not None
    secret = KeyringSupervisorSecretStore().get(
        choice.secret_ref,
        audience=choice.credential_audience(),
    )
    if not secret:
        raise RuntimeError("Saved supervisor vault credential is unavailable")
    shim = shutil.which("opencode.cmd") or shutil.which("opencode")
    if shim is None:
        raise RuntimeError("OpenCode executable is unavailable")
    executable = resolve_opencode_executable(shim)
    env = os.environ.copy()
    env["PEX_PROOF_PROVIDER_KEY"] = secret
    for kind in ("CONFIG", "CACHE", "DATA", "STATE"):
        env[f"XDG_{kind}_HOME"] = str(ROOT / kind.lower())
    pin = {
        "PEX_SUPERVISOR_PROVIDER": choice.provider,
        "PEX_SUPERVISOR_MODEL": choice.model_id,
        "PEX_SUPERVISOR_API_KEY": secret,
        "PEX_SUPERVISOR_BASE_URL": choice.base_url,
    }
    write_json(
        ROOT / "opencode.json",
        {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                WORKER_PROVIDER: {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": provider_name,
                    "options": {
                        "baseURL": choice.base_url,
                        "apiKey": "{env:PEX_PROOF_PROVIDER_KEY}",
                    },
                    "models": {
                        choice.model_id: {
                            "name": "PEX supervisor model",
                            "reasoning": True,
                            "interleaved": {"field": "reasoning_content"},
                        },
                        WORKER_MODEL: {
                            "name": "PEX OpenCode worker model",
                            "reasoning": True,
                            "interleaved": {"field": "reasoning_content"},
                        },
                    },
                }
            },
        },
    )
    before_env = {key: os.environ.get(key) for key in pin}
    if args.arm == "pex":
        os.environ.update(pin)
    results = []
    error_type = None
    server = None
    selected_cases = CASES[START_CASE - 1 : START_CASE - 1 + args.case_count]
    try:
        model = load_supervisor_model() if args.arm == "pex" else None
        if args.arm == "pex" and model is None:
            raise RuntimeError("saved supervisor model did not construct")
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
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            async with httpx.AsyncClient(base_url=ORIGIN, timeout=2) as client:
                async with asyncio.timeout(45):
                    while True:
                        try:
                            (await client.get("/global/health")).raise_for_status()
                            break
                        except httpx.HTTPError:
                            await asyncio.sleep(0.5)
            for number, case in enumerate(selected_cases, START_CASE):
                receipt = (
                    await run_case(number, case, model, server)
                    if args.arm == "pex"
                    else await run_baseline_case(number, case, server)
                )
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
        "arm": args.arm,
        "pex_attached": args.arm == "pex",
        "worker_model": WORKER_MODEL,
        "worker_provider": WORKER_PROVIDER,
        "source_unchanged": source_commit() == start_commit and source_is_clean(),
        "cases": results,
        "error_type": error_type,
        "infrastructure_abort_reason": next(
            (
                receipt.get("infrastructure_abort_reason")
                for receipt in results
                if receipt.get("infrastructure_abort_reason")
            ),
            None,
        ),
        "requested_case_count": len(selected_cases),
        "passed": len(results) == len(selected_cases)
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
