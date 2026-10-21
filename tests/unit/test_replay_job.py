"""Real deterministic pipeline in disposable processes; no hosted sandbox claim."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pex_bridge.hosted_replay import CATALOGUE
from pex_bridge.replay_job import FIXTURES, MAX_RESULT_BYTES, ReplayJobResult, encode_result
from pydantic import ValidationError


@pytest.fixture(scope="module")
def real_results(tmp_path_factory):
    results = {}
    for fixture in FIXTURES:
        root = tmp_path_factory.mktemp(fixture)
        # Sanitize BEFORE Python startup, rather than trusting the job's later
        # downstream scrub. No inherited provider keys, owner HOME or PEX config.
        env = {
            "PATH": os.pathsep.join((str(Path(sys.executable).parent), os.defpath)),
            "HOME": str(root),
            "PEX_HOME": str(root / "bootstrap"),
            "PEX_SUPERVISOR_DISABLE": "1",
            "PEX_CLOUD_REASONING": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        # Canaries fail the actual run if it constructs a default/live adapter
        # registry, calls semantic inference, or enters desktop discovery.
        guarded_entrypoint = """
import pex_bridge.adapters as adapters
from pex_bridge.agentcore import SupervisorRouter
from pex_bridge.pipeline import Pipeline

def forbidden(*args, **kwargs):
    raise AssertionError("live constructor/inference/discovery must not run")

adapters.AdapterRegistry.__init__ = forbidden
for name in ("CodexAdapter", "CursorAdapter", "OpenCodeAdapter", "ClaudeCodeAdapter",
             "QwenAdapter", "DevinAdapter", "HermesAdapter", "KimiAdapter",
             "OmpAdapter", "GrokBuildAdapter", "GrokBotAdapter"):
    getattr(adapters, name).__init__ = forbidden
SupervisorRouter.decide = forbidden
Pipeline.refresh_desktop_sessions = forbidden
from pex_bridge.replay_job import main
raise SystemExit(main())
"""
        completed = subprocess.run(
            [sys.executable, "-c", guarded_entrypoint, fixture, "--work-root", str(root)],
            capture_output=True,
            env=env,
            timeout=120,
            check=False,
        )
        assert completed.returncode == 0, (completed.stdout, completed.stderr)
        assert len(completed.stdout) <= MAX_RESULT_BYTES + 1
        result = ReplayJobResult.model_validate_json(completed.stdout)
        assert not list(root.iterdir()), "job must clean its home, database and workspaces"
        assert str(root) not in completed.stdout.decode()
        results[fixture] = result
    return results


def test_real_premature_stop_pipeline(real_results):
    result = real_results["premature_stop_eval"]
    assert result.replay and result.not_live_control
    assert result.inference_status == "not_attempted"
    assert result.declared_expectation_met is True
    assert result.claims_adjudicated > 0
    assert result.events_adjudicated > 0
    assert result.claim_verdicts
    assert result.evidence_summary
    assert [step.status for step in result.verification_sequence] == ["uncertain", "supported"]
    assert "no_pytest_observed" in result.evidence_summary
    assert result.completion_status == "verified_complete"


def test_real_tamper_pipeline(real_results):
    result = real_results["tampered_acceptance_eval"]
    assert result.completion_status == "verified_complete"
    assert result.declared_expectation_met is True
    assert [step.status for step in result.verification_sequence] == ["uncertain", "supported"]
    assert result.verification_sequence[0].modified_acceptance_files == ["tests/test_core.py"]
    assert "SEND_NUDGE" in result.interventions
    assert result.integrity_incidents > 0


def test_result_contract_is_bounded_and_has_no_raw_store(real_results):
    assert set(FIXTURES) == set(CATALOGUE)
    for result in real_results.values():
        encoded = encode_result(result)
        assert len(encoded) <= MAX_RESULT_BYTES
        fields = json.loads(encoded)
        assert "session_id" not in fields
        assert "goal_id" not in fields
        assert "workspace" not in fields
        assert "inbox" not in fields
        with pytest.raises(ValidationError):
            ReplayJobResult.model_validate({**fields, "raw_store": "not allowed"})
        with pytest.raises(ValidationError):
            ReplayJobResult.model_validate({**fields, "evidence_summary": ["x" * 161]})
        with pytest.raises(ValidationError):
            ReplayJobResult.model_validate(
                {**fields, "claim_verdicts": fields["claim_verdicts"] * 6}
            )


def test_unknown_job_fixture_rejected_without_execution(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "pex_bridge.replay_job", "../inline", "--work-root", str(tmp_path)],
        capture_output=True,
        env={"PATH": os.defpath, "HOME": str(tmp_path), "PEX_HOME": str(tmp_path / "bootstrap")},
        timeout=10,
        check=False,
    )
    assert completed.returncode == 2
    assert not list(tmp_path.iterdir())


def test_encoded_result_enforces_total_byte_bound(real_results):
    fields = real_results["tampered_acceptance_eval"].model_dump()
    fields["verification_sequence"] = [
        {"status": "uncertain", "modified_acceptance_files": ["x" * 240] * 16}
    ] * 16
    valid_but_too_large = ReplayJobResult.model_validate(fields)
    with pytest.raises(ValueError, match="transport bound"):
        encode_result(valid_but_too_large)
