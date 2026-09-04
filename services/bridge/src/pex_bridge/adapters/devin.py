"""Devin v3 Organization API. Granularity stays Basic even when attached.

Official: https://api.devin.ai/v3/organizations/{orgId}/sessions
Poll GET session until status is exit|error|suspended, then inspect.
POST .../messages to nudge. PEX does not pretend Devin exposes Cursor-grade tool telemetry.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import (
    MAX_ADAPTER_MESSAGE_CHARS,
    DeliveryUncertainError,
    HarnessAdapter,
    bounded_adapter_id,
    bounded_adapter_text,
    bounded_observed_text,
    preserve_bridge_state,
    session_binding_matches,
)
from pex_bridge.adapters.http_json import HttpJsonTransport
from pex_bridge.deep_links import devin_session_url

_TERMINAL = {"exit", "error", "suspended"}
_WAITING = {"waiting_for_user", "waiting_for_approval"}
_MAX_PAGES = 100
_POLL_INTERVAL_SECONDS = 10.0
_MAX_SESSIONS = 1_024
_MAX_PAGE_ITEMS = 200
_MAX_POLLED_PER_CYCLE = 100
_MAX_SEEN_MESSAGES = 10_000
_MAX_INBOX_MESSAGES = 1_000
_MAX_HOOK_RECEIPTS = 10_000
_MAX_PATH_CHARS = 4_096


class DevinAdapter(HarnessAdapter):
    name = "devin"

    def __init__(self, transport: HttpJsonTransport | None = None, org_id: str = "org") -> None:
        self.transport = transport
        self.org_id = org_id
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []
        self._pump_task: asyncio.Task | None = None
        self._terminal_markers: dict[str, str] = {}
        self._status_markers: dict[str, str] = {}
        self._seen_message_ids: dict[str, set[str]] = {}
        self._primed_messages: set[str] = set()
        self._last_pump_error: str | None = None
        self._poll_offset = 0

    def attach_transport(self, transport: HttpJsonTransport, org_id: str | None = None) -> None:
        if (
            self.transport is not None
            and self.transport is not transport
            and self._pump_task is not None
            and not self._pump_task.done()
        ):
            raise RuntimeError("detach the active Devin transport before replacing it")
        self.transport = transport
        if org_id:
            self.org_id = org_id

    def _sessions_path(self) -> str:
        return f"/v3/organizations/{quote(self.org_id, safe='')}/sessions"

    async def probe(self) -> AdapterCapabilities:
        connected = False
        if self.transport is not None:
            try:
                response = await self.transport.request("GET", f"{self._sessions_path()}?first=1")
                connected = _page_items(response) is not None
            except Exception:
                connected = False
        pumping = (
            self._pump_task is not None
            and not self._pump_task.done()
            and self._last_pump_error is None
        )
        return AdapterCapabilities(
            observe_messages=connected and pumping,
            observe_session_status=connected,
            send_message=connected,
            inject_context=connected,
            resume=connected,
            start=False,
            control_granularity=ControlGranularity.SESSION,
            trust_level=0.55 if connected else 0.0,
            support_label=AdapterSupportLabel.BASIC
            if connected
            else AdapterSupportLabel.UNAVAILABLE,
            notes=(
                "Official Devin v3 Organization API "
                "(cursor-paginated GET /v3/organizations/{org}/sessions and "
                ".../{id}/messages; POST .../{id}/messages). Sending a message "
                "automatically resumes a suspended session. Terminal statuses: "
                "exit, error, suspended; status_detail=finished is also observed. "
                "Label stays Basic because no tool stream or approval resolver is exposed. "
                + (
                    "Health probe passed."
                    + (
                        " Status poll running."
                        if pumping
                        else " Start the session poll to inspect exit."
                    )
                    if connected
                    else "No healthy authenticated API transport."
                )
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.transport is None:
            from pex_bridge.adapters.desktop import upsert_desktop_observe_session

            upsert_desktop_observe_session(
                self.sessions,
                harness=HarnessType.DEVIN,
                process="Devin.exe",
                skip_if_other_sessions=True,
            )
            return list(self.sessions.values())
        listed = await self._paginate(self._sessions_path())
        for item in listed or []:
            if not isinstance(item, dict):
                continue
            try:
                vendor_id = bounded_adapter_id(
                    item.get("session_id") or item.get("id") or "",
                    field="Devin session id",
                )
            except ValueError:
                continue
            session_id = f"devin:{vendor_id}"
            existing = self.sessions.get(session_id)
            status = bounded_observed_text(
                item.get("status"), field="Devin status", max_chars=512
            ) or ""
            status_detail = bounded_observed_text(
                item.get("status_detail"),
                field="Devin status detail",
                max_chars=4_096,
            ) or ""
            project_id = item.get("project_id") or item.get("projectId")
            project_id = (
                bounded_adapter_id(project_id, field="Devin project id")
                if project_id
                else None
            )
            goal_id, paused = preserve_bridge_state(
                existing,
                cwd=None,
                project_id=project_id,
            )
            provided_url = None
            for key in ("url", "session_url", "html_url", "web_url"):
                raw = item.get(key)
                if isinstance(raw, str) and raw.strip():
                    provided_url = raw
                    break
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.DEVIN,
                vendor_session_id=vendor_id,
                status=_session_status(status, status_detail),
                last_activity=_devin_timestamp(item.get("updated_at")),
                project_id=project_id,
                goal_id=goal_id,
                supervision_paused=paused,
                external_url=devin_session_url(vendor_id=vendor_id, provided=provided_url),
                metadata={
                    "status": status,
                    "status_detail": status_detail or None,
                    "origin": bounded_observed_text(
                        item.get("origin"), field="Devin origin", max_chars=512
                    ),
                    "is_archived": bool(item.get("is_archived", False)),
                },
            )
        return list(self.sessions.values())

    async def _paginate(self, path: str) -> list[dict]:
        if self.transport is None:
            return []
        items: list[dict] = []
        after: str | None = None
        for _ in range(_MAX_PAGES):
            request_path = f"{path}?first=200"
            if after:
                request_path += f"&after={quote(after, safe='')}"
            response = await self.transport.request("GET", request_path)
            page = _page_items(response)
            if page is None:
                raise ValueError("Devin v3 response is missing the items collection")
            if len(page) > _MAX_PAGE_ITEMS:
                raise ValueError("Devin v3 page exceeded the safety bound")
            items.extend(item for item in page if isinstance(item, dict))
            if len(items) > _MAX_SESSIONS:
                raise ValueError("Devin v3 listing exceeded the safety bound")
            if not isinstance(response, dict) or not response.get("has_next_page"):
                return items
            try:
                next_cursor = bounded_adapter_id(
                    response.get("end_cursor") or "", field="Devin pagination cursor"
                )
            except ValueError:
                raise ValueError("Devin v3 pagination returned an unsafe cursor") from None
            if next_cursor == after:
                raise ValueError("Devin v3 pagination did not advance")
            after = next_cursor
        raise ValueError("Devin v3 pagination exceeded the safety bound")

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        bound = self.sessions.get(session.id)
        if (
            self.transport is None
            or not session_binding_matches(bound, session, harness_type=HarnessType.DEVIN)
            or session.id != f"devin:{session.vendor_session_id}"
            or not bound.project_id
        ):
            return False
        try:
            cleaned = bounded_adapter_text(text).strip()
        except ValueError:
            return False
        session = bound
        inbox = self.inbox.setdefault(session.id, [])
        if len(inbox) >= _MAX_INBOX_MESSAGES:
            return False
        try:
            await self.transport.request(
                "POST",
                f"{self._sessions_path()}/{quote(session.vendor_session_id, safe='')}/messages",
                json={"message": cleaned},
            )
        except DeliveryUncertainError:
            raise
        except Exception:
            return False
        inbox.append(cleaned)
        return True

    def ingest_hook(self, payload: dict) -> HarnessSession:
        vendor_id = bounded_adapter_id(
            payload.get("session_id") or "", field="Devin session_id"
        )
        session_id = f"devin:{vendor_id}"
        existing = self.sessions.get(session_id)
        cwd = _optional_bounded_path(payload.get("cwd"))
        if existing is None and len(self.sessions) >= _MAX_SESSIONS:
            raise ValueError("Devin hook session safety bound reached")
        goal_id, paused = preserve_bridge_state(
            existing,
            cwd=cwd,
            project_id=cwd,
        )
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.DEVIN,
            vendor_session_id=vendor_id,
            cwd=cwd,
            project_id=cwd,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
            goal_id=goal_id,
            supervision_paused=paused,
            external_url=devin_session_url(vendor_id=vendor_id),
        )
        self.sessions[session_id] = session
        if len(self.hooks) >= _MAX_HOOK_RECEIPTS:
            del self.hooks[: len(self.hooks) - _MAX_HOOK_RECEIPTS + 1]
        self.hooks.append(
            {"session_id": session_id, "received_at": datetime.now(UTC).isoformat()}
        )
        return session

    def emit_status(self, session: HarnessSession, message: str) -> HarnessEvent:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.DEVIN
        ):
            raise ValueError("Devin status session binding mismatch")
        return HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(UTC),
            harness_type=HarnessType.DEVIN,
            session_id=session.id,
            event_type=EventType.STATUS,
            message_delta=bounded_adapter_text(message, field="status message"),
        )

    async def pump_into_pipeline(self, ingest) -> None:
        while True:
            try:
                if self.transport is None:
                    await asyncio.sleep(0.25)
                    continue
                try:
                    await self.discover_sessions()
                except Exception:
                    pass
                candidates = list(self.sessions.values())
                if candidates:
                    start = self._poll_offset % len(candidates)
                    candidates = (candidates[start:] + candidates[:start])[:_MAX_POLLED_PER_CYCLE]
                    self._poll_offset = (start + len(candidates)) % len(self.sessions)
                for session in candidates:
                    vendor_id = session.vendor_session_id
                    if session.metadata.get("is_archived"):
                        continue
                    if (
                        session.status in {SessionStatus.STOPPED, SessionStatus.ERROR}
                        and vendor_id in self._primed_messages
                        and vendor_id in self._terminal_markers
                    ):
                        continue
                    try:
                        detail = await self.transport.request(
                            "GET",
                            f"{self._sessions_path()}/{quote(vendor_id, safe='')}",
                        )
                    except Exception:
                        continue
                    if not isinstance(detail, dict):
                        continue
                    status = bounded_observed_text(
                        detail.get("status"), field="Devin status", max_chars=512
                    ) or ""
                    status_detail = bounded_observed_text(
                        detail.get("status_detail"),
                        field="Devin status detail",
                        max_chars=4_096,
                    ) or ""
                    raw_updated_at = detail.get("updated_at")
                    updated_at = (
                        raw_updated_at
                        if isinstance(raw_updated_at, (int, float))
                        and not isinstance(raw_updated_at, bool)
                        else bounded_observed_text(
                            raw_updated_at,
                            field="Devin updated timestamp",
                            max_chars=128,
                        )
                    )
                    session.status = _session_status(status, status_detail)
                    session.last_activity = _devin_timestamp(updated_at)
                    session.metadata.update(
                        {
                            "status": status,
                            "status_detail": status_detail or None,
                            "is_archived": bool(detail.get("is_archived", False)),
                        }
                    )
                    try:
                        rows = await self._paginate(
                            f"{self._sessions_path()}/{quote(vendor_id, safe='')}/messages"
                        )
                    except Exception:
                        rows = []
                    replay = vendor_id not in self._primed_messages
                    seen = self._seen_message_ids.setdefault(vendor_id, set())
                    for index, item in enumerate(rows):
                        message_id = _message_id(item, index)
                        if message_id in seen:
                            continue
                        if len(seen) >= _MAX_SEEN_MESSAGES:
                            raise RuntimeError("Devin message retention safety bound reached")
                        seen.add(message_id)
                        text = item.get("message") or item.get("content") or item.get("text")
                        source = (
                            bounded_observed_text(
                                item.get("source") or item.get("role"),
                                field="Devin message source",
                                max_chars=128,
                            )
                            or ""
                        ).lower()
                        event = HarnessEvent(
                            event_id=f"devin-message:{vendor_id}:{message_id}",
                            ts=_devin_timestamp(item.get("created_at")),
                            harness_type=HarnessType.DEVIN,
                            session_id=session.id,
                            event_type=(
                                EventType.AGENT_RESPONSE
                                if source in {"devin", "assistant", "agent"}
                                else EventType.USER_PROMPT
                            ),
                            phase=EventPhase.AFTER,
                            message_delta=_optional_bounded_text(text, field="Devin message"),
                            metadata={
                                "devin_status": status,
                                "devin_status_detail": status_detail or None,
                                "devin_event_id": bounded_observed_text(
                                    item.get("event_id"),
                                    field="Devin event id",
                                    max_chars=512,
                                ),
                                "source": source or None,
                                "replay": replay,
                            },
                        )
                        await ingest(event, session)
                    self._primed_messages.add(vendor_id)

                    status_marker = f"{status}:{status_detail}:{updated_at or ''}"
                    previous_status = self._status_markers.get(vendor_id)
                    if status_marker != previous_status and not _is_terminal(status, status_detail):
                        self._status_markers[vendor_id] = status_marker
                        event = HarnessEvent(
                            event_id=f"devin-status:{vendor_id}:{_digest(status_marker)}",
                            ts=_devin_timestamp(updated_at),
                            harness_type=HarnessType.DEVIN,
                            session_id=session.id,
                            event_type=EventType.STATUS,
                            phase=EventPhase.AFTER,
                            message_delta=status_detail or status or "unknown",
                            metadata={
                                "devin_status": status,
                                "devin_status_detail": status_detail or None,
                                "replay": previous_status is None,
                            },
                        )
                        await ingest(event, session)

                    terminal_marker = status_marker
                    if (
                        _is_terminal(status, status_detail)
                        and self._terminal_markers.get(vendor_id) != terminal_marker
                    ):
                        self._terminal_markers[vendor_id] = terminal_marker
                        self._status_markers[vendor_id] = status_marker
                        last = rows[-1] if rows else {}
                        text = ""
                        if isinstance(last, dict):
                            raw_text = (
                                last.get("message") or last.get("content") or last.get("text")
                            )
                            text = raw_text if isinstance(raw_text, str) else ""
                        event = HarnessEvent(
                            event_id=f"devin-terminal:{vendor_id}:{_digest(terminal_marker)}",
                            ts=_devin_timestamp(updated_at),
                            harness_type=HarnessType.DEVIN,
                            session_id=session.id,
                            event_type=EventType.STOP,
                            phase=EventPhase.TERMINAL,
                            message_delta=_optional_bounded_text(
                                text or status_detail or status, field="Devin terminal message"
                            ),
                            metadata={
                                "devin_status": status,
                                "devin_status_detail": status_detail or None,
                                "replay": previous_status is None,
                            },
                        )
                        await ingest(event, session)
                self._last_pump_error = None
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
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
            name="devin-org-api-poll",
        )
        return self._pump_task


def _page_items(response) -> list | None:
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        return None
    items = response.get("items")
    return items if isinstance(items, list) else None


def _session_status(status: str, status_detail: str) -> SessionStatus:
    if status == "error":
        return SessionStatus.ERROR
    if status == "exit" or status_detail == "finished":
        return SessionStatus.STOPPED
    if status == "suspended":
        return SessionStatus.BLOCKED
    if status_detail in _WAITING:
        return SessionStatus.NEEDS_DECISION
    if status in {"running", "claimed", "new", "resuming"}:
        return SessionStatus.WORKING
    return SessionStatus.DISCOVERED


def _is_terminal(status: str, status_detail: str) -> bool:
    return status in _TERMINAL or status_detail == "finished"


def _message_id(item: dict, index: int) -> str:
    raw_event_id = item.get("event_id")
    event_id = raw_event_id.strip() if isinstance(raw_event_id, str) else ""
    if event_id:
        try:
            return bounded_adapter_id(event_id, field="Devin event id")
        except ValueError:
            return f"unsafe-{_digest(event_id)}"
    fields = (
        item.get("created_at"),
        item.get("source") or item.get("role"),
        item.get("message") or item.get("content") or item.get("text"),
    )
    fallback = "\x1f".join(
        [*(value[:262_144] if isinstance(value, str) else "" for value in fields), str(index)]
    )
    return f"fallback-{_digest(fallback)}"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _devin_timestamp(value) -> datetime:
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 100_000_000_000:
            seconds /= 1000
        try:
            return datetime.fromtimestamp(seconds, UTC)
        except (OverflowError, OSError, ValueError):
            pass
    if isinstance(value, str) and value.strip() and len(value) <= 128:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _optional_bounded_text(value: object, *, field: str) -> str | None:
    return bounded_observed_text(value, field=field, max_chars=MAX_ADAPTER_MESSAGE_CHARS)


def _optional_bounded_path(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return None
    return bounded_adapter_text(value, field="path", max_chars=_MAX_PATH_CHARS)
