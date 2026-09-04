"""Strict, secret-free receipts for the live Codex closed-loop contract tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from pex_protocol.intervention import Intervention

PROOF_SCHEMA = "pex.codex.closed_loop.v3"
_MAX_SOURCE_FILES = 100_000
_HEX_REVISION = re.compile(r"[0-9a-f]{40,64}")
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}")
_RUN_ID = re.compile(
    r"codexproof_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_SAFE_AUTH_MODE = re.compile(r"[a-z][a-z0-9_.-]{0,63}")
_FORBIDDEN_SECRET_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "password",
    "refresh_token",
    "secret",
    "token_value",
}
_SECRET_ENV_MARKERS = (
    "API_KEY",
    "AUTHORIZATION",
    "CREDENTIAL",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _run_git(repo_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        timeout=30,
    )
    return completed.stdout


def capture_source_provenance(repo_root: Path) -> dict[str, Any]:
    """Fingerprint the exact Git revision and every non-ignored worktree file."""

    root = repo_root.resolve(strict=True)
    revision = _run_git(root, "rev-parse", "HEAD").decode("ascii").strip().casefold()
    if _HEX_REVISION.fullmatch(revision) is None:
        raise AssertionError("live proof source is not bound to a Git revision")
    status = _run_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    listed = _run_git(
        root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    )
    paths = sorted({part.decode("utf-8") for part in listed.split(b"\0") if part})
    if not paths or len(paths) > _MAX_SOURCE_FILES:
        raise AssertionError("live proof source file inventory is empty or unbounded")

    source = hashlib.sha256()
    source.update(f"revision:{revision}\0".encode())
    for relative in paths:
        if "\x00" in relative:
            raise AssertionError("live proof source path contains NUL")
        candidate = root / relative
        source.update(relative.replace("\\", "/").encode("utf-8"))
        source.update(b"\0")
        if candidate.is_symlink():
            source.update(b"symlink\0")
            source.update(os.readlink(candidate).encode("utf-8"))
        elif candidate.is_file():
            source.update(b"file\0")
            source.update(f"{candidate.stat().st_mode & 0o777:o}".encode("ascii"))
            source.update(b"\0")
            source.update(_sha256_file(candidate).encode("ascii"))
        elif candidate.exists():
            source.update(b"non-file\0")
        else:
            source.update(b"missing\0")
        source.update(b"\0")
    source_fingerprint = source.hexdigest()
    status_records = [part for part in status.split(b"\0") if part]
    return {
        "kind": "git_worktree",
        "repo_root": str(root),
        "revision": revision,
        "dirty": bool(status),
        "dirty_status_record_count": len(status_records),
        "dirty_fingerprint": _sha256_bytes(status + source_fingerprint.encode("ascii")),
        "source_file_count": len(paths),
        "source_fingerprint": source_fingerprint,
    }


def assert_source_unchanged(before: dict[str, Any], after: dict[str, Any]) -> None:
    if before != after:
        raise AssertionError("source or dirty worktree changed during the live proof")


def start_proof_receipt(
    *,
    proof_kind: str,
    source: dict[str, Any],
    sandbox: str,
) -> dict[str, Any]:
    if sandbox != "workspace-write":
        raise AssertionError("Codex closed-loop proof must use workspace-write")
    return {
        "schema": PROOF_SCHEMA,
        "proof_status": "running",
        "proof_kind": proof_kind,
        "run_id": f"codexproof_{uuid4()}",
        "started_at": utc_timestamp(),
        "sandbox": sandbox,
        "source": dict(source),
    }


def capture_process_provenance(transport: Any, binary: str) -> dict[str, Any]:
    """Bind the receipt to the exact live child and executable bytes."""

    executable = Path(binary).resolve(strict=True)
    command = [str(part) for part in getattr(transport, "command", [])]
    process = getattr(transport, "_proc", None)
    if (
        len(command) != 4
        or command[1:] != ["app-server", "--listen", "stdio://"]
        or Path(command[0]).resolve(strict=True) != executable
    ):
        raise AssertionError("Codex child command does not match the selected binary")
    if process is None or not isinstance(process.pid, int) or process.pid <= 0:
        raise AssertionError("Codex App Server child has no verified process id")
    if process.returncode is not None:
        raise AssertionError("Codex App Server child exited before proof capture")
    init_result = getattr(transport, "init_result", None)
    if getattr(transport, "initialized", False) is not True or not isinstance(init_result, dict):
        raise AssertionError("Codex App Server initialize receipt is missing")
    return {
        "captured_at": utc_timestamp(),
        "binary_path": str(executable),
        "binary_sha256": _sha256_file(executable),
        "binary_size": executable.stat().st_size,
        "process_id": process.pid,
        "process_running": True,
        "command": command,
        "command_fingerprint": _canonical_fingerprint(command),
        "initialized": True,
        "initialize_receipt": init_result,
        "initialize_receipt_fingerprint": _canonical_fingerprint(init_result),
    }


def assert_same_process(before: dict[str, Any], after: dict[str, Any]) -> None:
    stable_fields = {
        "binary_path",
        "binary_sha256",
        "binary_size",
        "process_id",
        "process_running",
        "command",
        "command_fingerprint",
        "initialized",
        "initialize_receipt",
        "initialize_receipt_fingerprint",
    }
    if {key: before.get(key) for key in stable_fields} != {
        key: after.get(key) for key in stable_fields
    }:
        raise AssertionError("Codex App Server process identity changed during the proof")


def supervisor_receipt(intervention: Intervention) -> dict[str, Any]:
    metadata = intervention.metadata or {}
    return {
        "intervention_id": intervention.id,
        "used_llm": metadata.get("used_llm"),
        "inference_status": metadata.get("inference_status"),
        "runtime": metadata.get("runtime"),
        "runtime_version": metadata.get("runtime_version"),
        "model_call_count": metadata.get("model_call_count"),
        "provider": metadata.get("provider"),
        "model": metadata.get("model_name"),
        "auth_mode": metadata.get("auth_mode"),
        "base_url": metadata.get("base_url"),
        "local_invocation_id": metadata.get("local_invocation_id"),
    }


def assert_public_supervisor_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("used_llm") is not True:
        raise AssertionError("live supervisor receipt does not prove used_llm=true")
    if receipt.get("inference_status") != "completed":
        raise AssertionError("live supervisor inference did not complete")
    if receipt.get("runtime") != "strands-agents":
        raise AssertionError("live supervisor did not use the Strands runtime")
    count = receipt.get("model_call_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise AssertionError("live supervisor receipt has no model call")
    for field in ("provider", "model", "runtime_version"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip():
            raise AssertionError(f"live supervisor receipt is missing {field}")
    invocation_id = receipt.get("local_invocation_id")
    if not isinstance(invocation_id, str) or not invocation_id.startswith("pexinv_"):
        raise AssertionError("live supervisor receipt has no local invocation id")
    auth_mode = receipt.get("auth_mode")
    if not isinstance(auth_mode, str) or _SAFE_AUTH_MODE.fullmatch(auth_mode) is None:
        raise AssertionError("live supervisor receipt has no safe auth-mode label")
    base_url = receipt.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise AssertionError("live supervisor receipt has no public provider base URL")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise AssertionError("live supervisor base URL is not safe public provenance")


def intervention_receipt(intervention: Intervention) -> dict[str, Any]:
    metadata = intervention.metadata or {}
    raw_delivery = metadata.get("worker_delivery_receipt")
    return {
        "intervention_id": intervention.id,
        "session_id": intervention.session_id,
        "goal_id": intervention.goal_id,
        "trigger": intervention.trigger,
        "trigger_event_id": metadata.get("trigger_event_id"),
        "proposed_action": intervention.proposed_action.type.value,
        "action": intervention.action_taken,
        "action_payload": dict(intervention.proposed_action.payload),
        "action_rationale": intervention.proposed_action.rationale,
        "delivery_result": intervention.result,
        "worker_delivery_receipt": (
            dict(raw_delivery) if isinstance(raw_delivery, dict) else None
        ),
        "evidence": list(intervention.evidence),
        "outcome": intervention.outcome,
        "helped": intervention.helped,
        "observed_event_refs": list(metadata.get("outcome_event_ids") or []),
        "verification": metadata.get("verification") or {},
        "supervisor": supervisor_receipt(intervention),
    }


def event_receipts(events: Iterable[Any]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": event.event_id,
            "session_id": event.session_id,
            "goal_id": event.goal_id,
            "harness_type": event.harness_type.value,
            "event_type": event.event_type.value,
            "raw_event_ref": event.raw_event_ref,
            "vendor_turn_id": (event.metadata or {}).get("vendor_turn_id"),
            "raw_method": (event.metadata or {}).get("raw_method"),
            "turn_status": (event.metadata or {}).get("turn_status"),
        }
        for event in events
    ]


async def correlated_audit_receipts(
    store: Any,
    interventions: Iterable[Intervention],
) -> dict[str, Any]:
    """Prove canonical SQLite rows and their JSONL projections are identical."""

    expected = {item.id: item for item in interventions}
    if not expected:
        raise AssertionError("proof has no interventions to correlate")
    placeholders = ",".join("?" for _ in expected)
    parameters = tuple(expected)
    intervention_cursor = await store.db.execute(
        "SELECT id, session_id, goal_id, project_id, project_binding, "
        "vendor_session_id, harness_type, action_hash, version, json "
        f"FROM interventions WHERE id IN ({placeholders})",  # noqa: S608
        parameters,
    )
    stored_interventions = {
        str(row["id"]): row for row in await intervention_cursor.fetchall()
    }
    if set(stored_interventions) != set(expected):
        raise AssertionError("canonical SQLite intervention row is missing")

    audit_cursor = await store.db.execute(
        "SELECT id, intervention_id, record_type, json FROM intervention_audit "
        f"WHERE intervention_id IN ({placeholders}) ORDER BY id",  # noqa: S608
        parameters,
    )
    audit_rows = await audit_cursor.fetchall()
    if not audit_rows:
        raise AssertionError("canonical SQLite intervention audit is missing")

    projected: dict[int, list[dict[str, Any]]] = {}
    for line in store.audit_path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict) or not isinstance(value.get("audit_id"), int):
            raise AssertionError("intervention JSONL contains a malformed row")
        projected.setdefault(int(value["audit_id"]), []).append(value)

    receipts: list[dict[str, Any]] = []
    seen_interventions: set[str] = set()
    for row in audit_rows:
        audit_id = int(row["id"])
        intervention_id = str(row["intervention_id"])
        payload = json.loads(str(row["json"]))
        projection_rows = projected.get(audit_id) or []
        expected_projection = {**payload, "audit_id": audit_id}
        if projection_rows != [expected_projection]:
            raise AssertionError("SQLite intervention audit does not match JSONL projection")
        if payload.get("intervention_id") != intervention_id:
            raise AssertionError("SQLite audit row has a mismatched intervention id")
        seen_interventions.add(intervention_id)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        receipts.append(
            {
                "audit_id": audit_id,
                "intervention_id": intervention_id,
                "record_type": str(row["record_type"]),
                "payload_sha256": _sha256_bytes(encoded),
                "sqlite_jsonl_match": True,
                "payload": payload,
            }
        )
    if seen_interventions != set(expected):
        raise AssertionError("not every proof intervention has an audit revision")

    canonical_interventions: list[dict[str, Any]] = []
    for intervention_id, intervention in expected.items():
        row = stored_interventions[intervention_id]
        envelope = json.loads(str(row["json"]))
        required_envelope_fields = {
            "schema",
            "payload",
            "project_id",
            "project_binding",
            "vendor_session_id",
            "harness_type",
            "action_hash",
            "version",
        }
        if (
            not isinstance(envelope, dict)
            or set(envelope) != required_envelope_fields
            or envelope.get("schema") != "pex.intervention-bound.v1"
            or not isinstance(envelope.get("payload"), dict)
        ):
            raise AssertionError("canonical SQLite intervention envelope is invalid")
        stored = envelope["payload"]
        expected_action_hash = _canonical_fingerprint(
            intervention.proposed_action.model_dump(mode="json")
        )
        version = envelope.get("version")
        if (
            row["session_id"] != intervention.session_id
            or row["goal_id"] != intervention.goal_id
            or envelope.get("project_id") != row["project_id"]
            or not isinstance(envelope.get("project_id"), str)
            or not envelope["project_id"]
            or envelope.get("project_binding") != row["project_binding"]
            or not isinstance(envelope.get("project_binding"), str)
            or not envelope["project_binding"]
            or envelope.get("vendor_session_id") != row["vendor_session_id"]
            or not isinstance(envelope.get("vendor_session_id"), str)
            or not envelope["vendor_session_id"]
            or envelope.get("harness_type") != row["harness_type"]
            or not isinstance(envelope.get("harness_type"), str)
            or not envelope["harness_type"]
            or envelope.get("action_hash") != row["action_hash"]
            or envelope.get("action_hash") != expected_action_hash
            or version != row["version"]
            or not isinstance(version, int)
            or isinstance(version, bool)
            or version < 0
        ):
            raise AssertionError("canonical SQLite intervention binding is invalid")
        if stored != intervention.model_dump(mode="json"):
            raise AssertionError("in-memory and canonical SQLite interventions differ")
        stored_encoded = json.dumps(
            stored,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        canonical_interventions.append(
            {
                "intervention_id": intervention_id,
                "payload_sha256": _sha256_bytes(stored_encoded),
                "payload": stored,
            }
        )
        latest = next(
            row for row in reversed(receipts) if row["intervention_id"] == intervention_id
        )
        payload = latest["payload"]
        if (
            payload.get("session_id") != intervention.session_id
            or payload.get("goal_id") != intervention.goal_id
            or payload.get("outcome") != intervention.outcome
            or payload.get("helped") != intervention.helped
            or payload.get("observed_event_refs")
            != list((intervention.metadata or {}).get("outcome_event_ids") or [])
        ):
            raise AssertionError("latest audit revision is not the final intervention state")
    return {
        "sqlite_path": str(Path(store.path).resolve()),
        "jsonl_path": str(Path(store.audit_path).resolve()),
        "sqlite_interventions": canonical_interventions,
        "audit_rows": receipts,
    }


def assert_no_secret_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in _FORBIDDEN_SECRET_KEYS:
                raise AssertionError("proof receipt contains a forbidden secret field")
            assert_no_secret_fields(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_secret_fields(item)


def assert_no_environment_secrets(value: Any) -> None:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    for name, secret in os.environ.items():
        normalized = name.upper()
        if (
            secret
            and len(secret) >= 8
            and any(marker in normalized for marker in _SECRET_ENV_MARKERS)
            and secret in encoded
        ):
            raise AssertionError("proof receipt contains configured secret material")


def publish_proof(path: Path, receipt: dict[str, Any]) -> None:
    """Atomically replace a proof; only ``validated`` is a reusable receipt."""

    if receipt.get("proof_status") == "validated":
        validate_proof(receipt)
    assert_no_secret_fields(receipt)
    assert_no_environment_secrets(receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _canonical_fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _require_sha256(value: Any, *, label: str) -> str:
    rendered = str(value or "")
    if _HEX_SHA256.fullmatch(rendered) is None:
        raise AssertionError(f"proof {label} is not a SHA-256 fingerprint")
    return rendered


def _require_positive_int(value: Any, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"proof {label} is not a positive integer")
    return value


def _require_utc_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AssertionError(f"proof {label} timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AssertionError(f"proof {label} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise AssertionError(f"proof {label} timestamp is not UTC")
    return parsed.astimezone(UTC)


def _absolute_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise AssertionError(f"proof {label} path is missing")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise AssertionError(f"proof {label} path is not absolute")
    return candidate.resolve(strict=False)


def _assert_latest_audit_state(
    intervention: Intervention,
    payload: dict[str, Any],
) -> None:
    metadata = intervention.metadata or {}
    action = intervention.proposed_action
    expected = {
        "intervention_id": intervention.id,
        "session_id": intervention.session_id,
        "goal_id": intervention.goal_id,
        "trigger_event": intervention.trigger,
        "claims": metadata.get("claims") or [],
        "evidence": list(action.evidence),
        "supervisor_model": metadata.get("model_name"),
        "inference_request_id": metadata.get("inference_request_id"),
        "local_invocation_id": metadata.get("local_invocation_id"),
        "inference_status": metadata.get("inference_status"),
        "model_call_count": metadata.get("model_call_count"),
        "diagnosis": intervention.diagnosis,
        "decision": action.type.value,
        "action": intervention.action_taken,
        "action_payload": action.payload,
        "action_rationale": action.rationale,
        "confidence": action.confidence,
        "risk": action.risk.value,
        "reversible": action.reversible,
        "authority_required": action.authority_required.value,
        "expected_benefit": action.expected_benefit,
        "cooldown_seconds": action.cooldown_seconds,
        "policy_verdict": intervention.policy_verdict.value,
        "delivery_result": intervention.result,
        "worker_response": intervention.worker_response,
        "outcome": intervention.outcome,
        "helped": intervention.helped,
        "backend": metadata.get("backend"),
        "runtime": metadata.get("runtime"),
        "runtime_version": metadata.get("runtime_version"),
        "model_class": metadata.get("model_class"),
        "provider": metadata.get("provider"),
        "base_url": metadata.get("base_url"),
        "auth_mode": metadata.get("auth_mode"),
        "execution_mode": metadata.get("execution_mode"),
        "transport": metadata.get("transport"),
        "transport_invocation_id": metadata.get("transport_invocation_id"),
        "transport_request_id": metadata.get("transport_request_id"),
        "transport_status": metadata.get("transport_status"),
        "evidence_tools": metadata.get("evidence_tools") or [],
        "traces": metadata.get("traces") or [],
        "trigger_event_id": metadata.get("trigger_event_id"),
        "observed_event_refs": metadata.get("outcome_event_ids") or [],
        "created_at": intervention.created_at.isoformat(),
    }
    for key, expected_value in expected.items():
        if payload.get(key) != expected_value:
            raise AssertionError(f"latest audit state disagrees on {key}")


def _artifact_success(
    receipt: dict[str, Any],
    *,
    filename: str,
    content: str,
) -> None:
    artifact = receipt.get("artifact") or {}
    session = receipt["session"]
    artifact_path = _absolute_path(artifact.get("path"), label="artifact")
    cwd = _absolute_path(session.get("cwd"), label="session cwd")
    if artifact_path.parent != cwd or artifact_path.name != filename:
        raise AssertionError("proof artifact is not the exact session-workspace target")
    if artifact.get("content") != content:
        raise AssertionError("proof artifact does not contain the exact success value")
    goal = receipt["goal"]
    goal_text = " ".join(
        [
            str(goal.get("objective") or ""),
            *(str(item) for item in goal.get("acceptance_criteria") or []),
            *(str(item) for item in goal.get("evidence_requirements") or []),
        ]
    ).casefold()
    if filename.casefold() not in goal_text or content.casefold() not in goal_text:
        raise AssertionError("proof artifact success is not grounded in the durable goal")


def _assert_proof_semantics(
    receipt: dict[str, Any],
    canonical: dict[str, Intervention],
) -> None:
    interventions = receipt["interventions"]
    turns = receipt["turns"]
    kind = receipt.get("proof_kind")
    if kind == "evidence_supported_noop":
        if len(interventions) != 1 or len(turns) != 1:
            raise AssertionError("supported NOOP proof has an unexpected action or turn count")
        final = interventions[0]
        if (
            final.get("proposed_action") != "NOOP"
            or final.get("action") != "NOOP"
            or final.get("delivery_result") != "noop"
            or final.get("worker_delivery_receipt") is not None
            or (final.get("verification") or {}).get("acceptance_status") != "supported"
            or not final.get("evidence")
            or final.get("outcome")
            or final.get("helped") is not None
            or final.get("observed_event_refs")
        ):
            raise AssertionError("supported NOOP proof does not prove an evidence-backed NOOP")
        _artifact_success(receipt, filename="ping.txt", content="pong")
        return
    if kind == "same_thread_intervention_outcome":
        if len(interventions) != 2 or len(turns) < 2:
            raise AssertionError(
                "intervention outcome proof has an unexpected action or turn count"
            )
        initial, final = interventions
        delivery = initial.get("worker_delivery_receipt")
        delivery_by_action = {
            "SEND_NUDGE": "sent",
            "CONTINUE_SESSION": "continued",
            "REQUEST_VERIFICATION": "verification_requested",
        }
        action = str(initial.get("action") or "")
        worker_text = str((initial.get("action_payload") or {}).get("text") or "")
        if (
            initial.get("proposed_action") != action
            or delivery_by_action.get(action) != initial.get("delivery_result")
            or not isinstance(delivery, dict)
            or "missing:report.txt" not in (initial.get("evidence") or [])
            or "report" not in worker_text.casefold()
            or worker_text.startswith("PEX:")
            or initial.get("outcome") != "goal_evidence_supported"
            or initial.get("helped") is not True
        ):
            raise AssertionError("initial intervention is not specific and evidence-grounded")
        if (
            final.get("proposed_action") != "NOOP"
            or final.get("action") != "NOOP"
            or final.get("delivery_result") != "noop"
            or final.get("worker_delivery_receipt") is not None
            or (final.get("verification") or {}).get("acceptance_status") != "supported"
            or not final.get("evidence")
        ):
            raise AssertionError("final intervention is not an evidence-supported NOOP")
        if initial.get("trigger_event_id") == final.get("trigger_event_id") or str(
            final.get("trigger_event_id")
        ) not in (initial.get("observed_event_refs") or []):
            raise AssertionError("initial intervention does not observe the final STOP outcome")
        events_by_id = {
            str(event.get("event_id") or ""): event
            for event in receipt.get("events") or []
            if isinstance(event, dict)
        }
        final_stop = events_by_id.get(str(final.get("trigger_event_id") or "")) or {}
        if delivery.get("vendor_turn_id") != final_stop.get("vendor_turn_id"):
            raise AssertionError(
                "initial intervention delivery turn does not equal the final STOP turn"
            )
        initial_model = canonical[str(initial["intervention_id"])]
        final_model = canonical[str(final["intervention_id"])]
        if initial_model.created_at > final_model.created_at:
            raise AssertionError("intervention outcome chronology is reversed")
        _artifact_success(receipt, filename="report.txt", content="shipped")
        return
    raise AssertionError("proof kind is not a supported current receipt")


def validate_proof(receipt: dict[str, Any]) -> None:
    """Fail-closed reuse gate for a self-contained fresh Codex proof receipt."""

    if not isinstance(receipt, dict):
        raise AssertionError("proof receipt is not an object")
    if receipt.get("schema") != PROOF_SCHEMA or receipt.get("proof_status") != "validated":
        raise AssertionError("proof receipt schema or status is not current")
    if _RUN_ID.fullmatch(str(receipt.get("run_id") or "")) is None:
        raise AssertionError("proof run id is not a UUID-bound Codex proof id")
    started_at = _require_utc_timestamp(receipt.get("started_at"), label="start")
    completed_at = _require_utc_timestamp(receipt.get("completed_at"), label="completion")
    now = datetime.now(UTC)
    if (
        started_at < datetime(2020, 1, 1, tzinfo=UTC)
        or completed_at < started_at
        or completed_at - started_at > timedelta(hours=1)
        or completed_at > now + timedelta(minutes=5)
    ):
        raise AssertionError("proof timestamps are unsafe or out of order")

    source = receipt.get("source")
    if not isinstance(source, dict):
        raise AssertionError("proof source provenance is malformed")
    repo_root = _absolute_path(source.get("repo_root"), label="source root")
    dirty = source.get("dirty")
    dirty_count = source.get("dirty_status_record_count")
    source_count = source.get("source_file_count")
    if (
        source.get("kind") != "git_worktree"
        or _HEX_REVISION.fullmatch(str(source.get("revision") or "")) is None
        or not isinstance(dirty, bool)
        or not isinstance(dirty_count, int)
        or isinstance(dirty_count, bool)
        or dirty_count < 0
        or dirty != (dirty_count > 0)
        or not isinstance(source_count, int)
        or isinstance(source_count, bool)
        or not 1 <= source_count <= _MAX_SOURCE_FILES
    ):
        raise AssertionError("proof source identity or inventory is invalid")
    _require_sha256(source.get("source_fingerprint"), label="source fingerprint")
    _require_sha256(source.get("dirty_fingerprint"), label="dirty fingerprint")
    assert_source_unchanged(source, capture_source_provenance(repo_root))

    app_server = receipt.get("app_server")
    if not isinstance(app_server, dict):
        raise AssertionError("proof Codex child provenance is malformed")
    binary_path = _absolute_path(app_server.get("binary_path"), label="Codex binary")
    command = app_server.get("command")
    if (
        not isinstance(command, list)
        or len(command) != 4
        or command[1:] != ["app-server", "--listen", "stdio://"]
        or _absolute_path(command[0], label="Codex command executable") != binary_path
    ):
        raise AssertionError("proof Codex child command is not exact")
    if app_server.get("process_running") is not True or app_server.get("initialized") is not True:
        raise AssertionError("proof Codex child was not initialized and running")
    _require_positive_int(app_server.get("process_id"), label="Codex child process id")
    _require_positive_int(app_server.get("binary_size"), label="Codex binary size")
    _require_sha256(app_server.get("binary_sha256"), label="Codex binary fingerprint")
    command_fingerprint = _require_sha256(
        app_server.get("command_fingerprint"), label="Codex command fingerprint"
    )
    if command_fingerprint != _canonical_fingerprint(command):
        raise AssertionError("proof Codex command fingerprint does not match the command")
    initialize_receipt = app_server.get("initialize_receipt")
    if (
        not isinstance(initialize_receipt, dict)
        or not initialize_receipt
        or not isinstance(initialize_receipt.get("platformOs"), str)
        or not initialize_receipt["platformOs"].strip()
    ):
        raise AssertionError("proof Codex initialize receipt is missing")
    initialize_fingerprint = _require_sha256(
        app_server.get("initialize_receipt_fingerprint"),
        label="Codex initialize fingerprint",
    )
    if initialize_fingerprint != _canonical_fingerprint(initialize_receipt):
        raise AssertionError("proof Codex initialize fingerprint does not match its receipt")
    process_captured_at = _require_utc_timestamp(
        app_server.get("captured_at"), label="process capture"
    )
    if not started_at <= process_captured_at <= completed_at:
        raise AssertionError("proof process capture is outside the proof interval")

    goal = receipt.get("goal")
    session = receipt.get("session")
    if not isinstance(goal, dict) or not isinstance(session, dict):
        raise AssertionError("proof durable goal or session is malformed")
    session_metadata = session.get("metadata") or {}
    vendor_thread_id = str(session.get("vendor_session_id") or "")
    session_id = str(session.get("id") or "")
    goal_id = str(goal.get("id") or "")
    project_id = str(goal.get("project_id") or "")
    if (
        receipt.get("sandbox") != "workspace-write"
        or session.get("harness_type") != "codex"
        or not vendor_thread_id
        or session_id != f"codex:{vendor_thread_id}"
        or session.get("goal_id") != goal_id
        or session.get("project_id") != project_id
        or session.get("cwd") != project_id
        or session_metadata.get("sandbox") != "workspace-write"
        or session_metadata.get("isolated") is not True
        or session_metadata.get("source") != "pexbench"
    ):
        raise AssertionError("proof durable goal/session/thread binding is invalid")
    _absolute_path(project_id, label="goal project")

    turns = receipt.get("turns")
    if not isinstance(turns, list) or not 1 <= len(turns) <= 20:
        raise AssertionError("proof turn receipt count is invalid")
    for turn in turns:
        sandbox_policy = turn.get("sandbox_policy") if isinstance(turn, dict) else None
        if (
            not isinstance(turn, dict)
            or set(turn) != {"thread_id", "cwd", "approval_policy", "sandbox_policy"}
            or turn.get("thread_id") != vendor_thread_id
            or turn.get("cwd") != project_id
            or turn.get("approval_policy") != "never"
            or sandbox_policy
            != {
                "type": "workspaceWrite",
                "writableRoots": [project_id],
                "networkAccess": False,
            }
        ):
            raise AssertionError("proof turn is not exact workspace-write same-thread delivery")

    events = receipt.get("events")
    if not isinstance(events, list) or not events:
        raise AssertionError("proof event evidence is missing")
    events_by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = str(event.get("event_id") or "") if isinstance(event, dict) else ""
        raw_event_ref = event.get("raw_event_ref") if isinstance(event, dict) else None
        vendor_turn_id = event.get("vendor_turn_id") if isinstance(event, dict) else None
        if (
            not event_id
            or event_id in events_by_id
            or set(event)
            != {
                "event_id",
                "session_id",
                "goal_id",
                "harness_type",
                "event_type",
                "raw_event_ref",
                "vendor_turn_id",
                "raw_method",
                "turn_status",
            }
            or event.get("session_id") != session_id
            or event.get("goal_id") != goal_id
            or event.get("harness_type") != "codex"
            or not isinstance(raw_event_ref, str)
            or not raw_event_ref
            or not isinstance(vendor_turn_id, str)
            or not vendor_turn_id
        ):
            raise AssertionError("proof event evidence has an invalid same-session binding")
        try:
            vendor_ref = json.loads(raw_event_ref)
        except (TypeError, ValueError) as exc:
            raise AssertionError("proof event raw reference is not canonical JSON") from exc
        if (
            not isinstance(vendor_ref, dict)
            or set(vendor_ref) not in (
                {"schema", "thread_id", "turn_id"},
                {"schema", "thread_id", "turn_id", "item_id"},
            )
            or vendor_ref.get("schema") != "pex.codex-event-ref.v1"
            or vendor_ref.get("thread_id") != vendor_thread_id
            or vendor_ref.get("turn_id") != vendor_turn_id
            or raw_event_ref
            != json.dumps(vendor_ref, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        ):
            raise AssertionError("proof event raw reference is not canonical Codex provenance")
        if event.get("event_type") == "stop":
            if (
                set(vendor_ref) != {"schema", "thread_id", "turn_id"}
                or event_id != f"{session_id}:turn:{vendor_turn_id}"
            ):
                raise AssertionError("proof STOP event does not match its vendor turn identity")
        else:
            item_id = str(vendor_ref.get("item_id") or "")
            if not item_id or event_id != f"{session_id}:item:{item_id}":
                raise AssertionError("proof item event does not match its vendor item identity")
        events_by_id[event_id] = event

    interventions = receipt.get("interventions")
    audit = receipt.get("audit_receipts")
    if not isinstance(interventions, list) or not interventions or not isinstance(audit, dict):
        raise AssertionError("proof durable intervention evidence is malformed")
    canonical_rows = audit.get("sqlite_interventions")
    audit_rows = audit.get("audit_rows")
    if not isinstance(canonical_rows, list) or not isinstance(audit_rows, list):
        raise AssertionError("proof durable audit rows are malformed")
    sqlite_path = _absolute_path(audit.get("sqlite_path"), label="SQLite receipt")
    jsonl_path = _absolute_path(audit.get("jsonl_path"), label="audit JSONL receipt")
    project_path = _absolute_path(project_id, label="session project")
    if (
        sqlite_path.parent != project_path
        or sqlite_path.name != "pex.sqlite"
        or jsonl_path.parent != project_path
        or jsonl_path.name != "PEX_INTERVENTION_LOG.jsonl"
    ):
        raise AssertionError("proof durable stores are not the exact isolated workspace stores")

    high_by_id: dict[str, dict[str, Any]] = {}
    referenced_event_ids: set[str] = set()
    for high in interventions:
        intervention_id = str(high.get("intervention_id") or "") if isinstance(high, dict) else ""
        if not intervention_id or intervention_id in high_by_id:
            raise AssertionError("proof high-level intervention ids are invalid")
        assert_public_supervisor_receipt(high.get("supervisor") or {})
        if high.get("session_id") != session_id or high.get("goal_id") != goal_id:
            raise AssertionError("proof intervention is not bound to the durable session")
        trigger_event_id = str(high.get("trigger_event_id") or "")
        observed = [str(value) for value in high.get("observed_event_refs") or []]
        if not trigger_event_id or len(observed) != len(set(observed)):
            raise AssertionError("proof intervention event references are invalid")
        referenced_event_ids.update({trigger_event_id, *observed})
        trigger = events_by_id.get(trigger_event_id) or {}
        if (
            trigger.get("event_type") != "stop"
            or trigger.get("harness_type") != "codex"
            or trigger.get("raw_method") != "turn/completed"
            or trigger.get("turn_status") != "completed"
            or not trigger_event_id.startswith(f"{session_id}:turn:")
        ):
            raise AssertionError("proof intervention trigger is not an exact successful STOP")
        delivery = high.get("worker_delivery_receipt")
        if delivery is not None:
            if (
                not isinstance(delivery, dict)
                or set(delivery)
                != {
                    "schema",
                    "target_session_id",
                    "vendor_session_id",
                    "vendor_turn_id",
                }
                or delivery.get("schema") != "pex.worker-delivery.codex-turn.v1"
                or delivery.get("target_session_id") != session_id
                or delivery.get("vendor_session_id") != vendor_thread_id
                or not isinstance(delivery.get("vendor_turn_id"), str)
                or not delivery["vendor_turn_id"]
            ):
                raise AssertionError("proof worker delivery receipt is not exact Codex authority")
            if any(
                (events_by_id.get(event_id) or {}).get("vendor_turn_id")
                != delivery["vendor_turn_id"]
                for event_id in observed
            ):
                raise AssertionError(
                    "proof observed event is not from the delivered Codex continuation"
                )
        high_by_id[intervention_id] = high
    if set(events_by_id) != referenced_event_ids:
        raise AssertionError("proof event receipt contains missing or unrelated evidence")

    canonical: dict[str, Intervention] = {}
    for row in canonical_rows:
        if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
            raise AssertionError("proof canonical SQLite intervention row is malformed")
        intervention_id = str(row.get("intervention_id") or "")
        if not intervention_id or intervention_id in canonical:
            raise AssertionError("proof canonical SQLite intervention ids are invalid")
        fingerprint = _require_sha256(
            row.get("payload_sha256"), label="SQLite intervention payload"
        )
        if fingerprint != _canonical_fingerprint(row["payload"]):
            raise AssertionError("proof canonical SQLite intervention hash does not match")
        try:
            model = Intervention.model_validate(row["payload"])
        except (TypeError, ValueError) as exc:
            raise AssertionError("proof canonical SQLite intervention is invalid") from exc
        if model.id != intervention_id or model.trigger != "stop":
            raise AssertionError("proof canonical SQLite intervention identity is invalid")
        if model.policy_verdict.value != "allow":
            raise AssertionError("proof canonical intervention was not policy-allowed")
        if intervention_receipt(model) != high_by_id.get(intervention_id):
            raise AssertionError("proof high-level receipt disagrees with canonical SQLite")
        created_at = _require_utc_timestamp(model.created_at.isoformat(), label="intervention")
        if not started_at <= created_at <= completed_at:
            raise AssertionError("proof intervention timestamp is outside the proof interval")
        canonical[intervention_id] = model
    if set(canonical) != set(high_by_id):
        raise AssertionError("proof canonical and high-level intervention sets differ")

    seen_audit_ids: set[int] = set()
    audited_intervention_ids: set[str] = set()
    latest_by_intervention: dict[str, dict[str, Any]] = {}
    previous_audit_id = 0
    created_audits: set[str] = set()
    for row in audit_rows:
        if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
            raise AssertionError("proof immutable audit row is malformed")
        audit_id = _require_positive_int(row.get("audit_id"), label="audit id")
        intervention_id = str(row.get("intervention_id") or "")
        payload = row["payload"]
        if (
            audit_id in seen_audit_ids
            or audit_id <= previous_audit_id
            or intervention_id not in canonical
            or row.get("sqlite_jsonl_match") is not True
            or row.get("record_type") != payload.get("record_type")
            or payload.get("intervention_id") != intervention_id
        ):
            raise AssertionError("proof immutable audit ordering or correlation is invalid")
        fingerprint = _require_sha256(row.get("payload_sha256"), label="audit payload")
        if fingerprint != _canonical_fingerprint(payload):
            raise AssertionError("proof immutable audit payload hash does not match")
        recorded_at = _require_utc_timestamp(payload.get("recorded_at"), label="audit record")
        if not started_at <= recorded_at <= completed_at:
            raise AssertionError("proof audit timestamp is outside the proof interval")
        if row.get("record_type") == "created":
            created_audits.add(intervention_id)
        seen_audit_ids.add(audit_id)
        audited_intervention_ids.add(intervention_id)
        latest_by_intervention[intervention_id] = payload
        previous_audit_id = audit_id
    if audited_intervention_ids != set(canonical) or created_audits != set(canonical):
        raise AssertionError("proof immutable audit history is incomplete")
    for intervention_id, model in canonical.items():
        _assert_latest_audit_state(model, latest_by_intervention[intervention_id])

    _assert_proof_semantics(receipt, canonical)
    assert_no_secret_fields(receipt)
    assert_no_environment_secrets(receipt)
