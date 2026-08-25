"""Attach the real PEX supervisor to an isolated worker after it has begun.

This module must not import the hidden evaluator. It must not receive stressor
labels or oracle facts. The only extra the treatment arm gets is this loop.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pex_bridge.observe import snapshot
from pex_protocol.actions import InterventionType
from pex_protocol.session import HarnessSession

PROCESS = Path(__file__).with_name("pex_supervisor_process.py")


async def supervise_isolated_codex(
    adapter: Any,
    session: HarnessSession,
    workspace: Path,
    task_md: str,
    *,
    store_path: Path,
    max_followups: int = 2,
    turn_timeout: float = 600,
) -> dict[str, Any]:
    """Observe a completed/stopped worker turn, reason, maybe intervene, observe again."""
    audits: list[dict[str, Any]] = []
    outgoing_messages: list[str] = []
    followups = 0
    observed = snapshot(workspace, run_pytest=False)
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
            timeout=min(turn_timeout, 180),
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
            audit["result_afterward"] = "max_followups_reached"
            break
        before_turn = getattr(adapter, "last_turn_id", None)
        sent, outcome, text = await _execute_public_intervention(adapter, session, action)
        audit["policy_result"] = "allow" if sent else "deny"
        audit["actual_action_sent"] = action_type if sent else None
        audit["result_afterward"] = outcome
        if text:
            outgoing_messages.append(text)
        after_turn = getattr(adapter, "last_turn_id", None)
        if not sent or not after_turn or after_turn == before_turn:
            break
        await adapter.wait_for_turn_completion(session, after_turn, timeout=turn_timeout)
        followups += 1
        observed = snapshot(workspace, run_pytest=False)

    return {
        "backend": backend,
        "used_llm": any(a.get("used_llm") for a in audits),
        "followups": followups,
        "audits": audits,
        "observed_files": observed["files"],
        "model": backend.get("model_id"),
        "outgoing_messages": outgoing_messages,
        "supervisor_process_isolated": True,
    }


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
            "pytest": None,
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
    control_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pex-supervisor-", dir=control_dir) as tmp:
        request_path = Path(tmp) / "request.json"
        response_path = Path(tmp) / "response.json"
        request_path.write_text(
            json.dumps(
                {
                    "public_task": task_md,
                    "project_id": str(workspace),
                    "goal_id": goal_id,
                    "session": session.model_dump(mode="json"),
                    "workspace_files": observed.get("files") or [],
                    "agent_messages": agent_messages[-20:],
                    "last_message": agent_messages[-1] if agent_messages else "stopped",
                },
                default=str,
            ),
            encoding="utf-8",
        )
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(PROCESS),
            str(request_path),
            str(response_path),
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
                    )
                )
            },
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError("PEX supervisor process timed out") from None
        if proc.returncode != 0 or not response_path.is_file():
            detail = (stderr or stdout).decode(errors="replace")[-2000:]
            raise RuntimeError(f"PEX supervisor process failed: {detail}")
        return json.loads(response_path.read_text(encoding="utf-8"))


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
