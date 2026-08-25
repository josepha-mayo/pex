"""Four-arm PexBench driver.

Refuses to freeze the manifest until live Cursor and Codex arms exist for every
task. Never invents lift. Isolated temp workspaces only — do not turn/start on
the operator's live Codex threads unless --allow-live is set, and even then only
on a newly created thread whose cwd is the temp workspace.

Paired arms receive the same TASK.md. The only treatment difference is an
independent PEX supervisor attached after the worker has begun.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import boundary  # noqa: E402
import evaluator  # noqa: E402
import runner  # noqa: E402

PRESENTATION_ARMS = evaluator.PRESENTATION_ARMS
CURSOR_LIVE_REFUSAL = (
    "refusing live Cursor arm: do not spawn another Cursor window. "
    "This desktop session is already Cursor; observe it via ~/.cursor/hooks.json."
)


def readiness() -> dict[str, Any]:
    from pex_bridge.adapters.codex_bin import resolve_codex_bin
    from pex_bridge.adapters.desktop import list_desktop_apps
    from pex_bridge.adapters.grok_build_bin import resolve_grok_build
    from pex_bridge.adapters.hermes_bin import resolve_hermes

    desktops = list_desktop_apps()
    coverage = arm_coverage()
    blockers = freeze_blockers(coverage)
    hooks = Path.home() / ".cursor" / "hooks.json"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "desktops": desktops,
        "bins": {
            "codex": resolve_codex_bin(),
            "cursor_hooks": str(hooks) if hooks.is_file() else None,
            "grok_build": resolve_grok_build(),
            "hermes": resolve_hermes(),
        },
        "manifest_frozen": bool(runner.load_manifest().get("frozen")),
        "coverage": coverage,
        "freeze_blockers": blockers,
        "can_freeze": not blockers,
        "note": (
            "Presentation arms are cursor, cursor_pex, codex, codex_pex. "
            "synthetic_pex smoke is infrastructure only. "
            "Live Cursor/Codex runs require --allow-live and isolated workspaces. "
            "Paired arms share one TASK.md; treatment is attached PEX, not a better prompt."
        ),
    }


def arm_coverage() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    if not runner.RESULTS.exists():
        return found
    for path in sorted(runner.RESULTS.glob("*.jsonl")):
        if "INVALID" in path.parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            arm = str(row.get("arm") or "")
            task = str(row.get("task") or "")
            key = f"{arm}:{task}"
            found[key] = {
                "arm": arm,
                "task": task,
                "success": row.get("success"),
                "live": bool(row.get("live")),
                "not_a_presentation_arm": bool(row.get("not_a_presentation_arm")),
                "pair_id": row.get("pair_id"),
                "prompt_sha256": row.get("prompt_sha256"),
                "seed_manifest_sha256": row.get("seed_manifest_sha256"),
                "worker_config_sha256": row.get("worker_config_sha256"),
                "worker_model": row.get("worker_model"),
                "harness_identity_sha256": row.get("harness_identity_sha256"),
                "transport_kind": row.get("transport_kind"),
                "pex_process_isolated": bool(
                    (row.get("pex") or {}).get("supervisor_process_isolated")
                ),
                "file": path.name,
            }
    return found


def freeze_blockers(coverage: dict[str, dict[str, Any]] | None = None) -> list[str]:
    coverage = coverage if coverage is not None else arm_coverage()
    missing: list[str] = []
    for arm in PRESENTATION_ARMS:
        for task in evaluator.task_ids():
            row = coverage.get(f"{arm}:{task}")
            if row is None:
                missing.append(f"no result for {arm}/{task}")
            elif not row.get("live"):
                missing.append(f"{arm}/{task} is not live")
            elif row.get("not_a_presentation_arm"):
                missing.append(f"{arm}/{task} is labeled non-presentation")
    for harness in ("cursor", "codex"):
        for task in evaluator.task_ids():
            baseline = coverage.get(f"{harness}:{task}")
            treatment = coverage.get(f"{harness}_pex:{task}")
            if not baseline or not treatment:
                continue
            for field in (
                "pair_id",
                "prompt_sha256",
                "seed_manifest_sha256",
                "worker_config_sha256",
                "worker_model",
                "harness_identity_sha256",
            ):
                if not baseline.get(field) or baseline.get(field) != treatment.get(field):
                    missing.append(f"{harness}/{task} paired {field} mismatch")
            if not treatment.get("pex_process_isolated"):
                missing.append(f"{harness}_pex/{task} supervisor was not process-isolated")
    return missing


def try_freeze() -> dict[str, Any]:
    blockers = freeze_blockers()
    if blockers:
        return {
            "frozen": False,
            "wrote": False,
            "blockers": blockers,
            "note": (
                "Manifest stays unfrozen until every presentation arm "
                "has a live evaluator row."
            ),
        }
    manifest = runner.load_manifest()
    manifest["frozen"] = True
    runner.MANIFEST.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return {"frozen": True, "wrote": True, "blockers": []}


def run_synthetic(task_id: str, run_id: str = "synthetic_smoke") -> dict[str, Any]:
    with TemporaryDirectory(prefix="pexbench_") as tmp:
        workspace = Path(tmp) / task_id
        seed = evaluator.seed_workspace(task_id, workspace)
        extra = evaluator.complete_synthetic(task_id, workspace)
        extra.update(seed)
        result = evaluator.evaluate(task_id, workspace, extra)
        path = runner.RESULTS / f"{run_id}.jsonl"
        runner.write_synthetic_smoke(
            path,
            success=bool(result["success"]),
            human_interventions=0,
            extra={"task": task_id, "reasons": result["reasons"]},
        )
        result["arm"] = "synthetic_pex"
        result["written"] = str(path)
        return result


def isolated_workspace(
    run_id: str,
    arm: str,
    task_id: str,
    workspace_root: Path | None = None,
) -> Path:
    """Host-visible isolated dir. Folder name is opaque so cwd does not leak the stressor."""
    base = Path(workspace_root) if workspace_root else (Path.home() / ".pex" / "pexbench")
    path = (base / "workspaces" / boundary.opaque_workspace_name(run_id, arm, task_id)).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_workspace(run_id: str, arm: str, task_id: str, workspace: Path) -> Path | None:
    dest = runner.RESULTS / "_scratch" / run_id / arm / task_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(workspace, dest, dirs_exist_ok=True)
    except OSError:
        return None
    return dest


async def run_live(
    arm: str,
    task_id: str,
    run_id: str,
    *,
    transport: Any = None,
    turn_timeout: float = 600,
    workspace_root: Path | None = None,
    worker_model: str | None = None,
) -> dict[str, Any]:
    """Isolated live run. Cursor never opens a second window. Codex only thread/start."""
    if arm in {"cursor", "cursor_pex"}:
        raise RuntimeError(CURSOR_LIVE_REFUSAL)
    if arm not in {"codex", "codex_pex"}:
        raise RuntimeError(f"unknown presentation arm {arm}")
    from pex_bridge.adapters.codex import CodexAdapter, CodexStdioTransport
    from pex_bridge.adapters.codex_bin import resolve_codex_bin

    owned_transport = False
    if transport is None:
        binary = resolve_codex_bin()
        if not binary:
            raise RuntimeError("codex CLI not found; cannot run a live Codex arm")
        transport = CodexStdioTransport(binary)
        owned_transport = True
    if isinstance(transport, CodexStdioTransport) and not worker_model:
        raise RuntimeError("live Codex arms require an explicit --worker-model for parity")
    adapter = CodexAdapter(transport)
    workspace = isolated_workspace(run_id, arm, task_id, workspace_root)
    try:
        seed = evaluator.seed_workspace(task_id, workspace)
        seed_manifest_sha256 = boundary.workspace_manifest_sha256(workspace)
        prompt = (workspace / "TASK.md").read_text(encoding="utf-8")
        boundary.assert_public_prompt(task_id, prompt)
        prompt_sha256 = boundary.sha256_text(prompt)
        session = await adapter.start_isolated_thread(str(workspace), name="isolated-job")
        started = await adapter.start_turn(
            session,
            prompt,
            extra_params={"model": worker_model} if worker_model else None,
        )
        turn_id = str((started.get("turn") or {}).get("id") or "")
        if not turn_id:
            raise RuntimeError("turn/start returned no turn id")
        sent = adapter.last_turn_params or {}
        worker_config_sha256 = boundary.worker_config_sha256(sent)
        if isinstance(sent.get("additionalContext"), dict) and sent["additionalContext"].get(
            "pex_handoff"
        ):
            raise RuntimeError(
                "refusing leaked additionalContext.pex_handoff on a presentation arm"
            )
        turn = await adapter.wait_for_turn_completion(
            session,
            turn_id,
            timeout=turn_timeout,
        )
        pex_meta: dict[str, Any] | None = None
        if arm == "codex_pex":
            from pex_attach import supervise_isolated_codex

            store_path = workspace.parent / f"{workspace.name}.pex.sqlite"
            pex_meta = await supervise_isolated_codex(
                adapter,
                session,
                workspace,
                prompt,
                store_path=store_path,
                turn_timeout=turn_timeout,
            )
            if not pex_meta.get("supervisor_process_isolated"):
                raise RuntimeError(
                    "refusing treatment result without an isolated supervisor process"
                )
            for message in pex_meta.get("outgoing_messages") or []:
                boundary.assert_public_intervention(str(message))
        if task_id.endswith("permission_spam"):
            joined = " ".join(adapter.isolated_agent_messages).lower()
            if any(
                token in joined for token in ("should i run", "can i run pytest", "run pytest?")
            ):
                seed["human_prompts_for_pytest"] = 1
        result = evaluator.evaluate(task_id, workspace, seed)
        snapshot = _snapshot_workspace(run_id, arm, task_id, workspace)
        process = getattr(transport, "_proc", None)
        verified_live = (
            isinstance(transport, CodexStdioTransport)
            and process is not None
            and process.returncode is None
        )
        transport_kind = "codex_stdio" if verified_live else "test_double"
        harness_identity_sha256 = boundary.sha256_text(
            json.dumps(
                {
                    "command": getattr(transport, "command", None),
                    "server_info": getattr(transport, "init_result", None),
                },
                sort_keys=True,
                default=str,
            )
        )
        record = {
            "arm": arm,
            "task": task_id,
            "success": bool(result["success"]),
            "live": verified_live,
            "not_a_presentation_arm": not verified_live,
            "isolated": True,
            "pair_id": f"{run_id}:{task_id}",
            "thread_id": session.vendor_session_id,
            "turn_id": turn_id,
            "turn_status": turn.get("status"),
            "turn_error": turn.get("error"),
            "cwd": session.cwd,
            "prompt_sha256": prompt_sha256,
            "seed_manifest_sha256": seed_manifest_sha256,
            "worker_config_sha256": worker_config_sha256,
            "worker_model": worker_model,
            "harness_identity_sha256": harness_identity_sha256,
            "transport_kind": transport_kind,
            "transport_evidence": {
                "command": getattr(transport, "command", None),
                "pid": getattr(process, "pid", None),
                "server_info": getattr(transport, "init_result", None),
            },
            "snapshot": str(snapshot) if snapshot else None,
            "workspace_files": sorted(p.name for p in workspace.iterdir() if p.is_file()),
            "human_interventions": int(seed.get("human_prompts_for_pytest") or 0),
            "approval_decisions": adapter.isolated_approval_decisions,
            "item_types": adapter.isolated_item_types,
            "agent_messages": adapter.isolated_agent_messages,
            "pex": pex_meta,
            "reasons": result["reasons"],
            "ts": datetime.now(UTC).isoformat(),
        }
        path = runner.append_immutable(run_id, record)
        result.update(record)
        result["written"] = str(path)
        return result
    finally:
        if owned_transport:
            await transport.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="PexBench four-arm driver")
    parser.add_argument("command", choices=("readiness", "run", "freeze", "evaluate"))
    parser.add_argument("--arm", default="synthetic_pex")
    parser.add_argument("--task", default="pexbench_001_premature_stop")
    parser.add_argument("--run-id", default="synthetic_smoke")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--turn-timeout", type=float, default=600)
    parser.add_argument("--worker-model", default=None)
    args = parser.parse_args()
    if args.command == "readiness":
        print(json.dumps(readiness(), indent=2))
        return
    if args.command == "freeze":
        print(json.dumps(try_freeze(), indent=2))
        raise SystemExit(0 if not freeze_blockers() else 2)
    if args.command == "evaluate":
        if not args.workspace:
            raise SystemExit("--workspace is required for evaluate")
        print(json.dumps(evaluator.evaluate(args.task, Path(args.workspace)), indent=2))
        return
    if args.arm == "synthetic_pex":
        print(json.dumps(run_synthetic(args.task, args.run_id), indent=2))
        return
    if args.arm in PRESENTATION_ARMS:
        if not args.allow_live:
            raise SystemExit("presentation arms require --allow-live")
        print(
            json.dumps(
                asyncio.run(
                    run_live(
                        args.arm,
                        args.task,
                        args.run_id,
                        turn_timeout=args.turn_timeout,
                        worker_model=args.worker_model,
                    )
                ),
                indent=2,
            )
        )
        return
    raise SystemExit(f"unknown arm {args.arm}")


if __name__ == "__main__":
    main()
