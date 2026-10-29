"""Adapter contract with inert CLI/remote/lifecycle objects only."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from staged_worker import *
from test_staged_funding import Ledger,use


class Remote:
    def __init__(self,deadline):self.vm_deadline=deadline;self.scope=None;self.closed=False
    def set_scope_deadline(self,value):
        assert self.scope is None and value<=self.vm_deadline;self.scope=value
    async def end_scope(self):self.scope=None
    async def close(self):self.closed=True


class Lifecycle:
    async def prepare(self,arm,*,deadline):return Remote(deadline)


class Inner:
    def __init__(self,tmp):
        self.root=tmp;self.funding={c:PhaseFunding(Ledger()) for c in ('baseline','pex')}
        self.remotes={};self.states={};self.key_path='SYNTHETIC-UNREAD-PATH'
    def _start(self,c):
        case=self.root/c;(case/'plugins/guard').mkdir(parents=True)
        (case/'opencode.json').write_text(json.dumps({'agents':{'paired':{'steps':12}}}))
        self.states[c]=dict(case=case,funding_channel={},stopped=False)
    async def execute_cli(self,arm,**kw):
        c=arm['condition'];limit=PHASES[self.funding[c].index];use(self.funding[c],limit.calls)
        return dict(session_id=c,receipt={'id':self.funding[c].index},_terminal_receipt='authored',
                    terminal='natural_stop',usage=dict(calls=limit.calls,input_tokens=limit.calls,output_tokens=limit.calls),worker_active_seconds=1)
    def collect_observation(self,arm,receipt):assert receipt=='authored';return {'public':'authored'}
    async def stop(self,arm):self.states[arm['condition']]['stopped']=True


@pytest.mark.asyncio
async def test_integrated_phase_config_ledger_observation_and_release(tmp_path):
    inner=Inner(tmp_path);worker=StagedWorker(inner,Lifecycle());arm={'condition':'pex'}
    await worker.prepare(arm,deadline=time.monotonic()+330)
    first=await worker.phase(arm,prompt='authored',session_id=None,phase_index=0,limit=PHASES[0])
    assert await worker.observe(arm,first)=={'public':'authored'}
    second=await worker.phase(arm,prompt='authored',session_id='pex',phase_index=1,limit=PHASES[1])
    assert first['usage']['calls']+second['usage']['calls']==12
    config=json.loads((inner.states['pex']['case']/'opencode.json').read_text())
    assert config['agents']['paired']['steps']==4
    guard=(inner.states['pex']['case']/'plugins/guard/index.ts').read_text()
    assert 'CONFIGURATION' not in guard and '"phaseCalls": 4' in guard
    await worker.stop(arm);await worker.release(arm);await worker.cleanup()
    assert worker.remotes['pex'].closed and inner.states['pex']['stopped']


@pytest.mark.parametrize('mode',['live','live-pilot',None])
def test_no_live_adapter_admission(mode):
    with pytest.raises(PermissionError):StagedWorker(None,None,mode=mode)


@pytest.mark.asyncio
async def test_observation_is_bound_to_actual_first_receipt(tmp_path):
    w=StagedWorker(Inner(tmp_path),Lifecycle());a={'condition':'baseline'}
    await w.prepare(a,deadline=time.monotonic()+330)
    with pytest.raises(ProtocolInconclusive):await w.observe(a,{'receipt':{}})
    await w.cleanup()


@pytest.mark.asyncio
async def test_changed_deadline_fails_after_retaining_owned_remote_for_cleanup(tmp_path):
    class Bad(Lifecycle):
        async def prepare(self,arm,*,deadline):return Remote(deadline+1)
    w=StagedWorker(Inner(tmp_path),Bad());a={'condition':'pex'}
    with pytest.raises(ProtocolInconclusive):await w.prepare(a,deadline=time.monotonic()+330)
    # Even a prepare failure leaves the owned object available for release.
    await w.release(a);assert w.remotes['pex'].closed


@pytest.mark.asyncio
@pytest.mark.parametrize('condition',['baseline','pex'])
async def test_unconfirmed_CLI_cleanup_remains_unconfirmed_after_VM_stop(tmp_path,condition):
    class Unconfirmed(Inner):
        async def execute_cli(self,*args,**kwargs):raise CliCleanupUnconfirmed('authored owned-process ambiguity')
    worker=StagedWorker(Unconfirmed(tmp_path),Lifecycle());arm={'condition':condition}
    await worker.prepare(arm,deadline=time.monotonic()+750)
    with pytest.raises(CliCleanupUnconfirmed):
        await worker.phase(arm,prompt='authored',session_id=None,phase_index=0,limit=PHASES[0])
    await worker.stop(arm)
    with pytest.raises(ProtocolInconclusive):await worker.release(arm)
    assert worker.remotes[condition].closed and condition in worker.unconfirmed


@pytest.mark.asyncio
async def test_unconfirmed_CLI_cleanup_never_prepares_next_arm(tmp_path):
    from staged_controller import run_staged_pair
    class Unconfirmed(Inner):
        async def execute_cli(self,*args,**kwargs):raise CliCleanupUnconfirmed('authored process ambiguity')
    inner=Unconfirmed(tmp_path);worker=StagedWorker(inner,Lifecycle())
    arms={c:{'condition':c,'prompt':'same authored prompt','public_sha256':'a'*64,
             'worker_identity':'same authored worker','workspace':c} for c in ('baseline','pex')}
    report=await run_staged_pair(arms,worker,None,None)
    assert set(inner.states)=={'baseline'} and set(report['arms'])=={'baseline'}
    assert report['arms']['baseline']['status']=='cleanup_unconfirmed'
    assert report['cleanup_confirmed'] is False


@pytest.mark.asyncio
async def test_CLI_cleanup_uncertainty_not_masked_by_an_earlier_funding_refusal(tmp_path,monkeypatch):
    from worker_funding import WorkerBudgetExhausted

    import nebius_worker as cw
    worker=object.__new__(cw.NebiusCLIWorker)
    worker._start=lambda c:None
    worker.states={'baseline':{'stopped':False,'profile':tmp_path,'case':tmp_path,'seq':0,
                   'funding_channel':SimpleNamespace(last_error=WorkerBudgetExhausted('worker_attempt_cap_refused'))}}
    worker.staged_binding=None;worker.binary=Path('/authored-never-executed')
    worker.funding={'baseline':SimpleNamespace(usage_snapshot=lambda:{'calls':8,'input_tokens':8,'output_tokens':8,'uncertain_calls':0})}
    async def failed(**kwargs):raise CliCleanupUnconfirmed('authored owned-process ambiguity')
    monkeypatch.setattr(cw,'run_turn',failed)
    with pytest.raises(CliCleanupUnconfirmed):
        await worker.execute_cli({'condition':'baseline'},prompt='authored',session_id=None,remaining={'active_seconds':1})

@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,remaining,status,expected',[(False,50,'graded_with_limits',False),(True,50,'graded_with_limits',True),(True,20,'graded_with_limits',False),(True,50,'inconclusive',False)])
async def test_optional_phase0_uses_only_original_grade_window(enabled,remaining,status,expected):
    remote=Remote(200);clock=[100]
    worker=SimpleNamespace(clock=lambda:clock[0],deadlines={'pex':200},remotes={'pex':remote})
    class Grade:
        def __init__(self):self.calls=[]
        async def grade(self,arm):
            self.calls.append('final');clock[0]=160-remaining
            return {'status':status,'summary':{'passed':40}}
        async def grade_phase0(self,arm):
            self.calls.append('phase0');assert remote.scope==160
            return {'status':'graded_with_limits','summary':{'passed':30}}
    impl=Grade();g=StagedGrade(impl,worker,grade_phase0_after_final=enabled)
    g.reserve_wall({'condition':'pex'},deadline=160)
    result=await g.grade({'condition':'pex'})
    assert impl.calls==(['final','phase0'] if expected else ['final'])
    assert result['summary']=={'passed':40};assert remote.scope is None
    if expected:assert result['pre_intervention_grade']['summary']['passed']==30
    elif enabled:assert result['pre_intervention_grade']['status']=='not_run'

@pytest.mark.asyncio
async def test_phase0_error_does_not_replace_final_grade():
    remote=Remote(200);worker=SimpleNamespace(clock=lambda:100,deadlines={'pex':200},remotes={'pex':remote})
    class Grade:
        async def grade(self,a):return {'status':'graded_with_limits','summary':{'passed':40}}
        async def grade_phase0(self,a):raise ValueError('authored invalid archive')
    g=StagedGrade(Grade(),worker,grade_phase0_after_final=True);g.reserve_wall({'condition':'pex'},deadline=160)
    result=await g.grade({'condition':'pex'})
    assert result['summary']=={'passed':40};assert result['pre_intervention_grade']['status']=='inconclusive'
    assert remote.scope is None
