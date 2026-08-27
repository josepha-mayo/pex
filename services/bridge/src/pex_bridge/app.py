from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventType, PolicyVerdict
from pex_protocol.goal import Goal
from pydantic import BaseModel, Field

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pets import (
    STARTERS,
    PetSettings,
    catalog,
    catalog_by_id,
    import_codex_pet,
    starters_by_id,
)
from pex_bridge.pets.hatch import HatchJob, HatchRegistry, run_hatch_job, slugify
from pex_bridge.pets.imagegen import describe_hatch_backend, probe_images_endpoint
from pex_bridge.pipeline import Pipeline, collapse_promptable_agents
from pex_bridge.store import Store, new_id, utcnow

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


def _permission_from_intervention(intervention: Any) -> str:
    if intervention is None:
        return "ask"
    verdict = intervention.policy_verdict
    value = verdict.value if hasattr(verdict, "value") else str(verdict or "")
    if value == PolicyVerdict.DENY.value:
        return "deny"
    if value == PolicyVerdict.ASK_HUMAN.value:
        return "ask"
    payload = {}
    proposed = getattr(intervention, "proposed_action", None)
    if proposed is not None:
        payload = proposed.payload or {}
    decision = str(payload.get("decision") or "").lower()
    if decision in {"deny", "ask"}:
        return decision
    return "allow"


TRUSTED_UI_ORIGINS = {
    "http://127.0.0.1:1420",
    "http://localhost:1420",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
}
TRUSTED_TAURI_ORIGINS = {
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
}


class AppState:
    def __init__(self) -> None:
        self.settings = Settings()
        self.store = Store(self.settings.resolved_db_path)
        self.adapters = AdapterRegistry()
        self.bus = EventBus()
        self.pipeline = Pipeline(self.store, self.adapters, self.bus, self.settings, model=None)
        self.token = self.settings.token
        self.sockets: list[WebSocket] = []
        self.pet_settings = PetSettings()
        self.pet_path = self.settings.data_dir / "pet.json"
        self.supervisor_error: str | None = None
        self.hatch = HatchRegistry(self.settings.data_dir / "hatch")

    async def broadcast(self, topic: str, payload: dict[str, Any]) -> None:
        if topic == "pet":
            payload = self.decorate_pet(payload)
        dead: list[WebSocket] = []
        for ws in self.sockets:
            try:
                await ws.send_json({"topic": topic, "payload": payload})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.remove(ws)

    def decorate_pet(self, snap: dict[str, Any]) -> dict[str, Any]:
        chosen = catalog_by_id(self.pet_settings).get(self.pet_settings.selected_id, STARTERS[0])
        appearance = chosen.model_dump(mode="json")
        if self.pet_settings.custom_name:
            appearance["display_name"] = self.pet_settings.custom_name
        appearance["spritesheet_url"] = f"/v1/pets/{chosen.id}/spritesheet"
        appearance["hue_shift"] = self.pet_settings.hue_shift
        appearance["scale"] = self.pet_settings.scale
        appearance["atlas_ready"] = bool(chosen.atlas_ready)
        snap["appearance"] = appearance
        snap["settings"] = self.pet_settings.model_dump(mode="json")
        last = snap.get("last_action") or {}
        if snap.get("needs_you"):
            snap["mood"] = "decision"
        elif snap.get("blocked"):
            snap["mood"] = "warning"
        elif snap.get("drifting"):
            snap["mood"] = "drift"
        elif snap.get("working"):
            snap["mood"] = "working"
        elif last.get("action") in {"SEND_NUDGE", "VERIFY", "HANDOFF_CONTEXT"}:
            snap["mood"] = "observing"
        else:
            snap["mood"] = "idle"
        return snap

    async def live_pet(self) -> dict[str, Any]:
        await self.pipeline.refresh_desktop_sessions()
        return self.decorate_pet(await self.pipeline.pet_snapshot())


state = AppState()


def _start_event_pumps() -> None:
    for adapter in state.adapters.all():
        starter = getattr(adapter, "start_pipeline_pump", None)
        if starter is None:
            continue
        starter(state.pipeline.ingest_event)


def _supervisor_health() -> dict[str, Any]:
    from pex_supervisor.providers import describe_backend

    info = describe_backend()
    info["model_loaded"] = state.pipeline.model is not None
    return info


async def _require_token(authorization: str | None = Header(default=None)) -> None:
    if not state.settings.require_auth:
        return
    expected = state.token or ""
    if not expected:
        return
    if not authorization or authorization.split(" ", 1)[-1] != expected:
        raise HTTPException(status_code=401, detail="invalid token")


class GoalIn(BaseModel):
    project_id: str
    title: str
    objective: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    forbidden_outcomes: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    priority: int = 0


class AttachIn(BaseModel):
    goal_id: str


class MessageIn(BaseModel):
    text: str


class HandoffIn(BaseModel):
    target_session_id: str


class AskIn(BaseModel):
    question: str = "what needs me?"


class PetSettingsIn(BaseModel):
    selected_id: str | None = None
    custom_name: str | None = None
    hue_shift: int | None = None
    scale: float | None = None
    click_through: bool | None = None
    quiet: bool | None = None
    imported_codex_dir: str | None = None


class ImportPetIn(BaseModel):
    directory: str


class HatchIn(BaseModel):
    display_name: str
    description: str = ""
    style_preset: str = "plush"
    pet_notes: str = ""


class SupervisorIn(BaseModel):
    provider: str | None = None
    model_id: str | None = None


class SyntheticEventIn(BaseModel):
    session_id: str
    event_type: EventType
    message: str | None = None
    command: str | None = None
    tool_name: str | None = None
    file_paths: list[str] = Field(default_factory=list)
    phase: str | None = None
    process_state: dict | None = None
    error: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await state.store.connect()
    if state.settings.require_auth:
        if state.settings.token_path.exists():
            state.token = state.settings.token_path.read_text(encoding="utf-8").strip()
        else:
            state.token = secrets.token_urlsafe(32)
            state.settings.token_path.write_text(state.token, encoding="utf-8")
    pet_file = state.settings.data_dir / "pet.json"
    if pet_file.exists():
        state.pet_settings = PetSettings.model_validate_json(pet_file.read_text(encoding="utf-8"))
        state.pet_path = pet_file
    from pex_bridge.pets import maybe_import_codex_home

    state.pet_settings = maybe_import_codex_home(state.pet_settings)
    if state.pet_settings.selected_id not in catalog_by_id(state.pet_settings):
        state.pet_settings.selected_id = STARTERS[0].id
    state.pet_path = pet_file
    pet_file.parent.mkdir(parents=True, exist_ok=True)
    pet_file.write_text(state.pet_settings.model_dump_json(indent=2), encoding="utf-8")
    state.bus.subscribe(state.broadcast)
    from pex_bridge.adapters.attach import attach_from_settings

    await attach_from_settings(state.adapters, state.settings)
    _start_event_pumps()
    from pex_supervisor.providers import apply_runtime_choice, load_supervisor_model

    choice_file = state.settings.data_dir / "supervisor.json"
    if choice_file.is_file():
        try:
            saved = json.loads(choice_file.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                apply_runtime_choice(
                    provider=saved.get("provider"),
                    model_id=saved.get("model_id"),
                )
        except (OSError, ValueError, json.JSONDecodeError):
            logger.exception("Could not apply saved supervisor choice")
    try:
        state.pipeline.model = load_supervisor_model()
        state.supervisor_error = None
    except Exception as exc:
        state.pipeline.model = None
        state.supervisor_error = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "Supervisor provider failed to load; deterministic supervision remains active"
        )
    yield
    for adapter in state.adapters.all():
        pump = getattr(adapter, "_pump_task", None)
        if pump is not None:
            pump.cancel()
            try:
                await pump
            except asyncio.CancelledError:
                pass
        transport = getattr(adapter, "transport", None)
        if transport is None and getattr(adapter, "acp", None) is not None:
            transport = getattr(adapter.acp, "transport", None)
        closer = getattr(transport, "close", None) or getattr(transport, "aclose", None)
        if closer:
            await closer()
    await state.store.close()


def create_app() -> FastAPI:
    app = FastAPI(title="PEX Bridge", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(TRUSTED_UI_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        attached = []
        for adapter in state.adapters.all():
            caps = await adapter.probe()
            if caps.support_label.value in {"deep", "strong", "basic"} and caps.trust_level > 0:
                attached.append(adapter.name)
        return {
            "ok": True,
            "service": "pex-bridge",
            "attached": attached,
            "supervisor": "degraded" if state.supervisor_error else "ready",
            "supervisor_error": state.supervisor_error,
            "supervisor_backend": _supervisor_health(),
        }

    @app.get("/v1/supervisor")
    async def get_supervisor(_: None = Depends(_require_token)):
        from pex_supervisor.catalog import catalog as model_catalog

        info = _supervisor_health()
        info["catalog"] = model_catalog()
        info["note"] = "Keys stay in .env. This response never includes secrets."
        return info

    @app.patch("/v1/supervisor")
    async def patch_supervisor(body: SupervisorIn, _: None = Depends(_require_token)):
        from pex_supervisor.catalog import catalog as model_catalog
        from pex_supervisor.providers import apply_runtime_choice, load_supervisor_model

        try:
            info = apply_runtime_choice(provider=body.provider, model_id=body.model_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        choice_file = state.settings.data_dir / "supervisor.json"
        payload = {
            "provider": info.get("backend"),
            "model_id": info.get("model_id"),
        }
        choice_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            state.pipeline.model = load_supervisor_model()
            state.supervisor_error = None
        except Exception as exc:
            state.pipeline.model = None
            state.supervisor_error = f"{type(exc).__name__}: {exc}"
        info["model_loaded"] = state.pipeline.model is not None
        info["catalog"] = model_catalog()
        info["note"] = "Keys stay in .env. This response never includes secrets."
        return info

    @app.get("/v1/discover")
    async def discover(_: None = Depends(_require_token)):
        from pex_bridge.adapters.discover import probe_local_harnesses

        found = await probe_local_harnesses()
        return {"found": found}

    @app.post("/v1/discover/attach")
    async def discover_attach(body: dict, _: None = Depends(_require_token)):
        from pex_bridge.adapters.codex import CodexStdioTransport
        from pex_bridge.adapters.discover import probe_local_harnesses
        from pex_bridge.adapters.http_json import LiveHttpTransport

        name = str(body.get("name") or "")
        kind = body.get("kind")
        found = await probe_local_harnesses()
        if kind:
            match = next(
                (item for item in found if item["name"] == name and item.get("kind") == kind),
                None,
            )
        else:
            match = next((item for item in found if item["name"] == name), None)
        if match is None:
            raise HTTPException(404, "no local desktop app or daemon found")
        adapter = state.adapters.get(name)
        if adapter is None:
            raise HTTPException(404, "adapter not found")
        if match.get("kind") == "desktop":
            if name == "cursor":
                from pex_bridge.adapters.cursor_hooks import install_user_hooks

                path = install_user_hooks()
                caps = await adapter.probe()
                return {
                    "ok": True,
                    "name": name,
                    "kind": "desktop",
                    "hooks": str(path),
                    "support": caps.support_label.value,
                    "note": "Installed Cursor desktop hooks. CLI ACP was not spawned.",
                }
            if name == "codex":
                sessions = await adapter.discover_sessions()
                caps = await adapter.probe()
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
            sessions = await adapter.discover_sessions()
            caps = await adapter.probe()
            return {
                "ok": True,
                "name": name,
                "kind": "desktop",
                "support": caps.support_label.value,
                "sessions": len(sessions),
                "note": match.get("surface"),
            }
        if match.get("kind") == "cli":
            caps = await adapter.probe()
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
                adapter.attach_transport(CodexStdioTransport(match["bin"]))
                _start_event_pumps()
            elif name in {"hermes", "kimi", "omp"}:
                from pex_bridge.adapters.acp_client import StdioAcpTransport
                from pex_bridge.adapters.hermes_bin import acp_command as hermes_acp

                command = hermes_acp(match["bin"]) if name == "hermes" else [match["bin"], "acp"]
                adapter.attach_acp(StdioAcpTransport(command))
            elif name == "grok_build":
                from pex_bridge.adapters.acp_client import StdioAcpTransport
                from pex_bridge.adapters.grok_build_bin import acp_command as grok_acp

                adapter.attach_acp(StdioAcpTransport(grok_acp(match["bin"])))
            else:
                raise HTTPException(400, f"no stdio/ACP attach path for {name}")
            caps = await adapter.probe()
            return {
                "ok": True,
                "name": name,
                "kind": match.get("kind"),
                "bin": match["bin"],
                "support": caps.support_label.value,
            }
        if not hasattr(adapter, "attach_transport"):
            raise HTTPException(400, "adapter cannot attach HTTP")
        adapter.attach_transport(LiveHttpTransport(match["base_url"], token=body.get("token")))
        _start_event_pumps()
        caps = await adapter.probe()
        return {
            "ok": True,
            "name": name,
            "base_url": match["base_url"],
            "support": caps.support_label.value,
        }

    @app.post("/v1/adapters/{name}/attach")
    async def attach_adapter(name: str, body: dict, _: None = Depends(_require_token)):
        from pex_bridge.adapters.codex import CodexStdioTransport
        from pex_bridge.adapters.codex_bin import resolve_codex_bin
        from pex_bridge.adapters.http_json import LiveHttpTransport

        adapter = state.adapters.get(name)
        if adapter is None:
            raise HTTPException(404, "adapter not found")
        if name in {"kimi", "hermes", "omp"}:
            from pex_bridge.adapters.acp_client import StdioAcpTransport
            from pex_bridge.adapters.hermes_bin import acp_command as hermes_acp
            from pex_bridge.adapters.hermes_bin import resolve_hermes

            binary = body.get("bin")
            if not binary and name == "hermes":
                binary = resolve_hermes()
            if not binary:
                raise HTTPException(400, f"{name} ACP binary not found; pass bin")
            command = hermes_acp(binary) if name == "hermes" else [binary, "acp"]
            adapter.attach_acp(StdioAcpTransport(command))
            caps = await adapter.probe()
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

            binary = body.get("bin") or resolve_grok_build()
            if not binary:
                raise HTTPException(400, "Grok Build CLI not found")
            adapter.attach_acp(StdioAcpTransport(grok_acp(binary)))
            caps = await adapter.probe()
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
            from pex_bridge.adapters.cursor_hooks import install_user_hooks

            if body.get("kind") == "acp":
                raise HTTPException(
                    400,
                    (
                        "Cursor ACP CLI is not auto-installed. "
                        "Desktop control is ~/.cursor/hooks.json."
                    ),
                )
            path = install_user_hooks()
            caps = await adapter.probe()
            return {
                "ok": True,
                "name": name,
                "kind": "desktop",
                "hooks": str(path),
                "support": caps.support_label.value,
                "note": "Installed Cursor desktop hooks. No cursor-agent CLI was spawned.",
            }
        if name == "codex":
            binary = body.get("bin") or resolve_codex_bin()
            if not binary:
                raise HTTPException(400, "codex binary not found; set PEX_CODEX_BIN")
            adapter.attach_transport(CodexStdioTransport(binary))
            _start_event_pumps()
            caps = await adapter.probe()
            return {
                "ok": True,
                "name": name,
                "kind": "stdio",
                "bin": binary,
                "support": caps.support_label.value,
            }
        if not hasattr(adapter, "attach_transport"):
            raise HTTPException(404, "adapter cannot attach a live transport")
        url = body.get("url")
        if not url:
            raise HTTPException(400, "url required")
        transport = LiveHttpTransport(url, token=body.get("token"))
        if name == "devin":
            adapter.attach_transport(transport, org_id=body.get("org_id"))
        else:
            adapter.attach_transport(transport)
        _start_event_pumps()
        caps = await adapter.probe()
        return {"ok": True, "name": name, "support": caps.support_label.value}

    @app.get("/v1/goals")
    async def list_goals(_: None = Depends(_require_token)):
        return [g.model_dump(mode="json") for g in await state.store.list_goals()]

    @app.get("/v1/pet")
    async def pet(_: None = Depends(_require_token)):
        return await state.live_pet()

    @app.get("/v1/pets")
    async def list_pets(_: None = Depends(_require_token)):
        return {
            "starters": [p.model_dump(mode="json") for p in STARTERS],
            "catalog": [p.model_dump(mode="json") for p in catalog(state.pet_settings)],
            "settings": state.pet_settings.model_dump(mode="json"),
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

        if chosen.spritesheet and Path(chosen.spritesheet).is_file():
            return Response(content=Path(chosen.spritesheet).read_bytes(), media_type="image/webp")
        from pex_bridge.pets.atlas import cached_bytes

        cache = str(state.settings.data_dir / "pets")
        data = cached_bytes(pet_id, int(state.pet_settings.hue_shift), cache)
        return Response(content=data, media_type="image/webp")

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
        state.pet_settings = PetSettings.model_validate(data)
        state.pet_path.write_text(state.pet_settings.model_dump_json(indent=2), encoding="utf-8")
        return state.pet_settings.model_dump(mode="json")

    @app.post("/v1/pets/import")
    async def import_pet(body: ImportPetIn, _: None = Depends(_require_token)):
        try:
            imported = import_codex_pet(body.directory)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        imports = [item for item in state.pet_settings.imports if item.id != imported.id]
        imports.append(imported)
        state.pet_settings.imports = imports
        state.pet_settings.selected_id = imported.id
        state.pet_settings.imported_codex_dir = imported.directory
        state.pet_path.write_text(state.pet_settings.model_dump_json(indent=2), encoding="utf-8")
        return imported.model_dump(mode="json")

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
    async def start_hatch(body: HatchIn, _: None = Depends(_require_token)):
        name = body.display_name.strip()
        if not name:
            raise HTTPException(400, "display_name is required")
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
        )
        state.hatch.create(job)
        asyncio.create_task(asyncio.to_thread(run_hatch_job, state.hatch, job.id))
        return job.public()

    @app.get("/v1/sessions")
    async def sessions(_: None = Depends(_require_token)):
        await state.pipeline.refresh_desktop_sessions()
        return [s.model_dump(mode="json") for s in await state.store.list_sessions()]

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str, _: None = Depends(_require_token)):
        session = await state.store.get_session(session_id)
        if not session:
            raise HTTPException(404, "session not found")
        return session.model_dump(mode="json")

    @app.post("/v1/goals")
    async def create_goal(body: GoalIn, _: None = Depends(_require_token)):
        now = utcnow()
        goal = Goal(
            id=new_id("goal_"),
            created_at=now,
            updated_at=now,
            **body.model_dump(),
        )
        await state.store.upsert_goal(goal)
        return goal.model_dump(mode="json")

    @app.get("/v1/goals/{goal_id}")
    async def get_goal(goal_id: str, _: None = Depends(_require_token)):
        goal = await state.store.get_goal(goal_id)
        if not goal:
            raise HTTPException(404, "goal not found")
        return goal.model_dump(mode="json")

    @app.post("/v1/sessions/{session_id}/attach")
    async def attach(session_id: str, body: AttachIn, _: None = Depends(_require_token)):
        session = await state.store.get_session(session_id)
        if not session:
            raise HTTPException(404, "session not found")
        session.goal_id = body.goal_id
        await state.store.upsert_session(session)
        return session.model_dump(mode="json")

    @app.post("/v1/sessions/{session_id}/message")
    async def message(session_id: str, body: MessageIn, _: None = Depends(_require_token)):
        session = await state.store.get_session(session_id)
        adapter = state.adapters.for_session(session_id)
        if not session or not adapter:
            raise HTTPException(404, "session not found")
        ok = await adapter.send_message(session, body.text)
        return {"ok": ok}

    @app.post("/v1/sessions/{session_id}/focus")
    async def focus(session_id: str, _: None = Depends(_require_token)):
        session = await state.store.get_session(session_id)
        adapter = state.adapters.for_session(session_id)
        if not session or not adapter:
            raise HTTPException(404, "session not found")
        ok = await adapter.focus_ui(session)
        return {"ok": ok}

    @app.post("/v1/harnesses/{name}/focus")
    async def focus_harness_named(name: str, _: None = Depends(_require_token)):
        from pex_bridge.adapters.winfocus import focus_harness

        return {"ok": focus_harness(name)}

    @app.post("/v1/sessions/{session_id}/pause-supervision")
    async def pause(session_id: str, _: None = Depends(_require_token)):
        session = await state.store.get_session(session_id)
        if not session:
            raise HTTPException(404, "session not found")
        session.supervision_paused = True
        await state.store.upsert_session(session)
        return {"ok": True}

    @app.post("/v1/sessions/{session_id}/resume-supervision")
    async def resume(session_id: str, _: None = Depends(_require_token)):
        session = await state.store.get_session(session_id)
        if not session:
            raise HTTPException(404, "session not found")
        session.supervision_paused = False
        await state.store.upsert_session(session)
        return {"ok": True}

    @app.post("/v1/sessions/{session_id}/handoff")
    async def handoff(session_id: str, body: HandoffIn, _: None = Depends(_require_token)):
        from pex_bridge.context.mesh import build_bundle

        source = await state.store.get_session(session_id)
        target = await state.store.get_session(body.target_session_id)
        if not source or not target or not source.goal_id:
            raise HTTPException(400, "handoff requires attached source and target")
        goal = await state.store.get_goal(source.goal_id)
        if not goal:
            raise HTTPException(404, "goal not found")
        items = await state.store.list_context(source.project_id or goal.project_id)
        recent = await state.store.recent_events(source.id)
        bundle = build_bundle(goal, target, items, recent, [source.id])
        adapter = state.adapters.for_session(target.id)
        if not adapter:
            raise HTTPException(400, "no adapter for target")
        ok = await adapter.inject_context(target, bundle)
        target.goal_id = source.goal_id
        await state.store.upsert_session(target)
        return {"ok": ok, "bundle": bundle.model_dump(mode="json")}

    @app.get("/v1/interventions")
    async def interventions(session_id: str | None = None, _: None = Depends(_require_token)):
        return [i.model_dump(mode="json") for i in await state.store.list_interventions(session_id)]

    @app.post("/v1/interventions/{intervention_id}/undo")
    async def undo_intervention(intervention_id: str, _: None = Depends(_require_token)):
        items = await state.store.list_interventions()
        found = next((item for item in items if item.id == intervention_id), None)
        if found is None:
            raise HTTPException(404, "intervention not found")
        if not found.reversible:
            raise HTTPException(400, "intervention is not reversible")
        adapter = state.adapters.for_session(found.session_id)
        session = await state.store.get_session(found.session_id)
        if adapter is None or session is None:
            raise HTTPException(400, "session gone")
        if found.action_taken == "APPLY_OVERLAY":
            overlay_id = str(found.proposed_action.payload.get("overlay", {}).get("id") or "")
            await adapter.revert_overlay(overlay_id)
        else:
            await adapter.send_message(
                session,
                "PEX undo: ignore the previous supervisor nudge if it is still in your queue.",
            )
        return {"ok": True, "undone": found.id}

    @app.get("/v1/context")
    async def list_context(project_id: str | None = None, _: None = Depends(_require_token)):
        if not project_id:
            goals = await state.store.list_goals()
            project_id = goals[0].project_id if goals else None
        if not project_id:
            return []
        return [item.model_dump(mode="json") for item in await state.store.list_context(project_id)]

    @app.get("/v1/deck")
    async def command_deck(_: None = Depends(_require_token)):
        sessions = await state.store.list_sessions()
        interventions = await state.store.list_interventions()
        adapters = []
        for adapter in state.adapters.all():
            caps = await adapter.probe()
            adapters.append({"name": adapter.name, "capabilities": caps.model_dump(mode="json")})
        fingerprints = {}
        for session in sessions:
            key = session.harness_type.value
            bucket = fingerprints.setdefault(
                key,
                {
                    "harness": key,
                    "observed_sessions": 0,
                    "models": set(),
                    "premature_stops": 0,
                },
            )
            bucket["observed_sessions"] += 1
            if session.model:
                bucket["models"].add(session.model)
        for item in interventions:
            if item.trigger == "stop":
                harness = item.session_id.split(":", 1)[0]
                if harness in fingerprints:
                    fingerprints[harness]["premature_stops"] += 1
        pretty = []
        for bucket in fingerprints.values():
            pretty.append(
                {
                    "harness": bucket["harness"],
                    "observed_sessions": bucket["observed_sessions"],
                    "models": sorted(bucket["models"]),
                    "premature_stop_rate": (
                        bucket["premature_stops"] / bucket["observed_sessions"]
                        if bucket["observed_sessions"]
                        else 0.0
                    ),
                    "recommended_overlays": (
                        ["evidence-before-done"] if bucket["premature_stops"] else []
                    ),
                }
            )
        return {
            "sessions": [s.model_dump(mode="json") for s in sessions],
            "interventions": [i.model_dump(mode="json") for i in interventions[:40]],
            "adapters": adapters,
            "fingerprints": pretty,
        }

    @app.post("/v1/ask")
    async def ask(body: AskIn, _: None = Depends(_require_token)):
        from datetime import UTC, datetime

        from pex_bridge.ask import answer_question

        await state.pipeline.refresh_desktop_sessions()
        sessions = collapse_promptable_agents(
            await state.store.list_sessions(), datetime.now(UTC)
        )
        interventions = await state.store.list_interventions()
        goals = await state.store.list_goals()
        answer = await asyncio.to_thread(
            answer_question,
            body.question,
            sessions,
            interventions,
            goals,
            state.pipeline.model,
        )
        return {"answer": answer}

    @app.get("/v1/demo/trajectories")
    async def demo_trajectories(_: None = Depends(_require_token)):
        from pex_bridge.demo import list_fixtures

        return {"replay": True, "not_live_control": True, "fixtures": list_fixtures()}

    @app.post("/v1/demo/replay")
    async def demo_replay(body: dict, _: None = Depends(_require_token)):
        from pex_protocol.enums import EventPhase, EventType

        from pex_bridge.demo import load_fixture

        fixture_id = str(body.get("fixture") or "")
        try:
            data = load_fixture(fixture_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "unknown fixture") from exc
        session = state.adapters.synthetic.seed_session(vendor_id=f"replay-{fixture_id}")
        session.metadata["replay"] = True
        session.metadata["not_live_control"] = True
        session.project_id = (data.get("goal") or {}).get("project_id") or "demo"
        goal_spec = data.get("goal") or {}
        if goal_spec:
            now = utcnow()
            goal = Goal(
                id=new_id("goal_"),
                created_at=now,
                updated_at=now,
                project_id=str(goal_spec.get("project_id") or "demo"),
                title=str(goal_spec.get("title") or "Replay"),
                objective=str(goal_spec.get("objective") or ""),
                acceptance_criteria=list(goal_spec.get("acceptance_criteria") or []),
                evidence_requirements=list(goal_spec.get("evidence_requirements") or []),
            )
            await state.store.upsert_goal(goal)
            session.goal_id = goal.id
        await state.store.upsert_session(session)
        interventions = []
        for raw in data.get("events") or []:
            event_type = EventType(raw.get("event_type") or "status")
            phase = EventPhase.BEFORE if event_type == EventType.SHELL else EventPhase.DURING
            if event_type == EventType.STOP:
                phase = EventPhase.TERMINAL
            event = state.adapters.synthetic.emit(
                session,
                event_type,
                phase=phase,
                message_delta=raw.get("message"),
                command=raw.get("command"),
            )
            intervention = await state.pipeline.ingest_event(event, session)
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
        out = []
        for adapter in state.adapters.all():
            caps = await adapter.probe()
            out.append({"name": adapter.name, "capabilities": caps.model_dump(mode="json")})
        return out

    @app.get("/v1/adapters/{name}/health")
    async def adapter_health(name: str, _: None = Depends(_require_token)):
        adapter = state.adapters.get(name)
        if not adapter:
            raise HTTPException(404, "adapter not found")
        return await adapter.health()

    @app.post("/v1/synthetic/sessions")
    async def synthetic_session(_: None = Depends(_require_token)):
        session = state.adapters.synthetic.seed_session()
        await state.store.upsert_session(session)
        return session.model_dump(mode="json")

    @app.post("/v1/synthetic/events")
    async def synthetic_event(body: SyntheticEventIn, _: None = Depends(_require_token)):
        session = await state.store.get_session(body.session_id)
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
    async def cursor_hook(payload: dict, _: None = Depends(_require_token)):
        adapter = state.adapters.cursor
        session = adapter.upsert_from_hook(payload)
        existing = await state.store.get_session(session.id)
        if existing:
            session.goal_id = existing.goal_id
            session.supervision_paused = existing.supervision_paused
        await state.store.upsert_session(session)
        event = adapter.normalize_hook(payload, session)
        hook_name = payload.get("hook_event_name")
        response: dict[str, Any] = {}
        if hook_name in _PRE_PERMISSION_HOOKS:
            try:
                intervention = await asyncio.wait_for(
                    state.pipeline.ingest_event(event, session),
                    timeout=8,
                )
            except TimeoutError:
                response["permission"] = "ask"
                return response
            response["permission"] = _permission_from_intervention(intervention)
            return response
        if hook_name == "beforeSubmitPrompt":
            try:
                intervention = await asyncio.wait_for(
                    state.pipeline.ingest_event(event, session),
                    timeout=2,
                )
            except TimeoutError:
                response["continue"] = True
                return response
            if intervention and intervention.proposed_action.type == InterventionType.ASK_HUMAN:
                response["continue"] = False
                response["user_message"] = intervention.proposed_action.payload.get(
                    "question", "Conflicts with persistent goal."
                )
            else:
                response["continue"] = True
            return response
        intervention = await state.pipeline.ingest_event(event, session)
        if hook_name == "stop":
            followup = adapter.consume_followup(session.id)
            used_llm = bool(intervention and (intervention.metadata or {}).get("used_llm"))
            text = (followup or "").strip()
            if used_llm and text and not text.startswith("PEX:"):
                response["followup_message"] = text
        return response

    @app.post("/v1/hooks/{harness}")
    async def named_hook(harness: str, payload: dict, _: None = Depends(_require_token)):
        if harness == "cursor":
            return await cursor_hook(payload)
        adapter = state.adapters.get(harness)
        if adapter is None or not hasattr(adapter, "ingest_hook"):
            raise HTTPException(404, f"no hook surface for {harness}")
        session = adapter.ingest_hook(payload)
        existing = await state.store.get_session(session.id)
        if existing:
            session.goal_id = existing.goal_id
            session.supervision_paused = existing.supervision_paused
        await state.store.upsert_session(session)
        if hasattr(adapter, "normalize_hook"):
            event = adapter.normalize_hook(payload, session)
        else:
            status_text = str(
                payload.get("text") or payload.get("hook_event_name") or "event"
            )
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
                    timeout=8,
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
        intervention = await state.pipeline.ingest_event(event, session)
        inbox = getattr(adapter, "inbox", {}).get(session.id, [])
        response = {
            "ok": True,
            "session_id": session.id,
            "intervention": intervention.model_dump(mode="json") if intervention else None,
            "inbox": inbox,
        }
        if hasattr(adapter, "hook_response"):
            extra = adapter.hook_response(session, payload, intervention)
            output = extra.get("hookSpecificOutput") if isinstance(extra, dict) else None
            if (
                hook_name in {"Stop", "stop"}
                and isinstance(output, dict)
                and str(output.get("additionalContext") or "").startswith("PEX:")
            ):
                extra = {k: v for k, v in extra.items() if k != "hookSpecificOutput"}
            response.update(extra)
        return response

    @app.websocket("/v1/events")
    async def ws_events(ws: WebSocket):
        origin = ws.headers.get("origin") or ""
        if origin not in TRUSTED_UI_ORIGINS:
            await ws.close(code=1008, reason="untrusted origin")
            return
        if state.settings.require_auth and origin not in TRUSTED_TAURI_ORIGINS:
            supplied = ws.query_params.get("token") or ""
            authorization = ws.headers.get("authorization") or ""
            if not supplied and authorization:
                supplied = authorization.split(" ", 1)[-1]
            if not supplied or supplied != (state.token or ""):
                await ws.close(code=1008, reason="invalid token")
                return
        await ws.accept()
        state.sockets.append(ws)
        try:
            await ws.send_json({"topic": "pet", "payload": await state.live_pet()})
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            if ws in state.sockets:
                state.sockets.remove(ws)

    return app
