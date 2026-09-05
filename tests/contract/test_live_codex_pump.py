"""Live App Server pump into ingest_event. Skips without a real `codex` binary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pex_bridge.adapters.codex_bin import resolve_codex_bin

from tests.contract.codex_live_proof import (
    assert_public_supervisor_receipt,
    assert_same_process,
    assert_source_unchanged,
    capture_process_provenance,
    capture_source_provenance,
    correlated_audit_receipts,
    event_receipts,
    intervention_receipt,
    publish_proof,
    start_proof_receipt,
    supervisor_receipt,
    utc_timestamp,
    validate_proof,
)
from tests.contract.live_gate import require_live_authorization

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROOF_SCRATCH = _REPO_ROOT / "benchmarks" / "results" / "_scratch"


def _turn_receipts(transport, session) -> list[dict]:
    receipts = [
        {
            "thread_id": item.get("threadId"),
            "cwd": item.get("cwd"),
            "approval_policy": item.get("approvalPolicy"),
            "sandbox_policy": item.get("sandboxPolicy"),
        }
        for item in getattr(transport, "turns", [])
    ]
    assert receipts
    for receipt in receipts:
        assert receipt == {
            "thread_id": session.vendor_session_id,
            "cwd": session.cwd,
            "approval_policy": "never",
            "sandbox_policy": {
                "type": "workspaceWrite",
                "writableRoots": [session.cwd],
                "networkAccess": False,
            },
        }
    return receipts


async def _durable_binding_receipts(store, goal, session) -> dict:
    stored_goal = await store.get_goal(goal.id)
    stored_session = await store.get_session(session.id)
    assert stored_goal == goal
    assert stored_session is not None
    assert stored_session.id == session.id
    assert stored_session.vendor_session_id == session.vendor_session_id
    assert stored_session.goal_id == goal.id
    assert stored_session.cwd == session.cwd
    assert stored_session.project_id == goal.project_id
    return {
        "goal": stored_goal.model_dump(mode="json"),
        "session": stored_session.model_dump(mode="json"),
    }


@pytest.mark.live_codex
@pytest.mark.asyncio
async def test_live_codex_app_server_stop_reaches_ingest(tmp_path: Path):
    require_live_authorization("PEX_LIVE_CODEX")
    binary = resolve_codex_bin()
    if not binary:
        pytest.skip("codex binary not found")

    from pex_bridge.adapters.codex import CodexAdapter, CodexStdioTransport

    transport = CodexStdioTransport(binary)
    adapter = CodexAdapter(transport)
    ingested: list[tuple[str, str | None]] = []

    async def ingest(event, session):
        ingested.append((event.event_type.value, session.vendor_session_id, session.cwd))

    try:
        session = await adapter.start_isolated_thread(str(tmp_path), name="pex-pump-proof")
        adapter.start_pipeline_pump(ingest)
        await adapter.start_turn(session, "Reply with the single word pong, then stop.")
        import asyncio

        for _ in range(200):
            if any(row[0] == "stop" for row in ingested):
                break
            await asyncio.sleep(0.25)
        proof = tmp_path / "codex_pump_proof.json"
        proof.write_text(json.dumps(ingested, indent=2), encoding="utf-8")
        assert any(row[0] == "stop" for row in ingested), f"no STOP ingested: {ingested!r}"
        assert any(row[1] == session.vendor_session_id for row in ingested)
    finally:
        existing = adapter._pump_task
        if existing is not None:
            existing.cancel()
            try:
                await existing
            except BaseException:
                pass
        await transport.close()


def _has_supervisor_key() -> bool:
    import os

    names = (
        "PEX_SUPERVISOR_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "PEX_ZEN_API_KEY",
        "OPENCODE_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
    )
    if any(os.environ.get(name) for name in names):
        return True
    env_path = Path(__file__).resolve().parents[2] / ".env"
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if any(name in text for name in names) and "PEX_SUPERVISOR_API_KEY=\n" not in text:
        return True
    return _local_openai_compat()


def _local_openai_compat() -> bool:
    import urllib.request

    try:
        urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=0.4)
        return True
    except Exception:
        return False


def _ensure_local_supervisor_env() -> None:
    import os

    from pex_supervisor.providers import _load_dotenv

    _load_dotenv()
    if os.environ.get("PEX_SUPERVISOR_PROVIDER"):
        return
    if os.environ.get("PEX_ZEN_API_KEY") or os.environ.get("OPENCODE_API_KEY"):
        return
    if not _local_openai_compat():
        return
    os.environ["PEX_SUPERVISOR_PROVIDER"] = "custom"
    os.environ["PEX_SUPERVISOR_BASE_URL"] = "http://127.0.0.1:8080/v1"
    os.environ.setdefault("PEX_SUPERVISOR_MODEL", "qwen3.8-27b")
    os.environ.setdefault("PEX_SUPERVISOR_API_KEY", "local")


@pytest.mark.live_codex
@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_codex_stop_inspects_with_strands(tmp_path: Path):
    """Recovery §12: STOP → ingest → inspect (used_llm) → NOOP or same-thread turn/start."""
    require_live_authorization("PEX_LIVE_CODEX", "PEX_LIVE_SUPERVISOR")
    if not _has_supervisor_key():
        pytest.skip("no supervisor API key or local OpenAI-compatible server")
    _ensure_local_supervisor_env()
    binary = resolve_codex_bin()
    if not binary:
        pytest.skip("codex binary not found")

    import asyncio
    from datetime import UTC, datetime

    from pex_bridge.adapters import AdapterRegistry
    from pex_bridge.adapters.codex import CodexAdapter, CodexStdioTransport
    from pex_bridge.bus import EventBus
    from pex_bridge.config import Settings
    from pex_bridge.pipeline import Pipeline
    from pex_bridge.store import Store, new_id
    from pex_protocol.goal import Goal
    from pex_supervisor.providers import load_supervisor_model

    model = load_supervisor_model()
    if model is None:
        pytest.skip("supervisor model did not construct")

    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    transport = CodexStdioTransport(binary)
    adapter = CodexAdapter(transport)
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    settings = Settings.for_test(
        require_auth=False, home=tmp_path, autonomy="manage", codex_attach=False
    )
    pipeline = Pipeline(store, registry, EventBus(), settings, model=model)
    now = datetime.now(UTC)
    goal = Goal(
        id=new_id("goal_"),
        project_id=str(tmp_path),
        title="ping",
        objective="Create ping.txt containing exactly the word pong.",
        acceptance_criteria=["ping.txt contains pong"],
        evidence_requirements=["ping.txt"],
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    source_before = capture_source_provenance(_REPO_ROOT)
    proof_path = _PROOF_SCRATCH / "codex_inspect_proof.json"
    proof = start_proof_receipt(
        proof_kind="evidence_supported_noop",
        source=source_before,
        sandbox="workspace-write",
    )
    publish_proof(proof_path, proof)
    last = None
    try:
        session = await adapter.start_isolated_thread(
            str(tmp_path),
            name="pex-inspect-proof",
            sandbox="workspace-write",
        )
        process_before = capture_process_provenance(transport, binary)
        session.goal_id = goal.id
        await store.upsert_session(session)
        adapter.start_pipeline_pump(pipeline.ingest_event)
        await adapter.start_turn(
            session,
            "Create a file named ping.txt containing exactly the word pong. "
            "Then stop. Do not do anything else.",
        )
        for _ in range(360):
            rows = await store.list_interventions(session.id)
            stops = [row for row in rows if row.trigger == "stop"]
            if stops:
                last = stops[0]
                break
            await asyncio.sleep(0.5)
        assert last is not None, "no STOP intervention"
        model_receipt = supervisor_receipt(last)
        assert_public_supervisor_receipt(model_receipt)
        assert last.session_id == session.id
        assert last.goal_id == goal.id
        assert last.action_taken == "NOOP"
        assert last.result == "noop"
        assert (last.metadata or {}).get("verification", {}).get("acceptance_status") == "supported"
        assert (tmp_path / "ping.txt").read_text(encoding="utf-8").strip() == "pong"
        assert not str((last.proposed_action.payload or {}).get("text") or "").startswith("PEX:")

        turns = _turn_receipts(transport, session)
        trigger_event_id = str((last.metadata or {}).get("trigger_event_id") or "")
        trigger = await store.get_event(trigger_event_id)
        assert trigger is not None
        assert trigger.event_type.value == "stop"
        assert trigger.session_id == session.id
        assert trigger.goal_id == goal.id
        assert trigger.event_id.startswith(f"{session.id}:turn:")
        assert trigger.raw_event_ref
        assert (trigger.metadata or {}).get("vendor_turn_id") == trigger.event_id.removeprefix(
            f"{session.id}:turn:"
        )
        assert (last.metadata or {}).get("worker_delivery_receipt") is None

        audit_receipts = await correlated_audit_receipts(store, [last])
        bindings = await _durable_binding_receipts(store, goal, session)
        process_after = capture_process_provenance(transport, binary)
        assert_same_process(process_before, process_after)
        source_after = capture_source_provenance(_REPO_ROOT)
        assert_source_unchanged(source_before, source_after)
        proof.update(
            {
                "proof_status": "validated",
                "completed_at": utc_timestamp(),
                "app_server": process_after,
                "goal": bindings["goal"],
                "session": bindings["session"],
                "turns": turns,
                "events": event_receipts([trigger]),
                "interventions": [intervention_receipt(last)],
                "audit_receipts": audit_receipts,
                "notification_methods": [
                    msg.get("method") for msg in getattr(transport, "notifications", [])[-20:]
                ],
                "artifact": {
                    "path": str(tmp_path / "ping.txt"),
                    "content": "pong",
                },
            }
        )
        validate_proof(proof)
        publish_proof(proof_path, proof)
        publish_proof(tmp_path / "codex_inspect_proof.json", proof)
    finally:
        current = asyncio.current_task()
        for task in list(asyncio.all_tasks()):
            if task is not current:
                task.cancel()
        existing = adapter._pump_task
        if existing is not None:
            try:
                await asyncio.wait_for(existing, timeout=1)
            except (asyncio.CancelledError, TimeoutError, Exception):
                pass
        try:
            await asyncio.wait_for(transport.close(), timeout=2)
        except Exception:
            pass
        try:
            await store.close()
        except Exception:
            pass


@pytest.mark.live_codex
@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_codex_incomplete_stop_sends_specific_continue(tmp_path: Path):
    """Genuine incomplete task → inspect → specific continue on the same threadId."""
    require_live_authorization("PEX_LIVE_CODEX", "PEX_LIVE_SUPERVISOR")
    if not _has_supervisor_key():
        pytest.skip("no supervisor API key or local OpenAI-compatible server")
    _ensure_local_supervisor_env()
    binary = resolve_codex_bin()
    if not binary:
        pytest.skip("codex binary not found")

    import asyncio
    from datetime import UTC, datetime

    from pex_bridge.adapters import AdapterRegistry
    from pex_bridge.adapters.codex import CodexAdapter, CodexStdioTransport
    from pex_bridge.bus import EventBus
    from pex_bridge.config import Settings
    from pex_bridge.pipeline import Pipeline
    from pex_bridge.store import Store, new_id
    from pex_protocol.goal import Goal
    from pex_supervisor.providers import load_supervisor_model

    model = load_supervisor_model()
    if model is None:
        pytest.skip("supervisor model did not construct")

    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    # Seed a readable empty target so the isolated Codex sandbox updates an
    # operator-owned artifact instead of creating a file the parent proof
    # process cannot inspect on Windows.
    (tmp_path / "report.txt").write_text("", encoding="utf-8")
    transport = CodexStdioTransport(binary)
    adapter = CodexAdapter(transport)
    registry = AdapterRegistry()
    registry.bind("codex", adapter)
    settings = Settings.for_test(
        require_auth=False, home=tmp_path, autonomy="manage", codex_attach=False
    )
    pipeline = Pipeline(store, registry, EventBus(), settings, model=model)
    now = datetime.now(UTC)
    goal = Goal(
        id=new_id("goal_"),
        project_id=str(tmp_path),
        title="report",
        objective="Create report.txt containing exactly the word shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    source_before = capture_source_provenance(_REPO_ROOT)
    proof_path = _PROOF_SCRATCH / "codex_incomplete_proof.json"
    proof = start_proof_receipt(
        proof_kind="same_thread_intervention_outcome",
        source=source_before,
        sandbox="workspace-write",
    )
    publish_proof(proof_path, proof)
    initial = None
    final = None
    try:
        session = await adapter.start_isolated_thread(
            str(tmp_path),
            name="pex-incomplete-proof",
            sandbox="workspace-write",
        )
        process_before = capture_process_provenance(transport, binary)
        session.goal_id = goal.id
        await store.upsert_session(session)
        adapter.start_pipeline_pump(pipeline.ingest_event)
        await adapter.start_turn(
            session,
            "Stop immediately after one short sentence. "
            "Do not create report.txt or any other file.",
        )
        for _ in range(360):
            rows = await store.list_interventions(session.id)
            stops = [row for row in rows if row.trigger == "stop"]
            if len(stops) >= 2:
                final = stops[0]
                initial = stops[-1]
                break
            await asyncio.sleep(0.5)
        assert initial is not None, "no initial STOP intervention"
        assert final is not None, "no final STOP intervention"
        initial_model = supervisor_receipt(initial)
        final_model = supervisor_receipt(final)
        assert_public_supervisor_receipt(initial_model)
        assert_public_supervisor_receipt(final_model)
        assert initial.session_id == final.session_id == session.id
        assert initial.goal_id == final.goal_id == goal.id
        assert initial.action_taken in {
            "SEND_NUDGE",
            "CONTINUE_SESSION",
            "REQUEST_VERIFICATION",
        }, f"incomplete task stayed silent: {initial!r}"
        assert initial.result in {
            "sent",
            "continued",
            "verification_requested",
        }
        assert (initial.metadata or {}).get("verification", {}).get(
            "acceptance_status"
        ) == "unsatisfied"
        initial_worker_text = str((initial.proposed_action.payload or {}).get("text") or "")
        assert "report" in initial_worker_text.lower()
        assert not initial_worker_text.startswith("PEX:")
        assert (tmp_path / "report.txt").read_text(encoding="utf-8") == "shipped"
        assert final.action_taken == "NOOP"
        assert final.result == "noop"
        assert (final.metadata or {}).get("verification", {}).get(
            "acceptance_status"
        ) == "supported"
        assert initial.outcome == "goal_evidence_supported"
        assert initial.helped is True
        delivery = (initial.metadata or {}).get("worker_delivery_receipt")
        assert isinstance(delivery, dict)
        assert isinstance(delivery.get("vendor_turn_id"), str)
        assert delivery["vendor_turn_id"]
        assert delivery == {
            "schema": "pex.worker-delivery.codex-turn.v1",
            "target_session_id": session.id,
            "vendor_session_id": session.vendor_session_id,
            "vendor_turn_id": delivery["vendor_turn_id"],
        }

        turns = _turn_receipts(transport, session)
        assert len(turns) >= 2
        initial_trigger_id = str((initial.metadata or {}).get("trigger_event_id") or "")
        final_trigger_id = str((final.metadata or {}).get("trigger_event_id") or "")
        observed_ids = list((initial.metadata or {}).get("outcome_event_ids") or [])
        assert initial_trigger_id != final_trigger_id
        assert final_trigger_id in observed_ids
        evidence_event_ids = sorted({initial_trigger_id, final_trigger_id, *observed_ids})
        evidence_events = []
        for event_id in evidence_event_ids:
            event = await store.get_event(event_id)
            assert event is not None
            assert event.session_id == session.id
            assert event.goal_id == goal.id
            evidence_events.append(event)
        events_by_id = {event.event_id: event for event in evidence_events}
        for trigger_id in (initial_trigger_id, final_trigger_id):
            trigger = events_by_id[trigger_id]
            assert trigger.event_type.value == "stop"
            assert trigger.event_id.startswith(f"{session.id}:turn:")
            assert trigger.raw_event_ref
        final_trigger = events_by_id[final_trigger_id]
        assert (final_trigger.metadata or {}).get("vendor_turn_id") == delivery[
            "vendor_turn_id"
        ]
        assert final_trigger_id == f"{session.id}:turn:{delivery['vendor_turn_id']}"

        audit_receipts = await correlated_audit_receipts(store, [initial, final])
        initial_audits = [
            row for row in audit_receipts["audit_rows"] if row["intervention_id"] == initial.id
        ]
        assert initial_audits[-1]["payload"]["outcome"] == "goal_evidence_supported"
        assert initial_audits[-1]["payload"]["helped"] is True
        assert final_trigger_id in initial_audits[-1]["payload"]["observed_event_refs"]

        bindings = await _durable_binding_receipts(store, goal, session)
        process_after = capture_process_provenance(transport, binary)
        assert_same_process(process_before, process_after)
        source_after = capture_source_provenance(_REPO_ROOT)
        assert_source_unchanged(source_before, source_after)
        proof.update(
            {
                "proof_status": "validated",
                "completed_at": utc_timestamp(),
                "app_server": process_after,
                "goal": bindings["goal"],
                "session": bindings["session"],
                "turns": turns,
                "events": event_receipts(evidence_events),
                "interventions": [
                    intervention_receipt(initial),
                    intervention_receipt(final),
                ],
                "audit_receipts": audit_receipts,
                "notification_methods": [
                    msg.get("method") for msg in getattr(transport, "notifications", [])[-40:]
                ],
                "artifact": {
                    "path": str(tmp_path / "report.txt"),
                    "content": "shipped",
                },
            }
        )
        validate_proof(proof)
        publish_proof(proof_path, proof)
        publish_proof(tmp_path / "codex_incomplete_proof.json", proof)
    finally:
        current = asyncio.current_task()
        for task in list(asyncio.all_tasks()):
            if task is not current:
                task.cancel()
        try:
            await asyncio.wait_for(transport.close(), timeout=2)
        except Exception:
            pass
        try:
            await store.close()
        except Exception:
            pass
