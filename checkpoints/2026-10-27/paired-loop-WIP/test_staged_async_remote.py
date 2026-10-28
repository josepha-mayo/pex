"""Inert async SDK objects only; never import/create an actual sandbox client."""
import asyncio
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from staged_async_remote import *


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
