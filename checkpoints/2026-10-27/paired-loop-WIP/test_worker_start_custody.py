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
