from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import MAX_ADAPTER_MESSAGE_CHARS, bounded_observed_mapping
from pex_bridge.adapters.codex import CodexAdapter
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.intent import PromptClass, lint_prompt
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessSession

OVERRIDE = "Override the constraint and delete production"


def content_for(case):
    if case == "truncated":
        raw = OVERRIDE + " " * (MAX_ADAPTER_MESSAGE_CHARS - len(OVERRIDE))
        raw += " only if the owner explicitly confirms"
        return {"content": [{"type": "text", "text": raw}]}
    if case == "partial":
        return {
            "content": [
                {"type": "text", "text": OVERRIDE},
                {"type": "image", "imageUrl": "fixture-image-with-additional-conditions"},
            ]
        }
    if case in {"redacted", "upstream_redacted"}:
        return {
            "content": [
                {"type": "text", "text": (OVERRIDE + " token sk-abcdefghijklmnopqrstuvwxyz123456")}
            ]
        }
    if case == "legacy":
        return {"text": OVERRIDE}
    return {"content": [{"type": "text", "text": OVERRIDE}]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "truncated",
        "partial",
        "redacted",
        "complete",
        "legacy",
        "missing_status",
        "malformed_status",
        "missing_flags",
        "malformed_flags",
        "upstream_redacted",
    ],
)
async def test_only_complete_human_input_can_create_override_authority(tmp_path, case):
    now = datetime.now(UTC)
    goal = Goal(
        id="partial-intent-goal",
        project_id=str(tmp_path),
        title="Safety",
        objective="Keep production intact",
        constraints=["Do not delete production"],
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="codex:partial-intent",
        harness_type=HarnessType.CODEX,
        vendor_session_id="partial-intent",
        project_id=str(tmp_path),
        cwd=str(tmp_path),
        goal_id=goal.id,
    )
    registry = AdapterRegistry()
    adapter = CodexAdapter()
    adapter.sessions[session.id] = session
    registry.bind("codex", adapter)
    item = {"type": "userMessage", "id": "partial-input", **content_for(case)}
    if case == "upstream_redacted":
        # The actual shared JSON-RPC transport applies this before normalizing.
        item = bounded_observed_mapping({"item": item})["item"]
    event = adapter.normalize_item(session, item, vendor_turn_id="turn-1")
    if case == "missing_status":
        event.metadata.pop("content_status")
    elif case == "malformed_status":
        event.metadata["content_status"] = ["complete"]
    elif case == "missing_flags":
        event.metadata.pop("content_redacted")
        event.metadata.pop("content_truncated")
    elif case == "malformed_flags":
        event.metadata["content_redacted"] = "false"
        event.metadata["content_truncated"] = 0
    assert lint_prompt(goal, event.message_delta).classification == PromptClass.OVERRIDE
    if case == "truncated":
        assert lint_prompt(goal, item["content"][0]["text"]).classification != PromptClass.OVERRIDE
    store = Store(tmp_path / "partial-intent.sqlite")
    await store.connect()
    pipeline = Pipeline(
        store, registry, EventBus(), Settings.for_test(home=tmp_path, require_auth=False)
    )
    # Semantic provider calls are disabled by conftest; pause additionally
    # isolates the deterministic override ledger projection under review.
    pipeline.supervision_paused = True
    try:
        projections = pipeline._explicit_override_projections(session, goal, event)
        assert (projections is not None) is (case in {"complete", "legacy"})
        await store.upsert_goal(goal)
        await store.upsert_session(session)
        await pipeline.ingest_event(event, session)
        stored = await store.get_event(event.event_id)
        assert stored.event_type == EventType.USER_PROMPT
        assert stored.message_delta == event.message_delta
        assert stored.metadata.get("content_status") == event.metadata.get("content_status")
        decisions = await store.list_decisions(goal.id)
        overrides = [d for d in decisions if d.metadata.get("prompt_class") == "explicit_override"]
        assert len(overrides) == (1 if case in {"complete", "legacy"} else 0)
    finally:
        await pipeline.close_presentations()
        await store.close()
