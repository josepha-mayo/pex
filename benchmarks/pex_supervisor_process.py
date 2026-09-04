"""Out-of-process PEX decision worker for public benchmark observations.

This process receives only the public task, normalized worker events, and a
bounded public-workspace observation. It never imports the hidden evaluator or
benchmark controller.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pex_bridge.claims import extract_claims
from pex_bridge.scoring import score_trajectory
from pex_bridge.store import new_id
from pex_protocol.enums import EventPhase, EventType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest
from pex_supervisor.loop import decide
from pex_supervisor.providers import describe_backend, load_supervisor_model
from pex_supervisor.public_task import parse_public_task
from pex_supervisor.verify import verify_claims

MAX_CONTROL_BYTES = 512_000
MAX_TASK_CHARS = 20_000
MAX_MESSAGE_CHARS = 4_000
MAX_AGENT_MESSAGES = 20


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(constant: str) -> None:
    raise ValueError(f"non-finite JSON number {constant}")


def _bounded_payload(path: Path) -> dict:
    if _is_link_like(path) or not path.is_file():
        raise ValueError("request must be a regular control file")
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_CONTROL_BYTES + 1)
    except OSError as exc:
        raise ValueError("request is not valid bounded UTF-8 JSON") from exc
    if len(raw) > MAX_CONTROL_BYTES:
        raise ValueError("request exceeds control-file limit")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("request is not valid bounded UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("request is not an object")
    task = payload.get("public_task")
    messages = payload.get("agent_messages")
    if not isinstance(task, str) or not task.strip() or len(task) > MAX_TASK_CHARS:
        raise ValueError("public task is invalid")
    if (
        not isinstance(messages, list)
        or len(messages) > MAX_AGENT_MESSAGES
        or any(not isinstance(item, str) or len(item) > MAX_MESSAGE_CHARS for item in messages)
    ):
        raise ValueError("agent messages are invalid")
    last_message = payload.get("last_message")
    if not isinstance(last_message, str) or len(last_message) > MAX_MESSAGE_CHARS:
        raise ValueError("last message is invalid")
    for key, limit in (("goal_id", 256), ("project_id", 4_096)):
        value = payload.get(key)
        if not isinstance(value, str) or not value or len(value) > limit:
            raise ValueError(f"{key} is invalid")
    if not isinstance(payload.get("session"), dict):
        raise ValueError("session is invalid")
    if not isinstance(payload.get("public_observation"), dict):
        raise ValueError("public observation is invalid")
    return payload


def _public_pytest_argv(workspace: Path, tests: list[str]) -> list[str]:
    """Return the exact controller argv used for the bounded public pytest run."""
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=line",
        "-p",
        "no:cacheprovider",
        "--confcutdir",
        str(workspace.resolve()),
        "-o",
        "testpaths=",
        "-o",
        "addopts=",
        *tests,
    ]


def _public_pytest_command(workspace: Path, tests: list[str]) -> str:
    """Render the executed argv in an equivalent, safely classifiable form."""
    return subprocess.list2cmdline(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=line",
            "-p",
            "no:cacheprovider",
            f"--confcutdir={workspace.resolve()}",
            "-o=testpaths=",
            "-o=addopts=",
            *tests,
        ]
    )


def _controller_verification(
    observation: dict, workspace: Path
) -> dict | None:
    """Accept only controller-labelled pytest evidence bound to this snapshot."""
    raw = observation.get("controller_verification")
    if raw is None:
        return None
    integrity = observation.get("public_test_integrity")
    pytest_result = observation.get("pytest")
    provenance = raw.get("provenance") if isinstance(raw, dict) else None
    tests = [
        name
        for name in observation.get("files") or []
        if isinstance(name, str)
        and Path(name).name.startswith("test_")
        and name.endswith(".py")
    ]
    expected_command = _public_pytest_command(workspace, tests) if tests else None
    if (
        not isinstance(raw, dict)
        or raw.get("owner") != "benchmark_controller"
        or raw.get("kind") != "pytest"
        or raw.get("invocation_scope") != "targeted"
        or raw.get("relative_targets") != tests
        or raw.get("command") != expected_command
        or raw.get("result") != pytest_result
        or not isinstance(pytest_result, dict)
        or type(pytest_result.get("ok")) is not bool
        or type(pytest_result.get("exit_code")) is not int
        or not isinstance(pytest_result.get("output"), str)
        or not isinstance(integrity, dict)
        or integrity.get("intact") is not True
        or integrity.get("expected_sha256") != integrity.get("observed_sha256")
        or not isinstance(provenance, dict)
        or provenance.get("public_workspace_sha256")
        != observation.get("public_workspace_sha256")
        or provenance.get("public_test_sha256") != integrity.get("expected_sha256")
        or provenance.get("workspace_stable_during_verification") is not True
        or provenance.get("executed_argv") != _public_pytest_argv(workspace, tests)
    ):
        raise ValueError("controller pytest verification is not bound to this observation")
    return {
        "command": str(raw["command"]),
        "invocation_scope": "targeted",
        "relative_targets": list(tests),
        "result": dict(pytest_result),
        "provenance": dict(provenance),
    }


def decide_public_observation(payload: dict) -> dict:
    now = datetime.now(UTC)
    task_md = str(payload["public_task"]).strip()
    session = HarnessSession.model_validate(payload["session"])
    project_id = str(payload["project_id"])
    try:
        expected_path = Path(project_id)
        session_project_path = Path(str(session.project_id or ""))
        session_cwd_path = Path(str(session.cwd or ""))
        if not all(
            path.is_absolute()
            for path in (expected_path, session_project_path, session_cwd_path)
        ):
            raise ValueError("relative workspace identity")
        expected_workspace = expected_path.resolve()
        session_project = session_project_path.resolve()
        session_cwd = session_cwd_path.resolve()
    except (OSError, ValueError) as exc:
        raise ValueError("session workspace identity is invalid") from exc
    if session_project != expected_workspace or session_cwd != expected_workspace:
        raise ValueError("session workspace identity does not match the public project")
    session.status = SessionStatus.STOPPED
    parsed = parse_public_task(task_md)
    goal = Goal(
        id=str(payload["goal_id"]),
        project_id=project_id,
        title=str(parsed["title"] or "Task"),
        objective=str(parsed["objective"] or task_md),
        acceptance_criteria=list(parsed["acceptance_criteria"]),
        constraints=list(parsed["constraints"]),
        non_goals=list(parsed["non_goals"]),
        evidence_requirements=list(parsed["evidence_requirements"]),
        created_at=now,
        updated_at=now,
    )
    session.goal_id = goal.id
    events = [
        HarnessEvent(
            event_id=new_id("evt_"),
            ts=now,
            harness_type=session.harness_type,
            session_id=session.id,
            project_id=project_id,
            goal_id=goal.id,
            event_type=EventType.AGENT_RESPONSE,
            phase=EventPhase.DURING,
            message_delta=str(text)[:4000],
        )
        for text in payload.get("agent_messages") or []
    ]
    observation = payload.get("public_observation")
    if not isinstance(observation, dict):
        observation = {}
    integrity = observation.get("public_test_integrity")
    controller_verification = _controller_verification(observation, expected_workspace)
    pytest_state = (
        dict(controller_verification["result"])
        if controller_verification is not None
        else None
    )
    workspace_state = {
        "workspace_files": list(observation.get("files") or []),
        "file_manifest": list(observation.get("file_manifest") or []),
        "public_workspace_sha256": observation.get("public_workspace_sha256"),
        "public_test_integrity": integrity if isinstance(integrity, dict) else None,
    }
    if controller_verification is not None:
        verification_state = {
            "pytest": pytest_state,
            "owner": "benchmark_controller",
            "kind": "pytest",
            "invocation_scope": controller_verification["invocation_scope"],
            "relative_targets": controller_verification["relative_targets"],
            "provenance": controller_verification["provenance"],
        }
        events.append(
            HarnessEvent(
                event_id=new_id("evt_"),
                ts=now,
                harness_type=session.harness_type,
                session_id=session.id,
                project_id=project_id,
                goal_id=goal.id,
                event_type=EventType.TOOL_RESULT,
                phase=EventPhase.AFTER,
                tool_name="controller_public_pytest",
                command=controller_verification["command"],
                process_state=verification_state,
                metadata={
                    "owner": "benchmark_controller",
                    "kind": "pytest",
                    "invocation_scope": controller_verification["invocation_scope"],
                    "provenance": controller_verification["provenance"],
                },
            )
        )
    else:
        verification_state = None
    stop = HarnessEvent(
        event_id=new_id("evt_"),
        ts=now,
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=project_id,
        goal_id=goal.id,
        event_type=EventType.STOP,
        phase=EventPhase.TERMINAL,
        message_delta=str(payload.get("last_message") or "stopped")[:4000],
        process_state=workspace_state,
    )
    events.append(stop)
    scores = score_trajectory(events, goal)
    claims = extract_claims(events)
    workspace = {
        "workspace": str(expected_workspace),
        "files": list(observation.get("files") or []),
        "file_manifest": list(observation.get("file_manifest") or []),
        "pytest": pytest_state,
    }
    verification = verify_claims(claims, events, goal, workspace)
    verification["evidence_gathering"] = {
        "performed": True,
        "sources": [
            "agent_messages",
            "public_observation",
            *(["controller_public_pytest"] if controller_verification else []),
        ],
        "workspace_snapshot": "public_observation",
        "claim_count": len(claims),
    }
    scores.features["claims"] = claims
    scores.features["verification"] = verification
    if verification.get("status") == "contradicted":
        scores.claim_contradiction = max(scores.claim_contradiction, 0.88)
    # The generic supervisor prompt consumes prefetched_evidence. Supplying the
    # allowlisted observation here makes the visible pytest result and exact
    # public-workspace state available to semantic inference without granting
    # the child access to benchmark internals.
    scores.features["prefetched_evidence"] = {
        **workspace_state,
        "controller_verification": verification_state,
    }
    request = SupervisorRequest(
        session=session,
        goal=goal,
        event=stop,
        recent_events=events,
        scores=scores,
        notes="",
    )
    model = load_supervisor_model()
    result = decide(request, model=model)
    return {
        "backend": describe_backend(),
        "action": result.action.model_dump(mode="json"),
        "diagnosis": result.diagnosis,
        "used_llm": result.used_llm,
        "model_name": result.model_name,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_ms": result.latency_ms,
        "inference_request_id": result.inference_request_id,
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: pex_supervisor_process.py REQUEST.json RESPONSE.json")
    request_path = Path(sys.argv[1])
    response_path = Path(sys.argv[2])
    if not request_path.is_absolute() or not response_path.is_absolute():
        raise ValueError("supervisor control paths must be absolute")
    if response_path.exists() or _is_link_like(response_path):
        raise ValueError("supervisor response path must be fresh")
    payload = _bounded_payload(request_path)
    response = decide_public_observation(payload)
    encoded = json.dumps(
        response,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_CONTROL_BYTES:
        raise ValueError("response exceeds control-file limit")
    with response_path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


if __name__ == "__main__":
    main()
