"""Live Devin Organization API exit poll through Pipeline inspect. Does not call api.devin.ai."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.contract.live_gate import require_live_authorization
from tests.contract.test_live_codex_pump import _ensure_local_supervisor_env, _has_supervisor_key


@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_devin_exit_sends_specific_message(tmp_path: Path):
    require_live_authorization("PEX_LIVE_SUPERVISOR")
    if not _has_supervisor_key():
        pytest.skip("no supervisor API key or local OpenAI-compatible server")
    _ensure_local_supervisor_env()

    import asyncio
    from datetime import UTC, datetime

    from pex_bridge.adapters import AdapterRegistry
    from pex_bridge.adapters.http_json import MemoryHttpTransport
    from pex_bridge.bus import EventBus
    from pex_bridge.config import Settings
    from pex_bridge.pipeline import Pipeline
    from pex_bridge.store import Store, new_id
    from pex_protocol.goal import Goal
    from pex_supervisor.providers import load_supervisor_model

    model = load_supervisor_model()
    if model is None:
        pytest.skip("supervisor model did not construct")

    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    transport = MemoryHttpTransport()
    transport.sessions = [
        {"id": "live-devin-inspect", "session_id": "live-devin-inspect", "status": "running"}
    ]
    transport.session_details["live-devin-inspect"] = {
        "session_id": "live-devin-inspect",
        "status": "exit",
        "status_detail": "finished",
    }
    transport.messages = [{"message": "I am done.", "role": "assistant"}]
    registry = AdapterRegistry()
    registry.devin.attach_transport(transport, org_id="org")
    settings = Settings.for_test(
        require_auth=False, home=tmp_path, autonomy="manage", codex_attach=False
    )
    pipeline = Pipeline(store, registry, EventBus(), settings, model=model)
    now = datetime.now(UTC)
    goal = Goal(
        id=new_id("goal_"),
        project_id=str(tmp_path),
        title="report",
        objective="Create report.txt containing exactly the word shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    session = registry.devin.ingest_hook({"session_id": "live-devin-inspect", "cwd": str(tmp_path)})
    session.goal_id = goal.id
    session.cwd = str(tmp_path)
    await store.upsert_session(session)
    proof: dict = {"used_llm": False, "action_taken": None, "prompts": []}
    pump = registry.devin.start_pipeline_pump(pipeline.ingest_event)
    try:
        for _ in range(120):
            rows = await store.list_interventions(session.id)
            stops = [row for row in rows if row.trigger == "stop"]
            if stops:
                last = stops[0]
                proof["used_llm"] = bool((last.metadata or {}).get("used_llm"))
                proof["action_taken"] = last.action_taken
                proof["diagnosis"] = last.diagnosis
                proof["worker_text"] = str((last.proposed_action.payload or {}).get("text") or "")
                proof["prompts"] = list(transport.prompts)
                break
            await asyncio.sleep(0.5)
        scratch = Path(__file__).resolve().parents[2] / "benchmarks" / "results" / "_scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "devin_inspect_proof.json").write_text(
            json.dumps(proof, indent=2, default=str), encoding="utf-8"
        )
        assert proof["action_taken"], f"no STOP intervention: {proof!r}"
        assert proof["used_llm"] is True, f"STOP did not inspect with a model: {proof!r}"
        assert not str(proof.get("worker_text") or "").startswith("PEX:")
        assert proof["action_taken"] in {
            "SEND_NUDGE",
            "CONTINUE_SESSION",
            "REQUEST_VERIFICATION",
        }, f"incomplete Devin exit stayed silent: {proof!r}"
        assert proof["prompts"], f"POST .../messages was not called: {proof!r}"
        sent = json.dumps(proof["prompts"]).lower()
        assert "report" in sent or "report" in str(proof.get("worker_text") or "").lower()
        assert "pex:" not in sent
    finally:
        pump.cancel()
        try:
            await pump
        except asyncio.CancelledError:
            pass
        current = asyncio.current_task()
        for task in list(asyncio.all_tasks()):
            if task is not current:
                task.cancel()
        await store.close()
