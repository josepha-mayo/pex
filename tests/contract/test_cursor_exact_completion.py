"""Exact-file acceptance remains strict through the real hook/ingest boundary."""

import pytest
from pex_bridge.app import apply_cursor_hook, state

from tests.contract.test_cursor_hooks import client as client


@pytest.mark.parametrize("content,verdict", [
    (b"shipped", "supported"),
    (b"shipped\n", "contradicted"),
    (b"\xef\xbb\xbfshipped", "contradicted"),
])
@pytest.mark.asyncio
async def test_cursor_exact_objective_checks_bytes_without_fake_control(
    client, tmp_path, content, verdict,
):
    worker = tmp_path / "exact-worker"
    worker.mkdir()
    (worker / "report.txt").write_bytes(content)
    started = await client.post("/v1/hooks/cursor", json={
        "hook_event_name": "sessionStart", "conversation_id": "exact-worker",
        "workspace_roots": [str(worker)],
    })
    assert started.status_code == 200
    goal = await client.post("/v1/goals", json={
        "project_id": str(worker), "title": "report",
        "objective": "Create report.txt containing exactly the word shipped.",
        "acceptance_criteria": ["report.txt contains shipped"],
        "evidence_requirements": ["report.txt"],
    })
    assert goal.status_code == 200
    session_id = "cursor:exact-worker"
    attached = await client.post(f"/v1/sessions/{session_id}/attach", json={
        "goal_id": goal.json()["id"],
    })
    assert attached.status_code == 200
    response = await apply_cursor_hook({
        "hook_event_name": "stop", "conversation_id": "exact-worker",
        "workspace_roots": [str(worker)], "status": "completed",
        "observed_ns": 1, "text": "I am done.",
    })
    assert "followup_message" not in response
    rows = await client.get("/v1/interventions", params={"session_id": session_id})
    assert rows.status_code == 200
    last = rows.json()[-1]
    assert last["metadata"]["verification"]["status"] == verdict
    assert last["action_taken"] == "NOOP"
    if verdict == "contradicted":
        assert last["policy_verdict"] == "deny"
        assert "missing_capability:send_message" in last["evidence"]
    assert not state.adapters.cursor.pending_followups.get(session_id)
    assert not state.adapters.cursor.inbox.get(session_id)
