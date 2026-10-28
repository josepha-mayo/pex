"""Authored terminal-accounting regressions only. No provider, VM or real CLI."""
import asyncio
from types import SimpleNamespace
import pytest
from controller import Budget,WorkerBudgetTerminal,run_pair
from budget_rpc import FundingChannel
import nebius_worker as cw
from worker_funding import WorkerBudgetExhausted
from test_worker_funding import ledger,request,stream,usage
from test_loop import Worker,Grade,Review,arms


def settle(db,call):
    raw,digest=request();db.reserve(call,digest,raw)
    db.settle_raw(call,digest,200,'text/event-stream',stream(used={'prompt_tokens':11,'completion_tokens':1,'total_tokens':12}))


def test_ledger_snapshot_counts_own_arm_and_keeps_unknown_tokens_explicit(tmp_path):
    path=tmp_path/'funding.sqlite';db=ledger(path)
    try:
        settle(db,'known');raw,digest=request();db.reserve('unknown',digest,raw)
        assert db.usage_snapshot()==dict(calls=2,input_tokens=11,output_tokens=1,uncertain_calls=1)
        other=ledger(path,'pex')
        try:assert other.usage_snapshot()==dict(calls=0,input_tokens=0,output_tokens=0,uncertain_calls=0)
        finally:other.close()
    finally:db.close()


def test_actual_worker_exception_retains_only_failed_turn_delta_and_active_time(tmp_path,monkeypatch):
    db=ledger(tmp_path/'funding.sqlite','pex');channel=FundingChannel()
    settle(db,'previous-0');settle(db,'previous-1')
    worker=object.__new__(cw.NebiusCLIWorker);worker.funding={'pex':db}
    worker.staged_binding=None  # Match __init__'s legacy default; no staged authority.
    worker.states={'pex':{'profile':tmp_path,'case':tmp_path,'stopped':False,'seq':0,'funding_channel':channel}}
    worker._start=lambda c:None;worker.binary=tmp_path/'never-executed'
    monkeypatch.setattr(cw,'prior_sequence',lambda *a:0)
    ticks=iter([100,100.1,101.25]);monkeypatch.setattr(cw,'time',SimpleNamespace(monotonic=lambda:next(ticks)))
    async def failed_cli(**kwargs):
        for i in range(10):settle(db,'current-'+str(i))
        raw,digest=request()
        try:db.reserve('refused-13th',digest,raw)
        except WorkerBudgetExhausted as error:channel.last_error=error
        else:raise AssertionError('cap must refuse')
        raise RuntimeError('authored CLI terminal')
    monkeypatch.setattr(cw,'run_turn',failed_cli)
    try:
        with pytest.raises(WorkerBudgetTerminal) as caught:
            asyncio.run(worker.turn({'condition':'pex'},prompt='authored',session_id=None,remaining={'active_seconds':180}))
        assert caught.value.code=='worker_attempt_cap_refused'
        assert caught.value.usage==dict(calls=10,input_tokens=110,output_tokens=10,uncertain_calls=0)
        assert caught.value.worker_active_seconds==1.25
        assert db.usage_snapshot()['calls']==12
    finally:db.close()


def test_first_turn_exhaustion_reports_24_attempts_not_zero():
    class Exhausted(Worker):
        async def turn(self,*a,**kw):
            raise WorkerBudgetTerminal('worker_attempt_cap_refused',usage=dict(calls=12,input_tokens=1234,output_tokens=567,uncertain_calls=0),worker_active_seconds=79.25)
    w=Exhausted();report=asyncio.run(run_pair(arms(),w,Review(),Grade(w),budget=Budget(calls=12,input_tokens=None,output_tokens=49152,active_seconds=180),mode='live-pilot',admission=SimpleNamespace(authorize=lambda *a:True)))
    assert report['real_worker_inference_calls']==report['real_worker_request_attempts']==24
    for s in report['arms'].values():
        assert s['calls']==12 and s['input_tokens']==1234 and s['output_tokens']==567
        assert s['worker_active_seconds']==79.25 and s['worker_active_time_exact']
        assert s['status']=='worker_budget_terminal_inconclusive' and not s['reviews']
    assert w.cleaned


def test_continuation_partial_usage_adds_to_prior_turn_without_double_counting():
    class Continuation(Worker):
        def __init__(self):super().__init__();self.seen=set()
        async def turn(self,arm,**kw):
            c=arm['workspace']
            if c in self.seen:
                raise WorkerBudgetTerminal('worker_attempt_cap_refused',usage=dict(calls=11,input_tokens=110,output_tokens=22,uncertain_calls=0),worker_active_seconds=7)
            self.seen.add(c)
            return dict(session_id=c,receipt='authored',usage=dict(calls=1,input_tokens=2,output_tokens=3),terminal='natural_stop',public_observation={},worker_active_seconds=2)
    w=Continuation();r=asyncio.run(run_pair(arms(),w,Review(),Grade(w),budget=Budget(calls=12)))
    s=r['arms']['pex'];assert (s['calls'],s['input_tokens'],s['output_tokens'],s['worker_active_seconds'])==(12,112,25,9)
    assert r['arms']['baseline']['calls']==1 and len(s['reviews'])==1


def test_uncertain_wire_preserves_attempts_but_does_not_claim_validated_inference():
    class Unknown(Worker):
        async def turn(self,*a,**kw):raise WorkerBudgetTerminal('worker_budget_reservation_refused',usage=dict(calls=1,input_tokens=0,output_tokens=0,uncertain_calls=1),worker_active_seconds=3)
    w=Unknown();r=asyncio.run(run_pair(arms(),w,Review(),Grade(w),mode='live-pilot',admission=SimpleNamespace(authorize=lambda *a:True)))
    assert r['real_worker_request_attempts']==2 and r['real_worker_inference_calls'] is None
    assert all(s['calls']==1 and not s['worker_token_usage_exact'] and s['worker_uncertain_calls']==1 for s in r['arms'].values())


@pytest.mark.parametrize('duration',[-1,True,float('nan'),float('inf'),10**400,'1'])
def test_invalid_terminal_duration_is_rejected(duration):
    with pytest.raises(ValueError):WorkerBudgetTerminal('worker_attempt_cap_refused',worker_active_seconds=duration)


def test_usage_delta_rejects_regression_or_bool():
    before=dict(calls=1,input_tokens=1,output_tokens=1,uncertain_calls=0)
    with pytest.raises(ValueError):cw.funding_usage_delta(before,{**before,'calls':0})
    with pytest.raises(ValueError):cw.funding_usage_delta(before,{**before,'calls':True})


def test_missing_terminal_receipt_is_explicitly_unknown_not_zero_inference():
    class Missing(Worker):
        async def turn(self,*a,**kw):raise WorkerBudgetTerminal('worker_attempt_cap_refused')
    w=Missing();r=asyncio.run(run_pair(arms(),w,Review(),Grade(w),mode='live-pilot',admission=SimpleNamespace(authorize=lambda *a:True)))
    assert r['real_worker_inference_calls'] is None and r['real_worker_request_attempts'] is None
    assert all(not s['worker_call_count_exact'] and not s['worker_active_time_exact'] for s in r['arms'].values())
