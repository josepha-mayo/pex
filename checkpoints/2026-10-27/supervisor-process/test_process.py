"""Authored responses only, in a new process initialized before framework import."""
import json
import pytest
from test_managed_chat import rig as rig, no_network as no_network, response, ENDPOINT, MODEL
from test_tool_transport import payload
from test_tool_protocol import request_fixture, final_arguments, ProposedAction, InterventionType
from managed_chat import Route, Limits
from accounting import Ledger
from process_adapter import fixture_model, invoke_live


@pytest.mark.asyncio
@pytest.mark.parametrize('role',['planner','verifier'])
async def test_real_owned_tools_with_durable_wire_receipts(tmp_path,rig,role):
    request=request_fixture(with_boundaries=True)
    proposal=ProposedAction(type=InterventionType.NOOP,session_id=request.session.id,goal_id=request.goal.id,rationale='Authored fixture') if role=='verifier' else None
    ledger=Ledger(tmp_path/'ledger.sqlite',budget=100000,input_rate=2,output_rate=3)
    model=fixture_model(Route(ENDPOINT,MODEL,role,Limits(max_usage_tokens=10000)),request,invocation_id='process-fixture-'+role,ledger=ledger,proposal=proposal)
    def handle(wire):
        # Commit is visible through an independent SQLite connection before send.
        import sqlite3
        with sqlite3.connect(tmp_path/'ledger.sqlite') as connection:
            assert connection.execute("SELECT COUNT(*) FROM calls WHERE state='reserved_uncertain'").fetchone()[0]==1
        if len(rig.calls)==1:
            return response(payload('get_goal','{"boundary_page":0}'))
        return response(payload(model.protocol.final_name,json.dumps(final_arguments(role)),"final_call"))
    rig.handler=handle
    result=await model.invoke_async()
    assert result.structured_output is not None
    assert len(model.observations)==1 and len(rig.calls)==2
    assert len(model.protocol.system_prompt)>2000
    assert all(row['state']=='settled_raw_wire' and row['charged']==33 for row in ledger.summary())
    ledger.close()
    reopened=Ledger(tmp_path/'ledger.sqlite',budget=100000,input_rate=2,output_rate=3)
    assert len(reopened.summary())==2
    reopened.close()
    with pytest.raises(Exception,match='reuse'):
        await model.invoke_async()


@pytest.mark.asyncio
async def test_429_retains_reservation_no_retry(tmp_path,rig):
    ledger=Ledger(tmp_path/'ledger.sqlite',budget=30000,input_rate=2,output_rate=3)
    model=fixture_model(Route(ENDPOINT,MODEL,'planner',Limits(max_usage_tokens=10000)),request_fixture(with_boundaries=True),invocation_id='uncertain-call',ledger=ledger)
    rig.handler=lambda request: response(status=429)
    with pytest.raises(Exception): await model.invoke_async()
    assert len(rig.calls)==1
    assert ledger.summary()[0]['charged']==30000
    assert ledger.summary()[0]['state']=='uncertain'
    ledger.close()


@pytest.mark.asyncio
async def test_budget_refusal_before_transport(tmp_path,rig):
    ledger=Ledger(tmp_path/'ledger.sqlite',budget=1,input_rate=2,output_rate=3)
    model=fixture_model(Route(ENDPOINT,MODEL,'planner'),request_fixture(with_boundaries=True),invocation_id='budget-call',ledger=ledger)
    with pytest.raises(Exception): await model.invoke_async()
    assert not rig.calls and not rig.created
    ledger.close()


def test_crash_reservation_survives_reopen(tmp_path):
    path=tmp_path/'ledger.sqlite'
    ledger=Ledger(path,budget=30000,input_rate=2,output_rate=3)
    route=Route(ENDPOINT,MODEL,'planner',Limits(max_usage_tokens=10000))
    ledger.reserve('crashed-call',route);ledger.close()
    ledger=Ledger(path,budget=30000,input_rate=2,output_rate=3)
    assert ledger.summary()[0]['charged']==30000
    with pytest.raises(ValueError): ledger.reserve('new-call',route)
    ledger.close()


def test_live_entry_refused():
    with pytest.raises(RuntimeError,match='not_admitted'): invoke_live()
