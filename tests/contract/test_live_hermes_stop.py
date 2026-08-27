"""Live Hermes on_session_end through Pipeline inspect. Does not spawn Hermes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from tests.contract.test_live_codex_pump import _ensure_local_supervisor_env, _has_supervisor_key


@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_hermes_session_end_injects_specific_context(tmp_path: Path):
    if not _has_supervisor_key():
        pytest.skip("no supervisor API key or local OpenAI-compatible server")
    _ensure_local_supervisor_env()

    from pex_bridge.adapters import AdapterRegistry
    from pex_bridge.app import create_app, state
    from pex_bridge.bus import EventBus
    from pex_bridge.config import Settings
    from pex_bridge.pipeline import Pipeline
    from pex_bridge.store import Store
    from pex_supervisor.providers import load_supervisor_model

    model = load_supervisor_model()
    if model is None:
        pytest.skip("supervisor model did not construct")

    settings = Settings(require_auth=False, home=tmp_path, autonomy="manage", codex_attach=False)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings, model=model)
    await store.connect()
    app = create_app()
    transport = ASGITransport(app=app)
    proof: dict = {"used_llm": False, "action_taken": None, "context": ""}
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            goal = await client.post(
                "/v1/goals",
                json={
                    "project_id": str(tmp_path),
                    "title": "report",
                    "objective": "Create report.txt containing exactly the word shipped.",
                    "acceptance_criteria": ["report.txt contains shipped"],
                    "evidence_requirements": ["report.txt"],
                },
            )
            assert goal.status_code == 200
            goal_id = goal.json()["id"]
            start = await client.post(
                "/v1/hooks/hermes",
                json={
                    "hook_event_name": "on_session_start",
                    "session_id": "live-hermes-inspect",
                    "cwd": str(tmp_path),
                },
            )
            assert start.status_code == 200
            attached = await client.post(
                "/v1/sessions/hermes:live-hermes-inspect/attach",
                json={"goal_id": goal_id},
            )
            assert attached.status_code == 200
            stop = await client.post(
                "/v1/hooks/hermes",
                json={
                    "hook_event_name": "on_session_end",
                    "session_id": "live-hermes-inspect",
                    "cwd": str(tmp_path),
                    "text": "I am done.",
                    "completed": True,
                },
            )
            assert stop.status_code == 200
            nxt = await client.post(
                "/v1/hooks/hermes",
                json={
                    "hook_event_name": "pre_llm_call",
                    "session_id": "live-hermes-inspect",
                    "cwd": str(tmp_path),
                    "user_message": "continue",
                },
            )
            assert nxt.status_code == 200
            context = str(nxt.json().get("context") or "")
            proof["context"] = context
            proof["stop_body"] = stop.json()
            rows = await store.list_interventions("hermes:live-hermes-inspect")
            stops = [row for row in rows if row.trigger == "stop"]
            if stops:
                last = stops[0]
                proof["used_llm"] = bool((last.metadata or {}).get("used_llm"))
                proof["action_taken"] = last.action_taken
                proof["diagnosis"] = last.diagnosis
                proof["worker_text"] = str((last.proposed_action.payload or {}).get("text") or "")
            scratch = Path(__file__).resolve().parents[2] / "benchmarks" / "results" / "_scratch"
            scratch.mkdir(parents=True, exist_ok=True)
            (scratch / "hermes_inspect_proof.json").write_text(
                json.dumps(proof, indent=2), encoding="utf-8"
            )
            assert stops, f"no STOP intervention: {proof!r}"
            assert proof["used_llm"] is True, f"STOP did not inspect with a model: {proof!r}"
            assert not context.startswith("PEX:")
            assert not str(proof.get("worker_text") or "").startswith("PEX:")
            assert proof["action_taken"] in {
                "SEND_NUDGE",
                "CONTINUE_SESSION",
                "REQUEST_VERIFICATION",
            }, f"incomplete Hermes session_end stayed silent: {proof!r}"
            assert context
            assert "report" in context.lower()
    finally:
        import asyncio

        current = asyncio.current_task()
        for task in list(asyncio.all_tasks()):
            if task is not current:
                task.cancel()
        await store.close()
