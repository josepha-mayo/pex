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
    if getattr(request,'param',None) in ('stockroom','composition','composition-v3','composition-asyncpool','composition-wirepool'):
        task=(Path(__file__).resolve().parents[1]/('runtime-private/pex-pilot-20261027/stockroom-v3-candidate-20261029/MANIFEST.json' if getattr(request,'param',None)=='composition-v3' else 'pex-hard-task-candidate-20261027-1421/MANIFEST.json'))
        if getattr(request,'param',None)=='composition-wirepool':task=Path(__file__).resolve().parents[1]/'pex-wirepool-benchmark-WIP-20261030/MANIFEST.json'
        if getattr(request,'param',None)=='composition-asyncpool':task=Path(__file__).resolve().parents[1]/'pex-asyncpool-benchmark-WIP-20261030/MANIFEST.json'
        if not task.is_file():pytest.skip('private frozen v3 fixture not distributed with source')
        cfg['task']={'path':str(task),'sha256':a.sha(task.read_bytes())}
        cfg['nebius_key']=dict(cfg['e2b_key'])  # Synthetic authored key, not a real provider key.
    if getattr(request,'param',None) in ('composition','composition-v3','composition-asyncpool','composition-wirepool'):
        from staged_composition import source_pins
        root=Path(__file__).resolve().parents[1]
        binary=root/'opencode-qualification-20261027/install/node_modules/@opencode/cli-linux-x64/bin/opencode'
        modules=root/'opencode-qualification-20261027/mock/node_modules'
        plugin=modules/'@opencode/plugin/package.json'
        cfg['cli']={'binary':{'path':str(binary),'sha256':a.sha(binary.read_bytes())},'modules_path':str(modules),
                    'plugin_package':{'path':str(plugin),'sha256':a.sha(plugin.read_bytes())}}
        cfg['sources']=source_pins()
    is_asyncpool=getattr(request,'param',None)=='composition-asyncpool'
    is_wirepool=getattr(request,'param',None)=='composition-wirepool'
    is_new=is_asyncpool or is_wirepool
    if is_new:
        if is_wirepool:import wirepool_history as h
        else:import asyncpool_history as h
        cfg['run_id']=('wirepool' if is_wirepool else 'asyncpool')+'-staged-pair-authored'
        if is_wirepool:cfg['profile']['provider_cap']=h.PROVIDER_ENVELOPE
        cfg['profile']['compute_cap']=h.COMPUTE_ENVELOPE
        prior=json.loads(Path(cfg['predecessor']['path']).read_bytes())
        for name in h.required_predecessors(a.REQUIRED_PREDECESSORS)-set(prior['ledgers']):
            path=tmp_path/name;path.write_bytes(b'AUTHORED-HISTORY');path.chmod(0o600)
            prior['ledgers'][name]={'path':str(path),'sha256':a.sha(path.read_bytes())}
        prior.update(provider_nano_usd=h.PRIOR_PROVIDER,compute_nano_usd=h.PRIOR_COMPUTE)
        path=Path(cfg['predecessor']['path']);path.write_bytes(a.canonical(prior));cfg['predecessor']['sha256']=a.sha(path.read_bytes())
    raw,grant=freeze();monkeypatch.setattr(a,'APPROVED_WIREPOOL_GRANT' if is_wirepool else 'APPROVED_ASYNCPOOL_GRANT' if is_asyncpool else 'APPROVED_STAGED_GRANT',a.GrantGate.identity(grant))
    admitted=a.load(grant)
    import e2b.api.client_async as c
    for n in ('_transports','_pools','_httpx_transports'):monkeypatch.setattr(c,n,{})
    compute=ComputeBudget(tmp_path/'compute.sqlite',prior_upper_bound_nano_usd=h.PRIOR_COMPUTE if is_new else 100,evidence_sha256=cfg['predecessor']['sha256'],cap_nano_usd=cfg['profile']['compute_cap'],vm_seconds=VM_SECONDS)
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
            if p=='/files' and request.method=='POST' and behavior.get('buffered_write_case'):
                from email.parser import BytesParser
                content_type=request.headers.get('content-type')
                assert content_type.startswith('multipart/form-data;')
                raw=request.content
                if not isinstance(raw,bytes):raw=b''.join([chunk async for chunk in raw])
                message=BytesParser().parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
                parts=[(part.get_param('name',header='content-disposition'),part.get_filename(),part.get_payload(decode=True)) for part in message.get_payload()]
                behavior.setdefault('multipart_attempts',[]).append((request.url,parts))
                behavior['write_attempts']=behavior.get('write_attempts',0)+1
                case=behavior['buffered_write_case']
                if case=='connect_always' or (case=='connect_once' and behavior['write_attempts']==1):
                    from pyqwest import ConnectTimeout
                    raise ConnectTimeout('AUTHORED predispatch')
                if case=='read_timeout':raise TimeoutError('AUTHORED afterdispatch ambiguity')
                return Response(status=200,headers=Headers({'content-type':'application/json'}),content=b'[{"name":"safe.txt","path":"/home/user/pex-task/safe.txt","type":"file"}]')
            if p=='/health' and behavior.get('buffered_write_case'):
                return Response(status=200,content=b'{}')
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
        receipt=json.loads((Path(scope.admitted.grant.config_path).parent/'owned-vm-baseline.json').read_text())
        assert receipt['sandbox_id']=='authored-baseline'
        # Caller must still clean the retained ID when no SDK handle was returned.
        scope.begin_cleanup();behavior['mode']='normal'
        await AsyncSandbox.kill('authored-baseline',api_key='AUTHORED-NOT-A-CREDENTIAL',
            proxy='http://authored.invalid:8888',retries=0,http_version='1.1',request_timeout=1)
        assert wire[-1][0]=='DELETE'

@pytest.mark.asyncio
async def test_owned_identity_is_private_fsynced_and_secret_free_before_handle(bound,monkeypatch):
    from datetime import datetime
    import os,stat
    scope,compute,wire,pools,behavior=bound
    synced=[];original=os.fsync
    def sync(fd):
        synced.append(stat.S_ISDIR(os.fstat(fd).st_mode));original(fd)
    monkeypatch.setattr(os,'fsync',sync)
    with scope:
        synced.clear();sdk=await create(scope,compute)
        path=Path(scope.admitted.grant.config_path).parent/'owned-vm-baseline.json'
        raw=path.read_bytes();receipt=json.loads(raw)
        assert synced==[False,True]
        assert path.stat().st_mode&0o777==0o600
        assert receipt['schema']=='pex.owned-sandbox-identity.v1'
        assert receipt['sandbox_id']==sdk.sandbox_id=='authored-baseline'
        assert receipt['config_sha256']==scope.admitted.grant.config_sha256
        assert receipt['run_id']==scope.admitted.grant.run_id and receipt['arm']=='baseline'
        assert receipt['metadata']=={'pex_pilot':scope.admitted.grant.run_id,'pex_arm':'baseline'}
        assert receipt['template_id']==b.BASE_TEMPLATE and receipt['timeout_seconds']==VM_SECONDS
        assert receipt['create_idempotency_key']==scope.admitted.grant.run_id+'-baseline'
        assert datetime.fromisoformat(receipt['create_started_at_utc'])<=datetime.fromisoformat(receipt['response_received_at_utc'])
        assert len(receipt['create_response_sha256'])==64
        assert receipt['ownership_only_not_cleanup_or_allocation_proof'] is True
        assert b'SYNTHETIC-ENVD' not in raw and b'AUTHORED-NOT-A-CREDENTIAL' not in raw
        assert b'api_key' not in raw and b'envdAccessToken' not in raw

@pytest.mark.asyncio
@pytest.mark.parametrize('existing_kind',['file','symlink'])
async def test_owned_identity_never_overwrites_existing_private_evidence(bound,tmp_path,existing_kind):
    scope,compute,wire,pools,behavior=bound
    receipt=Path(scope.admitted.grant.config_path).parent/'owned-vm-baseline.json'
    target=tmp_path/'untouched';target.write_bytes(b'existing-evidence')
    if existing_kind=='symlink':receipt.symlink_to(target)
    else:receipt.write_bytes(b'existing-evidence')
    with scope:
        with pytest.raises(FileExistsError):await create(scope,compute)
        assert scope.owned=={'authored-baseline'} and scope.uncertain
        assert target.read_bytes()==receipt.read_bytes()==b'existing-evidence'
        assert len(wire)==1 and compute.total()==100+RESERVATION
        with pytest.raises(a.AdmissionRefused):await create(scope,compute,'pex')
        assert len(wire)==1

@pytest.mark.asyncio
async def test_owned_receipt_fsync_failure_retains_in_memory_cleanup_identity(bound,monkeypatch):
    import os
    scope,compute,wire,pools,behavior=bound
    with scope:
        original=os.fsync
        def fail(fd):raise OSError('authored durability failure')
        monkeypatch.setattr(os,'fsync',fail)
        with pytest.raises(OSError,match='authored durability'):await create(scope,compute)
        monkeypatch.setattr(os,'fsync',original)
        assert scope.owned=={'authored-baseline'} and scope.uncertain
        scope.begin_cleanup()
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


@pytest.mark.asyncio
@pytest.mark.parametrize('bound',['composition-asyncpool','composition-wirepool'],indirect=True)
@pytest.mark.parametrize('batch',[False,True])
@pytest.mark.parametrize('case',['connect_once','connect_always','read_timeout'])
async def test_actual_SDK_buffered_write_predispatch_only_retry(bound,batch,case):
    import time
    from staged_async_remote import BoundedAsyncRemote,BoundedRemoteError
    scope,compute,wire,pools,behavior=bound
    with scope:
        sdk=await create(scope,compute);behavior['buffered_write_case']=case
        task='wirepool' if scope.cfg['run_id'].startswith('wirepool-') else 'asyncpool'
        remote=BoundedAsyncRemote(sdk,vm_deadline=time.monotonic()+5,evaluation_task=task)
        deadline=time.monotonic()+3;remote.set_scope_deadline(deadline)
        operation=(lambda:remote._write_absolute_files({'/tmp/pex-'+task+'-evaluation-'+'a'*32+'/candidate/safe.txt':b'AUTHORED'})) if batch else (lambda:remote.write('safe.txt','AUTHORED'))
        if case=='connect_once':await asyncio.to_thread(operation)
        else:
            with pytest.raises(BoundedRemoteError):await asyncio.to_thread(operation)
        assert behavior['write_attempts']==(1 if case=='read_timeout' else 2)
        assert all(x==behavior['multipart_attempts'][0]for x in behavior['multipart_attempts'])
        assert behavior['multipart_attempts'][0][1][0][2]==b'AUTHORED'
        expected_path=('/tmp/pex-'+task+'-evaluation-'+'a'*32+'/candidate/safe.txt') if batch else '/home/user/pex-task/safe.txt'
        assert expected_path in str(behavior['multipart_attempts'][0])
        assert remote.poisoned==(case=='read_timeout')
        assert remote.deadline==deadline and len(scope.creates)==1
        assert remote.diagnostics['buffered_file_connect_retries']==(0 if case=='read_timeout' else 1)
        assert all(p['connect_timeout']==30 for p in pools)
        await remote.end_scope()
        if not remote.poisoned:
            remote.set_scope_deadline(time.monotonic()+1)
            observed=await asyncio.to_thread(remote.run,'printf AUTHORED',1)
            assert observed['exit_code']==0
            await remote.end_scope()
        await remote.close();assert remote.closed
