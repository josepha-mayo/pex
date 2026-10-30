"""Synthetic closed grant/cumulative ledgers; no provider or real runtime evidence."""
import json
import base64
from pathlib import Path
import pytest
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
import staged_admission as a
from staged_accounting import *
from worker_funding import STAGED_RESERVATION as RESERVATION,WorkerBudgetExhausted,MODEL as WORKER_MODEL

@pytest.fixture
def funded(bound,monkeypatch):
    scope,compute,wire,pools,behavior=bound
    # Build a fresh synthetic immutable grant before entering its atomic scope.
    cfg=scope.cfg;cfg['profile']['equal_worker_fresh']=750000000
    cfg['profile']['worker_output_per_call']=16384
    cfg['profile']['supervisor_fresh']=SUPERVISOR_FRESH
    p=Path(cfg['predecessor']['path']);prior=json.loads(p.read_bytes());is_asyncpool=cfg['run_id'].startswith('asyncpool-staged-pair-');is_wirepool=cfg['run_id'].startswith('wirepool-staged-pair-');prior['provider_nano_usd']=prior['provider_nano_usd'] if is_asyncpool or is_wirepool else SUPERVISOR_PRIOR+100
    p.write_bytes(canonical(prior));cfg['predecessor']['sha256']=sha(p.read_bytes())
    # New compute object must carry the exact new synthetic predecessor pin.
    from cumulative_compute import ComputeBudget
    compute.close();Path(p.parent/'compute.sqlite').unlink()
    compute=ComputeBudget(p.parent/'compute.sqlite',prior_upper_bound_nano_usd=prior['compute_nano_usd'],evidence_sha256=cfg['predecessor']['sha256'],cap_nano_usd=cfg['profile']['compute_cap'],vm_seconds=cfg['profile']['vm_seconds'])
    raw=canonical(cfg);Path(scope.admitted.grant.config_path).write_bytes(raw)
    from dataclasses import replace
    grant=replace(scope.admitted.grant,config_sha256=sha(raw),profile_sha256=sha(canonical(cfg['profile'])),predecessor_sha256=cfg['predecessor']['sha256'])
    monkeypatch.setattr(a,'APPROVED_WIREPOOL_GRANT' if is_wirepool else 'APPROVED_ASYNCPOOL_GRANT' if is_asyncpool else 'APPROVED_STAGED_GRANT',a.GrantGate.identity(grant))
    replacement=SDKTransportBinding(a.load(grant),compute)
    with replacement:
        bundle=StagedAccounting(replacement)
        try:yield bundle,replacement
        finally:bundle.close();compute.close()

def request():
    raw=canonical({'model':WORKER_MODEL,'messages':[{'role':'user','content':'AUTHORED'}],
        'max_completion_tokens':16384,'tools':[{'type':'function','function':{'name':'pex_remote_run'}}]})
    return sha(raw),raw

def test_closed_before_accounting_files():
    with pytest.raises(AdmissionRefused):StagedAccounting(None)

def test_equal_fresh_and_unknown_liabilities_count_once(funded):
    bundle,scope=funded;digest,raw=request()
    bundle.workers['baseline'].reserve('authored-one',digest,raw)
    summary=bundle.summary()
    assert summary['worker_fresh_nano_usd']=={'baseline':RESERVATION,'pex':0}
    assert summary['provider_cumulative_nano_usd']==SUPERVISOR_PRIOR+100+RESERVATION
    bundle.workers['baseline'].reserve('authored-two',digest,raw)
    with pytest.raises(WorkerBudgetExhausted):bundle.workers['baseline'].reserve('authored-three',digest,raw)
    bundle.workers['pex'].reserve('authored-pex-one',digest,raw)
    assert bundle.summary()['provider_cumulative_nano_usd']==SUPERVISOR_PRIOR+100+3*RESERVATION
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
    monkeypatch.setattr(a,'APPROVED_ASYNCPOOL_GRANT' if bundle.cfg['run_id'].startswith('asyncpool-staged-pair-') else 'APPROVED_STAGED_GRANT',None)
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


def test_new_prospective_allocation_preserves_reservations_and_fresh_caps(funded):
    bundle,scope=funded
    assert bundle.fresh==750000000 and SUPERVISOR_FRESH==350000000
    assert all(raw.phase_limit==750000000 and raw.output_token_bound==16384 for raw in bundle.raw_workers.values())
    assert bundle.supervisor.budget==SUPERVISOR_PRIOR+350000000
    assert RESERVATION==334233600 and bundle.supervisor.reservation==82329600
    assert 2212403400+2*750000000+350000000==4062403400<5000000000


@pytest.mark.parametrize('bad_details',[False,True])
def test_new_composition_privately_preserves_exact_wire_and_reason_without_relaxation(funded,bad_details):
    bundle,scope=funded;digest,raw=request();bundle.workers['baseline'].reserve('authored-wire',digest,raw)
    value={'model':WORKER_MODEL,'choices':[{'index':0,'finish_reason':'stop'}],
        'usage':{'prompt_tokens':11,'completion_tokens':1,'total_tokens':12,
            'prompt_tokens_details':{'cached_tokens':12 if bad_details else 0}}}
    body=canonical(value)
    result=bundle.workers['baseline'].settle_raw('authored-wire',digest,200,'application/json',body)
    row=json.loads(bundle.raw_workers['baseline'].db.execute('SELECT receipt FROM calls').fetchone()[0]);p=Path(row['wire_evidence']['path'])
    assert p.parent==bundle.root/'worker-wire' and p.stat().st_mode&0o077==0 and p.stat().st_nlink==1
    assert sha(p.read_bytes())==row['wire_evidence']['sha256']
    captured=json.loads(p.read_bytes());assert base64.b64decode(captured['raw_response_base64'])==body
    assert captured['response_sha256']==sha(body) and captured['request_sha256']==digest
    assert captured['config_sha256']==scope.admitted.grant.config_sha256
    assert captured['request_body_or_headers_captured'] is False
    expected='invalid_usage_detail_count' if bad_details else 'validated_complete_wire'
    assert row['usage_validation_code']==captured['usage_validation_code']==expected
    assert result['state']==('uncertain' if bad_details else 'settled_raw_wire')
    assert result['charged_nano_usd']==(RESERVATION if bad_details else 4500)
    assert not scope.creates  # Authored local wire only, no VM/model/provider call.
    assert not scope.creates


def test_new_supervisor_outer_cannot_reopen_or_change_old_ledger(funded):
    bundle,_=funded;path=bundle.root/'old-supervisor-ledger.sqlite'
    args=dict(input_rate=300,output_rate=900,route=bundle.routes[0],currency='USD',
        pricing_provenance_sha256=bundle.cfg['profile']['supervisor_pricing_sha256'],
        input_token_bound=262144,output_token_bound=4096,approved_routes=bundle.routes,max_attempts=12,
        prior_charged_nano_usd=SUPERVISOR_PRIOR,predecessor_sha256=bundle.cfg['predecessor']['sha256'])
    old=Ledger(path,budget=1180535400,**args);old.reserve('uncertain-old',bundle.routes[0]);old.close()
    with pytest.raises(ValueError,match='budget identity changed'):
        Ledger(path,budget=SUPERVISOR_OUTER,**args)
    import sqlite3
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    assert db.execute('SELECT budget FROM config').fetchall()==[(1180535400,)]
    assert db.execute('SELECT charged,state FROM calls').fetchall()==[(82329600,'reserved_uncertain')]
    db.close()


def test_new_16k_large_wire_archive_is_bounded_and_profile_matched(funded):
    bundle,_=funded;digest,raw=request();db=bundle.raw_workers['baseline']
    assert db.output_token_bound==16384 and db.max_response_bytes==8*1024*1024
    bundle.workers['baseline'].reserve('large-authored',digest,raw)
    value={'model':WORKER_MODEL,'choices':[{'index':0,'finish_reason':'stop'}],
        'usage':{'prompt_tokens':37,'completion_tokens':16384,'total_tokens':16421},
        'authored_padding':'x'*(3*1024*1024)}
    body=canonical(value);assert 2*1024*1024<len(body)<8*1024*1024
    result=bundle.workers['baseline'].settle_raw('large-authored',digest,200,'application/json',body)
    assert result['state']=='settled_raw_wire' and result['charged_nano_usd']==19671900
    row=json.loads(db.db.execute('SELECT receipt FROM calls').fetchone()[0])
    p=Path(row['wire_evidence']['path']);assert p.stat().st_size<12*1024*1024
    capture=json.loads(p.read_bytes());assert base64.b64decode(capture['raw_response_base64'])==body
    old=canonical({'model':WORKER_MODEL,'messages':[{'role':'user','content':'AUTHORED'}],
        'max_completion_tokens':4096,'tools':[{'type':'function','function':{'name':'pex_remote_run'}}]})
    with pytest.raises(ValueError):bundle.workers['baseline'].reserve('old-bound',sha(old),old)
    assert db.usage_snapshot()['calls']==1
