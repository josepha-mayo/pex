"""Closed composition with actual SDK serializers and local mock transport only."""
import asyncio
import time
from datetime import datetime,timedelta,timezone
import json
from urllib.parse import urlsplit
import pytest
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
from staged_sdk_lifecycle import *
from staged_async_remote import BoundedRemoteError
from cumulative_compute import allocation_bounds
from staged_envelope import VM_SECONDS
RESERVATION,VERIFIED_FULL_LIFETIME=allocation_bounds(VM_SECONDS)
from pyqwest import Response,Headers

@pytest.fixture
def lifecycle(bound,monkeypatch):
    scope,compute,wire,pools,behavior=bound
    # Override only locally scripted info responses, not SDK serialization.
    original=scope._execute
    async def wrapped(inner,request):
        original_execute=inner.execute
        class LocalInfo:
            async def execute(self,req):
                p=urlsplit(req.url).path
                sid=p.split('/')[-1]
                if req.method=='GET' and p.startswith('/sandboxes/') and sid not in scope.kill_attempted and behavior['mode']=='normal':
                    wire.append((req.method,req.url,req.content))
                    now=datetime.now(timezone.utc)
                    value={'templateID':BASE_TEMPLATE,'sandboxID':sid,'clientID':'authored',
                        'startedAt':now.isoformat(),'endAt':(now+timedelta(seconds=VM_SECONDS)).isoformat(),
                        'envdVersion':'0.5.7','cpuCount':2,'memoryMB':512,'diskSizeMB':1024,'state':'running'}
                    return Response(status=200,headers=Headers({'content-type':'application/json'}),content=json.dumps(value).encode())
                return await original_execute(req)
        return await original(LocalInfo(),request)
    monkeypatch.setattr(scope,'_execute',wrapped)
    events=[]
    async def stage(arm,remote):
        result=await asyncio.to_thread(remote.run,'printf authored',.5)
        assert result['stdout']=='authored stream';events.append(('stage',arm['condition']))
    with scope:
        life=AdmittedSDKLifecycle(scope,stage)
        yield life,bound,events

@pytest.mark.asyncio
async def test_actual_SDK_cumulative_reserve_lifetime_stage_stop_then_next(lifecycle):
    life,(scope,compute,wire,pools,behavior),events=lifecycle
    for arm in ('baseline','pex'):
        remote=await life.prepare({'condition':arm},deadline=time.monotonic()+VM_SECONDS)
        assert life.provider_evidence[arm]['provider_lifetime_seconds']==VM_SECONDS
        await remote.close()
    await life.cleanup()
    assert events==[('stage','baseline'),('stage','pex')]
    assert compute.total()==100+2*VERIFIED_FULL_LIFETIME
    assert scope.stopped==scope.owned and len(scope.creates)==2
    assert all(r.closed for r in life.remotes.values())

@pytest.mark.asyncio
async def test_SDK_constructor_failure_retains_generic_and_adapter_cleans_raw_ID(lifecycle):
    life,(scope,compute,wire,pools,behavior),events=lifecycle
    behavior['mode']='constructor_failure'
    with pytest.raises(Exception):await life.prepare({'condition':'baseline'},deadline=time.monotonic()+VM_SECONDS)
    assert life.unknown_creates=={'baseline'} and scope.owned and compute.total()==100+RESERVATION
    behavior['mode']='normal'
    # Cancellation/error classification remains inconclusive even after exact
    # independent stop proof. No reservation refund or replacement is granted.
    with pytest.raises(BoundedRemoteError):await life.cleanup()
    assert scope.stopped==scope.owned and life.raw_stopped=={'baseline'}
    assert compute.total()==100+RESERVATION

@pytest.mark.asyncio
async def test_unknown_create_cannot_refund_retry_or_claim_cleanup(lifecycle):
    life,(scope,compute,wire,pools,behavior),events=lifecycle
    behavior['mode']='connect_failure'
    with pytest.raises(Exception):await life.prepare({'condition':'baseline'},deadline=time.monotonic()+VM_SECONDS)
    with pytest.raises(BoundedRemoteError):await life.prepare({'condition':'pex'},deadline=time.monotonic()+VM_SECONDS)
    with pytest.raises(BoundedRemoteError):await life.cleanup()
    assert compute.total()==100+RESERVATION and len(wire)==1 and not scope.owned

def test_no_unadmitted_SDK_lifecycle():
    with pytest.raises(AdmissionRefused):AdmittedSDKLifecycle(None,None)
