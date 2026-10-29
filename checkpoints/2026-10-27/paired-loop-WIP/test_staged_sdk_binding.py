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
from cumulative_compute import ComputeBudget,allocation_bounds
from staged_envelope import VM_SECONDS
RESERVATION=allocation_bounds(VM_SECONDS)[0]
from e2b import AsyncSandbox
from pyqwest import Response,Headers,Request

@pytest.fixture
def bound(candidate,monkeypatch,tmp_path,request):
    cfg,freeze=candidate
    cfg['sdk_sources']=b.installed_source_pins()
    key=tmp_path/'SYNTHETIC-KEY';key.write_bytes(b'AUTHORED-NOT-A-CREDENTIAL');key.chmod(0o600)
    cfg['e2b_key']={'path':str(key),'sha256':a.sha(key.read_bytes())}
    if getattr(request,'param',None) in ('stockroom','composition'):
        task=Path(__file__).resolve().parents[1]/'pex-hard-task-candidate-20261027-1421/MANIFEST.json'
        cfg['task']={'path':str(task),'sha256':a.sha(task.read_bytes())}
        cfg['nebius_key']=dict(cfg['e2b_key'])  # Synthetic authored key, not a real provider key.
    if getattr(request,'param',None)=='composition':
        from staged_composition import source_pins
        root=Path(__file__).resolve().parents[1]
        binary=root/'opencode-qualification-20261027/install/node_modules/@opencode/cli-linux-x64/bin/opencode'
        modules=root/'opencode-qualification-20261027/mock/node_modules'
        plugin=modules/'@opencode/plugin/package.json'
        cfg['cli']={'binary':{'path':str(binary),'sha256':a.sha(binary.read_bytes())},'modules_path':str(modules),
                    'plugin_package':{'path':str(plugin),'sha256':a.sha(plugin.read_bytes())}}
        cfg['sources']=source_pins()
    raw,grant=freeze();monkeypatch.setattr(a,'APPROVED_STAGED_GRANT',a.GrantGate.identity(grant))
    admitted=a.load(grant)
    import e2b.api.client_async as c
    for n in ('_transports','_pools','_httpx_transports'):monkeypatch.setattr(c,n,{})
    compute=ComputeBudget(tmp_path/'compute.sqlite',prior_upper_bound_nano_usd=100,evidence_sha256=cfg['predecessor']['sha256'],cap_nano_usd=cfg['profile']['compute_cap'],vm_seconds=VM_SECONDS)
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
                while not behavior['finish'].is_set():
                    try:await behavior['finish'].wait()
                    except asyncio.CancelledError:behavior['cancelled'].set()
            p=urlsplit(request.url).path
            if p=='/v2/sandboxes':
                body=json.loads(request.content)
                value={'templateID':b.BASE_TEMPLATE,'sandboxID':'authored-'+body['metadata']['pex_arm'],
                       'clientID':'authored','envdVersion':'0.5.7','envdAccessToken':'SYNTHETIC-ENVD','domain':'e2b.app'}
                if mode=='constructor_failure':value['envdVersion']='invalid'
                return Response(status=201,headers=Headers({'content-type':'application/json'}),content=json.dumps(value).encode())
            if p.endswith('/Start'):
                from protobuf import Oneof
                from e2b.envd.process import process_pb as pb
                values=[pb.StartResponse(event=pb.ProcessEvent(event=Oneof('start',pb.ProcessEvent.StartEvent(pid=123)))),
                    pb.StartResponse(event=pb.ProcessEvent(event=Oneof('data',pb.ProcessEvent.DataEvent(output=Oneof('stdout',b'authored stream'))))),
                    pb.StartResponse(event=pb.ProcessEvent(event=Oneof('end',pb.ProcessEvent.EndEvent(exit_code=behavior.get('command_exit_code',0),exited=True))))]
                def frame(raw,flag=0):return bytes([flag])+len(raw).to_bytes(4,'big')+raw
                body=b''.join(frame(v.to_json().encode()) for v in values)+frame(b'{}',2)
                return Response(status=200,headers=Headers({'content-type':'application/connect+json'}),content=body)
            if p.endswith('/SendSignal'):
                if behavior.get('slow_dead_kill'):await asyncio.sleep(1.1)
                return Response(status=200,headers=Headers({'content-type':'application/json'}),content=b'{}')
            if p.endswith('/List'):return Response(status=200,headers=Headers({'content-type':'application/json'}),content=b'{"processes":[]}')
            if request.method=='DELETE':return Response(status=204)
            if p=='/files' and request.method=='GET' and behavior.get('file_connect_timeout_once') and not behavior.get('file_timeout_injected'):
                import httpx
                behavior['file_timeout_injected']=True
                raise httpx.ConnectTimeout('AUTHORED')
            if p=='/health':return Response(status=502,content=b'{"message":"sandbox not found"}')
            if p.startswith('/sandboxes/'):
                if mode=='ambiguous_info':return Response(status=502,content=b'{"message":"unreachable"}')
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
    sdk=await AsyncSandbox.create(template=b.BASE_TEMPLATE,timeout=VM_SECONDS,
        lifecycle={'on_timeout':'kill','auto_resume':False},metadata={'pex_pilot':scope.admitted.grant.run_id,'pex_arm':arm},
        idempotency_key=identity,request_timeout=1,**scope.options())
    return scope.bind_owned(sdk)

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
            await AsyncSandbox.create(template=b.BASE_TEMPLATE,timeout=VM_SECONDS,lifecycle={'on_timeout':'kill','auto_resume':False},
                metadata={'pex_pilot':scope.admitted.grant.run_id,'pex_arm':'baseline'},idempotency_key='authored-new-baseline',**scope.options())
        with pytest.raises(a.AdmissionRefused):
            await AsyncSandbox.kill('unowned',request_timeout=1,**scope.options())
        assert not wire and compute.total()==100

def test_atomic_claim_cannot_be_reused(bound):
    scope,*_=bound
    (Path(scope.admitted.grant.config_path).parent/'launch.claim').write_text('occupied')
    with pytest.raises(FileExistsError):scope.__enter__()
    assert scope.active is False


@pytest.mark.parametrize('proxy',[
    'http://authored-user:authored-pass@proxy.example:8888',
    'http://authored-user:p%40ss%3Aword@proxy.example:8888/',
    'https://proxy.example:443',
])
def test_actual_SDK_preserves_explicit_string_proxy_without_auth_split(proxy):
    # Synthetic FORMAT probe only. Never inspect or copy actual platform values.
    from e2b.connection_config import ConnectionConfig
    from e2b.api import proxy_to_config
    config=ConnectionConfig(api_key='SYNTHETIC',proxy=proxy,domain='e2b.app',debug=False,retries=0,http_version='1.1')
    parsed=proxy_to_config(config.proxy)
    assert parsed.url==proxy and parsed.auth is None and parsed.headers==()
    assert a.sha(parsed.url.encode())==a.sha(proxy.encode())

@pytest.mark.asyncio
async def test_actual_RPC_factory_uses_same_guarded_mock_transport(bound):
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute)
        assert await sdk.commands.list(request_timeout=1)==[]
        assert urlsplit(wire[-1][1]).path.endswith('/List') and len(wire)==2
        # The SDK REST, health, filesystem and ConnectRPC factories share the
        # same guarded pool for their common options, with no direct fallback.
        assert len(pools)==2

@pytest.mark.asyncio
async def test_actual_SDK_suppressed_cancel_returns_bounded_keeps_late_owned_id(bound):
    scope,compute,wire,pools,behavior=bound
    behavior.update(mode='suppress_cancel',finish=asyncio.Event(),cancelled=asyncio.Event())
    with scope:
        opts=scope.options()
        task=asyncio.create_task(create(scope,compute))
        try:
            done,_=await asyncio.wait([task],timeout=.03)
            assert not done and len(wire)==1
            task.cancel()
            await asyncio.wait_for(behavior['cancelled'].wait(),timeout=.2)
            # Orchestrator returns without waiting for SDK cancellation. The
            # SDK's internal wait_for can remain pending; not remote stop proof.
            assert not task.done() and scope.uncertain and compute.total()==100+RESERVATION
            behavior['finish'].set()
            await asyncio.wait([task],timeout=.3)
            assert task.done()
            if not task.cancelled():task.result()
            assert scope.owned=={'authored-baseline'} and scope.uncertain
            assert compute.total()==100+RESERVATION
            behavior['mode']='normal';scope.begin_cleanup()
            await AsyncSandbox.kill('authored-baseline',request_timeout=1,**opts)
            assert wire[-1][0]=='DELETE'
        finally:
            behavior['finish'].set()
            await asyncio.wait([task],timeout=.3)

@pytest.mark.asyncio
async def test_actual_RPC_cancel_bound_poisoned_bridge_not_stop_claim(bound):
    from staged_async_remote import BoundedAsyncRemote,BoundedRemoteError
    import time
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute)
        behavior.update(mode='suppress_cancel',finish=asyncio.Event(),cancelled=asyncio.Event())
        remote=BoundedAsyncRemote(sdk,vm_deadline=time.monotonic()+2)
        remote.set_scope_deadline(time.monotonic()+.03)
        started=time.monotonic()
        try:
            with pytest.raises(BoundedRemoteError):
                await asyncio.to_thread(remote._call,lambda:sdk.commands.list(request_timeout=1))
            assert time.monotonic()-started < .5 and remote.poisoned
            assert len(wire)==2 and compute.total()==100+RESERVATION
        finally:
            behavior['finish'].set()
            await remote.end_scope()
            behavior['mode']='normal';await remote.close()
            assert remote.closed

def test_mutated_binding_config_refused_before_credential_read(bound):
    scope,*_=bound
    with scope:
        scope.cfg['profile']['equal_worker_fresh']+=1
        with pytest.raises(a.AdmissionRefused,match='immutable'):scope.options()


@pytest.mark.asyncio
async def test_raw_SDK_generic_502_cannot_mark_bounded_remote_closed(bound):
    import time
    from staged_async_remote import BoundedAsyncRemote
    scope,compute,wire,pools,behavior=bound
    with scope:
        identity=scope.admitted.grant.run_id+'-baseline';compute.reserve(identity)
        raw=await AsyncSandbox.create(template=b.BASE_TEMPLATE,timeout=VM_SECONDS,lifecycle={'on_timeout':'kill','auto_resume':False},
            metadata={'pex_pilot':scope.admitted.grant.run_id,'pex_arm':'baseline'},idempotency_key=identity,**scope.options())
        remote=BoundedAsyncRemote(raw,vm_deadline=time.monotonic()+2)
        with pytest.raises(a.AdmissionRefused,match='502'):await remote.close()
        assert not remote.closed and not remote.cleanup_evidence['stopped_confirmed'] and not scope.stopped
        assert compute.total()==100+RESERVATION
        # Same owned raw handle can be wrapped; no connect, resume or replacement.
        safer=BoundedAsyncRemote(scope.bind_owned(raw),vm_deadline=remote.vm_deadline)
        await safer.close()
        assert safer.closed and safer.cleanup_evidence['stopped_confirmed']
        assert scope.stopped==scope.owned

@pytest.mark.asyncio
async def test_control_plane_ambiguity_cannot_confirm_cleanup_or_next_create(bound):
    import time
    from staged_async_remote import BoundedAsyncRemote
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute);remote=BoundedAsyncRemote(sdk,vm_deadline=time.monotonic()+2)
        behavior['mode']='ambiguous_info'
        with pytest.raises(Exception):await remote.close()
        assert not remote.closed and not remote.cleanup_evidence['stopped_confirmed'] and not scope.stopped
        n=len(wire)
        with pytest.raises(a.AdmissionRefused,match='stop_unproven'):await create(scope,compute,'pex')
        assert len(wire)==n

@pytest.mark.asyncio
async def test_second_arm_requires_first_owned_control_plane_stop(bound):
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute)
        identity=scope.admitted.grant.run_id+'-pex';compute.reserve(identity)
        kwargs=dict(template=b.BASE_TEMPLATE,timeout=VM_SECONDS,lifecycle={'on_timeout':'kill','auto_resume':False},
            metadata={'pex_pilot':scope.admitted.grant.run_id,'pex_arm':'pex'},idempotency_key=identity,**scope.options())
        with pytest.raises(a.AdmissionRefused,match='stop_unproven'):await AsyncSandbox.create(**kwargs)
        await sdk.kill(request_timeout=1);assert await sdk.is_running(request_timeout=1) is False
        second=await AsyncSandbox.create(**kwargs)
        assert second.sandbox_id in scope.owned and len(scope.creates)==2


@pytest.mark.asyncio
async def test_actual_SDK_streamed_command_callbacks_and_file_reader(bound):
    import time
    from staged_async_remote import BoundedAsyncRemote
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute)
        remote=BoundedAsyncRemote(sdk,vm_deadline=time.monotonic()+3)
        remote.set_scope_deadline(time.monotonic()+1)
        result=await asyncio.to_thread(remote.run,'printf authored',.5)
        assert result=={'stdout':'authored stream','stderr':'','exit_code':0}
        assert await asyncio.to_thread(remote.read,'public.txt')=='authored file'
        assert any(urlsplit(x[1]).path.endswith('/Start') for x in wire)
        assert not any(urlsplit(x[1]).path.endswith('/SendSignal') for x in wire)
        assert any(urlsplit(x[1]).path=='/files' for x in wire)
        await remote.end_scope();await remote.close()
        assert remote.closed and remote.cleanup_evidence['stopped_confirmed']


@pytest.mark.asyncio
@pytest.mark.parametrize('exit_code',[0,7])
async def test_actual_SDK_terminal_event_avoids_redundant_slow_signal_request(bound,exit_code):
    import time
    from staged_async_remote import BoundedAsyncRemote
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute);behavior.update(slow_dead_kill=True,command_exit_code=exit_code)
        remote=BoundedAsyncRemote(sdk,vm_deadline=time.monotonic()+5)
        remote.set_scope_deadline(time.monotonic()+3)
        result=await asyncio.to_thread(remote.run,'printf AUTHORED',2)
        assert result['exit_code']==exit_code and result['stdout']=='authored stream'
        await remote.end_scope()
        assert not remote.poisoned
        assert not any('/SendSignal' in url for _,url,_ in wire)
        remote.set_scope_deadline(time.monotonic()+1);await remote.end_scope()
        await remote.close();assert remote.closed


@pytest.mark.asyncio
async def test_actual_SDK_completed_file_connect_timeout_does_not_block_next_read(bound):
    import time
    from staged_async_remote import BoundedAsyncRemote,BoundedRemoteError
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute);behavior['file_connect_timeout_once']=True
        remote=BoundedAsyncRemote(sdk,vm_deadline=time.monotonic()+4)
        remote.set_scope_deadline(time.monotonic()+2)
        with pytest.raises(BoundedRemoteError,match='read_only_connection_timeout_no_state_change'):
            await asyncio.to_thread(remote.read,'safe.txt')
        assert not remote.poisoned
        assert await asyncio.to_thread(remote.read,'safe.txt')=='authored file'
        assert len(scope.creates)==1
        await remote.end_scope();await remote.close();assert remote.closed
