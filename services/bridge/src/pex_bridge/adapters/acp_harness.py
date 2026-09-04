"""Shared ACP-capable harness adapters.

Kimi (``kimi acp``), Hermes (``hermes acp``), and Oh My Pi (``omp acp``)
share the Agent Client Protocol. Grok Build uses ``grok agent stdio``. ACP turn
completion is the result of ``session/prompt``; it is not an idle notification.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pex_protocol.capabilities import (
    AdapterCapabilities,
    AdapterSupportLabel,
    ControlGranularity,
    PermissionResponseMode,
)
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.acp_client import (
    AcpClient,
    AcpPermissionResponse,
    AcpTransport,
)
from pex_bridge.adapters.base import (
    MAX_ADAPTER_MESSAGE_CHARS,
    DeliveryUncertainError,
    HarnessAdapter,
    bounded_adapter_id,
    bounded_adapter_text,
    bounded_observed_mapping,
    bounded_observed_text,
    preserve_bridge_state,
    session_binding_matches,
    verified_inline_permission_outcome,
)
from pex_bridge.adapters.desktop import is_desktop_observe_session
from pex_bridge.adapters.http_json import transport_events_since
from pex_bridge.adapters.strict_json import strict_json_dumps

ACP_PERMISSION_DELIVERY_TIMEOUT_SECONDS = 10.0
ACP_PERMISSION_DECISION_TIMEOUT_SECONDS = 300.0
ACP_PROMPT_TIMEOUT_SECONDS = 3600.0
ACP_CANCEL_TIMEOUT_SECONDS = 5.0
ACP_PROMPT_DELIVERY_TIMEOUT_SECONDS = 10.0
MAX_TRACKED_SESSIONS = 1_024
MAX_INBOX_MESSAGES = 1_000
MAX_PENDING_PERMISSIONS = 1_024
MAX_PERMISSION_OPTIONS = 64
MAX_PENDING_RESULTS = 1_024
MAX_HOOK_RECEIPTS = 10_000
MAX_FILE_PATHS = 256
MAX_PATH_CHARS = 4_096


@dataclass(slots=True)
class _PendingAcpPermission:
    session_id: str
    options: list[dict]
    decision: asyncio.Future[dict]
    delivered: asyncio.Future[None]


class AcpHarnessAdapter(HarnessAdapter):
    name = "acp"
    harness_type = HarnessType.UNKNOWN
    notes_base = "ACP JSON-RPC."
    hook_heartbeat_ttl_seconds = 30.0
    accepts_hooks = False

    def __init__(self, acp: AcpClient | None = None) -> None:
        self.acp = acp
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []
        self._pump_task: asyncio.Task | None = None
        self._last_hook_at: float | None = None
        self._prompt_results: asyncio.Queue[tuple[HarnessSession, str, dict | BaseException]] = (
            asyncio.Queue(maxsize=MAX_PENDING_RESULTS)
        )
        self._prompt_tasks: dict[str, asyncio.Task[bool]] = {}
        self._permission_events: asyncio.Queue[tuple[HarnessSession, HarnessEvent]] = (
            asyncio.Queue(maxsize=MAX_PENDING_RESULTS)
        )
        self._permission_requests: dict[str, _PendingAcpPermission] = {}
        self._permission_handler_installed = False
        self._last_pump_error: str | None = None
        self._active_hook: ContextVar[tuple[str, str] | None] = ContextVar(
            f"pex_{self.name}_active_hook_{id(self)}", default=None
        )
        self._bind_permission_handler()

    def attach_acp(self, transport: AcpTransport) -> None:
        if (
            self.acp is not None
            and self.acp.transport is not transport
            and self._pump_task is not None
            and not self._pump_task.done()
        ):
            raise RuntimeError("detach the active ACP transport before replacing it")
        self.acp = AcpClient(transport)
        self._bind_permission_handler()

    def _hook_live(self) -> bool:
        return (
            self._last_hook_at is not None
            and time.monotonic() - self._last_hook_at <= self.hook_heartbeat_ttl_seconds
        )

    def attach_transport(self, transport: AcpTransport) -> None:
        self.attach_acp(transport)

    def _bind_permission_handler(self) -> None:
        self._permission_handler_installed = False
        transport = self.acp.transport if self.acp is not None else None
        if transport is None or not hasattr(transport, "on_permission"):
            return
        transport.on_permission = self._handle_acp_permission
        self._permission_handler_installed = True

    async def _handle_acp_permission(self, params: dict) -> dict | AcpPermissionResponse:
        """Bridge one ACP server request through the normal intervention ledger."""
        cancelled = {"outcome": {"outcome": "cancelled"}}
        if (
            not isinstance(params, dict)
            or self.acp is None
            or self._pump_task is None
            or self._pump_task.done()
        ):
            return cancelled
        try:
            vendor_id = bounded_adapter_id(params.get("sessionId") or "", field="ACP session id")
        except ValueError:
            return cancelled
        session = self.sessions.get(f"{self.name}:{vendor_id}")
        if (
            not vendor_id
            or vendor_id not in self.acp.active_sessions
            or session is None
            or session.vendor_session_id != vendor_id
            or session.harness_type != self.harness_type
        ):
            return cancelled
        tool_call = params.get("toolCall")
        raw_options = params.get("options")
        if not isinstance(tool_call, dict):
            return cancelled
        try:
            tool_call_id = bounded_adapter_id(
                tool_call.get("toolCallId") or "", field="ACP tool call id"
            )
        except ValueError:
            return cancelled
        if not isinstance(raw_options, list):
            return cancelled
        options = [
            _bounded_permission_option(option)
            for option in raw_options[:MAX_PERMISSION_OPTIONS]
            if isinstance(option, dict)
            and str(option.get("optionId") or "").strip()
            and str(option.get("kind") or "").strip()
        ]
        if not options:
            return cancelled
        if len(self._permission_requests) >= MAX_PENDING_PERMISSIONS:
            return cancelled
        request_id = f"acp_perm_{uuid4().hex}"
        loop = asyncio.get_running_loop()
        pending = _PendingAcpPermission(
            session_id=session.id,
            options=options,
            decision=loop.create_future(),
            delivered=loop.create_future(),
        )
        self._permission_requests[request_id] = pending
        tool_call = {**tool_call, "toolCallId": tool_call_id}
        event = self._permission_event(session, request_id, params, tool_call, options)
        try:
            self._permission_events.put_nowait((session, event))
        except asyncio.QueueFull:
            self._permission_requests.pop(request_id, None)
            return cancelled
        try:
            try:
                result = await asyncio.wait_for(
                    asyncio.shield(pending.decision),
                    timeout=ACP_PERMISSION_DECISION_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                return cancelled
            return AcpPermissionResponse(result=result, delivered=pending.delivered)
        finally:
            if self._permission_requests.get(request_id) is pending:
                self._permission_requests.pop(request_id, None)

    def _permission_event(
        self,
        session: HarnessSession,
        request_id: str,
        params: dict,
        tool_call: dict,
        options: list[dict],
    ) -> HarnessEvent:
        raw_input = tool_call.get("rawInput")
        tool_input = bounded_observed_mapping(raw_input)
        command = _optional_bounded_text(
            (tool_input or {}).get("command"), field="ACP command"
        )
        locations = tool_call.get("locations")
        file_paths = [
            _bounded_path(item["path"])
            for item in (locations if isinstance(locations, list) else [])[:MAX_FILE_PATHS]
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and item.get("path", "").strip()
        ]
        title = _optional_bounded_text(tool_call.get("title"), field="ACP tool title") or ""
        kind = _optional_bounded_text(tool_call.get("kind"), field="ACP tool kind") or ""
        return HarnessEvent(
            event_id=f"{session.id}:acp-permission:{request_id}",
            ts=datetime.now(UTC),
            harness_type=self.harness_type,
            session_id=session.id,
            project_id=session.project_id,
            event_type=EventType.PERMISSION_REQUEST,
            phase=EventPhase.BEFORE,
            message_delta=title or kind or "ACP permission request",
            tool_name=title or kind or None,
            tool_input=tool_input,
            command=command,
            file_paths=file_paths,
            approval_request={
                "request_id": request_id,
                "method": "session/request_permission",
                "tool_call_id": str(tool_call.get("toolCallId")),
                "options": options,
            },
            metadata={
                "acp_method": "session/request_permission",
                "tool_call_id": str(tool_call.get("toolCallId")),
                "has_meta": isinstance(params.get("_meta"), dict),
            },
        )

    async def respond_permission(
        self, session: HarnessSession, request_id: str, decision: str
    ) -> bool:
        try:
            request_id = bounded_adapter_id(request_id, field="ACP permission request id")
        except ValueError:
            return False
        pending = self._permission_requests.get(request_id)
        normalized = str(decision or "").strip().lower()
        if (
            pending is None
            or pending.session_id != session.id
            or not session_binding_matches(
                self.sessions.get(session.id), session, harness_type=self.harness_type
            )
            or session.id != f"{self.name}:{session.vendor_session_id}"
            or normalized not in {"allow", "deny"}
            or pending.decision.done()
        ):
            return False
        option_kind = "allow_once" if normalized == "allow" else "reject_once"
        selected = next(
            (
                str(option.get("optionId"))
                for option in pending.options
                if option.get("kind") == option_kind and str(option.get("optionId") or "").strip()
            ),
            None,
        )
        exact = selected is not None or normalized == "deny"
        outcome = (
            {"outcome": {"outcome": "selected", "optionId": selected}}
            if selected is not None
            else {"outcome": {"outcome": "cancelled"}}
        )
        pending.decision.set_result(outcome)
        await asyncio.wait_for(
            asyncio.shield(pending.delivered),
            timeout=ACP_PERMISSION_DELIVERY_TIMEOUT_SECONDS,
        )
        # An allow without a one-time option was cancelled rather than silently
        # escalating to allow_always. A deny may safely use ACP cancellation when
        # the agent omitted reject_once.
        return exact

    async def probe(self) -> AdapterCapabilities:
        connected = False
        if self.acp is not None:
            try:
                if not self.acp.ready:
                    await self.acp.handshake()
                # initialize alone does not prove authentication or session
                # access. Listing is the passive, capability-gated attach probe.
                await self.acp.list_sessions()
                connected = True
            except Exception:
                connected = False
        pumping = self._pump_task is not None and not self._pump_task.done()
        transport = self.acp.transport if self.acp is not None else None
        reader = getattr(transport, "_reader_task", None)
        transport_healthy = reader is None or not reader.done()
        controllable = (
            connected
            and pumping
            and self._last_pump_error is None
            and transport_healthy
        )
        permission_control = controllable and self._permission_handler_installed
        hook_live = (
            self.accepts_hooks
            and self._last_hook_at is not None
            and time.monotonic() - self._last_hook_at <= self.hook_heartbeat_ttl_seconds
        )
        label = (
            AdapterSupportLabel.STRONG
            if controllable
            else AdapterSupportLabel.BASIC
            if connected
            else AdapterSupportLabel.OBSERVE_ONLY
            if hook_live
            else AdapterSupportLabel.UNAVAILABLE
        )
        return AdapterCapabilities(
            observe_messages=controllable or hook_live,
            observe_tool_calls=controllable or hook_live,
            observe_permissions=permission_control,
            observe_session_status=connected or hook_live,
            send_message=controllable,
            inject_context=controllable,
            approve=permission_control,
            deny=permission_control,
            permission_response_mode=(
                PermissionResponseMode.ASYNC if permission_control else PermissionResponseMode.NONE
            ),
            start=False,
            resume=controllable,
            control_granularity=(
                ControlGranularity.EVENT if controllable else ControlGranularity.SESSION
            ),
            trust_level=0.8 if controllable else 0.6 if connected else 0.55 if hook_live else 0.0,
            support_label=label,
            notes=self.notes_base
            + (
                " ACP session/list passed and the event/turn-result pump is running."
                if controllable
                else " ACP session/list passed; controls stay disabled until the event pump runs."
                if connected
                else " A recent explicitly installed hook heartbeat is observable."
                if hook_live
                else " No authenticated, capability-gated ACP session/list surface."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.acp is not None:
            try:
                listed = await self.acp.list_sessions()
            except Exception:
                listed = []
            for item in listed:
                if len(self.sessions) >= MAX_TRACKED_SESSIONS:
                    break
                try:
                    vendor_id = bounded_adapter_id(
                        item.get("sessionId") or "", field="ACP session id"
                    )
                except ValueError:
                    continue
                session_id = f"{self.name}:{vendor_id}"
                existing = self.sessions.get(session_id)
                cwd = _optional_bounded_path(item.get("cwd"))
                goal_id, paused = preserve_bridge_state(
                    existing,
                    cwd=cwd,
                    project_id=cwd,
                )
                self.sessions[session_id] = HarnessSession(
                    id=session_id,
                    harness_type=self.harness_type,
                    vendor_session_id=vendor_id,
                    cwd=cwd,
                    project_id=cwd,
                    status=SessionStatus.IDLE,
                    last_activity=datetime.now(UTC),
                    goal_id=goal_id,
                    supervision_paused=paused,
                    metadata={
                        "source": "acp",
                        "title": bounded_observed_text(
                            item.get("title"), field="ACP session title"
                        ),
                    },
                )
        return list(self.sessions.values())

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        if self.acp is None or self._pump_task is None or self._pump_task.done():
            return False
        bound = self.sessions.get(session.id)
        if (
            not session_binding_matches(bound, session, harness_type=self.harness_type)
            or is_desktop_observe_session(session)
            or is_desktop_observe_session(bound)
            or not session.vendor_session_id
            or session.id != f"{self.name}:{session.vendor_session_id}"
            or not bound.cwd
            or not bound.project_id
        ):
            return False
        try:
            cleaned = bounded_adapter_text(text).strip()
        except ValueError:
            return False
        session = bound
        inbox = self.inbox.setdefault(session.id, [])
        if len(inbox) >= MAX_INBOX_MESSAGES:
            return False
        current = self._prompt_tasks.get(session.id)
        if current is not None and not current.done():
            return False
        try:
            await self.acp.activate(session.vendor_session_id, str(session.cwd or ""))
        except DeliveryUncertainError:
            raise
        except Exception:
            return False
        dispatch_id = uuid4().hex
        delivered = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(
            self._run_prompt(session, cleaned, dispatch_id, delivered),
            name=f"{self.name}-acp-prompt",
        )
        self._prompt_tasks[session.id] = task
        try:
            await asyncio.wait_for(
                asyncio.shield(delivered), timeout=ACP_PROMPT_DELIVERY_TIMEOUT_SECONDS
            )
        except (DeliveryUncertainError, TimeoutError):
            # The write may complete after the local deadline; report uncertainty
            # to the executor instead of a false failed-delivery receipt.
            raise
        except Exception:
            return False
        inbox.append(cleaned)
        return True

    async def _run_prompt(
        self,
        session: HarnessSession,
        text: str,
        dispatch_id: str,
        delivered: asyncio.Future[None],
    ) -> bool:
        assert self.acp is not None
        try:
            try:
                result = await asyncio.wait_for(
                    self.acp.prompt(
                        session.vendor_session_id,
                        text,
                        delivered=delivered,
                    ),
                    timeout=ACP_PROMPT_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                try:
                    await asyncio.wait_for(
                        self.acp.cancel(session.vendor_session_id),
                        timeout=ACP_CANCEL_TIMEOUT_SECONDS,
                    )
                except Exception:
                    pass
                raise RuntimeError("ACP session prompt exceeded its bounded lifetime") from None
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            try:
                self._prompt_results.put_nowait((session, dispatch_id, exc))
            except asyncio.QueueFull:
                self._last_pump_error = "PromptResultQueueFull"
            return False
        else:
            try:
                self._prompt_results.put_nowait((session, dispatch_id, result))
            except asyncio.QueueFull:
                self._last_pump_error = "PromptResultQueueFull"
            return True
        finally:
            current = asyncio.current_task()
            if self._prompt_tasks.get(session.id) is current:
                self._prompt_tasks.pop(session.id, None)

    def ingest_hook(self, payload: dict) -> HarnessSession:
        if not self.accepts_hooks:
            raise RuntimeError(f"{self.name} has no installed HTTP hook surface")
        self._last_hook_at = time.monotonic()
        vendor_id = bounded_adapter_id(
            payload.get("session_id") or payload.get("task_id") or "",
            field="hook session_id or task_id",
        )
        session_id = f"{self.name}:{vendor_id}"
        existing = self.sessions.get(session_id)
        cwd = _optional_bounded_path(payload.get("cwd"))
        if existing is None and len(self.sessions) >= MAX_TRACKED_SESSIONS:
            raise ValueError("ACP hook session safety bound reached")
        goal_id, paused = preserve_bridge_state(
            existing,
            cwd=cwd,
            project_id=cwd,
        )
        session = HarnessSession(
            id=session_id,
            harness_type=self.harness_type,
            vendor_session_id=vendor_id,
            cwd=cwd,
            project_id=cwd,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
            goal_id=goal_id,
            supervision_paused=paused,
            metadata={
                "source": "hook",
                "identity_kind": "session_id" if payload.get("session_id") else "task_id",
            },
        )
        self.sessions[session_id] = session
        if len(self.hooks) >= MAX_HOOK_RECEIPTS:
            del self.hooks[: len(self.hooks) - MAX_HOOK_RECEIPTS + 1]
        self.hooks.append(
            {
                "session_id": session_id,
                "hook_event_name": bounded_observed_text(
                    payload.get("hook_event_name"),
                    field="ACP hook name",
                    max_chars=512,
                ),
                "received_at": datetime.now(UTC).isoformat(),
            }
        )
        return session

    def emit_status(self, session: HarnessSession, message: str) -> HarnessEvent:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=self.harness_type
        ):
            raise ValueError("ACP status session binding mismatch")
        return HarnessEvent(
            event_id=_stable_event_id(session.id, {"status": message}),
            ts=datetime.now(UTC),
            harness_type=self.harness_type,
            session_id=session.id,
            event_type=EventType.STATUS,
            message_delta=bounded_adapter_text(message, field="status message"),
        )

    def _params(self, payload: dict) -> dict:
        params = payload.get("params")
        return params if isinstance(params, dict) else {}

    def _session_for(self, payload: dict) -> HarnessSession | None:
        params = self._params(payload)
        try:
            vendor_id = bounded_adapter_id(
                params.get("sessionId")
                or params.get("session_id")
                or payload.get("sessionId")
                or "",
                field="ACP event session id",
            )
        except ValueError:
            return None
        session_id = f"{self.name}:{vendor_id}"
        existing = self.sessions.get(session_id)
        if existing:
            return existing
        return None

    def normalize_acp(
        self, session: HarnessSession, payload: dict, *, sequence: int | None = None
    ) -> HarnessEvent | None:
        method = bounded_adapter_id(payload.get("method") or "", field="ACP event method")
        if method != "session/update":
            return None
        params = self._params(payload)
        if (
            str(params.get("sessionId") or params.get("session_id") or "")
            != session.vendor_session_id
        ):
            raise ValueError("ACP event/session binding mismatch")
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=self.harness_type
        ):
            raise ValueError("ACP canonical session binding mismatch")
        update = params.get("update") if isinstance(params.get("update"), dict) else params
        kind = bounded_adapter_id(
            update.get("sessionUpdate") or update.get("session_update") or "unknown",
            field="ACP session update",
        )
        state = _optional_bounded_text(update.get("state"), field="ACP state") or ""
        stop = _optional_bounded_text(
            update.get("stopReason") or update.get("stop_reason"),
            field="ACP stop reason",
        ) or ""
        content = update.get("content")
        text = ""
        if isinstance(content, dict):
            text = _optional_bounded_text(content.get("text"), field="ACP content") or ""
        elif isinstance(content, str):
            text = content
        if not text:
            text = _optional_bounded_text(
                update.get("text") or update.get("title"), field="ACP event message"
            ) or stop or kind or state
        if kind in {"agent_message_chunk", "agentMessageChunk"}:
            event_type = EventType.AGENT_RESPONSE
            phase = EventPhase.AFTER
        elif kind in {"agent_thought_chunk", "agentThoughtChunk"}:
            event_type = EventType.AGENT_THOUGHT
            phase = EventPhase.DURING
        elif kind in {"tool_call", "toolCall"}:
            event_type = EventType.TOOL_CALL
            phase = EventPhase.DURING
        elif kind in {"tool_call_update", "toolCallUpdate"}:
            raw_status = update.get("status")
            status = (
                bounded_adapter_id(raw_status, field="ACP tool status")
                if isinstance(raw_status, str) and raw_status
                else ""
            )
            event_type = (
                EventType.TOOL_FAILURE
                if status == "failed"
                else EventType.TOOL_RESULT
                if status == "completed"
                else EventType.TOOL_CALL
            )
            phase = EventPhase.AFTER
        else:
            event_type = EventType.STATUS
            phase = EventPhase.AFTER
        raw_input = update.get("rawInput") or update.get("raw_input")
        tool_input = bounded_observed_mapping(raw_input)
        locations = update.get("locations")
        file_paths = [
            _bounded_path(item.get("path"))
            for item in (locations if isinstance(locations, list) else [])[:MAX_FILE_PATHS]
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and item.get("path", "").strip()
        ]
        tool_name = _optional_bounded_text(
            update.get("title") or update.get("kind"), field="ACP tool name"
        )
        return HarnessEvent(
            event_id=_stable_event_id(session.id, payload, sequence=sequence),
            ts=datetime.now(UTC),
            harness_type=self.harness_type,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=phase,
            message_delta=_optional_bounded_text(text, field="ACP event message"),
            tool_name=tool_name,
            tool_input=tool_input,
            command=_optional_bounded_text(
                (tool_input or {}).get("command"), field="ACP command"
            ),
            file_paths=file_paths,
            error=(text if event_type == EventType.TOOL_FAILURE else None),
            metadata={
                "acp_method": method,
                "session_update": kind,
                "stop_reason": stop,
                "replay": False,
            },
        )

    def normalize_prompt_result(
        self,
        session: HarnessSession,
        dispatch_id: str,
        result: dict | BaseException,
    ) -> HarnessEvent:
        if isinstance(result, BaseException):
            return HarnessEvent(
                event_id=f"{session.id}:acp-prompt:{dispatch_id}",
                ts=datetime.now(UTC),
                harness_type=self.harness_type,
                session_id=session.id,
                project_id=session.project_id,
                event_type=EventType.ERROR,
                phase=EventPhase.TERMINAL,
                error=type(result).__name__,
                metadata={"acp_method": "session/prompt", "dispatch_id": dispatch_id},
            )
        stop_reason = (
            bounded_observed_text(
                result.get("stopReason"),
                field="ACP stop reason",
                max_chars=512,
            )
            or ""
        ).strip()
        if not stop_reason:
            return HarnessEvent(
                event_id=f"{session.id}:acp-prompt:{dispatch_id}",
                ts=datetime.now(UTC),
                harness_type=self.harness_type,
                session_id=session.id,
                project_id=session.project_id,
                event_type=EventType.ERROR,
                phase=EventPhase.TERMINAL,
                error="ACP session/prompt result omitted stopReason",
                metadata={"acp_method": "session/prompt", "dispatch_id": dispatch_id},
            )
        return HarnessEvent(
            event_id=f"{session.id}:acp-prompt:{dispatch_id}",
            ts=datetime.now(UTC),
            harness_type=self.harness_type,
            session_id=session.id,
            project_id=session.project_id,
            event_type=EventType.STOP,
            phase=EventPhase.TERMINAL,
            message_delta=stop_reason,
            metadata={
                "acp_method": "session/prompt",
                "stop_reason": stop_reason,
                "dispatch_id": dispatch_id,
            },
        )

    async def pump_into_pipeline(self, ingest) -> None:
        seen = 0
        active_transport: object | None = None
        while True:
            try:
                transport = getattr(self.acp, "transport", None) if self.acp is not None else None
                if transport is None:
                    await asyncio.sleep(0.25)
                    continue
                if transport is not active_transport:
                    active_transport = transport
                    seen = 0
                next_seen, events, dropped = transport_events_since(transport, seen)
                if dropped:
                    raise RuntimeError("ACP event retention gap detected")
                for sequence, payload in enumerate(events, start=seen + 1):
                    if not isinstance(payload, dict):
                        continue
                    session = self._session_for(payload)
                    if session is None:
                        continue
                    event = self.normalize_acp(session, payload, sequence=sequence)
                    if event is None:
                        continue
                    await ingest(event, session)
                seen = next_seen
                while not self._prompt_results.empty():
                    session, dispatch_id, result = self._prompt_results.get_nowait()
                    await ingest(
                        self.normalize_prompt_result(session, dispatch_id, result), session
                    )
                while not self._permission_events.empty():
                    session, event = self._permission_events.get_nowait()
                    await ingest(event, session)
                self._last_pump_error = None
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_pump_error = type(exc).__name__
                await asyncio.sleep(0.5)

    def start_pipeline_pump(self, ingest) -> asyncio.Task:
        existing = self._pump_task
        if existing is not None and not existing.done():
            return existing
        self._pump_task = asyncio.create_task(
            self.pump_into_pipeline(ingest),
            name=f"{self.name}-acp-pipeline-pump",
        )
        return self._pump_task


class KimiAdapter(AcpHarnessAdapter):
    name = "kimi"
    harness_type = HarnessType.KIMI
    notes_base = (
        "Official `kimi acp`: initialize, session/new|load|resume|prompt, "
        "session/request_permission."
    )


class HermesAdapter(AcpHarnessAdapter):
    name = "hermes"
    harness_type = HarnessType.HERMES
    notes_base = (
        "Official Hermes ACP (`hermes acp`) plus plugin hooks "
        "(pre_tool_call block, pre_llm_call {context} inject, on_session_end observe). "
        "Do not launch Hermes desktop."
    )
    accepts_hooks = True

    async def discover_sessions(self) -> list[HarnessSession]:
        listed = await super().discover_sessions()
        from pex_bridge.adapters.desktop import upsert_desktop_observe_session

        upsert_desktop_observe_session(
            self.sessions,
            harness=HarnessType.HERMES,
            process=("Hermes.exe", "NousHermes.exe"),
            skip_if_other_sessions=True,
        )
        return list(self.sessions.values()) if self.sessions else listed

    HOOK_EVENT_MAP = {
        "pre_tool_call": EventType.TOOL_CALL,
        "post_tool_call": EventType.TOOL_RESULT,
        "pre_llm_call": EventType.USER_PROMPT,
        "post_llm_call": EventType.AGENT_RESPONSE,
        "on_session_start": EventType.SESSION_START,
        "on_session_end": EventType.STOP,
        "on_session_finalize": EventType.SESSION_END,
        "pre_approval_request": EventType.PERMISSION_REQUEST,
        "subagent_stop": EventType.STOP,
    }

    async def probe(self):
        caps = await super().probe()
        from pex_bridge.adapters.desktop import matching_desktop_image

        hook_live = self._hook_live()
        desktop = matching_desktop_image(("Hermes.exe", "NousHermes.exe")) is not None
        if not hook_live:
            if desktop and caps.support_label == AdapterSupportLabel.UNAVAILABLE:
                return caps.model_copy(
                    update={
                        "observe_session_status": True,
                        "focus_ui": True,
                        "trust_level": 0.4,
                        "support_label": AdapterSupportLabel.OBSERVE_ONLY,
                        "notes": caps.notes
                        + (
                            " A Hermes desktop process is already running; "
                            "observe/focus only until ACP attaches."
                        ),
                    }
                )
            return caps
        active = self._active_hook.get()
        active_deny = bool(active and active[1] == "pre_tool_call")
        return caps.model_copy(
            update={
                "observe_messages": True,
                "observe_tool_calls": True,
                "observe_session_status": True,
                "observe_permissions": caps.observe_permissions,
                # Current Hermes plugin hooks support a block directive, not a
                # portable auto-allow or force-human directive. ACP may
                # independently provide an exact asynchronous allow-once vote.
                "approve": caps.approve,
                "deny": caps.deny or active_deny,
                "permission_response_mode": (
                    PermissionResponseMode.BOTH
                    if caps.permission_response_mode == PermissionResponseMode.ASYNC
                    and active_deny
                    else PermissionResponseMode.INLINE
                    if active_deny
                    else caps.permission_response_mode
                ),
                "control_granularity": ControlGranularity.EVENT,
                "trust_level": 0.75,
                "support_label": (
                    AdapterSupportLabel.STRONG
                    if caps.support_label == AdapterSupportLabel.STRONG
                    else AdapterSupportLabel.BASIC
                ),
                "notes": caps.notes
                + (
                    " Official plugin hooks can block the active tool request. "
                    "Messaging/resume remains unavailable until ACP handshakes."
                ),
            }
        )

    async def focus_ui(self, session: HarnessSession) -> bool:
        from pex_bridge.adapters.winfocus import focus_harness

        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.HERMES
        ):
            return False
        return focus_harness("hermes")

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        if self.acp is not None:
            ok = await super().send_message(session, text, attachments)
            if ok:
                return True
        # pre_llm_call can return context, but it cannot itself start/resume a
        # stopped worker. Queuing text here would falsely claim delivery.
        return False

    def normalize_hook(self, payload: dict, session: HarnessSession) -> HarnessEvent:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.HERMES
        ):
            raise ValueError("Hermes hook session binding mismatch")
        payload_session = payload.get("session_id") or payload.get("task_id")
        if payload_session and bounded_adapter_id(
            payload_session, field="Hermes session id"
        ) != session.vendor_session_id:
            raise ValueError("Hermes hook payload session mismatch")
        hook_name = bounded_adapter_id(
            payload.get("hook_event_name") or payload.get("hook") or "unknown",
            field="Hermes hook name",
        )
        self._active_hook.set((session.id, hook_name))
        args = payload.get("args") if isinstance(payload.get("args"), dict) else None
        text = (
            payload.get("assistant_response")
            or payload.get("user_message")
            or payload.get("text")
            or payload.get("message")
            or payload.get("result")
        )
        return HarnessEvent(
            event_id=_stable_event_id(session.id, payload),
            ts=datetime.now(UTC),
            harness_type=HarnessType.HERMES,
            session_id=session.id,
            event_type=self.HOOK_EVENT_MAP.get(hook_name, EventType.STATUS),
            phase=EventPhase.TERMINAL
            if hook_name in {"on_session_end", "on_session_finalize"}
            else EventPhase.BEFORE,
            message_delta=_optional_bounded_text(text, field="Hermes hook message"),
            tool_name=_optional_bounded_text(payload.get("tool_name"), field="Hermes tool name"),
            tool_input=bounded_observed_mapping(args),
            command=_optional_bounded_text(
                (args or {}).get("command") if args else payload.get("command"),
                field="Hermes hook command",
            ),
            metadata={"hook_event_name": hook_name},
        )

    def hook_response(
        self, session: HarnessSession, payload: dict, intervention: Intervention | None
    ) -> dict:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.HERMES
        ):
            return {}
        raw_hook_name = payload.get("hook_event_name") or payload.get("hook")
        if not isinstance(raw_hook_name, str):
            return {}
        try:
            hook_name = bounded_adapter_id(raw_hook_name, field="Hermes hook name")
        except ValueError:
            return {}
        if hook_name == "pre_tool_call":
            if not self._hook_live() or self._active_hook.get() != (session.id, hook_name):
                return {}
            self._active_hook.set(None)
            decision = verified_inline_permission_outcome(
                session,
                intervention,
                expected_trigger=EventType.TOOL_CALL,
                expected_request_id=_stable_event_id(session.id, payload),
            )
            if decision == "deny":
                return {
                    "action": "block",
                    "message": bounded_observed_text(
                        intervention.diagnosis or "PEX denied this permission request",
                        field="Hermes hook response",
                        max_chars=4_096,
                    )
                    or "PEX denied this permission request",
                }
            # Hermes documents only the block directive. It cannot express a
            # portable allow or force-human response, and a PEX policy failure
            # is never converted to a worker denial.
            return {}
        return {}


class OmpAdapter(AcpHarnessAdapter):
    name = "omp"
    harness_type = HarnessType.OMP
    notes_base = (
        "Oh My Pi official `omp acp` JSON-RPC; session/request_permission gates destructive tools. "
        "STOP inspect comes from the terminal session/prompt stopReason."
    )


def _stable_event_id(session_id: str, payload: dict, *, sequence: int | None = None) -> str:
    canonical = strict_json_dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    suffix = f":{sequence}" if sequence is not None else ""
    return f"{session_id}:acp:{digest}{suffix}"


def _optional_bounded_text(value: object, *, field: str) -> str | None:
    return bounded_observed_text(value, field=field, max_chars=MAX_ADAPTER_MESSAGE_CHARS)


def _bounded_path(value: object) -> str:
    return bounded_adapter_text(value, field="path", max_chars=MAX_PATH_CHARS)


def _optional_bounded_path(value: object) -> str | None:
    if value is None or value == "":
        return None
    return _bounded_path(value)


def _bounded_permission_option(option: dict) -> dict:
    result: dict[str, str] = {}
    for key in ("optionId", "kind", "name", "label"):
        value = option.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            result[key] = bounded_adapter_id(value, field=f"ACP permission {key}")
        except ValueError:
            continue
    return result
