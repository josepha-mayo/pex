"""Real API -> local job -> owned result integration, NOT a hosted sandbox test.

The subprocess adapter is deliberately TEST ONLY. Production has no such runner.
"""

import asyncio
import os
import signal
import sys
from pathlib import Path

import httpx
import pytest
from pex_bridge.hosted_replay import Limits, create_hosted_replay_app
from pex_bridge.replay_job import FIXTURES, MAX_RESULT_BYTES, ReplayJobResult

ORIGIN = "https://pex.example"
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "demo"


class TestOnlySubprocessRunner:
    __test__ = False

    def __init__(self, timeout=30):
        self.timeout = timeout
        self.processes = []
        self.calls = 0
        self.started = asyncio.Event()

    def command(self, context):
        return [
            sys.executable,
            "-m",
            "pex_bridge.replay_job",
            context.fixture_path.stem,
            "--work-root",
            str(context.workspace),
        ]

    async def execute(self, context):
        self.calls += 1
        # Sanitized before Python starts. The job independently scrubs its
        # downstream environment; neither layer is a security sandbox.
        env = {
            "PATH": os.pathsep.join((str(Path(sys.executable).parent), os.defpath)),
            "HOME": str(context.pex_home),
            "PEX_HOME": str(context.pex_home),
            "PEX_SUPERVISOR_DISABLE": "1",
            "PEX_CLOUD_REASONING": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        process = await asyncio.create_subprocess_exec(
            *self.command(context),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=os.name == "posix",
        )
        self.processes.append(process)
        self.started.set()
        try:
            stdout, _stderr = await asyncio.wait_for(process.communicate(), self.timeout)
            if process.returncode != 0 or len(stdout) > MAX_RESULT_BYTES + 1:
                raise ValueError("local replay job failed or exceeded output bound")
            return ReplayJobResult.model_validate_json(stdout)
        finally:
            if process.returncode is None:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                await process.wait()


async def create_visitor(client):
    response = await client.post("/api/replay/visitors")
    assert response.status_code == 201
    return {"authorization": "Bearer " + response.json()["visitor_token"]}


async def terminal_status(client, headers, run_id):
    async with asyncio.timeout(40):
        while True:
            response = await client.get("/api/replay/runs/" + run_id, headers=headers)
            assert response.status_code == 200
            if response.json()["state"] != "running":
                return response.json()
            await asyncio.sleep(0.01)


def app_for(tmp_path, runner, *, run_timeout=35):
    return create_hosted_replay_app(
        allowed_origin=ORIGIN,
        state_root=tmp_path / "runs",
        fixture_root=FIXTURE_ROOT,
        runner=runner,
        limits=Limits(run_timeout_seconds=run_timeout),
    )


@pytest.mark.parametrize("fixture", FIXTURES)
async def test_real_job_through_owned_api(tmp_path, monkeypatch, fixture):
    monkeypatch.setenv("PEX_HOME", str(tmp_path / "test-home"))
    runner = TestOnlySubprocessRunner()
    app = app_for(tmp_path, runner)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={"origin": ORIGIN}
        ) as client,
    ):
        owner, foreign = await create_visitor(client), await create_visitor(client)
        body = {"fixture_id": fixture, "idempotency_key": "real-job"}
        started = await client.post("/api/replay/runs", headers=owner, json=body)
        assert started.status_code == 202
        run_id = started.json()["run_id"]
        path = f"/api/replay/runs/{run_id}/result"
        assert (await client.get(path, headers=foreign)).status_code == 404
        assert (await client.get(path)).status_code == 401
        retry = await client.post("/api/replay/runs", headers=owner, json=body)
        assert retry.json()["run_id"] == run_id
        assert (await terminal_status(client, owner, run_id))["state"] == "completed"
        response = await client.get(path, headers=owner)
        assert response.status_code == 200
        assert len(response.content) <= MAX_RESULT_BYTES
        result = ReplayJobResult.model_validate_json(response.content)
        assert result.fixture_id == fixture
        assert result.replay and result.not_live_control
        assert result.inference_status == "not_attempted"
        assert result.completion_status == "verified_complete"
        assert result.declared_expectation_met is True
        assert [item.status for item in result.verification_sequence] == ["uncertain", "supported"]
        if fixture == "premature_stop_eval":
            assert "no_pytest_observed" in result.evidence_summary
        else:
            assert "acceptance_surface_modified:tests/test_core.py" in result.evidence_summary
            assert result.verification_sequence[0].modified_acceptance_files == [
                "tests/test_core.py"
            ]
            assert result.integrity_incidents == 1
            assert "SEND_NUDGE" in result.interventions
        assert (await client.get(path, headers=foreign)).status_code == 404
        assert runner.calls == 1
        assert all(process.returncode == 0 for process in runner.processes)
        assert list((tmp_path / "runs").iterdir()) == []
        assert str(tmp_path) not in response.text


@pytest.mark.parametrize("timeout_source", ["adapter", "api"])
async def test_test_only_process_timeout_reaps_and_cleans(tmp_path, monkeypatch, timeout_source):
    monkeypatch.setenv("PEX_HOME", str(tmp_path / "test-home"))

    class BlockedProcessRunner(TestOnlySubprocessRunner):
        def command(self, context):
            # Explicit timeout fault injection, not a simulated PEX result.
            return [sys.executable, "-c", "import time; time.sleep(60)"]

    runner = BlockedProcessRunner(timeout=0.1 if timeout_source == "adapter" else 30)
    app = app_for(tmp_path, runner, run_timeout=0.2 if timeout_source == "api" else 35)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={"origin": ORIGIN}
        ) as client,
    ):
        owner = await create_visitor(client)
        response = await client.post(
            "/api/replay/runs",
            headers=owner,
            json={"fixture_id": FIXTURES[0], "idempotency_key": "timeout"},
        )
        assert response.status_code == 202
        await runner.started.wait()
        run_id = response.json()["run_id"]
        status = await terminal_status(client, owner, run_id)
        assert status["state"] == "failed"
        assert status["error"] == "run_timeout"
        failed = await client.get(f"/api/replay/runs/{run_id}/result", headers=owner)
        assert failed.status_code == 409
        assert failed.json() == {"detail": "run_failed"}
        assert all(process.returncode is not None for process in runner.processes)
        assert list((tmp_path / "runs").iterdir()) == []
