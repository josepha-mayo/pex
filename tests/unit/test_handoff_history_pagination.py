from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pex_bridge.pipeline import Pipeline
from pex_protocol.actions import InterventionType


@pytest.mark.asyncio
async def test_delivered_handoff_history_reads_past_first_page():
    pipeline = object.__new__(Pipeline)
    pipeline.store = SimpleNamespace(list_interventions_for_authority=AsyncMock())
    target = SimpleNamespace(id="target", project_id="project", cwd="project", harness_type="codex")
    goal = SimpleNamespace(id="goal")

    def handoff(item_id: str):
        return SimpleNamespace(
            proposed_action=SimpleNamespace(
                type=InterventionType.FRESH_HANDOFF,
                payload={"bundle": {"items": [{"id": item_id}]}},
            ),
            metadata={"handoff_delivery_status": "delivered"},
            result="handoff_injected",
        )

    first_page = [handoff(f"item-{index}") for index in range(1000)]
    last_page = [handoff("oldest-item")]
    pipeline.store.list_interventions_for_authority.side_effect = [first_page, last_page]

    delivered = await pipeline._delivered_context_item_ids(target, goal)

    assert len(delivered) == 1001
    assert "oldest-item" in delivered
    offsets = [
        call.kwargs["offset"]
        for call in pipeline.store.list_interventions_for_authority.call_args_list
    ]
    assert offsets == [0, 1000]
