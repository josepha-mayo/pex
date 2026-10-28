"""Actual E2B 2.61.0 serialization with pyqwest transport replaced by local mocks.

No socket, provider, real key, VM, or evidence of provider cancellation behavior.
"""
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from test_staged_admission import candidate
import staged_admission as a
import staged_sdk_binding as b
from cumulative_compute import ComputeBudget,RESERVATION
from e2b import AsyncSandbox
from pyqwest import Response,Headers,Request

@pytest.fixture
def bound(candidate,monkeypatch,tmp_path):
    cfg,freeze=candidate
    cfg['sdk_sources']=b.installed_source_pins()
    key=tmp_path/'SYNTHETIC-KEY';key.write_bytes(b'AUTHORED-NOT-A-CREDENTIAL');key.chmod(0o600)
    cfg['e2b_key']={'path':str(key),'sha256':a.sha(key.read_bytes())}
    raw,grant=freeze();monkeypatch.setattr(a,'APPROVED_STAGED_GRANT',grant)
    admitted=a.load()
    import e2b.api.client_async as c
    for n in ('_transports','_pools','_httpx_transports'):monkeypatch.setattr(c,n,{})
    compute=ComputeBudget(tmp_path/'compute.sqlite',prior_upper_bound_nano_usd=100,evidence_sha256=cfg['predecessor']['sha256'])
    wire=[];pools=[];behavior={'mode':'normal'}
    class MockPool:
        def __init__(self,**opts):
            assert opts['tls_ca_cert']==b'authored' and opts['tls_include_system_certs'] is False
            assert opts['follow_redirects'] is False and opts['enable_otel'] is False
            assert opts['pool_max_idle_per_host']==0
            pools.append(opts)
        async def execute(self,request):
            wire.append((request.method,request.url,request.content))
            mode=behavior['mode']
            if mode=='connect_failure':raise ConnectionError('AUTHORED')
            if mode=='retryable':return Response(status=503,headers=Headers({'Should-Retry':'true'}),content=b'{"code":503,"message":"AUTHORED"}')
            if mode=='cancel':await asyncio.Event().wait()
            if mode=='suppress_cancel':
                try:await behavior['finish'].wait()
                except asyncio.CancelledError:
                    behavior['cancelled'].set();await behavior['finish'].wait()
            p=urlsplit(request.url).path
            if p=='/v2/sandboxes':
                body=json.loads(request.content)
                value={'templateID':b.BASE_TEMPLATE,'sandboxID':'authored-'+body['metadata']['pex_arm'],
                       'clientID':'authored','envdVersion':'0.5.7','envdAccessToken':'SYNTHETIC-ENVD','domain':'e2b.app'}
                if mode=='constructor_failure':value['envdVersion']='invalid'
                return Response(status=201,headers=Headers({'content-type':'application/json'}),content=json.dumps(value).encode())
            if request.method=='DELETE':return Response(status=204)
            if p=='/health':return Response(status=502,content=b'{"message":"sandbox not found"}')
            if p.startswith('/sandboxes/'):
                return Response(status=404,content=b'{"code":404,"message":"sandbox not found"}')
            return Response(status=200,content=b'authored file')
    import pyqwest
    monkeypatch.setattr(pyqwest,'HTTPTransport',MockPool)
    # Guard against accidentally falling through any real Python socket path.
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *x,**k:pytest.fail('network forbidden'))
    scope=b.SDKTransportBinding(admitted,compute)
    yield scope,compute,wire,pools,behavior
    scope.__exit__();compute.close()

async def create(scope,compute,arm='baseline'):
    identity=scope.admitted.grant.run_id+'-'+arm
    compute.reserve(identity)
    return await AsyncSandbox.create(template=b.BASE_TEMPLATE,timeout=330,
        lifecycle={'on_timeout':'kill','auto_resume':False},metadata={'pex_pilot':scope.admitted.grant.run_id,'pex_arm':arm},
        idempotency_key=identity,request_timeout=1,**scope.options())

def test_closed_before_SDK_or_credential_access(monkeypatch):
    monkeypatch.setattr(b,'installed_source_pins',lambda:pytest.fail('SDK must not load'))
    with pytest.raises(a.AdmissionRefused):b.SDKTransportBinding(None,None)

@pytest.mark.asyncio
async def test_actual_SDK_create_serialization_owned_cleanup_and_claim(bound):
    scope,compute,wire,pools,mode=bound
    with scope:
        assert (Path(scope.admitted.grant.config_path).parent/'launch.claim').is_file()
        sdk=await create(scope,compute)
        assert sdk.sandbox_id in scope.owned and len(wire)==1
        assert compute.total()==100+RESERVATION  # SDK success is not allocation/expiry evidence.
        scope.begin_cleanup()
        await sdk.kill(request_timeout=1)
        assert await sdk.is_running(request_timeout=1) is False
        with pytest.raises(a.AdmissionRefused):await sdk.files.read('/home/user/pex-task/a',request_timeout=1)
        assert len(wire)==3 and len(pools)==2  # normal + streamed-file idle pool; both mocked.
    with pytest.raises(a.AdmissionRefused):scope.options()

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['connect_failure','retryable'])
async def test_actual_SDK_has_zero_retries_and_retains_unknown(bound,mode):
    scope,compute,wire,pools,behavior=bound;behavior['mode']=mode
    with scope:
        with pytest.raises(Exception):await create(scope,compute)
        assert len(wire)==1 and scope.uncertain and compute.total()==100+RESERVATION
        with pytest.raises(Exception):await create(scope,compute,'pex')
        assert len(wire)==1  # Never retry unknown or create replacement.

@pytest.mark.asyncio
async def test_actual_SDK_task_cancellation_retains_reservation(bound):
    scope,compute,wire,pools,behavior=bound;behavior['mode']='cancel'
    with scope:
        task=asyncio.create_task(create(scope,compute))
        while not wire and not task.done():await asyncio.sleep(0)
        if task.done():task.result()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert scope.uncertain and compute.total()==100+RESERVATION and not scope.owned

@pytest.mark.asyncio
async def test_late_mock_response_retained_before_SDK_constructor_failure(bound):
    scope,compute,wire,pools,behavior=bound;behavior['mode']='constructor_failure'
    with scope:
        with pytest.raises(Exception):await create(scope,compute)
        assert scope.owned=={'authored-baseline'} and compute.total()==100+RESERVATION
        # Caller must still clean the retained ID when no SDK handle was returned.
        scope.begin_cleanup();behavior['mode']='normal'
        await AsyncSandbox.kill('authored-baseline',api_key='AUTHORED-NOT-A-CREDENTIAL',
            proxy='http://authored.invalid:8888',retries=0,http_version='1.1',request_timeout=1)
        assert wire[-1][0]=='DELETE'

@pytest.mark.asyncio
async def test_transport_identity_rechecked_each_operation(bound,monkeypatch):
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute)
        monkeypatch.setenv('HTTPS_PROXY','http://changed.invalid:9')
        with pytest.raises(a.AdmissionRefused):await sdk.kill(request_timeout=1)
        assert len(wire)==1

@pytest.mark.asyncio
async def test_revocation_blocks_work_but_cleanup_only_retains_owned_authority(bound,monkeypatch):
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute)
        monkeypatch.setattr(a,'APPROVED_STAGED_GRANT',None)
        with pytest.raises(a.AdmissionRefused):await sdk.is_running(request_timeout=1)
        scope.begin_cleanup();await sdk.kill(request_timeout=1)
        assert await sdk.is_running(request_timeout=1) is False
        with pytest.raises(a.AdmissionRefused):scope.options()

@pytest.mark.asyncio
async def test_unfunded_create_and_unowned_route_never_reach_mock_wire(bound):
    scope,compute,wire,pools,behavior=bound
    with scope:
        with pytest.raises(a.AdmissionRefused):
            await AsyncSandbox.create(template=b.BASE_TEMPLATE,timeout=330,lifecycle={'on_timeout':'kill','auto_resume':False},
                metadata={'pex_pilot':scope.admitted.grant.run_id,'pex_arm':'baseline'},idempotency_key='authored-new-baseline',**scope.options())
        with pytest.raises(a.AdmissionRefused):
            await AsyncSandbox.kill('unowned',request_timeout=1,**scope.options())
        assert not wire and compute.total()==100

def test_atomic_claim_cannot_be_reused(bound):
    scope,*_=bound
    (Path(scope.admitted.grant.config_path).parent/'launch.claim').write_text('occupied')
    with pytest.raises(FileExistsError):scope.__enter__()
    assert scope.active is False
