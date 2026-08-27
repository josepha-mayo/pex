import pytest
from httpx import ASGITransport, AsyncClient

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import EventType


@pytest.fixture
async def client(tmp_path):
    settings = Settings(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await store.close()


@pytest.mark.asyncio
async def test_context_handoff_injects_bundle(client: AsyncClient):
    source = (await client.post("/v1/synthetic/sessions")).json()
    # second session
    source_adapter = state.adapters.synthetic
    target = source_adapter.seed_session(vendor_id="synth-2")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Eval",
                "objective": "Share the dataset path discovered by Codex with Cursor",
                "acceptance_criteria": ["both agents use prepared_dataset.parquet"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": "Dataset is at artifacts/prepared_dataset.parquet. Do not regenerate it.",
        },
    )
    handoff = await client.post(
        f"/v1/sessions/{source['id']}/handoff",
        json={"target_session_id": target.id},
    )
    assert handoff.status_code == 200
    body = handoff.json()
    assert body["ok"] is True
    assert "prepared_dataset" in str(body["bundle"]).lower() or body["bundle"]["goal_summary"]
    assert source_adapter.inbox[target.id]


@pytest.mark.asyncio
async def test_auto_handoff_injects_without_explicit_post(client: AsyncClient):
    source = (await client.post("/v1/synthetic/sessions")).json()
    source_adapter = state.adapters.synthetic
    target = source_adapter.seed_session(vendor_id="synth-auto")
    await state.store.upsert_session(target)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Share path",
                "objective": "Share the dataset path discovered by Codex with Cursor",
                "acceptance_criteria": ["both agents use prepared_dataset.parquet"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{source['id']}/attach", json={"goal_id": goal["id"]})
    event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": source["id"],
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": "Dataset is at artifacts/prepared_dataset.parquet. Do not regenerate it.",
        },
    )
    assert event.status_code == 200
    inbox = source_adapter.inbox[target.id]
    assert inbox
    assert "prepared_dataset" in inbox[-1].lower() or "goal" in inbox[-1].lower()
    attached = await client.get(f"/v1/sessions/{target.id}")
    assert attached.json()["goal_id"] == goal["id"]


@pytest.mark.asyncio
async def test_goal_persists_non_goals(client: AsyncClient):
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Keep loader",
                "objective": "Finish eval without rewriting the loader",
                "acceptance_criteria": ["results.json exists"],
                "constraints": ["Do not alter dataset preprocessing."],
                "non_goals": ["Do not rewrite the dataset loader."],
            },
        )
    ).json()
    assert goal["non_goals"] == ["Do not rewrite the dataset loader."]
    fetched = await client.get(f"/v1/goals/{goal['id']}")
    assert fetched.json()["non_goals"] == ["Do not rewrite the dataset loader."]


@pytest.mark.asyncio
async def test_stop_stores_extracted_claims(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Parser",
                "objective": "Implement the parser with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session['id']}/attach", json={"goal_id": goal["id"]})
    stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session["id"],
            "event_type": EventType.STOP.value,
            "message": "Implemented the parser and tests pass.",
        },
    )
    body = stop.json()["intervention"]
    claims = (body.get("metadata") or {}).get("claims") or []
    kinds = {item["kind"] for item in claims}
    assert "tests_pass" in kinds
    assert "implemented" in kinds
    items = await client.get("/v1/context", params={"project_id": "demo"})
    kinds_stored = {item["kind"] for item in items.json()}
    assert "claim" in kinds_stored


@pytest.mark.asyncio
async def test_false_test_claim_nudges_with_failing_pytest(client: AsyncClient, tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / "src").mkdir()
    (worker / "src" / "parser.py").write_text("def parse():\n    return 1\n", encoding="utf-8")
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="false-claim", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Parser",
                "objective": "Implement the parser with passing tests",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "file_paths": ["src/parser.py"],
            "process_state": {
                "pytest": {
                    "ok": False,
                    "exit_code": 1,
                    "failed": "tests/test_parser.py::test_nested_array",
                }
            },
        },
    )
    stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    body = stop.json()
    assert body["intervention"]["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "test_nested_array" in text
    assert not text.startswith("PEX:")
    assert (body["intervention"].get("metadata") or {}).get("verification", {}).get("status") == "contradicted"


@pytest.mark.asyncio
async def test_short_eval_artifact_contradicts_done(client: AsyncClient, tmp_path):
    worker = tmp_path / "eval-worker"
    worker.mkdir()
    rows = "\n".join(f'{{"id": {i}}}' for i in range(27))
    (worker / "results.jsonl").write_text(rows + "\n", encoding="utf-8")
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="short-eval", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "Eval",
                "objective": "Produce a complete evaluation",
                "acceptance_criteria": ["results.jsonl has 30 rows"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session.id}/attach", json={"goal_id": goal["id"]})
    stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "The evaluation is complete.",
        },
    )
    body = stop.json()
    assert body["intervention"]["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "27" in text and "30" in text
    assert not text.startswith("PEX:")


@pytest.mark.asyncio
async def test_pytest_permission_auto_allowed(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "project_id": "demo",
                "title": "t",
                "objective": "o",
                "acceptance_criteria": ["tests pass"],
            },
        )
    ).json()
    await client.post(f"/v1/sessions/{session['id']}/attach", json={"goal_id": goal["id"]})
    event = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session["id"],
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
        },
    )
    # default phase is DURING; force via hook-style permission using cursor adapter
    assert event.status_code == 200
    hook = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "conv-perm",
            "command": "pytest -q",
            "workspace_roots": ["C:/proj"],
        },
    )
    assert hook.json().get("permission") == "allow"


@pytest.mark.asyncio
async def test_destructive_shell_permission_asks_human(client: AsyncClient):
    hook = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeShellExecution",
            "conversation_id": "conv-rm",
            "command": "rm -rf /tmp/pex-scratch",
            "workspace_roots": ["C:/proj"],
        },
    )
    assert hook.json().get("permission") == "ask"
