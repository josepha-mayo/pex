"""Qwen Code via official `qwen serve` HTTP + SSE daemon.

Strong only after capability negotiation and a session-bound SSE stream.
Documented routes: GET /capabilities, workspace-scoped session listing,
POST /session/:id/prompt, GET /session/:id/events, and bound permission votes.
Default daemon port 4170.
"""

from __future__ import annotations

import asyncio
import hashlib
import ntpath
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import quote, unquote, urlparse

from pex_protocol.capabilities import (
    AdapterCapabilities,
    AdapterSupportLabel,
    ControlGranularity,
    PermissionResponseMode,
)
from pex_protocol.enums import (
    EventPhase,
    EventType,
    HarnessType,
    PolicyVerdict,
    SessionStatus,
)
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import (
    MAX_ADAPTER_MESSAGE_CHARS,
    AdapterMessageResult,
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
from pex_bridge.adapters.http_json import (
    HttpJsonTransport,
    MemoryHttpTransport,
    transport_events_since,
)
from pex_bridge.adapters.strict_json import strict_json_dumps

QWEN_MAX_SESSION_PAGES = 100
QWEN_MAX_SESSIONS = 1_024
QWEN_MAX_PAGE_SESSIONS = 256
MAX_INBOX_MESSAGES = 1_000
MAX_HOOK_RECEIPTS = 10_000
MAX_PERMISSION_REQUESTS = 1_024
MAX_PERMISSION_OPTIONS = 64
MAX_PATH_CHARS = 4_096
ACTIVE_PROMPT_TTL_SECONDS = 3_600.0


class QwenAdapter(HarnessAdapter):
    name = "qwen"
    accepts_hooks = True
    hook_heartbeat_ttl_seconds = 30.0
    session_discovery_interval_seconds = 2.0

    def __init__(self, transport: HttpJsonTransport | None = None) -> None:
        self.transport = transport
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []
        self._pump_task: asyncio.Task | None = None
        self._daemon_capabilities: dict = {}
        self._permission_options: dict[tuple[str, str], list[dict]] = {}
        self._permission_request_owners: dict[str, str] = {}
        self._active_prompt_ids: dict[str, str] = {}
        self._active_prompt_started_at: dict[str, float] = {}
        self._last_hook_at: float | None = None
        self._pending_followups: dict[str, str] = {}
        self._active_hook: ContextVar[tuple[str, str] | None] = ContextVar(
            f"pex_qwen_active_hook_{id(self)}", default=None
        )
        self._last_pump_error: str | None = None
        self._event_gap_detected = False

    def attach_transport(self, transport: HttpJsonTransport) -> None:
        if (
            self.transport is not None
            and self.transport is not transport
            and self._pump_task is not None
            and not self._pump_task.done()
        ):
            raise RuntimeError("detach the active Qwen transport before replacing it")
        self.transport = transport

    def _pumping(self) -> bool:
        task = self._pump_task
        return task is not None and not task.done()

    def _hook_live(self) -> bool:
        return (
            self._last_hook_at is not None
            and time.monotonic() - self._last_hook_at <= self.hook_heartbeat_ttl_seconds
        )

    def _events_connected(self, session: HarnessSession | None = None) -> bool:
        paths = getattr(self.transport, "connected_sse_paths", set())
        if not isinstance(paths, set):
            return False
        if session is None:
            return any(path.startswith("/session/") and path.endswith("/events") for path in paths)
        return f"/session/{quote(session.vendor_session_id, safe='')}/events" in paths

    async def probe(self) -> AdapterCapabilities:
        daemon: dict = {}
        if self.transport is not None:
            try:
                result = await self.transport.request("GET", "/capabilities")
                raw_features = result.get("features") if isinstance(result, dict) else None
                if (
                    isinstance(result, dict)
                    and result.get("v") == 1
                    and isinstance(raw_features, list)
                    and all(isinstance(item, str) for item in raw_features)
                ):
                    daemon = result
            except Exception:
                daemon = {}
        self._daemon_capabilities = daemon
        features = {str(item) for item in daemon.get("features", []) if isinstance(item, str)}
        connected = bool(daemon)
        can_list = connected and "session_list" in features
        can_prompt = connected and "session_prompt" in features
        can_events = connected and "session_events" in features
        can_vote = connected and _permission_voting_available(self.transport, daemon, features)
        events_live = (
            can_events
            and self._pumping()
            and self._events_connected()
            and not self._event_gap_detected
            and self._last_pump_error is None
        )
        daemon_control = can_list and can_prompt and events_live
        hook_live = self._hook_live()
        active = self._active_hook.get()
        active_stop = bool(hook_live and active and active[1] == "Stop")
        active_permission = bool(
            hook_live and active and active[1] in {"PreToolUse", "PermissionRequest"}
        )
        label = (
            AdapterSupportLabel.STRONG
            if daemon_control or hook_live
            else AdapterSupportLabel.BASIC
            if connected
            else AdapterSupportLabel.UNAVAILABLE
        )
        return AdapterCapabilities(
            observe_messages=events_live or hook_live,
            observe_tool_calls=events_live or hook_live,
            observe_session_status=can_list or hook_live,
            observe_permissions=(events_live and can_vote) or hook_live,
            send_message=daemon_control or active_stop,
            inject_context=daemon_control or active_stop,
            approve=(events_live and can_vote) or active_permission,
            deny=(events_live and can_vote) or active_permission,
            permission_response_mode=(
                PermissionResponseMode.BOTH
                if events_live and can_vote and active_permission
                else PermissionResponseMode.ASYNC
                if events_live and can_vote
                else PermissionResponseMode.INLINE
                if active_permission
                else PermissionResponseMode.NONE
            ),
            start=False,
            resume=daemon_control or active_stop,
            modify_config=False,
            control_granularity=(
                ControlGranularity.EVENT
                if daemon_control or active_stop or active_permission
                else ControlGranularity.SESSION
            ),
            trust_level=0.82 if daemon_control or hook_live else 0.5 if connected else 0.0,
            support_label=label,
            notes=(
                "Official qwen serve v1 surface: GET /capabilities, workspace-scoped "
                "session listing, POST /session/:id/prompt, GET /session/:id/events, "
                "and negotiated session permission votes. "
                + (
                    "A session-bound SSE stream is connected and prompt admission is verified."
                    if daemon_control
                    else "SSE retention gap detected; observation and control are downgraded."
                    if self._event_gap_detected
                    else "A recent official Qwen hook heartbeat proves observation; "
                    "control is limited to a matching active hook."
                    if hook_live
                    else "Capability handshake passed; controls stay disabled until a "
                    "session-bound SSE stream connects."
                    if connected
                    else "No valid v1 capability handshake; label stays Unavailable."
                )
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.transport is None:
            return list(self.sessions.values())
        daemon = self._daemon_capabilities
        if not daemon:
            await self.probe()
            daemon = self._daemon_capabilities
        features = set(daemon.get("features") or [])
        workspace = str(daemon.get("workspaceCwd") or "").strip()
        if "session_list" not in features or not workspace:
            return list(self.sessions.values())
        if not _absolute_path(workspace):
            raise RuntimeError("Qwen capabilities returned a non-absolute workspaceCwd")
        if len(workspace) > MAX_PATH_CHARS or "\x00" in workspace:
            raise RuntimeError("Qwen capabilities returned an unsafe workspaceCwd")
        cursor: str | None = None
        seen_cursors: set[str] = set()
        listed_items: list[dict] = []
        for _ in range(QWEN_MAX_SESSION_PAGES):
            path = f"/workspace/{quote(workspace, safe='')}/sessions"
            if cursor:
                path += f"?cursor={quote(cursor, safe='')}"
            response = await self.transport.request("GET", path)
            if not isinstance(response, dict) or not isinstance(response.get("sessions"), list):
                raise RuntimeError("Qwen session listing returned a malformed page")
            page = response["sessions"]
            if len(page) > QWEN_MAX_PAGE_SESSIONS:
                raise RuntimeError("Qwen session page exceeded the safety bound")
            listed_items.extend(dict(item) for item in page if isinstance(item, dict))
            if len(listed_items) > QWEN_MAX_SESSIONS:
                raise RuntimeError("Qwen session listing exceeded the safety bound")
            next_cursor = response.get("nextCursor")
            if next_cursor is None or next_cursor == "":
                break
            if not isinstance(next_cursor, str):
                raise RuntimeError("Qwen session listing returned a malformed cursor")
            if next_cursor == cursor or next_cursor in seen_cursors:
                raise RuntimeError("Qwen session listing repeated a pagination cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            raise RuntimeError("Qwen session listing exceeded the pagination safety bound")
        for item in listed_items:
            try:
                vendor_id = bounded_adapter_id(
                    item.get("sessionId") or item.get("id") or "",
                    field="Qwen session id",
                )
            except ValueError:
                continue
            session_id = f"qwen:{vendor_id}"
            existing = self.sessions.get(session_id)
            item_cwd = _optional_bounded_path(item.get("workspaceCwd") or item.get("cwd")) or ""
            if item_cwd and ntpath.normcase(ntpath.normpath(item_cwd)) != ntpath.normcase(
                ntpath.normpath(workspace)
            ):
                raise RuntimeError("Qwen session escaped the negotiated workspace")
            goal_id, paused = preserve_bridge_state(
                existing,
                cwd=workspace,
                project_id=workspace,
            )
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.QWEN,
                vendor_session_id=vendor_id,
                cwd=workspace,
                project_id=workspace,
                status=SessionStatus.WORKING
                if item.get("hasActivePrompt")
                else SessionStatus.DISCOVERED,
                last_activity=datetime.now(UTC),
                goal_id=goal_id,
                supervision_paused=paused,
                metadata={
                    "source": "qwen_serve",
                    "title": bounded_observed_text(
                        item.get("title"), field="Qwen session title"
                    ),
                },
            )
        return list(self.sessions.values())

    async def send_message(
        self, session: HarnessSession, text: str, attachments=None
    ) -> bool | AdapterMessageResult:
        bound = self.sessions.get(session.id)
        if not session_binding_matches(bound, session, harness_type=HarnessType.QWEN):
            return False
        try:
            cleaned = bounded_adapter_text(text).strip()
        except ValueError:
            return False
        if session.id != f"qwen:{session.vendor_session_id}" or self._prompt_active(session.id):
            return False
        session = bound
        inbox = self.inbox.setdefault(session.id, [])
        if len(inbox) >= MAX_INBOX_MESSAGES:
            return False
        if self._hook_live() and self._active_hook.get() == (session.id, "Stop"):
            if (
                session.id not in self._pending_followups
                and len(self._pending_followups) >= QWEN_MAX_SESSIONS
            ):
                return False
            self._pending_followups[session.id] = cleaned
            inbox.append(cleaned)
            return AdapterMessageResult(
                accepted=True,
                vendor_session_id=session.vendor_session_id,
                vendor_turn_id=f"qwen-stop-{len(inbox):04d}",
            )
        if self.transport is None or not self._pumping() or not self._events_connected(session):
            return False
        features = set(self._daemon_capabilities.get("features") or [])
        if "session_prompt" not in features:
            await self.probe()
            features = set(self._daemon_capabilities.get("features") or [])
        if "session_prompt" not in features:
            return False
        try:
            result = await self.transport.request(
                "POST",
                f"/session/{quote(session.vendor_session_id, safe='')}/prompt",
                json={"prompt": [{"type": "text", "text": cleaned}]},
            )
        except DeliveryUncertainError:
            raise
        except Exception:
            return False
        try:
            prompt_id = bounded_adapter_id(
                result.get("promptId") if isinstance(result, dict) else "",
                field="Qwen prompt id",
            )
        except ValueError as exc:
            raise DeliveryUncertainError(
                "Qwen accepted the prompt request but returned no verified prompt id"
            ) from exc
        self._active_prompt_ids[session.id] = prompt_id
        self._active_prompt_started_at[session.id] = time.monotonic()
        inbox.append(cleaned)
        return AdapterMessageResult(
            accepted=True,
            vendor_session_id=session.vendor_session_id,
            vendor_turn_id=prompt_id,
        )

    def _prompt_active(self, session_id: str) -> bool:
        prompt_id = self._active_prompt_ids.get(session_id)
        if not prompt_id:
            return False
        started = self._active_prompt_started_at.get(session_id)
        if started is None or time.monotonic() - started <= ACTIVE_PROMPT_TTL_SECONDS:
            return True
        # The adapter cannot prove whether an expired prompt completed. Keep the
        # admission lock until a bound terminal event arrives rather than risk
        # overlapping a still-running turn.
        session = self.sessions.get(session_id)
        if session is not None:
            session.metadata["prompt_delivery_state"] = "completion_unobserved"
        return True

    async def respond_permission(
        self, session: HarnessSession, request_id: str, decision: str
    ) -> bool:
        try:
            request_id = bounded_adapter_id(request_id, field="permission request id")
        except ValueError:
            return False
        if (
            self.transport is None
            or not session_binding_matches(
                self.sessions.get(session.id), session, harness_type=HarnessType.QWEN
            )
            or session.id != f"qwen:{session.vendor_session_id}"
        ):
            return False
        features = set(self._daemon_capabilities.get("features") or [])
        if not {"session_permission_vote", "permission_vote"}.intersection(features):
            await self.probe()
            features = set(self._daemon_capabilities.get("features") or [])
        if not _permission_voting_available(self.transport, self._daemon_capabilities, features):
            return False
        binding_key = (session.id, request_id)
        if self._permission_request_owners.get(request_id) != session.id:
            return False
        options = self._permission_options.get(binding_key)
        if options is None:
            return False
        outcome = _permission_outcome(options, decision)
        if outcome is None:
            return False
        # Both current feature names vote on the documented global request
        # resource. The request itself remains bound to a session in PEX.
        path = f"/permission/{quote(request_id, safe='')}"
        try:
            await self.transport.request(
                "POST",
                path,
                json={"outcome": outcome},
            )
        except DeliveryUncertainError:
            raise
        except Exception:
            return False
        self._permission_options.pop(binding_key, None)
        self._permission_request_owners.pop(request_id, None)
        return True

    def ingest_hook(self, payload: dict) -> HarnessSession:
        self._last_hook_at = time.monotonic()
        vendor_id = bounded_adapter_id(
            payload.get("session_id") or payload.get("sessionId") or "",
            field="Qwen session_id",
        )
        session_id = f"qwen:{vendor_id}"
        existing = self.sessions.get(session_id)
        cwd = _optional_bounded_path(payload.get("cwd"))
        if existing is None and len(self.sessions) >= QWEN_MAX_SESSIONS:
            raise ValueError("Qwen session safety bound reached")
        goal_id, paused = preserve_bridge_state(
            existing,
            cwd=cwd,
            project_id=cwd,
        )
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.QWEN,
            vendor_session_id=vendor_id,
            cwd=cwd,
            project_id=cwd,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
            goal_id=goal_id,
            supervision_paused=paused,
            metadata={
                "source": "qwen_hook",
                "hook": bounded_observed_text(
                    payload.get("hook_event_name"),
                    field="Qwen hook name",
                    max_chars=512,
                ),
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
                    field="Qwen hook name",
                    max_chars=512,
                ),
                "received_at": datetime.now(UTC).isoformat(),
            }
        )
        return session

    def normalize_hook(self, payload: dict, session: HarnessSession) -> HarnessEvent:
        bound = self.sessions.get(session.id)
        if not session_binding_matches(bound, session, harness_type=HarnessType.QWEN):
            raise ValueError("Qwen hook session binding mismatch")
        payload_session_id = payload.get("session_id") or payload.get("sessionId")
        if payload_session_id and bounded_adapter_id(
            payload_session_id, field="Qwen session_id"
        ) != bound.vendor_session_id:
            raise ValueError("Qwen hook payload session mismatch")
        session = bound
        hook_name = bounded_adapter_id(
            payload.get("hook_event_name") or payload.get("hook") or "unknown",
            field="hook event name",
        )
        self._active_hook.set((session.id, hook_name))
        event_map = {
            "PreToolUse": EventType.TOOL_CALL,
            "PostToolUse": EventType.TOOL_RESULT,
            "PostToolUseFailure": EventType.TOOL_FAILURE,
            "PermissionRequest": EventType.PERMISSION_REQUEST,
            "UserPromptSubmit": EventType.USER_PROMPT,
            "Stop": EventType.STOP,
            "PreCompact": EventType.COMPACTION,
            "SessionStart": EventType.SESSION_START,
            "SessionEnd": EventType.SESSION_END,
            "MessageDisplay": EventType.STATUS,
        }
        tool_input = bounded_observed_mapping(payload.get("tool_input"))
        raw_submitted_prompt = payload.get("submitted_prompt")
        submitted_prompt = (
            raw_submitted_prompt.strip() if isinstance(raw_submitted_prompt, str) else ""
        )
        if submitted_prompt:
            submitted_prompt = bounded_adapter_text(submitted_prompt, field="submitted prompt")
        event_type = event_map.get(hook_name, EventType.STATUS)
        if hook_name == "UserPromptSubmit" and not submitted_prompt:
            # Qwen documents `prompt` as the prompt being sent to the model. It
            # can be synthesized by headless/ACP/serve callers. Only the
            # optional submitted_prompt field is evidence of direct human input.
            event_type = EventType.STATUS
        return HarnessEvent(
            event_id=_event_id(session.id, payload, source="hook"),
            ts=datetime.now(UTC),
            harness_type=HarnessType.QWEN,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=(
                EventPhase.TERMINAL if hook_name in {"Stop", "SessionEnd"} else EventPhase.BEFORE
            ),
            message_delta=_optional_bounded_text(
                submitted_prompt
                if hook_name == "UserPromptSubmit"
                else payload.get("message")
                or payload.get("text")
                or payload.get("last_assistant_message"),
                field="hook message",
            ),
            tool_name=_optional_bounded_text(payload.get("tool_name"), field="hook tool name"),
            tool_input=tool_input,
            command=_optional_bounded_text((tool_input or {}).get("command"), field="hook command"),
            approval_request=(
                {"hook": hook_name} if hook_name in {"PreToolUse", "PermissionRequest"} else None
            ),
            metadata={"hook_event_name": hook_name, "source": "qwen_hook"},
        )

    def hook_response(
        self, session: HarnessSession, payload: dict, intervention: Intervention | None
    ) -> dict:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.QWEN
        ):
            return {}
        raw_hook_name = payload.get("hook_event_name")
        if not isinstance(raw_hook_name, str):
            return {}
        try:
            hook_name = bounded_adapter_id(raw_hook_name, field="Qwen hook name")
        except ValueError:
            return {}
        if hook_name == "PreToolUse":
            if not self._hook_live() or self._active_hook.get() != (session.id, hook_name):
                return {}
            self._active_hook.set(None)
            decision = verified_inline_permission_outcome(
                session,
                intervention,
                expected_trigger=EventType.TOOL_CALL,
                expected_request_id=_event_id(session.id, payload, source="hook"),
            )
            if decision == "ask":
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "ask",
                        "permissionDecisionReason": (
                            _bounded_response_text(
                                intervention.diagnosis or "PEX requested human review"
                            )
                        ),
                    }
                }
            if decision not in {"allow", "deny"}:
                return {}
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": _bounded_response_text(
                        intervention.diagnosis or f"PEX policy {decision}"
                    ),
                }
            }
        if hook_name == "PermissionRequest":
            if not self._hook_live() or self._active_hook.get() != (session.id, hook_name):
                return {}
            self._active_hook.set(None)
            behavior = verified_inline_permission_outcome(
                session,
                intervention,
                expected_trigger=EventType.PERMISSION_REQUEST,
                expected_request_id=_event_id(session.id, payload, source="hook"),
            )
            if behavior not in {"allow", "deny"}:
                return {}
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": behavior},
                }
            }
        if hook_name == "Stop":
            active_hook = self._active_hook.get()
            self._active_hook.set(None)
            followup = self._pending_followups.pop(session.id, None)
            if _evidenced_stop_delivery(session, active_hook, followup, intervention):
                cleaned = str(followup).strip()
                return {"decision": "block", "reason": cleaned}
        # An escalation record is not authority to reject a user's submitted
        # prompt. Only the verified permission and Stop paths control Qwen.
        return {}

    def emit_status(self, session: HarnessSession, message: str) -> HarnessEvent:
        return HarnessEvent(
            event_id=_event_id(session.id, {"status": message}, source="hook"),
            ts=datetime.now(UTC),
            harness_type=HarnessType.QWEN,
            session_id=session.id,
            event_type=EventType.STATUS,
            message_delta=message,
        )

    def _vendor_id(self, payload: dict) -> str | None:
        explicit_ids: list[str] = []
        for key in ("sessionID", "sessionId", "session_id", "id"):
            value = payload.get(key)
            if isinstance(value, str) and value and not value.startswith("evt_"):
                if key == "id":
                    continue
                try:
                    explicit_ids.append(bounded_adapter_id(value, field="Qwen session id"))
                except ValueError:
                    return None
        props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
        for key in ("sessionID", "sessionId", "session_id"):
            value = props.get(key)
            if isinstance(value, str) and value:
                try:
                    explicit_ids.append(bounded_adapter_id(value, field="Qwen session id"))
                except ValueError:
                    return None
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        for key in ("sessionID", "sessionId", "session_id"):
            value = data.get(key)
            if isinstance(value, str) and value:
                try:
                    explicit_ids.append(bounded_adapter_id(value, field="Qwen session id"))
                except ValueError:
                    return None
        raw_source_path = payload.get("_pex_sse_path")
        source_path = raw_source_path if isinstance(raw_source_path, str) else ""
        route = source_path.split("?", 1)[0].strip("/").split("/")
        source_id: str | None = None
        if len(route) == 3 and route[0] == "session" and route[2] == "events":
            try:
                source_id = bounded_adapter_id(unquote(route[1]), field="Qwen SSE session id")
            except ValueError:
                return None
        if source_id is not None:
            if any(item != source_id for item in explicit_ids):
                return None
            return source_id
        if not explicit_ids or any(item != explicit_ids[0] for item in explicit_ids[1:]):
            return None
        return explicit_ids[0]

    def _session_for(self, payload: dict) -> HarnessSession | None:
        vendor_id = self._vendor_id(payload)
        if not vendor_id:
            return None
        session_id = f"qwen:{vendor_id}"
        existing = self.sessions.get(session_id)
        if existing:
            return existing
        # A stream frame may identify a session, but only workspace-scoped
        # discovery establishes its project binding.
        return None

    def normalize_sse(self, session: HarnessSession, payload: dict) -> HarnessEvent:
        payload_vendor_id = self._vendor_id(payload)
        if payload_vendor_id != session.vendor_session_id:
            raise ValueError("Qwen SSE session binding mismatch")
        bound = self.sessions.get(session.id)
        if bound is not None and not session_binding_matches(
            bound, session, harness_type=HarnessType.QWEN
        ):
            raise ValueError("Qwen SSE canonical session mismatch")
        if bound is not None:
            session = bound
        raw_kind = payload.get("type") or payload.get("event") or "status"
        kind = bounded_adapter_id(raw_kind, field="Qwen SSE event type")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        raw_update = data.get("sessionUpdate")
        update = (
            bounded_adapter_id(raw_update, field="Qwen session update")
            if isinstance(raw_update, str) and raw_update
            else ""
        )
        content = data.get("content") if isinstance(data.get("content"), dict) else {}
        event_type = EventType.STATUS
        phase = EventPhase.AFTER
        if kind == "permission_request":
            event_type = EventType.PERMISSION_REQUEST
            phase = EventPhase.BEFORE
        elif kind == "turn_complete":
            event_type = EventType.STOP
            phase = EventPhase.TERMINAL
        elif kind in {"turn_error", "session_died"}:
            event_type = EventType.ERROR
            phase = EventPhase.TERMINAL
        elif kind == "session_closed":
            event_type = EventType.SESSION_END
            phase = EventPhase.TERMINAL
        elif kind == "session_update":
            if update == "agent_message_chunk":
                event_type = EventType.AGENT_RESPONSE
            elif update == "agent_thought_chunk":
                event_type = EventType.AGENT_THOUGHT
            elif update.startswith("tool_call"):
                event_type = (
                    EventType.TOOL_RESULT
                    if (
                        bounded_adapter_id(data.get("status"), field="Qwen tool status").lower()
                        if isinstance(data.get("status"), str) and data.get("status")
                        else ""
                    )
                    in {"completed", "failed"}
                    else EventType.TOOL_CALL
                )
        text = (
            content.get("text")
            or data.get("message")
            or data.get("error")
            or data.get("stopReason")
            or update
            or kind
        )
        try:
            request_id = (
                bounded_adapter_id(data.get("requestId"), field="permission request id")
                if data.get("requestId")
                else ""
            )
        except ValueError:
            request_id = ""
        raw_options = data.get("options") if isinstance(data.get("options"), list) else []
        options = [
            _bounded_permission_option(option)
            for option in raw_options[:MAX_PERMISSION_OPTIONS]
            if isinstance(option, dict)
            and isinstance(option.get("optionId"), str)
            and option.get("optionId", "").strip()
        ]
        if kind == "permission_request" and request_id:
            prior_owner = self._permission_request_owners.get(request_id)
            if prior_owner and prior_owner != session.id:
                self._permission_options.pop((prior_owner, request_id), None)
                self._permission_request_owners[request_id] = "__ambiguous__"
            elif len(self._permission_options) < MAX_PERMISSION_REQUESTS:
                self._permission_options[(session.id, request_id)] = options
                self._permission_request_owners[request_id] = session.id
        elif kind == "permission_resolved" and request_id:
            self._permission_options.pop((session.id, request_id), None)
            if self._permission_request_owners.get(request_id) == session.id:
                self._permission_request_owners.pop(request_id, None)
        try:
            prompt_id = (
                bounded_adapter_id(data.get("promptId"), field="Qwen prompt id")
                if data.get("promptId")
                else ""
            )
        except ValueError:
            prompt_id = ""
        expected_prompt_id = self._active_prompt_ids.get(session.id)
        if kind in {"turn_complete", "turn_error"} and expected_prompt_id:
            if not prompt_id or prompt_id != expected_prompt_id:
                event_type = EventType.STATUS
                phase = EventPhase.AFTER
                text = "Ignored terminal event for a different Qwen prompt"
            else:
                self._active_prompt_ids.pop(session.id, None)
                self._active_prompt_started_at.pop(session.id, None)
        elif kind in {"session_died", "session_closed"}:
            self._active_prompt_ids.pop(session.id, None)
            self._active_prompt_started_at.pop(session.id, None)
        tool_call = data.get("toolCall") if isinstance(data.get("toolCall"), dict) else {}
        return HarnessEvent(
            event_id=_event_id(session.id, payload, source="sse"),
            ts=datetime.now(UTC),
            harness_type=HarnessType.QWEN,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=phase,
            message_delta=_optional_bounded_text(text, field="SSE message"),
            tool_name=_optional_bounded_text(tool_call.get("name"), field="SSE tool name"),
            tool_input=bounded_observed_mapping(tool_call.get("input")),
            approval_request=(
                {"request_id": request_id, "options": options}
                if kind == "permission_request" and request_id
                else None
            ),
            error=_optional_bounded_text(data.get("error"), field="SSE error"),
            metadata={
                "sse_type": kind,
                "session_update": update or None,
                "prompt_id": prompt_id or None,
                "replay": bool(payload.get("_replay", False)),
            },
        )

    async def pump_into_pipeline(self, ingest) -> None:
        seen = 0
        active_transport: HttpJsonTransport | None = None
        next_discovery = 0.0
        while True:
            try:
                transport = self.transport
                if transport is None:
                    await asyncio.sleep(0.25)
                    continue
                if transport is not active_transport:
                    active_transport = transport
                    seen = 0
                    next_discovery = 0.0
                    self._event_gap_detected = False
                now = time.monotonic()
                if now >= next_discovery:
                    await self.discover_sessions()
                    next_discovery = now + self.session_discovery_interval_seconds
                ensure = getattr(transport, "ensure_sse", None)
                if ensure is not None:
                    for session in self.sessions.values():
                        if session.vendor_session_id:
                            await ensure(
                                f"/session/{quote(session.vendor_session_id, safe='')}/events"
                            )
                next_seen, events, dropped = transport_events_since(transport, seen)
                if dropped:
                    self._event_gap_detected = True
                for payload in events:
                    if not isinstance(payload, dict):
                        continue
                    kind = payload.get("type") if isinstance(payload.get("type"), str) else ""
                    if kind in {"server.connected", "server.heartbeat"}:
                        continue
                    session = self._session_for(payload)
                    if session is None:
                        continue
                    event = self.normalize_sse(session, payload)
                    await ingest(event, session)
                seen = next_seen
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
            name="qwen-pipeline-pump",
        )
        return self._pump_task


def _evidenced_stop_delivery(
    session: HarnessSession,
    active_hook: tuple[str, str] | None,
    followup: str | None,
    intervention: Intervention | None,
) -> bool:
    """Emit a Stop block only for this hook's completed, auditable delivery."""
    cleaned = str(followup or "").strip()
    if (
        active_hook != (session.id, "Stop")
        or not cleaned
        or cleaned.startswith("PEX:")
        or intervention is None
        or intervention.session_id != session.id
        or intervention.trigger != EventType.STOP.value
        or intervention.policy_verdict != PolicyVerdict.ALLOW
        or not any(str(item).strip() for item in intervention.evidence)
    ):
        return False
    action = intervention.proposed_action
    action_name = str(intervention.action_taken or "")
    expected_results = {
        "SEND_NUDGE": "sent",
        "INJECT_CONTEXT": "sent",
        "CONTINUE_SESSION": "continued",
        "REQUEST_VERIFICATION": "verification_requested",
    }
    return (
        action_name in expected_results
        and action.type.value == action_name
        and action.session_id == session.id
        and intervention.result == expected_results[action_name]
        and str(action.payload.get("text") or "").strip() == cleaned
    )


def _permission_outcome(options: list[dict], decision: str) -> dict | None:
    normalized = str(decision or "").strip().lower()
    if normalized == "deny":
        for option in options:
            option_id = str(option.get("optionId") or "")
            if option_id and option.get("kind") == "reject_once":
                return {"outcome": "selected", "optionId": option_id}
        deny_terms = ("deny", "reject", "cancel", "decline", "abort")
        for option in options:
            option_id = str(option.get("optionId") or "")
            label = str(option.get("name") or option.get("label") or "")
            haystack = f"{option_id} {label}".lower()
            if (
                option_id
                and "always" not in haystack
                and option.get("kind") in {None, "", "reject_once"}
                and any(term in haystack for term in deny_terms)
            ):
                return {"outcome": "selected", "optionId": option_id}
        return {"outcome": "cancelled"}
    if normalized != "allow":
        return None
    for option in options:
        option_id = str(option.get("optionId") or "")
        if option_id and option.get("kind") == "allow_once":
            return {"outcome": "selected", "optionId": option_id}
    allow_terms = ("allow", "approve", "proceed", "accept", "yes")
    one_time_terms = ("once", "one_time", "one-time", "this time", "proceed_once")
    for option in options:
        option_id = str(option.get("optionId") or "")
        label = str(option.get("name") or option.get("label") or "")
        haystack = f"{option_id} {label}".lower()
        if (
            option_id
            and "always" not in haystack
            and option.get("kind") in {None, "", "allow_once"}
            and any(term in haystack for term in allow_terms)
            and any(term in haystack for term in one_time_terms)
        ):
            return {"outcome": "selected", "optionId": option_id}
    return None


def _absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _event_id(session_id: str, payload: dict, *, source: str) -> str:
    canonical = strict_json_dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"{session_id}:{source}:{digest}"


def _optional_bounded_text(value: object, *, field: str) -> str | None:
    return bounded_observed_text(value, field=field, max_chars=MAX_ADAPTER_MESSAGE_CHARS)


def _optional_bounded_path(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return None
    path = bounded_adapter_text(value, field="path", max_chars=MAX_PATH_CHARS)
    if not _absolute_path(path):
        raise ValueError("Qwen project path must be absolute")
    return path


def _bounded_response_text(value: object) -> str:
    return bounded_observed_text(value, field="hook response", max_chars=4_096) or "PEX policy"


def _bounded_permission_option(option: dict) -> dict:
    result: dict[str, str] = {}
    for key in ("optionId", "name", "label", "kind"):
        value = option.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            text = bounded_adapter_id(value, field=f"Qwen permission {key}")
        except ValueError:
            continue
        result[key] = text
    return result


def _permission_voting_available(
    transport: HttpJsonTransport | None, daemon: dict, features: set[str]
) -> bool:
    if not {"session_permission_vote", "permission_vote"}.intersection(features):
        return False
    policy_block = daemon.get("policy")
    policy = (
        str(policy_block.get("permission") or "first-responder")
        if isinstance(policy_block, dict)
        else "first-responder"
    )
    if policy == "first-responder":
        return True
    if policy != "local-only":
        # designated/consensus require a registered X-Qwen-Client-Id and
        # originator/quorum tracking, which this adapter does not implement.
        return False
    base_url = str(getattr(transport, "base_url", "") or "")
    if not base_url:
        return isinstance(transport, MemoryHttpTransport)
    return urlparse(base_url).hostname in {"127.0.0.1", "localhost", "::1"}
