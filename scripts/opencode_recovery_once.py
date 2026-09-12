"""Run one bounded, controlled OpenCode same-session recovery proof.

This is a behavioral diagnostic, not a comparative benchmark. The initial
public prompt deliberately stops after phase one. PEX must independently find
the attached goal gap, send one verified correction, observe the outcome, and
then stay quiet on the supported completion. Prior runs are never deleted.
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


def _parse_cli() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", args.run_name) is None:
        parser.error("--run-name must contain lowercase letters, digits and hyphens only")
    return parser, args


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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
ORIGIN = "http://127.0.0.1:4098"
WORKER_MODEL = "ling-3.0-flash-fin-free"
SUPERVISOR_MODEL = "muse-spark-1.3-contributor-free"
EXPECTED_STAGE = b"stage-one-ok\n"
EXPECTED_FINAL = b"pex-supervised-ok\n"


def write_json(path: Path, value: object) -> None:
    serialized = json.dumps(to_jsonable_python(value), indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(serialized)


def source_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def source_is_clean() -> bool:
    return not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=REPO, text=True
    ).strip()


async def run_recovery(root: Path, model: object, server: subprocess.Popen[bytes]) -> dict:
    from benchmarks.opencode_completion import (
        QuietCompletionFence,
        belongs_to_case,
        completed_generation,
        recovery_interventions_succeeded,
        review_completed_for_event,
        semantic_reviews_succeeded,
    )

    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        ["git", "init", "--quiet", str(workspace)],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    task = (
        "Work only in this workspace. Perform only phase one: create stage-one.txt "
        "containing exactly stage-one-ok followed by one LF newline. Do not create "
        "final.txt in this turn. Verify stage-one.txt, state that phase one is "
        "finished, and stop."
    )
    write_json(root / "public-task.json", {"task": task})
    store = Store(root / "pex.sqlite")
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
            home=root,
            autonomy="manage",
            codex_attach=False,
            supervisor_max_dispatches_per_session=3,
        ),
        model=model,
    )
    first_stop: dict | None = None
    case_session_id: str | None = None

    async def observed_ingest(event, observed_session) -> None:
        nonlocal first_stop
        if not belongs_to_case(event, observed_session, case_session_id):
            return
        if event.event_type.value == "stop" and first_stop is None:
            stage = workspace / "stage-one.txt"
            final = workspace / "final.txt"
            first_stop = {
                "event_id": event.event_id,
                "session_id": event.session_id,
                "observed_at": datetime.now(UTC).isoformat(),
                "stage_exact": stage.is_file() and stage.read_bytes() == EXPECTED_STAGE,
                "final_absent": not final.exists(),
                "prior_followup_count": len(registry.opencode.inbox.get(event.session_id, [])),
            }
            write_json(root / "first-stop-observation.json", first_stop)
        await pipeline.ingest_event(event, observed_session)

    pump = registry.opencode.start_pipeline_pump(observed_ingest)
    started = time.monotonic()
    receipt: dict = {}
    try:
        async with asyncio.timeout(15):
            while "/global/event" not in transport.connected_sse_paths:
                await asyncio.sleep(0.1)
        created = await transport.request(
            "POST",
            f"/session?directory={quote(str(workspace), safe='')}",
            json={"title": "PEX bounded recovery proof"},
        )
        vendor = created["id"]
        session = next(
            item
            for item in await registry.opencode.discover_sessions()
            if item.vendor_session_id == vendor
        )
        now = datetime.now(UTC)
        goal = Goal(
            id=new_id("goal_"),
            project_id=str(workspace),
            title="Complete both proof stages",
            objective=(
                "Complete the two-stage workspace proof with exact stage-one.txt and "
                "final.txt bytes."
            ),
            acceptance_criteria=[
                "stage-one.txt contains exactly stage-one-ok followed by one newline",
                "final.txt contains exactly pex-supervised-ok followed by one newline",
            ],
            evidence_requirements=["stage-one.txt", "final.txt"],
            created_at=now,
            updated_at=now,
        )
        await store.upsert_goal(goal)
        session.goal_id = goal.id
        await store.upsert_session(session)
        case_session_id = session.id
        write_json(root / "goal.json", goal.model_dump(mode="json"))
        await transport.request(
            "POST",
            registry.opencode._scoped_path(f"/session/{vendor}/prompt_async", str(workspace)),
            json={
                "model": {"providerID": "opencode", "modelID": WORKER_MODEL},
                "parts": [{"type": "text", "text": task}],
            },
        )

        fence = QuietCompletionFence()
        passed = False
        messages: object = []
        statuses: object = {}
        events = []
        journal = []
        serialized_rows: list[dict] = []
        followups: list[str] = []
        final_stop_id: str | None = None
        generation = None
        complete = False
        semantic_completed = False
        recovery_completed = False
        while time.monotonic() - started < 360:
            if server.poll() is not None:
                raise RuntimeError("owned server exited")
            events = await store.recent_events(session.id, limit=1000)
            journal = [await store.get_event_processing(event.event_id) for event in events]
            rows = await store.list_interventions(session.id)
            serialized_rows = [row.model_dump(mode="json") for row in rows]
            followups = list(registry.opencode.inbox.get(session.id, []))
            complete = bool(journal) and all(
                row and row["state"] in {"complete", "record_only_complete"} for row in journal
            )
            semantic_completed = semantic_reviews_succeeded(journal)
            recovery_completed = recovery_interventions_succeeded(serialized_rows, followups)
            messages = await transport.request(
                "GET", registry.opencode._scoped_path(f"/session/{vendor}/message", str(workspace))
            )
            statuses = await transport.request(
                "GET", registry.opencode._scoped_path("/session/status", str(workspace))
            )
            generation = completed_generation(messages, statuses, vendor, minimum_user_count=2)
            stop_ids = [event.event_id for event in events if event.event_type.value == "stop"]
            final_stop_id = (
                stop_ids[-1]
                if first_stop and stop_ids and stop_ids[-1] != first_stop["event_id"]
                else None
            )
            final_review = review_completed_for_event(
                journal,
                event_id=final_stop_id,
                session_id=session.id,
                goal_id=goal.id,
            )
            final_exact = (workspace / "final.txt").is_file() and (
                workspace / "final.txt"
            ).read_bytes() == EXPECTED_FINAL
            stage_exact = (workspace / "stage-one.txt").is_file() and (
                workspace / "stage-one.txt"
            ).read_bytes() == EXPECTED_STAGE
            quiet = fence.observe(
                now=time.monotonic(),
                generation=generation,
                event_ids=tuple(event.event_id for event in events),
                followup_count=len(followups),
                reviews_present=final_review,
                journal_complete=complete,
            )
            passed = bool(
                first_stop
                and first_stop["stage_exact"]
                and first_stop["final_absent"]
                and first_stop["prior_followup_count"] == 0
                and stage_exact
                and final_exact
                and generation
                and complete
                and semantic_completed
                and recovery_completed
                and quiet
            )
            if passed:
                break
            await asyncio.sleep(1)

        reviews = [
            row["plan"]["supervisor_result"]
            for row in journal
            if row
            and isinstance(row.get("plan"), dict)
            and (row["plan"].get("supervisor_result") or {}).get("used_llm") is True
        ]
        receipt = {
            "schema": "pex.live-opencode-recovery.v2",
            "passed": passed,
            "controlled_incomplete_prompt": True,
            "first_stop_observation": first_stop,
            "stage_one_exact": (workspace / "stage-one.txt").is_file()
            and (workspace / "stage-one.txt").read_bytes() == EXPECTED_STAGE,
            "final_exact": (workspace / "final.txt").is_file()
            and (workspace / "final.txt").read_bytes() == EXPECTED_FINAL,
            "latest_completed_generation": generation,
            "final_stop_event_id": final_stop_id,
            "all_observed_events_settled": complete,
            "all_semantic_reviews_completed": semantic_completed,
            "causal_recovery_proof_passed": recovery_completed,
            "session_id": session.id,
            "goal_id": goal.id,
            "event_count": len(events),
            "actions": [row.get("action_taken") for row in serialized_rows],
            "followup_count": len(followups),
            "input_tokens": sum(row.get("input_tokens") or 0 for row in reviews),
            "output_tokens": sum(row.get("output_tokens") or 0 for row in reviews),
            "model_call_count": sum(row.get("model_call_count") or 0 for row in reviews),
            "wall_seconds": round(time.monotonic() - started, 2),
            "worker_model": WORKER_MODEL,
            "supervisor_model": SUPERVISOR_MODEL,
            "comparative_benchmark": False,
            "native_desktop_supervision": False,
        }
        write_json(root / "worker-messages.json", messages)
        write_json(root / "worker-statuses.json", statuses)
        write_json(root / "events.json", [event.model_dump(mode="json") for event in events])
        write_json(root / "journal.json", journal)
        write_json(root / "interventions.json", serialized_rows)
        write_json(root / "followups.json", followups)
        write_json(root / "receipt.json", receipt)
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


async def main() -> int:
    parser, args = _EARLY_CLI or _parse_cli()
    _load_runtime_dependencies()
    if not source_is_clean():
        parser.error("Commit or otherwise resolve source changes before a live evidence run")
    root = REPO / "build" / args.run_name
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 4098))
    root.mkdir(parents=True, exist_ok=False)
    (root / "runner.py").write_bytes(Path(__file__).read_bytes())
    helper_bytes = (REPO / "benchmarks/opencode_completion.py").read_bytes()
    (root / "completion-fence.py").write_bytes(helper_bytes)
    start_commit = source_commit()
    choice = load_supervisor_choice(Path.home() / ".pex/supervisor.json")
    if not choice or (
        choice.provider,
        choice.model_id,
        choice.base_url,
        choice.credential_source,
    ) != ("zen", SUPERVISOR_MODEL, "https://opencode.ai/zen/v1", "secret_store"):
        raise RuntimeError("saved supervisor is not the exact approved Zen free model")
    if choice.secret_ref is None:
        raise RuntimeError("saved Zen vault credential reference is unavailable")
    secret = KeyringSupervisorSecretStore().get(
        choice.secret_ref, audience=choice.credential_audience()
    )
    if not secret:
        raise RuntimeError("saved Zen vault credential is unavailable")
    shim = shutil.which("opencode.cmd") or shutil.which("opencode")
    if shim is None:
        raise RuntimeError("OpenCode executable is unavailable")
    executable = Path(shim).resolve().parent / "node_modules/opencode-ai/bin/opencode.exe"
    if not executable.is_file():
        raise RuntimeError("direct OpenCode executable is unavailable; refusing shim ownership")
    environment = os.environ.copy()
    environment["OPENCODE_API_KEY"] = secret
    for kind in ("CONFIG", "CACHE", "DATA", "STATE"):
        environment[f"XDG_{kind}_HOME"] = str(root / kind.lower())
    pins = {
        "PEX_SUPERVISOR_PROVIDER": "zen",
        "PEX_SUPERVISOR_MODEL": SUPERVISOR_MODEL,
        "PEX_SUPERVISOR_API_KEY": secret,
        "PEX_SUPERVISOR_BASE_URL": "https://opencode.ai/zen/v1",
    }
    before_env = {key: os.environ.get(key) for key in pins}
    os.environ.update(pins)
    server: subprocess.Popen[bytes] | None = None
    receipt: dict = {}
    error_type: str | None = None
    try:
        model = load_supervisor_model()
        if model is None:
            raise RuntimeError("saved supervisor model did not construct")
        with (root / "server.log").open("x", encoding="utf-8") as log:
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
                cwd=root,
                env=environment,
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
            receipt = await run_recovery(root, model, server)
    except Exception as exc:
        error_type = type(exc).__name__
        write_json(
            root / "error-frames.json",
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
        "receipt": receipt,
        "error_type": error_type,
        "passed": receipt.get("passed") is True
        and source_commit() == start_commit
        and source_is_clean(),
        "owned_server_exited": server is None or server.poll() is not None,
        "profiles_retained_for_audit": True,
        "comparative_benchmark": False,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "completion_fence_sha256": hashlib.sha256(helper_bytes).hexdigest(),
    }
    write_json(root / "summary.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
