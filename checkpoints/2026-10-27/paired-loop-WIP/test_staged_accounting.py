"""Synthetic closed grant/cumulative ledgers; no provider or real runtime evidence."""
import json
from pathlib import Path
import pytest
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
import staged_admission as a
from staged_accounting import *
from worker_funding import RESERVATION,WorkerBudgetExhausted,MODEL as WORKER_MODEL

@pytest.fixture
def funded(bound,monkeypatch):
    scope,compute,wire,pools,behavior=bound
    # Build a fresh synthetic immutable grant before entering its atomic scope.
    cfg=scope.cfg;cfg['profile']['equal_worker_fresh']=360000000
    cfg['profile']['supervisor_fresh']=SUPERVISOR_FRESH
    p=Path(cfg['predecessor']['path']);prior=json.loads(p.read_bytes());prior['provider_nano_usd']=SUPERVISOR_PRIOR+100
    p.write_bytes(canonical(prior));cfg['predecessor']['sha256']=sha(p.read_bytes())
    # New compute object must carry the exact new synthetic predecessor pin.
    from cumulative_compute import ComputeBudget
    compute.close();Path(p.parent/'compute.sqlite').unlink()
    compute=ComputeBudget(p.parent/'compute.sqlite',prior_upper_bound_nano_usd=100,evidence_sha256=cfg['predecessor']['sha256'])
    raw=canonical(cfg);Path(scope.admitted.grant.config_path).write_bytes(raw)
    from dataclasses import replace
    grant=replace(scope.admitted.grant,config_sha256=sha(raw),profile_sha256=sha(canonical(cfg['profile'])),predecessor_sha256=cfg['predecessor']['sha256'])
    monkeypatch.setattr(a,'APPROVED_STAGED_GRANT',a.GrantGate.identity(grant))
    replacement=SDKTransportBinding(a.load(grant),compute)
    with replacement:
        bundle=StagedAccounting(replacement)
        try:yield bundle,replacement
        finally:bundle.close();compute.close()

def request():
    raw=canonical({'model':WORKER_MODEL,'messages':[{'role':'user','content':'AUTHORED'}],
        'max_completion_tokens':4096,'tools':[{'type':'function','function':{'name':'pex_remote_run'}}]})
    return sha(raw),raw

def test_closed_before_accounting_files():
    with pytest.raises(AdmissionRefused):StagedAccounting(None)

def test_equal_fresh_and_unknown_liabilities_count_once(funded):
    bundle,scope=funded;digest,raw=request()
    bundle.workers['baseline'].reserve('authored-one',digest,raw)
    summary=bundle.summary()
    assert summary['worker_fresh_nano_usd']=={'baseline':RESERVATION,'pex':0}
    assert summary['provider_cumulative_nano_usd']==SUPERVISOR_PRIOR+100+RESERVATION
    with pytest.raises(WorkerBudgetExhausted):bundle.workers['baseline'].reserve('authored-two',digest,raw)
    bundle.workers['pex'].reserve('authored-pex-one',digest,raw)
    assert bundle.summary()['provider_cumulative_nano_usd']==SUPERVISOR_PRIOR+100+2*RESERVATION
    assert not scope.creates

def test_supervisor_shared_attempts_separate_fresh_overhead(funded):
    bundle,scope=funded
    bundle.supervisor_ledger.reserve('authored-planner',bundle.routes[0])
    bundle.supervisor_ledger.reserve('authored-verifier',bundle.routes[1])
    s=bundle.summary()
    assert s['supervisor_wire_attempts']==2
    assert s['supervisor_fresh_overhead_nano_usd']==2*bundle.supervisor.reservation
    assert s['provider_cumulative_nano_usd']==SUPERVISOR_PRIOR+100+2*bundle.supervisor.reservation

def test_revocation_blocks_reserve_without_refunding_unknown(funded,monkeypatch):
    bundle,scope=funded;digest,raw=request()
    bundle.workers['baseline'].reserve('authored-one',digest,raw)
    monkeypatch.setattr(a,'APPROVED_STAGED_GRANT',None)
    with pytest.raises(AdmissionRefused):bundle.workers['pex'].reserve('authored-two',digest,raw)
    assert bundle.summary()['worker_fresh_nano_usd']['baseline']==RESERVATION

def test_metadata_mutation_and_reopen_refused(funded):
    bundle,scope=funded
    with pytest.raises(FileExistsError):StagedAccounting(scope)
    bundle.identity_path.write_bytes(b'changed')
    with pytest.raises(AdmissionRefused):bundle.workers['baseline'].reserve('a',*request())


@pytest.mark.asyncio
async def test_worker_RPC_thread_never_reads_owner_thread_supervisor_DB(funded):
    import asyncio
    bundle,scope=funded
    digest,raw=request()
    await asyncio.to_thread(bundle.workers['baseline'].reserve,'thread-authored',digest,raw)
    assert bundle.summary()['worker_fresh_nano_usd']['baseline']==RESERVATION
