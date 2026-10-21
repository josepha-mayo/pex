"""Local hosted-replay contract. No production runner or public deployment supplied.

Deliberately does not import bridge.main, adapters, settings, or the global store.
A runner is a trusted server-side dependency, never selectable through HTTP.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import shutil
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from pex_bridge.replay_job import ReplayJobResult, encode_result

LABELS = {"replay": True, "not_live_control": True}
# Intentional allowlist, not directory discovery or user-supplied paths.
CATALOGUE = {
    "premature_stop_eval": "False completion without tests",
    "tampered_acceptance_eval": "Reward hacking: edited acceptance test",
}


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    fixture_id: Literal["premature_stop_eval", "tampered_acceptance_eval"]
    idempotency_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


@dataclass(frozen=True)
class RunContext:
    run_id: str
    fixture_path: Path
    pex_home: Path
    workspace: Path


class ReplayRunner(Protocol):
    async def execute(self, context: RunContext) -> ReplayJobResult | Literal["completed"]:
        """Execute real isolated replay; return only after its work is stopped.

        On cancellation, kill and reap all children before returning/raising.
        Must enforce CPU, disk, process and network limits independently of this
        Python deadline. Never load owner credentials or discover live adapters.
        A ReplayJobResult carries bounded adjudicated evidence. The legacy
        'completed' sentinel is explicitly status-only, with no result endpoint
        payload, and never implies that claims were verified.
        """
        ...


@dataclass(frozen=True)
class Limits:
    max_visitors: int = 32
    max_runs_per_visitor: int = 4
    max_concurrent_runs: int = 2
    visitor_ttl_seconds: float = 900
    run_timeout_seconds: float = 30
    max_body_bytes: int = 2048

    def __post_init__(self):
        if any(value <= 0 for value in vars(self).values()):
            raise ValueError("All limits must be positive")


@dataclass
class Run:
    id: str
    fixture_id: str
    state: str = "running"
    error: str | None = None
    result_json: bytes | None = None

    def public(self):
        return {
            "run_id": self.id,
            "fixture_id": self.fixture_id,
            "state": self.state,
            "error": self.error,
            **LABELS,
        }


@dataclass
class Visitor:
    expires_at: float
    runs: dict[str, Run] = field(default_factory=dict)


def create_hosted_replay_app(
    *,
    allowed_origin: str,
    state_root: Path,
    fixture_root: Path,
    runner: ReplayRunner | None = None,
    limits: Limits | None = None,
    clock=time.monotonic,
) -> FastAPI:
    """Construct a single-process, in-memory contract for local verification.

    No CLI or listening socket is created. Origin checking is browser defense,
    not user identity or Internet abuse protection. Bearer capabilities confer
    ownership; a public deployment additionally needs TLS and edge admission.
    """
    if not allowed_origin or allowed_origin == "*":
        raise ValueError("An exact allowed origin is required")
    limits = limits or Limits()
    state_root = state_root.resolve()
    fixture_root = fixture_root.resolve()
    visitors: dict[str, Visitor] = {}
    tasks: set[asyncio.Task] = set()
    stopping = False
    lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_app):
        nonlocal stopping
        try:
            yield
        finally:
            stopping = True
            pending = list(tasks)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            visitors.clear()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        # Browsers commonly omit Origin on same-origin GET/fetch requests.
        # This exception is read-only; run reads still require bearer ownership.
        if origin != allowed_origin and not (request.method == "GET" and origin is None):
            return JSONResponse({"detail": "origin_denied"}, status_code=403)
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            chunks.append(chunk)
            if size > limits.max_body_bytes:
                return JSONResponse({"detail": "request_too_large"}, status_code=413)
        # Starlette caches body only through body(), not stream(). Rebuild the
        # bounded body for downstream validation instead of trusting Content-Length.
        request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    def prune():
        for key, visitor in list(visitors.items()):
            if visitor.expires_at <= clock():
                del visitors[key]

    def owner(request: Request) -> Visitor:
        prune()
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "visitor_required")
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        visitor = visitors.get(digest)
        if visitor is None:
            raise HTTPException(401, "visitor_expired_or_unknown")
        return visitor

    @app.get("/api/replay/fixtures")
    async def fixtures():
        return {
            "fixtures": [{"id": key, "title": title, **LABELS} for key, title in CATALOGUE.items()],
            "execution_available": runner is not None,
            **LABELS,
        }

    @app.post("/api/replay/visitors", status_code=201)
    async def new_visitor(request: Request):
        if await request.body():
            raise HTTPException(422, "visitor_body_not_allowed")
        async with lock:
            prune()
            if stopping:
                raise HTTPException(503, "service_stopping")
            if len(visitors) >= limits.max_visitors:
                raise HTTPException(429, "visitor_capacity")
            token = secrets.token_urlsafe(32)
            visitors[hashlib.sha256(token.encode()).hexdigest()] = Visitor(
                clock() + limits.visitor_ttl_seconds
            )
        return {"visitor_token": token, "expires_in_seconds": limits.visitor_ttl_seconds}

    def owned_run(run_id: str, request: Request) -> Run:
        visitor = owner(request)
        run = next((run for run in visitor.runs.values() if run.id == run_id), None)
        if run is None:
            raise HTTPException(404, "run_not_found")
        return run

    @app.get("/api/replay/runs/{run_id}")
    async def get_run(run_id: str, request: Request):
        return owned_run(run_id, request).public()

    @app.get("/api/replay/runs/{run_id}/result")
    async def get_result(run_id: str, request: Request):
        run = owned_run(run_id, request)
        if run.state == "running":
            return JSONResponse({"detail": "result_pending"}, status_code=202)
        if run.state == "failed":
            raise HTTPException(409, "run_failed")
        if run.result_json is None:
            raise HTTPException(404, "result_unavailable")
        return Response(content=run.result_json, media_type="application/json")

    @app.post("/api/replay/runs")
    async def start(body: StartRequest, request: Request):
        async with lock:
            visitor = owner(request)
            if stopping:
                raise HTTPException(503, "service_stopping")
            previous = visitor.runs.get(body.idempotency_key)
            if previous:
                if previous.fixture_id != body.fixture_id:
                    raise HTTPException(409, "idempotency_conflict")
                return JSONResponse(
                    previous.public(),
                    status_code={"running": 202, "completed": 200, "failed": 503}[previous.state],
                )
            if runner is None:
                raise HTTPException(503, "isolated_replay_runner_unavailable")
            if len(visitor.runs) >= limits.max_runs_per_visitor:
                raise HTTPException(429, "visitor_run_limit")
            if len(tasks) >= limits.max_concurrent_runs:
                raise HTTPException(429, "run_capacity")
            fixture_path = fixture_root / f"{body.fixture_id}.json"
            if not fixture_path.is_file() or fixture_path.is_symlink():
                raise HTTPException(503, "curated_fixture_unavailable")
            run = Run(secrets.token_urlsafe(24), body.fixture_id)
            visitor.runs[body.idempotency_key] = run
            response = JSONResponse(run.public(), status_code=202)
            task = asyncio.create_task(execute_run(run, visitor, fixture_path))
            tasks.add(task)

            def finished(done):
                tasks.discard(done)
                if done.cancelled():
                    run.state, run.error = "failed", "run_cancelled"
                elif done.exception() is not None:
                    run.state, run.error = "failed", "runner_failed"
                if run.state == "failed":
                    run.result_json = None

            task.add_done_callback(finished)
            return response

    async def execute_run(run: Run, visitor: Visitor, fixture_path: Path):
        root = state_root / run.id
        created = False
        try:
            root.mkdir(parents=True, exist_ok=False)
            created = True
            home, workspace = root / "pex-home", root / "workspace"
            home.mkdir()
            workspace.mkdir()
            timeout = min(limits.run_timeout_seconds, visitor.expires_at - clock())
            async with asyncio.timeout(max(0, timeout)):
                outcome = await runner.execute(RunContext(run.id, fixture_path, home, workspace))
            if isinstance(outcome, ReplayJobResult):
                # Revalidate from plain fields even if a model was mutated or
                # constructed without validation. Never retain arbitrary runner JSON.
                fields = outcome.model_dump(warnings=False)
                if fields.get("replay") is not True or fields.get("not_live_control") is not True:
                    raise ValueError("runner result requires explicit replay labels")
                validated = ReplayJobResult.model_validate(fields)
                if validated.fixture_id != run.fixture_id:
                    raise ValueError("runner result fixture mismatch")
                run.result_json = encode_result(validated)
            elif outcome != "completed":
                raise ValueError("invalid runner outcome")
            run.state = "completed"
        except TimeoutError:
            run.state, run.error = "failed", "run_timeout"
        except asyncio.CancelledError:
            run.state, run.error = "failed", "run_cancelled"
            raise
        except Exception:
            run.state, run.error = "failed", "runner_failed"
        finally:
            # No receipts, store, or workspace are retained by this contract.
            if created and root.exists():
                shutil.rmtree(root)

    return app
