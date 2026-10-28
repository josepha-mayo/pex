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
        return SimpleNamespace(started_at=now,end_at=now+timedelta(seconds=330),
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
    first=await life.prepare(a,deadline=time.monotonic()+330)
    with pytest.raises(BoundedRemoteError):await life.prepare(b,deadline=time.monotonic()+330)
    assert len(ledger.reserved)==1
    await first.close()
    second=await life.prepare(b,deadline=time.monotonic()+330)
    await life.cleanup();assert second.closed
    assert len(api.calls)==2 and len(ledger.reserved)==len(ledger.settled)==2
    assert all(c['timeout']==330 and c['lifecycle']=={'on_timeout':'kill','auto_resume':False} and c['retries']==0 for c in api.calls)
    assert all(v['admitted_full_lifetime_seconds']==330 and not v['paused_time_discounted'] for v in life.provider_evidence.values())


@pytest.mark.asyncio
async def test_uncertain_create_retains_reservation_and_refuses_replacement():
    class Bad(API):
        async def create(self,**kw):self.calls.append(kw);raise ConnectionError('authored uncertainty')
    api=Bad();ledger=Ledger();life=StagedLifecycle(api,ledger,stage,run_id='authored')
    with pytest.raises(ConnectionError):await life.prepare({'condition':'baseline'},deadline=time.monotonic()+330)
    with pytest.raises(BoundedRemoteError):await life.prepare({'condition':'pex'},deadline=time.monotonic()+330)
    assert len(api.calls)==len(ledger.reserved)==1 and not ledger.settled and life.uncertain


@pytest.mark.asyncio
async def test_wrong_allocation_retains_generic_reservation_and_kills_owned_VM():
    class BadSDK(SDK):
        async def get_info(self,**kw):
            obj=await super().get_info(**kw);obj.cpu_count=4;return obj
    class Bad(API):
        async def create(self,**kw):self.sdk=BadSDK();return self.sdk
    api=Bad();ledger=Ledger();life=StagedLifecycle(api,ledger,stage,run_id='authored')
    with pytest.raises(BoundedRemoteError):await life.prepare({'condition':'baseline'},deadline=time.monotonic()+330)
    await life.cleanup()
    assert api.sdk.killed and not ledger.settled and len(ledger.reserved)==1


@pytest.mark.parametrize('mode',['live','live-pilot',None])
def test_lifecycle_cannot_open_live_authority(mode):
    with pytest.raises(PermissionError):StagedLifecycle(API(),None,stage,run_id='authored',mode=mode)


def test_actual_SDK_class_not_accepted_as_authored_fake():
    with pytest.raises(PermissionError):StagedLifecycle(object(),None,stage,run_id='authored')
