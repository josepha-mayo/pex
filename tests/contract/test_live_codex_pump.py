"""Live App Server pump into ingest_event. Skips without a real `codex` binary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pex_bridge.adapters.codex_bin import resolve_codex_bin


@pytest.mark.live_codex
@pytest.mark.asyncio
async def test_live_codex_app_server_stop_reaches_ingest(tmp_path: Path):
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
    if not _has_supervisor_key():
        pytest.skip("no supervisor API key or local OpenAI-compatible server")
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
    settings = Settings(require_auth=False, home=tmp_path, autonomy="manage", codex_attach=False)
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
    proof: dict = {"used_llm": False, "action_taken": None, "thread_id": None, "turns": []}
    try:
        session = await adapter.start_isolated_thread(str(tmp_path), name="pex-inspect-proof")
        session.goal_id = goal.id
        await store.upsert_session(session)
        adapter.start_pipeline_pump(pipeline.ingest_event)
        await adapter.start_turn(
            session,
            "Create a file named ping.txt containing exactly the word pong. Then stop. Do not do anything else.",
        )
        for _ in range(360):
            rows = await store.list_interventions(session.id)
            stops = [row for row in rows if row.trigger == "stop"]
            if stops:
                last = stops[0]
                proof["used_llm"] = bool((last.metadata or {}).get("used_llm"))
                proof["action_taken"] = last.action_taken
                proof["diagnosis"] = last.diagnosis
                proof["thread_id"] = session.vendor_session_id
                proof["worker_text"] = str((last.proposed_action.payload or {}).get("text") or "")
                proof["turns"] = [item.get("threadId") for item in getattr(transport, "turns", [])]
                break
            await asyncio.sleep(0.5)
        events = await store.recent_events(session.id, 30)
        proof["event_types"] = [event.event_type.value for event in events]
        proof["notification_methods"] = [
            msg.get("method") for msg in getattr(transport, "notifications", [])[-20:]
        ]
        scratch = Path(__file__).resolve().parents[2] / "benchmarks" / "results" / "_scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "codex_inspect_proof.json").write_text(
            json.dumps(proof, indent=2), encoding="utf-8"
        )
        (tmp_path / "codex_inspect_proof.json").write_text(
            json.dumps(proof, indent=2), encoding="utf-8"
        )
        assert proof["action_taken"], f"no STOP intervention: {proof!r}"
        assert proof["used_llm"] is True, f"STOP did not inspect with a model: {proof!r}"
        assert not str(proof.get("worker_text") or "").startswith("PEX:")
        if proof["action_taken"] in {"SEND_NUDGE", "CONTINUE_SESSION", "REQUEST_VERIFICATION"}:
            assert session.vendor_session_id in proof["turns"]
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
    if not _has_supervisor_key():
        pytest.skip("no supervisor API key or local OpenAI-compatible server")
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
    settings = Settings(require_auth=False, home=tmp_path, autonomy="manage", codex_attach=False)
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
    proof: dict = {"used_llm": False, "action_taken": None, "thread_id": None, "turns": []}
    try:
        session = await adapter.start_isolated_thread(str(tmp_path), name="pex-incomplete-proof")
        session.goal_id = goal.id
        await store.upsert_session(session)
        adapter.start_pipeline_pump(pipeline.ingest_event)
        await adapter.start_turn(
            session,
            "Stop immediately after one short sentence. Do not create report.txt or any other file.",
        )
        for _ in range(360):
            rows = await store.list_interventions(session.id)
            stops = [row for row in rows if row.trigger == "stop"]
            if stops:
                last = stops[0]
                proof["used_llm"] = bool((last.metadata or {}).get("used_llm"))
                proof["action_taken"] = last.action_taken
                proof["diagnosis"] = last.diagnosis
                proof["thread_id"] = session.vendor_session_id
                proof["worker_text"] = str((last.proposed_action.payload or {}).get("text") or "")
                proof["turns"] = [item.get("threadId") for item in getattr(transport, "turns", [])]
                proof["report_exists"] = (tmp_path / "report.txt").exists()
                break
            await asyncio.sleep(0.5)
        scratch = Path(__file__).resolve().parents[2] / "benchmarks" / "results" / "_scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "codex_incomplete_proof.json").write_text(
            json.dumps(proof, indent=2), encoding="utf-8"
        )
        assert proof["used_llm"] is True, f"STOP did not inspect with a model: {proof!r}"
        assert not str(proof.get("worker_text") or "").startswith("PEX:")
        if not proof.get("report_exists"):
            assert proof["action_taken"] in {
                "SEND_NUDGE",
                "CONTINUE_SESSION",
                "REQUEST_VERIFICATION",
            }, f"incomplete task stayed silent: {proof!r}"
            assert session.vendor_session_id in proof["turns"]
            assert "report" in str(proof.get("worker_text") or "").lower()
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
