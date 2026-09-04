"""OpenCode via official `opencode serve` HTTP API.

Deep only after the server session probe succeeds and the global SSE stream is
actually connected. The in-process transport is a test double, not live proof.
We do not scrape the TUI.
"""

from __future__ import annotations

import asyncio
import hashlib
import ntpath
from datetime import UTC, datetime
from time import monotonic
from urllib.parse import quote
from uuid import uuid4

from pex_protocol.capabilities import (
    AdapterCapabilities,
    AdapterSupportLabel,
    ControlGranularity,
    PermissionResponseMode,
)
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
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
)
from pex_bridge.adapters.desktop import (
    is_desktop_observe_session,
    matching_desktop_image,
    upsert_desktop_observe_session,
)
from pex_bridge.adapters.http_json import HttpJsonTransport, transport_events_since
from pex_bridge.adapters.strict_json import strict_json_dumps

OPENCODE_DESKTOP_IMAGES = ("OpenCode.exe", "opencode.exe")

PLUGIN_HEARTBEAT_TTL_SECONDS = 30.0
_OVERLAY_METADATA_KEYS = {"phase", "pin", "fingerprint_overlay"}
MAX_TRACKED_SESSIONS = 1_024
MAX_INBOX_MESSAGES = 1_000
MAX_HOOK_RECEIPTS = 10_000
MAX_PERMISSION_REQUESTS = 10_000
MAX_MESSAGE_ROLES = 10_000
MAX_PATH_CHARS = 4_096
PROMPT_RECEIPT_POLL_ATTEMPTS = 10
PROMPT_RECEIPT_POLL_SECONDS = 0.1


class OpenCodeAdapter(HarnessAdapter):
    name = "opencode"

    def __init__(self, transport: HttpJsonTransport | None = None) -> None:
        self.transport = transport
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []
        self._pump_task: asyncio.Task | None = None
        self._plugin_seen_at: float | None = None
        self._plugin_sessions_seen_at: dict[str, float] = {}
        self._permission_requests: set[tuple[str, str]] = set()
        self._message_roles: dict[tuple[str, str], str] = {}
        self._message_send_locks: dict[str, asyncio.Lock] = {}
        self._last_pump_error: str | None = None
        self._event_gap_detected = False

    def attach_transport(self, transport: HttpJsonTransport) -> None:
        if (
            self.transport is not None
            and self.transport is not transport
            and self._pump_task is not None
            and not self._pump_task.done()
        ):
            raise RuntimeError("detach the active OpenCode transport before replacing it")
        self.transport = transport

    def _pumping(self) -> bool:
        task = self._pump_task
        return task is not None and not task.done()

    def _events_connected(self) -> bool:
        paths = getattr(self.transport, "connected_sse_paths", set())
        return isinstance(paths, set) and "/global/event" in paths

    def mark_plugin_heartbeat(self, session_id: str | None = None) -> None:
        seen_at = monotonic()
        self._plugin_seen_at = seen_at
        if session_id:
            bounded = bounded_adapter_id(session_id, field="OpenCode plugin session id")
            if not bounded.startswith("opencode:"):
                bounded = f"opencode:{bounded}"
            if (
                len(self._plugin_sessions_seen_at) >= MAX_TRACKED_SESSIONS
                and bounded not in self._plugin_sessions_seen_at
            ):
                raise ValueError("OpenCode plugin session heartbeat bound reached")
            self._plugin_sessions_seen_at[bounded] = seen_at

    def _plugin_live(self, session_id: str | None = None) -> bool:
        seen = (
            self._plugin_sessions_seen_at.get(session_id)
            if session_id is not None
            else self._plugin_seen_at
        )
        return seen is not None and monotonic() - seen <= PLUGIN_HEARTBEAT_TTL_SECONDS

    def overlay_projection_ready(self, session: HarnessSession) -> bool:
        return bool(
            self._plugin_live(session.id)
            and session.harness_type == HarnessType.OPENCODE
            and session.id == f"opencode:{session.vendor_session_id}"
            and session_binding_matches(
                self.sessions.get(session.id),
                session,
                harness_type=HarnessType.OPENCODE,
            )
        )

    @staticmethod
    def _scoped_path(path: str, directory: str | None) -> str:
        if not directory:
            return path
        separator = "&" if "?" in path else "?"
        return f"{path}{separator}directory={quote(directory, safe='')}"

    async def probe(self) -> AdapterCapabilities:
        connected = False
        if self.transport is not None:
            try:
                listed = await self.transport.request("GET", "/session")
                connected = isinstance(listed, list)
            except Exception:
                connected = False
        deep = (
            connected
            and self._pumping()
            and self._events_connected()
            and not self._event_gap_detected
            and self._last_pump_error is None
        )
        plugin_live = self._plugin_live()
        desktop = matching_desktop_image(OPENCODE_DESKTOP_IMAGES) is not None
        return AdapterCapabilities(
            observe_messages=deep,
            observe_tool_calls=deep,
            observe_session_status=connected or desktop,
            observe_file_edits=deep,
            observe_permissions=deep,
            send_message=connected,
            inject_context=connected,
            approve=deep,
            deny=deep,
            permission_response_mode=(
                PermissionResponseMode.ASYNC if deep else PermissionResponseMode.NONE
            ),
            start=False,
            resume=connected,
            fork=connected,
            modify_config=plugin_live,
            modify_system_instructions=plugin_live,
            modify_tools=plugin_live,
            modify_permissions=False,
            config_scope="session" if plugin_live else "none",
            focus_ui=desktop,
            control_granularity=(ControlGranularity.EVENT if deep else ControlGranularity.SESSION),
            trust_level=(
                0.9
                if deep
                else 0.72
                if connected
                else 0.65
                if plugin_live
                else 0.4
                if desktop
                else 0.0
            ),
            support_label=(
                AdapterSupportLabel.DEEP
                if deep
                else AdapterSupportLabel.STRONG
                if connected
                else AdapterSupportLabel.BASIC
                if plugin_live
                else AdapterSupportLabel.OBSERVE_ONLY
                if desktop
                else AdapterSupportLabel.UNAVAILABLE
            ),
            notes=(
                "Official surface: `opencode serve` HTTP+SSE "
                "(GET /session, POST /session/:id/prompt_async, "
                "POST /session/:id/fork, and "
                "POST /session/:id/permissions/:id). Project-persistent PATCH /config "
                "is deliberately not used for ephemeral overlays. A recent PEX plugin "
                "heartbeat enables session-scoped system/tool overlays. OpenCode's "
                "declared permission.ask plugin hook is not invoked by the current "
                "runtime, so permission overlays stay disabled. "
                + (
                    "SSE pump running."
                    if deep
                    else "SSE retention gap detected; observation is incomplete."
                    if self._event_gap_detected
                    else "Health probe passed; Strong until the SSE pump is started."
                    if connected
                    else "PEX OpenCode plugin is live; HTTP server control is detached."
                    if plugin_live
                    else "An OpenCode desktop/TUI is running; listing it does not spawn serve."
                    if desktop
                    else "No healthy live server; label stays Unavailable."
                )
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.transport is None:
            upsert_desktop_observe_session(
                self.sessions,
                harness=HarnessType.OPENCODE,
                process=OPENCODE_DESKTOP_IMAGES,
                skip_if_other_sessions=True,
            )
            return list(self.sessions.values())
        listed = await self.transport.request("GET", "/session")
        if not isinstance(listed, list):
            raise RuntimeError("OpenCode session listing returned a malformed response")
        known_directories: list[str] = []
        seen_directories: set[str] = set()
        for existing in self.sessions.values():
            if (
                is_desktop_observe_session(existing)
                or not existing.cwd
                or existing.cwd in seen_directories
            ):
                continue
            seen_directories.add(existing.cwd)
            known_directories.append(existing.cwd)
            if len(known_directories) >= 32:
                break
        merged: list[object] = list(listed)
        for directory in known_directories:
            try:
                extra = await self.transport.request(
                    "GET", self._scoped_path("/session", directory)
                )
            except Exception:
                continue
            if not isinstance(extra, list):
                continue
            merged.extend(extra)
        if len(merged) > MAX_TRACKED_SESSIONS:
            raise RuntimeError("OpenCode session listing exceeded the safety bound")
        for item in merged:
            if not isinstance(item, dict):
                continue
            try:
                vendor_id = bounded_adapter_id(item.get("id") or "", field="OpenCode session id")
            except ValueError:
                continue
            session_id = f"opencode:{vendor_id}"
            existing = self.sessions.get(session_id)
            cwd = _optional_bounded_path(item.get("cwd") or item.get("directory"))
            goal_id, paused = preserve_bridge_state(
                existing,
                cwd=cwd,
                project_id=cwd,
            )
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.OPENCODE,
                vendor_session_id=vendor_id,
                cwd=cwd,
                project_id=cwd,
                status=SessionStatus.WORKING if existing else SessionStatus.DISCOVERED,
                last_activity=datetime.now(UTC),
                goal_id=goal_id,
                supervision_paused=paused,
                metadata={
                    "title": bounded_observed_text(
                        item.get("title"), field="OpenCode session title"
                    )
                },
            )
        upsert_desktop_observe_session(
            self.sessions,
            harness=HarnessType.OPENCODE,
            process=OPENCODE_DESKTOP_IMAGES,
            skip_if_other_sessions=True,
        )
        return list(self.sessions.values())

    async def focus_ui(self, session: HarnessSession) -> bool:
        from pex_bridge.adapters.winfocus import focus_harness

        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.OPENCODE
        ):
            return False
        return focus_harness("opencode")

    async def send_message(
        self, session: HarnessSession, text: str, attachments=None
    ) -> bool | AdapterMessageResult:
        if not self._message_session_is_bound(session, self.sessions.get(session.id)):
            return False
        lock = self._message_send_locks.get(session.id)
        if lock is None:
            if len(self._message_send_locks) >= MAX_TRACKED_SESSIONS:
                return False
            lock = asyncio.Lock()
            self._message_send_locks[session.id] = lock
        async with lock:
            return await self._send_message_locked(session, text)

    async def _send_message_locked(
        self, session: HarnessSession, text: str
    ) -> bool | AdapterMessageResult:
        bound = self.sessions.get(session.id)
        if not self._message_session_is_bound(session, bound):
            return False
        try:
            cleaned = bounded_adapter_text(text).strip()
        except ValueError:
            return False
        session = bound
        inbox = self.inbox.setdefault(session.id, [])
        if len(inbox) >= MAX_INBOX_MESSAGES:
            return False
        prior_message_ids = await self._user_message_ids(session)
        try:
            await self.transport.request(
                "POST",
                self._scoped_path(
                    f"/session/{quote(session.vendor_session_id, safe='')}/prompt_async",
                    session.cwd,
                ),
                json={"parts": [{"type": "text", "text": cleaned}]},
            )
        except DeliveryUncertainError:
            raise
        except Exception:
            return False
        inbox.append(cleaned)
        turn_id = await self._new_prompt_turn_id(
            session,
            cleaned,
            prior_message_ids=prior_message_ids,
        )
        if turn_id is None:
            return True
        return AdapterMessageResult(
            accepted=True,
            vendor_session_id=session.vendor_session_id,
            vendor_turn_id=turn_id,
        )

    def _message_session_is_bound(
        self,
        session: HarnessSession,
        bound: HarnessSession | None,
    ) -> bool:
        return bool(
            self.transport is not None
            and session_binding_matches(
                bound, session, harness_type=HarnessType.OPENCODE
            )
            and not is_desktop_observe_session(session)
            and not is_desktop_observe_session(bound)
            and bound is not None
            and bound.cwd
            and bound.project_id
            and session.id == f"opencode:{session.vendor_session_id}"
        )

    async def _messages(self, session: HarnessSession) -> list[dict] | None:
        if self.transport is None:
            return None
        try:
            listed = await self.transport.request(
                "GET",
                self._scoped_path(
                    f"/session/{quote(session.vendor_session_id, safe='')}/message",
                    session.cwd,
                ),
            )
        except Exception:
            return None
        if not isinstance(listed, list):
            return None
        return [item for item in listed if isinstance(item, dict)]

    async def _user_message_ids(self, session: HarnessSession) -> set[str] | None:
        listed = await self._messages(session)
        if listed is None:
            return None
        ids: set[str] = set()
        for item in listed:
            info = item.get("info")
            if not isinstance(info, dict) or info.get("role") != "user":
                continue
            try:
                message_id = bounded_adapter_id(
                    info.get("id") or "", field="OpenCode message id"
                )
            except ValueError:
                continue
            ids.add(message_id)
        return ids

    async def _new_prompt_turn_id(
        self,
        session: HarnessSession,
        cleaned: str,
        *,
        prior_message_ids: set[str] | None,
    ) -> str | None:
        if prior_message_ids is None:
            return None
        for attempt in range(PROMPT_RECEIPT_POLL_ATTEMPTS):
            listed = await self._messages(session)
            if listed is None:
                return None
            turn_id = self._matching_new_prompt_id(
                listed,
                cleaned,
                prior_message_ids=prior_message_ids,
                vendor_session_id=session.vendor_session_id,
            )
            if turn_id is not None:
                return turn_id
            if attempt + 1 < PROMPT_RECEIPT_POLL_ATTEMPTS:
                await asyncio.sleep(PROMPT_RECEIPT_POLL_SECONDS)
        return None

    @staticmethod
    def _matching_new_prompt_id(
        listed: list[dict],
        cleaned: str,
        *,
        prior_message_ids: set[str],
        vendor_session_id: str,
    ) -> str | None:
        candidates: set[str] = set()
        for item in reversed(listed):
            info = item.get("info")
            if not isinstance(info, dict) or info.get("role") != "user":
                continue
            if info.get("sessionID") != vendor_session_id:
                continue
            parts = item.get("parts")
            texts = [
                str(part.get("text") or "")
                for part in parts
                if isinstance(part, dict) and part.get("type") == "text"
            ] if isinstance(parts, list) else []
            if cleaned not in texts:
                continue
            try:
                message_id = bounded_adapter_id(
                    info.get("id") or "", field="OpenCode message id"
                )
            except ValueError:
                continue
            if message_id not in prior_message_ids:
                candidates.add(message_id)
        if len(candidates) != 1:
            return None
        return next(iter(candidates))

    async def fork_or_fresh_handoff(self, session: HarnessSession, context_bundle):
        bound = self.sessions.get(session.id)
        if (
            self.transport is None
            or not session_binding_matches(
                bound, session, harness_type=HarnessType.OPENCODE
            )
            or not bound.cwd
            or not bound.project_id
            or session.id != f"opencode:{session.vendor_session_id}"
        ):
            return None
        if len(self.sessions) >= MAX_TRACKED_SESSIONS:
            return None
        try:
            created = await self.transport.request(
                "POST",
                self._scoped_path(
                    f"/session/{quote(session.vendor_session_id, safe='')}/fork",
                    bound.cwd,
                ),
                json={},
            )
        except DeliveryUncertainError:
            raise
        except Exception:
            return None
        if not isinstance(created, dict):
            return None
        try:
            vendor_id = bounded_adapter_id(
                created.get("id") or "", field="OpenCode session id"
            )
        except ValueError:
            return None
        child_id = f"opencode:{vendor_id}"
        if child_id == bound.id or child_id in self.sessions:
            return None
        cwd = _optional_bounded_path(created.get("cwd") or created.get("directory"))
        if cwd and bound.cwd and not _same_path(cwd, bound.cwd):
            cwd = bound.cwd
        if not cwd:
            cwd = bound.cwd
        child = HarnessSession(
            id=child_id,
            harness_type=HarnessType.OPENCODE,
            vendor_session_id=vendor_id,
            cwd=cwd,
            project_id=bound.project_id,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
            goal_id=bound.goal_id,
            metadata={
                "title": bounded_observed_text(
                    created.get("title"), field="OpenCode session title"
                ),
                "source": "pex_lifecycle",
                "forked_from": bound.id,
                "probe": True,
            },
        )
        self.sessions[child_id] = child
        try:
            delivered = await self.inject_context(child, context_bundle)
        except DeliveryUncertainError:
            self.sessions.pop(child_id, None)
            raise
        except Exception:
            self.sessions.pop(child_id, None)
            return None
        if not delivered:
            self.sessions.pop(child_id, None)
            return None
        return child

    async def respond_permission(
        self, session: HarnessSession, request_id: str, decision: str
    ) -> bool:
        try:
            request_id = bounded_adapter_id(request_id, field="permission request id")
        except ValueError:
            return False
        bound = self.sessions.get(session.id)
        if (
            self.transport is None
            or not session_binding_matches(
                bound, session, harness_type=HarnessType.OPENCODE
            )
            or not bound.cwd
            or not bound.project_id
            or session.id != f"opencode:{session.vendor_session_id}"
            or (session.id, request_id) not in self._permission_requests
        ):
            return False
        if decision not in {"allow", "once", "deny"}:
            return False
        response = (
            "once" if decision in {"allow", "once"} else "reject"
        )
        session = bound
        try:
            await self.transport.request(
                "POST",
                self._scoped_path(
                    f"/session/{quote(session.vendor_session_id, safe='')}/permissions/"
                    f"{quote(request_id, safe='')}",
                    session.cwd,
                ),
                json={"response": response},
            )
        except DeliveryUncertainError:
            raise
        except Exception:
            return False
        self._permission_requests.discard((session.id, request_id))
        return True

    async def apply_overlay(self, session: HarnessSession, overlay) -> bool:
        if (
            not self.overlay_projection_ready(session)
            or overlay.scope != "session"
            or overlay.session_id != session.id
            or session.harness_type != HarnessType.OPENCODE
            or session.id != f"opencode:{session.vendor_session_id}"
            or not session_binding_matches(
                self.sessions.get(session.id), session, harness_type=HarnessType.OPENCODE
            )
        ):
            return False
        diff = overlay.diff
        if any(
            value is not None
            for value in (
                diff.tools_enabled,
                diff.mcp_servers,
                diff.model,
                diff.reasoning_effort,
                diff.permission_policy,
            )
        ):
            return False
        if set(diff.extra) - _OVERLAY_METADATA_KEYS:
            return False
        has_effect = bool(
            (diff.system_instructions or "").strip()
            or diff.tools_disabled
            or any(str(diff.extra.get(key) or "").strip() for key in _OVERLAY_METADATA_KEYS)
        )
        if not has_effect:
            return False
        overlay.rollback.update(
            {
                "adapter": self.name,
                "operation": "revert_overlay",
                "overlay_id": overlay.id,
                "strategy": "bridge_active_overlay_query",
                "scope": "session",
                "plugin": "pex-opencode-plugin",
                "session_id": session.id,
            }
        )
        return True

    async def revert_overlay(self, overlay_id: str, rollback: dict | None = None) -> bool:
        # The plugin reads active overlays from the durable bridge store on each
        # affected hook. Reversion is the atomic store transition performed by
        # the executor; no persistent OpenCode config was changed.
        return bool(
            self._plugin_live(str((rollback or {}).get("session_id") or ""))
            and rollback
            and rollback.get("adapter") == self.name
            and rollback.get("overlay_id") == overlay_id
            and rollback.get("strategy") == "bridge_active_overlay_query"
            and rollback.get("scope") == "session"
        )

    def ingest_hook(self, payload: dict) -> HarnessSession:
        vendor_id = bounded_adapter_id(
            payload.get("session_id") or "",
            field="OpenCode session_id",
        )
        session_id = f"opencode:{vendor_id}"
        if payload.get("source") == "pex-opencode-plugin":
            self.mark_plugin_heartbeat(session_id)
        existing = self.sessions.get(session_id)
        cwd = _optional_bounded_path(payload.get("cwd"))
        if existing is None and len(self.sessions) >= MAX_TRACKED_SESSIONS:
            raise ValueError("OpenCode session safety bound reached")
        goal_id, paused = preserve_bridge_state(
            existing,
            cwd=cwd,
            project_id=cwd,
        )
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.OPENCODE,
            vendor_session_id=vendor_id,
            cwd=cwd,
            project_id=cwd,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
            goal_id=goal_id,
            supervision_paused=paused,
        )
        self.sessions[session_id] = session
        if len(self.hooks) >= MAX_HOOK_RECEIPTS:
            del self.hooks[: len(self.hooks) - MAX_HOOK_RECEIPTS + 1]
        self.hooks.append(
            {
                "session_id": session_id,
                "source": bounded_observed_text(
                    payload.get("source"), field="OpenCode hook source", max_chars=512
                ),
                "received_at": datetime.now(UTC).isoformat(),
            }
        )
        return session

    def emit_status(self, session: HarnessSession, message: str) -> HarnessEvent:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.OPENCODE
        ):
            raise ValueError("OpenCode status session binding mismatch")
        return HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(UTC),
            harness_type=HarnessType.OPENCODE,
            session_id=session.id,
            event_type=EventType.STATUS,
            message_delta=bounded_adapter_text(message, field="status message"),
        )

    def _cwd(self, payload: dict) -> str | None:
        props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
        info = props.get("info") if isinstance(props.get("info"), dict) else {}
        path = info.get("path") if isinstance(info.get("path"), dict) else {}
        for blob in (payload, props, info, path):
            if not isinstance(blob, dict):
                continue
            for key in ("cwd", "directory", "workspace", "_pex_directory"):
                value = blob.get(key)
                if isinstance(value, str) and value:
                    try:
                        return _optional_bounded_path(value)
                    except ValueError:
                        return None
        return None

    def _vendor_id(self, payload: dict) -> str | None:
        props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
        info = props.get("info") if isinstance(props.get("info"), dict) else {}
        part = props.get("part") if isinstance(props.get("part"), dict) else {}
        candidates: list[str] = []
        for blob in (payload, props, info, part):
            for key in ("sessionID", "sessionId", "session_id"):
                value = blob.get(key) if isinstance(blob, dict) else None
                if isinstance(value, str) and value.strip():
                    try:
                        candidates.append(
                            bounded_adapter_id(value, field="OpenCode session id")
                        )
                    except ValueError:
                        return None
        if not candidates or any(item != candidates[0] for item in candidates[1:]):
            return None
        return candidates[0]

    def _session_for(self, payload: dict) -> HarnessSession | None:
        vendor_id = self._vendor_id(payload)
        if not vendor_id:
            return None
        session_id = f"opencode:{vendor_id}"
        existing = self.sessions.get(session_id)
        cwd = self._cwd(payload)
        if existing:
            if cwd and existing.cwd and not _same_path(cwd, existing.cwd):
                return None
            if cwd and not existing.cwd:
                existing.goal_id = None
                existing.supervision_paused = False
                existing.cwd = cwd
                existing.project_id = cwd
            return existing
        if not cwd or len(self.sessions) >= MAX_TRACKED_SESSIONS:
            return None
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.OPENCODE,
            vendor_session_id=vendor_id,
            cwd=cwd,
            project_id=cwd,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
        )
        self.sessions[session_id] = session
        return session

    def normalize_sse(self, session: HarnessSession, payload: dict) -> HarnessEvent:
        canonical_id = f"opencode:{session.vendor_session_id}"
        payload_vendor_id = self._vendor_id(payload)
        if (
            session.harness_type != HarnessType.OPENCODE
            or session.id != canonical_id
            or payload_vendor_id != session.vendor_session_id
        ):
            raise ValueError("OpenCode SSE event/session identity mismatch")
        bound = self.sessions.get(session.id)
        if bound is not None and not session_binding_matches(
            bound, session, harness_type=HarnessType.OPENCODE
        ):
            raise ValueError("OpenCode SSE session binding changed")
        if bound is None:
            # The first authenticated/transport-observed event is sufficient to
            # establish the exact session binding used by later control calls.
            event_cwd = self._cwd(payload)
            if not session.cwd or not event_cwd or not _same_path(session.cwd, event_cwd):
                raise ValueError("OpenCode SSE project binding is unverified")
            session.project_id = session.cwd
            self.sessions[session.id] = session
        else:
            session = bound
        kind = bounded_adapter_id(
            payload.get("type") or payload.get("event") or "status",
            field="OpenCode SSE event type",
        )
        props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
        part = props.get("part") if isinstance(props.get("part"), dict) else {}
        info = props.get("info") if isinstance(props.get("info"), dict) else {}
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        raw_message_id = info.get("id") or part.get("messageID")
        message_id = (
            bounded_adapter_id(raw_message_id, field="OpenCode message id")
            if isinstance(raw_message_id, str) and raw_message_id
            else ""
        )
        raw_role = info.get("role")
        role = (
            bounded_adapter_id(raw_role, field="OpenCode message role").lower()
            if isinstance(raw_role, str) and raw_role
            else ""
        )
        if kind == "message.updated" and message_id and role:
            if len(self._message_roles) < MAX_MESSAGE_ROLES:
                self._message_roles[(session.id, message_id)] = role
        elif message_id:
            role = self._message_roles.get((session.id, message_id), "")
        mapping = {
            "message.updated": EventType.AGENT_RESPONSE,
            "message.part.updated": EventType.AGENT_RESPONSE,
            "session.idle": EventType.STOP,
            "session.deleted": EventType.SESSION_END,
            "permission.asked": EventType.PERMISSION_REQUEST,
            "permission.updated": EventType.PERMISSION_REQUEST,
            "permission.replied": EventType.STATUS,
            "file.edited": EventType.FILE_EDIT,
            "session.error": EventType.ERROR,
        }
        if kind == "message.part.updated" and part.get("type") == "reasoning":
            event_type = EventType.AGENT_THOUGHT
        elif kind == "message.part.updated" and part.get("type") == "tool":
            event_type = (
                EventType.TOOL_FAILURE
                if state.get("status") == "error"
                else EventType.TOOL_RESULT
                if state.get("status") == "completed"
                else EventType.TOOL_CALL
            )
        elif kind in {"message.updated", "message.part.updated"} and role == "user":
            event_type = EventType.USER_PROMPT
        else:
            event_type = mapping.get(kind, EventType.STATUS)
        text = (
            payload.get("text")
            or payload.get("message")
            or props.get("delta")
            or props.get("text")
            or part.get("text")
            or state.get("output")
            or state.get("error")
            or info.get("role")
            or kind
        )
        if isinstance(text, dict):
            text = text.get("text") or kind
        permission = kind in {"permission.asked", "permission.updated"}
        try:
            request_id = (
                bounded_adapter_id(
                    props.get("id")
                    or props.get("requestID")
                    or props.get("requestId")
                    or payload.get("id"),
                    field="permission request id",
                )
                if permission
                else ""
            )
        except ValueError:
            request_id = ""
        if permission and request_id and len(self._permission_requests) < MAX_PERMISSION_REQUESTS:
            self._permission_requests.add((session.id, request_id))
        elif kind == "permission.replied":
            raw_replied_id = (
                props.get("permissionID")
                or props.get("requestID")
                or props.get("requestId")
            )
            replied_id = (
                bounded_adapter_id(raw_replied_id, field="OpenCode permission id")
                if isinstance(raw_replied_id, str) and raw_replied_id
                else ""
            )
            if replied_id:
                self._permission_requests.discard((session.id, replied_id))
        tool_input = bounded_observed_mapping(state.get("input"))
        return HarnessEvent(
            event_id=_event_id(session.id, payload),
            ts=datetime.now(UTC),
            harness_type=HarnessType.OPENCODE,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=(
                EventPhase.TERMINAL
                if kind in {"session.idle", "session.deleted"}
                else EventPhase.BEFORE
                if permission
                else EventPhase.AFTER
            ),
            message_delta=_optional_bounded_text(text, field="SSE message"),
            tool_name=_optional_bounded_text(part.get("tool"), field="SSE tool name"),
            tool_input=tool_input,
            command=(
                _optional_bounded_text(tool_input.get("command"), field="SSE command")
                if tool_input is not None
                else None
            ),
            file_paths=[_bounded_path(props["file"])]
            if kind == "file.edited" and isinstance(props.get("file"), str) and props.get("file")
            else [],
            error=_optional_bounded_text(state.get("error"), field="SSE error"),
            approval_request={"request_id": request_id} if permission and request_id else None,
            metadata={"sse_type": kind},
        )

    async def pump_into_pipeline(self, ingest) -> None:
        seen = 0
        active_transport: HttpJsonTransport | None = None
        while True:
            try:
                transport = self.transport
                if transport is None:
                    await asyncio.sleep(0.25)
                    continue
                if transport is not active_transport:
                    active_transport = transport
                    seen = 0
                    self._event_gap_detected = False
                ensure = getattr(transport, "ensure_sse", None)
                if ensure is not None:
                    await ensure("/global/event")
                next_seen, events, dropped = transport_events_since(transport, seen)
                if dropped:
                    self._event_gap_detected = True
                for raw_payload in events:
                    payload = _unwrap_global_event(raw_payload)
                    if payload is None:
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
            name="opencode-pipeline-pump",
        )
        return self._pump_task


def _unwrap_global_event(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None
    nested = payload.get("payload")
    if not isinstance(nested, dict):
        return dict(payload)
    event = dict(nested)
    directory = payload.get("directory")
    if isinstance(directory, str) and directory:
        event.setdefault("_pex_directory", directory)
    if payload.get("_pex_sse_path"):
        event.setdefault("_pex_sse_path", payload["_pex_sse_path"])
    return event


def _event_id(session_id: str, payload: dict) -> str:
    canonical = strict_json_dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"{session_id}:sse:{digest}"


def _optional_bounded_text(value: object, *, field: str) -> str | None:
    return bounded_observed_text(value, field=field, max_chars=MAX_ADAPTER_MESSAGE_CHARS)


def _bounded_path(value: object) -> str:
    return bounded_adapter_text(value, field="path", max_chars=MAX_PATH_CHARS)


def _optional_bounded_path(value: object) -> str | None:
    if value is None or value == "":
        return None
    return _bounded_path(value)


def _same_path(left: str, right: str) -> bool:
    return ntpath.normcase(ntpath.normpath(left)) == ntpath.normcase(ntpath.normpath(right))
