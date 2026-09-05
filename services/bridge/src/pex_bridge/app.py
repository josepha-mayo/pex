from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import inspect
import json
import logging
import os
import secrets
import stat
import threading
from contextlib import AsyncExitStack, asynccontextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any, Literal
from unicodedata import category

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pex_protocol.actions import InterventionType
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.context import ContextHandoffRequest
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import ProjectLocator
from pex_protocol.session import HarnessEvent, HarnessSession
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.acp_client import AcpRpcError
from pex_bridge.adapters.base import resolve_adapter_message_result
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings, validate_bridge_token
from pex_bridge.fingerprints import decorate_agent_fingerprints
from pex_bridge.handoff_views import public_intervention
from pex_bridge.hook_auth import (
    HOOK_CREDENTIAL_TTL_SECONDS,
    OPENCODE_HEARTBEAT_ROUTE,
    OPENCODE_OVERLAY_ROUTE,
    HookPrincipal,
    allowed_hook_routes,
    digest_hook_token,
    mint_hook_token,
)
from pex_bridge.mcp_auth import (
    MCP_PRINCIPAL_SCOPE_KEY,
    MCP_SESSION_SCOPES,
    MCPPrincipal,
    digest_mcp_session_token,
    mint_mcp_session_token,
)
from pex_bridge.origin_guard import (
    TrustedLoopbackHostMiddleware,
    TrustedMutationOriginMiddleware,
)
from pex_bridge.pets import (
    MAX_PET_SPRITESHEET_BYTES,
    STARTERS,
    PetSettings,
    catalog,
    catalog_by_id,
    import_codex_pet,
    starters_by_id,
    validate_codex_v2_atlas,
)
from pex_bridge.pets.hatch import (
    HatchAuthorizationError,
    HatchConflictError,
    HatchJob,
    HatchRegistry,
    authorize_hatch,
    run_hatch_job,
    slugify,
)
from pex_bridge.pets.imagegen import (
    describe_hatch_backend,
    hatch_image_config,
    probe_images_endpoint,
)
from pex_bridge.pipeline import Pipeline, collapse_promptable_agents
from pex_bridge.request_limits import RequestBodyLimitMiddleware
from pex_bridge.store import (
    GOAL_CONTROL_ACTION_ATTACH,
    GOAL_CONTROL_ACTION_CREATE,
    GOAL_CONTROL_ACTION_OVERRIDE,
    GOAL_CONTROL_ACTION_UPDATE,
    OperatorEffectConflictError,
    ProjectIdentityBlockedError,
    Store,
    new_id,
    stable_operator_effect_id,
    utcnow,
)
from pex_bridge.supervisor_config import (
    KeyringSupervisorSecretStore,
    SupervisorChoice,
    SupervisorSecretStore,
    SupervisorSecretStoreError,
    load_supervisor_choice,
    save_supervisor_choice,
)

logger = logging.getLogger(__name__)
_PRE_PERMISSION_HOOKS = {
    "preToolUse",
    "beforeShellExecution",
    "beforeMCPExecution",
    "beforeReadFile",
    "PreToolUse",
    "PermissionRequest",
    "pre_tool_call",
}
CURSOR_PERMISSION_PIPELINE_TIMEOUT_SECONDS = 5.0
CURSOR_SUBMIT_PIPELINE_TIMEOUT_SECONDS = 4.0
CURSOR_STOP_PIPELINE_TIMEOUT_SECONDS = 40.0
NAMED_HOOK_PERMISSION_PIPELINE_TIMEOUT_SECONDS = 5.0
NAMED_HOOK_EVENT_PIPELINE_TIMEOUT_SECONDS = 5.0
NAMED_HOOK_STOP_PIPELINE_TIMEOUT_SECONDS = 40.0
ADAPTER_PROBE_TIMEOUT_SECONDS = 2.0
ADAPTER_DISCOVERY_TIMEOUT_SECONDS = 5.0
ADAPTER_MESSAGE_TIMEOUT_SECONDS = 10.0
ADAPTER_FOCUS_TIMEOUT_SECONDS = 5.0
ACP_ATTACH_TIMEOUT_SECONDS = 12.0
TRANSPORT_CLOSE_TIMEOUT_SECONDS = 3.0
SOCKET_SEND_TIMEOUT_SECONDS = 2.0
DESKTOP_REFRESH_TIMEOUT_SECONDS = 5.0
ASK_MODEL_TIMEOUT_SECONDS = 25.0
MAX_WEBSOCKET_MESSAGE_CHARS = 4096
WEBSOCKET_TOKEN_PROTOCOL_PREFIX = "pex-token."
MAX_EVENT_SOCKETS = 16
EVENT_SOCKET_QUEUE_SIZE = 128
EVENT_SOCKET_CATCHUP_PAGE = 100
EVENT_SOCKET_MAX_CATCHUP = 1000
EVENT_SOCKET_HEARTBEAT_SECONDS = 15.0
EVENT_SOCKET_POLL_SECONDS = 0.25
MAX_ID_CHARS = 512
MAX_PATH_CHARS = 4096
MAX_CONTROL_TEXT_CHARS = 65_536
MAX_GOAL_LIST_ITEMS = 128
MAX_GOAL_ITEM_CHARS = 8192
MAX_EVENT_FILE_PATHS = 256
MAX_TOKEN_FILE_BYTES = 4096
MAX_PET_SETTINGS_BYTES = 1_048_576
MAX_SUPERVISOR_CHOICE_BYTES = 16_384
MCP_SESSION_CREDENTIAL_TTL_SECONDS = 86_400
HATCH_AUTHORIZATION_TTL_MINUTES = 10
LOCAL_HATCH_OPERATOR_PRINCIPAL = "operator:local"
_OBSERVE_ONLY_STOP_HOOKS = {
    ("hermes", "on_session_end"),
    ("hermes", "on_session_finalize"),
}
_HOOK_CREDENTIAL_ISSUABLE_STATUSES = {
    SessionStatus.DISCOVERED,
    SessionStatus.IDLE,
    SessionStatus.WORKING,
    SessionStatus.BLOCKED,
    SessionStatus.NEEDS_DECISION,
    SessionStatus.DRIFTING,
    SessionStatus.VERIFYING,
}

BoundedId = Annotated[str, Field(min_length=1, max_length=MAX_ID_CHARS)]
BoundedPath = Annotated[str, Field(min_length=1, max_length=MAX_PATH_CHARS)]
GoalListItem = Annotated[str, Field(min_length=1, max_length=MAX_GOAL_ITEM_CHARS)]


def _named_hook_pipeline_timeout(
    harness: str,
    hook_name: str,
    event_type: EventType,
) -> float:
    """Bound hook work by whether the harness can consume a lifecycle response."""

    if (harness, hook_name) in _OBSERVE_ONLY_STOP_HOOKS:
        return NAMED_HOOK_EVENT_PIPELINE_TIMEOUT_SECONDS
    if event_type == EventType.STOP:
        return NAMED_HOOK_STOP_PIPELINE_TIMEOUT_SECONDS
    return NAMED_HOOK_EVENT_PIPELINE_TIMEOUT_SECONDS


def _permission_from_intervention(intervention: Any) -> str:
    if intervention is None:
        return "ask"
    if str(getattr(intervention, "action_taken", "")) != InterventionType.RESPOND_PERMISSION.value:
        return "ask"
    verdict = intervention.policy_verdict
    value = verdict.value if hasattr(verdict, "value") else str(verdict or "")
    if value == PolicyVerdict.ASK_HUMAN.value:
        return "ask"
    result = str(getattr(intervention, "result", ""))
    if result in {"permission_deny", "permission_deny_inline"}:
        return "deny"
    if result in {"permission_allow", "permission_allow_inline"}:
        return "allow"
    return "ask"


def _cursor_submit_response(
    intervention: Intervention | None,
    event: HarnessEvent,
    session: HarnessSession,
) -> dict[str, Any]:
    """Only a completed, policy-approved decision for this prompt may affect it."""
    passthrough = {"continue": True}
    if (
        not isinstance(intervention, Intervention)
        or session.harness_type != HarnessType.CURSOR
        or session.supervision_paused
        or not session.goal_id
        or event.harness_type != HarnessType.CURSOR
        or event.event_type != EventType.USER_PROMPT
        or event.phase != EventPhase.BEFORE
        or event.metadata.get("hook_event_name") != "beforeSubmitPrompt"
        or event.session_id != session.id
        or event.project_id != session.project_id
        or (event.goal_id is not None and event.goal_id != session.goal_id)
        or intervention.session_id != session.id
        or intervention.goal_id != session.goal_id
        or intervention.trigger != EventType.USER_PROMPT.value
        or intervention.metadata.get("trigger_event_id") != event.event_id
        or not any(item.strip() for item in intervention.evidence)
    ):
        return passthrough
    action = intervention.proposed_action
    if (
        action.session_id != session.id
        or action.goal_id != session.goal_id
        or intervention.action_taken != action.type.value
    ):
        return passthrough
    if (
        action.type == InterventionType.ASK_HUMAN
        and intervention.policy_verdict in {PolicyVerdict.ALLOW, PolicyVerdict.ASK_HUMAN}
        and intervention.result == "escalated"
    ):
        field, proceed = "question", False
    elif (
        action.type == InterventionType.ANNOTATE
        and intervention.policy_verdict == PolicyVerdict.ALLOW
        and intervention.result == "annotated"
    ):
        field, proceed = "text", True
    else:
        return passthrough
    message = action.payload.get(field)
    if not isinstance(message, str) or not message.strip() or len(message) > 4_096:
        return passthrough
    return {"continue": proceed, "user_message": message.strip()}


async def _cursor_submit_authority(session_id: str) -> tuple[HarnessSession, tuple] | None:
    """Snapshot canonical prompt authority; CAS revisions detect pause/rebind ABA."""
    try:
        before = await state.store.get_session_control_state(session_id)
        session = await state.store.get_session_for_authority(session_id, require_goal_binding=True)
        if before is None or session is None or not session.goal_id or session.supervision_paused:
            return None
        goal = await state.store.get_goal_intent_view(session.goal_id)
        after = await state.store.get_session_control_state(session_id)
    except (ProjectIdentityBlockedError, PermissionError):
        return None
    if goal is None or goal.get("paused") or after is None:
        return None
    control_fields = ("control_revision", "project_binding", "discovery_generation")
    if any(before[key] != after[key] for key in control_fields):
        return None
    current = after["session"]
    if current.supervision_paused or any(
        getattr(current, key) != getattr(session, key)
        for key in ("id", "harness_type", "vendor_session_id", "goal_id", "project_id", "cwd")
    ):
        return None
    return current, (
        *(after[key] for key in control_fields),
        session.goal_id,
        goal["intent_revision"],
        goal["intent_hash"],
    )


async def _process_cursor_submit(event: HarnessEvent, session: HarnessSession) -> dict[str, Any]:
    # Authority reads share the hook's deadline with inference; a locked store
    # must not make the synchronous editor callback wait without a bound.
    paused = state.pipeline.supervision_paused
    authority = await _cursor_submit_authority(session.id)
    intervention = await state.pipeline.ingest_event(event, session)
    current = await _cursor_submit_authority(session.id)
    if (
        paused
        or state.pipeline.supervision_paused
        or authority is None
        or current is None
        or authority[1] != current[1]
    ):
        return {"continue": True}
    return _cursor_submit_response(intervention, event, current[0])


async def _observe_cursor_continuation(event_id: str) -> None:
    try:
        await asyncio.wait_for(state.store.observe_cursor_hook_continuation(event_id), timeout=1.0)
    except (TimeoutError, LookupError, PermissionError, ProjectIdentityBlockedError):
        return
    except Exception as exc:
        logger.warning("Cursor continuation observation unavailable (%s)", type(exc).__name__)


async def _process_cursor_stop(event: HarnessEvent, session: HarnessSession) -> dict[str, Any]:
    adapter = state.adapters.cursor
    paused = state.pipeline.supervision_paused
    authority = await _cursor_submit_authority(session.id)
    try:
        intervention = await state.pipeline.ingest_event(event, session)
        await _observe_cursor_continuation(event.event_id)
        current = await _cursor_submit_authority(session.id)
        if (
            paused
            or state.pipeline.supervision_paused
            or authority is None
            or current is None
            or authority[1] != current[1]
            or event.metadata.get("tool_status") in {"aborted", "error"}
        ):
            return {}
        text = adapter.consume_verified_stop_followup(current[0], intervention)
        if not text or intervention is None:
            return {}
        revision, binding, generation, goal_id, intent_revision, intent_hash = current[1]
        packet = await state.store.prepare_cursor_hook_delivery(
            intervention.id,
            intervention.metadata.get("hook_preparation_receipt"),
            expected_authority={
                "control_revision": revision,
                "project_binding": binding,
                "discovery_generation": generation,
                "goal_id": goal_id,
                "intent_revision": intent_revision,
                "intent_hash": intent_hash,
            },
        )
        return {"followup_message": text, "pex_hook_delivery": packet}
    finally:
        adapter.consume_followup(session.id, trigger_event_id=event.event_id)


async def _record_cursor_delivery_ack(payload: dict) -> dict[str, Any]:
    if (
        set(payload) != {
            "hook_event_name", "conversation_id", "workspace_roots", "receipt", "delivery_evidence",
        }
        or payload.get("delivery_evidence") != "hook_stdout_flushed"
        or not isinstance(payload.get("receipt"), dict)
    ):
        raise HTTPException(422, "invalid Cursor delivery observation")
    packet = payload["receipt"]
    conversation_id = payload.get("conversation_id")
    if (
        not isinstance(conversation_id, str)
        or packet.get("vendor_session_id") != conversation_id
        or packet.get("target_session_id") != f"cursor:{conversation_id}"
    ):
        raise HTTPException(422, "Cursor delivery observation identity mismatch")
    _, project_id = _hook_payload_binding(HarnessType.CURSOR, payload)
    if project_id is None:
        raise HTTPException(422, "Cursor delivery observation requires a project identity")
    try:
        return await asyncio.wait_for(
            state.store.record_cursor_hook_flush(packet, project_id=project_id), timeout=1.0,
        )
    except (LookupError, PermissionError, ProjectIdentityBlockedError, ValueError, TypeError):
        raise HTTPException(409, "Cursor delivery observation rejected") from None
    except TimeoutError:
        raise HTTPException(503, "Cursor delivery observation is unavailable") from None


TRUSTED_UI_ORIGINS = {
    "http://127.0.0.1:1420",
    "http://localhost:1420",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
}


class MCPTokenMiddleware:
    """Authenticate MCP callers and bind session credentials to live state."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if not state.settings.require_auth:
            scope[MCP_PRINCIPAL_SCOPE_KEY] = MCPPrincipal.anonymous()
            await self.app(scope, receive, send)
            return
        expected = state.token or ""
        authorization = next(
            (
                value.decode("latin-1")
                for name, value in scope.get("headers", [])
                if name.lower() == b"authorization"
            ),
            "",
        )
        scheme, separator, supplied = authorization.partition(" ")
        if not separator or scheme.casefold() != "bearer":
            response = Response(
                content='{"detail":"invalid token"}',
                status_code=401,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return
        if expected and secrets.compare_digest(supplied, expected):
            scope[MCP_PRINCIPAL_SCOPE_KEY] = MCPPrincipal.operator()
            await self.app(scope, receive, send)
            return
        try:
            checked_at = utcnow()
            digest = digest_mcp_session_token(supplied)
            record = await state.store.get_mcp_principal_by_digest(
                digest,
                now=checked_at,
            )
            principal = (
                MCPPrincipal.from_store_record(record, now=checked_at)
                if record is not None
                else None
            )
            if principal is not None:
                principal = await _revalidate_mcp_session_principal(principal)
        except (TypeError, ValueError):
            principal = None
        except Exception:
            logger.exception("MCP session authentication is unavailable")
            response = Response(
                content='{"detail":"bridge authentication is unavailable"}',
                status_code=503,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return
        if principal is None:
            status_code = 401 if expected else 503
            detail = "invalid token" if expected else "bridge authentication is unavailable"
            response = Response(
                content=json.dumps({"detail": detail}, separators=(",", ":")),
                status_code=status_code,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return
        scope[MCP_PRINCIPAL_SCOPE_KEY] = principal
        await self.app(scope, receive, send)


async def _revalidate_mcp_session_principal(
    principal: MCPPrincipal,
) -> MCPPrincipal | None:
    """Recheck every credential binding against canonical live Store state."""

    if principal.kind != "session" or principal.session_id is None:
        return None
    try:
        session = await state.store.get_session_for_authority(
            principal.session_id,
            require_goal_binding=True,
        )
    except ProjectIdentityBlockedError:
        return None
    if session is None or session.status == SessionStatus.DETACHED:
        return None
    from pex_bridge.adapters.desktop import is_desktop_observe_session

    if is_desktop_observe_session(session):
        return None
    if (
        session.goal_id != principal.goal_id
        or session.vendor_session_id != principal.vendor_session_id
        or session.harness_type != principal.harness_type
        or not principal.scopes.issubset(MCP_SESSION_SCOPES)
    ):
        return None
    try:
        goal = (
            await state.store.get_goal_for_authority(session.goal_id)
            if session.goal_id
            else None
        )
    except ProjectIdentityBlockedError:
        return None
    project_id = session.project_id or session.cwd
    if (
        goal is None
        or project_id is None
        or principal.project_id is None
        or await state.store.has_goal_successor_for_authority(goal.id)
    ):
        return None
    try:
        live_project_binding = await state.store.project_binding_for_authority(
            principal.project_id
        )
    except ProjectIdentityBlockedError:
        return None
    if live_project_binding != principal.project_binding:
        return None
    return principal


def _atomic_write_text(path: Path, text: str) -> None:
    """Durably replace a small control-plane file without exposing partial JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / (
        f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_bounded_utf8(path: Path, max_bytes: int, label: str) -> str:
    try:
        if path.stat().st_size > max_bytes:
            raise ValueError(f"{label} exceeds its safety bound")
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError:
        raise
    if len(raw) > max_bytes:
        raise ValueError(f"{label} exceeds its safety bound")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be valid UTF-8") from exc


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _strict_json_loads(raw: str) -> Any:
    return json.loads(
        raw,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_unique_json_object,
    )


class _RecordedReplaySupervisor:
    """Deterministic-only supervisor for fixtures advertised as non-live replay."""

    async def decide(self, request: Any, *, local_model: object | None) -> Any:
        del local_model
        from pex_protocol.supervisor import SupervisorResult
        from pex_supervisor.planner import plan_deterministic

        return SupervisorResult(
            action=plan_deterministic(request),
            used_llm=False,
            diagnosis="recorded_replay_deterministic",
            execution_mode="recorded_replay",
            inference_status="not_attempted",
        )


def _validate_pet_atlas(data: bytes) -> bytes:
    if not data or len(data) > MAX_PET_SPRITESHEET_BYTES:
        raise ValueError("pet spritesheet must be between 1 byte and 16 MiB")
    try:
        with Image.open(BytesIO(data)) as image:
            validate_codex_v2_atlas(image, subject="pet spritesheet")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("pet spritesheet is not a valid WebP image") from exc
    return data


def _read_pet_atlas(path: Path) -> bytes:
    try:
        sheet = path.resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(path) from exc
    if not sheet.is_file():
        raise FileNotFoundError(path)
    if sheet.stat().st_size > MAX_PET_SPRITESHEET_BYTES:
        raise ValueError("pet spritesheet exceeds the 16 MiB safety bound")
    with sheet.open("rb") as handle:
        data = handle.read(MAX_PET_SPRITESHEET_BYTES + 1)
    return _validate_pet_atlas(data)


def _public_pet_definition(pet: Any) -> dict[str, Any]:
    """Expose catalog metadata without leaking a local filesystem path."""

    return pet.model_dump(mode="json", exclude={"spritesheet"})


def _public_pet_settings(settings: PetSettings) -> dict[str, Any]:
    """Return only appearance controls consumed by the desktop UI."""

    return settings.model_dump(
        mode="json",
        exclude={"imported_codex_dir", "imports"},
    )


def _resolved_attach_binary(
    requested: object,
    resolved: str | None,
    label: str,
) -> str:
    """Accept only a binary resolved by the trusted local inventory/env path."""

    if not resolved:
        raise ValueError(f"{label} binary was not discovered")
    try:
        resolved_path = Path(resolved).resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} binary was not discovered") from exc
    if not resolved_path.is_file():
        raise ValueError(f"{label} binary was not discovered")
    if requested is not None and str(requested).strip():
        try:
            requested_path = Path(str(requested).strip()).resolve(strict=True)
        except OSError as exc:
            raise ValueError(
                f"{label} attach accepts only the discovered binary; configure PATH or PEX env"
            ) from exc
        if not requested_path.is_file() or requested_path != resolved_path:
            raise ValueError(
                f"{label} attach accepts only the discovered binary; configure PATH or PEX env"
            )
    return str(resolved_path)


class _BridgeStateLock:
    def __init__(self, database_path: Path) -> None:
        resolved_database_path = database_path.resolve()
        self.database_parent = resolved_database_path.parent
        self.path = (
            self.database_parent / f".{resolved_database_path.name}.bridge.lock"
            if os.name == "nt"
            else self.database_parent
        )
        self._descriptor: int | None = None

    def acquire(self) -> None:
        if self._descriptor is not None:
            raise RuntimeError("PEX bridge state lock is already held")
        self.database_parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT if os.name == "nt" else os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_DIRECTORY", 0) if os.name != "nt" else 0
        descriptor = os.open(self.path, flags, 0o600)
        try:
            os.set_inheritable(descriptor, False)
            if os.name == "nt":
                import msvcrt

                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception as exc:
            os.close(descriptor)
            raise RuntimeError(
                f"PEX bridge could not acquire the state database lock: {self.path}"
            ) from exc
        self._descriptor = descriptor

    def release(self) -> None:
        descriptor = self._descriptor
        if descriptor is None:
            return
        self._descriptor = None
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


class AppState:
    def __init__(self) -> None:
        self.settings = Settings()
        self.store = Store(self.settings.resolved_db_path)
        self.adapters = AdapterRegistry()
        self.bus = EventBus()
        self.pipeline = Pipeline(self.store, self.adapters, self.bus, self.settings, model=None)
        self.token = self.settings.token
        self.settings.token = None
        if self.token:
            from pex_bridge.adapters.cursor import set_internal_bridge_token

            set_internal_bridge_token(self.token)
        self.sockets: list[WebSocket] = []
        self._socket_send_locks: dict[WebSocket, asyncio.Lock] = {}
        self._socket_queues: dict[WebSocket, asyncio.Queue[dict[str, Any]]] = {}
        self._socket_registry_lock = threading.Lock()
        self.pet_settings = PetSettings()
        self.pet_path = self.settings.data_dir / "pet.json"
        self.supervisor_error: str | None = None
        self.supervisor_choice: SupervisorChoice | None = None
        self.supervisor_secret_store: SupervisorSecretStore = KeyringSupervisorSecretStore()
        self.supervisor_config_lock = asyncio.Lock()
        from pex_bridge.codex_shared_attach import SharedCodexAttachments

        self.codex_shared_attachments = SharedCodexAttachments()
        self.hatch = HatchRegistry(self.settings.data_dir / "hatch")
        self.background_tasks: set[asyncio.Task[Any]] = set()
        self.hatch_tasks: dict[str, asyncio.Task[Any]] = {}

    def register_event_socket(
        self,
        socket: WebSocket,
        queue: asyncio.Queue[dict[str, Any]],
    ) -> bool:
        """Register one accepted socket without crossing a cancellation point."""

        with self._socket_registry_lock:
            if len(self.sockets) >= MAX_EVENT_SOCKETS:
                return False
            self.sockets.append(socket)
            self._socket_queues[socket] = queue
            return True

    def detach_event_socket(self, socket: WebSocket) -> None:
        """Idempotently detach a socket before any fallible close or await."""

        with self._socket_registry_lock:
            if socket in self.sockets:
                self.sockets.remove(socket)
            self._socket_queues.pop(socket, None)
            self._socket_send_locks.pop(socket, None)

    def detach_all_event_sockets(self) -> list[WebSocket]:
        """Atomically empty the capacity ledger and return sockets to close."""

        with self._socket_registry_lock:
            sockets = list(self.sockets)
            self.sockets.clear()
            self._socket_queues.clear()
            self._socket_send_locks.clear()
            return sockets

    def event_socket_snapshot(self) -> list[WebSocket]:
        with self._socket_registry_lock:
            return list(self.sockets)

    def track_background(self, task: asyncio.Task[Any]) -> None:
        """Retain a task and consume failures so background work cannot disappear silently."""

        self.background_tasks.add(task)

        def finished(completed: asyncio.Task[Any]) -> None:
            self.background_tasks.discard(completed)
            if completed.cancelled():
                return
            try:
                completed.result()
            except Exception as exc:
                logger.error(
                    "Background task %s failed (%s)",
                    completed.get_name(),
                    type(exc).__name__,
                )

        task.add_done_callback(finished)

    def track_hatch_background(
        self,
        job_id: str,
        task: asyncio.Task[Any],
    ) -> None:
        """Retain exactly one process-local dispatcher for a canonical hatch job."""

        active = self.hatch_tasks.get(job_id)
        if active is not None and not active.done():
            raise RuntimeError("hatch dispatcher is already active")
        self.hatch_tasks[job_id] = task
        self.track_background(task)

        def finished(completed: asyncio.Task[Any]) -> None:
            if self.hatch_tasks.get(job_id) is completed:
                self.hatch_tasks.pop(job_id, None)

        task.add_done_callback(finished)

    async def broadcast(self, topic: str, payload: dict[str, Any]) -> None:
        if topic == "event":
            # Canonical event sockets tail the durable acceptance ledger. A
            # process-local wake/broadcast is never an event delivery receipt.
            return
        if topic == "pet":
            payload = self.decorate_pet(payload)
        sockets = self.event_socket_snapshot()
        queued_dead: list[WebSocket] = []
        direct_sockets: list[WebSocket] = []
        message = {"topic": topic, "payload": payload}
        for ws in sockets:
            queue = self._socket_queues.get(ws)
            if queue is None:
                # Kept for small unit fakes and pre-upgrade callers. Real event
                # sockets always install a bounded queue before acceptance.
                direct_sockets.append(ws)
                continue
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                queued_dead.append(ws)

        async def send_one(ws: WebSocket) -> WebSocket | None:
            lock = self._socket_send_locks.setdefault(ws, asyncio.Lock())
            try:
                async with lock:
                    await asyncio.wait_for(
                        ws.send_json(message),
                        timeout=SOCKET_SEND_TIMEOUT_SECONDS,
                    )
            except Exception:
                return ws
            return None

        dead = [
            ws
            for ws in await asyncio.gather(*(send_one(ws) for ws in direct_sockets))
            if ws is not None
        ]
        for ws in queued_dead:
            self.detach_event_socket(ws)
            try:
                await ws.close(code=1013, reason="event socket queue full")
            except Exception:
                pass
        for ws in dead:
            self.detach_event_socket(ws)

    def decorate_pet(self, snap: dict[str, Any]) -> dict[str, Any]:
        chosen = catalog_by_id(self.pet_settings).get(self.pet_settings.selected_id, STARTERS[0])
        appearance = _public_pet_definition(chosen)
        if self.pet_settings.custom_name:
            appearance["display_name"] = self.pet_settings.custom_name
        if chosen.atlas_ready:
            appearance["spritesheet_url"] = f"/v1/pets/{chosen.id}/spritesheet"
        appearance["hue_shift"] = self.pet_settings.hue_shift
        appearance["scale"] = self.pet_settings.scale
        appearance["atlas_ready"] = bool(chosen.atlas_ready)
        snap["appearance"] = appearance
        snap["settings"] = _public_pet_settings(self.pet_settings)
        last = snap.get("last_action") or {}
        transition_mood = snap.get("mood")
        if snap.get("needs_you"):
            snap["mood"] = "decision"
        elif snap.get("blocked"):
            snap["mood"] = "warning"
        elif transition_mood in {"handoff", "approved"}:
            snap["mood"] = transition_mood
        elif snap.get("drifting"):
            snap["mood"] = "drift"
        elif snap.get("working"):
            snap["mood"] = "working"
        elif transition_mood:
            snap["mood"] = transition_mood
        elif last.get("action") in {"SEND_NUDGE", "REQUEST_VERIFICATION", "FRESH_HANDOFF"}:
            snap["mood"] = "observing"
        else:
            snap["mood"] = "idle"
        return snap

    async def live_pet(self) -> dict[str, Any]:
        try:
            await asyncio.wait_for(
                self.pipeline.refresh_desktop_sessions(),
                timeout=DESKTOP_REFRESH_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning("Desktop session refresh timed out; returning durable state")
        snapshot = self.decorate_pet(await self.pipeline.pet_snapshot())
        for session in snapshot.get("sessions") or []:
            if not isinstance(session, dict) or not isinstance(session.get("id"), str):
                continue
            control = await self.store.get_session_control_state(session["id"])
            if control is not None:
                session["revision"] = control["revision"]
                session["control_revision"] = control["control_revision"]
        return snapshot


state = AppState()


async def _close_owned_transport(transport: Any) -> None:
    closer = getattr(transport, "aclose", None) or getattr(transport, "close", None)
    if closer is None:
        return
    result = closer()
    if inspect.isawaitable(result):
        await result


async def _replace_http_transport(
    adapter: Any,
    transport: Any,
    *,
    org_id: str | None = None,
) -> None:
    """Transfer ownership of one HTTP transport without leaking failed swaps."""

    previous = getattr(adapter, "transport", None)
    try:
        if org_id is None:
            adapter.attach_transport(transport)
        else:
            adapter.attach_transport(transport, org_id=org_id)
    except Exception:
        await _close_owned_transport(transport)
        raise
    if previous is not None and previous is not transport:
        try:
            await _close_owned_transport(previous)
        except Exception as exc:
            logger.warning(
                "Replaced HTTP transport could not be closed (%s)",
                type(exc).__name__,
            )


async def _attach_verified_http_transport(
    adapter: Any,
    transport: Any,
    *,
    org_id: str | None = None,
) -> AdapterCapabilities:
    """Install a candidate only when its bounded live probe succeeds."""

    previous = getattr(adapter, "transport", None)
    previous_org = getattr(adapter, "org_id", None)
    try:
        if org_id is None:
            adapter.attach_transport(transport)
        else:
            adapter.attach_transport(transport, org_id=org_id)
    except Exception:
        await _close_owned_transport(transport)
        raise

    capabilities = await _bounded_adapter_probe(adapter)
    if capabilities.support_label.value == "unavailable":
        try:
            if previous is None:
                adapter.transport = None
                if org_id is not None and previous_org is not None:
                    adapter.org_id = previous_org
            elif org_id is None:
                adapter.attach_transport(previous)
            else:
                adapter.attach_transport(previous, org_id=previous_org)
        finally:
            await _close_owned_transport(transport)
        raise HTTPException(502, "adapter attach probe failed; candidate was discarded")

    if previous is not None and previous is not transport:
        try:
            await _close_owned_transport(previous)
        except Exception as exc:
            logger.warning(
                "Verified adapter replaced a transport that could not be closed (%s)",
                type(exc).__name__,
            )
    return capabilities


async def _attach_isolated_codex(binary: str) -> AdapterCapabilities:
    """Publish a verified isolated connection without replacing an owned worker."""
    from pex_bridge.adapters.codex import CodexAdapter, CodexStdioTransport

    manager = state.codex_shared_attachments
    async with manager.lock:
        if manager.closed or state.codex_shared_attachments is not manager:
            raise HTTPException(409, "Codex attachment manager is closed")
        previous = state.adapters.get("codex")
        if previous is None:
            raise HTTPException(404, "adapter not found")
        if (
            not isinstance(previous, CodexAdapter)
            or previous.transport is not None
            or manager.active is not None
        ):
            raise HTTPException(409, "detach the existing Codex connection before attaching")

        candidate = CodexAdapter()
        transport = CodexStdioTransport(binary)
        old_pump = previous._pump_task
        stopped_old_pump = False
        published = False
        try:
            candidate.attach_transport(transport)
            caps = await _bounded_adapter_probe(candidate)
            if not transport.initialized or not caps.send_message:
                raise HTTPException(502, "isolated Codex attach probe failed; candidate discarded")
            if state.adapters.get("codex") is not previous or previous.transport is not None:
                raise HTTPException(409, "Codex connection changed during attachment")
            if old_pump is not None and not old_pump.done():
                stopped_old_pump = True
                old_pump.cancel()
                await asyncio.wait_for(
                    asyncio.gather(old_pump, return_exceptions=True),
                    timeout=TRANSPORT_CLOSE_TIMEOUT_SECONDS,
                )
            if state.adapters.get("codex") is not previous or previous.transport is not None:
                raise HTTPException(409, "Codex connection changed during attachment")
            state.adapters.bind("codex", candidate)
            published = True
            candidate.start_pipeline_pump(state.pipeline.ingest_event)
            # These are the capabilities actually probed before pump startup.
            # Do not upgrade the response to Deep merely for scheduling a task.
            return caps
        except BaseException:
            if published and state.adapters.get("codex") is candidate:
                state.adapters.bind("codex", previous)
            pump = candidate._pump_task
            if pump is not None:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
            try:
                await asyncio.wait_for(
                    _close_owned_transport(transport),
                    timeout=TRANSPORT_CLOSE_TIMEOUT_SECONDS,
                )
            finally:
                if stopped_old_pump and state.adapters.get("codex") is previous:
                    previous.start_pipeline_pump(state.pipeline.ingest_event)
            raise


def _start_event_pumps() -> None:
    for adapter in state.adapters.all():
        starter = getattr(adapter, "start_pipeline_pump", None)
        if starter is None:
            continue
        starter(state.pipeline.ingest_event)


async def _stop_runtime_loop(
    stop: asyncio.Event,
    task: asyncio.Task[Any],
    *,
    name: str,
) -> None:
    """Stop and join one lifespan-owned loop without blocking later cleanup."""

    stop.set()
    try:
        await asyncio.wait_for(
            task,
            timeout=TRANSPORT_CLOSE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        logger.warning("%s did not stop before the shutdown deadline", name)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("%s shutdown failed (%s)", name, type(exc).__name__)


async def _shutdown_runtime_resources() -> None:
    """Cancel runtime work and close adapter-owned transports before Store shutdown."""

    await state.codex_shared_attachments.close_pending()
    await state.pipeline.close_presentations()
    sockets = state.detach_all_event_sockets()
    for socket in sockets:
        try:
            await socket.close(code=1001, reason="bridge shutting down")
        except Exception:
            pass
    background = list(state.background_tasks)
    for task in background:
        task.cancel()
    if background:
        await asyncio.gather(*background, return_exceptions=True)
    state.background_tasks.difference_update(background)
    state.hatch_tasks.clear()

    for adapter in state.adapters.all():
        pump = getattr(adapter, "_pump_task", None)
        if pump is not None:
            pump.cancel()
            try:
                await pump
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning(
                    "Adapter %s pump shutdown failed (%s)",
                    getattr(adapter, "name", "unknown"),
                    type(exc).__name__,
                )
        transport = getattr(adapter, "transport", None)
        if transport is None and getattr(adapter, "acp", None) is not None:
            transport = getattr(adapter.acp, "transport", None)
        if transport is not None:
            try:
                await asyncio.wait_for(
                    _close_owned_transport(transport),
                    timeout=TRANSPORT_CLOSE_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                logger.warning(
                    "Adapter %s transport close failed or timed out (%s)",
                    getattr(adapter, "name", "unknown"),
                    type(exc).__name__,
                )


async def _finish_acp_attach(adapter: Any, body: dict) -> Any:
    """Verify an explicitly requested ACP attach before reporting success."""
    client = getattr(adapter, "acp", None)
    if client is None:
        raise HTTPException(500, "ACP client was not attached")
    auth_method = str(body.get("auth_method") or "").strip()
    metadata = body.get("auth_metadata")

    async def discard() -> None:
        try:
            await asyncio.wait_for(
                client.transport.close(), timeout=TRANSPORT_CLOSE_TIMEOUT_SECONDS
            )
        except Exception:
            pass
        if getattr(adapter, "acp", None) is client:
            adapter.acp = None

    if metadata is not None and not isinstance(metadata, dict):
        await discard()
        raise HTTPException(400, "auth_metadata must be an object")
    try:
        async with asyncio.timeout(ACP_ATTACH_TIMEOUT_SECONDS):
            if not client.ready:
                await client.handshake()
            if auth_method:
                await client.authenticate(auth_method, metadata=metadata)
            # Verify the ACP surface itself. Adapter probe may have an independent
            # hook fallback (Hermes), which must not make a failed ACP attach pass.
            await client.list_sessions()
            preflight = await adapter.probe()
    except TimeoutError as exc:
        await discard()
        raise HTTPException(504, "ACP attach timed out and was discarded") from exc
    except ValueError as exc:
        await discard()
        raise HTTPException(400, str(exc)) from exc
    except AcpRpcError as exc:
        offered = sorted(getattr(client, "auth_methods", {}))
        await discard()
        if exc.code == -32000 and offered and not auth_method:
            raise HTTPException(
                409,
                {
                    "code": "acp_auth_required",
                    "auth_methods": offered,
                    "message": "Retry the explicit attach with a protocol-driven auth_method.",
                },
            ) from exc
        raise HTTPException(502, "ACP handshake or session/list failed") from exc
    except Exception as exc:
        await discard()
        raise HTTPException(502, "ACP handshake or session/list failed") from exc
    if preflight.support_label.value == "unavailable":
        await discard()
        raise HTTPException(
            502,
            {
                "code": "acp_attach_failed",
                "auth_methods": [],
                "message": "ACP did not expose capability-gated session access.",
            },
        )
    _start_event_pumps()
    await asyncio.sleep(0)
    return await _bounded_adapter_probe(adapter)


async def _attach_verified_acp(adapter: Any, transport: Any, body: dict) -> Any:
    """Preserve an existing ACP client until the candidate is fully verified."""

    previous = getattr(adapter, "acp", None)
    try:
        adapter.attach_acp(transport)
    except Exception:
        await _close_owned_transport(transport)
        raise
    try:
        capabilities = await _finish_acp_attach(adapter, body)
    except Exception:
        if getattr(adapter, "acp", None) is None:
            adapter.acp = previous
        raise
    if previous is not None and previous is not getattr(adapter, "acp", None):
        try:
            await asyncio.wait_for(
                _close_owned_transport(previous.transport),
                timeout=TRANSPORT_CLOSE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "Verified ACP attach replaced a client that could not be closed (%s)",
                type(exc).__name__,
            )
    return capabilities


def _install_cursor_hooks_or_error() -> Path:
    from pex_bridge.adapters.cursor_hooks import install_user_hooks

    try:
        return install_user_hooks(mode="observe")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, "Cursor hooks could not be updated atomically") from exc


async def apply_cursor_hook(payload: dict) -> dict[str, Any]:
    adapter = state.adapters.cursor
    channel = "observe" if payload.get("observed_ns") is not None else "hook"
    token = adapter._delivery_channel.set(channel)
    try:
        return await _apply_cursor_hook(payload)
    finally:
        adapter._delivery_channel.reset(token)


async def _apply_cursor_hook(payload: dict) -> dict[str, Any]:
    adapter = state.adapters.cursor
    try:
        session = adapter.upsert_from_hook(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = await state.store.get_session_for_authority(session.id)
    if existing:
        session.goal_id = existing.goal_id
        session.supervision_paused = existing.supervision_paused
        if not session.cwd:
            session.cwd = existing.cwd
        if not session.project_id:
            session.project_id = existing.project_id
    await state.store.upsert_session(session)
    event = adapter.normalize_hook(payload, session)
    hook_name = payload.get("hook_event_name")
    response: dict[str, Any] = {}
    if hook_name in _PRE_PERMISSION_HOOKS:
        try:
            intervention = await asyncio.wait_for(
                state.pipeline.ingest_event(event, session),
                timeout=CURSOR_PERMISSION_PIPELINE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            response["permission"] = "ask"
            return response
        response["permission"] = _permission_from_intervention(intervention)
        return response
    if hook_name == "beforeSubmitPrompt":
        try:
            return await asyncio.wait_for(
                _process_cursor_submit(event, session),
                timeout=CURSOR_SUBMIT_PIPELINE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return {"continue": True}
    if hook_name == "stop":
        try:
            return await asyncio.wait_for(
                _process_cursor_stop(event, session),
                timeout=CURSOR_STOP_PIPELINE_TIMEOUT_SECONDS,
            )
        except (
            TimeoutError,
            PermissionError,
            ProjectIdentityBlockedError,
            LookupError,
            ValueError,
        ):
            return response
        finally:
            adapter.consume_followup(session.id, trigger_event_id=event.event_id)
    else:
        try:
            intervention = await asyncio.wait_for(
                state.pipeline.ingest_event(event, session),
                timeout=NAMED_HOOK_EVENT_PIPELINE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            intervention = None
    await _observe_cursor_continuation(event.event_id)
    return response


async def _cursor_observe_loop(stop: asyncio.Event) -> None:
    from pex_bridge.adapters.cursor_inbox import drain_inbox

    while not stop.is_set():
        try:
            for payload in drain_inbox(state.settings.data_dir):
                try:
                    await apply_cursor_hook(payload)
                except HTTPException:
                    continue
                except ValueError as exc:
                    if "event id collision" not in str(exc):
                        raise
                    logger.debug("Cursor observe inbox skipped a timestamp replay")
                except Exception:
                    logger.exception("Cursor observe inbox record failed")
        except Exception:
            logger.exception("Cursor observe inbox drain failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.25)
        except TimeoutError:
            pass


async def _overlay_expiry_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await state.pipeline.executor.expire_overlays()
        except Exception:
            logger.exception("Overlay TTL sweep failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=1)
        except TimeoutError:
            pass


def _supervisor_health() -> dict[str, Any]:
    from pex_supervisor.providers import describe_backend

    info = describe_backend()
    info["model_loaded"] = state.pipeline.model is not None
    return info


def _public_supervisor_health() -> dict[str, Any]:
    """Return only non-sensitive readiness facts on the unauthenticated endpoint."""

    info = _supervisor_health()
    return {
        key: info[key]
        for key in ("backend", "model_id", "model_loaded", "disabled")
        if key in info
    }


async def _bounded_adapter_probe(adapter: Any) -> AdapterCapabilities:
    """Probe one adapter without letting a dead integration stall the control plane."""

    try:
        return await asyncio.wait_for(
            adapter.probe(), timeout=ADAPTER_PROBE_TIMEOUT_SECONDS
        )
    except TimeoutError:
        logger.warning("Adapter %s probe timed out", getattr(adapter, "name", "unknown"))
    except Exception as exc:
        logger.warning(
            "Adapter %s probe failed (%s)",
            getattr(adapter, "name", "unknown"),
            type(exc).__name__,
        )
    return AdapterCapabilities(notes="Adapter probe unavailable or timed out.")


async def _bounded_discover_sessions(adapter: Any) -> list[Any]:
    try:
        return await asyncio.wait_for(
            adapter.discover_sessions(), timeout=ADAPTER_DISCOVERY_TIMEOUT_SECONDS
        )
    except TimeoutError as exc:
        raise HTTPException(504, "adapter session discovery timed out") from exc


def _is_reparse_point(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _windows_current_user_sid() -> str:
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    convert = advapi32.ConvertSidToStringSidW
    convert.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    convert.restype = wintypes.BOOL

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    class TOKEN_USER(ctypes.Structure):
        _fields_ = [("User", SID_AND_ATTRIBUTES)]

    token_handle = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token_handle)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token_handle, 1, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token_handle, 1, buf, size.value, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        token_user = ctypes.cast(buf, ctypes.POINTER(TOKEN_USER)).contents
        sid_string = wintypes.LPWSTR()
        if not convert(token_user.User.Sid, ctypes.byref(sid_string)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return sid_string.value or ""
        finally:
            kernel32.LocalFree(sid_string)
    finally:
        kernel32.CloseHandle(token_handle)


def _windows_path_from_descriptor(descriptor: int) -> str:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_path = kernel32.GetFinalPathNameByHandleW
    get_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_path.restype = wintypes.DWORD
    buf = ctypes.create_unicode_buffer(32768)
    length = get_path(msvcrt.get_osfhandle(descriptor), buf, len(buf), 0)
    if length == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    path = buf.value
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def _windows_named_sddl(path: str) -> str:
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    get_info = advapi32.GetNamedSecurityInfoW
    get_info.restype = wintypes.DWORD
    get_info.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    owner = ctypes.c_void_p()
    group = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    sacl = ctypes.c_void_p()
    security = ctypes.c_void_p()
    err = get_info(
        path,
        1,
        0x00000001 | 0x00000004,
        ctypes.byref(owner),
        ctypes.byref(group),
        ctypes.byref(dacl),
        ctypes.byref(sacl),
        ctypes.byref(security),
    )
    if err:
        raise OSError(err, "GetNamedSecurityInfoW failed for bridge token file")
    try:
        convert = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW
        convert.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(wintypes.ULONG),
        ]
        convert.restype = wintypes.BOOL
        text = wintypes.LPWSTR()
        if not convert(security, 1, 0x00000001 | 0x00000004, ctypes.byref(text), None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return text.value or ""
        finally:
            kernel32.LocalFree(text)
    finally:
        kernel32.LocalFree(security)


def _enforce_windows_owner_only_acl(descriptor: int) -> None:
    import ctypes
    from ctypes import wintypes

    sid = _windows_current_user_sid()
    if not sid:
        raise RuntimeError("bridge token file owner SID could not be determined")
    path = _windows_path_from_descriptor(descriptor)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    convert_sd = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert_sd.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.ULONG),
    ]
    convert_sd.restype = wintypes.BOOL
    security = ctypes.c_void_p()
    if not convert_sd(f"D:P(A;;FA;;;{sid})", 1, ctypes.byref(security), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        present = wintypes.BOOL()
        dacl = ctypes.c_void_p()
        defaulted = wintypes.BOOL()
        get_dacl = advapi32.GetSecurityDescriptorDacl
        get_dacl.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.BOOL),
        ]
        get_dacl.restype = wintypes.BOOL
        if not get_dacl(
            security, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        set_info = advapi32.SetNamedSecurityInfoW
        set_info.restype = wintypes.DWORD
        set_info.argtypes = [
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        err = set_info(
            ctypes.create_unicode_buffer(path),
            1,
            0x00000004 | 0x80000000,
            None,
            None,
            dacl,
            None,
        )
        if err:
            raise OSError(err, "SetNamedSecurityInfoW failed for bridge token file")
    finally:
        kernel32.LocalFree(security)

    compact = _windows_named_sddl(path).casefold().replace(" ", "")
    if f"(a;;fa;;;{sid.casefold()})" not in compact:
        raise RuntimeError("bridge token file ACL is not owner-only")
    if "d:p" not in compact and ":p(" not in compact:
        raise RuntimeError("bridge token file ACL is not protected from inheritance")
    if any(
        marker in compact
        for marker in (";;;wd)", ";;;bu)", ";;;s-1-1-0)", ";;;s-1-5-32-545)")
    ):
        raise RuntimeError("bridge token file ACL grants other users")


def _validate_token_descriptor(descriptor: int) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or _is_reparse_point(metadata):
        raise RuntimeError("bridge token file must be a regular file")
    if metadata.st_nlink != 1:
        raise RuntimeError("bridge token file must have exactly one link")
    if metadata.st_size > MAX_TOKEN_FILE_BYTES:
        raise RuntimeError("bridge token file exceeds its safety bound")
    if os.name != "nt":
        if metadata.st_uid != os.geteuid():
            raise RuntimeError("bridge token file must be owned by the current user")
        try:
            os.fchmod(descriptor, 0o600)
        except OSError as exc:
            raise RuntimeError(
                "bridge token file permissions could not be made owner-only"
            ) from exc
        metadata = os.fstat(descriptor)
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise RuntimeError("bridge token file permissions are not owner-only")
    else:
        try:
            _enforce_windows_owner_only_acl(descriptor)
        except OSError as exc:
            raise RuntimeError(
                "bridge token file permissions could not be made owner-only"
            ) from exc
    return metadata


def _open_token_parent(path: Path) -> int | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        before = os.lstat(path.parent)
    except OSError as exc:
        raise RuntimeError("bridge token directory is unavailable") from exc
    if not stat.S_ISDIR(before.st_mode) or _is_reparse_point(before):
        raise RuntimeError("bridge token directory must not be a link or reparse point")
    try:
        descriptor = (
            _open_windows_directory(path.parent)
            if os.name == "nt"
            else os.open(
                path.parent,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOINHERIT", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
        )
    except OSError as exc:
        raise RuntimeError("bridge token directory is unavailable") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) or not _same_file(before, opened):
            raise RuntimeError("bridge token directory changed while it was opened")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _open_windows_directory(path: Path) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.restype = wintypes.HANDLE
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    generic_read = 0x80000000
    share = 0x00000001 | 0x00000002 | 0x00000004
    open_existing = 3
    file_flag_backup_semantics = 0x02000000
    handle = create_file(
        str(path),
        generic_read,
        share,
        None,
        open_existing,
        file_flag_backup_semantics,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(int(handle), os.O_RDONLY)
    except OSError:
        kernel32.CloseHandle(handle)
        raise


def _token_dir_fd(parent_descriptor: int | None) -> int | None:
    if parent_descriptor is None or os.name == "nt":
        return None
    return parent_descriptor


def _token_path_stat(path: Path, parent_descriptor: int | None) -> os.stat_result:
    dir_fd = _token_dir_fd(parent_descriptor)
    if dir_fd is None:
        return os.lstat(path)
    return os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)


def _open_existing_token(path: Path, parent_descriptor: int | None) -> int:
    try:
        before = _token_path_stat(path, parent_descriptor)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise RuntimeError("bridge token file is unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or _is_reparse_point(before):
        raise RuntimeError("bridge token file must not be a link or reparse point")
    if not stat.S_ISREG(before.st_mode):
        raise RuntimeError("bridge token file must be a regular file")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    dir_fd = _token_dir_fd(parent_descriptor)
    target: str | Path = path if dir_fd is None else path.name
    try:
        descriptor = os.open(target, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise RuntimeError("bridge token file is unavailable") from exc
    try:
        opened = _validate_token_descriptor(descriptor)
        after = _token_path_stat(path, parent_descriptor)
        if (
            stat.S_ISLNK(after.st_mode)
            or _is_reparse_point(after)
            or not _same_file(before, opened)
            or not _same_file(after, opened)
        ):
            raise RuntimeError("bridge token file changed while it was opened")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _read_token_descriptor(descriptor: int) -> str:
    raw = bytearray()
    while len(raw) <= MAX_TOKEN_FILE_BYTES:
        chunk = os.read(descriptor, min(1024, MAX_TOKEN_FILE_BYTES + 1 - len(raw)))
        if not chunk:
            break
        raw.extend(chunk)
    if len(raw) > MAX_TOKEN_FILE_BYTES:
        raise RuntimeError("bridge token file exceeds its safety bound")
    try:
        token = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError("bridge token file must be valid UTF-8") from exc
    if not token:
        raise RuntimeError("bridge token file is empty")
    try:
        return validate_bridge_token(token, label="bridge token file")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def _load_or_create_bridge_token(path: Path) -> str:
    """Load or exclusively create a bounded token without following the file link."""

    parent_descriptor = _open_token_parent(path)
    descriptor: int | None = None
    try:
        try:
            descriptor = _open_existing_token(path, parent_descriptor)
        except FileNotFoundError:
            token = secrets.token_urlsafe(32)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOINHERIT", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            dir_fd = _token_dir_fd(parent_descriptor)
            target: str | Path = path if dir_fd is None else path.name
            try:
                descriptor = os.open(target, flags, 0o600, dir_fd=dir_fd)
            except FileExistsError:
                descriptor = _open_existing_token(path, parent_descriptor)
            else:
                opened = _validate_token_descriptor(descriptor)
                encoded = token.encode("ascii")
                written = 0
                while written < len(encoded):
                    count = os.write(descriptor, encoded[written:])
                    if count <= 0:
                        raise RuntimeError("bridge token file could not be written")
                    written += count
                os.fsync(descriptor)
                after = _token_path_stat(path, parent_descriptor)
                if not _same_file(opened, after):
                    raise RuntimeError("bridge token file changed while it was created")
                return token
        return _read_token_descriptor(descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


async def _require_token(authorization: str | None = Header(default=None)) -> None:
    if not state.settings.require_auth:
        return
    expected = state.token or ""
    if not expected:
        raise HTTPException(status_code=503, detail="bridge authentication is unavailable")
    scheme, separator, supplied = (authorization or "").partition(" ")
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not secrets.compare_digest(supplied, expected)
    ):
        raise HTTPException(status_code=401, detail="invalid token")


async def _require_operator_token(
    authorization: str | None = Header(default=None),
) -> OperatorActorEvidence:
    """Require the bridge operator bearer even when ordinary test auth is disabled."""

    if not state.settings.require_auth:
        raise HTTPException(
            status_code=403,
            detail="operator mutations require bridge authentication",
        )
    await _require_token(authorization)
    return OperatorActorEvidence(
        principal_id=_LOCAL_OPERATOR_PRINCIPAL,
        actor_assurance="bridge_bearer",
    )


async def _goal_control_actor(
    authorization: str | None = Header(default=None),
) -> OperatorActorEvidence | None:
    """Freeze production actor evidence while retaining explicit no-auth test fixtures."""

    if not state.settings.require_auth:
        return None
    return await _require_operator_token(authorization)


def _decode_websocket_token_protocol(protocol: str) -> str | None:
    """Decode one RFC-token-safe wrapper without weakening the bearer contract."""

    if not protocol.startswith(WEBSOCKET_TOKEN_PROTOCOL_PREFIX):
        return None
    encoded = protocol.removeprefix(WEBSOCKET_TOKEN_PROTOCOL_PREFIX)
    if not encoded or len(encoded) > 684 or any(
        not (char.isascii() and (char.isalnum() or char in "-_"))
        for char in encoded
    ):
        return None
    try:
        raw = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4),
            altchars=b"-_",
            validate=True,
        ).decode("ascii")
        return validate_bridge_token(raw, label="WebSocket bridge token")
    except (UnicodeDecodeError, ValueError, binascii.Error):
        return None


async def _require_hook_access(
    authorization: str | None = Header(default=None),
) -> HookPrincipal | None:
    """Accept only the operator bearer or a live digest-backed hook bearer."""

    if not state.settings.require_auth:
        return None
    expected = state.token or ""
    if not expected:
        raise HTTPException(503, "bridge authentication is unavailable")
    scheme, separator, supplied = (authorization or "").partition(" ")
    if not separator or scheme.casefold() != "bearer":
        raise HTTPException(401, "invalid token")
    if secrets.compare_digest(supplied, expected):
        return None
    try:
        checked_at = utcnow()
        record = await state.store.get_hook_credential_by_digest(
            digest_hook_token(supplied),
            now=checked_at,
        )
        if record is None:
            raise ValueError("inactive hook credential")
        return HookPrincipal.from_store_record(record, now=checked_at)
    except (TypeError, ValueError) as exc:
        raise HTTPException(401, "invalid token") from exc
    except Exception as exc:
        logger.exception("Hook credential authentication is unavailable")
        raise HTTPException(503, "bridge authentication is unavailable") from exc


async def _authorize_hook_route(
    principal: HookPrincipal | None,
    *,
    route: str,
    harness_type: HarnessType,
    session_id: str | None = None,
    vendor_session_id: str | None = None,
    project_id: str | None = None,
) -> None:
    if principal is None:
        return
    if not principal.authorizes(route) or principal.harness_type != harness_type:
        raise HTTPException(403, "hook credential does not authorize this route")
    if principal.is_bound and session_id is not None and principal.session_id != session_id:
        raise HTTPException(403, "hook credential session binding mismatch")
    if (
        principal.is_bound
        and vendor_session_id is not None
        and principal.vendor_session_id != vendor_session_id
    ):
        raise HTTPException(403, "hook credential vendor session binding mismatch")
    if principal.is_bound and project_id is not None:
        try:
            live_project_binding = await state.store.project_binding_for_authority(
                project_id
            )
        except (ProjectIdentityBlockedError, ValueError) as exc:
            raise HTTPException(403, "hook credential project binding mismatch") from exc
        if live_project_binding != principal.project_binding:
            raise HTTPException(403, "hook credential project binding mismatch")


def _hook_payload_binding(harness_type: HarnessType, payload: dict) -> tuple[str, str | None]:
    if harness_type == HarnessType.CURSOR:
        vendor_value = payload.get("conversation_id")
        roots = payload.get("workspace_roots")
        project_value = roots[0] if isinstance(roots, list) and roots else payload.get("cwd")
    elif harness_type == HarnessType.CLAUDE_CODE:
        vendor_value = (
            payload.get("session_id")
            or payload.get("conversation_id")
            or payload.get("sessionId")
        )
        roots = payload.get("cwd") or payload.get("workspace_roots")
        project_value = roots[0] if isinstance(roots, list) and roots else roots
    elif harness_type == HarnessType.QWEN:
        vendor_value = payload.get("session_id") or payload.get("sessionId")
        project_value = payload.get("cwd")
    elif harness_type == HarnessType.HERMES:
        vendor_value = payload.get("session_id") or payload.get("task_id")
        project_value = payload.get("cwd")
    else:
        raise HTTPException(403, "harness has no scoped hook route")
    if (
        not isinstance(vendor_value, str)
        or not vendor_value.strip()
        or len(vendor_value) > MAX_ID_CHARS
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in vendor_value)
    ):
        raise HTTPException(422, "hook payload has no valid vendor session identity")
    vendor_id = vendor_value.strip()
    project_id: str | None = None
    if project_value not in (None, ""):
        if (
            not isinstance(project_value, str)
            or not project_value.strip()
            or len(project_value) > MAX_PATH_CHARS
            or "\x00" in project_value
        ):
            raise HTTPException(422, "hook payload has no valid project identity")
        project_id = project_value
    return vendor_id, project_id


async def _authorize_hook_payload(
    principal: HookPrincipal | None,
    *,
    harness_type: HarnessType,
    payload: dict,
) -> HookPrincipal | None:
    if principal is None:
        return None
    vendor_id, project_id = _hook_payload_binding(harness_type, payload)
    await _authorize_hook_route(
        principal,
        route=f"hook:{harness_type.value}",
        harness_type=harness_type,
        session_id=f"{harness_type.value}:{vendor_id}",
        vendor_session_id=vendor_id,
        project_id=project_id,
    )
    if principal.is_bound:
        return principal
    if project_id is None:
        raise HTTPException(403, "bootstrap hook credential requires a project identity")
    candidate = HarnessSession(
        id=f"{harness_type.value}:{vendor_id}",
        harness_type=harness_type,
        vendor_session_id=vendor_id,
        project_id=project_id,
        cwd=project_id,
        status=SessionStatus.DISCOVERED,
        last_activity=utcnow(),
        metadata={"source": "authenticated_hook_bootstrap"},
    )
    try:
        record = await state.store.bind_hook_credential_session(
            principal.token_digest,
            candidate,
            bound_at=utcnow(),
        )
        return HookPrincipal.from_store_record(record, now=utcnow())
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


async def _bind_path_hook_principal(
    principal: HookPrincipal | None,
    *,
    harness_type: HarnessType,
    session_id: str,
) -> HookPrincipal | None:
    if principal is None or principal.is_bound:
        return principal
    prefix = f"{harness_type.value}:"
    if not session_id.startswith(prefix):
        raise HTTPException(403, "hook credential session binding mismatch")
    vendor_id = session_id.removeprefix(prefix)
    if (
        not vendor_id
        or len(vendor_id) > MAX_ID_CHARS
        or any(ord(char) < 0x21 or ord(char) == 0x7F for char in vendor_id)
    ):
        raise HTTPException(422, "hook route has no valid vendor session identity")
    candidate = HarnessSession(
        id=session_id,
        harness_type=harness_type,
        vendor_session_id=vendor_id,
        project_id=principal.project_id,
        cwd=principal.project_id,
        status=SessionStatus.DISCOVERED,
        last_activity=utcnow(),
        metadata={"source": "authenticated_hook_bootstrap"},
    )
    try:
        record = await state.store.bind_hook_credential_session(
            principal.token_digest,
            candidate,
            bound_at=utcnow(),
        )
        return HookPrincipal.from_store_record(record, now=utcnow())
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


async def _ask_context_items(goals: list[Goal]) -> list[Any]:
    """Load canonical context for Ask PEX without interrupting workers."""
    items: list[Any] = []
    for goal in goals[:8]:
        items.extend(
            await state.store.list_context_for_authority(
                goal.project_id,
                goal_id=goal.id,
                limit=80,
            )
        )
    return items


class _StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalIn(_StrictRequestModel):
    idempotency_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$",
    )
    project_id: str = Field(min_length=1, max_length=MAX_PATH_CHARS)
    title: str = Field(min_length=1, max_length=512)
    objective: str = Field(min_length=1, max_length=MAX_CONTROL_TEXT_CHARS)
    acceptance_criteria: list[GoalListItem] = Field(
        default_factory=list, max_length=MAX_GOAL_LIST_ITEMS
    )
    constraints: list[GoalListItem] = Field(default_factory=list, max_length=MAX_GOAL_LIST_ITEMS)
    preferences: list[GoalListItem] = Field(default_factory=list, max_length=MAX_GOAL_LIST_ITEMS)
    forbidden_outcomes: list[GoalListItem] = Field(
        default_factory=list, max_length=MAX_GOAL_LIST_ITEMS
    )
    non_goals: list[GoalListItem] = Field(default_factory=list, max_length=MAX_GOAL_LIST_ITEMS)
    evidence_requirements: list[GoalListItem] = Field(
        default_factory=list, max_length=MAX_GOAL_LIST_ITEMS
    )
    decisions: list[GoalListItem] = Field(default_factory=list, max_length=MAX_GOAL_LIST_ITEMS)
    rejected_approaches: list[GoalListItem] = Field(
        default_factory=list, max_length=MAX_GOAL_LIST_ITEMS
    )
    unresolved_questions: list[GoalListItem] = Field(
        default_factory=list, max_length=MAX_GOAL_LIST_ITEMS
    )
    priority: int = Field(default=0, ge=-1000, le=1000)
    deadline: datetime | None = None


class GoalPatch(_StrictRequestModel):
    idempotency_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$",
    )
    mode: Literal["update", "override"] = "update"
    expected_intent_revision: int | None = Field(default=None, ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=512)
    objective: str | None = Field(
        default=None, min_length=1, max_length=MAX_CONTROL_TEXT_CHARS
    )
    acceptance_criteria: list[GoalListItem] | None = Field(
        default=None, max_length=MAX_GOAL_LIST_ITEMS
    )
    constraints: list[GoalListItem] | None = Field(
        default=None, max_length=MAX_GOAL_LIST_ITEMS
    )
    preferences: list[GoalListItem] | None = Field(
        default=None, max_length=MAX_GOAL_LIST_ITEMS
    )
    forbidden_outcomes: list[GoalListItem] | None = Field(
        default=None, max_length=MAX_GOAL_LIST_ITEMS
    )
    non_goals: list[GoalListItem] | None = Field(
        default=None, max_length=MAX_GOAL_LIST_ITEMS
    )
    evidence_requirements: list[GoalListItem] | None = Field(
        default=None, max_length=MAX_GOAL_LIST_ITEMS
    )
    decisions: list[GoalListItem] | None = Field(default=None, max_length=MAX_GOAL_LIST_ITEMS)
    rejected_approaches: list[GoalListItem] | None = Field(
        default=None, max_length=MAX_GOAL_LIST_ITEMS
    )
    unresolved_questions: list[GoalListItem] | None = Field(
        default=None, max_length=MAX_GOAL_LIST_ITEMS
    )
    priority: int | None = Field(default=None, ge=-1000, le=1000)
    deadline: datetime | None = None
    paused: bool | None = None


_GOAL_EXTRACT_LIST_FIELDS = (
    "acceptance_criteria",
    "constraints",
    "non_goals",
    "preferences",
    "evidence_requirements",
)


class AttachIn(_StrictRequestModel):
    idempotency_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$",
    )
    goal_id: BoundedId
    replace_existing: bool = False
    expected_goal_id: BoundedId | None = None
    expected_control_revision: int | None = Field(default=None, ge=0)
    expected_goal_intent_revision: int | None = Field(default=None, ge=0)


def _goal_control_store_authority(
    actor: OperatorActorEvidence | None,
    idempotency_key: str | None,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    if actor is None or idempotency_key is None:
        return {}
    return {
        "principal_id": actor.principal_id,
        "actor_assurance": actor.actor_assurance,
        "idempotency_key": idempotency_key,
        "request_payload": request_payload,
    }


def _require_goal_control_idempotency(
    actor: OperatorActorEvidence | None,
    idempotency_key: str | None,
) -> None:
    if actor is not None and idempotency_key is None:
        raise HTTPException(
            428,
            {
                "code": "idempotency_key_required",
                "message": (
                    "idempotency_key is required for authenticated goal control mutation"
                ),
            },
        )


def _require_authenticated_attach_cas(
    actor: OperatorActorEvidence | None,
    body: AttachIn,
) -> None:
    if actor is None:
        return
    missing: list[str] = []
    if "expected_goal_id" not in body.model_fields_set:
        missing.append("expected_goal_id")
    if body.expected_control_revision is None:
        missing.append("expected_control_revision")
    if body.expected_goal_intent_revision is None:
        missing.append("expected_goal_intent_revision")
    if missing:
        raise HTTPException(
            428,
            {
                "code": "session_goal_attachment_cas_required",
                "message": f"authenticated attachment requires: {', '.join(missing)}",
            },
        )


async def _goal_control_replay(
    *,
    action_kind: str,
    actor: OperatorActorEvidence | None,
    idempotency_key: str | None,
    request_payload: dict[str, Any],
) -> dict[str, Any] | None:
    if actor is None or idempotency_key is None:
        return None
    return await state.store.get_goal_control_operation_replay(
        action_kind=action_kind,
        principal_id=actor.principal_id,
        actor_assurance=actor.actor_assurance,
        idempotency_key=idempotency_key,
        request_payload=request_payload,
    )


def _set_goal_control_response_headers(
    response: Response,
    payload: dict[str, Any],
    *,
    replayed: bool,
) -> None:
    operation = payload.get("operator_operation_receipt")
    if not isinstance(operation, dict):
        return
    operation_id = operation.get("operation_id")
    if not isinstance(operation_id, str) or not operation_id:
        raise RuntimeError("goal control response operation is invalid")
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    response.headers["PEX-Operation-Id"] = operation_id


class MessageIn(_StrictRequestModel):
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$",
    )
    text: str = Field(min_length=1, max_length=65_536)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("message must contain non-whitespace text without NUL bytes")
        return value


class UndoIn(_StrictRequestModel):
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$",
    )


def _overlay_revert_response(
    result: object,
    *,
    missing_status: int = 404,
) -> JSONResponse:
    """Expose only the executor's path-free canonical overlay receipt."""

    if not isinstance(result, dict):
        response = {
            "ok": False,
            "code": "overlay_revert_result_uncertain",
            "state": "delivery_uncertain",
            "replayed": False,
            "receipt": None,
        }
        return JSONResponse(status_code=502, content=response)

    raw_receipt = result.get("receipt")
    receipt = None
    if isinstance(raw_receipt, dict):
        raw_result = raw_receipt.get("result")
        receipt = {
            "operation_id": raw_receipt.get("operation_id"),
            "state": raw_receipt.get("state"),
            "version": raw_receipt.get("version"),
            "reserved_at": raw_receipt.get("reserved_at"),
            "dispatch_started_at": raw_receipt.get("dispatch_started_at"),
            "finished_at": raw_receipt.get("finished_at"),
            "result": dict(raw_result) if isinstance(raw_result, dict) else None,
        }
    response = {
        "ok": result.get("ok") is True,
        "code": str(result.get("code") or "overlay_revert_result_uncertain"),
        "state": str(result.get("state") or "delivery_uncertain"),
        "replayed": result.get("replayed") is True,
        "receipt": receipt,
    }
    code = response["code"]
    operation_state = response["state"]
    if operation_state == "delivered" and response["ok"] is True:
        status_code = 200
    elif operation_state in {"reserved", "dispatching"}:
        status_code = 202
    elif operation_state == "not_found" or code == "overlay_not_found":
        status_code = missing_status
    elif operation_state == "delivery_uncertain" or "uncertain" in code:
        status_code = 502
    elif (
        operation_state in {"failed", "skipped", "refused", "conflict"}
        or any(
            marker in code
            for marker in (
                "conflict",
                "invalid",
                "mismatch",
                "not_delivered",
                "refused",
            )
        )
    ):
        status_code = 409
    else:
        status_code = 502
    return JSONResponse(status_code=status_code, content=response)


class ProjectLocatorRegisterIn(_StrictRequestModel):
    legacy_project_id: str = Field(min_length=1, max_length=MAX_PATH_CHARS)
    locator: ProjectLocator

    @field_validator("legacy_project_id")
    @classmethod
    def validate_legacy_project_id(cls, value: str) -> str:
        if value != value.rstrip("\r\n") or any(
            category(char).startswith("C") for char in value
        ):
            raise ValueError("legacy project id must contain no control characters")
        return value


class ProjectIdentityResolveIn(_StrictRequestModel):
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$",
    )
    legacy_project_id: str = Field(min_length=1, max_length=MAX_PATH_CHARS)
    selected_identity_id: str = Field(pattern=r"^prj_[0-9a-f]{32}$")
    rationale: str = Field(min_length=1, max_length=2_000)

    @field_validator("legacy_project_id")
    @classmethod
    def validate_legacy_project_id(cls, value: str) -> str:
        if value != value.rstrip("\r\n") or any(
            category(char).startswith("C") for char in value
        ):
            raise ValueError("legacy project id must contain no control characters")
        return value

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        if value != value.strip() or any(category(char).startswith("C") for char in value):
            raise ValueError("rationale must be trimmed and contain no controls")
        return value


_LOCAL_OPERATOR_PRINCIPAL = "local_bridge_operator"


@dataclass(frozen=True, slots=True)
class OperatorActorEvidence:
    """Non-secret proof that the operator-only dependency accepted the bearer."""

    principal_id: str
    actor_assurance: str


def _public_operator_effect(effect: dict[str, Any]) -> dict[str, Any]:
    return {
        key: effect.get(key)
        for key in (
            "effect_id",
            "action_kind",
            "idempotency_key",
            "request_hash",
            "source_session_id",
            "target_session_id",
            "project_id",
            "goal_id",
            "state",
            "reserved_at",
            "dispatch_started_at",
            "finished_at",
            "updated_at",
            "result",
            "downstream_operation_id",
        )
    }


def _operator_effect_response(
    effect: dict[str, Any],
    *,
    replayed: bool,
) -> JSONResponse:
    state_name = str(effect.get("state") or "")
    status_code = {
        "delivered": 200,
        "reserved": 202,
        "dispatching": 202,
        "delivery_uncertain": 502,
        "failed": 409,
        "skipped": 409,
    }.get(state_name, 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": state_name == "delivered",
            "replayed": replayed,
            "status": state_name,
            "receipt": _public_operator_effect(effect),
        },
    )


class DecisionResolveIn(_StrictRequestModel):
    decision: str = Field(min_length=1, max_length=500)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        if value != value.strip() or any(category(char).startswith("C") for char in value):
            raise ValueError("decision must be trimmed and contain no controls")
        return value


class HandoffIn(ContextHandoffRequest):
    """Operator-facing form of the canonical context-handoff request."""


class AskIn(_StrictRequestModel):
    question: str = Field(
        default="what needs me?", min_length=1, max_length=MAX_CONTROL_TEXT_CHARS
    )


class DemoReplayIn(_StrictRequestModel):
    fixture: BoundedId


class DemoEventIn(_StrictRequestModel):
    event_type: EventType
    message: str | None = Field(default=None, max_length=MAX_CONTROL_TEXT_CHARS)
    command: str | None = Field(default=None, max_length=MAX_CONTROL_TEXT_CHARS)


class PluginHeartbeatIn(_StrictRequestModel):
    source: Literal["pex-opencode-plugin"]
    version: str | None = Field(default=None, max_length=128)
    directory: str | None = Field(default=None, max_length=MAX_PATH_CHARS)
    session_id: BoundedId | None = None


class HookBootstrapIn(_StrictRequestModel):
    harness_type: HarnessType
    project_id: BoundedPath


class PetSettingsIn(_StrictRequestModel):
    selected_id: str | None = Field(default=None, min_length=1, max_length=128)
    custom_name: str | None = Field(default=None, max_length=128)
    hue_shift: int | None = Field(default=None, ge=-360, le=360)
    scale: float | None = Field(default=None, ge=0.6, le=2.0)
    click_through: bool | None = None
    quiet: bool | None = None
    imported_codex_dir: str | None = Field(default=None, max_length=MAX_PATH_CHARS)


class ImportPetIn(_StrictRequestModel):
    directory: BoundedPath


class HatchIn(_StrictRequestModel):
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=4096)
    style_preset: Literal[
        "plush",
        "clay",
        "sticker",
        "flat-vector",
        "3d-toy",
        "auto",
    ] = "plush"
    pet_notes: str = Field(default="", max_length=8192)
    idempotency_key: str = Field(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$",
    )
    confirm_one_base_candidate_call: Literal[True]

    @field_validator("display_name", "description", "pet_notes")
    @classmethod
    def _validate_hatch_text(cls, value: str, info: Any) -> str:
        if value != value.strip() or any(
            category(char).startswith("C") for char in value
        ):
            raise ValueError(
                f"{info.field_name} must be canonical text without control characters"
            )
        return value


class SupervisorIn(_StrictRequestModel):
    expected_revision: int | None = Field(default=None, ge=0, le=2_147_483_647)
    provider: str | None = Field(default=None, max_length=256)
    model_id: str | None = Field(default=None, max_length=512)
    auth_mode: Literal[
        "api_key", "login", "local", "custom", "bedrock", "agentcore"
    ] | None = None
    protocol: Literal["openai", "anthropic"] | None = None
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: SecretStr | None = Field(default=None, max_length=16_384, repr=False)
    clear_api_key: bool = False
    use_environment_credentials: bool | None = None

    @model_validator(mode="after")
    def _one_credential_operation(self) -> SupervisorIn:
        supplied_key = self.api_key is not None
        operations = sum(
            (
                supplied_key,
                self.clear_api_key,
                self.use_environment_credentials is not None,
            )
        )
        if operations > 1:
            raise ValueError(
                "choose only one credential operation: api_key, clear_api_key, or "
                "use_environment_credentials"
            )
        return self


class SupervisorCatalogIn(_StrictRequestModel):
    provider: str | None = Field(default=None, max_length=256)


class SyntheticEventIn(_StrictRequestModel):
    session_id: BoundedId
    event_type: EventType
    message: str | None = Field(default=None, max_length=MAX_CONTROL_TEXT_CHARS)
    command: str | None = Field(default=None, max_length=MAX_CONTROL_TEXT_CHARS)
    tool_name: str | None = Field(default=None, max_length=512)
    file_paths: list[BoundedPath] = Field(
        default_factory=list, max_length=MAX_EVENT_FILE_PATHS
    )
    phase: str | None = Field(default=None, max_length=64)
    process_state: dict | None = None
    error: str | None = Field(default=None, max_length=MAX_CONTROL_TEXT_CHARS)


def _default_supervisor_auth(provider: str | None) -> str | None:
    if provider in {"ollama", "lmstudio", "llamacpp", "vllm"}:
        return "local"
    if provider == "custom":
        return "custom"
    if provider == "bedrock":
        return "bedrock"
    return "api_key" if provider else None


def _choice_runtime_config(choice: SupervisorChoice, api_key: str | None) -> Any:
    from pex_supervisor.providers import SupervisorRuntimeConfig

    return SupervisorRuntimeConfig(
        provider=choice.provider,
        model_id=choice.model_id,
        auth_mode=choice.auth_mode,
        protocol=choice.protocol,
        base_url=choice.base_url,
        credential_source=choice.credential_source,
        api_key=api_key,
    )


def _resolve_choice_secret(choice: SupervisorChoice) -> str | None:
    if choice.credential_source != "secret_store" or not choice.secret_ref:
        return None
    return state.supervisor_secret_store.get(
        choice.secret_ref,
        audience=choice.credential_audience(),
    )


def _activate_supervisor_choice(choice: SupervisorChoice | None) -> tuple[dict[str, Any], Any]:
    from pex_supervisor.providers import (
        configure_runtime,
        load_supervisor_model,
        validate_runtime_config,
    )

    if choice is None:
        info = configure_runtime(None)
        return info, load_supervisor_model()
    runtime = validate_runtime_config(
        _choice_runtime_config(choice, _resolve_choice_secret(choice))
    )
    model = load_supervisor_model(runtime)
    info = configure_runtime(runtime)
    return info, model


def _clean_patch_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned != value or any(char in value for char in ("\r", "\n", "\x00")):
        raise ValueError("configuration text must be canonical and single-line")
    return cleaned or None


def _supervisor_choice_from_patch(
    body: SupervisorIn,
    current: SupervisorChoice | None,
) -> tuple[SupervisorChoice, str | None, bool]:
    """Resolve a partial request into a full snapshot and optional staged key."""

    fields = body.model_fields_set
    previous = current or SupervisorChoice()
    provider = (
        _clean_patch_text(body.provider).casefold() if body.provider else None
    ) if "provider" in fields else previous.provider
    provider_changed = provider != previous.provider
    model_id = (
        _clean_patch_text(body.model_id)
        if "model_id" in fields
        else None
        if provider_changed
        else previous.model_id
    )
    base_url = (
        _clean_patch_text(body.base_url)
        if "base_url" in fields
        else None
        if provider_changed
        else previous.base_url
    )
    if provider is None and base_url:
        provider = "custom"
        provider_changed = provider != previous.provider
    if provider is not None and base_url is None:
        from pex_supervisor.providers import PROVIDERS

        spec = PROVIDERS.get(provider)
        if spec is not None:
            base_url = spec.base_url
    auth_mode = (
        body.auth_mode
        if "auth_mode" in fields
        else _default_supervisor_auth(provider)
        if provider_changed
        else previous.auth_mode or _default_supervisor_auth(provider)
    )
    protocol = (
        body.protocol
        if "protocol" in fields
        else ("openai" if provider == "custom" else None)
        if provider_changed
        else previous.protocol
    )
    revision = previous.revision + 1 if current is not None else 1
    provisional = SupervisorChoice(
        revision=revision,
        provider=provider,
        model_id=model_id,
        auth_mode=auth_mode,
        protocol=protocol,
        base_url=base_url,
        credential_source="none",
    )

    supplied_secret = body.api_key.get_secret_value() if body.api_key is not None else None
    explicit_credential = any(
        name in fields
        for name in ("api_key", "clear_api_key", "use_environment_credentials")
    )
    staged_secret: str | None = None
    retire_previous = False
    source: Literal["none", "environment", "secret_store"]
    secret_ref: str | None = None

    if supplied_secret is not None:
        if not provider or auth_mode in {"login", "local", "bedrock", "agentcore"}:
            raise ValueError("the selected supervisor auth mode does not accept an API key")
        public_values = {value for value in (provider, model_id, base_url) if value}
        if supplied_secret in public_values:
            raise ValueError("api_key must not be reused as a public configuration value")
        staged_secret = supplied_secret
        source = "secret_store"
        retire_previous = previous.secret_ref is not None
    elif body.use_environment_credentials is True:
        source = "environment"
        retire_previous = previous.secret_ref is not None
    elif body.clear_api_key or body.use_environment_credentials is False:
        source = "none"
        retire_previous = previous.secret_ref is not None
    elif (
        not explicit_credential
        and previous.secret_ref
        and provisional.audience() == previous.audience()
    ):
        source = "secret_store"
        secret_ref = previous.secret_ref
    elif not explicit_credential and previous.credential_source == "environment":
        source = "environment" if provisional.audience() == previous.audience() else "none"
    else:
        source = "none"
        retire_previous = previous.secret_ref is not None

    if auth_mode in {"login", "local"}:
        source = "none"
        secret_ref = None
        retire_previous = previous.secret_ref is not None
    elif auth_mode in {"bedrock", "agentcore"}:
        source = "environment"
        secret_ref = None
        retire_previous = previous.secret_ref is not None

    desired = SupervisorChoice.model_validate(
        {
            **provisional.model_dump(),
            "credential_source": "none" if staged_secret is not None else source,
            "secret_ref": None if staged_secret is not None else secret_ref,
        }
    )
    return desired, staged_secret, retire_previous


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as cleanup:
        state_lock = _BridgeStateLock(state.store.path)
        state_lock.acquire()
        cleanup.callback(state_lock.release)
        if state.codex_shared_attachments.closed:
            from pex_bridge.codex_shared_attach import SharedCodexAttachments

            state.codex_shared_attachments = SharedCodexAttachments()
        cleanup.push_async_callback(state.store.close)
        await state.store.connect()
        recovered_operator_effects = await state.store.recover_interrupted_operator_effects()
        if recovered_operator_effects:
            logger.warning(
                "Sealed %d prior-process operator dispatches as delivery-uncertain",
                recovered_operator_effects,
            )
        recovered_overlay_operations = (
            await state.store.recover_interrupted_overlay_operations()
        )
        if recovered_overlay_operations:
            logger.warning(
                "Sealed %d prior-process overlay dispatches as delivery-uncertain",
                recovered_overlay_operations,
            )
        cleanup.push_async_callback(_shutdown_runtime_resources)

        if state.settings.require_auth:
            configured_token = (state.token or state.settings.token or "").strip()
            state.token = (
                validate_bridge_token(configured_token)
                if configured_token
                else _load_or_create_bridge_token(state.settings.token_path)
            )
            state.settings.token = None
            from pex_bridge.adapters.cursor import set_internal_bridge_token

            set_internal_bridge_token(state.token)
        else:
            state.token = None
        pet_file = state.settings.data_dir / "pet.json"
        preserve_invalid_pet_file = False
        if pet_file.exists():
            try:
                state.pet_settings = PetSettings.model_validate(
                    _strict_json_loads(
                        _read_bounded_utf8(
                            pet_file,
                            MAX_PET_SETTINGS_BYTES,
                            "pet settings file",
                        )
                    )
                )
            except (OSError, ValueError) as exc:
                preserve_invalid_pet_file = True
                state.pet_settings = PetSettings()
                logger.warning(
                    "Pet settings were invalid and were preserved unchanged (%s)",
                    type(exc).__name__,
                )
            state.pet_path = pet_file
        from pex_bridge.pets import maybe_import_codex_home

        state.pet_settings = maybe_import_codex_home(state.pet_settings)
        if state.pet_settings.selected_id not in catalog_by_id(state.pet_settings):
            state.pet_settings.selected_id = STARTERS[0].id
        state.pet_path = pet_file
        pet_file.parent.mkdir(parents=True, exist_ok=True)
        if not preserve_invalid_pet_file:
            _atomic_write_text(pet_file, state.pet_settings.model_dump_json(indent=2))
        state.bus.subscribe(state.broadcast)
        from pex_bridge.adapters.attach import attach_from_settings

        await attach_from_settings(state.adapters, state.settings)
        choice_file = state.settings.data_dir / "supervisor.json"
        try:
            state.supervisor_choice = load_supervisor_choice(choice_file)
            _info, state.pipeline.model = _activate_supervisor_choice(
                state.supervisor_choice
            )
            state.supervisor_error = (
                None
                if state.pipeline.model is not None or state.supervisor_choice is None
                else "SupervisorUnavailable"
            )
        except (OSError, ValueError, SupervisorSecretStoreError) as exc:
            state.pipeline.model = None
            state.supervisor_choice = None
            state.supervisor_error = type(exc).__name__
            logger.error(
                "Saved supervisor configuration failed closed (%s)", type(exc).__name__
            )
        except Exception as exc:
            state.pipeline.model = None
            state.supervisor_error = type(exc).__name__
            logger.error(
                "Supervisor provider failed to load (%s); deterministic supervision remains active",
                type(exc).__name__,
            )

        recovered_events = await state.pipeline.recover_unfinished_events()
        if recovered_events:
            logger.info(
                "Recovered %d unfinished accepted events before starting adapter pumps",
                len(recovered_events),
            )
        _start_event_pumps()

        await cleanup.enter_async_context(app.state.pex_mcp.session_manager.run())

        overlay_expiry_stop = asyncio.Event()
        overlay_expiry_task = asyncio.create_task(
            _overlay_expiry_loop(overlay_expiry_stop)
        )
        cleanup.push_async_callback(
            _stop_runtime_loop,
            overlay_expiry_stop,
            overlay_expiry_task,
            name="Overlay expiry loop",
        )

        cursor_observe_stop = asyncio.Event()
        cursor_observe_task = asyncio.create_task(
            _cursor_observe_loop(cursor_observe_stop)
        )
        cleanup.push_async_callback(
            _stop_runtime_loop,
            cursor_observe_stop,
            cursor_observe_task,
            name="Cursor observe loop",
        )

        yield


def create_app() -> FastAPI:
    from pex_bridge.mcp_server import build_mcp_server

    pex_mcp, pex_mcp_app = build_mcp_server()
    app = FastAPI(title="PEX Bridge", version="0.1.0", lifespan=lifespan)
    from pex_bridge.codex_shared_attach import register_shared_codex_routes

    register_shared_codex_routes(app, state, _require_token, _require_operator_token)
    app.state.pex_mcp = pex_mcp

    @app.exception_handler(RequestValidationError)
    async def sanitized_request_validation(_request: Any, exc: RequestValidationError):
        """Return validation structure without echoing attacker-controlled inputs."""

        errors = []
        for error in exc.errors():
            errors.append(
                {
                    key: value
                    for key, value in error.items()
                    if key not in {"input", "ctx", "url"}
                }
            )
        return JSONResponse(status_code=422, content={"detail": errors})

    app.add_middleware(TrustedLoopbackHostMiddleware)
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(TRUSTED_UI_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )
    app.add_middleware(
        TrustedMutationOriginMiddleware,
        allowed_origins=TRUSTED_UI_ORIGINS,
    )
    app.mount("/mcp", MCPTokenMiddleware(pex_mcp_app))

    @app.exception_handler(ProjectIdentityBlockedError)
    async def project_identity_blocked(_request: Any, exc: ProjectIdentityBlockedError):
        """Expose typed quarantine/unresolved gates without turning them into 500s."""

        return JSONResponse(
            status_code=409,
            content={"detail": {"code": exc.code, "message": str(exc)}},
        )

    @app.get("/health/live")
    async def liveness():
        """Cheap public process liveness; callers must not treat it as identity proof."""
        return {"ok": True, "service": "pex-bridge"}

    @app.get("/health/identity")
    async def identity(
        challenge: Annotated[
            str,
            Query(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
        ],
    ):
        """Prove bridge identity without sending the bearer token to the port owner."""

        if not state.settings.require_auth or not state.token:
            raise HTTPException(503, "bridge identity proof is unavailable")
        proof = hmac.new(
            state.token.encode("utf-8"),
            challenge.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "ok": True,
            "service": "pex-bridge",
            "challenge": challenge,
            "proof": proof,
        }

    @app.get("/health")
    async def health(_: None = Depends(_require_token)):
        adapters = state.adapters.all()
        capabilities = await asyncio.gather(
            *[_bounded_adapter_probe(adapter) for adapter in adapters]
        )
        attached = [
            adapter.name
            for adapter, caps in zip(adapters, capabilities, strict=True)
            if caps.support_label.value in {"deep", "strong", "basic"}
            and caps.trust_level > 0
        ]
        return {
            "ok": True,
            "service": "pex-bridge",
            "attached": attached,
            "supervisor": "degraded" if state.supervisor_error else "ready",
            "supervisor_error": state.supervisor_error,
            "supervisor_backend": _public_supervisor_health(),
        }

    @app.get("/v1/supervisor")
    async def get_supervisor(_: None = Depends(_require_token)):
        from pex_supervisor.catalog import catalog as model_catalog

        info = _supervisor_health()
        # First-run authority is an explicit revision, not a client-side guess
        # from missing fields or an unavailable configuration response.
        info["revision"] = 0
        if state.supervisor_choice is not None:
            try:
                stored_key_present = bool(_resolve_choice_secret(state.supervisor_choice))
            except SupervisorSecretStoreError:
                stored_key_present = False
            info.update(
                state.supervisor_choice.public_dict(
                    has_api_key=stored_key_present or bool(info.get("has_api_key"))
                )
            )
            info["backend"] = state.supervisor_choice.provider
        info["catalog"] = model_catalog()
        info["model_loaded"] = state.pipeline.model is not None
        info["note"] = (
            "Credentials stay in the selected local source. This response never "
            "includes credentials or secret references."
        )
        return info

    @app.patch("/v1/supervisor")
    async def patch_supervisor(body: SupervisorIn, _: None = Depends(_require_token)):
        from pex_supervisor.catalog import catalog as model_catalog
        from pex_supervisor.providers import (
            configure_runtime,
            current_runtime_config,
            describe_backend,
            load_supervisor_model,
            validate_runtime_config,
        )

        async with state.supervisor_config_lock:
            current = state.supervisor_choice
            current_revision = current.revision if current is not None else 0
            if (
                body.expected_revision is not None
                and body.expected_revision != current_revision
            ):
                raise HTTPException(409, "supervisor configuration revision changed")
            old_model = state.pipeline.model
            old_runtime = current_runtime_config()
            staged_ref: str | None = None
            retire_previous = False
            try:
                desired, staged_secret, retire_previous = _supervisor_choice_from_patch(
                    body, current
                )
                if staged_secret is not None:
                    staged_ref = state.supervisor_secret_store.put(
                        staged_secret,
                        audience=desired.credential_audience(),
                    )
                    desired = SupervisorChoice.model_validate(
                        {
                            **desired.model_dump(exclude={"secret_ref"}),
                            "credential_source": "secret_store",
                            "secret_ref": staged_ref,
                        }
                    )
                api_key = _resolve_choice_secret(desired)
                if desired.auth_mode == "api_key" and not api_key:
                    if desired.credential_source != "environment":
                        raise ValueError("api_key auth requires a credential source")
                candidate_runtime = validate_runtime_config(
                    _choice_runtime_config(desired, api_key)
                )
                candidate_model = load_supervisor_model(candidate_runtime)
                if desired.auth_mode == "api_key" and candidate_model is None:
                    raise ValueError("the selected credential or provider is unavailable")
                save_supervisor_choice(
                    state.settings.data_dir / "supervisor.json",
                    desired,
                )
                configure_runtime(candidate_runtime)
            except (OSError, ValueError, SupervisorSecretStoreError) as exc:
                configure_runtime(old_runtime)
                state.pipeline.model = old_model
                if staged_ref is not None:
                    try:
                        state.supervisor_secret_store.delete(staged_ref)
                    except SupervisorSecretStoreError:
                        logger.error("Could not retire an uncommitted supervisor credential")
                if isinstance(exc, SupervisorSecretStoreError):
                    raise HTTPException(503, "supervisor secret store unavailable") from None
                if isinstance(exc, OSError):
                    raise HTTPException(
                        503, "supervisor configuration storage unavailable"
                    ) from None
                raise HTTPException(400, "invalid supervisor configuration") from None
            except Exception as exc:
                configure_runtime(old_runtime)
                state.pipeline.model = old_model
                if staged_ref is not None:
                    try:
                        state.supervisor_secret_store.delete(staged_ref)
                    except SupervisorSecretStoreError:
                        logger.error("Could not retire an uncommitted supervisor credential")
                logger.error("Supervisor configuration was not committed (%s)", type(exc).__name__)
                raise HTTPException(409, "supervisor model could not be constructed") from None

            state.supervisor_choice = desired
            state.pipeline.model = candidate_model
            state.supervisor_error = (
                None if candidate_model is not None else "SupervisorUnavailable"
            )
            if (
                retire_previous
                and current is not None
                and current.secret_ref
                and current.secret_ref != desired.secret_ref
            ):
                try:
                    state.supervisor_secret_store.delete(current.secret_ref)
                except SupervisorSecretStoreError:
                    logger.error("Could not retire the previous supervisor credential")

            info = describe_backend()
            info.update(
                desired.public_dict(
                    has_api_key=bool(api_key) or bool(info.get("has_api_key"))
                )
            )
            info["backend"] = desired.provider
            info["model_loaded"] = candidate_model is not None
            info["catalog"] = model_catalog()
            info["note"] = (
                "Credentials stay in the selected local source. This response never "
                "includes credentials or secret references."
            )
            return info

    @app.post("/v1/supervisor/catalog/refresh")
    async def refresh_supervisor_catalog(
        body: SupervisorCatalogIn,
        _: None = Depends(_require_token),
    ):
        from pex_supervisor.providers import (
            ModelCatalogRefreshError,
            refresh_model_catalog,
        )

        try:
            return await asyncio.to_thread(refresh_model_catalog, body.provider)
        except ModelCatalogRefreshError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/v1/channels")
    async def list_channels(_: None = Depends(_require_token)):
        pipeline = state.pipeline
        if pipeline is None or getattr(pipeline, "channels", None) is None:
            return {
                "attention_policy": "human_decisions_only",
                "channels": [],
            }
        return pipeline.channels.status()

    @app.get("/v1/discover")
    async def discover(_: None = Depends(_require_token)):
        from pex_bridge.adapters.discover import probe_local_harnesses

        found = await probe_local_harnesses()
        present = {item["name"] for item in found if item.get("kind") == "desktop"}
        from pex_bridge.adapters.desktop import DESKTOP_APPS

        not_running = sorted(
            app["name"] for app in DESKTOP_APPS if app["name"] not in present
        )
        return {"found": found, "not_running": not_running}

    @app.post("/v1/discover/attach")
    async def discover_attach(body: dict, _: None = Depends(_require_token)):
        from pex_bridge.adapters.attach import (
            _bounded_secret,
            _loopback_http_origin,
            opencode_basic_auth,
        )
        from pex_bridge.adapters.discover import prefer_attach_match, probe_local_harnesses
        from pex_bridge.adapters.http_json import LiveHttpTransport

        name = str(body.get("name") or "")
        kind = body.get("kind")
        found = await probe_local_harnesses()
        if name == "codex" and kind != "stdio":
            match = prefer_attach_match(found, name, "desktop")
            if match is None:
                raise HTTPException(
                    400,
                    (
                        "ChatGPT.exe is observe/focus only. Isolated App Server requires "
                        "kind=stdio or POST /v1/adapters/codex/attach."
                    ),
                )
        else:
            match = prefer_attach_match(found, name, kind)
        if match is None:
            raise HTTPException(404, "no local desktop app or daemon found")
        adapter = state.adapters.get(name)
        if adapter is None:
            raise HTTPException(404, "adapter not found")
        if match.get("kind") == "desktop":
            if name == "cursor":
                install_hooks = body.get("install_hooks") is True
                path = _install_cursor_hooks_or_error() if install_hooks else None
                sessions = await _bounded_discover_sessions(adapter)
                caps = await _bounded_adapter_probe(adapter)
                return {
                    "ok": True,
                    "name": name,
                    "kind": "desktop",
                    "hooks": str(path) if path else None,
                    "support": caps.support_label.value,
                    "sessions": len(sessions),
                    "note": (
                        "Installed fail-open Cursor observe hooks (JSONL drop, timeout 3, "
                        "no failClosed). Edits, shells, and subagent rollouts are not gated. "
                        "CLI ACP was not spawned."
                        if install_hooks
                        else (
                            "Observed an already-running Cursor.exe. Hooks were not "
                            "installed; the editor was not restarted or blocked."
                        )
                    ),
                }
            if name == "codex":
                sessions = await _bounded_discover_sessions(adapter)
                caps = await _bounded_adapter_probe(adapter)
                return {
                    "ok": True,
                    "name": name,
                    "kind": "desktop",
                    "support": caps.support_label.value,
                    "sessions": len(sessions),
                    "note": (
                        "ChatGPT.exe is observe/focus only. Isolated App Server is "
                        "POST /v1/adapters/codex/attach or discover attach with kind=stdio."
                    ),
                }
            sessions = await _bounded_discover_sessions(adapter)
            caps = await _bounded_adapter_probe(adapter)
            return {
                "ok": True,
                "name": name,
                "kind": "desktop",
                "support": caps.support_label.value,
                "sessions": len(sessions),
                "note": match.get("surface"),
            }
        if match.get("kind") == "cli":
            caps = await _bounded_adapter_probe(adapter)
            return {
                "ok": True,
                "name": name,
                "kind": "cli",
                "bin": match.get("bin"),
                "support": caps.support_label.value,
                "note": match.get("surface"),
            }
        if match.get("kind") in {"stdio", "acp"}:
            if name == "cursor":
                raise HTTPException(
                    400,
                    (
                        "Cursor desktop uses ~/.cursor/hooks.json. "
                        "The leftover cursor-agent CLI is not used."
                    ),
                )
            elif name == "codex":
                caps = await _attach_isolated_codex(match["bin"])
            elif name in {"hermes", "kimi", "omp"}:
                from pex_bridge.adapters.acp_client import StdioAcpTransport
                from pex_bridge.adapters.hermes_bin import acp_command as hermes_acp

                command = hermes_acp(match["bin"]) if name == "hermes" else [match["bin"], "acp"]
                caps = await _attach_verified_acp(adapter, StdioAcpTransport(command), body)
            elif name == "grok_build":
                from pex_bridge.adapters.acp_client import StdioAcpTransport
                from pex_bridge.adapters.grok_build_bin import acp_command as grok_acp

                caps = await _attach_verified_acp(
                    adapter,
                    StdioAcpTransport(grok_acp(match["bin"])),
                    body,
                )
            else:
                raise HTTPException(400, f"no stdio/ACP attach path for {name}")
            return {
                "ok": True,
                "name": name,
                "kind": match.get("kind"),
                "bin": match["bin"],
                "support": caps.support_label.value,
                **({"isolated": True, "existing_worker": False} if name == "codex" else {}),
            }
        if not hasattr(adapter, "attach_transport"):
            raise HTTPException(400, "adapter cannot attach HTTP")
        try:
            base_url = _loopback_http_origin(match["base_url"], name)
            if name == "opencode":
                if body.get("token"):
                    raise ValueError("OpenCode uses Basic auth, not a bearer token")
                transport = LiveHttpTransport(
                    base_url,
                    auth=opencode_basic_auth(body.get("username"), body.get("password")),
                )
            elif name == "qwen":
                transport = LiveHttpTransport(
                    base_url,
                    token=_bounded_secret(body.get("token")),
                )
            else:
                raise ValueError(f"no verified local HTTP attach path for {name}")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            caps = await _attach_verified_http_transport(adapter, transport)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        _start_event_pumps()
        return {
            "ok": True,
            "name": name,
            "base_url": match["base_url"],
            "support": caps.support_label.value,
        }

    @app.post("/v1/adapters/{name}/attach")
    async def attach_adapter(name: str, body: dict, _: None = Depends(_require_token)):
        from pex_bridge.adapters.attach import (
            _bounded_secret,
            _https_origin,
            _loopback_http_origin,
            opencode_basic_auth,
        )
        from pex_bridge.adapters.codex_bin import resolve_codex_bin
        from pex_bridge.adapters.http_json import LiveHttpTransport

        adapter = state.adapters.get(name)
        if adapter is None:
            raise HTTPException(404, "adapter not found")
        if name in {"kimi", "hermes", "omp"}:
            import shutil

            from pex_bridge.adapters.acp_client import StdioAcpTransport
            from pex_bridge.adapters.hermes_bin import acp_command as hermes_acp
            from pex_bridge.adapters.hermes_bin import resolve_hermes

            resolved = resolve_hermes() if name == "hermes" else shutil.which(name)
            try:
                binary = _resolved_attach_binary(body.get("bin"), resolved, name)
            except (OSError, ValueError) as exc:
                raise HTTPException(400, str(exc)) from exc
            command = hermes_acp(binary) if name == "hermes" else [binary, "acp"]
            caps = await _attach_verified_acp(adapter, StdioAcpTransport(command), body)
            return {
                "ok": True,
                "name": name,
                "kind": "acp",
                "bin": binary,
                "support": caps.support_label.value,
            }
        if name == "grok_build":
            from pex_bridge.adapters.acp_client import StdioAcpTransport
            from pex_bridge.adapters.grok_build_bin import acp_command as grok_acp
            from pex_bridge.adapters.grok_build_bin import resolve_grok_build

            try:
                binary = _resolved_attach_binary(
                    body.get("bin"),
                    resolve_grok_build(),
                    "Grok Build",
                )
            except (OSError, ValueError) as exc:
                raise HTTPException(400, str(exc)) from exc
            caps = await _attach_verified_acp(
                adapter,
                StdioAcpTransport(grok_acp(binary)),
                body,
            )
            return {
                "ok": True,
                "name": name,
                "kind": "acp",
                "bin": binary,
                "command": grok_acp(binary),
                "support": caps.support_label.value,
                "note": "Official ACP is grok agent stdio. This is Grok Build, not Grok Bot.",
            }
        if name == "cursor":
            if body.get("kind") == "acp":
                raise HTTPException(
                    400,
                    (
                        "Cursor ACP CLI is not auto-installed. "
                        "Desktop control is ~/.cursor/hooks.json."
                    ),
                )
            install_hooks = body.get("install_hooks") is True
            path = _install_cursor_hooks_or_error() if install_hooks else None
            sessions = await _bounded_discover_sessions(adapter)
            caps = await _bounded_adapter_probe(adapter)
            return {
                "ok": True,
                "name": name,
                "kind": "desktop",
                "hooks": str(path) if path else None,
                "support": caps.support_label.value,
                "sessions": len(sessions),
                "note": (
                    "Installed fail-open Cursor observe hooks. No cursor-agent CLI was spawned."
                    if install_hooks
                    else (
                        "Observed an already-running Cursor.exe. Hooks were not "
                        "installed; the editor was not restarted or blocked."
                    )
                ),
            }
        if name == "codex":
            try:
                binary = _resolved_attach_binary(
                    body.get("bin"),
                    resolve_codex_bin(),
                    "Codex",
                )
            except (OSError, ValueError) as exc:
                raise HTTPException(400, str(exc)) from exc
            caps = await _attach_isolated_codex(binary)
            return {
                "ok": True,
                "name": name,
                "kind": "stdio",
                "bin": binary,
                "support": caps.support_label.value,
                "isolated": True,
                "existing_worker": False,
            }
        if name not in {"opencode", "qwen", "devin"} or not hasattr(
            adapter, "attach_transport"
        ):
            raise HTTPException(400, f"no verified HTTP attach path for {name}")
        try:
            if name == "opencode":
                if body.get("token"):
                    raise ValueError("OpenCode uses Basic auth, not a bearer token")
                url = _loopback_http_origin(body.get("url"), "OpenCode")
                transport = LiveHttpTransport(
                    url,
                    auth=opencode_basic_auth(body.get("username"), body.get("password")),
                )
            elif name == "qwen":
                url = _loopback_http_origin(body.get("url"), "Qwen")
                transport = LiveHttpTransport(
                    url,
                    token=_bounded_secret(body.get("token")),
                )
            else:
                url = _https_origin(body.get("url"), "Devin")
                token = _bounded_secret(body.get("token"))
                org_id = str(body.get("org_id") or "").strip()
                if token is None:
                    raise ValueError("Devin bearer token is required")
                if not org_id or len(org_id) > 256:
                    raise ValueError("Devin org_id is required and must be at most 256 characters")
                transport = LiveHttpTransport(url, token=token)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            caps = await _attach_verified_http_transport(
                adapter,
                transport,
                org_id=org_id if name == "devin" else None,
            )
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        _start_event_pumps()
        return {"ok": True, "name": name, "support": caps.support_label.value}

    @app.get("/v1/goals")
    async def list_goals(
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        _: None = Depends(_require_token),
    ):
        return await state.store.list_goal_intent_views_page(limit=limit, offset=offset)

    @app.post("/v1/project-identities/locators")
    async def register_project_locator(
        body: ProjectLocatorRegisterIn,
        _: None = Depends(_require_operator_token),
    ):
        """Register operator-observed typed identity evidence for one legacy key."""

        try:
            result = await state.store.register_project_locator(
                legacy_project_id=body.legacy_project_id,
                locator=body.locator,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        outcome = str(result.get("outcome") or "")
        return {
            **result,
            "replayed": (
                True if outcome == "replayed" else False if outcome == "created" else None
            ),
            "project_identity_status": result["binding"]["status"],
        }

    @app.get("/v1/project-identities/conflicts")
    async def list_project_identity_conflicts(
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        _: None = Depends(_require_operator_token),
    ):
        return await state.store.list_project_identity_conflicts_page(
            limit=limit,
            offset=offset,
        )

    @app.get("/v1/project-identities/conflict")
    async def get_project_identity_conflict(
        legacy_project_id: Annotated[str, Query(min_length=1, max_length=MAX_PATH_CHARS)],
        candidate_limit: int = Query(default=100, ge=1, le=200),
        candidate_offset: int = Query(default=0, ge=0, le=1_000_000),
        _: None = Depends(_require_operator_token),
    ):
        try:
            conflict = await state.store.get_project_identity_conflict(
                legacy_project_id,
                candidate_limit=candidate_limit,
                candidate_offset=candidate_offset,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if conflict is None:
            raise HTTPException(404, "project identity conflict not found")
        return conflict

    @app.get("/v1/project-identities/status")
    async def get_project_identity_status(
        legacy_project_id: Annotated[str, Query(min_length=1, max_length=MAX_PATH_CHARS)],
        candidate_limit: int = Query(default=100, ge=1, le=200),
        candidate_offset: int = Query(default=0, ge=0, le=1_000_000),
        _: None = Depends(_require_operator_token),
    ):
        try:
            return await state.store.get_project_identity_status(
                legacy_project_id,
                candidate_limit=candidate_limit,
                candidate_offset=candidate_offset,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/v1/project-identities/resolve")
    async def resolve_project_identity_conflict(
        body: ProjectIdentityResolveIn,
        _: None = Depends(_require_operator_token),
    ):
        resolution_id = stable_operator_effect_id(
            _LOCAL_OPERATOR_PRINCIPAL,
            "resolve_project_identity",
            body.idempotency_key,
        )
        try:
            result = await state.store.resolve_project_identity_conflict(
                resolution_id=resolution_id,
                legacy_project_id=body.legacy_project_id,
                selected_identity_id=body.selected_identity_id,
                resolved_by=_LOCAL_OPERATOR_PRINCIPAL,
                rationale=body.rationale,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            **result,
            "current_status": result["binding"]["status"],
            "fresh_credentials_required": True,
        }

    @app.get("/v1/pet")
    async def pet(_: None = Depends(_require_token)):
        return await state.live_pet()

    @app.get("/v1/pets")
    async def list_pets(_: None = Depends(_require_token)):
        resolved_catalog = catalog(state.pet_settings)
        starter_ids = set(starters_by_id())
        return {
            "starters": [
                _public_pet_definition(p) for p in resolved_catalog if p.id in starter_ids
            ],
            "catalog": [_public_pet_definition(p) for p in resolved_catalog],
            "settings": _public_pet_settings(state.pet_settings),
            "hatch": describe_hatch_backend(),
            "codex_contract": {
                "spriteVersionNumber": 2,
                "cell": [192, 208],
                "atlas": [1536, 2288],
                "rows": [
                    "idle",
                    "running-right",
                    "running-left",
                    "waving",
                    "jumping",
                    "failed",
                    "waiting",
                    "running",
                    "review",
                    "look-9",
                    "look-10",
                ],
            },
        }

    @app.get("/v1/pets/{pet_id}/spritesheet")
    async def pet_spritesheet(pet_id: str, _: None = Depends(_require_token)):
        chosen = catalog_by_id(state.pet_settings).get(pet_id)
        if chosen is None:
            raise HTTPException(404, "unknown pet")
        from pathlib import Path

        if chosen.spritesheet:
            sheet = Path(chosen.spritesheet)
            if chosen.source == "imported":
                imported = next(
                    (item for item in state.pet_settings.imports if item.id == chosen.id),
                    None,
                )
                if imported is None:
                    raise HTTPException(409, "imported pet metadata is unavailable")
                try:
                    sheet.resolve(strict=True).relative_to(
                        Path(imported.directory).resolve(strict=True)
                    )
                except (OSError, ValueError) as exc:
                    raise HTTPException(409, "imported pet spritesheet is unavailable") from exc
            try:
                data = _read_pet_atlas(sheet)
            except FileNotFoundError as exc:
                raise HTTPException(409, "pet spritesheet is unavailable") from exc
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            return Response(content=data, media_type="image/webp")
        raise HTTPException(409, "pet spritesheet is unavailable")

    @app.patch("/v1/pets/settings")
    async def patch_pets(body: PetSettingsIn, _: None = Depends(_require_token)):
        data = state.pet_settings.model_dump()
        incoming = body.model_dump(exclude_none=True)
        data.update(incoming)
        selected = data.get("selected_id")
        if (
            selected
            and selected not in catalog_by_id(state.pet_settings)
            and selected not in starters_by_id()
        ):
            raise HTTPException(400, "unknown pet")
        updated = PetSettings.model_validate(data)
        _atomic_write_text(state.pet_path, updated.model_dump_json(indent=2))
        state.pet_settings = updated
        return _public_pet_settings(updated)

    @app.post("/v1/pets/import")
    async def import_pet(body: ImportPetIn, _: None = Depends(_require_token)):
        try:
            imported = import_codex_pet(body.directory)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        imports = [item for item in state.pet_settings.imports if item.id != imported.id]
        imports.append(imported)
        updated = state.pet_settings.model_copy(deep=True)
        updated.imports = imports
        updated.selected_id = imported.id
        updated.imported_codex_dir = imported.directory
        _atomic_write_text(state.pet_path, updated.model_dump_json(indent=2))
        state.pet_settings = updated
        return imported.model_dump(mode="json", exclude={"directory", "spritesheet"})

    @app.get("/v1/pets/hatch/capability")
    async def hatch_capability(_: None = Depends(_require_token)):
        return probe_images_endpoint()

    @app.get("/v1/pets/hatch")
    async def list_hatches(_: None = Depends(_require_token)):
        return {"jobs": [job.public() for job in state.hatch.list_jobs()]}

    @app.get("/v1/pets/hatch/{job_id}")
    async def get_hatch(job_id: str, _: None = Depends(_require_token)):
        job = state.hatch.get(job_id)
        if job is None:
            raise HTTPException(404, "unknown hatch job")
        return job.public()

    @app.post("/v1/pets/hatch")
    async def start_hatch(body: HatchIn, _: None = Depends(_require_operator_token)):
        name = body.display_name.strip()
        if not name:
            raise HTTPException(400, "display_name is required")
        config = hatch_image_config()
        if config is None:
            raise HTTPException(
                409,
                {
                    "code": "hatch_provider_unavailable",
                    "message": (
                        "No authorized image provider configuration is available; "
                        "no call was made."
                    ),
                },
            )
        pet_id = slugify(name)
        job = HatchJob(
            id=new_id("hatch_"),
            pet_id=pet_id,
            display_name=name,
            description=body.description.strip(),
            style_preset=body.style_preset.strip() or "plush",
            pet_notes=body.pet_notes.strip() or body.description.strip(),
            status="queued",
            step="Getting pet ready.",
            paid_generation_acknowledged=True,
        )
        issued_at = datetime.now(UTC)
        try:
            authorization = authorize_hatch(
                job,
                principal=LOCAL_HATCH_OPERATOR_PRINCIPAL,
                idempotency_key=body.idempotency_key,
                config=config,
                issued_at=issued_at,
                expires_at=issued_at
                + timedelta(minutes=HATCH_AUTHORIZATION_TTL_MINUTES),
            )
            canonical = state.hatch.create_or_replay(job, authorization)
        except HatchAuthorizationError as exc:
            raise HTTPException(
                400,
                {
                    "code": "hatch_authorization_invalid",
                    "message": str(exc),
                },
            ) from exc
        except HatchConflictError as exc:
            raise HTTPException(
                409,
                {
                    "code": "hatch_idempotency_conflict",
                    "message": str(exc),
                },
            ) from exc

        active = state.hatch_tasks.get(canonical.id)
        if canonical.effect_status == "reserved" and (
            active is None or active.done()
        ):
            task = asyncio.create_task(
                asyncio.to_thread(
                    run_hatch_job,
                    state.hatch,
                    canonical.id,
                    config=config,
                ),
                name=f"hatch:{canonical.id}",
            )
            state.track_hatch_background(canonical.id, task)
        return canonical.public()

    @app.get("/v1/sessions")
    async def sessions(
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        _: None = Depends(_require_token),
    ):
        try:
            await asyncio.wait_for(
                state.pipeline.refresh_desktop_sessions(),
                timeout=DESKTOP_REFRESH_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning("Session refresh timed out; returning durable state")
        return [
            s.model_dump(mode="json")
            for s in await state.store.list_sessions(limit=limit, offset=offset)
        ]

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str, _: None = Depends(_require_token)):
        session = await state.store.get_session(session_id)
        if not session:
            raise HTTPException(404, "session not found")
        return session.model_dump(mode="json")

    @app.post("/v1/goals")
    async def create_goal(
        body: GoalIn,
        response: Response,
        actor: Annotated[OperatorActorEvidence | None, Depends(_goal_control_actor)],
    ):
        from pex_supervisor.public_task import fill_empty_goal_lists_from_objective

        from pex_bridge.ledger import ledger_lists_from_body, ledger_projections

        _require_goal_control_idempotency(actor, body.idempotency_key)
        request_payload = body.model_dump(mode="json", exclude={"idempotency_key"})
        try:
            replay = await _goal_control_replay(
                action_kind=GOAL_CONTROL_ACTION_CREATE,
                actor=actor,
                idempotency_key=body.idempotency_key,
                request_payload=request_payload,
            )
        except OperatorEffectConflictError as exc:
            raise HTTPException(
                409,
                {
                    "code": "operator_intent_idempotency_conflict",
                    "message": str(exc),
                },
            ) from exc
        if replay is not None:
            _set_goal_control_response_headers(response, replay, replayed=True)
            return replay
        now = utcnow()
        payload = dict(request_payload)
        explicit = ledger_lists_from_body(payload)
        goal = Goal(
            id=new_id("goal_"),
            created_at=now,
            updated_at=now,
            **payload,
        )
        goal = fill_empty_goal_lists_from_objective(goal)
        try:
            receipt = await state.store.create_goal_with_ledger_receipt(
                goal,
                ledger_projections(goal, explicit=explicit),
                **_goal_control_store_authority(
                    actor,
                    body.idempotency_key,
                    request_payload,
                ),
            )
        except OperatorEffectConflictError as exc:
            raise HTTPException(
                409,
                {
                    "code": "operator_intent_idempotency_conflict",
                    "message": str(exc),
                },
            ) from exc
        except ProjectIdentityBlockedError as exc:
            raise HTTPException(
                409,
                {"code": exc.code, "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        public = receipt.public()
        _set_goal_control_response_headers(response, public, replayed=receipt.replayed)
        return public

    @app.get("/v1/goals/{goal_id}")
    async def get_goal(goal_id: str, _: None = Depends(_require_token)):
        try:
            view = await state.store.get_goal_intent_view(goal_id)
        except ProjectIdentityBlockedError as exc:
            raise HTTPException(
                409,
                {"code": exc.code, "message": str(exc)},
            ) from exc
        if view is None:
            raise HTTPException(404, "goal not found")
        return view

    @app.get("/v1/goals/{goal_id}/completion")
    async def get_goal_completion(goal_id: str, _: None = Depends(_require_token)):
        try:
            return await state.store.goal_completion_projection(goal_id)
        except LookupError as exc:
            raise HTTPException(404, "goal not found") from exc
        except ProjectIdentityBlockedError as exc:
            raise HTTPException(
                409,
                {"code": exc.code, "message": str(exc)},
            ) from exc

    @app.get("/v1/goals/{goal_id}/decisions")
    async def list_goal_decisions(goal_id: str, _: None = Depends(_require_token)):
        goal = await state.store.get_goal(goal_id)
        if not goal:
            raise HTTPException(404, "goal not found")
        return [
            decision.model_dump(mode="json")
            for decision in await state.store.list_decisions(goal_id)
        ]

    @app.patch("/v1/goals/{goal_id}")
    async def patch_goal(
        goal_id: str,
        body: GoalPatch,
        response: Response,
        actor: Annotated[OperatorActorEvidence | None, Depends(_goal_control_actor)],
    ):
        _require_goal_control_idempotency(actor, body.idempotency_key)
        request_body = body.model_dump(
            mode="json",
            exclude_unset=True,
            exclude={"idempotency_key"},
        )
        request_body["mode"] = body.mode
        request_payload = {"goal_id": goal_id, "body": request_body}
        action_kind = (
            GOAL_CONTROL_ACTION_OVERRIDE
            if body.mode == "override"
            else GOAL_CONTROL_ACTION_UPDATE
        )
        try:
            replay = await _goal_control_replay(
                action_kind=action_kind,
                actor=actor,
                idempotency_key=body.idempotency_key,
                request_payload=request_payload,
            )
        except OperatorEffectConflictError as exc:
            raise HTTPException(
                409,
                {
                    "code": "operator_intent_idempotency_conflict",
                    "message": str(exc),
                },
            ) from exc
        if replay is not None:
            _set_goal_control_response_headers(response, replay, replayed=True)
            return replay
        current = await state.store.get_goal_for_authority(goal_id)
        if current is None:
            raise HTTPException(404, "goal not found")
        if await state.store.has_goal_successor_for_authority(goal_id):
            raise HTTPException(409, "goal has already been superseded")

        from pex_supervisor.public_task import (
            LEDGER_DECISION_FIELDS,
            fill_empty_goal_lists_from_objective,
        )

        from pex_bridge.ledger import ledger_kinds_for_fields, ledger_projections

        changes = body.model_dump(
            exclude_unset=True,
            exclude={"mode", "expected_intent_revision", "idempotency_key"},
        )
        skip_ledger = {key for key in LEDGER_DECISION_FIELDS if key in changes}
        explicit = {
            key: [str(item) for item in (changes.pop(key) or []) if str(item).strip()]
            for key in skip_ledger
        }
        if not changes and not skip_ledger:
            raise HTTPException(400, "goal patch must include an intent change")
        if body.expected_intent_revision is None:
            raise HTTPException(
                428,
                {
                    "code": "goal_intent_revision_required",
                    "message": "expected_intent_revision is required for goal mutation",
                },
            )
        if not changes and body.mode == "update":
            try:
                receipt = await state.store.patch_goal_with_ledger_receipt(
                    current,
                    current,
                    ledger_projections(
                        current,
                        explicit=explicit,
                        skip_fields=skip_ledger,
                    ),
                    replace_ledger_kinds=ledger_kinds_for_fields(skip_ledger),
                    expected_intent_revision=body.expected_intent_revision,
                    **_goal_control_store_authority(
                        actor,
                        body.idempotency_key,
                        request_payload,
                    ),
                )
            except OperatorEffectConflictError as exc:
                raise HTTPException(
                    409,
                    {
                        "code": "operator_intent_idempotency_conflict",
                        "message": str(exc),
                    },
                ) from exc
            except ProjectIdentityBlockedError as exc:
                raise HTTPException(
                    409,
                    {"code": exc.code, "message": str(exc)},
                ) from exc
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            public = receipt.public()
            _set_goal_control_response_headers(response, public, replayed=receipt.replayed)
            return public
        nullable = {"deadline"}
        cleared = sorted(
            key for key, value in changes.items() if value is None and key not in nullable
        )
        if cleared:
            raise HTTPException(400, f"goal fields cannot be null: {', '.join(cleared)}")

        data = current.model_dump()
        data.update(changes)
        now = utcnow()
        data["updated_at"] = now
        if body.mode == "update":
            updated = Goal.model_validate(data)
            from pex_supervisor.public_task import fill_empty_goal_lists_from_objective

            updated = fill_empty_goal_lists_from_objective(
                updated,
                skip_fields={
                    key for key in _GOAL_EXTRACT_LIST_FIELDS if key in changes
                },
            )
            projections = (
                []
                if changes == {"paused": True} and not skip_ledger
                else ledger_projections(
                    updated,
                    explicit=explicit,
                    skip_fields=skip_ledger,
                )
            )
            try:
                receipt = await state.store.patch_goal_with_ledger_receipt(
                    current,
                    updated,
                    projections,
                    replace_ledger_kinds=ledger_kinds_for_fields(skip_ledger),
                    expected_intent_revision=body.expected_intent_revision,
                    **_goal_control_store_authority(
                        actor,
                        body.idempotency_key,
                        request_payload,
                    ),
                )
            except OperatorEffectConflictError as exc:
                raise HTTPException(
                    409,
                    {
                        "code": "operator_intent_idempotency_conflict",
                        "message": str(exc),
                    },
                ) from exc
            except ProjectIdentityBlockedError as exc:
                raise HTTPException(
                    409,
                    {"code": exc.code, "message": str(exc)},
                ) from exc
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            public = receipt.public()
            _set_goal_control_response_headers(response, public, replayed=receipt.replayed)
            return public

        data.update(
            id=new_id("goal_"),
            created_at=now,
            updated_at=now,
            supersedes=current.id,
        )
        replacement = Goal.model_validate(data)
        from pex_supervisor.public_task import fill_empty_goal_lists_from_objective

        replacement = fill_empty_goal_lists_from_objective(
            replacement,
            skip_fields={
                key for key in _GOAL_EXTRACT_LIST_FIELDS if key in changes
            },
        )
        try:
            receipt = await state.store.supersede_goal_with_ledger_receipt(
                current,
                replacement,
                ledger_projections(
                    replacement,
                    explicit=explicit,
                    skip_fields=skip_ledger,
                ),
                replace_ledger_kinds=ledger_kinds_for_fields(skip_ledger),
                expected_intent_revision=body.expected_intent_revision,
                **_goal_control_store_authority(
                    actor,
                    body.idempotency_key,
                    request_payload,
                ),
            )
        except OperatorEffectConflictError as exc:
            raise HTTPException(
                409,
                {
                    "code": "operator_intent_idempotency_conflict",
                    "message": str(exc),
                },
            ) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ProjectIdentityBlockedError as exc:
            raise HTTPException(
                409,
                {"code": exc.code, "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        public = receipt.public()
        _set_goal_control_response_headers(response, public, replayed=receipt.replayed)
        return public

    @app.post("/v1/sessions/{session_id}/attach")
    async def attach(
        session_id: str,
        body: AttachIn,
        response: Response,
        actor: Annotated[OperatorActorEvidence | None, Depends(_goal_control_actor)],
    ):
        _require_goal_control_idempotency(actor, body.idempotency_key)
        _require_authenticated_attach_cas(actor, body)
        request_payload = {
            "session_id": session_id,
            "body": body.model_dump(mode="json", exclude={"idempotency_key"}),
        }
        try:
            replay = await _goal_control_replay(
                action_kind=GOAL_CONTROL_ACTION_ATTACH,
                actor=actor,
                idempotency_key=body.idempotency_key,
                request_payload=request_payload,
            )
        except OperatorEffectConflictError as exc:
            raise HTTPException(
                409,
                {
                    "code": "operator_intent_idempotency_conflict",
                    "message": str(exc),
                },
            ) from exc
        if replay is not None:
            _set_goal_control_response_headers(response, replay, replayed=True)
            return replay
        session = await state.store.get_session(session_id)
        if not session:
            raise HTTPException(404, "session not found")
        from pex_bridge.adapters.desktop import is_desktop_observe_session

        if is_desktop_observe_session(session):
            raise HTTPException(
                409,
                (
                    "This is an observe-only desktop inventory tile. Attach the goal to a "
                    "live vendor session (isolated App Server thread, Cursor conversation, "
                    "or hooked Claude session), not the generic desktop row."
                ),
            )
        try:
            result = await state.store.attach_session_goal(
                session_id,
                body.goal_id,
                expected_goal_id=body.expected_goal_id,
                replace_existing=body.replace_existing,
                expected_control_revision=body.expected_control_revision,
                expected_goal_intent_revision=body.expected_goal_intent_revision,
                **_goal_control_store_authority(
                    actor,
                    body.idempotency_key,
                    request_payload,
                ),
            )
        except OperatorEffectConflictError as exc:
            raise HTTPException(
                409,
                {
                    "code": "operator_intent_idempotency_conflict",
                    "message": str(exc),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not result["granted"]:
            reason = str(result["reason"])
            if reason == "session_not_found":
                raise HTTPException(404, "session not found")
            if reason == "goal_not_found":
                raise HTTPException(404, "goal not found")
            messages = {
                "goal_superseded": "goal has been superseded; attach its successor",
                "session_goal_changed": (
                    "session goal changed; explicit replacement requires its exact prior goal"
                ),
                "session_project_identity_changed": "session project identity changed",
                "session_control_revision_changed": "session control revision changed",
                "goal_intent_revision_changed": "goal intent revision changed",
            }
            detail: str | dict[str, str] = messages.get(reason, reason)
            if reason.startswith("project_identity_"):
                detail = {"code": reason, "message": reason.replace("_", " ")}
            raise HTTPException(409, detail)
        canonical = result.get("session")
        if not isinstance(canonical, HarnessSession):
            raise HTTPException(500, "session attachment receipt is invalid")
        operation = result.get("operator_operation")
        if operation is not None:
            public = state.store.session_goal_attachment_public_response(result)
            _set_goal_control_response_headers(
                response,
                public,
                replayed=bool(result.get("replayed")),
            )
            return public
        attachment_receipt = {
            "schema": "pex.session-goal-attachment-receipt.v1",
            "changed": bool(result["changed"]),
            "reason": str(result["reason"]),
            "goal_id": str(result["goal_id"]),
            "goal_intent_revision": int(result["goal_intent_revision"]),
            "goal_intent_hash": str(result["goal_intent_hash"]),
            "before_goal_id": result["before_goal_id"],
            "after_goal_id": str(result["after_goal_id"]),
            "before_revision": int(result["before_revision"]),
            "after_revision": int(result["after_revision"]),
            "before_control_revision": int(result["before_control_revision"]),
            "after_control_revision": int(result["after_control_revision"]),
            "project_binding": result["project_binding"],
            "discovery_generation": result["discovery_generation"],
            "mcp_principals_revoked": int(result["mcp_principals_revoked"]),
            "hook_credentials_revoked": int(result["hook_credentials_revoked"]),
        }
        return {
            **canonical.model_dump(mode="json"),
            "revision": int(result["revision"]),
            "control_revision": int(result["control_revision"]),
            "session_goal_attachment_receipt": attachment_receipt,
        }

    @app.post("/v1/sessions/{session_id}/mcp-credential")
    async def issue_mcp_credential(
        session_id: str,
        response: Response,
        _: None = Depends(_require_operator_token),
    ):
        """Rotate and return one session-bound MCP bearer exactly once."""

        session = await state.store.get_session(session_id)
        if session is None:
            raise HTTPException(404, "session not found")
        from pex_bridge.adapters.desktop import is_desktop_observe_session

        if is_desktop_observe_session(session):
            raise HTTPException(409, "MCP credentials require a live vendor session")
        if session.status == SessionStatus.DETACHED:
            raise HTTPException(409, "MCP credentials require an attached live session")
        if not session.goal_id:
            raise HTTPException(409, "session has no attached persistent goal")
        session = await state.store.get_session_for_authority(
            session_id,
            require_goal_binding=True,
        )
        if session is None:
            raise HTTPException(404, "session not found")
        goal = await state.store.get_goal_for_authority(session.goal_id)
        if goal is None:
            raise HTTPException(409, "session goal not found")
        if await state.store.has_goal_successor_for_authority(goal.id):
            raise HTTPException(409, "session goal has been superseded")
        project_id = session.project_id or session.cwd
        if not project_id:
            raise HTTPException(409, "session has no project identity")

        raw_token = mint_mcp_session_token()
        issued_at = utcnow()
        expires_at = issued_at + timedelta(seconds=MCP_SESSION_CREDENTIAL_TTL_SECONDS)
        principal_id = new_id("mcp_principal_")
        try:
            record = await state.store.issue_mcp_principal(
                principal_id=principal_id,
                session_id=session.id,
                goal_id=goal.id,
                project_id=project_id,
                vendor_session_id=session.vendor_session_id,
                harness_type=session.harness_type.value,
                scopes=sorted(MCP_SESSION_SCOPES),
                token_digest=digest_mcp_session_token(raw_token),
                issued_at=issued_at,
                expires_at=expires_at,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return {
            "principal_id": record["principal_id"],
            "session_id": record["session_id"],
            "goal_id": record["goal_id"],
            "project_id": record["project_id"],
            "scopes": record["scopes"],
            "issued_at": record["issued_at"],
            "expires_at": record["expires_at"],
            "token": raw_token,
        }

    @app.post("/v1/hook-credentials/bootstrap")
    async def issue_hook_bootstrap(
        body: HookBootstrapIn,
        response: Response,
        _: None = Depends(_require_operator_token),
    ):
        """Pre-register one project-bound bearer that binds on its first session hook."""

        routes = allowed_hook_routes(body.harness_type)
        if not routes:
            raise HTTPException(409, "harness has no scoped hook credential surface")
        raw_token = mint_hook_token()
        issued_at = utcnow()
        expires_at = issued_at + timedelta(seconds=HOOK_CREDENTIAL_TTL_SECONDS)
        try:
            record = await state.store.issue_hook_credential(
                credential_id=new_id("hook_credential_"),
                session_id=None,
                project_id=body.project_id,
                vendor_session_id=None,
                harness_type=body.harness_type.value,
                allowed_routes=sorted(routes),
                token_digest=digest_hook_token(raw_token),
                issued_at=issued_at,
                expires_at=expires_at,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return {
            "credential_id": record["credential_id"],
            "session_id": None,
            "project_id": record["project_id"],
            "harness_type": record["harness_type"],
            "allowed_routes": record["allowed_routes"],
            "issued_at": record["issued_at"],
            "expires_at": record["expires_at"],
            "token": raw_token,
        }

    @app.post("/v1/sessions/{session_id}/hook-credential")
    async def issue_hook_credential(
        session_id: str,
        response: Response,
        _: None = Depends(_require_operator_token),
    ):
        """Rotate and return one least-privilege worker hook bearer once."""

        session = await state.store.get_session_for_authority(session_id)
        if session is None:
            raise HTTPException(404, "session not found")
        from pex_bridge.adapters.desktop import is_desktop_observe_session

        if is_desktop_observe_session(session):
            raise HTTPException(409, "hook credentials require a live vendor session")
        if session.status not in _HOOK_CREDENTIAL_ISSUABLE_STATUSES:
            raise HTTPException(409, "hook credentials require a non-terminal live session")
        routes = allowed_hook_routes(session.harness_type)
        if not routes:
            raise HTTPException(409, "session harness has no scoped hook credential surface")
        project_id = session.project_id or session.cwd
        if not project_id:
            raise HTTPException(409, "session has no project binding")
        if not session.vendor_session_id:
            raise HTTPException(409, "session has no vendor identity")

        raw_token = mint_hook_token()
        issued_at = utcnow()
        expires_at = issued_at + timedelta(seconds=HOOK_CREDENTIAL_TTL_SECONDS)
        try:
            record = await state.store.issue_hook_credential(
                credential_id=new_id("hook_credential_"),
                session_id=session.id,
                project_id=project_id,
                vendor_session_id=session.vendor_session_id,
                harness_type=session.harness_type.value,
                allowed_routes=sorted(routes),
                token_digest=digest_hook_token(raw_token),
                issued_at=issued_at,
                expires_at=expires_at,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return {
            "credential_id": record["credential_id"],
            "session_id": record["session_id"],
            "project_id": record["project_id"],
            "harness_type": record["harness_type"],
            "allowed_routes": record["allowed_routes"],
            "issued_at": record["issued_at"],
            "expires_at": record["expires_at"],
            "token": raw_token,
        }

    @app.delete("/v1/hook-credentials/{credential_id}")
    async def revoke_hook_credential(
        credential_id: str,
        _: None = Depends(_require_operator_token),
    ):
        try:
            revoked = await state.store.revoke_hook_credential(
                credential_id,
                revoked_at=utcnow(),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not revoked:
            raise HTTPException(404, "hook credential not found")
        return {"ok": True, "credential_id": credential_id}

    @app.get("/v1/sessions/{session_id}/overlays")
    async def session_overlays(session_id: str, _: None = Depends(_require_token)):
        if await state.store.get_session(session_id) is None:
            raise HTTPException(404, "session not found")
        overlays = await state.store.list_overlays(session_id)
        return [overlay.model_dump(mode="json") for overlay in overlays]

    @app.get("/v1/sessions/{session_id}/overlay-runtime")
    async def session_overlay_runtime(
        session_id: str,
        principal: Annotated[HookPrincipal | None, Depends(_require_hook_access)],
    ):
        from pex_bridge.overlay_runtime import compile_overlay_runtime

        await _authorize_hook_route(
            principal,
            route=OPENCODE_OVERLAY_ROUTE,
            harness_type=HarnessType.OPENCODE,
            session_id=session_id,
        )
        if principal is not None and not principal.is_bound:
            raise HTTPException(403, "hook credential must bind through a plugin heartbeat")
        session = await state.store.get_session_for_authority(session_id)
        if session is None:
            raise HTTPException(404, "session not found")
        if session.harness_type != HarnessType.OPENCODE:
            raise HTTPException(400, "overlay runtime is only available to the OpenCode plugin")
        return compile_overlay_runtime(
            await state.store.runtime_overlays(
                session_id,
                global_supervision_paused=state.pipeline.supervision_paused,
            )
        )

    @app.post("/v1/adapters/opencode/plugin-heartbeat")
    async def opencode_plugin_heartbeat(
        body: PluginHeartbeatIn,
        principal: Annotated[HookPrincipal | None, Depends(_require_hook_access)],
    ):
        if principal is not None and not body.directory:
            raise HTTPException(403, "hook credential project binding is required")
        await _authorize_hook_route(
            principal,
            route=OPENCODE_HEARTBEAT_ROUTE,
            harness_type=HarnessType.OPENCODE,
            project_id=body.directory,
        )
        if principal is not None and body.session_id:
            principal = await _bind_path_hook_principal(
                principal,
                harness_type=HarnessType.OPENCODE,
                session_id=f"opencode:{body.session_id}",
            )
            await _authorize_hook_route(
                principal,
                route=OPENCODE_HEARTBEAT_ROUTE,
                harness_type=HarnessType.OPENCODE,
                session_id=f"opencode:{body.session_id}",
                project_id=body.directory,
            )
        session_id = None
        if body.session_id and body.directory:
            session = state.adapters.opencode.ingest_hook(
                {
                    "session_id": body.session_id,
                    "cwd": body.directory,
                    "source": "pex-opencode-plugin",
                }
            )
            await state.store.upsert_session(session)
            session_id = session.id
        state.adapters.opencode.mark_plugin_heartbeat(
            f"opencode:{body.session_id}" if body.session_id else None
        )
        return {
            "ok": True,
            "plugin": "pex-opencode-plugin",
            "overlay_scope": "session",
            "supported": ["system_instructions", "tools_disabled"],
            "session_id": session_id,
        }

    @app.post("/v1/overlays/{overlay_id}/revert")
    async def revert_overlay(
        overlay_id: str,
        body: UndoIn,
        _: None = Depends(_require_operator_token),
    ):
        result = await state.pipeline.executor.revert_overlay_receipt(
            overlay_id,
            authorized_by=_LOCAL_OPERATOR_PRINCIPAL,
            idempotency_key=body.idempotency_key,
            reason="user_requested",
        )
        return _overlay_revert_response(result)

    @app.post("/v1/sessions/{session_id}/message")
    async def message(
        session_id: str,
        body: MessageIn,
        _: Annotated[OperatorActorEvidence, Depends(_require_operator_token)],
    ):
        try:
            reservation = await state.store.reserve_operator_message(
                principal_id=_.principal_id,
                idempotency_key=body.idempotency_key,
                session_id=session_id,
                text=body.text,
                actor_assurance=_.actor_assurance,
            )
        except LookupError as exc:
            raise HTTPException(404, "session not found") from exc
        except ProjectIdentityBlockedError as exc:
            raise HTTPException(
                409,
                {"code": exc.code, "message": str(exc)},
            ) from exc
        except OperatorEffectConflictError as exc:
            raise HTTPException(
                409,
                {"code": "operator_message_idempotency_conflict", "message": str(exc)},
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                409,
                {"code": "operator_message_binding_rejected", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                409,
                {"code": "operator_message_binding_rejected", "message": str(exc)},
            ) from exc

        effect = reservation["effect"]
        if effect["state"] != "reserved":
            return _operator_effect_response(effect, replayed=True)
        adapter = state.adapters.for_session(session_id)
        if adapter is None:
            skipped = await state.store.finalize_operator_effect(
                effect_id=effect["effect_id"],
                state="skipped",
                result={"status": "skipped", "reason": "adapter_unavailable"},
            )
            return _operator_effect_response(skipped, replayed=False)

        try:
            dispatch = await state.store.start_operator_message_dispatch(
                effect["effect_id"],
                global_supervision_paused=state.pipeline.supervision_paused,
            )
        except (ProjectIdentityBlockedError, PermissionError, ValueError) as exc:
            code = getattr(exc, "code", "operator_message_binding_rejected")
            skipped = await state.store.finalize_operator_effect(
                effect_id=effect["effect_id"],
                state="skipped",
                result={"status": "skipped", "reason": str(code)},
            )
            return _operator_effect_response(skipped, replayed=False)
        if not dispatch["granted"]:
            current = dispatch.get("effect") or effect
            if dispatch["reason"] == "session_dispatch_busy":
                return JSONResponse(
                    status_code=409,
                    content={
                        "ok": False,
                        "replayed": not reservation["created"],
                        "status": current["state"],
                        "code": "operator_message_session_busy",
                        "receipt": _public_operator_effect(current),
                    },
                )
            return _operator_effect_response(current, replayed=True)

        dispatched = dispatch["effect"]
        live_session = dispatch["session"]

        async def durable_finalize(
            state_name: str,
            result: dict[str, Any],
        ) -> dict[str, Any]:
            completion = asyncio.create_task(
                state.store.finalize_operator_effect(
                    effect_id=dispatched["effect_id"],
                    state=state_name,
                    result=result,
                )
            )
            try:
                return await asyncio.shield(completion)
            except asyncio.CancelledError:
                # Once adapter I/O started, the immutable receipt must outlive
                # request cancellation. Shield prevents cancelling the Store CAS.
                await asyncio.gather(completion)
                raise

        async def finalize_uncertain(reason: str) -> dict[str, Any]:
            return await durable_finalize(
                "delivery_uncertain",
                {"status": "delivery_uncertain", "reason": reason},
            )

        try:
            ok = await asyncio.wait_for(
                adapter.send_message(
                    live_session,
                    body.text,
                    attachments={"operator_effect_id": dispatched["effect_id"]},
                ),
                timeout=ADAPTER_MESSAGE_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            try:
                await finalize_uncertain("request_cancelled_after_dispatch_started")
            except Exception as exc:
                logger.error(
                    "Operator message cancellation receipt failed (%s)",
                    type(exc).__name__,
                )
            raise
        except TimeoutError:
            uncertain = await finalize_uncertain("adapter_timeout_after_dispatch_started")
            return _operator_effect_response(uncertain, replayed=False)
        except Exception as exc:
            uncertain = await finalize_uncertain(
                f"adapter_exception_after_dispatch_started:{type(exc).__name__}"
            )
            return _operator_effect_response(uncertain, replayed=False)
        message_resolution = resolve_adapter_message_result(ok, session=live_session)
        if message_resolution.status in {"delivery_uncertain", "hook_prepared"}:
            uncertain = await finalize_uncertain("invalid_adapter_receipt")
            return _operator_effect_response(uncertain, replayed=False)
        if message_resolution.status == "rejected":
            failed = await durable_finalize(
                "failed",
                {"status": "failed", "reason": "adapter_rejected_message"},
            )
            return _operator_effect_response(failed, replayed=False)
        result: dict[str, Any] = {"status": "delivered"}
        if message_resolution.worker_delivery_receipt is not None:
            result["worker_delivery_receipt"] = (
                message_resolution.worker_delivery_receipt
            )
        delivered = await durable_finalize(
            "delivered",
            result,
        )
        return _operator_effect_response(delivered, replayed=False)

    @app.post("/v1/sessions/{session_id}/focus")
    async def focus(session_id: str, _: None = Depends(_require_token)):
        session = await state.store.get_session_for_authority(session_id)
        adapter = state.adapters.for_session(session_id)
        if not session or not adapter:
            raise HTTPException(404, "session not found")
        try:
            ok = await asyncio.wait_for(
                adapter.focus_ui(session), timeout=ADAPTER_FOCUS_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:
            raise HTTPException(504, "focus request timed out; outcome is unknown") from exc
        except Exception as exc:
            raise HTTPException(502, "focus request failed; outcome may be unknown") from exc
        if not ok:
            raise HTTPException(409, "adapter could not focus the session")
        return {"ok": ok}

    @app.post("/v1/harnesses/{name}/focus")
    async def focus_harness_named(name: str, _: None = Depends(_require_token)):
        from pex_bridge.adapters.winfocus import focus_harness

        try:
            ok = await asyncio.wait_for(
                asyncio.to_thread(focus_harness, name),
                timeout=ADAPTER_FOCUS_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise HTTPException(504, "focus request timed out; outcome is unknown") from exc
        except Exception as exc:
            raise HTTPException(502, "focus request failed") from exc
        if not ok:
            raise HTTPException(409, "desktop harness could not be focused")
        return {"ok": True}

    @app.post("/v1/sessions/{session_id}/pause-supervision")
    async def pause(session_id: str, _: None = Depends(_require_operator_token)):
        control = await state.store.get_session_control_state(session_id)
        if control is None:
            raise HTTPException(404, "session not found")
        result = await state.store.set_session_supervision_paused(
            session_id,
            paused=True,
            expected_control_revision=control["control_revision"],
            principal_id=_LOCAL_OPERATOR_PRINCIPAL,
            actor_assurance="bridge_bearer",
        )
        if not result["granted"]:
            raise HTTPException(409, str(result["reason"]))
        return {"ok": True, "human_action_receipt": result.get("human_action_receipt")}

    @app.post("/v1/sessions/{session_id}/resume-supervision")
    async def resume(session_id: str, _: None = Depends(_require_operator_token)):
        control = await state.store.get_session_control_state(session_id)
        if control is None:
            raise HTTPException(404, "session not found")
        result = await state.store.set_session_supervision_paused(
            session_id,
            paused=False,
            expected_control_revision=control["control_revision"],
            principal_id=_LOCAL_OPERATOR_PRINCIPAL,
            actor_assurance="bridge_bearer",
        )
        if not result["granted"]:
            reason = str(result["reason"])
            detail: str | dict[str, str] = reason
            if reason.startswith("project_identity_"):
                detail = {"code": reason, "message": reason.replace("_", " ")}
            raise HTTPException(409, detail)
        return {"ok": True, "human_action_receipt": result.get("human_action_receipt")}

    @app.post("/v1/sessions/{session_id}/handoff")
    async def handoff(
        session_id: str,
        body: HandoffIn,
        _: Annotated[OperatorActorEvidence, Depends(_require_operator_token)],
    ):
        source = await state.store.get_session_for_authority(
            session_id,
            require_goal_binding=True,
        )
        if source is None:
            raise HTTPException(404, "session not found")
        try:
            result = await state.pipeline.request_context_handoff(
                source,
                principal_id=_.principal_id,
                request=ContextHandoffRequest.model_validate(body.model_dump(mode="python")),
                actor_assurance=_.actor_assurance,
            )
        except ProjectIdentityBlockedError as exc:
            raise HTTPException(
                409,
                {"code": exc.code, "message": str(exc)},
            ) from exc
        except OperatorEffectConflictError as exc:
            raise HTTPException(
                409,
                {
                    "code": "context_handoff_idempotency_conflict",
                    "message": str(exc),
                },
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                409,
                {"code": "context_handoff_binding_rejected", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                409,
                {"code": "context_handoff_binding_rejected", "message": str(exc)},
            ) from exc
        status_code = {
            "delivered": 200,
            "reserved": 202,
            "dispatching": 202,
            "delivery_uncertain": 502,
            "failed": 409,
            "skipped": 409,
        }.get(str(result.get("status") or ""), 500)
        return JSONResponse(status_code=status_code, content=result)

    @app.get("/v1/handoffs/{effect_id}/assimilation")
    async def handoff_assimilation(
        effect_id: str,
        _: None = Depends(_require_token),
    ):
        try:
            return await state.store.handoff_assimilation_status(effect_id)
        except LookupError as exc:
            raise HTTPException(404, "handoff not found") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/v1/interventions")
    async def interventions(
        session_id: str | None = Query(default=None, max_length=MAX_ID_CHARS),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        include_handoff_bundle: bool = Query(default=False),
        _: None = Depends(_require_token),
    ):
        items = await state.store.list_interventions(
            session_id,
            limit=limit,
            offset=offset,
        )
        return [
            item.model_dump(mode="json") if include_handoff_bundle else public_intervention(item)
            for item in items
        ]

    @app.get("/v1/attention/metrics")
    async def attention_metrics(_: None = Depends(_require_token)):
        """Return durable metric truth independently of paginated UI detail rows."""

        return await state.store.attention_metrics()

    @app.get("/v1/bench/runs")
    async def benchmark_runs(_: None = Depends(_require_token)):
        from pex_bridge.benchmark_public import load_public_summary

        return load_public_summary()

    async def _publish_committed_decision_update(intervention) -> None:
        await state.bus.publish_committed(
            "intervention",
            intervention.model_dump(mode="json"),
        )
        try:
            pet = await state.pipeline.pet_snapshot()
        except Exception as exc:
            logger.warning(
                "committed decision pet snapshot failed error=%s",
                type(exc).__name__,
            )
        else:
            await state.bus.publish_committed("pet", pet)

    @app.post("/v1/decisions/{decision_id}/resolve")
    async def resolve_decision(
        decision_id: str,
        body: DecisionResolveIn,
        _: None = Depends(_require_operator_token),
    ):
        from pex_bridge.decisions import (
            DecisionResolutionError,
            resolve_lifecycle_decision,
            resolve_permission_decision,
            resolve_requested_human_decision,
        )

        try:
            # This read classifies the request only. The decision subsystem's
            # bound reserve/start operation is the execution grant and retains
            # deliberate deny/STOP containment through quarantine.
            pending = (
                await state.store.get_intervention_for_resolution_classification(
                    decision_id
                )
            )
            lifecycle_types = {
                InterventionType.START_AGENT,
                InterventionType.STOP_AGENT,
                InterventionType.FORK_PROBE,
                InterventionType.CLEANUP,
            }
            if (
                pending
                and pending.proposed_action.type == InterventionType.ASK_HUMAN
                and pending.metadata.get("decision_kind") == "mcp_human_request"
            ):
                human = await resolve_requested_human_decision(
                    state.store,
                    state.adapters,
                    intervention_id=decision_id,
                    choice=body.decision,
                )
                if not human.replayed:
                    await _publish_committed_decision_update(human.intervention)
                response = human.response()
                delivery_status = str(human.payload.get("delivery_status") or "")
                if delivery_status != "delivered":
                    uncertain = delivery_status in {"dispatching", "delivery_uncertain"}
                    raise HTTPException(
                        502 if uncertain else 409,
                        detail={
                            "code": f"human_decision_{delivery_status or 'failed'}",
                            "message": (
                                "The answer may have reached the worker; PEX will not send it "
                                "again automatically."
                                if uncertain
                                else "The answer was recorded, but this exact worker could not "
                                "confirm delivery."
                            ),
                            "resolution": response,
                        },
                    )
                return response
            if pending and pending.proposed_action.type in lifecycle_types:
                lifecycle = await resolve_lifecycle_decision(
                    state.store,
                    state.adapters,
                    state.pipeline.executor,
                    intervention_id=decision_id,
                    decision=body.decision,
                )
                if not lifecycle.replayed:
                    await _publish_committed_decision_update(lifecycle.intervention)
                response = lifecycle.response()
                status = str(lifecycle.resolution.get("status") or "")
                if status in {"failed", "delivery_uncertain"}:
                    raise HTTPException(
                        502 if status == "delivery_uncertain" else 409,
                        detail={
                            "code": f"lifecycle_{status}",
                            "message": (
                                "The lifecycle action may have partially completed; PEX will not "
                                "replay it automatically."
                                if status == "delivery_uncertain"
                                else "The approved lifecycle action was rejected without success."
                            ),
                            "resolution": response,
                        },
                    )
                return response
            resolved = await resolve_permission_decision(
                state.store,
                state.adapters,
                intervention_id=decision_id,
                decision=body.decision,
            )
        except DecisionResolutionError as exc:
            raise HTTPException(
                exc.status_code,
                detail={"code": exc.code, "message": exc.detail},
            ) from exc

        if not resolved.replayed:
            await _publish_committed_decision_update(resolved.intervention)
        response = resolved.response()
        if not resolved.delivered:
            uncertain = resolved.resolution.get("status") == "delivery_uncertain"
            raise HTTPException(
                502,
                detail={
                    "code": (
                        "permission_delivery_uncertain"
                        if uncertain
                        else "permission_delivery_failed"
                    ),
                    "message": (
                        "The human decision was recorded, but delivery may have partially "
                        "completed. "
                        "PEX will not replay it automatically."
                        if uncertain
                        else "The human decision was recorded but the adapter rejected delivery. "
                        "PEX will not replay it automatically."
                    ),
                    "resolution": response,
                },
            )
        return response

    @app.post("/v1/interventions/{intervention_id}/undo")
    async def undo_intervention(
        intervention_id: str,
        body: UndoIn,
        _: None = Depends(_require_operator_token),
    ):
        classified = await state.store.get_intervention(intervention_id)
        if classified is None:
            raise HTTPException(404, "intervention not found")
        if not classified.reversible:
            raise HTTPException(400, "intervention is not reversible")
        if classified.action_taken == InterventionType.CLEANUP.value:
            restore = await state.pipeline.executor.restore_cleanup(
                intervention_id,
                authorized_by=_LOCAL_OPERATOR_PRINCIPAL,
                idempotency_key=body.idempotency_key,
            )
            if not isinstance(restore, dict):
                raise HTTPException(
                    502,
                    {
                        "code": "cleanup_restore_result_uncertain",
                        "message": "Cleanup restore did not return a structured receipt.",
                    },
                )
            raw_receipt = restore.get("receipt")
            receipt = None
            if isinstance(raw_receipt, dict):
                raw_counts = raw_receipt.get("outcome_counts")
                receipt = {
                    "operation_id": raw_receipt.get("operation_id"),
                    "cleanup_operation_id": raw_receipt.get("cleanup_operation_id"),
                    "intervention_id": raw_receipt.get("intervention_id"),
                    "session_id": raw_receipt.get("session_id"),
                    "goal_id": raw_receipt.get("goal_id"),
                    "state": raw_receipt.get("state"),
                    "version": raw_receipt.get("version"),
                    "reserved_at": raw_receipt.get("reserved_at"),
                    "dispatch_started_at": raw_receipt.get("dispatch_started_at"),
                    "finished_at": raw_receipt.get("finished_at"),
                    "resource_count": raw_receipt.get("resource_count"),
                    "outcome_counts": {
                        name: raw_counts.get(name)
                        for name in ("restored", "not_restored", "conflict")
                    }
                    if isinstance(raw_counts, dict)
                    else None,
                }
            response = {
                "ok": restore.get("ok") is True,
                "code": str(restore.get("code") or "cleanup_restore_result_uncertain"),
                "status": str(restore.get("status") or "uncertain"),
                "replayed": restore.get("replayed") is True,
                "receipt": receipt,
            }
            code = response["code"]
            status = response["status"]
            if (
                status == "completed"
                and response["ok"] is True
                and code.startswith("cleanup_restored:")
            ):
                status_code = 200
            elif status in {"reserved", "dispatching"}:
                status_code = 202
            elif (
                status in {"failed", "conflict", "refused"}
                or code.endswith("_refused")
                or code.startswith("cleanup_restore_not_restored:")
                or code.startswith("cleanup_restore_conflict:")
            ):
                status_code = 409
            elif status in {"delivery_uncertain", "uncertain"} or "uncertain" in code:
                status_code = 502
            else:
                status_code = 502
            return JSONResponse(status_code=status_code, content=response)

        if classified.action_taken == InterventionType.APPLY_OVERLAY.value:
            result = await state.pipeline.executor.revert_overlay_receipt(
                owned_by_intervention_id=intervention_id,
                authorized_by=_LOCAL_OPERATOR_PRINCIPAL,
                idempotency_key=body.idempotency_key,
                reason="operator_undo",
            )
            # The intervention exists, so failure to resolve its exact frozen apply
            # is a binding/ownership conflict rather than a genuinely missing resource.
            return _overlay_revert_response(result, missing_status=409)
        # A delivered message, permission response, or lifecycle side effect cannot
        # be made un-happen by sending another message.  `reversible` is advisory
        # proposal metadata; the API only advertises undo when it has an exact,
        # state-backed inverse operation.
        raise HTTPException(409, "intervention has no truthful undo operation")

    @app.get("/v1/context")
    async def list_context(
        project_id: str | None = Query(default=None, max_length=MAX_PATH_CHARS),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0, le=1_000_000),
        _: None = Depends(_require_token),
    ):
        if not project_id:
            goals = await state.store.list_goals_page(limit=1)
            project_id = goals[0].project_id if goals else None
        if not project_id:
            return []
        return [
            item.model_dump(mode="json")
            for item in await state.store.list_context(
                project_id,
                limit=limit,
                offset=offset,
            )
        ]

    @app.get("/v1/deck")
    async def command_deck(_: None = Depends(_require_token)):
        session_limit = 200
        projection = await state.pipeline.current_projection(
            session_limit=session_limit,
            session_scan_limit=session_limit + 1,
            intervention_limit=40,
            event_limit=0,
        )
        visible_sessions = projection["sessions"]
        interventions = projection["interventions"]
        fingerprint_rows = await state.store.agent_fingerprint_stats()

        async def probe_for_deck(adapter: Any) -> dict[str, Any]:
            try:
                caps = await asyncio.wait_for(adapter.probe(), timeout=2.0)
            except Exception:
                return {
                    "name": adapter.name,
                    "capabilities": {
                        "support_label": "unavailable",
                        "notes": "Live capability probe timed out or failed; nothing was inferred.",
                    },
                }
            return {
                "name": adapter.name,
                "capabilities": caps.model_dump(mode="json"),
            }

        adapters = await asyncio.gather(
            *(probe_for_deck(adapter) for adapter in state.adapters.all())
        )
        pretty = decorate_agent_fingerprints(fingerprint_rows)
        return {
            "sessions": [s.model_dump(mode="json") for s in visible_sessions],
            "interventions": [i.model_dump(mode="json") for i in interventions],
            "adapters": adapters,
            "fingerprints": pretty,
            "evidence_basis": {
                "fingerprints": (
                    "all persisted sessions; verifier-backed stop outcomes only; "
                    "unmeasured rates stay null"
                ),
                "current_projection": (
                    "live Store authority only; quarantined or rebound rows remain history"
                ),
                "sessions_returned": len(visible_sessions),
                "sessions_truncated": projection["sessions_truncated"],
                "interventions_returned": len(interventions),
                "interventions_order": "latest_first",
                "interventions_truncated": projection["interventions_truncated"],
            },
        }

    @app.post("/v1/ask")
    async def ask(body: AskIn, _: None = Depends(_require_token)):
        from datetime import UTC, datetime

        from pex_supervisor.evidence_tools import workspace_evidence_guard
        from pex_supervisor.review_authority import review_invocation_guard

        from pex_bridge.ask import answer_question, asks_about_goal_completion
        from pex_bridge.workspace_access import workspace_read_check
        from pex_bridge.workspace_binding import WorkspaceAuthorityError

        try:
            await asyncio.wait_for(
                state.pipeline.refresh_desktop_sessions(),
                timeout=DESKTOP_REFRESH_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning("Ask refresh timed out; answering from durable state")
        forensic_goals = await state.store.list_goals_page(limit=200)
        goals: list[Goal] = []
        for forensic_goal in forensic_goals:
            goal = await state.store.get_goal_for_authority(forensic_goal.id)
            if goal is not None:
                goals.append(goal)
        interventions = []
        for goal in goals:
            interventions.extend(
                await state.store.list_interventions_for_goal_for_authority(
                    goal.id,
                    project_id=goal.project_id,
                    limit=20,
                )
            )
        authority_sessions: list[HarnessSession] = []
        for goal in goals:
            remaining = 1_000 - len(authority_sessions)
            if remaining <= 0:
                break
            authority_sessions.extend(
                await state.store.list_sessions_for_goal_for_authority(
                    goal.id,
                    project_id=goal.project_id,
                    limit=min(50, remaining),
                )
            )
        sessions = collapse_promptable_agents(authority_sessions, datetime.now(UTC))
        interventions.sort(key=lambda row: row.created_at, reverse=True)
        interventions = interventions[:20]
        items = await _ask_context_items(goals)
        if asks_about_goal_completion(body.question):
            lowered = body.question.casefold()
            named_goal_ids = {
                session.goal_id
                for session in sessions
                if session.goal_id is not None
                and session.harness_type.value.replace("_", " ") in lowered
            }
            latest_verified_goal_id = next(
                (
                    intervention.goal_id
                    for intervention in interventions
                    if intervention.goal_id is not None
                    and isinstance(intervention.metadata.get("verification"), dict)
                ),
                None,
            )
            candidate_goal_ids = (
                named_goal_ids
                if named_goal_ids
                else {latest_verified_goal_id}
                if latest_verified_goal_id is not None
                else {goal.id for goal in goals}
                if len(goals) == 1
                else set()
            )
            if len(candidate_goal_ids) != 1:
                return {
                    "answer": (
                        "PEX needs one specific active goal or agent name before reporting "
                        "completion; it will not combine evidence across goals."
                    )
                }
            try:
                for candidate in authority_sessions:
                    if (candidate.goal_id in candidate_goal_ids
                            and candidate.status != SessionStatus.DETACHED):
                        await state.store.require_session_workspace_current(candidate)
            except WorkspaceAuthorityError:
                return {
                    "answer": (
                        "Completion is uncertain: the workspace connection has changed. "
                        "Earlier STOP evidence cannot verify the replacement workspace."
                    )
                }
            completion = await state.store.goal_completion_projection(
                next(iter(candidate_goal_ids))
            )
            try:
                for candidate in authority_sessions:
                    if (candidate.goal_id in candidate_goal_ids
                            and candidate.status != SessionStatus.DETACHED):
                        await state.store.require_session_workspace_current(candidate)
            except WorkspaceAuthorityError:
                return {"answer": "Completion is uncertain: workspace authority changed."}
            answer = {
                "verified_complete": "Yes. Current-intent STOP evidence supports completion.",
                "incomplete": "No. Current evidence shows unmet acceptance requirements.",
                "in_progress": "Not yet. Newer work is active on this goal.",
                "uncertain": (
                    "Completion is uncertain; PEX has no current-intent supported STOP evidence."
                ),
            }[str(completion["status"])]
            return {"answer": answer, "completion": completion}
        # Match Ask's one selected review workspace. A model may inspect this
        # target only under server-owned publication authority, never metadata
        # alone. The scope is revoked even if a timed-out thread keeps running.
        selected = next((row for row in sessions if row.cwd), sessions[0] if sessions else None)
        try:
            witness = (
                await state.store.require_session_workspace_current(selected)
                if selected is not None else None
            )
            scope = (
                workspace_evidence_guard(
                    selected, workspace_read_check(state.store, selected, witness)
                )
                if witness is not None else nullcontext()
            )
            invocation_active = threading.Event()
            invocation_active.set()
            review_model = state.pipeline.model
            check = (
                workspace_read_check(state.store, selected, witness)
                if witness is not None else None
            )

            def check_invocation():
                if not invocation_active.is_set():
                    raise WorkspaceAuthorityError("Ask invocation expired before it started")
                if check is not None:
                    check()
                if not invocation_active.is_set():
                    raise WorkspaceAuthorityError("Ask invocation expired during validation")

            def invoke_answer():
                check_invocation()
                return answer_question(
                    body.question, sessions, interventions, goals,
                    review_model, context=items,
                )

            try:
                with scope, review_invocation_guard(check_invocation):
                    answer = await asyncio.wait_for(
                        asyncio.to_thread(invoke_answer),
                        timeout=ASK_MODEL_TIMEOUT_SECONDS,
                    )
            finally:
                invocation_active.clear()
            if selected is not None:
                await state.store.require_session_workspace_current(selected)
        except WorkspaceAuthorityError:
            answer = (
                "The selected workspace connection has changed. Reconnect it before "
                "using a fresh inspection; earlier observations remain in the timeline."
            )
        except TimeoutError:
            answer = answer_question(
                body.question,
                sessions,
                interventions,
                goals,
                None,
                context=items,
            )
        return {"answer": answer}

    @app.get("/v1/demo/trajectories")
    async def demo_trajectories(_: None = Depends(_require_token)):
        from pex_bridge.demo import list_fixtures

        return {"replay": True, "not_live_control": True, "fixtures": list_fixtures()}

    @app.post("/v1/demo/replay")
    async def demo_replay(body: DemoReplayIn, _: None = Depends(_require_token)):
        from pex_protocol.enums import EventPhase, EventType

        from pex_bridge.demo import load_fixture

        fixture_id = body.fixture
        try:
            data = load_fixture(fixture_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "unknown fixture") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        goal_spec = data.get("goal") or {}
        try:
            validated_goal = (
                GoalIn.model_validate(
                    {
                        **goal_spec,
                        "project_id": goal_spec.get("project_id") or "demo",
                        "title": goal_spec.get("title") or "Replay",
                    }
                )
                if goal_spec
                else None
            )
            replay_events = [
                DemoEventIn.model_validate(raw) for raw in data.get("events") or []
            ]
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "demo fixture violates the replay schema") from exc

        session = state.adapters.synthetic.seed_session(vendor_id=f"replay-{fixture_id}")
        session.metadata["replay"] = True
        session.metadata["not_live_control"] = True
        session.project_id = validated_goal.project_id if validated_goal else "demo"
        if validated_goal:
            now = utcnow()
            goal = Goal(
                **validated_goal.model_dump(),
                id=new_id("goal_"),
                created_at=now,
                updated_at=now,
            )
            await state.store.upsert_goal(goal)
            session.goal_id = goal.id
        await state.store.upsert_session(session)
        replay_pipeline = Pipeline(
            state.store,
            state.adapters,
            state.bus,
            state.settings,
            model=None,
        )
        replay_pipeline.supervisor = _RecordedReplaySupervisor()
        interventions = []
        for raw in replay_events:
            event_type = raw.event_type
            phase = EventPhase.BEFORE if event_type == EventType.SHELL else EventPhase.DURING
            if event_type == EventType.STOP:
                phase = EventPhase.TERMINAL
            event = state.adapters.synthetic.emit(
                session,
                event_type,
                phase=phase,
                message_delta=raw.message,
                command=raw.command,
            )
            intervention = await replay_pipeline.ingest_event(event, session)
            if intervention:
                interventions.append(intervention.model_dump(mode="json"))
        return {
            "replay": True,
            "not_live_control": True,
            "session_id": session.id,
            "inbox": state.adapters.synthetic.inbox.get(session.id, []),
            "interventions": interventions,
        }

    @app.get("/v1/adapters")
    async def adapters(_: None = Depends(_require_token)):
        registered = state.adapters.all()
        capabilities = await asyncio.gather(
            *[_bounded_adapter_probe(adapter) for adapter in registered]
        )
        return [
            {"name": adapter.name, "capabilities": caps.model_dump(mode="json")}
            for adapter, caps in zip(registered, capabilities, strict=True)
        ]

    @app.get("/v1/adapters/{name}/health")
    async def adapter_health(name: str, _: None = Depends(_require_token)):
        adapter = state.adapters.get(name)
        if not adapter:
            raise HTTPException(404, "adapter not found")
        try:
            return await asyncio.wait_for(
                adapter.health(), timeout=ADAPTER_PROBE_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:
            raise HTTPException(504, "adapter health probe timed out") from exc
        except Exception as exc:
            raise HTTPException(503, "adapter health probe failed") from exc

    @app.post("/v1/synthetic/sessions")
    async def synthetic_session(_: None = Depends(_require_token)):
        session = state.adapters.synthetic.seed_session()
        await state.store.upsert_session(session)
        return session.model_dump(mode="json")

    @app.post("/v1/synthetic/events")
    async def synthetic_event(body: SyntheticEventIn, _: None = Depends(_require_token)):
        session = await state.store.get_session_for_authority(body.session_id)
        if not session:
            raise HTTPException(404, "session not found")
        event = state.adapters.synthetic.emit(
            session,
            body.event_type,
            message_delta=body.message,
            command=body.command,
            tool_name=body.tool_name,
            file_paths=body.file_paths,
            process_state=body.process_state,
            error=body.error,
            **({"phase": body.phase} if body.phase else {}),
        )
        intervention = await state.pipeline.ingest_event(event, session)
        return {
            "event": event.model_dump(mode="json"),
            "intervention": intervention.model_dump(mode="json") if intervention else None,
            "inbox": state.adapters.synthetic.inbox.get(session.id, []),
        }

    @app.post("/v1/hooks/cursor")
    async def cursor_hook(
        payload: dict,
        principal: Annotated[HookPrincipal | None, Depends(_require_hook_access)],
    ):
        await _authorize_hook_payload(
            principal,
            harness_type=HarnessType.CURSOR,
            payload=payload,
        )
        if payload.get("hook_event_name") == "pexDeliveryReceipt":
            return await _record_cursor_delivery_ack(payload)
        return await apply_cursor_hook(payload)

    @app.post("/v1/hooks/{harness}")
    async def named_hook(
        harness: str,
        payload: dict,
        principal: Annotated[HookPrincipal | None, Depends(_require_hook_access)],
    ):
        if harness == "cursor":
            await _authorize_hook_payload(
                principal,
                harness_type=HarnessType.CURSOR,
                payload=payload,
            )
            if payload.get("hook_event_name") == "pexDeliveryReceipt":
                return await _record_cursor_delivery_ack(payload)
            return await apply_cursor_hook(payload)
        adapter = state.adapters.get(harness)
        if (
            adapter is None
            or getattr(adapter, "accepts_hooks", False) is not True
            or not hasattr(adapter, "ingest_hook")
        ):
            raise HTTPException(404, f"no hook surface for {harness}")
        try:
            harness_type = HarnessType(harness)
        except ValueError as exc:
            raise HTTPException(404, f"no hook surface for {harness}") from exc
        await _authorize_hook_payload(
            principal,
            harness_type=harness_type,
            payload=payload,
        )
        try:
            session = adapter.ingest_hook(payload)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        existing = await state.store.get_session_for_authority(session.id)
        if existing:
            session.goal_id = existing.goal_id
            session.supervision_paused = existing.supervision_paused
            if not getattr(session, "cwd", None):
                session.cwd = existing.cwd
            if not getattr(session, "project_id", None):
                session.project_id = existing.project_id
        await state.store.upsert_session(session)
        if hasattr(adapter, "normalize_hook"):
            event = adapter.normalize_hook(payload, session)
        else:
            status_text = str(payload.get("text") or payload.get("hook_event_name") or "event")
            event = adapter.emit_status(session, status_text)
            if payload.get("hook_event_name") in {
                "Stop",
                "stop",
                "SessionEnd",
                "on_session_end",
                "on_session_finalize",
                "UserPromptSubmit",
                "pre_llm_call",
            }:
                event.event_type = (
                    EventType.STOP
                    if payload.get("hook_event_name")
                    in {"Stop", "stop", "SessionEnd", "on_session_end", "on_session_finalize"}
                    else EventType.USER_PROMPT
                )
            if payload.get("hook_event_name") in {
                "PermissionRequest",
                "pre_tool_call",
                "PreToolUse",
            }:
                event.event_type = EventType.PERMISSION_REQUEST
        hook_name = str(payload.get("hook_event_name") or payload.get("hook") or "")
        if hook_name in _PRE_PERMISSION_HOOKS:
            try:
                intervention = await asyncio.wait_for(
                    state.pipeline.ingest_event(event, session),
                    timeout=NAMED_HOOK_PERMISSION_PIPELINE_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                intervention = None
            response = {
                "ok": True,
                "session_id": session.id,
                "inbox": getattr(adapter, "inbox", {}).get(session.id, []),
                "permission": _permission_from_intervention(intervention),
            }
            if hasattr(adapter, "hook_response"):
                response.update(adapter.hook_response(session, payload, intervention))
            return response
        pipeline_timeout = _named_hook_pipeline_timeout(
            harness,
            hook_name,
            event.event_type,
        )
        try:
            intervention = await asyncio.wait_for(
                state.pipeline.ingest_event(event, session),
                timeout=pipeline_timeout,
            )
        except TimeoutError:
            intervention = None
        inbox = getattr(adapter, "inbox", {}).get(session.id, [])
        response = {
            "ok": True,
            "session_id": session.id,
            "intervention": intervention.model_dump(mode="json") if intervention else None,
            "inbox": inbox,
        }
        if hasattr(adapter, "hook_response"):
            extra = adapter.hook_response(session, payload, intervention)
            if (
                hook_name in {"Stop", "stop"}
                and isinstance(extra, dict)
                and extra.get("decision") == "block"
                and str(extra.get("reason") or "").startswith("PEX:")
            ):
                extra = {k: v for k, v in extra.items() if k not in {"decision", "reason"}}
            response.update(extra)
        return response

    @app.get("/v1/events")
    async def get_events(
        _: None = Depends(_require_token),
        after: Annotated[str, Query(pattern=r"^(0|[1-9][0-9]{0,18})$")] = "0",
        through: Annotated[
            str | None,
            Query(pattern=r"^(0|[1-9][0-9]{0,18})$"),
        ] = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        session_id: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    ):
        """Read a frozen acceptance-ordered page from the canonical event ledger."""

        try:
            return await state.store.event_publication_page(
                after=int(after),
                through=int(through) if through is not None else None,
                limit=limit,
                session_id=session_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.websocket("/v1/events")
    async def ws_events(ws: WebSocket):
        origin = ws.headers.get("origin") or ""
        if origin not in TRUSTED_UI_ORIGINS:
            await ws.close(code=1008, reason="untrusted origin")
            return
        offered_protocols = [
            item.strip()
            for item in (ws.headers.get("sec-websocket-protocol") or "").split(",")
            if item.strip()
        ]
        if state.settings.require_auth:
            if ws.query_params.get("token"):
                # Query strings are routinely retained by access logs and
                # diagnostics.  The desktop uses a WebSocket subprotocol, and
                # non-browser clients can use Authorization instead.
                await ws.close(code=1008, reason="query-string tokens are not accepted")
                return
            supplied = ""
            authorization = ws.headers.get("authorization") or ""
            if not supplied and authorization:
                scheme, separator, candidate = authorization.partition(" ")
                if separator and scheme.casefold() == "bearer":
                    supplied = candidate
            if not supplied and len(offered_protocols) == 2:
                if offered_protocols[0] == "pex-v1":
                    supplied = _decode_websocket_token_protocol(offered_protocols[1]) or ""
            if not supplied or not secrets.compare_digest(supplied, state.token or ""):
                await ws.close(code=1008, reason="invalid token")
                return
        raw_after = ws.query_params.get("after") or "0"
        if (
            not raw_after.isascii()
            or not raw_after.isdigit()
            or (len(raw_after) > 1 and raw_after.startswith("0"))
            or len(raw_after) > 19
        ):
            await ws.close(code=1008, reason="invalid event cursor")
            return
        cursor = int(raw_after)
        outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=EVENT_SOCKET_QUEUE_SIZE
        )
        selected_protocol = "pex-v1" if "pex-v1" in offered_protocols else None
        try:
            await ws.accept(subprotocol=selected_protocol)
        except Exception:
            return
        # The capacity check and registration intentionally contain no await,
        # so they are one cooperative-event-loop step.  Registering only after
        # accept also prevents cancellation during the handshake from leaking
        # an unreachable socket into the capacity ledger.
        if not state.register_event_socket(ws, outbound):
            await ws.close(code=1013, reason="event socket capacity reached")
            return

        async def send_queued() -> None:
            while True:
                message = await outbound.get()
                try:
                    await asyncio.wait_for(
                        ws.send_json(message),
                        timeout=SOCKET_SEND_TIMEOUT_SECONDS,
                    )
                except TimeoutError:
                    await ws.close(code=1013, reason="event socket send timed out")
                    raise
                finally:
                    outbound.task_done()

        async def enqueue(topic: str, payload: dict[str, Any]) -> None:
            try:
                outbound.put_nowait({"topic": topic, "payload": payload})
            except asyncio.QueueFull:
                await ws.close(code=1013, reason="event socket queue full")
                raise RuntimeError("event socket queue full") from None

        async def send_initial_pet() -> None:
            await enqueue("pet", await state.live_pet())

        async def receive_client() -> None:
            while True:
                incoming = await ws.receive_text()
                if len(incoming) > MAX_WEBSOCKET_MESSAGE_CHARS:
                    await ws.close(code=1009, reason="message too large")
                    return

        sender: asyncio.Task[None] | None = None
        receiver: asyncio.Task[None] | None = None
        try:
            sender = asyncio.create_task(send_queued())
            await asyncio.wait_for(
                send_initial_pet(),
                timeout=SOCKET_SEND_TIMEOUT_SECONDS + DESKTOP_REFRESH_TIMEOUT_SECONDS,
            )
            receiver = asyncio.create_task(receive_client())
            caught_up = 0
            initial_catchup = True
            frozen_through: int | None = None
            last_send_at = asyncio.get_running_loop().time()
            while True:
                if sender.done():
                    await sender
                    return
                if receiver.done():
                    await receiver
                    return
                page = await state.store.event_publication_page(
                    after=cursor,
                    through=frozen_through,
                    limit=EVENT_SOCKET_CATCHUP_PAGE,
                )
                if page["gap"]["detected"]:
                    await enqueue("event_page", page)
                    # Flush the explicit gap receipt before the deterministic
                    # resync close, still under the bounded send deadline.
                    await asyncio.wait_for(
                        outbound.join(),
                        timeout=SOCKET_SEND_TIMEOUT_SECONDS,
                    )
                    await ws.close(code=1013, reason="event cursor retention gap")
                    return
                if frozen_through is None:
                    frozen_through = int(page["through"])
                if page["items"]:
                    if initial_catchup:
                        caught_up += len(page["items"])
                    if initial_catchup and caught_up > EVENT_SOCKET_MAX_CATCHUP:
                        await ws.close(code=1013, reason="event catch-up limit exceeded")
                        return
                    await enqueue("event_page", page)
                    last_send_at = asyncio.get_running_loop().time()
                    cursor = int(page["next"])
                    if page["has_more"]:
                        continue
                # Once the frozen backlog is exhausted, each poll freezes a new
                # current watermark. This gives a monotonic DB-backed tail.
                frozen_through = None
                initial_catchup = False
                if (
                    asyncio.get_running_loop().time() - last_send_at
                    >= EVENT_SOCKET_HEARTBEAT_SECONDS
                ):
                    await enqueue(
                        "heartbeat",
                        {"schema": "pex.event-heartbeat.v1", "cursor": str(cursor)},
                    )
                    last_send_at = asyncio.get_running_loop().time()
                try:
                    await asyncio.wait_for(
                        asyncio.shield(receiver),
                        timeout=EVENT_SOCKET_POLL_SECONDS,
                    )
                except TimeoutError:
                    pass
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            # Client disconnect cancels Starlette's per-socket handler. The
            # socket owns no authoritative mutation, so cleanup is terminal.
            pass
        except TimeoutError:
            try:
                await ws.close(code=1013, reason="event socket send timed out")
            except Exception:
                pass
        finally:
            # Unregister before the first cancellation point.  Test clients and
            # ASGI servers may cancel the handler at the same time they deliver
            # websocket.disconnect; AnyIO cancellation is level-triggered, so
            # an awaited child-task join or lock acquisition here can itself be
            # cancelled.  Leaving registry cleanup until after either await can
            # leak a dead socket and eventually exhaust MAX_EVENT_SOCKETS.
            state.detach_event_socket(ws)
            if sender is not None and not sender.done():
                sender.cancel()
            if receiver is not None and not receiver.done():
                receiver.cancel()
            children = [task for task in (sender, receiver) if task is not None]
            if children:
                try:
                    await asyncio.gather(*children, return_exceptions=True)
                except asyncio.CancelledError:
                    # Both children were already cancelled synchronously and
                    # the authoritative registry cleanup is complete.
                    pass

    return app
