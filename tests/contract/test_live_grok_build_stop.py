"""Synthetic Grok Build hook contract. Does not spawn `grok` or prove delivery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from tests.contract.live_gate import require_live_authorization
from tests.contract.test_live_codex_pump import _ensure_local_supervisor_env, _has_supervisor_key


@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_grok_build_hook_without_acp_does_not_claim_delivery(tmp_path: Path):
    require_live_authorization("PEX_LIVE_SUPERVISOR")
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

    settings = Settings.for_test(
        require_auth=False, home=tmp_path, autonomy="manage", codex_attach=False
    )
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
    proof: dict = {"used_llm": False, "action_taken": None, "followup": ""}
    try:
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            primed = await client.post(
                "/v1/hooks/grok_build",
                json={
                    "hook_event_name": "SessionStart",
                    "session_id": "live-grok-inspect",
                    "cwd": str(tmp_path),
                },
            )
            assert primed.status_code == 404
            proof["hook_status"] = primed.status_code
            proof["hook_body"] = primed.json()
            assert await store.list_sessions() == []
            assert await store.list_interventions() == []
            scratch = Path(__file__).resolve().parents[2] / "benchmarks" / "results" / "_scratch"
            scratch.mkdir(parents=True, exist_ok=True)
            (scratch / "grok_build_inspect_proof.json").write_text(
                json.dumps(proof, indent=2), encoding="utf-8"
            )
            # Grok Build has no generic hook contract. Only an attached
            # `grok agent stdio` ACP channel may create/control sessions.
            assert proof["hook_status"] == 404
    finally:
        import asyncio

        current = asyncio.current_task()
        for task in list(asyncio.all_tasks()):
            if task is not current:
                task.cancel()
        await store.close()
