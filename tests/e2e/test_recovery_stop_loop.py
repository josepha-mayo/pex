from __future__ import annotations

import subprocess
import sys
from itertools import count

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.enums import EventPhase, EventType

_OPERATOR_TOKEN = "recovery-stop-operator-token-0123456789"
_GOAL_CONTROL_SEQUENCE = count(1)


@pytest.fixture
async def client(tmp_path):
    settings = Settings(
        require_auth=True,
        token=_OPERATOR_TOKEN,
        home=tmp_path,
        autonomy="manage",
    )
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = _OPERATOR_TOKEN
    await store.connect()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"},
    ) as ac:
        yield ac
    await store.close()


async def _attach_goal(client: AsyncClient, session_id: str, title: str, **goal_fields):
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "idempotency_key": f"recovery-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}",
                "project_id": "demo",
                "title": title,
                **goal_fields,
            },
        )
    ).json()
    attached = await client.post(
        f"/v1/sessions/{session_id}/attach",
        json={
            "idempotency_key": f"recovery-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "goal_id": goal["id"],
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert attached.status_code == 200
    return goal


@pytest.mark.asyncio
async def test_genuine_pytest_completion_is_noop(client: AsyncClient, tmp_path):
    worker = tmp_path / "complete-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="genuine-complete", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = await _attach_goal(
        client,
        session.id,
        "Parser",
        objective="Implement the parser with passing tests",
        acceptance_criteria=["tests pass"],
    )
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        },
    )
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    intervention = stopped.json()["intervention"]
    assert intervention["action_taken"] == "NOOP"
    assert intervention["metadata"]["verification"]["status"] == "supported"
    assert adapter.inbox[session.id] == []
    assert not str(intervention.get("worker_response") or "").startswith("PEX:")
    completion = await client.get(f"/v1/goals/{goal['id']}/completion")
    assert completion.status_code == 200
    assert completion.json()["status"] == "verified_complete"
    assert completion.json()["worker_narration_used"] is False
    asked = await client.post("/v1/ask", json={"question": "Is the task complete?"})
    assert asked.status_code == 200
    assert asked.json()["completion"]["status"] == "verified_complete"
    assert "Current-intent STOP evidence" in asked.json()["answer"]

    sibling = adapter.seed_session(vendor_id="genuine-complete-sibling", cwd=str(worker))
    await state.store.upsert_session(sibling)
    sibling_attach = await client.post(
        f"/v1/sessions/{sibling.id}/attach",
        json={
            "idempotency_key": f"recovery-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "goal_id": goal["id"],
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert sibling_attach.status_code == 200
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": sibling.id,
            "event_type": EventType.FILE_EDIT.value,
            "file_paths": ["parser.py"],
            "message": "Continuing work after the sibling STOP.",
        },
    )
    active = await client.get(f"/v1/goals/{goal['id']}/completion")
    assert active.json()["status"] == "in_progress"
    active_ask = await client.post("/v1/ask", json={"question": "Is the task complete?"})
    assert active_ask.json()["completion"]["status"] == "in_progress"
    assert active_ask.json()["answer"] == "Not yet. Newer work is active on this goal."
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": sibling.id,
            "event_type": EventType.STOP.value,
            "message": "Pausing without a completion claim.",
        },
    )

    changed = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={
            "idempotency_key": f"recovery-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "mode": "update",
            "expected_intent_revision": goal["intent_revision"],
            "acceptance_criteria": ["tests pass", "integration tests pass"],
        },
    )
    assert changed.status_code == 200
    stale = await client.get(f"/v1/goals/{goal['id']}/completion")
    assert stale.status_code == 200
    assert stale.json()["status"] == "uncertain"
    assert stale.json()["stale_evidence_excluded"] == 1


@pytest.mark.asyncio
async def test_completion_follows_newer_attached_unsatisfied_stop(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "newer-unsatisfied-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="older-supported-stop", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = await _attach_goal(
        client,
        session.id,
        "Parser",
        objective="Implement the parser with passing tests",
        acceptance_criteria=["tests pass"],
    )
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        },
    )
    first = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    assert first.json()["intervention"]["metadata"]["verification"]["status"] == (
        "supported"
    )
    assert (await client.get(f"/v1/goals/{goal['id']}/completion")).json()[
        "status"
    ] == "verified_complete"

    sibling = adapter.seed_session(vendor_id="newer-unsatisfied-stop", cwd=str(worker))
    await state.store.upsert_session(sibling)
    sibling_attach = await client.post(
        f"/v1/sessions/{sibling.id}/attach",
        json={
            "idempotency_key": f"recovery-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "goal_id": goal["id"],
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert sibling_attach.status_code == 200
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": sibling.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {
                "pytest": {
                    "ok": False,
                    "exit_code": 1,
                    "failed": "tests/test_parser.py::test_nested_array",
                    "output": "FAILED tests/test_parser.py::test_nested_array",
                }
            },
        },
    )
    later = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": sibling.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    assert later.json()["intervention"]["metadata"]["verification"]["status"] == (
        "contradicted"
    )
    completion = await client.get(f"/v1/goals/{goal['id']}/completion")
    assert completion.json()["status"] == "incomplete"
    asked = await client.post("/v1/ask", json={"question": "Is the task complete?"})
    assert asked.json()["completion"]["status"] == "incomplete"


@pytest.mark.asyncio
async def test_completion_does_not_credit_session_moved_off_the_goal(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "detached-complete-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="detached-complete", cwd=str(worker))
    await state.store.upsert_session(session)
    goal = await _attach_goal(
        client,
        session.id,
        "Parser",
        objective="Implement the parser with passing tests",
        acceptance_criteria=["tests pass"],
    )
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "pytest -q",
            "process_state": {"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        },
    )
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    assert stopped.json()["intervention"]["metadata"]["verification"]["status"] == (
        "supported"
    )
    completion = await client.get(f"/v1/goals/{goal['id']}/completion")
    assert completion.json()["status"] == "verified_complete"

    attached = await state.store.get_session_control_state(session.id)
    assert attached is not None
    other = (
        await client.post(
            "/v1/goals",
            json={
                "idempotency_key": f"recovery-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}",
                "project_id": "demo",
                "title": "Unrelated follow-on",
                "objective": "Do not inherit the previous STOP.",
            },
        )
    ).json()
    moved = await client.post(
        f"/v1/sessions/{session.id}/attach",
        json={
            "idempotency_key": f"recovery-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "goal_id": other["id"],
            "replace_existing": True,
            "expected_goal_id": goal["id"],
            "expected_control_revision": attached["control_revision"],
            "expected_goal_intent_revision": other["intent_revision"],
        },
    )
    assert moved.status_code == 200
    leftover = await client.get(f"/v1/goals/{goal['id']}/completion")
    assert leftover.status_code == 200
    assert leftover.json()["status"] == "uncertain"
    assert leftover.json()["reason"] == "no_current_supported_completion_evidence"


@pytest.mark.asyncio
async def test_premature_stop_continues_then_verifies_completion(client: AsyncClient, tmp_path):
    worker = tmp_path / "premature-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="premature", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "report",
        objective="Create report.txt containing exactly the word shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
    )
    first = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "I am done.",
        },
    )
    first_intervention = first.json()["intervention"]
    assert first_intervention["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "report.txt" in text
    assert "missing" in text.lower()
    assert not text.startswith("PEX:")

    (worker / "report.txt").write_text("shipped\n", encoding="utf-8")
    progress = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.FILE_EDIT.value,
            "file_paths": ["report.txt"],
            "message": "Wrote report.txt",
        },
    )
    assert progress.status_code == 200
    stored = await client.get("/v1/interventions", params={"session_id": session.id})
    nudge = next(item for item in stored.json() if item["action_taken"] == "SEND_NUDGE")
    assert nudge["outcome"] == "new_file_progress_observed"

    completed = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "I am done.",
        },
    )
    done = completed.json()["intervention"]
    assert done["action_taken"] == "NOOP"
    assert done["metadata"]["verification"]["status"] == "supported"
    stored = await client.get(
        "/v1/interventions",
        params={"session_id": session.id},
    )
    final_nudge = next(
        item for item in stored.json() if item["action_taken"] == "SEND_NUDGE"
    )
    assert final_nudge["outcome"] == "goal_evidence_supported"
    assert final_nudge["helped"] is True
    assert adapter.inbox[session.id] == [text]


@pytest.mark.asyncio
async def test_labeled_objective_is_extracted_on_create_and_checked_at_stop(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "extract-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="extract-goal", cwd=str(worker))
    await state.store.upsert_session(session)
    created = await client.post(
        "/v1/goals",
        json={
            "idempotency_key": f"recovery-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "project_id": "demo",
            "title": "receipt",
            "objective": (
                "Create the release receipt.\n\n"
                "Acceptance criteria:\n\n"
                "- report.txt contains shipped\n"
            ),
        },
    )
    assert created.status_code == 200
    goal = created.json()
    assert goal["acceptance_criteria"] == ["report.txt contains shipped"]
    attached = await client.post(
        f"/v1/sessions/{session.id}/attach",
        json={
            "idempotency_key": f"recovery-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
            "goal_id": goal["id"],
            "expected_goal_id": None,
            "expected_control_revision": 0,
            "expected_goal_intent_revision": goal["intent_revision"],
        },
    )
    assert attached.status_code == 200
    first = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "I am done.",
        },
    )
    intervention = first.json()["intervention"]
    assert intervention["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "report.txt" in text
    assert not text.startswith("PEX:")


@pytest.mark.asyncio
async def test_ten_genuine_completions_do_not_nag(client: AsyncClient, tmp_path):
    inspected = 10
    false_positives = 0
    for index in range(inspected):
        worker = tmp_path / f"complete-{index}"
        worker.mkdir()
        adapter = state.adapters.synthetic
        session = adapter.seed_session(vendor_id=f"fp-{index}", cwd=str(worker))
        await state.store.upsert_session(session)
        await _attach_goal(
            client,
            session.id,
            f"Parser {index}",
            objective="Implement the parser with passing tests",
            acceptance_criteria=["tests pass"],
        )
        await client.post(
            "/v1/synthetic/events",
            json={
                "session_id": session.id,
                "event_type": EventType.SHELL.value,
                "command": "pytest -q",
                "process_state": {"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
            },
        )
        stopped = await client.post(
            "/v1/synthetic/events",
            json={
                "session_id": session.id,
                "event_type": EventType.STOP.value,
                "message": "All tests passed. I am done.",
            },
        )
        intervention = stopped.json()["intervention"]
        false_positives += int(intervention["action_taken"] != "NOOP")
        assert adapter.inbox[session.id] == []
        assert intervention["metadata"]["verification"]["status"] == "supported"
    assert false_positives == 0
    assert false_positives / inspected == 0.0


@pytest.mark.asyncio
async def test_eval_before_missing_dataset_is_redirected(client: AsyncClient, tmp_path):
    worker = tmp_path / "eval-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="eval-before-data", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Eval",
        objective="Generate the evaluation dataset then run eval_runner",
        acceptance_criteria=["dataset.parquet exists"],
    )
    started = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "python eval_runner.py --full",
        },
    )
    assert started.status_code == 200
    intervention = started.json()["intervention"]
    assert intervention["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "dataset.parquet" in text
    assert not text.startswith("PEX:")


@pytest.mark.asyncio
async def test_premature_cleanup_of_required_artifact_asks(client: AsyncClient, tmp_path):
    worker = tmp_path / "cleanup-worker"
    worker.mkdir()
    (worker / "dataset.parquet").write_bytes(b"rows")
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="premature-cleanup", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Eval",
        objective="Keep the evaluation dataset",
        acceptance_criteria=["dataset.parquet exists"],
    )
    blocked = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "phase": EventPhase.BEFORE.value,
            "command": "rm dataset.parquet",
        },
    )
    assert blocked.status_code == 200
    intervention = blocked.json()["intervention"]
    assert intervention["action_taken"] == "ASK_HUMAN"
    question = str(intervention["proposed_action"]["payload"].get("question") or "")
    assert "dataset.parquet" in question
    assert adapter.inbox.get(session.id, []) == []


@pytest.mark.asyncio
async def test_agent_output_contradicting_ledger_is_redirected(client: AsyncClient, tmp_path):
    worker = tmp_path / "lint-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="agent-lint", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Train",
        objective="Train without touching preprocessing",
        constraints=["Do not alter dataset preprocessing."],
    )
    drifted = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.AGENT_RESPONSE.value,
            "message": "I will alter dataset preprocessing next.",
        },
    )
    assert drifted.status_code == 200
    intervention = drifted.json()["intervention"]
    assert intervention["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "dataset preprocessing" in text.lower()
    assert not text.startswith("PEX:")


@pytest.mark.asyncio
async def test_abandoned_background_train_is_woken_on_stop(client: AsyncClient, tmp_path):
    worker = tmp_path / "train-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="abandoned-train", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Train",
        objective="Train the model to completion",
        acceptance_criteria=["the training job finishes"],
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=worker,
    )
    try:
        launched = await client.post(
            "/v1/synthetic/events",
            json={
                "session_id": session.id,
                "event_type": EventType.SHELL.value,
                "command": "nohup python train.py --full &",
                "process_state": {"background": True, "pid": proc.pid, "running": True},
            },
        )
        assert launched.status_code == 200
        stopped = await client.post(
            "/v1/synthetic/events",
            json={
                "session_id": session.id,
                "event_type": EventType.STOP.value,
                "message": "I am done.",
            },
        )
        intervention = stopped.json()["intervention"]
        assert intervention["action_taken"] == "SEND_NUDGE"
        text = adapter.inbox[session.id][-1]
        assert "train.py" in text
        assert str(proc.pid) in text
        assert "process table" in text.lower()
        assert not text.startswith("PEX:")
    finally:
        proc.kill()
        proc.wait(timeout=10)


@pytest.mark.asyncio
async def test_exited_background_job_is_not_treated_as_abandoned(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "finished-train-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="finished-train", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Train",
        objective="Train the model to completion",
        acceptance_criteria=["the training job finishes"],
    )
    proc = subprocess.Popen([sys.executable, "-c", "pass"], cwd=worker)
    proc.wait(timeout=10)
    launched = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.SHELL.value,
            "command": "nohup python train.py --full &",
            "process_state": {"background": True, "pid": proc.pid, "running": True},
        },
    )
    assert launched.status_code == 200
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "Training finished.",
        },
    )
    intervention = stopped.json()["intervention"]
    assert intervention is None or intervention["action_taken"] == "NOOP"
    assert adapter.inbox[session.id] == []


@pytest.mark.asyncio
async def test_unrelated_refactor_is_redirected(client: AsyncClient, tmp_path):
    worker = tmp_path / "refactor-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="broad-refactor", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Eval",
        objective="Produce a complete evaluation",
        acceptance_criteria=["results.jsonl has 30 rows"],
    )
    drifted = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.FILE_EDIT.value,
            "file_paths": ["style.css", "readme.md", "helpers.py", "utils.py"],
            "message": "Broad cleanup of unrelated files.",
        },
    )
    intervention = drifted.json()["intervention"]
    assert intervention["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "style.css" in text
    assert not text.startswith("PEX:")
    stored = await state.store.get_session(session.id)
    assert stored is not None
    assert stored.status.value == "drifting"
    pet = await client.get("/v1/pet")
    assert pet.status_code == 200
    body = pet.json()
    assert body["drifting"] == 1
    assert "corrected" not in (body["headline"] or "").casefold()
    assert "drifting" in (body["headline"] or "").casefold()


@pytest.mark.asyncio
async def test_compaction_checkpoints_durable_ledger(client: AsyncClient, tmp_path):
    worker = tmp_path / "compact-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="precompact", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Eval",
        objective="Produce a complete evaluation",
        acceptance_criteria=["results.jsonl has 30 rows"],
        constraints=["Do not alter dataset preprocessing."],
    )
    compacted = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.COMPACTION.value,
            "message": "Compacting context.",
        },
    )
    intervention = compacted.json()["intervention"]
    assert intervention["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[session.id][-1]
    assert "Eval" in text
    assert "results.jsonl" in text
    assert "preprocessing" in text.lower()
    assert not text.startswith("PEX:")


@pytest.mark.asyncio
async def test_repeated_forgotten_facts_after_compaction_apply_context_overlay(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "health-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="context-health", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Parser",
        objective="Keep schema.json as the source of truth for the parser",
        acceptance_criteria=["parser tests pass"],
    )
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.FILE_EDIT.value,
            "file_paths": ["src/schema.json"],
            "message": "schema.json is the source of truth for the parser.",
        },
    )
    first = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.COMPACTION.value,
            "message": "Compacting context.",
        },
    )
    assert first.json()["intervention"]["action_taken"] == "SEND_NUDGE"
    for _ in range(2):
        await client.post(
            "/v1/synthetic/events",
            json={
                "session_id": session.id,
                "event_type": EventType.FILE_READ.value,
                "file_paths": ["src/schema.json"],
                "message": "Read schema.json",
            },
        )
    second = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.COMPACTION.value,
            "message": "Compacting context again.",
        },
    )
    intervention = second.json()["intervention"]
    assert intervention["action_taken"] == "APPLY_OVERLAY"
    assert intervention["result"] == "overlay_applied"
    assert intervention["reversible"] is True
    payload = (intervention.get("proposed_action") or {}).get("payload") or {}
    overlay = payload.get("overlay") or {}
    operation = await state.store.get_overlay_operation(str(overlay["id"]), "apply")
    parent = await state.store.get_event_effect(second.json()["event"]["event_id"], "main")
    assert operation is not None and operation["state"] == "delivered"
    assert parent is not None and parent["state"] == "delivered"
    assert operation["parent_effect_id"] == parent["effect_id"]
    assert parent["downstream_operation_id"] == operation["operation_id"]
    instructions = str((overlay.get("diff") or {}).get("system_instructions") or "")
    assert "schema.json is the source of truth" in instructions
    saved = await state.store.get_session(session.id)
    assert saved is not None
    assert saved.context_health < 0.6
    assert (saved.metadata.get("context_health_signals") or {}).get("forgotten_fact_count") == 1


@pytest.mark.asyncio
async def test_duplicate_work_across_agents_is_redirected(client: AsyncClient, tmp_path):
    worker = tmp_path / "dup-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    first = adapter.seed_session(vendor_id="dup-first", cwd=str(worker))
    second = adapter.seed_session(vendor_id="dup-second", cwd=str(worker))
    await state.store.upsert_session(first)
    await state.store.upsert_session(second)
    goal = (
        await client.post(
            "/v1/goals",
            json={
                "idempotency_key": f"recovery-goal-{next(_GOAL_CONTROL_SEQUENCE):08d}",
                "project_id": "demo",
                "title": "Parser",
                "objective": "Implement parser.py with passing tests",
                "acceptance_criteria": ["parser.py exists", "tests pass"],
            },
        )
    ).json()
    for session_id in (first.id, second.id):
        attached = await client.post(
            f"/v1/sessions/{session_id}/attach",
            json={
                "idempotency_key": f"recovery-attach-{next(_GOAL_CONTROL_SEQUENCE):08d}",
                "goal_id": goal["id"],
                "expected_goal_id": None,
                "expected_control_revision": 0,
                "expected_goal_intent_revision": goal["intent_revision"],
            },
        )
        assert attached.status_code == 200
    first_edit = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": first.id,
            "event_type": EventType.FILE_EDIT.value,
            "file_paths": ["parser.py"],
            "message": "Inspect and update the parser.",
        },
    )
    assert first_edit.status_code == 200
    first_body = first_edit.json()
    first_intervention = first_body["intervention"] if first_body else None
    assert first_intervention is None or first_intervention["action_taken"] == "NOOP"
    repeated = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": second.id,
            "event_type": EventType.FILE_EDIT.value,
            "file_paths": ["parser.py"],
            "message": "Inspect and update the parser.",
        },
    )
    assert repeated.status_code == 200
    intervention = repeated.json()["intervention"]
    assert intervention is not None
    assert intervention["action_taken"] == "SEND_NUDGE"
    text = adapter.inbox[second.id][-1]
    assert "parser.py" in text
    assert "repeating" in text
    assert "dup-first" not in text
    assert not text.startswith("PEX:")


class _UnavailableSupervisor:
    async def decide(self, request, *, local_model):
        del request, local_model
        raise ConnectionError("agentcore unavailable")


@pytest.mark.asyncio
async def test_cloud_supervisor_unavailable_still_corrects_missing_rows(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "cloud-down-worker"
    worker.mkdir()
    rows = "\n".join(f'{{"id": {i}}}' for i in range(27))
    (worker / "results.jsonl").write_text(rows + "\n", encoding="utf-8")
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="cloud-down", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Eval",
        objective="Produce a complete evaluation",
        acceptance_criteria=["results.jsonl has 30 rows"],
    )
    state.pipeline.supervisor = _UnavailableSupervisor()
    stopped = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session.id,
            "event_type": EventType.STOP.value,
            "message": "The evaluation is complete.",
        },
    )
    intervention = stopped.json()["intervention"]
    assert intervention["action_taken"] == "SEND_NUDGE"
    assert intervention["metadata"]["inference_status"] == "failed"
    text = adapter.inbox[session.id][-1]
    assert "27" in text and "30" in text
    assert not text.startswith("PEX:")


@pytest.mark.asyncio
async def test_repeated_identical_error_loop_is_redirected(client: AsyncClient, tmp_path):
    worker = tmp_path / "loop-worker"
    worker.mkdir()
    adapter = state.adapters.synthetic
    session = adapter.seed_session(vendor_id="error-loop", cwd=str(worker))
    await state.store.upsert_session(session)
    await _attach_goal(
        client,
        session.id,
        "Train",
        objective="Train the model to completion",
        acceptance_criteria=["the training job finishes"],
    )
    last = None
    for _ in range(4):
        last = await client.post(
            "/v1/synthetic/events",
            json={
                "session_id": session.id,
                "event_type": EventType.SHELL.value,
                "command": "python train.py",
                "error": "FileNotFoundError: data.parquet",
            },
        )
        assert last.status_code == 200
    intervention = last.json()["intervention"]
    assert intervention is not None
    assert intervention["action_taken"] in {"APPLY_OVERLAY", "SEND_NUDGE"}
    if intervention["action_taken"] == "SEND_NUDGE":
        text = adapter.inbox[session.id][-1]
        assert "acceptance" in text.lower()
        assert not text.startswith("PEX:")
        return
    assert intervention["reversible"] is True
    assert intervention["result"] == "overlay_applied", intervention
    undone = await client.post(
        f"/v1/interventions/{intervention['id']}/undo",
        json={"idempotency_key": "overlay-undo-recovery-0001"},
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["ok"] is True
