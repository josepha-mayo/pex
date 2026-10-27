"""Authored responses only, in a new process initialized before framework import."""

import json
import sqlite3

import pytest
from accounting import Ledger as RealLedger
from managed_chat import Limits, Refusal, Route
from process_adapter import fixture_model, invoke_live
from test_managed_chat import ENDPOINT, MODEL, response
from test_managed_chat import no_network as no_network  # noqa: PLC0414
from test_managed_chat import rig as rig  # noqa: PLC0414
from test_tool_protocol import (
    InterventionType,
    ProposedAction,
    final_arguments,
    request_fixture,
)
from test_tool_transport import payload


def Ledger(
    path,
    *,
    budget,
    input_rate,
    output_rate,
    route=None,
    currency="USD",
    provenance="a" * 64,
):
    """Explicitly authored pricing fixture; never a fetched/authorized rate."""
    return RealLedger(
        path,
        budget=budget,
        input_rate=input_rate,
        output_rate=output_rate,
        route=route
        or Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000)),
        currency=currency,
        pricing_provenance_sha256=provenance,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["planner", "verifier"])
async def test_real_owned_tools_with_durable_wire_receipts(tmp_path, rig, role):
    request = request_fixture(with_boundaries=True)
    proposal = (
        ProposedAction(
            type=InterventionType.NOOP,
            session_id=request.session.id,
            goal_id=request.goal.id,
            rationale="Authored fixture",
        )
        if role == "verifier"
        else None
    )
    ledger = Ledger(
        tmp_path / "ledger.sqlite",
        budget=100000,
        input_rate=2,
        output_rate=3,
        route=Route(ENDPOINT, MODEL, role, Limits(max_usage_tokens=10000)),
    )
    model = fixture_model(
        Route(ENDPOINT, MODEL, role, Limits(max_usage_tokens=10000)),
        request,
        invocation_id="process-fixture-" + role,
        ledger=ledger,
        proposal=proposal,
    )

    def handle(wire):
        # Commit is visible through an independent SQLite connection before send.
        import sqlite3

        with sqlite3.connect(tmp_path / "ledger.sqlite") as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM calls WHERE state='reserved_uncertain'"
                ).fetchone()[0]
                == 1
            )
        if len(rig.calls) == 1:
            return response(payload("get_goal", '{"boundary_page":0}'))
        return response(
            payload(
                model.protocol.final_name,
                json.dumps(final_arguments(role)),
                "final_call",
            )
        )

    rig.handler = handle
    result = await model.invoke_async()
    assert result.structured_output is not None
    assert len(model.observations) == 1 and len(rig.calls) == 2
    assert len(model.protocol.system_prompt) > 2000
    assert all(
        row["state"] == "settled_raw_wire" and row["charged"] == 33
        for row in ledger.summary()
    )
    ledger.close()
    reopened = Ledger(
        tmp_path / "ledger.sqlite",
        budget=100000,
        input_rate=2,
        output_rate=3,
        route=Route(ENDPOINT, MODEL, role, Limits(max_usage_tokens=10000)),
    )
    assert len(reopened.summary()) == 2
    reopened.close()
    with pytest.raises(Exception, match="reuse"):
        await model.invoke_async()


@pytest.mark.asyncio
async def test_429_retains_reservation_no_retry(tmp_path, rig):
    ledger = Ledger(
        tmp_path / "ledger.sqlite", budget=30000, input_rate=2, output_rate=3
    )
    model = fixture_model(
        Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000)),
        request_fixture(with_boundaries=True),
        invocation_id="uncertain-call",
        ledger=ledger,
    )
    rig.handler = lambda request: response(status=429)
    with pytest.raises(Refusal, match="managed_transport_not_validated"):
        await model.invoke_async()
    assert len(rig.calls) == 1
    assert ledger.summary()[0]["charged"] == 30000
    assert ledger.summary()[0]["state"] == "uncertain"
    ledger.close()


@pytest.mark.asyncio
async def test_budget_refusal_before_transport(tmp_path, rig):
    ledger = Ledger(tmp_path / "ledger.sqlite", budget=1, input_rate=2, output_rate=3)
    model = fixture_model(
        Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000)),
        request_fixture(with_boundaries=True),
        invocation_id="budget-call",
        ledger=ledger,
    )
    with pytest.raises(ValueError, match="budget reservation refused"):
        await model.invoke_async()
    assert not rig.calls and not rig.created
    ledger.close()


def test_crash_reservation_survives_reopen(tmp_path):
    path = tmp_path / "ledger.sqlite"
    ledger = Ledger(path, budget=30000, input_rate=2, output_rate=3)
    route = Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000))
    ledger.reserve("crashed-call", route)
    ledger.close()
    ledger = Ledger(path, budget=30000, input_rate=2, output_rate=3)
    assert ledger.summary()[0]["charged"] == 30000
    with pytest.raises(ValueError):
        ledger.reserve("new-call", route)
    ledger.close()


def test_live_entry_refused():
    with pytest.raises(RuntimeError, match="not_admitted"):
        invoke_live()


def test_ledger_identity_and_reuse_refused(tmp_path):
    from dataclasses import replace

    from managed_chat import Receipt, Usage

    path = tmp_path / "ledger.sqlite"
    ledger = Ledger(path, budget=60000, input_rate=2, output_rate=3)
    route = Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000))
    ledger.reserve("call", route)
    assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(sqlite3.IntegrityError):
        ledger.reserve("call", route)
    receipt = Receipt(
        "call",
        route.fingerprint,
        MODEL,
        "planner",
        attempts=1,
        http_status=200,
        dispatch_state="response_complete",
        outcome="succeeded",
        usage=Usage(12, 3, 15),
    )
    with pytest.raises(ValueError):
        ledger.settle("call", replace(receipt, route_fingerprint="wrong"))
    assert ledger.summary()[0]["charged"] == 30000
    ledger.settle("call", receipt)
    with pytest.raises(ValueError):
        ledger.settle("call", receipt)
    ledger.close()
    with pytest.raises(ValueError):
        Ledger(path, budget=60001, input_rate=2, output_rate=3)


def test_sdk_telemetry_cannot_settle_wire_receipt(tmp_path):
    ledger = Ledger(
        tmp_path / "ledger.sqlite", budget=30000, input_rate=2, output_rate=3
    )
    route = Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000))
    ledger.reserve("call", route)
    with pytest.raises(ValueError):
        ledger.settle("call", {"usage": {"input_tokens": 12, "output_tokens": 3}})
    assert ledger.summary()[0]["charged"] == 30000
    ledger.close()


def test_late_telemetry_initialization_refused():
    from process_adapter import initialize_process

    with pytest.raises(RuntimeError, match="precede"):
        initialize_process()


def test_nonfixture_route_refused(tmp_path):
    ledger = Ledger(
        tmp_path / "ledger.sqlite", budget=30000, input_rate=2, output_rate=3
    )
    with pytest.raises(RuntimeError, match="fixture route"):
        fixture_model(
            Route("https://example.com/v1/chat/completions", MODEL, "planner"),
            request_fixture(with_boundaries=True),
            invocation_id="invalid",
            ledger=ledger,
        )
    assert ledger.summary() == []
    ledger.close()


@pytest.mark.parametrize("value", [None, -1, "1", "oops", 1.5])
def test_corrupt_charges_fail_closed(tmp_path, value):
    path = tmp_path / "ledger.sqlite"
    ledger = Ledger(path, budget=60000, input_rate=2, output_rate=3)
    route = Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000))
    ledger.reserve("call", route)
    # Simulate storage corruption/legacy DB with constraints bypassed.
    ledger.db.execute("PRAGMA ignore_check_constraints=ON")
    ledger.db.execute("UPDATE calls SET charged=?", (value,))
    with pytest.raises(ValueError):
        ledger.reserve("next", route)
    ledger.close()
    with pytest.raises(ValueError):
        Ledger(path, budget=60000, input_rate=2, output_rate=3)


def test_concurrent_stale_settlement_cannot_overwrite(tmp_path):
    from dataclasses import replace

    from managed_chat import Receipt, Usage

    path = tmp_path / "ledger.sqlite"
    first = Ledger(path, budget=60000, input_rate=2, output_rate=3)
    second = Ledger(path, budget=60000, input_rate=2, output_rate=3)
    route = Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000))
    first.reserve("call", route)
    receipt = Receipt(
        "call",
        route.fingerprint,
        MODEL,
        "planner",
        attempts=1,
        http_status=200,
        dispatch_state="response_complete",
        outcome="succeeded",
        usage=Usage(12, 3, 15),
    )
    original = first.db

    class InterleavedConnection:
        fired = False

        def execute(self, sql, args=()):
            if sql.startswith("UPDATE calls SET charged") and not self.fired:
                self.fired = True
                second.settle("call", receipt)
            return original.execute(sql, args)

    first.db = InterleavedConnection()
    with pytest.raises(ValueError, match="concurrently"):
        first.settle("call", replace(receipt, usage=Usage(1, 1, 2)))
    assert second.summary()[0]["charged"] == 33
    first.db = original
    first.close()
    second.close()


def test_schema_rejects_invalid_charge(tmp_path):
    ledger = Ledger(
        tmp_path / "ledger.sqlite", budget=60000, input_rate=2, output_rate=3
    )
    route = Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000))
    ledger.reserve("call", route)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.db.execute("UPDATE calls SET charged=-1")
    with pytest.raises(sqlite3.IntegrityError):
        ledger.db.execute("UPDATE calls SET charged=NULL")
    ledger.close()


@pytest.mark.parametrize(
    "change",
    [
        {"model_id": "fixture/expensive-other-model"},
        {"endpoint": "https://different.invalid/v1/chat/completions"},
        {"role": "verifier"},
        {"limits": Limits(max_usage_tokens=20000)},
    ],
)
def test_different_route_cannot_reuse_pricing(tmp_path, change):
    from dataclasses import replace

    route = Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000))
    ledger = Ledger(
        tmp_path / "ledger.sqlite",
        budget=60000,
        input_rate=2,
        output_rate=3,
        route=route,
    )
    with pytest.raises(ValueError, match="pinned pricing"):
        ledger.reserve("call", replace(route, **change))
    assert ledger.summary() == []
    ledger.close()


@pytest.mark.parametrize(
    "change",
    [
        {"currency": "EUR"},
        {"provenance": "b" * 64},
        {
            "route": Route(
                ENDPOINT,
                "fixture/expensive-other-model",
                "planner",
                Limits(max_usage_tokens=10000),
            )
        },
    ],
)
def test_reopen_pricing_identity_mismatch_refused(tmp_path, change):
    path = tmp_path / "ledger.sqlite"
    ledger = Ledger(path, budget=60000, input_rate=2, output_rate=3)
    ledger.close()
    with pytest.raises(ValueError, match="identity changed"):
        Ledger(path, budget=60000, input_rate=2, output_rate=3, **change)


def test_stored_pricing_provenance_corruption_refused(tmp_path):
    path = tmp_path / "ledger.sqlite"
    ledger = Ledger(path, budget=60000, input_rate=2, output_rate=3)
    ledger.db.execute("UPDATE pricing_identity SET currency='EUR'")
    with pytest.raises(ValueError, match="corrupt"):
        ledger.reserve(
            "call", Route(ENDPOINT, MODEL, "planner", Limits(max_usage_tokens=10000))
        )
    ledger.close()
    with pytest.raises(ValueError, match="identity changed"):
        Ledger(path, budget=60000, input_rate=2, output_rate=3)


@pytest.mark.parametrize(
    "change", [{"currency": ""}, {"currency": "usd"}, {"provenance": "unverified"}]
)
def test_invalid_pricing_identity_refused_before_file(tmp_path, change):
    path = tmp_path / "ledger.sqlite"
    with pytest.raises(ValueError):
        Ledger(path, budget=60000, input_rate=2, output_rate=3, **change)
    assert not path.exists()

# Split-envelope tests are authored accounting checks: no provider calls.
def split_route():
    return Route(
        "https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions",
        "nvidia/nemotron-3-super-120b-a12b", "planner",
        Limits(max_output_tokens=4096, max_usage_tokens=266240),
    )


def split_ledger(path, **changes):
    args = dict(budget=250000000, input_rate=300, output_rate=900,
                route=split_route(), currency="USD",
                pricing_provenance_sha256="c" * 64,
                input_token_bound=262144, output_token_bound=4096)
    args.update(changes)
    return RealLedger(path, **args)


def split_receipt(call_id, input_tokens=1000, output_tokens=100):
    from managed_chat import Receipt, Usage
    route = split_route()
    return Receipt(call_id, route.fingerprint, route.model_id, route.role,
                   attempts=1, http_status=200, dispatch_state="response_complete",
                   outcome="succeeded", usage=Usage(input_tokens, output_tokens,
                                                   input_tokens + output_tokens))


def test_six_small_settlements_fit_quarter_dollar(tmp_path):
    path = tmp_path / "split.sqlite"
    ledger = split_ledger(path)
    for index in range(6):
        call = f"small-{index}"
        ledger.reserve(call, split_route())
        assert ledger.summary()[-1]["reserved"] == 82329600
        ledger.settle(call, split_receipt(call))
    assert sum(row["charged"] for row in ledger.summary()) == 2340000
    assert all(row["state"] == "settled_raw_wire" for row in ledger.summary())
    ledger.close()
    reopened = split_ledger(path)
    assert len(reopened.summary()) == 6
    reopened.close()


@pytest.mark.parametrize("uncertain", [True, False])
def test_three_full_reservations_refuse_fourth_before_dispatch(tmp_path, uncertain):
    ledger = split_ledger(tmp_path / "split.sqlite")
    for index in range(3):
        call = f"large-{index}"
        ledger.reserve(call, split_route())
        ledger.settle(call, None if uncertain else split_receipt(call, 262144, 4096))
    assert sum(row["charged"] for row in ledger.summary()) == 246988800
    with pytest.raises(ValueError, match="budget reservation refused"):
        ledger.reserve("fourth", split_route())
    assert len(ledger.summary()) == 3
    ledger.close()


def test_concurrent_split_reservations_never_exceed_ceiling(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    path = tmp_path / "split.sqlite"
    initial = split_ledger(path)
    initial.close()
    barrier = Barrier(6)
    def attempt(index):
        ledger = split_ledger(path)
        try:
            barrier.wait(timeout=10)
            try:
                ledger.reserve(f"parallel-{index}", split_route())
                return True
            except ValueError as exc:
                assert str(exc) == "budget reservation refused"
                return False
        finally:
            ledger.close()
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(attempt, range(6))) == 3
    ledger = split_ledger(path)
    assert sum(row["charged"] for row in ledger.summary()) == 246988800
    ledger.close()


@pytest.mark.parametrize("change", [
    {"input_rate": 301}, {"output_rate": 899}, {"currency": "EUR"},
    {"input_token_bound": 200000}, {"output_token_bound": 4095},
    {"input_token_bound": None}, {"output_token_bound": None},
])
def test_split_profile_mismatch_refused_before_storage(tmp_path, change):
    path = tmp_path / "split.sqlite"
    with pytest.raises(ValueError, match="pinned Nebius"):
        split_ledger(path, **change)
    assert not path.exists()


@pytest.mark.parametrize("change", [
    {"endpoint": "https://api.tokenfactory.nebius.com/v1/chat/completions"},
    {"model_id": "nvidia/other-model"}, {"output_field": "max_tokens"},
    {"limits": Limits(max_output_tokens=512)},
])
def test_split_route_mismatch_refused(tmp_path, change):
    from dataclasses import replace
    with pytest.raises(ValueError, match="pinned Nebius"):
        split_ledger(tmp_path / "split.sqlite", route=replace(split_route(), **change))


@pytest.mark.parametrize("counts", [(262145, 0), (0, 4097)])
def test_split_usage_bounds_reject_even_when_cost_fits(tmp_path, counts):
    ledger = split_ledger(tmp_path / "split.sqlite")
    ledger.reserve("call", split_route())
    with pytest.raises(ValueError, match="split token envelope"):
        ledger.settle("call", split_receipt("call", *counts))
    assert ledger.summary()[0]["charged"] == 82329600
    assert ledger.summary()[0]["state"] == "reserved_uncertain"
    ledger.close()


def test_split_envelope_persisted_and_corruption_refused(tmp_path):
    path = tmp_path / "split.sqlite"
    ledger = split_ledger(path)
    ledger.db.execute("UPDATE reservation_identity SET input_bound=1")
    with pytest.raises(ValueError, match="envelope corrupt"):
        ledger.reserve("call", split_route())
    ledger.close()
    with pytest.raises(ValueError, match="envelope identity changed"):
        split_ledger(path)
