"""Pending proposal arithmetic and pure local ledger tests. No external execution."""
import json
import hashlib
import pytest
import successor_budget as b
import worker_funding as wf
from accounting import Ledger, PilotBudgetExhausted
from successor_supervisor import _routes


def test_exact_total_and_equal_fresh_allowance():
    assert b.WORKER_CUMULATIVE == {'baseline':410081800,'pex':409382800}
    assert b.SUPERVISOR_CUMULATIVE == 1180535400
    assert b.SUPERVISOR_FRESH == 521020500
    assert sum(b.WORKER_CUMULATIVE.values()) + b.SUPERVISOR_CUMULATIVE == 2000000000
    assert all(b.WORKER_CUMULATIVE[a]-b.PRIOR_WORKERS[a]==400000000 for a in b.PRIOR_WORKERS)


def worker(path,arm='baseline',**changes):
    path.parent.chmod(0o700)
    args=dict(arm=arm,approved_config_digest='a'*64,approval_ref='authored',pricing_provenance_sha256=wf.PRICING_SHA,prior_charged_nano_usd=b.PRIOR_WORKERS,predecessor_sha256='b'*64,arm_budget_nano_usd=b.WORKER_SHARED_OUTER,phase_limit_nano_usd=b.WORKER_FRESH)
    args.update(changes)
    return wf._WorkerLedger(path,**args)


def body():
    value=dict(model=wf.MODEL,max_completion_tokens=4096,n=1,stream=True,stream_options={'include_usage':True},messages=[{'role':'user','content':'Authored task'}],tools=[{'type':'function','function':{'name':'pex_remote_run','parameters':{'type':'object'}}}])
    raw=json.dumps(value,separators=(',',':')).encode()
    return raw,hashlib.sha256(raw).hexdigest()


def test_original_approval_cannot_activate_new_worker_profile(tmp_path):
    assert wf.APPROVED_SUCCESSOR_WORKER_REF != wf.APPROVED_WORKER_REF
    with pytest.raises(PermissionError):
        wf.WorkerFunding(tmp_path/'never.sqlite',approval_ref=wf.APPROVED_WORKER_REF,arm_budget_nano_usd=b.WORKER_SHARED_OUTER)
    assert not (tmp_path/'never.sqlite').exists()


@pytest.mark.parametrize('arm',['baseline','pex'])
def test_each_arm_retains_uncertain_reservation_and_cannot_borrow(tmp_path,arm):
    ledger=worker(tmp_path/'worker.sqlite',arm);raw,digest=body()
    ledger.reserve('one',digest,raw)
    with pytest.raises(wf.WorkerBudgetExhausted):ledger.reserve('two',digest,raw)
    assert ledger.summary()['charged_nano_usd'][arm] == b.PRIOR_WORKERS[arm]+wf.RESERVATION
    ledger.close()
    ledger=worker(tmp_path/'worker.sqlite',arm)
    with pytest.raises(wf.WorkerBudgetExhausted):ledger.reserve('two',digest,raw)
    ledger.close()


@pytest.mark.parametrize('changes',[{'phase_limit_nano_usd':400000001},{'prior_charged_nano_usd':{'baseline':0,'pex':0}},{'arm_budget_nano_usd':410081801}])
def test_exact_pending_worker_profile_not_caller_expandable(tmp_path,changes):
    with pytest.raises(ValueError):worker(tmp_path/'worker.sqlite',**changes)


def test_supervisor_six_worst_case_calls_are_separate_and_seventh_refused(tmp_path):
    routes=_routes();args=dict(budget=b.SUPERVISOR_CUMULATIVE,input_rate=300,output_rate=900,route=routes[0],currency='USD',pricing_provenance_sha256='b'*64,input_token_bound=262144,output_token_bound=4096,approved_routes=routes,max_attempts=12,prior_charged_nano_usd=b.PRIOR_SUPERVISOR,predecessor_sha256='c'*64)
    ledger=Ledger(tmp_path/'supervisor.sqlite',**args)
    for i in range(6):ledger.reserve('call-'+str(i),routes[i%2])
    with pytest.raises(PilotBudgetExhausted):ledger.reserve('seventh',routes[0])
    assert sum(row['charged'] for row in ledger.summary()) == 6*82329600
    ledger.close()
    with pytest.raises(ValueError):Ledger(tmp_path/'other.sqlite',**dict(args,prior_charged_nano_usd=0))
