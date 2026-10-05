"""The evidence pack must be re-verifiable offline: bundled bytes hash to the
digests the report asserts, the event ledger re-chains, and the manifest covers
the whole payload — so `verify_pack.py` never has to trust the demo."""

from __future__ import annotations

import hashlib
import json
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
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import (
    Authority,
    EventType,
    HarnessType,
    PolicyVerdict,
    SessionStatus,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession

from scripts.verify_pack import load_pack, render_html, verify


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


SEALED = "assert result == 'a,b'\n"
FLAGGED = "assert result == result\n"


async def _seed(store: Store, tmp_path: Path) -> tuple[Goal, HarnessSession]:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-pack",
        project_id=str(workspace),
        title="Fix the CSV parser",
        objective="All tests green without touching tests.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="opencode:pack-1",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="pack-1",
        status=SessionStatus.STOPPED,
        goal_id=goal.id,
        project_id=str(workspace),
        cwd=str(workspace),
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    await store.recall_or_seal_acceptance_baseline(
        session.id,
        goal.id,
        workspace=str(workspace),
        captured_at="2026-10-05T00:00:00+00:00",
        files={"test_csv_utils.py": hashlib.sha256(SEALED.encode()).hexdigest()},
        files_complete=True,
        file_contents={"test_csv_utils.py": SEALED},
    )
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
    await store.add_intervention(
        Intervention(
            id="int-pack",
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
            created_at=now,
            metadata={
                "verification": {
                    "status": "uncertain",
                    "acceptance_surface": {"modified": ["test_csv_utils.py"]},
                    "flagged_content": {"test_csv_utils.py": FLAGGED},
                    "verdicts": [
                        {
                            "claim": {
                                "kind": "tests_pass",
                                "statement": "All tests passed",
                            },
                            "status": "uncertain",
                            "evidence": ["acceptance_surface_modified:test_csv_utils.py"],
                        }
                    ],
                }
            },
        )
    )
    for index, text in enumerate(("tampering", "all tests pass")):
        await store.add_event(
            HarnessEvent(
                event_id=f"ev-{index}",
                ts=now,
                harness_type=HarnessType.OPENCODE,
                session_id=session.id,
                event_type=EventType.AGENT_RESPONSE,
                message_delta=text,
            )
        )
    return goal, session


async def test_pack_roundtrips_through_the_offline_verifier(client) -> None:
    http, store, tmp_path = client
    goal, session = await _seed(store, tmp_path)

    response = await http.get(f"/v1/goals/{goal.id}/evidence-pack")
    assert response.status_code == 200
    pack = response.json()
    assert pack["schema"] == "pex.evidence-pack.v1"
    assert pack["goal_id"] == goal.id
    assert pack["report"]["schema"] == "pex.verification-report.v1"

    baseline = pack["acceptance_baselines"][0]
    assert baseline["session_id"] == session.id
    assert baseline["contents"]["test_csv_utils.py"] == SEALED
    assert baseline["files"]["test_csv_utils.py"] == hashlib.sha256(SEALED.encode()).hexdigest()

    flagged = pack["flagged"][0]
    assert flagged["contents"]["test_csv_utils.py"] == FLAGGED
    assert flagged["flagged_sha256"]["test_csv_utils.py"] != baseline["files"]["test_csv_utils.py"]

    ledger = pack["event_ledger"][0]
    assert ledger["session_id"] == session.id
    assert ledger["count"] == 2
    assert len(ledger["chain_sha256"]) == 64

    # The worker's own words ride each verdict so the timeline reads
    # claim -> independent verdict, not just action names.
    assert pack["report"]["claims"][0]["claim_statements"] == ["All tests passed"]

    # The acid test: the shipped verifier passes the endpoint's own output.
    checks = verify(pack)
    failures = [line for line in checks if line.startswith("FAIL")]
    assert failures == []
    assert any("hash chain reaches" in line for line in checks)


async def test_verifier_catches_a_mutated_pack() -> None:
    pack = json.loads(json.dumps(_fixture_pack()))
    assert not any(line.startswith("FAIL") for line in verify(pack))

    # Flip one baseline byte — every digest layer must reject it.
    pack["acceptance_baselines"][0]["contents"]["test_csv_utils.py"] = "assert True\n"
    failures = [line for line in verify(pack) if line.startswith("FAIL")]
    assert failures  # content no longer matches the sealed digest


def _fixture_pack() -> dict:
    def canonical(v) -> str:
        return json.dumps(
            v,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def sha(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    event = {"event_id": "e1", "event_type": "agent_response", "message_delta": "done"}
    event_sha = sha(canonical(event))
    pack = {
        "schema": "pex.evidence-pack.v1",
        "generated_at": "2026-10-05T00:00:00+00:00",
        "goal_id": "g",
        "report": {
            "schema": "pex.verification-report.v1",
            "goal": {"id": "g"},
            "claims": [],
            "summary": {"claims": 0},
        },
        "acceptance_baselines": [
            {
                "session_id": "s1",
                "files": {"test_csv_utils.py": sha(SEALED)},
                "contents": {"test_csv_utils.py": SEALED},
            }
        ],
        "flagged": [
            {
                "session_id": "s1",
                "intervention_id": "i1",
                "flagged_paths": ["test_csv_utils.py"],
                "flagged_sha256": {"test_csv_utils.py": sha(FLAGGED)},
                "contents": {"test_csv_utils.py": FLAGGED},
                "acceptance_surface": {"modified": ["test_csv_utils.py"]},
            }
        ],
        "event_ledger": [
            {
                "session_id": "s1",
                "count": 1,
                "truncated": False,
                "events": [{"sha256": event_sha, "event": event}],
                "chain_sha256": sha(f"|{event_sha}"),
            }
        ],
    }
    pack["manifest_sha256"] = sha(canonical(pack))
    return pack


async def test_render_html_is_self_contained_and_escapes(client) -> None:
    http, store, tmp_path = client
    goal, _ = await _seed(store, tmp_path)
    pack = (await http.get(f"/v1/goals/{goal.id}/evidence-pack")).json()

    page = render_html(pack, verify(pack))
    assert "CHECKS PASSED" in page
    assert "sealed/test_csv_utils.py" in page
    # The flagged bytes appear in the diff, HTML-escaped (the fixture's
    # ' quotes must not break out of the markup).
    assert "assert result == &#x27;" in page or "assert result == result" in page
    assert 'src="http' not in page and 'href="http' not in page


async def test_rendered_html_verifies_itself(client, tmp_path) -> None:
    http, store, _ = client
    goal, _ = await _seed(store, tmp_path)
    pack = (await http.get(f"/v1/goals/{goal.id}/evidence-pack")).json()

    page_path = tmp_path / "report.html"
    page_path.write_text(render_html(pack, verify(pack)), encoding="utf-8")
    reloaded = load_pack(page_path)
    assert reloaded["manifest_sha256"] == pack["manifest_sha256"]
    assert not any(line.startswith("FAIL") for line in verify(reloaded))


async def test_pack_for_unknown_goal_is_404(client) -> None:
    http, _, _ = client
    assert (await http.get("/v1/goals/nope/evidence-pack")).status_code == 404
