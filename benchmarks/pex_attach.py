"""Attach the real PEX supervisor to an isolated worker after it has begun.

This module must not import the hidden evaluator. It must not receive stressor
labels or oracle facts. The only extra the treatment arm gets is this loop.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from tempfile import TemporaryDirectory
from typing import Any

from pex_bridge.observe import HIDDEN_NAME_MARKERS, snapshot
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.session import HarnessSession

PROCESS = Path(__file__).with_name("pex_supervisor_process.py")
_PUBLIC_OBSERVATION_FIELDS = {
    "files",
    "file_manifest",
    "public_workspace_sha256",
    "public_test_integrity",
    "pytest",
    "controller_verification",
}
_MAX_CONTROL_BYTES = 512_000
_MAX_TASK_CHARS = 20_000
_MAX_MESSAGE_CHARS = 4_000
_MAX_AGENT_MESSAGES = 20
_MAX_BACKEND_BYTES = 32_768
_MAX_PUBLIC_TEST_BYTES = 1024 * 1024
_PYTEST_BOOTSTRAP_FILES = {
    "conftest.py",
    "pytest.ini",
    "pyproject.toml",
    "setup.cfg",
    "sitecustomize.py",
    "tox.ini",
    "usercustomize.py",
}
_PUBLIC_ACTIONS = {
    InterventionType.NOOP,
    InterventionType.SEND_NUDGE,
    InterventionType.CONTINUE_SESSION,
    InterventionType.REQUEST_VERIFICATION,
}
_PRIVATE_TEXT_MARKERS = (
    *HIDDEN_NAME_MARKERS,
    "".join(("pex", "bench_")),
    "handoff fact:",
    "schema.json is the source of truth",
    "do not stop until pytest passes",
)


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _raise_walk_error(error: OSError) -> None:
    raise error


def _assert_unlinked_workspace(workspace: Path) -> None:
    """Prevent public observation from traversing a worker-created link or junction."""
    if not workspace.is_absolute() or _is_link_like(workspace) or not workspace.is_dir():
        raise RuntimeError("supervisor workspace must be an absolute regular directory")
    entries = 0

    for directory, names, filenames in os.walk(
        workspace,
        topdown=True,
        onerror=_raise_walk_error,
        followlinks=False,
    ):
        base = Path(directory)
        entries += len(names) + len(filenames)
        if entries > 20_000:
            raise RuntimeError("supervisor workspace exceeds the link-audit entry bound")
        for name in (*names, *filenames):
            if _is_link_like(base / name):
                raise RuntimeError("refusing a linked path in the supervised workspace")


def _assert_public_text(value: str, label: str) -> None:
    lowered = value.replace("\\", "/").casefold()
    for marker in _PRIVATE_TEXT_MARKERS:
        if marker.casefold() in lowered:
            raise RuntimeError(f"refusing private benchmark marker in supervisor {label}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(constant: str) -> None:
    raise ValueError(f"non-finite JSON number {constant}")


def _public_session(session: HarnessSession, workspace: Path) -> dict[str, Any]:
    if not workspace.is_absolute():
        raise RuntimeError("supervisor workspace identity must be absolute")
    expected = workspace.resolve()
    try:
        cwd_path = Path(str(session.cwd or ""))
        project_path = Path(str(session.project_id or ""))
        if not cwd_path.is_absolute() or not project_path.is_absolute():
            raise ValueError("relative session workspace")
        cwd = cwd_path.resolve()
        project = project_path.resolve()
    except (OSError, ValueError) as exc:
        raise RuntimeError("supervisor session has invalid workspace identity") from exc
    if cwd != expected or project != expected:
        raise RuntimeError("supervisor session does not match the isolated workspace")
    # Session metadata can contain adapter/controller labels. The public child
    # needs identity and capability-neutral state only, never benchmark labels.
    return {
        "id": session.id,
        "harness_type": session.harness_type.value,
        "vendor_session_id": session.vendor_session_id,
        "project_id": str(expected),
        "cwd": str(expected),
        "model": session.model,
        "reasoning_effort": session.reasoning_effort,
        "status": session.status.value,
        "context_health": session.context_health,
        "supervision_paused": session.supervision_paused,
    }


def _public_observation(observed: dict[str, Any]) -> dict[str, Any]:
    """Allowlist normal workspace evidence sent across the process boundary."""
    public = {key: observed.get(key) for key in _PUBLIC_OBSERVATION_FIELDS}
    try:
        encoded = json.dumps(public, sort_keys=True, allow_nan=False).lower()
    except (TypeError, ValueError) as exc:
        raise RuntimeError("refusing non-finite public benchmark observation") from exc
    if len(encoded.encode()) > 250_000:
        raise RuntimeError("refusing oversized public benchmark observation")
    for marker in HIDDEN_NAME_MARKERS:
        if marker.lower() in encoded:
            raise RuntimeError(f"refusing hidden benchmark marker in public observation: {marker}")
    files = public.get("files")
    manifest = public.get("file_manifest")
    digest = str(public.get("public_workspace_sha256") or "")
    if (
        not isinstance(files, list)
        or not isinstance(manifest, list)
        or len(files) != len(manifest)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise RuntimeError("refusing malformed public workspace evidence")
    for name, row in zip(files, manifest, strict=True):
        if (
            not isinstance(name, str)
            or not isinstance(row, dict)
            or row.get("path") != name
            or PurePosixPath(name).is_absolute()
            or PureWindowsPath(name).is_absolute()
            or "\\" in name
            or ".." in PurePosixPath(name).parts
            or type(row.get("size_bytes")) is not int
            or int(row["size_bytes"]) < 0
            or len(str(row.get("sha256") or "")) != 64
            or any(
                character not in "0123456789abcdef"
                for character in str(row.get("sha256") or "")
            )
        ):
            raise RuntimeError("refusing malformed public file manifest")
    canonical_manifest = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(canonical_manifest.encode()).hexdigest() != digest:
        raise RuntimeError("refusing inconsistent public workspace fingerprint")
    pytest_evidence = public.get("pytest")
    if pytest_evidence is not None and (
        not isinstance(pytest_evidence, dict)
        or type(pytest_evidence.get("ok")) is not bool
        or type(pytest_evidence.get("exit_code")) is not int
        or not isinstance(pytest_evidence.get("output"), str)
    ):
        raise RuntimeError("refusing malformed public pytest evidence")
    integrity = public.get("public_test_integrity")
    if integrity is not None and (
        not isinstance(integrity, dict)
        or integrity.get("path") != "test_public.py"
        or type(integrity.get("intact")) is not bool
        or len(str(integrity.get("expected_sha256") or "")) != 64
        or len(str(integrity.get("observed_sha256") or "")) != 64
        or any(
            character not in "0123456789abcdef"
            for key in ("expected_sha256", "observed_sha256")
            for character in str(integrity.get(key) or "")
        )
    ):
        raise RuntimeError("refusing malformed public test integrity evidence")
    controller_verification = public.get("controller_verification")
    if controller_verification is not None:
        expected_targets = [
            name
            for name in files
            if Path(name).name.startswith("test_") and name.endswith(".py")
        ]
        provenance = (
            controller_verification.get("provenance")
            if isinstance(controller_verification, dict)
            else None
        )
        if (
            not isinstance(controller_verification, dict)
            or controller_verification.get("owner") != "benchmark_controller"
            or controller_verification.get("kind") != "pytest"
            or controller_verification.get("invocation_scope") != "targeted"
            or controller_verification.get("relative_targets") != expected_targets
            or not isinstance(controller_verification.get("command"), str)
            or not str(controller_verification.get("command") or "").strip()
            or len(str(controller_verification.get("command") or "")) > 16_384
            or controller_verification.get("result") != pytest_evidence
            or not isinstance(integrity, dict)
            or integrity.get("intact") is not True
            or not isinstance(provenance, dict)
            or provenance.get("public_workspace_sha256") != digest
            or provenance.get("public_test_sha256") != integrity.get("expected_sha256")
            or provenance.get("public_test_sha256") != integrity.get("observed_sha256")
            or provenance.get("workspace_stable_during_verification") is not True
        ):
            raise RuntimeError("refusing unbound controller pytest verification")
    return public


def _validate_decision(raw: Any, *, session_id: str, goal_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RuntimeError("supervisor response is not an object")
    action = ProposedAction.model_validate(raw.get("action"))
    if action.type not in _PUBLIC_ACTIONS:
        raise RuntimeError("supervisor proposed a non-public benchmark action")
    if action.session_id != session_id or action.goal_id not in {None, goal_id}:
        raise RuntimeError("supervisor action identity does not match its request")
    if len(action.rationale) > _MAX_MESSAGE_CHARS:
        raise RuntimeError("supervisor rationale exceeds the control limit")
    if len(action.evidence) > 32 or any(len(item) > 512 for item in action.evidence):
        raise RuntimeError("supervisor evidence exceeds the control limit")
    if set(action.payload) - {"text"}:
        raise RuntimeError("supervisor action contains an unsupported public payload")
    text = action.payload.get("text")
    if text is not None and (not isinstance(text, str) or len(text) > _MAX_MESSAGE_CHARS):
        raise RuntimeError("supervisor intervention text exceeds the control limit")
    if isinstance(text, str):
        _assert_public_text(text, "intervention")
    backend = raw.get("backend")
    if not isinstance(backend, dict):
        backend = {}
    if len(json.dumps(backend, sort_keys=True, default=str).encode("utf-8")) > _MAX_BACKEND_BYTES:
        raise RuntimeError("supervisor backend description exceeds the control limit")
    _assert_public_text(
        json.dumps(backend, sort_keys=True, default=str),
        "backend description",
    )
    diagnosis = raw.get("diagnosis")
    if not isinstance(diagnosis, str) or len(diagnosis) > _MAX_MESSAGE_CHARS:
        raise RuntimeError("supervisor diagnosis exceeds the control limit")
    _assert_public_text(action.rationale, "rationale")
    _assert_public_text(diagnosis, "diagnosis")
    for item in action.evidence:
        _assert_public_text(item, "evidence")
    sanitized: dict[str, Any] = {
        "backend": backend,
        "action": action.model_dump(mode="json"),
        "diagnosis": diagnosis,
        "used_llm": raw.get("used_llm") is True,
    }
    for key in ("model_name", "inference_request_id"):
        value = raw.get(key)
        sanitized[key] = value if isinstance(value, str) and len(value) <= 256 else None
        if sanitized[key] is not None:
            _assert_public_text(str(sanitized[key]), key)
    for key in ("input_tokens", "output_tokens", "latency_ms"):
        value = raw.get(key)
        sanitized[key] = value if type(value) is int and 0 <= value <= 10**12 else 0
    return sanitized


def _bind_public_test_integrity(
    observed: dict[str, Any], expected_sha256: str | None
) -> dict[str, Any]:
    if not expected_sha256:
        observed["public_test_integrity"] = None
        return observed
    current = next(
        (
            str(row.get("sha256") or "")
            for row in observed.get("file_manifest") or []
            if isinstance(row, dict) and row.get("path") == "test_public.py"
        ),
        "0" * 64,
    )
    observed["public_test_integrity"] = {
        "path": "test_public.py",
        "expected_sha256": expected_sha256,
        "observed_sha256": current,
        "intact": current == expected_sha256,
    }
    return observed


def _public_pytest_argv(workspace: Path, tests: list[str]) -> list[str]:
    """Return the exact argv used by pex_bridge.observe for public pytest."""
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


def _bind_controller_verification(
    observed: dict[str, Any],
    *,
    before: dict[str, Any] | None,
    workspace: Path,
) -> dict[str, Any]:
    """Bind a controller-run result to one unchanged public workspace snapshot."""
    observed["controller_verification"] = None
    integrity = observed.get("public_test_integrity")
    pytest_result = observed.get("pytest")
    if (
        not isinstance(before, dict)
        or not isinstance(integrity, dict)
        or integrity.get("intact") is not True
        or not isinstance(pytest_result, dict)
        or before.get("public_workspace_sha256")
        != observed.get("public_workspace_sha256")
    ):
        return observed
    tests = [
        name
        for name in before.get("files") or []
        if isinstance(name, str)
        and Path(name).name.startswith("test_")
        and name.endswith(".py")
    ]
    if not tests:
        return observed
    observed["controller_verification"] = {
        "owner": "benchmark_controller",
        "kind": "pytest",
        "command": _public_pytest_command(workspace, tests),
        "invocation_scope": "targeted",
        "relative_targets": tests,
        "result": dict(pytest_result),
        "provenance": {
            "public_workspace_sha256": observed.get("public_workspace_sha256"),
            "public_test_sha256": integrity.get("expected_sha256"),
            "workspace_stable_during_verification": True,
            "executed_argv": _public_pytest_argv(workspace, tests),
        },
    }
    return observed


def _public_test_execution_allowed(expected_sha256: str | None) -> bool:
    """Run repository tests only when the controller binds the seeded test exactly."""
    if expected_sha256 is None:
        return False
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValueError("public_test_sha256 must be an exact lowercase SHA-256")
    return True


def _seeded_public_test_is_intact(workspace: Path, expected_sha256: str) -> bool:
    """Verify the controller-seeded public test before allowing it to execute."""
    public_test = workspace / "test_public.py"
    try:
        if (
            _is_link_like(public_test)
            or not public_test.is_file()
            or public_test.stat().st_size > _MAX_PUBLIC_TEST_BYTES
        ):
            return False
        digest = hashlib.sha256()
        size = 0
        chunks: list[bytes] = []
        with public_test.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                size += len(chunk)
                if size > _MAX_PUBLIC_TEST_BYTES:
                    return False
                digest.update(chunk)
                chunks.append(chunk)
        if digest.hexdigest() != expected_sha256:
            return False
        tree = ast.parse(b"".join(chunks).decode("utf-8"), filename="test_public.py")
        allowed_test_files = {Path("test_public.py")}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                parts = node.args[0].value.split(".")
                if parts and all(part.isidentifier() for part in parts):
                    allowed_test_files.add(Path(*parts).with_suffix(".py"))
        for directory, _, filenames in os.walk(
            workspace,
            onerror=_raise_walk_error,
            followlinks=False,
        ):
            base = Path(directory)
            for filename in filenames:
                relative = (base / filename).relative_to(workspace)
                if filename.casefold() in _PYTEST_BOOTSTRAP_FILES or (
                    filename.startswith("test_")
                    and filename.endswith(".py")
                    and relative not in allowed_test_files
                ):
                    return False
        return True
    except (OSError, UnicodeError, SyntaxError):
        return False


def _observe_controlled_workspace(
    workspace: Path,
    expected_sha256: str | None,
) -> dict[str, Any]:
    """Observe safely; execute only the exact controller-seeded fixture test."""
    _assert_unlinked_workspace(workspace)
    hash_is_authorized = _public_test_execution_allowed(expected_sha256)
    run_public_tests = bool(
        hash_is_authorized
        and expected_sha256
        and _seeded_public_test_is_intact(workspace, expected_sha256)
    )
    before = snapshot(workspace, run_pytest=False) if run_public_tests else None
    observed = _bind_public_test_integrity(
        snapshot(workspace, run_pytest=run_public_tests), expected_sha256
    )
    return _bind_controller_verification(observed, before=before, workspace=workspace)


async def supervise_isolated_codex(
    adapter: Any,
    session: HarnessSession,
    workspace: Path,
    task_md: str,
    *,
    store_path: Path,
    max_followups: int = 2,
    turn_timeout: float = 600,
    decision_timeout: float = 180,
    public_test_sha256: str | None = None,
) -> dict[str, Any]:
    """Observe a completed/stopped worker turn, reason, maybe intervene, observe again."""
    if type(max_followups) is not int or not 0 <= max_followups <= 10:
        raise ValueError("max_followups is outside the public benchmark bound")
    if (
        isinstance(turn_timeout, bool)
        or isinstance(decision_timeout, bool)
        or not isinstance(turn_timeout, (int, float))
        or not isinstance(decision_timeout, (int, float))
        or not math.isfinite(float(turn_timeout))
        or not math.isfinite(float(decision_timeout))
        or not 0 < turn_timeout <= 86_400
        or not 0 < decision_timeout <= turn_timeout
    ):
        raise ValueError("supervision timeouts must be finite and within the task budget")
    supervision_started = time.perf_counter()
    worker_followup_wall_seconds = 0.0
    deadline = time.perf_counter() + turn_timeout

    def remaining_budget() -> float:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise TimeoutError("PEX exhausted the shared worker-plus-supervisor task budget")
        return remaining

    audits: list[dict[str, Any]] = []
    outgoing_messages: list[str] = []
    followups = 0
    remaining_budget()
    observed = _observe_controlled_workspace(workspace, public_test_sha256)
    backend: dict[str, Any] = {}
    goal_id = f"public-{session.id}"

    while True:
        started = time.perf_counter()
        decision = await _decide_out_of_process(
            task_md=task_md,
            workspace=workspace,
            session=session,
            observed=observed,
            agent_messages=adapter.isolated_agent_messages,
            goal_id=goal_id,
            control_dir=store_path.parent,
            timeout=min(remaining_budget(), decision_timeout),
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        backend = decision.get("backend") or {}
        audit = _audit(decision, observed, task_md, elapsed)
        audits.append(audit)
        action = decision.get("action") or {}
        action_type = str(action.get("type") or InterventionType.NOOP.value)
        if action_type not in {
            InterventionType.SEND_NUDGE.value,
            InterventionType.CONTINUE_SESSION.value,
            InterventionType.REQUEST_VERIFICATION.value,
        }:
            break
        if followups >= max_followups:
            audit["policy_result"] = "deny"
            audit["result_afterward"] = {"delivery": "max_followups_reached"}
            break
        before_turn = getattr(adapter, "last_turn_id", None)
        sent, outcome, text = await _execute_public_intervention(adapter, session, action)
        audit["policy_result"] = "allow" if sent else "deny"
        audit["actual_action_sent"] = action_type if sent else None
        audit["result_afterward"] = {"delivery": outcome}
        if text:
            outgoing_messages.append(text)
        after_turn = getattr(adapter, "last_turn_id", None)
        if not sent or not after_turn or after_turn == before_turn:
            break
        worker_started = time.perf_counter()
        completed = await adapter.wait_for_turn_completion(
            session,
            after_turn,
            timeout=remaining_budget(),
        )
        if (
            not isinstance(completed, dict)
            or str(completed.get("status") or "").casefold() != "completed"
            or completed.get("error")
        ):
            raise RuntimeError("PEX follow-up turn did not reach a clean natural completion")
        worker_followup_wall_seconds += time.perf_counter() - worker_started
        followups += 1
        remaining_budget()
        next_observed = _observe_controlled_workspace(workspace, public_test_sha256)
        audit["result_afterward"] = _observed_outcome(
            outcome,
            before=observed,
            after=next_observed,
            followup_turn_id=str(after_turn),
        )
        observed = next_observed

    supervision_wall_seconds = time.perf_counter() - supervision_started
    return {
        "backend": backend,
        "used_llm": any(a.get("used_llm") for a in audits),
        "followups": followups,
        "audits": audits,
        "observed_files": observed["files"],
        "model": backend.get("model_id"),
        "outgoing_messages": outgoing_messages,
        "supervisor_process_isolated": True,
        "worker_followup_wall_seconds": round(worker_followup_wall_seconds, 6),
        "supervisor_wall_seconds": round(
            max(0.0, supervision_wall_seconds - worker_followup_wall_seconds), 6
        ),
    }


def _observed_outcome(
    delivery: str,
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    followup_turn_id: str,
) -> dict[str, Any]:
    before_pytest = before.get("pytest") if isinstance(before.get("pytest"), dict) else {}
    after_pytest = after.get("pytest") if isinstance(after.get("pytest"), dict) else {}
    result: dict[str, Any] = {
        "delivery": delivery,
        "followup_turn_id": followup_turn_id,
        "public_workspace_sha256": after.get("public_workspace_sha256"),
        "workspace_changed": before.get("public_workspace_sha256")
        != after.get("public_workspace_sha256"),
        "pytest_before": before_pytest.get("ok"),
        "pytest_after": after_pytest.get("ok"),
    }
    if before_pytest.get("ok") is not True and after_pytest.get("ok") is True:
        result["helped"] = True
    return result


def _audit(
    decision: dict[str, Any],
    observed: dict[str, Any],
    public_task: str,
    latency_ms: int,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "persistent_goal": public_task,
        "observable_evidence": {
            "files": observed.get("files"),
            "file_manifest": observed.get("file_manifest"),
            "public_workspace_sha256": observed.get("public_workspace_sha256"),
            "public_test_integrity": observed.get("public_test_integrity"),
            "pytest": observed.get("pytest"),
            "trigger": "stop",
            "evidence": (decision.get("action") or {}).get("evidence") or [],
        },
        "PEX_backend": decision.get("backend") or {},
        "inference_request_id": decision.get("inference_request_id"),
        "diagnosis": decision.get("diagnosis"),
        "proposed_action": decision.get("action"),
        "policy_result": None,
        "actual_action_sent": None,
        "result_afterward": None,
        "latency_ms": latency_ms,
        "used_llm": bool(decision.get("used_llm")),
        "model_name": decision.get("model_name"),
        "input_tokens": decision.get("input_tokens") or 0,
        "output_tokens": decision.get("output_tokens") or 0,
    }


async def _decide_out_of_process(
    *,
    task_md: str,
    workspace: Path,
    session: HarnessSession,
    observed: dict[str, Any],
    agent_messages: list[str],
    goal_id: str,
    control_dir: Path,
    timeout: float,
) -> dict[str, Any]:
    if len(task_md) > _MAX_TASK_CHARS:
        raise RuntimeError("public benchmark task exceeds the control limit")
    _assert_public_text(task_md, "public task")
    for message in agent_messages[-_MAX_AGENT_MESSAGES:]:
        if not isinstance(message, str) or len(message) > _MAX_MESSAGE_CHARS:
            raise RuntimeError("worker message exceeds the control limit")
        _assert_public_text(message, "worker message")
    if not control_dir.is_absolute() or (control_dir.exists() and _is_link_like(control_dir)):
        raise RuntimeError("supervisor control directory is not an absolute regular path")
    control_dir.mkdir(parents=True, exist_ok=True)
    if _is_link_like(control_dir):
        raise RuntimeError("supervisor control directory is linked")
    with TemporaryDirectory(prefix=".pex-supervisor-", dir=control_dir) as tmp:
        request_path = Path(tmp) / "request.json"
        response_path = Path(tmp) / "response.json"
        control_payload = {
            "public_task": task_md,
            "project_id": str(workspace.resolve()),
            "goal_id": goal_id,
            "session": _public_session(session, workspace),
            "public_observation": _public_observation(observed),
            "agent_messages": [
                str(message)[:_MAX_MESSAGE_CHARS]
                for message in agent_messages[-_MAX_AGENT_MESSAGES:]
            ],
            "last_message": (
                str(agent_messages[-1])[:_MAX_MESSAGE_CHARS]
                if agent_messages
                else "stopped"
            ),
        }
        encoded_request = json.dumps(
            control_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded_request) > _MAX_CONTROL_BYTES:
            raise RuntimeError("supervisor request exceeds the control-file limit")
        with request_path.open("xb") as handle:
            handle.write(encoded_request)
            handle.flush()
            os.fsync(handle.fileno())
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(PROCESS),
            str(request_path),
            str(response_path),
            cwd=workspace,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env={
                key: value
                for key, value in os.environ.items()
                if not any(
                    marker in key.upper()
                    for marker in (
                        "EVALUATOR",
                        "PEX_BENCH",
                        "PYTEST_CURRENT_TEST",
                        "STRESSOR",
                        "TASK_ID",
                        "PYTHONPATH",
                        "PYTHONHOME",
                    )
                )
            },
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError("PEX supervisor process timed out") from None
        if proc.returncode != 0 or _is_link_like(response_path) or not response_path.is_file():
            raise RuntimeError(f"PEX supervisor process failed with exit {proc.returncode}")
        with response_path.open("rb") as handle:
            raw_response = handle.read(_MAX_CONTROL_BYTES + 1)
        if len(raw_response) > _MAX_CONTROL_BYTES:
            raise RuntimeError("supervisor response exceeds the control-file limit")
        try:
            decoded = json.loads(
                raw_response.decode("utf-8"),
                parse_constant=_reject_json_constant,
                object_pairs_hook=_unique_json_object,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("supervisor response is not valid UTF-8 JSON") from exc
        return _validate_decision(decoded, session_id=session.id, goal_id=goal_id)


async def _execute_public_intervention(
    adapter: Any,
    session: HarnessSession,
    action: dict[str, Any],
) -> tuple[bool, str, str]:
    action_type = InterventionType(str(action.get("type") or InterventionType.NOOP.value))
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    text = str(payload.get("text") or "")
    if action_type == InterventionType.CONTINUE_SESSION:
        ok = await adapter.continue_or_resume(session, text or None)
        return ok, "continued" if ok else "continue_failed", text
    if action_type in {
        InterventionType.SEND_NUDGE,
        InterventionType.REQUEST_VERIFICATION,
    }:
        if not text:
            return False, "empty_intervention_refused", text
        ok = await adapter.send_message(session, text)
        return ok, "sent" if ok else "send_failed", text
    return False, f"action_not_allowed:{action_type.value}", text


def _cursor_conversation_id(payload: dict[str, Any]) -> str:
    return str(
        payload.get("conversation_id")
        or payload.get("session_id")
        or payload.get("composer_id")
        or ""
    ).strip()


def _load_isolated_meta(control_dir: Path) -> dict[str, Any]:
    path = control_dir / "pex_meta.json"
    if _is_link_like(path) or not path.is_file():
        return {
            "backend": {},
            "used_llm": False,
            "followups": 0,
            "audits": [],
            "outgoing_messages": [],
            "observed_files": [],
            "model": None,
            "supervisor_process_isolated": True,
            "worker_followup_wall_seconds": 0.0,
            "supervisor_wall_seconds": 0.0,
        }
    raw = path.read_bytes()
    if len(raw) > _MAX_CONTROL_BYTES:
        raise RuntimeError("isolated supervisor receipt exceeds the control-file limit")
    loaded = json.loads(
        raw.decode("utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_unique_json_object,
    )
    if not isinstance(loaded, dict) or loaded.get("supervisor_process_isolated") is not True:
        raise RuntimeError("isolated supervisor receipt is not a process-isolated PEX record")
    audits = loaded.get("audits")
    messages = loaded.get("outgoing_messages")
    if not isinstance(audits, list) or not isinstance(messages, list):
        raise RuntimeError("isolated supervisor receipt is malformed")
    return loaded


def _write_isolated_meta(control_dir: Path, meta: dict[str, Any]) -> None:
    path = control_dir / "pex_meta.json"
    encoded = json.dumps(
        meta,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        default=str,
    )
    if len(encoded.encode("utf-8")) > _MAX_CONTROL_BYTES:
        raise RuntimeError("isolated supervisor receipt exceeds the control-file limit")
    tmp = control_dir / f".pex_meta.{os.getpid()}.{time.time_ns()}.tmp"
    with tmp.open("x", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


async def decide_isolated_cursor_stop(
    control: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """One out-of-process STOP decision whose follow-up returns through this Cursor hook."""
    workspace = Path(str(control.get("workspace") or "")).expanduser()
    control_dir = Path(str(control.get("control_dir") or "")).expanduser()
    if not workspace.is_absolute() or not control_dir.is_absolute():
        raise RuntimeError("isolated Cursor supervisor paths must be absolute")
    workspace = workspace.resolve()
    control_dir = control_dir.resolve()
    if _is_link_like(workspace) or _is_link_like(control_dir):
        raise RuntimeError("isolated Cursor supervisor paths must not be linked")
    timeout = control.get("decision_timeout")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or not 0 < float(timeout) <= 86_400
    ):
        raise RuntimeError("isolated Cursor supervisor timeout is invalid")
    conversation_id = _cursor_conversation_id(payload)
    if not conversation_id or len(conversation_id) > 256:
        raise RuntimeError("isolated Cursor stop lacks a bounded conversation id")
    task_md = (workspace / "TASK.md").read_text(encoding="utf-8")
    public_test_sha256 = control.get("public_test_sha256")
    if public_test_sha256 is not None and (
        not isinstance(public_test_sha256, str)
        or (public_test_sha256 and len(public_test_sha256) != 64)
    ):
        raise RuntimeError("isolated Cursor public-test fingerprint is invalid")
    expected_sha256 = public_test_sha256 or None
    session = HarnessSession(
        id=f"cursor:{conversation_id}",
        harness_type=HarnessType.CURSOR,
        vendor_session_id=conversation_id,
        project_id=str(workspace),
        cwd=str(workspace),
        model=str(payload.get("model_id") or payload.get("model") or "")[:256] or None,
        status=SessionStatus.STOPPED,
    )
    completion = str(
        payload.get("completion")
        or payload.get("text")
        or payload.get("message")
        or payload.get("last_assistant_message")
        or "stopped"
    )[:_MAX_MESSAGE_CHARS]
    control_dir.mkdir(parents=True, exist_ok=True)
    if _is_link_like(control_dir):
        raise RuntimeError("isolated Cursor control directory is linked")
    meta = _load_isolated_meta(control_dir)
    observed = _observe_controlled_workspace(workspace, expected_sha256)
    started = time.perf_counter()
    decision = await _decide_out_of_process(
        task_md=task_md,
        workspace=workspace,
        session=session,
        observed=observed,
        agent_messages=[completion],
        goal_id=f"public-{session.id}",
        control_dir=control_dir,
        timeout=float(timeout),
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    audit = _audit(decision, observed, task_md, elapsed)
    action = decision.get("action") if isinstance(decision.get("action"), dict) else {}
    action_type = str(action.get("type") or InterventionType.NOOP.value)
    action_payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    text = str(action_payload.get("text") or "").strip()
    followup = ""
    if (
        action_type
        in {
            InterventionType.SEND_NUDGE.value,
            InterventionType.CONTINUE_SESSION.value,
            InterventionType.REQUEST_VERIFICATION.value,
        }
        and text
        and not text.startswith("PEX:")
    ):
        followup = text[:_MAX_MESSAGE_CHARS]
        audit["policy_result"] = "allow"
        audit["actual_action_sent"] = action_type
        audit["result_afterward"] = {"delivery": "hook_stdout"}
        meta["followups"] = int(meta.get("followups") or 0) + 1
        messages = list(meta.get("outgoing_messages") or [])
        messages.append(followup)
        meta["outgoing_messages"] = messages[-_MAX_AGENT_MESSAGES:]
    else:
        audit["policy_result"] = "deny" if text.startswith("PEX:") else "allow"
        audit["actual_action_sent"] = None
        audit["result_afterward"] = {"delivery": "noop" if not followup else "refused"}
    audits = list(meta.get("audits") or [])
    audits.append(audit)
    wall = float(meta.get("supervisor_wall_seconds") or 0.0) + max(0.0, elapsed / 1000.0)
    meta.update(
        {
            "backend": decision.get("backend") or {},
            "used_llm": bool(meta.get("used_llm")) or bool(decision.get("used_llm")),
            "audits": audits,
            "observed_files": observed.get("files") or [],
            "model": (decision.get("backend") or {}).get("model_id") or decision.get("model_name"),
            "supervisor_process_isolated": True,
            "supervisor_wall_seconds": round(wall, 6),
        }
    )
    _write_isolated_meta(control_dir, meta)
    hook_stdout = {"followup_message": followup} if followup else {}
    return {"hook_stdout": hook_stdout, "pex": meta}
