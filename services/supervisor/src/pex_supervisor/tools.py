from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

from pex_protocol.supervisor import SupervisorRequest

try:
    from strands import tool
except ImportError:  # pragma: no cover

    def tool(fn=None, **_kwargs):  # type: ignore[misc]
        if fn is None:
            return lambda f: f
        return fn


_RUNTIME: ContextVar[dict[str, Any]] = ContextVar("pex_supervisor_runtime")


def bind_request(request: SupervisorRequest) -> Any:
    return _RUNTIME.set({"request": request, "proposed": None})


def reset_request(token: Any) -> None:
    _RUNTIME.reset(token)


def current_request() -> SupervisorRequest:
    return _RUNTIME.get()["request"]


@tool
def get_goal() -> str:
    """Return the persistent goal attached to this session, or 'none'."""
    goal = current_request().goal
    return goal.model_dump_json() if goal else "none"


@tool
def get_session_state() -> str:
    """Return the current harness session record."""
    return current_request().session.model_dump_json()


@tool
def get_recent_events() -> str:
    """Return recent normalized events as JSON."""
    events = current_request().recent_events[-20:]
    return "[" + ",".join(e.model_dump_json() for e in events) + "]"


@tool
def get_scores() -> str:
    """Return deterministic drift/stagnation/premature-completion scores."""
    return current_request().scores.model_dump_json()


@tool
def get_context() -> str:
    """Return compact observed process state and last worker messages."""
    request = current_request()
    messages = [
        (e.message_delta or e.command or "")
        for e in request.recent_events[-8:]
        if e.message_delta or e.command
    ]
    return json.dumps(
        {
            "process_state": request.event.process_state,
            "recent": messages,
            "goal": request.goal.objective if request.goal else None,
        }
    )


@tool
def run_verification() -> str:
    """Inspect the worker workspace and visible tests. Does not read hidden evaluators."""
    from pex_supervisor.workspace import snapshot

    cwd = current_request().session.cwd
    if not cwd:
        return json.dumps({"error": "session has no cwd"})
    return json.dumps(snapshot(cwd))


@tool
def web_search(query: str, provider: str = "") -> str:
    """Search the public web to verify a worker claim.

    Uses BYOK Firecrawl/Exa/Tavily/Brave/Serper, else DuckDuckGo.
    """
    from pex_supervisor.search import web_search as _search

    return json.dumps(_search(query, provider=provider or None))


@tool
def scrape_url(url: str) -> str:
    """Scrape a URL the worker cited (Firecrawl /v2/scrape). Requires FIRECRAWL_API_KEY."""
    from pex_supervisor.search import scrape_url as _scrape

    return json.dumps(_scrape(url))


@tool
def propose_typed_action(
    action_type: str,
    rationale: str,
    evidence: str,
    message: str = "",
    payload_json: str = "",
    request_id: str = "",
    decision: str = "",
    overlay_id: str = "",
    confidence: float = 0.7,
    risk: str = "low",
) -> str:
    """Commit PEX's single typed intervention.

    action_type must be a valid InterventionType.
    """
    payload: dict[str, Any] = {"text": message} if message else {}
    payload_error = ""
    if payload_json:
        try:
            decoded = json.loads(payload_json)
            if not isinstance(decoded, dict):
                raise ValueError("payload_json must decode to an object")
            payload.update(decoded)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            payload_error = str(exc)
    if request_id:
        payload["request_id"] = request_id
    if decision:
        payload["decision"] = decision
    if overlay_id:
        payload["overlay_id"] = overlay_id
    _RUNTIME.get()["proposed"] = {
        "type": action_type,
        "rationale": rationale,
        "evidence": [item.strip() for item in evidence.split("|") if item.strip()],
        "payload": payload,
        "payload_error": payload_error,
        "confidence": confidence,
        "risk": risk,
    }
    return "recorded"


def take_proposed() -> dict[str, Any] | None:
    state = _RUNTIME.get()
    return state.get("proposed")


SUPERVISOR_TOOLS = [
    get_goal,
    get_session_state,
    get_recent_events,
    get_scores,
    get_context,
    run_verification,
    web_search,
    scrape_url,
    propose_typed_action,
]
