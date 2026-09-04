from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_protocol.context import ContextBundle
from pex_protocol.enums import HarnessType


def _bundle(target_id: str) -> ContextBundle:
    return ContextBundle(
        goal_id="goal-1",
        target_session_id=target_id,
        source_session_ids=[target_id],
        goal_summary="Pick the cheaper index.",
        acceptance_criteria=[],
        next_objective="Isolated speculative probe. Try only this approach: sqlite.",
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_opencode_fork_uses_official_session_fork_and_injects_probe():
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    parent = (await adapter.discover_sessions())[0]
    assert parent.harness_type == HarnessType.OPENCODE
    caps = await adapter.probe()
    assert caps.fork is True

    child = await adapter.fork_or_fresh_handoff(parent, _bundle(parent.id))
    assert child is not None
    assert child.id != parent.id
    assert child.id.startswith("opencode:")
    assert child.metadata["probe"] is True
    assert child.metadata["forked_from"] == parent.id
    assert child.project_id == parent.project_id
    assert any(path.split("?", 1)[0].endswith("/fork") for _, path, _ in transport.calls)
    assert child.id in adapter.inbox
    assert "sqlite" in adapter.inbox[child.id][0]


@pytest.mark.asyncio
async def test_opencode_fork_is_unavailable_without_a_live_server():
    adapter = OpenCodeAdapter()
    assert (await adapter.probe()).fork is False
    fake = (await OpenCodeAdapter(MemoryHttpTransport()).discover_sessions())[0]
    assert await adapter.fork_or_fresh_handoff(fake, _bundle(fake.id)) is None
