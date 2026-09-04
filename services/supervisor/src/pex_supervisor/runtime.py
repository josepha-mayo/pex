"""Strict AgentCore Runtime entrypoint for the PEX supervisor.

Set ``PEX_RUNTIME_SERVER=local_http`` for an explicit local contract smoke.
The deploy image defaults to the AgentCore SDK server and never silently
switches server implementations after an error.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from functools import lru_cache
from typing import Any

from pex_protocol.supervisor import SupervisorRequest
from pydantic import ValidationError
from starlette.requests import Request

from pex_supervisor.loop import decide
from pex_supervisor.providers import load_supervisor_model

PROTOCOL_VERSION = 1
MAX_RUNTIME_REQUEST_BYTES = 1_048_576
MAX_RUNTIME_RESPONSE_BYTES = 1_048_576
MAX_RUNTIME_BODY_CHUNKS = 4096
_UNSET = object()
_INVOCATION_ID = re.compile(r"^pexinv_[0-9a-f]{32}$")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _bounded_json_bytes(value: object, *, limit: int, label: str) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as exc:
        raise ValueError(f"AgentCore {label} must be finite JSON") from exc
    if len(encoded) > limit:
        raise ValueError(f"AgentCore {label} exceeds the runtime byte limit")
    return encoded


def _request_data(payload: object) -> tuple[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("AgentCore payload must be a JSON object")
    _bounded_json_bytes(
        payload,
        limit=MAX_RUNTIME_REQUEST_BYTES,
        label="payload",
    )
    body = payload.get("input") if isinstance(payload.get("input"), dict) else payload
    version = body.get("schema_version")
    if version != PROTOCOL_VERSION:
        raise ValueError("unsupported PEX AgentCore schema version")
    invocation_id = body.get("invocation_id")
    if not isinstance(invocation_id, str) or not _INVOCATION_ID.fullmatch(invocation_id):
        raise ValueError("invalid or missing PEX AgentCore invocation id")
    request_data = body.get("request")
    if not isinstance(request_data, dict):
        raise ValueError("AgentCore request must be a JSON object")
    return invocation_id, request_data


def _project_key(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/").casefold()


def _project_matches(observed: str | None, expected: str | None) -> bool:
    if observed is None:
        return True
    return bool(expected and _project_key(observed) == _project_key(expected))


def _validate_request_binding(request: SupervisorRequest) -> None:
    if request.event.session_id != request.session.id:
        raise ValueError("AgentCore event is bound to a different session")
    if request.event.harness_type != request.session.harness_type:
        raise ValueError("AgentCore event is bound to a different harness")
    if not _project_matches(request.event.project_id, request.session.project_id):
        raise ValueError("AgentCore event is bound to a different project")
    expected_goal = request.goal.id if request.goal else None
    if request.session.goal_id != expected_goal:
        raise ValueError("AgentCore request has inconsistent goal binding")
    if request.goal and not _project_matches(request.goal.project_id, request.session.project_id):
        raise ValueError("AgentCore request has inconsistent project binding")
    for event in request.recent_events:
        if event.session_id != request.session.id:
            raise ValueError("AgentCore recent event is bound to a different session")
        if event.harness_type != request.session.harness_type:
            raise ValueError("AgentCore recent event is bound to a different harness")
        if not _project_matches(event.project_id, request.session.project_id):
            raise ValueError("AgentCore recent event is bound to a different project")


def _validate_result_binding(request: SupervisorRequest, result: object) -> None:
    expected_goal = request.goal.id if request.goal else None
    action = getattr(result, "action", None)
    if getattr(action, "session_id", None) != request.session.id:
        raise ValueError("AgentCore result is bound to a different session")
    if getattr(action, "goal_id", None) != expected_goal:
        raise ValueError("AgentCore result is bound to a different goal")


@lru_cache(maxsize=1)
def _runtime_model() -> object:
    """Construct one explicitly configured model or fail runtime startup."""
    provider = (os.environ.get("PEX_SUPERVISOR_PROVIDER") or "").strip()
    model_id = (os.environ.get("PEX_SUPERVISOR_MODEL") or "").strip()
    if not provider or not model_id:
        raise RuntimeError(
            "AgentCore runtime requires explicit PEX_SUPERVISOR_PROVIDER and "
            "PEX_SUPERVISOR_MODEL values"
        )
    model = load_supervisor_model()
    if model is None:
        raise RuntimeError("configured AgentCore Strands model could not be constructed")
    return model


def handle_payload(
    payload: object,
    *,
    model: object = _UNSET,
    force_llm: bool | None = None,
) -> dict[str, Any]:
    invocation_id, request_data = _request_data(payload)
    try:
        request = SupervisorRequest.model_validate(request_data)
    except ValidationError as exc:
        # Pydantic's rendered exception can contain attacker-controlled input.
        # Keep the public runtime error fixed while retaining the exception chain.
        raise ValueError("AgentCore request failed protocol validation") from exc
    _validate_request_binding(request)
    configured_model = _runtime_model() if model is _UNSET else model
    result = decide(
        request,
        model=configured_model,
        force_llm=(os.environ.get("PEX_FORCE_LLM") == "1" if force_llm is None else force_llm),
    )
    _validate_result_binding(request, result)
    response = {
        "schema_version": PROTOCOL_VERSION,
        "invocation_id": invocation_id,
        "result": result.model_dump(mode="json"),
    }
    _bounded_json_bytes(
        response,
        limit=MAX_RUNTIME_RESPONSE_BYTES,
        label="response",
    )
    return response


def _agentcore_app(*, model: object = _UNSET):
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    configured_model = _runtime_model() if model is _UNSET else model
    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload: dict):
        return handle_payload(payload, model=configured_model)

    return app


def _fastapi_app(*, model: object = _UNSET):
    from fastapi import FastAPI, HTTPException

    # The explicit local HTTP mode is a deterministic contract smoke. It never
    # loads a billable model from ambient environment variables. Tests may inject
    # a model explicitly; the deployed AgentCore mode above remains strict.
    configured_model = None if model is _UNSET else model
    app = FastAPI(title="PEX Supervisor", version="0.1.0")

    @app.get("/ping")
    def ping():
        return {
            "status": "Healthy",
            "service": "pex-supervisor",
            "model_configured": configured_model is not None,
        }

    @app.post("/invocations")
    async def invocations(request: Request):
        try:
            content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type != "application/json":
                raise HTTPException(status_code=415, detail="application/json required")
            content_lengths = request.headers.getlist("content-length")
            declared_length: int | None = None
            if content_lengths:
                try:
                    parsed_lengths = [int(value) for value in content_lengths]
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail="invalid request") from exc
                if any(value < 0 for value in parsed_lengths) or len(set(parsed_lengths)) != 1:
                    raise HTTPException(status_code=400, detail="invalid request")
                declared_length = parsed_lengths[0]
                if declared_length > MAX_RUNTIME_REQUEST_BYTES:
                    raise HTTPException(status_code=413, detail="request too large")
            body = bytearray()
            chunk_count = 0
            async for chunk in request.stream():
                chunk_count += 1
                if chunk_count > MAX_RUNTIME_BODY_CHUNKS:
                    raise HTTPException(status_code=413, detail="request too fragmented")
                if len(body) + len(chunk) > MAX_RUNTIME_REQUEST_BYTES:
                    raise HTTPException(status_code=413, detail="request too large")
                body.extend(chunk)
            if declared_length is not None and len(body) != declared_length:
                raise HTTPException(status_code=400, detail="invalid request")
            try:
                payload = json.loads(
                    bytes(body),
                    parse_constant=_reject_json_constant,
                    object_pairs_hook=_unique_json_object,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="invalid JSON") from exc
            # ``handle_payload`` is the synchronous AgentCore entry point and
            # ultimately calls ``asyncio.run``.  FastAPI is already executing
            # this handler on an event loop, so run the synchronous contract in
            # a worker thread instead of crashing every real local invocation.
            return await asyncio.to_thread(
                handle_payload,
                payload,
                model=configured_model,
                force_llm=False,
            )
        except HTTPException:
            raise
        except (TypeError, ValueError) as exc:
            # Do not echo validation input, local paths, or model output.
            raise HTTPException(status_code=400, detail="invalid AgentCore invocation") from exc

    return app


def main() -> None:
    server = os.environ.get("PEX_RUNTIME_SERVER", "agentcore").strip().lower()
    if server == "agentcore":
        app = _agentcore_app()
        app.run()
        return
    if server == "local_http":
        import uvicorn

        uvicorn.run(
            _fastapi_app(),
            host=os.environ.get("PEX_RUNTIME_HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "8080")),
        )
        return
    raise ValueError("PEX_RUNTIME_SERVER must be agentcore or local_http")


if __name__ == "__main__":
    main()
