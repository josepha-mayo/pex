"""Fake asynchronous SDK + synthetic accounting only; no provider or VM."""
import asyncio
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from staged_lifecycle import *


class Ledger:
    def __init__(self):self.reserved=[];self.settled=[]
    def reserve(self,identity):self.reserved.append(identity)
    def settle_verified_allocation(self,identity,**kwargs):self.settled.append((identity,kwargs))


class SDK:
    def __init__(self):self.killed=False
    async def get_info(self,**kw):
        now=datetime.now(timezone.utc)
        return SimpleNamespace(started_at=now,end_at=now+timedelta(seconds=VM_SECONDS),
            cpu_count=2,memory_mb=512,template_id=BASE_TEMPLATE)
    async def kill(self,**kw):self.killed=True
    async def is_running(self,**kw):return not self.killed


class API:
    AUTHORED_FAKE_ONLY=True
    def __init__(self):self.calls=[]
    async def create(self,**kw):self.calls.append(kw);return SDK()


async def stage(arm,remote):assert remote.deadline<=remote.vm_deadline


@pytest.mark.asyncio
async def test_sequential_exact_provider_lifetime_and_no_pause_discount():
    api=API();ledger=Ledger();life=StagedLifecycle(api,ledger,stage,run_id='authored')
    a={'condition':'baseline'};b={'condition':'pex'}
    first=await life.prepare(a,deadline=time.monotonic()+VM_SECONDS)
    with pytest.raises(BoundedRemoteError):await life.prepare(b,deadline=time.monotonic()+VM_SECONDS)
    assert len(ledger.reserved)==1
    await first.close()
    second=await life.prepare(b,deadline=time.monotonic()+VM_SECONDS)
    await life.cleanup();assert second.closed
    assert len(api.calls)==2 and len(ledger.reserved)==len(ledger.settled)==2
    assert all(c['timeout']==VM_SECONDS and c['lifecycle']=={'on_timeout':'kill','auto_resume':False} and c['retries']==0 for c in api.calls)
    assert all(v['admitted_full_lifetime_seconds']==VM_SECONDS and not v['paused_time_discounted'] for v in life.provider_evidence.values())


@pytest.mark.asyncio
async def test_uncertain_create_retains_reservation_and_refuses_replacement():
    class Bad(API):
        async def create(self,**kw):self.calls.append(kw);raise ConnectionError('authored uncertainty')
    api=Bad();ledger=Ledger();life=StagedLifecycle(api,ledger,stage,run_id='authored')
    with pytest.raises(ConnectionError):await life.prepare({'condition':'baseline'},deadline=time.monotonic()+VM_SECONDS)
    with pytest.raises(BoundedRemoteError):await life.prepare({'condition':'pex'},deadline=time.monotonic()+VM_SECONDS)
    assert len(api.calls)==len(ledger.reserved)==1 and not ledger.settled and life.uncertain


@pytest.mark.asyncio
async def test_wrong_allocation_retains_generic_reservation_and_kills_owned_VM():
    class BadSDK(SDK):
        async def get_info(self,**kw):
            obj=await super().get_info(**kw);obj.cpu_count=4;return obj
    class Bad(API):
        async def create(self,**kw):self.sdk=BadSDK();return self.sdk
    api=Bad();ledger=Ledger();life=StagedLifecycle(api,ledger,stage,run_id='authored')
    with pytest.raises(BoundedRemoteError):await life.prepare({'condition':'baseline'},deadline=time.monotonic()+VM_SECONDS)
    await life.cleanup()
    assert api.sdk.killed and not ledger.settled and len(ledger.reserved)==1


@pytest.mark.parametrize('mode',['live','live-pilot',None])
def test_lifecycle_cannot_open_live_authority(mode):
    with pytest.raises(PermissionError):StagedLifecycle(API(),None,stage,run_id='authored',mode=mode)


def test_actual_SDK_class_not_accepted_as_authored_fake():
    with pytest.raises(PermissionError):StagedLifecycle(object(),None,stage,run_id='authored')


@pytest.mark.asyncio
async def test_closed_first_deadline_cannot_prevent_current_owned_VM_cleanup():
    clock=[0.0];api=API();life=StagedLifecycle(api,Ledger(),stage,run_id='authored',clock=lambda:clock[0])
    first=await life.prepare({'condition':'baseline'},deadline=VM_SECONDS)
    await first.close()
    clock[0]=800
    second=await life.prepare({'condition':'pex'},deadline=800+VM_SECONDS)
    await life.cleanup()
    assert first.closed and second.closed and life.raw_stopped=={'baseline','pex'}


@pytest.mark.asyncio
async def test_after_deadline_create_handle_is_retained_killed_and_never_refunded():
    clock=[0.0]
    class Late(API):
        async def create(self,**kw):
            self.sdk=SDK();clock[0]=VM_SECONDS+1;return self.sdk
    api=Late();ledger=Ledger();life=StagedLifecycle(api,ledger,stage,run_id='authored',clock=lambda:clock[0])
    with pytest.raises(BoundedRemoteError):await life.prepare({'condition':'baseline'},deadline=VM_SECONDS)
    assert life.raw_owned['baseline'] is api.sdk and api.sdk.killed
    assert life.cleanup_evidence['baseline']['stopped_confirmed']
    assert life.cleanup_evidence['baseline']['cleanup_only_after_worker_deadline']
    assert len(ledger.reserved)==1 and not ledger.settled and life.uncertain
    assert 'baseline' not in life.remotes  # No worker wrapper or continuation.
    await life.cleanup()


@pytest.mark.asyncio
async def test_cancellation_suppressed_late_create_is_still_owned_and_cleaned():
    class Late(API):
        async def create(self,**kw):
            try:await asyncio.sleep(10)
            except asyncio.CancelledError:await asyncio.sleep(.01)
            self.sdk=SDK();return self.sdk
    api=Late();ledger=Ledger();life=StagedLifecycle(api,ledger,stage,run_id='authored')
    with pytest.raises(TimeoutError):await life.prepare({'condition':'baseline'},deadline=time.monotonic()+.02)
    await asyncio.sleep(.05)
    assert life.raw_owned['baseline'] is api.sdk and api.sdk.killed
    assert 'baseline' in life.raw_stopped and not ledger.settled
    await life.cleanup()
