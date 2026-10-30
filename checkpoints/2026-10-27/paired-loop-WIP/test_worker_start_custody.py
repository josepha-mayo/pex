"""Independent authored fault injection, no remote server/VM/model/credentials."""
from pathlib import Path
from types import SimpleNamespace
import asyncio
import nebius_worker as nw

def test_start_cleanup_when_budget_setup_fails(tmp_path, monkeypatch):
    events=[]
    class FakeRemoteCM:
        def __enter__(self): events.append('remote-enter'); return '/authored/inert.sock'
        def __exit__(self,*args): events.append('remote-exit')
    def bad_budget(*args): raise OSError('AUTHORED setup fault')
    monkeypatch.setattr(nw,'serve_remote',lambda *args:FakeRemoteCM())
    monkeypatch.setattr(nw,'serve_budget',bad_budget)
    worker=object.__new__(nw.NebiusCLIWorker)
    worker.root=tmp_path;worker.modules=tmp_path/'authored-modules'
    worker.remotes={'baseline':object()};worker.states={};worker.funding={'baseline':object()}
    try:worker._start('baseline')
    except OSError:pass
    asyncio.run(worker.stop({'condition':'baseline'}))
    print('EVENTS',events,'STATES',worker.states)
    assert events == ['remote-enter','remote-exit']


def test_config_failure_closes_both_entered_contexts(tmp_path,monkeypatch):
    events=[]
    class CM:
        def __init__(self,name):self.name=name
        def __enter__(self):events.append(self.name+'-enter');return 'AUTHORED'
        def __exit__(self,*args):events.append(self.name+'-exit')
    monkeypatch.setattr(nw,'serve_remote',lambda *args:CM('remote'))
    monkeypatch.setattr(nw,'serve_budget',lambda *args:CM('budget'))
    worker=object.__new__(nw.NebiusCLIWorker)
    worker.root=tmp_path;worker.modules=tmp_path/'authored-modules';worker.remotes={'baseline':object()};worker.states={};worker.funding={'baseline':object()}
    # Missing max_calls faults the config after both contexts have entered.
    try:worker._start('baseline')
    except AttributeError:pass
    assert events==['remote-enter','budget-enter','remote-exit','budget-exit']
    state=worker.states['baseline']
    assert state['stopped'] and state['mcp_revoked'] and state['funding_revoked'] and state['startup_failed']
    asyncio.run(worker.stop({'condition':'baseline'}))
    assert len(events)==4


def test_failed_cleanup_retains_unconfirmed_and_still_closes_other_context():
    import pytest
    events=[]
    class Remote:
        def __exit__(self,*args):events.append('remote-exit');raise OSError('AUTHORED')
    class Budget:
        def __exit__(self,*args):events.append('budget-exit')
    state={'cm':Remote(),'budget_cm':Budget(),'remote_entered':True,'budget_entered':True,'stopped':False}
    with pytest.raises(RuntimeError,match='unconfirmed'):nw.NebiusCLIWorker._stop_state(state)
    assert events==['remote-exit','budget-exit'] and state['mcp_revoked'] is False and state['funding_revoked'] is True
    assert state['local_cleanup_unconfirmed']
    with pytest.raises(RuntimeError,match='unconfirmed'):nw.NebiusCLIWorker._stop_state(state)
    assert len(events)==2

import threading
import pytest
from staged_worker import StagedWorker
from staged_funding import PhaseFunding
from test_staged_funding import Ledger
from test_staged_worker import Lifecycle

@pytest.mark.asyncio
async def test_cancelled_start_must_not_finish_after_confirmed_cleanup(tmp_path):
    started=threading.Event();resume=threading.Event();finished=threading.Event()
    class SlowInner:
        def __init__(self):
            self.funding={c:PhaseFunding(Ledger()) for c in ('baseline','pex')}
            self.states={};self.remotes={}
        def _start(self,c):
            started.set();resume.wait(5)
            self.states[c]={'stopped':False,'mcp_revoked':False};finished.set()
        async def stop(self,arm):
            c=arm['condition']
            if c not in self.states:return
            self.states[c].update(stopped=True,mcp_revoked=True)
    inner=SlowInner();worker=StagedWorker(inner,Lifecycle());arm={'condition':'baseline'}
    task=asyncio.create_task(worker.prepare(arm,deadline=worker.clock()+750))
    try:
        assert await asyncio.to_thread(started.wait,2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        with pytest.raises(Exception,match='unconfirmed'):await worker.stop(arm)
        with pytest.raises(Exception,match='unconfirmed'):await worker.release(arm)
        with pytest.raises(Exception,match='unconfirmed'):await worker.cleanup()
        resume.set();assert await asyncio.to_thread(finished.wait,2)
        print('POST_CLEANUP_STATES',inner.states,'UNCONFIRMED',worker.unconfirmed)
        await asyncio.wait_for(asyncio.shield(worker.start_tasks['baseline']),2)
        assert inner.states['baseline']['stopped'] and inner.states['baseline']['mcp_revoked']
        assert 'baseline' in worker.unconfirmed
    finally:
        resume.set()

@pytest.mark.asyncio
async def test_real_start_cancel_during_budget_constructor_cannot_leak(tmp_path,monkeypatch):
    events=[];started=threading.Event();resume=threading.Event();entered=threading.Event()
    class CM:
        def __init__(self,name):self.name=name
        def __enter__(self):
            events.append(self.name+'-enter')
            if self.name=='budget':entered.set()
            return 'AUTHORED'
        def __exit__(self,*args):events.append(self.name+'-exit')
    def budget(*args):
        started.set();resume.wait(5);return CM('budget')
    monkeypatch.setattr(nw,'serve_remote',lambda *args:CM('remote'))
    monkeypatch.setattr(nw,'serve_budget',budget)
    inner=object.__new__(nw.NebiusCLIWorker)
    inner.root=tmp_path;inner.modules=tmp_path/'authored-modules';inner.remotes={};inner.states={}
    inner.funding={c:PhaseFunding(Ledger()) for c in ('baseline','pex')}
    inner.max_calls=12;inner.output_per_call=16384;inner.key_path='/AUTHORED-unread-inert'
    worker=StagedWorker(inner,Lifecycle());arm={'condition':'baseline'}
    task=asyncio.create_task(worker.prepare(arm,deadline=worker.clock()+750))
    try:
        assert await asyncio.to_thread(started.wait,2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        with pytest.raises(Exception,match='unconfirmed'):await worker.stop(arm)
        with pytest.raises(Exception,match='unconfirmed'):await worker.release(arm)
        with pytest.raises(Exception,match='unconfirmed'):await worker.cleanup()
        resume.set();assert await asyncio.to_thread(entered.wait,2)
        print('REAL_POST_CLEANUP_EVENTS',events,'UNCONFIRMED',worker.unconfirmed,'STATE',inner.states['baseline'])
        await asyncio.wait_for(asyncio.shield(worker.start_tasks['baseline']),2)
        assert events==['remote-enter','budget-enter','remote-exit','budget-exit']
        assert inner.states['baseline']['funding_revoked'] and inner.states['baseline']['mcp_revoked']
        assert 'baseline' in worker.unconfirmed
    finally:resume.set()
