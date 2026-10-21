"""One process, one real deterministic replay job; NOT a security sandbox.

Invoke with ``python -m pex_bridge.replay_job FIXTURE --work-root DIRECTORY``.
Never import/call main from a shared service: it replaces process environment and
bridge adapter construction. Public hosted starts remain disabled by default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

FIXTURES = ("premature_stop_eval", "tampered_acceptance_eval")
MAX_RESULT_BYTES = 16_384
# These projection/verifier statuses currently have no shared protocol enum.
# Keep explicit fail-closed sets aligned with Store.goal_completion_projection
# and pex_supervisor.verify's final aggregate verdict branch.
CompletionStatus = Literal["verified_complete", "incomplete", "in_progress", "uncertain"]
VerificationStatus = Literal[
    "supported", "contradicted", "acceptance_gap", "no_claims", "uncertain"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClaimSummary(StrictModel):
    claim: str = Field(max_length=200)
    status: VerificationStatus


class VerificationSummary(StrictModel):
    status: VerificationStatus
    modified_acceptance_files: list[Annotated[str, StringConstraints(max_length=240)]] = Field(
        max_length=16
    )


class ReplayJobResult(StrictModel):
    schema_version: Literal["pex.replay-job.v1"] = "pex.replay-job.v1"
    fixture_id: Literal["premature_stop_eval", "tampered_acceptance_eval"]
    replay: Literal[True] = True
    not_live_control: Literal[True] = True
    execution_mode: Literal["local_deterministic_replay"] = "local_deterministic_replay"
    inference_status: Literal["not_attempted"] = "not_attempted"
    completion_status: CompletionStatus
    completion_reason: str = Field(max_length=400)
    claim_verdicts: list[ClaimSummary] = Field(max_length=5)
    evidence_summary: list[Annotated[str, StringConstraints(max_length=160)]] = Field(max_length=4)
    verification_sequence: list[VerificationSummary] = Field(max_length=16)
    interventions: list[Annotated[str, StringConstraints(max_length=64)]] = Field(max_length=32)
    events_adjudicated: int = Field(ge=0, le=1000)
    claims_adjudicated: int = Field(ge=0, le=1000)
    integrity_incidents: int = Field(ge=0, le=1000)
    declared_expectation_met: bool


def encode_result(result: ReplayJobResult) -> bytes:
    encoded = result.model_dump_json().encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError("replay result exceeds transport bound")
    return encoded


def _configure_private_environment(root: Path) -> None:
    # Explicit allowlist, not a blacklist of known provider secrets. The launcher
    # must sanitize before Python startup too; this prevents downstream inheritance.
    system = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    os.environ.clear()
    os.environ.update(system)
    os.environ.update(
        PATH=os.pathsep.join((str(Path(sys.executable).parent), os.defpath)),
        HOME=str(root / "home"),
        USERPROFILE=str(root / "home"),
        XDG_CONFIG_HOME=str(root / "config"),
        XDG_CACHE_HOME=str(root / "cache"),
        TMPDIR=str(root / "tmp"),
        TEMP=str(root / "tmp"),
        TMP=str(root / "tmp"),
        PEX_HOME=str(root / "pex-home"),
        PEX_SUPERVISOR_DISABLE="1",
        PEX_CLOUD_REASONING="false",
        PEX_SUPERVISOR_MODE="local",
        PEX_CODEX_ATTACH="0",
        PEX_CURSOR_ATTACH="0",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    for child in ("home", "config", "cache", "tmp", "pex-home"):
        (root / child).mkdir()
    tempfile.tempdir = str(root / "tmp")


def _deny_network_audit(event, args):
    # Defense in depth for this Python process, not a sandbox/network firewall.
    # Public pytest subprocesses still require external OS network isolation.
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo"}:
        raise RuntimeError("network activity is forbidden in replay jobs")


async def _execute(fixture_id: str) -> ReplayJobResult:
    from httpx import ASGITransport, AsyncClient

    import pex_bridge.adapters as adapter_module
    from pex_bridge.adapters.synthetic import SyntheticAdapter

    class SyntheticOnlyRegistry:
        def __init__(self):
            self.synthetic = SyntheticAdapter()

        def get(self, name):
            return self.synthetic if name == "synthetic" else None

        def for_session(self, session_id):
            return self.get(session_id.split(":", 1)[0])

        def all(self):
            return [self.synthetic]

    # app.py constructs global state on import. Replace its constructor dependency
    # BEFORE importing it, in this disposable process only; do not instantiate any
    # live adapter and do not mutate a shared running bridge.
    if "pex_bridge.app" in sys.modules:
        raise RuntimeError("replay job requires a fresh process")
    adapter_module.AdapterRegistry = SyntheticOnlyRegistry
    from pex_bridge.app import create_app, state
    from pex_bridge.config import Settings

    state.settings = Settings.for_test(
        require_auth=False,
        home=Path(os.environ["PEX_HOME"]),
        cloud_reasoning=False,
        supervisor_mode="local",
        autonomy="manage",
    )
    state.pipeline.settings = state.settings
    state.token = None
    await state.store.connect()
    try:
        # ASGITransport does not run app lifespan: no discovery, server, sockets,
        # pumps, external workers, credential loading or remote model initialization.
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post("/v1/demo/replay", json={"fixture": fixture_id})
            response.raise_for_status()
            body = response.json()
        if body.get("replay") is not True or body.get("not_live_control") is not True:
            raise ValueError("missing replay labels")
        completion = body.get("completion") or {}
        declared = body.get("declared") or {}
        if not isinstance(declared.get("met"), bool):
            raise ValueError("fixture expectation was not adjudicated")
        verifications = []
        for intervention in body["interventions"]:
            metadata = intervention.get("metadata") or {}
            verification = metadata.get("verification")
            if verification:
                modified = (verification.get("acceptance_surface") or {}).get("modified") or []
                verifications.append(
                    VerificationSummary(
                        status=str(verification.get("status") or "")[:32],
                        modified_acceptance_files=[str(item)[:240] for item in modified[:16]],
                    )
                )
        return ReplayJobResult(
            fixture_id=fixture_id,
            completion_status=str(completion.get("status") or "")[:64],
            completion_reason=str(completion.get("reason") or "")[:400],
            claim_verdicts=[ClaimSummary.model_validate(item) for item in body["claim_verdicts"]],
            evidence_summary=[str(item)[:160] for item in body["verified_facts"][:4]],
            verification_sequence=verifications[:16],
            interventions=[
                str(item.get("action_taken") or "")[:64] for item in body["interventions"][:32]
            ],
            events_adjudicated=body["stats"]["events_adjudicated"],
            claims_adjudicated=body["stats"]["claims_adjudicated"],
            integrity_incidents=body["stats"]["integrity_incidents"],
            declared_expectation_met=declared["met"],
        )
    finally:
        await state.pipeline.close_presentations()
        await state.store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", choices=FIXTURES)
    parser.add_argument("--work-root", required=True, type=Path)
    args = parser.parse_args()
    # Caller supplies an already allocated private directory INSIDE its sandbox.
    work_root = args.work_root.resolve(strict=True)
    if not work_root.is_dir():
        parser.error("work-root must be an existing private directory")
    try:
        with tempfile.TemporaryDirectory(prefix="job-", dir=work_root) as private:
            _configure_private_environment(Path(private))
            sys.addaudithook(_deny_network_audit)
            result = asyncio.run(_execute(args.fixture))
            encoded = encode_result(result)
        sys.stdout.buffer.write(encoded + b"\n")
        return 0
    except Exception:
        # No exception text, paths, logs, credentials, raw store or partial results.
        sys.stdout.write(json.dumps({"error": "replay_job_failed"}) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
