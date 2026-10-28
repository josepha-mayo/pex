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
