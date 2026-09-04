from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import (
    AdapterMessageResult,
    HarnessAdapter,
    resolve_adapter_message_result,
)
from pex_bridge.adapters.claude_code import ClaudeCodeAdapter
from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport
from pex_bridge.adapters.cursor import CursorAdapter
from pex_bridge.adapters.devin import DevinAdapter
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_bridge.adapters.qwen import QwenAdapter
from pex_bridge.adapters.synthetic import SyntheticAdapter
from pex_bridge.app import _bounded_adapter_probe
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.capabilities import (
    AdapterCapabilities,
    AdapterSupportLabel,
    PermissionResponseMode,
)
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorResult


class ProbeAdapter(HarnessAdapter):
    name = "probe"

    def __init__(self, caps: AdapterCapabilities) -> None:
        self.caps = caps
        self.probe_calls = 0

    async def probe(self) -> AdapterCapabilities:
        self.probe_calls += 1
        return self.caps

    async def discover_sessions(self) -> list[HarnessSession]:
        return []


class SlowProbeAdapter(HarnessAdapter):
    name = "slow-probe"

    async def probe(self) -> AdapterCapabilities:
        await asyncio.sleep(60)
        raise AssertionError("cancelled probe must never finish")

    async def discover_sessions(self) -> list[HarnessSession]:
        return []


def test_supports_only_reports_negotiated_boolean_capabilities() -> None:
    capabilities = AdapterCapabilities(send_message=True, config_scope="session")

    assert capabilities.supports("send_message") is True
    assert capabilities.supports("config_scope") is False
    assert capabilities.supports("not_a_capability") is False


def _session(session_id: str = "probe:s1") -> HarnessSession:
    return HarnessSession(
        id=session_id,
        harness_type=HarnessType.UNKNOWN,
        vendor_session_id=session_id.split(":", 1)[-1],
        project_id="probe-project",
        cwd="probe-project",
        status=SessionStatus.WORKING,
        last_activity=datetime.now(UTC),
    )


def _event(session: HarnessSession, event_id: str = "status-1") -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=datetime.now(UTC),
        harness_type=session.harness_type,
        session_id=session.id,
        event_type=EventType.STATUS,
        message_delta="working",
    )


@pytest.mark.asyncio
async def test_adapter_probe_timeout_degrades_to_explicit_unavailable(monkeypatch):
    monkeypatch.setattr("pex_bridge.app.ADAPTER_PROBE_TIMEOUT_SECONDS", 0.01)
    capabilities = await _bounded_adapter_probe(SlowProbeAdapter())
    assert capabilities.support_label == AdapterSupportLabel.UNAVAILABLE
    assert capabilities.trust_level == 0
    assert "unavailable" in capabilities.notes.lower()


@pytest.mark.asyncio
async def test_pipeline_probes_and_persists_missing_capabilities(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    adapter = ProbeAdapter(
        AdapterCapabilities(
            send_message=True,
            support_label=AdapterSupportLabel.STRONG,
            notes="test transport",
        )
    )
    registry.bind("probe", adapter)
    pipeline = Pipeline(
        store,
        registry,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path),
    )
    session = _session()
    try:
        assert await pipeline.ingest_event(_event(session), session) is None
        saved = await store.get_session(session.id)
        assert saved is not None
        assert saved.capabilities["send_message"] is True
        assert saved.capabilities["support_label"] == "strong"
        assert saved.metadata["capabilities_adapter"] == "probe"
        assert adapter.probe_calls == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pipeline_refreshes_stored_capabilities_from_live_probe(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    registry = AdapterRegistry()
    adapter = ProbeAdapter(
        AdapterCapabilities(
            send_message=False,
            support_label=AdapterSupportLabel.UNAVAILABLE,
            notes="live probe supersedes stale stored state",
        )
    )
    registry.bind("probe", adapter)
    stored = _session()
    stored.capabilities = AdapterCapabilities(
        send_message=True,
        support_label=AdapterSupportLabel.STRONG,
        notes="stored negotiated state",
    ).model_dump(mode="json")
    await store.upsert_session(stored)
    incoming = _session()
    pipeline = Pipeline(
        store,
        registry,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path),
    )
    try:
        await pipeline.ingest_event(_event(incoming, "status-2"), incoming)
        saved = await store.get_session(incoming.id)
        assert saved is not None
        assert saved.capabilities["send_message"] is False
        assert saved.capabilities["notes"] == "live probe supersedes stale stored state"
        assert adapter.probe_calls == 1
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_store_upsert_preserves_negotiated_capabilities(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    stored = _session()
    stored.capabilities = AdapterCapabilities(
        send_message=True,
        support_label=AdapterSupportLabel.STRONG,
        notes="stored negotiated state",
    ).model_dump(mode="json")
    stored.metadata["capabilities_adapter"] = "probe"
    await store.upsert_session(stored)
    incoming = _session()
    try:
        await store.upsert_session(incoming)
        saved = await store.get_session(incoming.id)
        assert saved is not None
        assert saved.capabilities["send_message"] is True
        assert saved.metadata["capabilities_adapter"] == "probe"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_unknown_empty_capabilities_fail_closed(tmp_path, monkeypatch):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    session = _session("missing:s1")
    now = datetime.now(UTC)
    goal = Goal(
        id="goal-missing-capabilities",
        project_id=str(tmp_path),
        title="Keep capability checks fail closed",
        objective="Do not send a nudge through an unavailable adapter.",
        created_at=now,
        updated_at=now,
    )
    session.project_id = goal.project_id
    session.cwd = goal.project_id
    session.goal_id = goal.id
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session.id,
        goal_id=goal.id,
        payload={"text": "Continue with the missing acceptance criterion."},
        rationale="test capability gate",
        evidence=["missing criterion"],
    )

    async def decide(*_args, **_kwargs):
        return SupervisorResult(action=action, diagnosis="test")

    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path),
    )
    monkeypatch.setattr(pipeline.supervisor, "decide", decide)
    stop = HarnessEvent(
        event_id="stop-unknown",
        ts=datetime.now(UTC),
        harness_type=HarnessType.UNKNOWN,
        session_id=session.id,
        event_type=EventType.STOP,
        phase=EventPhase.TERMINAL,
    )
    try:
        intervention = await pipeline.ingest_event(stop, session)
        assert intervention is not None
        assert intervention.action_taken == InterventionType.NOOP.value
        assert intervention.proposed_action.type == InterventionType.SEND_NUDGE
        assert intervention.policy_verdict == PolicyVerdict.DENY
        assert intervention.result == "denied_by_policy"
        assert "missing_capability:send_message" in intervention.evidence
        saved = await store.get_session(session.id)
        assert saved is not None
        assert saved.capabilities["support_label"] == "unavailable"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_probes_do_not_advertise_unimplemented_controls(monkeypatch):
    monkeypatch.setattr("pex_bridge.adapters.desktop.running_image_names", lambda: set())
    cursor_adapter = CursorAdapter()
    cold_cursor = await cursor_adapter.probe()
    assert cold_cursor.support_label == AdapterSupportLabel.UNAVAILABLE
    assert cold_cursor.send_message is False
    cursor_session = cursor_adapter.upsert_from_hook(
        {"conversation_id": "live", "hook_event_name": "stop"}
    )
    cursor_adapter.normalize_hook({"hook_event_name": "stop"}, cursor_session)
    cursor = await cursor_adapter.probe()
    assert cursor.send_message is True
    assert cursor.approve is False
    assert cursor.deny is False
    assert cursor.permission_response_mode == PermissionResponseMode.NONE
    assert cursor.start is False
    assert cursor.modify_system_instructions is False

    claude_adapter = ClaudeCodeAdapter()
    cold_claude = await claude_adapter.probe()
    assert cold_claude.support_label == AdapterSupportLabel.UNAVAILABLE
    assert cold_claude.send_message is False
    claude_session = claude_adapter.ingest_hook(
        {"session_id": "live", "hook_event_name": "PermissionRequest"}
    )
    claude_adapter.normalize_hook({"hook_event_name": "PermissionRequest"}, claude_session)
    claude = await claude_adapter.probe()
    assert claude.approve is True
    assert claude.deny is True
    assert claude.permission_response_mode == PermissionResponseMode.INLINE
    assert claude.modify_system_instructions is False

    codex = await CodexAdapter(CodexAppServerTransport()).probe()
    assert codex.support_label == AdapterSupportLabel.BASIC
    assert codex.observe_messages is False
    assert codex.permission_response_mode == PermissionResponseMode.NONE
    assert codex.fork is False

    opencode = await OpenCodeAdapter(MemoryHttpTransport()).probe()
    assert opencode.support_label == AdapterSupportLabel.STRONG
    assert opencode.start is False
    assert opencode.fork is True
    assert opencode.observe_messages is False
    assert opencode.permission_response_mode == PermissionResponseMode.NONE
    assert opencode.modify_config is False
    assert opencode.config_scope == "none"

    qwen = await QwenAdapter(MemoryHttpTransport()).probe()
    assert qwen.start is False
    assert qwen.modify_config is False
    assert qwen.observe_permissions is False
    assert qwen.permission_response_mode == PermissionResponseMode.NONE

    devin = await DevinAdapter(MemoryHttpTransport()).probe()
    assert devin.start is False
    assert devin.observe_messages is False

    synthetic = await SyntheticAdapter().probe()
    assert synthetic.permission_response_mode == PermissionResponseMode.ASYNC
    assert synthetic.start is True
    assert synthetic.stop is True
    assert synthetic.fork is True
    assert synthetic.summarize is False
    assert synthetic.modify_model is False

    registry = AdapterRegistry()
    pi_adapter = registry.get("pi")
    assert pi_adapter is not None
    cold_pi = await pi_adapter.probe()
    assert cold_pi.support_label == AdapterSupportLabel.UNAVAILABLE
    with pytest.raises(RuntimeError, match="no verified hook integration"):
        pi_adapter.ingest_hook({"session_id": "pi-live"})  # type: ignore[attr-defined]
    pi = await pi_adapter.probe()
    assert pi.support_label == AdapterSupportLabel.UNAVAILABLE
    assert pi.observe_session_status is False
    assert pi.observe_messages is False
    assert pi.observe_tool_calls is False


@pytest.mark.asyncio
async def test_devin_v3_cursor_pages_and_message_events_match_current_contract():
    class CurrentDevinTransport:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict | None]] = []

        async def request(self, method: str, path: str, *, json=None):
            self.calls.append((method.upper(), path, json))
            if method.upper() == "POST":
                return {"session_id": "devin-1", "status": "resuming"}
            if path.endswith("?first=1"):
                return {"items": [], "has_next_page": False, "end_cursor": None}
            if path.endswith("/sessions?first=200"):
                return {
                    "items": [
                        {
                            "session_id": "devin-1",
                            "project_id": "project-1",
                            "status": "running",
                            "status_detail": "waiting_for_user",
                            "updated_at": 1_788_000_000,
                        }
                    ],
                    "has_next_page": True,
                    "end_cursor": "page two",
                }
            if "after=page%20two" in path:
                return {
                    "items": [
                        {
                            "session_id": "devin-2",
                            "project_id": "project-1",
                            "status": "running",
                            "status_detail": "working",
                            "updated_at": 1_788_000_001,
                        }
                    ],
                    "has_next_page": False,
                    "end_cursor": None,
                }
            if "/devin-1/messages?" in path:
                return {
                    "items": [
                        {
                            "created_at": 1_788_000_002,
                            "event_id": "evt-1",
                            "message": "I finished the requested change.",
                            "source": "devin",
                        }
                    ],
                    "has_next_page": False,
                    "end_cursor": None,
                }
            if "/devin-2/messages?" in path:
                return {"items": [], "has_next_page": False, "end_cursor": None}
            if path.endswith("/devin-1"):
                return {
                    "session_id": "devin-1",
                    "status": "exit",
                    "status_detail": "finished",
                    "updated_at": 1_788_000_003,
                }
            if path.endswith("/devin-2"):
                return {
                    "session_id": "devin-2",
                    "status": "running",
                    "status_detail": "working",
                    "updated_at": 1_788_000_004,
                }
            raise AssertionError(f"unexpected request: {method} {path}")

    transport = CurrentDevinTransport()
    adapter = DevinAdapter(transport)  # type: ignore[arg-type]
    caps = await adapter.probe()
    assert caps.resume is True
    sessions = await adapter.discover_sessions()
    assert [session.vendor_session_id for session in sessions] == ["devin-1", "devin-2"]
    assert sessions[0].external_url == "https://app.devin.ai/sessions/devin-1"
    assert sessions[1].external_url == "https://app.devin.ai/sessions/devin-2"
    assert sessions[0].status == SessionStatus.NEEDS_DECISION

    events: list[HarnessEvent] = []
    terminal_seen = asyncio.Event()

    async def ingest(event: HarnessEvent, _session: HarnessSession):
        events.append(event)
        if event.event_type == EventType.STOP:
            terminal_seen.set()

    pump = adapter.start_pipeline_pump(ingest)
    try:
        await asyncio.wait_for(terminal_seen.wait(), timeout=2)
        await asyncio.sleep(0.3)
    finally:
        pump.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pump

    messages = [event for event in events if event.event_type == EventType.AGENT_RESPONSE]
    terminals = [event for event in events if event.event_type == EventType.STOP]
    assert [event.event_id for event in messages] == ["devin-message:devin-1:evt-1"]
    assert messages[0].metadata["replay"] is True
    assert len(terminals) == 1
    assert terminals[0].event_id.startswith("devin-terminal:devin-1:")
    assert terminals[0].metadata["devin_status_detail"] == "finished"

    assert await adapter.send_message(sessions[0], "Continue in the same session.") is True
    assert transport.calls[-1] == (
        "POST",
        "/v3/organizations/org/sessions/devin-1/messages",
        {"message": "Continue in the same session."},
    )


@pytest.mark.asyncio
async def test_http_permission_events_are_pre_action_with_request_ids():
    opencode_adapter = OpenCodeAdapter(MemoryHttpTransport())
    opencode_session = HarnessSession(
        id="opencode:s1",
        harness_type=HarnessType.OPENCODE,
        vendor_session_id="s1",
        cwd="C:/project",
        project_id="C:/project",
    )
    opencode_adapter.sessions[opencode_session.id] = opencode_session
    opencode = opencode_adapter.normalize_sse(
        opencode_session,
        {
            "id": "evt-1",
            "type": "permission.asked",
            "properties": {
                "id": "permission-1",
                "sessionID": "s1",
                "cwd": "C:/project",
            },
        },
    )
    assert opencode.phase == EventPhase.BEFORE
    assert opencode.approval_request == {"request_id": "permission-1"}

    qwen_adapter = QwenAdapter(MemoryHttpTransport())
    qwen_session = HarnessSession(
        id="qwen:s1",
        harness_type=HarnessType.QWEN,
        vendor_session_id="s1",
    )
    qwen_adapter.sessions[qwen_session.id] = qwen_session
    qwen = qwen_adapter.normalize_sse(
        qwen_session,
        {
            "id": 2,
            "v": 1,
            "type": "permission_request",
            "data": {
                "requestId": "permission-2",
                "sessionId": "s1",
                "options": [
                    {"optionId": "proceed_once", "name": "Proceed once"},
                    {"optionId": "reject", "name": "Reject"},
                ],
            },
            "_pex_sse_path": "/session/s1/events",
        },
    )
    assert qwen.phase == EventPhase.BEFORE
    assert qwen.approval_request == {
        "request_id": "permission-2",
        "options": [
            {"optionId": "proceed_once", "name": "Proceed once"},
            {"optionId": "reject", "name": "Reject"},
        ],
    }


@pytest.mark.asyncio
async def test_attached_but_unhealthy_http_transports_are_unavailable():
    class DeadServer(MemoryHttpTransport):
        async def request(self, method: str, path: str, *, json=None):
            if method == "GET":
                raise RuntimeError("server down")
            return await super().request(method, path, json=json)

    for adapter in (
        OpenCodeAdapter(DeadServer()),
        QwenAdapter(DeadServer()),
        DevinAdapter(DeadServer()),
    ):
        caps = await adapter.probe()
        assert caps.support_label == AdapterSupportLabel.UNAVAILABLE
        assert caps.send_message is False


@pytest.mark.asyncio
async def test_failed_delivery_does_not_enter_opencode_inbox():
    class FailedPrompt(MemoryHttpTransport):
        async def request(self, method: str, path: str, *, json=None):
            if "prompt_async" in path:
                raise RuntimeError("server down")
            return await super().request(method, path, json=json)

    adapter = OpenCodeAdapter(FailedPrompt())
    sessions = await adapter.discover_sessions()
    assert await adapter.send_message(sessions[0], "continue") is False
    assert adapter.inbox.get(sessions[0].id, []) == []


@pytest.mark.asyncio
async def test_opencode_prompt_async_returns_verified_turn_receipt():
    adapter = OpenCodeAdapter(MemoryHttpTransport())
    sessions = await adapter.discover_sessions()
    result = await adapter.send_message(sessions[0], "report.txt is missing")
    assert isinstance(result, AdapterMessageResult)
    assert result.accepted is True
    assert result.vendor_session_id == sessions[0].vendor_session_id
    assert result.vendor_turn_id == "msg_prompt_1"
    resolution = resolve_adapter_message_result(result, session=sessions[0])
    assert resolution.status == "delivered"
    assert resolution.worker_delivery_receipt is not None
    assert resolution.worker_delivery_receipt["vendor_turn_id"] == "msg_prompt_1"


@pytest.mark.asyncio
async def test_opencode_repeated_prompt_requires_a_new_turn_receipt():
    transport = MemoryHttpTransport()
    transport.messages.append(
        {
            "info": {
                "id": "msg_old",
                "role": "user",
                "sessionID": "sess_demo",
            },
            "parts": [{"type": "text", "text": "report.txt is missing"}],
        }
    )
    adapter = OpenCodeAdapter(transport)
    sessions = await adapter.discover_sessions()

    result = await adapter.send_message(sessions[0], "report.txt is missing")

    assert isinstance(result, AdapterMessageResult)
    assert result.vendor_turn_id == "msg_prompt_1"
    assert result.vendor_turn_id != "msg_old"


@pytest.mark.asyncio
async def test_opencode_prompt_receipt_waits_for_new_message_visibility():
    class DelayedPromptReceipt(MemoryHttpTransport):
        def __init__(self) -> None:
            super().__init__()
            self.message_reads_after_prompt = 0

        async def request(self, method: str, path: str, *, json=None):
            result = await super().request(method, path, json=json)
            if method == "GET" and "/message" in path and self.prompts:
                self.message_reads_after_prompt += 1
                if self.message_reads_after_prompt < 3:
                    return []
            return result

    transport = DelayedPromptReceipt()
    adapter = OpenCodeAdapter(transport)
    sessions = await adapter.discover_sessions()

    result = await adapter.send_message(sessions[0], "continue with exact evidence")

    assert isinstance(result, AdapterMessageResult)
    assert result.vendor_turn_id == "msg_prompt_1"
    assert transport.message_reads_after_prompt == 3


@pytest.mark.asyncio
async def test_opencode_prompt_without_a_new_message_id_stays_delivery_uncertain():
    old_message = {
        "info": {
            "id": "msg_old",
            "role": "user",
            "sessionID": "sess_demo",
        },
        "parts": [{"type": "text", "text": "repeat the correction"}],
    }

    class OldReceiptOnly(MemoryHttpTransport):
        def __init__(self) -> None:
            super().__init__()
            self.messages.append(old_message)

        async def request(self, method: str, path: str, *, json=None):
            result = await super().request(method, path, json=json)
            if method == "GET" and "/message" in path:
                return [old_message]
            return result

    adapter = OpenCodeAdapter(OldReceiptOnly())
    sessions = await adapter.discover_sessions()

    result = await adapter.send_message(sessions[0], "repeat the correction")

    assert result is True
    resolution = resolve_adapter_message_result(result, session=sessions[0])
    assert resolution.status == "delivery_uncertain"
    assert resolution.worker_delivery_receipt is None


@pytest.mark.asyncio
async def test_opencode_concurrent_identical_prompts_get_distinct_receipts():
    class YieldingPromptTransport(MemoryHttpTransport):
        async def request(self, method: str, path: str, *, json=None):
            if method == "POST" and "/prompt_async" in path:
                await asyncio.sleep(0.01)
            return await super().request(method, path, json=json)

    adapter = OpenCodeAdapter(YieldingPromptTransport())
    sessions = await adapter.discover_sessions()

    first, second = await asyncio.gather(
        adapter.send_message(sessions[0], "same correction"),
        adapter.send_message(sessions[0], "same correction"),
    )

    assert isinstance(first, AdapterMessageResult)
    assert isinstance(second, AdapterMessageResult)
    assert {first.vendor_turn_id, second.vendor_turn_id} == {
        "msg_prompt_1",
        "msg_prompt_2",
    }


@pytest.mark.asyncio
async def test_opencode_prompt_ignores_foreign_session_receipt():
    foreign_message = {
        "info": {
            "id": "msg_foreign",
            "role": "user",
            "sessionID": "other-session",
        },
        "parts": [{"type": "text", "text": "continue locally"}],
    }

    class ForeignReceiptOnly(MemoryHttpTransport):
        async def request(self, method: str, path: str, *, json=None):
            result = await super().request(method, path, json=json)
            if method == "GET" and "/message" in path and self.prompts:
                return [foreign_message]
            return result

    adapter = OpenCodeAdapter(ForeignReceiptOnly())
    sessions = await adapter.discover_sessions()

    result = await adapter.send_message(sessions[0], "continue locally")

    assert result is True
    resolution = resolve_adapter_message_result(result, session=sessions[0])
    assert resolution.status == "delivery_uncertain"
    assert resolution.worker_delivery_receipt is None


@pytest.mark.asyncio
async def test_opencode_prompt_rejects_ambiguous_same_session_receipts():
    class SameTextCollision(MemoryHttpTransport):
        async def request(self, method: str, path: str, *, json=None):
            result = await super().request(method, path, json=json)
            if method == "POST" and "/prompt_async" in path:
                self.messages.append(
                    {
                        "info": {
                            "id": "msg_external",
                            "role": "user",
                            "sessionID": "sess_demo",
                        },
                        "parts": [{"type": "text", "text": "same correction"}],
                    }
                )
            return result

    adapter = OpenCodeAdapter(SameTextCollision())
    sessions = await adapter.discover_sessions()

    result = await adapter.send_message(sessions[0], "same correction")

    assert result is True
    resolution = resolve_adapter_message_result(result, session=sessions[0])
    assert resolution.status == "delivery_uncertain"
    assert resolution.worker_delivery_receipt is None


@pytest.mark.asyncio
async def test_opencode_invalid_sessions_cannot_exhaust_send_locks():
    adapter = OpenCodeAdapter(MemoryHttpTransport())
    sessions = await adapter.discover_sessions()
    for index in range(1_100):
        bogus = HarnessSession(
            id=f"opencode:bogus-{index}",
            harness_type=HarnessType.OPENCODE,
            vendor_session_id=f"bogus-{index}",
            cwd="C:/wrong",
            project_id="C:/wrong",
            status=SessionStatus.WORKING,
        )
        assert await adapter.send_message(bogus, "do not queue") is False

    assert adapter._message_send_locks == {}
    result = await adapter.send_message(sessions[0], "valid correction")
    assert isinstance(result, AdapterMessageResult)
    assert result.vendor_turn_id == "msg_prompt_1"


@pytest.mark.asyncio
async def test_failed_cursor_acp_delivery_is_not_queued_as_hook_followup():
    class FailedAcp:
        ready = True

        async def prompt(self, _session_id: str, _text: str):
            raise RuntimeError("acp down")

    adapter = CursorAdapter()
    session = adapter.upsert_from_hook({"conversation_id": "c1"})
    adapter.acp = FailedAcp()  # type: ignore[assignment]
    assert await adapter.send_message(session, "continue") is False
    assert adapter.consume_followup(session.id) is None
    assert adapter.inbox.get(session.id, []) == []


@pytest.mark.asyncio
async def test_cursor_hook_message_only_prepares_inside_active_stop():
    from pex_bridge.adapters.base import CursorHookPreparation

    adapter = CursorAdapter()
    session = adapter.upsert_from_hook({"conversation_id": "c-stop"})

    adapter.normalize_hook({"hook_event_name": "afterAgentResponse"}, session)
    inactive_capabilities = await adapter.probe()
    assert inactive_capabilities.support_label == AdapterSupportLabel.OBSERVE_ONLY
    assert inactive_capabilities.send_message is False
    assert await adapter.send_message(session, "continue") is False
    assert adapter.consume_followup(session.id) is None

    adapter.normalize_hook({"hook_event_name": "stop"}, session)
    capabilities = await adapter.probe()
    assert capabilities.support_label == AdapterSupportLabel.STRONG
    assert capabilities.send_message is True
    assert capabilities.inject_context is True
    assert capabilities.resume is True
    prepared = await adapter.send_message(session, "continue with the missing file")
    assert isinstance(prepared, CursorHookPreparation)
    assert not hasattr(prepared, "accepted")
    assert adapter.consume_followup(session.id) is None
    assert not adapter.pending_followups
    assert adapter.inbox.get(session.id, []) == []


@pytest.mark.asyncio
async def test_observe_inbox_stop_does_not_claim_hook_followup_delivery():
    adapter = CursorAdapter()
    session = adapter.upsert_from_hook({"conversation_id": "c-obs"})
    token = adapter._delivery_channel.set("observe")
    try:
        adapter.normalize_hook({"hook_event_name": "stop"}, session)
        capabilities = await adapter.probe()
        assert capabilities.support_label == AdapterSupportLabel.OBSERVE_ONLY
        assert capabilities.send_message is False
        assert capabilities.inject_context is False
        assert capabilities.resume is False
        assert await adapter.send_message(session, "continue with the missing file") is False
        assert adapter.consume_followup(session.id) is None
        assert adapter.inbox.get(session.id, []) == []
    finally:
        adapter._delivery_channel.reset(token)


@pytest.mark.asyncio
async def test_observe_inbox_permission_does_not_claim_inline_control():
    adapter = CursorAdapter()
    session = adapter.upsert_from_hook({"conversation_id": "c-obs-permission"})
    token = adapter._delivery_channel.set("observe")
    try:
        adapter.normalize_hook({"hook_event_name": "beforeShellExecution"}, session)
        capabilities = await adapter.probe()
        assert capabilities.support_label == AdapterSupportLabel.OBSERVE_ONLY
        assert capabilities.approve is False
        assert capabilities.deny is False
        assert capabilities.permission_response_mode == PermissionResponseMode.NONE
    finally:
        adapter._delivery_channel.reset(token)


@pytest.mark.asyncio
async def test_claude_hook_message_only_claims_delivery_inside_active_stop():
    adapter = ClaudeCodeAdapter()
    session = adapter.ingest_hook({"session_id": "c-stop"})

    adapter.normalize_hook({"hook_event_name": "PostToolUse"}, session)
    assert await adapter.send_message(session, "continue") is False

    adapter.normalize_hook({"hook_event_name": "Stop"}, session)
    assert await adapter.send_message(session, "verify report.txt")
    assert adapter.consume_followup(session.id) == "verify report.txt"
