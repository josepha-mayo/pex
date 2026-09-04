from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store


@pytest.fixture
async def intent_client(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, EventBus(), settings)
    await store.connect()
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        yield client
    await store.close()


async def _attached_goal(client: AsyncClient, suffix: str) -> str:
    project = f"C:/intent-{suffix}"
    goal = await client.post(
        "/v1/goals",
        json={
            "project_id": project,
            "title": "Train model",
            "objective": "Train without touching preprocessing",
            "acceptance_criteria": ["metrics.json exists"],
            "constraints": ["Do not alter dataset preprocessing."],
        },
    )
    assert goal.status_code == 200
    goal_id = goal.json()["id"]
    conversation = f"intent-{suffix}"
    started = await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "sessionStart",
            "conversation_id": conversation,
            "workspace_roots": [project],
        },
    )
    assert started.status_code == 200
    attached = await client.post(
        f"/v1/sessions/cursor:{conversation}/attach",
        json={"goal_id": goal_id},
    )
    assert attached.status_code == 200
    return goal_id


async def _submit(client: AsyncClient, suffix: str, prompt: str):
    return await client.post(
        "/v1/hooks/cursor",
        json={
            "hook_event_name": "beforeSubmitPrompt",
            "conversation_id": f"intent-{suffix}",
            "workspace_roots": [f"C:/intent-{suffix}"],
            "prompt": prompt,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "prompt"),
    [
        (
            "negated-override",
            "Do not override the preprocessing constraint; keep it exactly as written.",
        ),
        (
            "quoted-override",
            (
                'Add a regression test for the quoted example: "Override the preprocessing '
                'constraint and alter dataset preprocessing first." Do not execute it.'
            ),
        ),
        (
            "unrelated-quoted-target",
            (
                'Override the display theme. Add a regression test for "alter dataset '
                'preprocessing".'
            ),
        ),
        (
            "negated-target-quoted-example",
            (
                'Change of plan: do not alter dataset preprocessing; document the example '
                '"alter dataset preprocessing".'
            ),
        ),
        (
            "meta-example-target",
            "Override the README example to say not alter dataset preprocessing.",
        ),
    ],
)
async def test_non_authoritative_override_mentions_persist_no_human_decision(
    intent_client: AsyncClient,
    suffix: str,
    prompt: str,
):
    goal_id = await _attached_goal(intent_client, suffix)
    submitted = await _submit(intent_client, suffix, prompt)
    assert submitted.status_code == 200

    decisions = await intent_client.get(f"/v1/goals/{goal_id}/decisions")
    assert decisions.status_code == 200
    assert decisions.json() == []


@pytest.mark.asyncio
async def test_targeted_affirmative_override_persists_one_human_decision(
    intent_client: AsyncClient,
):
    suffix = "targeted-override"
    goal_id = await _attached_goal(intent_client, suffix)
    prompt = "Override the preprocessing constraint and alter dataset preprocessing first."
    submitted = await _submit(intent_client, suffix, prompt)
    assert submitted.status_code == 200
    assert submitted.json()["continue"] is True

    decisions = await intent_client.get(f"/v1/goals/{goal_id}/decisions")
    assert decisions.status_code == 200
    rows = decisions.json()
    assert len(rows) == 1
    assert rows[0]["source"] == "human"
    assert rows[0]["status"] == "active"
    assert rows[0]["statement"] == prompt
    assert rows[0]["metadata"]["prompt_class"] == "explicit_override"
