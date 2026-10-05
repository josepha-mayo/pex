"""Sealed-baseline diff: the tamper evidence a flag alone cannot show."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessSession


@pytest.fixture
async def client(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path / "home")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    await store.connect()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as c:
            yield c, store, tmp_path
    finally:
        await store.close()


async def _bind(store: Store, tmp_path: Path) -> tuple[Goal, HarnessSession]:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-diff",
        project_id=str(workspace),
        title="Fix the CSV parser",
        objective="All tests green without touching tests.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="opencode:diff-1",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="diff-1",
        status=SessionStatus.STOPPED,
        goal_id=goal.id,
        project_id=str(workspace),
        cwd=str(workspace),
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    return goal, session


async def _seal(store: Store, goal: Goal, session: HarnessSession, text: bytes):
    digest = hashlib.sha256(text).hexdigest()
    await store.recall_or_seal_acceptance_baseline(
        session.id,
        goal.id,
        workspace=session.cwd,
        captured_at="2026-10-05T00:00:00+00:00",
        files={"test_csv_utils.py": digest},
        files_complete=True,
        file_contents={"test_csv_utils.py": text.decode("utf-8")},
    )


async def test_diff_shows_sealed_text_against_current_bytes(client) -> None:
    http, store, tmp_path = client
    goal, session = await _bind(store, tmp_path)
    sealed = b"assert result == 'a,b'\n"
    await _seal(store, goal, session, sealed)
    (tmp_path / "ws" / "test_csv_utils.py").write_bytes(b"assert result == result\n")

    body = (
        await http.get(
            f"/v1/goals/{goal.id}/acceptance-diff",
            params={"path": "test_csv_utils.py"},
        )
    ).json()
    assert body["baseline"]["text"] == "assert result == 'a,b'\n"
    assert body["baseline"]["sealed_at"] == "2026-10-05T00:00:00+00:00"
    assert body["current"]["text"] == "assert result == result\n"
    assert body["current"]["state"] == "present"
    assert body["identical"] is False
    assert body["session_id"] == session.id
    assert body["flagged"] == {"text": None}


def _intervention_with_flagged(
    goal: Goal, session: HarnessSession, flagged_text: str
):
    from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
    from pex_protocol.enums import Authority, PolicyVerdict
    from pex_protocol.intervention import Intervention

    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session.id,
        goal_id=goal.id,
        payload={"text": "re-verify"},
        rationale="acceptance surface modified",
        evidence=["acceptance_surface_modified:test_csv_utils.py"],
        risk=RiskLevel.LOW,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id="int-flagged",
        session_id=session.id,
        goal_id=goal.id,
        trigger="stop",
        evidence=list(action.evidence),
        diagnosis="acceptance surface modified",
        proposed_action=action,
        risk=RiskLevel.LOW.value,
        authority_required=Authority.LOCAL_POLICY.value,
        action_taken=InterventionType.SEND_NUDGE.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="sent",
        created_at=datetime.now(UTC),
        metadata={
            "verification": {
                "status": "uncertain",
                "acceptance_surface": {"modified": ["test_csv_utils.py"]},
                "flagged_content": {"test_csv_utils.py": flagged_text},
            }
        },
    )


async def test_diff_surfaces_the_flagged_bytes_from_the_incident(client) -> None:
    http, store, tmp_path = client
    goal, session = await _bind(store, tmp_path)
    await _seal(store, goal, session, b"assert result == 'a,b'\n")
    await store.add_intervention(
        _intervention_with_flagged(goal, session, "assert result == result\n")
    )
    body = (
        await http.get(
            f"/v1/goals/{goal.id}/acceptance-diff",
            params={"path": "test_csv_utils.py"},
        )
    ).json()
    assert body["flagged"]["text"] == "assert result == result\n"
    assert body["flagged"]["captured_at"]


async def test_diff_reports_missing_current_file_honestly(client) -> None:
    http, store, tmp_path = client
    goal, session = await _bind(store, tmp_path)
    await _seal(store, goal, session, b"assert True\n")
    body = (
        await http.get(
            f"/v1/goals/{goal.id}/acceptance-diff",
            params={"path": "test_csv_utils.py"},
        )
    ).json()
    assert body["current"]["state"] == "missing"
    assert body["current"]["text"] is None
    assert body["identical"] is None


async def test_diff_reports_digest_only_baseline(client) -> None:
    http, store, tmp_path = client
    goal, session = await _bind(store, tmp_path)
    digest = hashlib.sha256(b"x").hexdigest()
    await store.recall_or_seal_acceptance_baseline(
        session.id,
        goal.id,
        workspace=session.cwd,
        captured_at="t",
        files={"test_csv_utils.py": digest},
        files_complete=True,
    )
    body = (
        await http.get(
            f"/v1/goals/{goal.id}/acceptance-diff",
            params={"path": "test_csv_utils.py"},
        )
    ).json()
    assert body["baseline"]["state"] == "digest_only"
    assert body["baseline"]["text"] is None


async def test_diff_rejects_paths_outside_the_surface(client) -> None:
    http, store, tmp_path = client
    goal, _session = await _bind(store, tmp_path)
    assert (
        await http.get(
            f"/v1/goals/{goal.id}/acceptance-diff", params={"path": "../secret.txt"}
        )
    ).status_code == 422
    assert (
        await http.get(
            f"/v1/goals/{goal.id}/acceptance-diff", params={"path": "src/app.py"}
        )
    ).status_code == 422
    assert (
        await http.get(
            "/v1/goals/missing/acceptance-diff",
            params={"path": "test_a.py"},
        )
    ).status_code == 404


async def test_diff_without_baseline_is_a_404(client) -> None:
    http, store, tmp_path = client
    goal, _session = await _bind(store, tmp_path)
    assert (
        await http.get(
            f"/v1/goals/{goal.id}/acceptance-diff", params={"path": "test_a.py"}
        )
    ).status_code == 404
