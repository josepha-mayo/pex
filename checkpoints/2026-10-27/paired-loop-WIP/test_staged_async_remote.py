"""Inert async SDK objects only; never import/create an actual sandbox client."""
import asyncio
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
import time
from staged_async_remote import (BoundedAsyncRemote,BoundedRemoteError,validate_provider_lifetime,BASE_TEMPLATE,MAX_BYTES)


def info(**changes):
    now=datetime.now(timezone.utc)
    d=dict(started_at=now,end_at=now+timedelta(seconds=330),cpu_count=2,memory_mb=512,template_id=BASE_TEMPLATE)
    d.update(changes);return SimpleNamespace(**d)


def test_provider_full_lifetime_includes_pause():
    assert validate_provider_lifetime(info())['admitted_full_lifetime_seconds']==330
    assert validate_provider_lifetime(info())['paused_time_discounted'] is False


@pytest.mark.parametrize('changes',[{'cpu_count':True},{'memory_mb':8192},{'template_id':'other'},
    {'end_at':datetime.now(timezone.utc)+timedelta(seconds=400)},{'started_at':datetime.now()}])
def test_unproven_provider_lifetime_refused(changes):
    with pytest.raises(BoundedRemoteError): validate_provider_lifetime(info(**changes))


@pytest.mark.asyncio
async def test_thread_bridge_bounds_SDK_request_and_cleanup():
    events=[]
    async def write(*a,**kw): events.append(('write',kw));return True
    async def kill(**kw): events.append(('kill',kw));return True
    async def running(**kw): events.append(('running',kw));return False
    sdk=SimpleNamespace(files=SimpleNamespace(write=write),kill=kill,is_running=running)
    r=BoundedAsyncRemote(sdk,vm_deadline=time.monotonic()+1)
    r.set_scope_deadline(time.monotonic()+.5)
    assert (await asyncio.to_thread(r.write,'safe.txt','authored'))['written']=='safe.txt'
    assert 0<events[0][1]['request_timeout']<=.5
    with pytest.raises(BoundedRemoteError): r.write('safe.txt','ownerloop')
    await r.end_scope();await r.close();assert r.closed
    assert [e[0] for e in events]==['write','kill','running']


@pytest.mark.asyncio
async def test_timeout_cancels_async_SDK_and_forbids_next_scope():
    cancelled=asyncio.Event()
    async def write(*a,**kw):
        try: await asyncio.sleep(10)
        finally: cancelled.set()
    r=BoundedAsyncRemote(SimpleNamespace(files=SimpleNamespace(write=write)),vm_deadline=time.monotonic()+1)
    r.set_scope_deadline(time.monotonic()+.03)
    with pytest.raises(BoundedRemoteError): await asyncio.to_thread(r.write,'safe.txt','authored')
    await r.end_scope()
    assert cancelled.is_set() and r.poisoned and not r.active
    with pytest.raises(BoundedRemoteError): r.set_scope_deadline(time.monotonic()+.5)


@pytest.mark.asyncio
async def test_deadline_cannot_extend_or_reset_on_pause():
    r=BoundedAsyncRemote(None,vm_deadline=time.monotonic()+1)
    with pytest.raises(BoundedRemoteError): r.set_scope_deadline(r.vm_deadline+1)
    r.set_scope_deadline(time.monotonic()+.1)
    with pytest.raises(BoundedRemoteError): r.set_scope_deadline(time.monotonic()+.2)
    await r.end_scope()


@pytest.mark.asyncio
async def test_cleanup_not_confirmed_when_provider_still_running():
    async def kill(**kw): return True
    async def running(**kw): return True
    r=BoundedAsyncRemote(SimpleNamespace(kill=kill,is_running=running),vm_deadline=time.monotonic()+1)
    with pytest.raises(BoundedRemoteError): await r.close()
    assert not r.closed


@pytest.mark.asyncio
async def test_cancellation_suppressing_SDK_returns_bounded_and_still_kills_owned_VM():
    stop=asyncio.Event();events=[]
    async def write(*a,**kw):
        while not stop.is_set():
            try: await asyncio.sleep(.01)
            except asyncio.CancelledError: pass
    async def kill(**kw): events.append('kill');stop.set();return True
    async def running(**kw): events.append('is_running');return False
    r=BoundedAsyncRemote(SimpleNamespace(files=SimpleNamespace(write=write),kill=kill,is_running=running),
        vm_deadline=time.monotonic()+3)
    r.set_scope_deadline(time.monotonic()+.03)
    started=time.monotonic()
    with pytest.raises(BoundedRemoteError): await asyncio.to_thread(r.write,'safe.txt','authored')
    assert time.monotonic()-started < .5 and r.poisoned
    try:
        await r.close()
        assert time.monotonic()-started < 1.5
        assert r.closed and r.cancellation_unconfirmed
        assert r.cleanup_evidence['kill_attempted'] and r.cleanup_evidence['stopped_confirmed']
        assert events==['kill','is_running']
    finally:
        stop.set()
        if r.active: await asyncio.wait(list(r.active),timeout=.1)


@pytest.mark.asyncio
async def test_cancellation_ambiguity_cannot_skip_cleanup_attempt():
    events=[]
    async def kill(**kw):events.append('kill')
    async def running(**kw):return False
    r=BoundedAsyncRemote(SimpleNamespace(kill=kill,is_running=running),vm_deadline=time.monotonic()+1)
    async def broken():
        r.cancellation_unconfirmed=True
        raise BoundedRemoteError('SDK_cancellation_unconfirmed')
    r.end_scope=broken
    await r.close()
    assert events==['kill'] and r.closed and r.cleanup_evidence['cancellation_unconfirmed']


@pytest.mark.asyncio
@pytest.mark.parametrize('exit_code',[0,7])
async def test_natural_terminal_must_not_kill_finished_process_or_poison_next_scope(exit_code):
    events=[]
    async def wait():
        if exit_code:
            from e2b import CommandExitException
            raise CommandExitException(stdout='',stderr='',exit_code=exit_code,error='AUTHORED')
        return SimpleNamespace(exit_code=0)
    async def process_kill():events.append('unnecessary_kill');await asyncio.sleep(1.1);return False
    async def run(*args,**kwargs):return SimpleNamespace(wait=wait,kill=process_kill)
    remote=BoundedAsyncRemote(SimpleNamespace(commands=SimpleNamespace(run=run)),vm_deadline=time.monotonic()+5)
    remote.set_scope_deadline(time.monotonic()+3)
    result=await asyncio.to_thread(remote.run,'printf AUTHORED')
    assert result['exit_code']==exit_code
    await remote.end_scope()
    assert not remote.poisoned and events==[]
    remote.set_scope_deadline(time.monotonic()+1)
    await remote.end_scope()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['wait_error','output_bound','cancel','cleanup_error'])
async def test_unacknowledged_command_is_killed_poisoned_and_owned_VM_cleanup_unchanged(failure):
    events=[];options={};waiting=asyncio.Event()
    async def wait():
        waiting.set()
        if failure=='cancel':await asyncio.Event().wait()
        if failure=='output_bound':options['on_stdout']('x'*(MAX_BYTES+1))
        raise TimeoutError('AUTHORED-RAW-ERROR-MUST-NOT-BE-RETAINED')
    async def process_kill():
        events.append('process_kill')
        if failure=='cleanup_error':raise RuntimeError('https://secret.invalid/AUTHORED-RAW-ERROR-MUST-NOT-BE-RETAINED')
        return False  # Not found is not an acknowledged end receipt.
    async def run(*args,**kwargs):options.update(kwargs);return SimpleNamespace(wait=wait,kill=process_kill)
    async def vm_kill(**kw):events.append('vm_kill')
    async def running(**kw):events.append('running');return False
    remote=BoundedAsyncRemote(SimpleNamespace(commands=SimpleNamespace(run=run),kill=vm_kill,is_running=running),vm_deadline=time.monotonic()+3)
    remote.set_scope_deadline(time.monotonic()+1)
    task=asyncio.create_task(asyncio.to_thread(remote.run,'AUTHORED'))
    if failure=='cancel':
        await waiting.wait();await remote.end_scope()
    with pytest.raises(BoundedRemoteError):await task
    await remote.end_scope()
    assert remote.poisoned and remote.diagnostics['acknowledged_terminal_commands']==0
    assert 'process_kill' in events
    with pytest.raises(BoundedRemoteError):remote.set_scope_deadline(time.monotonic()+1)
    await remote.close()
    assert remote.closed and events[-2:]==['vm_kill','running']
    import json
    diagnostic=json.dumps(remote.diagnostics)
    assert 'AUTHORED-RAW-ERROR' not in diagnostic and 'https://' not in diagnostic
    assert remote.diagnostics['exception_types'] and remote.diagnostics['scope_refusals']
