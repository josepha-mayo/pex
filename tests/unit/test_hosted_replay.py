"""Mock-tested HTTP boundary only: these tests do not execute PEX replay."""

import asyncio
from pathlib import Path

import httpx
import pytest
from pex_bridge.hosted_replay import Limits, create_hosted_replay_app

ORIGIN = "https://pex.example"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "demo"


class StubRunner:
    def __init__(self):
        self.contexts = []

    async def execute(self, context):
        self.contexts.append(context)
        assert context.pex_home.is_dir()
        assert context.workspace.is_dir()
        return "completed"


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setenv("PEX_HOME", str(tmp_path / "test-home"))

    def make(runner=None, limits=None, clock=None):
        kwargs = {} if clock is None else {"clock": clock}
        app = create_hosted_replay_app(
            allowed_origin=ORIGIN,
            state_root=tmp_path / "runs",
            fixture_root=FIXTURES,
            runner=runner,
            limits=limits,
            **kwargs,
        )
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=ORIGIN,
            headers={"origin": ORIGIN},
        )

    return make


async def visitor(client):
    response = await client.post("/api/replay/visitors")
    assert response.status_code == 201
    return {"authorization": "Bearer " + response.json()["visitor_token"]}


def payload(key="retry", fixture="premature_stop_eval"):
    return {"fixture_id": fixture, "idempotency_key": key}


async def poll(client, headers, started):
    assert started.status_code == 202
    path = "/api/replay/runs/" + started.json()["run_id"]
    async with asyncio.timeout(2):
        while True:
            response = await client.get(path, headers=headers)
            if response.status_code != 200 or response.json()["state"] != "running":
                return response
            await asyncio.sleep(0.005)


async def test_default_fails_closed(factory, tmp_path):
    async with factory() as client:
        catalog = (await client.get("/api/replay/fixtures")).json()
        assert catalog["execution_available"] is False
        assert len(catalog["fixtures"]) == 2
        assert all(item["replay"] and item["not_live_control"] for item in catalog["fixtures"])
        headers = await visitor(client)
        response = await client.post("/api/replay/runs", headers=headers, json=payload())
        assert response.status_code == 503
        assert response.json()["detail"] == "isolated_replay_runner_unavailable"
        assert not (tmp_path / "runs").exists()


async def test_ownership_idempotency_and_cleanup(factory, tmp_path):
    runner = StubRunner()
    async with factory(runner) as client:
        first, second = await visitor(client), await visitor(client)
        a = await client.post("/api/replay/runs", headers=first, json=payload())
        a = await poll(client, first, a)
        repeat = await client.post("/api/replay/runs", headers=first, json=payload())
        assert a.status_code == repeat.status_code == 200
        assert a.json() == repeat.json()
        assert a.json()["replay"] and a.json()["not_live_control"]
        path = "/api/replay/runs/" + a.json()["run_id"]
        assert (await client.get(path, headers=second)).status_code == 404
        assert (await client.get(path)).status_code == 401
        b = await client.post("/api/replay/runs", headers=second, json=payload())
        b = await poll(client, second, b)
        assert b.json()["run_id"] != a.json()["run_id"]
        assert len(runner.contexts) == 2
        assert runner.contexts[0].pex_home != runner.contexts[1].pex_home
        assert list((tmp_path / "runs").iterdir()) == []
        conflict = await client.post(
            "/api/replay/runs",
            headers=first,
            json=payload(fixture="tampered_acceptance_eval"),
        )
        assert conflict.status_code == 409


@pytest.mark.parametrize(
    "extra", ["goal_id", "workspace", "command", "fixture", "provider", "token"]
)
async def test_unknown_fields_rejected(factory, extra):
    runner = StubRunner()
    async with factory(runner) as client:
        headers = await visitor(client)
        response = await client.post(
            "/api/replay/runs", headers=headers, json={**payload(), extra: "injected"}
        )
        assert response.status_code == 422
        assert runner.contexts == []


@pytest.mark.parametrize("fixture", ["../secret", "captured_live_eval", "", 1, None])
async def test_only_curated_fixtures(factory, fixture):
    async with factory(StubRunner()) as client:
        headers = await visitor(client)
        response = await client.post(
            "/api/replay/runs", headers=headers, json=payload(fixture=fixture)
        )
        assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/v1/sessions",
        "/v1/demo/replay",
        "/mcp/",
        "/docs",
        "/openapi.json",
        "/api/replay/runs/x/pause",
    ],
)
async def test_operator_routes_absent(factory, path):
    async with factory() as client:
        headers = await visitor(client)
        assert (await client.post(path, headers=headers, json={})).status_code == 404
        assert (await client.get(path, headers=headers)).status_code == 404


async def test_origin_body_and_visitor_capacity(factory):
    async with factory(limits=Limits(max_visitors=1)) as client:
        assert (await client.post("/api/replay/visitors", json={})).status_code == 422
        assert (
            await client.get("/api/replay/fixtures", headers={"origin": "null"})
        ).status_code == 403
        headers = await visitor(client)
        assert (await client.post("/api/replay/visitors")).status_code == 429

        async def chunks():
            yield b"x" * 1024
            yield b"x" * 1025

        result = await client.post("/api/replay/runs", headers=headers, content=chunks())
        assert result.status_code == 413


async def test_expiry_and_total_run_limit(factory):
    now = [0]
    async with factory(
        StubRunner(), Limits(max_visitors=1, max_runs_per_visitor=1), lambda: now[0]
    ) as client:
        headers = await visitor(client)
        result = await client.post("/api/replay/runs", headers=headers, json=payload())
        assert result.status_code == 202
        await poll(client, headers, result)
        assert (
            await client.post("/api/replay/runs", headers=headers, json=payload("another"))
        ).status_code == 429
        now[0] = 901
        assert (
            await client.get("/api/replay/runs/" + result.json()["run_id"], headers=headers)
        ).status_code == 401
        assert (
            await client.post("/api/replay/runs", headers=headers, json=payload())
        ).status_code == 401
        await visitor(client)  # Expiry frees bounded visitor metadata.


async def test_concurrent_retry_admission_and_timeout(factory, tmp_path):
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class SlowRunner:
        async def execute(self, context):
            entered.set()
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()

    async with factory(
        SlowRunner(), Limits(max_concurrent_runs=1, run_timeout_seconds=0.1)
    ) as client:
        headers = await visitor(client)
        # Response arrives before the runner finishes; no proxy-long request.
        started = await asyncio.wait_for(
            client.post("/api/replay/runs", headers=headers, json=payload()), timeout=0.05
        )
        assert started.status_code == 202
        await entered.wait()
        status = await client.get("/api/replay/runs/" + started.json()["run_id"], headers=headers)
        assert status.json()["state"] == "running"
        retry = await client.post("/api/replay/runs", headers=headers, json=payload())
        assert retry.status_code == 202
        assert (
            await client.post("/api/replay/runs", headers=headers, json=payload("second"))
        ).status_code == 429
        result = await poll(client, headers, started)
        assert result.status_code == 200
        assert result.json()["error"] == "run_timeout"
        assert result.json()["run_id"] == retry.json()["run_id"]
        assert cancelled.is_set()
        assert list((tmp_path / "runs").iterdir()) == []


async def test_runner_errors_are_sanitized(factory):
    class BrokenRunner:
        async def execute(self, context):
            raise RuntimeError("private filesystem and token details")

    async with factory(BrokenRunner()) as client:
        headers = await visitor(client)
        result = await client.post("/api/replay/runs", headers=headers, json=payload())
        result = await poll(client, headers, result)
        assert result.status_code == 200
        assert result.json()["error"] == "runner_failed"
        assert "private" not in result.text


async def test_expiry_during_execution_withholds_result(factory, tmp_path):
    now = [0]

    class ExpiringRunner:
        async def execute(self, context):
            now[0] = 901
            return "completed"

    async with factory(ExpiringRunner(), clock=lambda: now[0]) as client:
        headers = await visitor(client)
        result = await client.post("/api/replay/runs", headers=headers, json=payload())
        result = await poll(client, headers, result)
        assert result.status_code == 401
        assert "run_id" not in result.json()
        assert list((tmp_path / "runs").iterdir()) == []


async def test_failed_retries_do_not_execute_again(factory):
    class InvalidRunner:
        calls = 0

        async def execute(self, context):
            self.calls += 1
            return {"private": "not an allowed outcome"}

    runner = InvalidRunner()
    async with factory(runner) as client:
        headers = await visitor(client)
        first = await client.post("/api/replay/runs", headers=headers, json=payload())
        first = await poll(client, headers, first)
        second = await client.post("/api/replay/runs", headers=headers, json=payload())
        assert first.status_code == 200
        assert second.status_code == 503
        assert first.json() == second.json()
        assert runner.calls == 1
        assert "private" not in first.text
        assert first.headers["cache-control"] == "no-store"


async def test_same_origin_browser_get_without_origin(factory):
    async with factory(StubRunner()) as client:
        first, second = await visitor(client), await visitor(client)
        result = await client.post("/api/replay/runs", headers=first, json=payload())
        path = "/api/replay/runs/" + result.json()["run_id"]
        del client.headers["origin"]  # Typical browser same-origin GET headers.
        assert (await client.get("/api/replay/fixtures")).status_code == 200
        assert (await client.get(path, headers=first)).status_code == 200
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers=second)).status_code == 404
        foreign = {**first, "origin": "https://foreign.example"}
        assert (await client.get(path, headers=foreign)).status_code == 403
        assert (await client.get("/api/replay/fixtures", headers=foreign)).status_code == 403


@pytest.mark.parametrize("origin", [None, "null", "https://foreign.example", ""])
async def test_mutations_always_require_exact_origin(factory, origin):
    runner = StubRunner()
    async with factory(runner) as client:
        headers = await visitor(client)
        del client.headers["origin"]
        if origin is not None:
            headers["origin"] = origin
        assert (await client.post("/api/replay/visitors", headers=headers)).status_code == 403
        result = await client.post("/api/replay/runs", headers=headers, json=payload())
        assert result.status_code == 403
        assert runner.contexts == []


async def test_shutdown_cancels_drains_and_cleans(factory, tmp_path):
    entered = asyncio.Event()
    drained = asyncio.Event()

    class ShutdownRunner:
        async def execute(self, context):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                # Shutdown must await runner teardown, not just request cancellation.
                await asyncio.sleep(0.01)
                drained.set()

    client = factory(ShutdownRunner())
    app = client._transport.app
    async with client:
        async with app.router.lifespan_context(app):
            headers = await visitor(client)
            response = await client.post("/api/replay/runs", headers=headers, json=payload())
            assert response.status_code == 202
            await entered.wait()
            assert not drained.is_set()
        assert drained.is_set()
        assert list((tmp_path / "runs").iterdir()) == []
        assert (await client.post("/api/replay/visitors")).status_code == 503
        path = "/api/replay/runs/" + response.json()["run_id"]
        assert (await client.get(path, headers=headers)).status_code == 401


def schema_result(**updates):
    """A schema-valid test double, NOT evidence of real pipeline execution."""
    from pex_bridge.replay_job import ReplayJobResult

    fields = {
        "fixture_id": "premature_stop_eval",
        "completion_status": "verified_complete",
        "completion_reason": "test double only",
        "claim_verdicts": [{"claim": "Fixture test claim", "status": "supported"}],
        "evidence_summary": ["test double evidence"],
        "verification_sequence": [{"status": "supported", "modified_acceptance_files": []}],
        "interventions": ["NOOP"],
        "events_adjudicated": 1,
        "claims_adjudicated": 1,
        "integrity_incidents": 0,
        "declared_expectation_met": True,
    }
    return ReplayJobResult.model_validate({**fields, **updates})


async def test_bounded_result_transport_and_ownership(factory):
    from pex_bridge.replay_job import MAX_RESULT_BYTES, encode_result

    result = schema_result()

    class ResultRunner:
        async def execute(self, context):
            return result

    async with factory(ResultRunner()) as client:
        first, second = await visitor(client), await visitor(client)
        started = await client.post("/api/replay/runs", headers=first, json=payload())
        status = await poll(client, first, started)
        assert status.json()["state"] == "completed"
        assert "result_json" not in status.json()
        path = "/api/replay/runs/" + started.json()["run_id"] + "/result"
        response = await client.get(path, headers=first)
        assert response.status_code == 200
        assert response.content == encode_result(result)
        assert len(response.content) <= MAX_RESULT_BYTES
        assert response.headers["cache-control"] == "no-store"
        assert (await client.get(path, headers=second)).status_code == 404
        assert (await client.get(path)).status_code == 401
        # Serialization is a snapshot, not a retained mutable result object.
        result.completion_reason = "mutated after admission"
        assert (await client.get(path, headers=first)).content == response.content


@pytest.mark.parametrize(
    "invalid",
    [
        "dictionary",
        "oversize",
        "fixture",
        "replay",
        "not_live",
        "numeric_label",
        "inference",
        "execution",
        "shape",
        "completion_status",
        "claim_status",
        "verification_status",
    ],
)
async def test_invalid_results_fail_closed(factory, invalid):
    result = schema_result()
    if invalid == "dictionary":
        result = result.model_dump()
    elif invalid == "oversize":
        result = schema_result(
            verification_sequence=[
                {"status": "uncertain", "modified_acceptance_files": ["x" * 240] * 16}
            ]
            * 16
        )
    elif invalid == "claim_status":
        result.claim_verdicts[0].status = "approved_without_checks"
    elif invalid == "verification_status":
        result.verification_sequence[0].status = "approved_without_checks"
    else:
        field, value = {
            "fixture": ("fixture_id", "tampered_acceptance_eval"),
            "replay": ("replay", False),
            "numeric_label": ("replay", 1),
            "not_live": ("not_live_control", False),
            "inference": ("inference_status", "attempted"),
            "execution": ("execution_mode", "live"),
            "shape": ("events_adjudicated", "not an integer"),
            "completion_status": ("completion_status", "approved_without_checks"),
        }[invalid]
        setattr(result, field, value)  # Boundary must revalidate, not trust the model instance.

    class InvalidResultRunner:
        async def execute(self, context):
            return result

    async with factory(InvalidResultRunner()) as client:
        headers = await visitor(client)
        started = await client.post("/api/replay/runs", headers=headers, json=payload())
        status = await poll(client, headers, started)
        assert status.json()["state"] == "failed"
        assert status.json()["error"] == "runner_failed"
        response = await client.get(
            "/api/replay/runs/" + started.json()["run_id"] + "/result", headers=headers
        )
        assert response.status_code == 409
        assert response.json() == {"detail": "run_failed"}


async def test_result_pending_status_only_and_expired(factory):
    release = asyncio.Event()
    now = [0]

    class DelayedStatusRunner:
        async def execute(self, context):
            await release.wait()
            return "completed"

    async with factory(DelayedStatusRunner(), clock=lambda: now[0]) as client:
        headers = await visitor(client)
        started = await client.post("/api/replay/runs", headers=headers, json=payload())
        path = "/api/replay/runs/" + started.json()["run_id"] + "/result"
        pending = await client.get(path, headers=headers)
        assert pending.status_code == 202
        assert pending.json() == {"detail": "result_pending"}
        release.set()
        await poll(client, headers, started)
        no_result = await client.get(path, headers=headers)
        assert no_result.status_code == 404
        assert no_result.json() == {"detail": "result_unavailable"}
        now[0] = 901
        expired = await client.get(path, headers=headers)
        assert expired.status_code == 401


async def test_expired_result_cannot_be_read(factory):
    now = [0]

    class ResultRunner:
        async def execute(self, context):
            return schema_result()

    async with factory(ResultRunner(), clock=lambda: now[0]) as client:
        headers = await visitor(client)
        started = await client.post("/api/replay/runs", headers=headers, json=payload())
        await poll(client, headers, started)
        path = "/api/replay/runs/" + started.json()["run_id"] + "/result"
        assert (await client.get(path, headers=headers)).status_code == 200
        now[0] = 901
        assert (await client.get(path, headers=headers)).status_code == 401


async def test_exhausted_visitor_quota_is_not_transient_or_requeued(factory):
    runner = StubRunner()
    async with factory(runner, Limits(max_runs_per_visitor=1)) as client:
        headers = await visitor(client)
        started = await client.post("/api/replay/runs", headers=headers, json=payload())
        completed = await poll(client, headers, started)
        assert completed.json()["state"] == "completed"
        assert len(runner.contexts) == 1
        # Completion releases concurrency, not this visitor's lifetime quota.
        for key in ("second", "second", "third"):
            denied = await client.post("/api/replay/runs", headers=headers, json=payload(key))
            assert denied.status_code == 429
            assert denied.json() == {"detail": "visitor_run_limit"}
        retry = await client.post("/api/replay/runs", headers=headers, json=payload())
        assert retry.status_code == 200
        assert retry.json() == completed.json()
        assert len(runner.contexts) == 1  # No queue, new job, restart or hidden visitor reset.
