from unittest.mock import AsyncMock

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.executor import ActionExecutor
from pex_bridge.pipeline import _same_session_project
from pex_bridge.store import Store, _same_live_project_binding
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import HarnessType
from pex_protocol.session import HarnessSession

DISTINCT_PROJECTS = [
    ("/work/PEX", "/work/pex"),
    ("project:PEX", "project:pex"),
    ("C:/work/straße", "C:/work/strasse"),
    ("C:/", "C:"),
]


def _session(project: str) -> HarnessSession:
    return HarnessSession(
        id="synthetic:bound",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="bound",
        project_id=project,
        goal_id="goal",
    )


@pytest.mark.parametrize("left,right", DISTINCT_PROJECTS)
def test_pipeline_does_not_merge_distinct_session_projects(left: str, right: str) -> None:
    assert not _same_session_project(_session(left), _session(right))


@pytest.mark.parametrize("left,right", DISTINCT_PROJECTS)
@pytest.mark.asyncio
async def test_start_rejects_foreign_project_before_any_adapter_probe(
    left: str,
    right: str,
    monkeypatch,
) -> None:
    executor = ActionExecutor(AdapterRegistry(), None)
    probe = AsyncMock(side_effect=AssertionError("foreign project reached adapter probe"))
    monkeypatch.setattr(executor, "_refresh_lifecycle_capability", probe)
    action = ProposedAction(
        type=InterventionType.START_AGENT,
        session_id="synthetic:bound",
        goal_id="goal",
        payload={"project": right, "prompt": "Perform the authorized task."},
        rationale="Bounded test",
        evidence=["event:test"],
        confidence=1.0,
    )
    result = await executor._start_agent(action, _session(left), object())
    assert result == "agent_start_project_mismatch"
    probe.assert_not_awaited()


def test_pipeline_preserves_windows_absolute_path_spelling_compatibility() -> None:
    assert _same_session_project(_session("C:/Work/PEX"), _session("c:\\work\\pex\\"))


@pytest.mark.parametrize("left,right", DISTINCT_PROJECTS)
@pytest.mark.asyncio
async def test_store_without_registered_aliases_rejects_distinct_projects(
    left: str,
    right: str,
    tmp_path,
) -> None:
    store = Store(tmp_path / "binding.sqlite")
    await store.connect()
    try:
        assert not await _same_live_project_binding(store.db, left, right)
        assert await _same_live_project_binding(store.db, left, left)
    finally:
        await store.close()
