"""WIP pinned actual-SDK transport binding; no runner and CLOSED grant.

Only the ordinary same-process platform proxy and pinned CA are used. This
scope replaces the SDK's two async transport-factory references, not security
settings or environment variables. It must own a fresh isolated process: prior
SDK transport caches are refused. Both retry layers are disabled. Local mocked
wire qualification does NOT establish provider cancellation/expiry behavior.

The existing staged lifecycle/controller are still authored-only. A future
reviewed launcher must reserve ComputeBudget before create, retain owned handles,
perform bounded cleanup, and compose worker/supervisor admission separately.
"""
import asyncio
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from staged_admission import AdmissionRefused, check_authority, validate_transport, read_pin, sha, canonical
from cumulative_compute import ComputeBudget, RESERVATION
from e2b_transport import BASE_TEMPLATE

SDK_MODULES = ('e2b.api.client_async','e2b.envd.client_async','e2b.connection_config',
    'e2b.sandbox_async.main','e2b.sandbox_async.sandbox_api','e2b.retry',
    'e2b.api.client.client','pyqwest','pyqwest.httpx')
SDK_VERSIONS = {'e2b':'2.61.0','connectrpc':'0.12.1','pyqwest':'0.12.0','httpx':'0.28.1'}
_ACTIVE = None


def installed_source_pins():
    """Public code only. No clients, credentials, environment reads or network."""
    if any(importlib.metadata.version(k) != v for k,v in SDK_VERSIONS.items()):
        raise AdmissionRefused('pinned_SDK_versions_required')
    result={}
    for name in SDK_MODULES:
        p=Path(importlib.import_module(name).__file__).resolve()
        result[name]={'path':str(p),'sha256':sha(p.read_bytes())}
    return result


class SDKTransportBinding:
    def __init__(self, admitted, compute, *, clock=time.monotonic):
        # No SDK import, client, key or transport before immutable authority.
        check_authority(admitted)
        self.admitted=admitted;self.cfg=admitted.config();self.clock=clock
        validate_transport(self.cfg['network'])
        if self.cfg['sdk_sources'] != installed_source_pins():
            raise AdmissionRefused('installed_SDK_source_identity_changed')
        prior=json.loads(read_pin(self.cfg['predecessor'],private=True))
        if type(compute) is not ComputeBudget or compute.expected != (prior['compute_nano_usd'],self.cfg['predecessor']['sha256']):
            raise AdmissionRefused('pinned_cumulative_compute_ledger_required')
        self.compute=compute;self.active=False;self.cleanup_deadline=None
        self.creates=set();self.owned=set();self.owned_by_arm={};self.stopped=set();self.kill_attempted=set();self.uncertain=False;self.pools={}
        self.control=importlib.import_module('e2b.api.client_async')
        self.rpc=importlib.import_module('e2b.envd.client_async')
        self.original=None

    def __repr__(self): return '<private staged SDK ordinary transport binding>'

    def _check(self):
        if not self.active: raise AdmissionRefused('SDK_binding_closed')
        if sha(canonical(self.cfg)) != self.admitted.grant.config_sha256:
            raise AdmissionRefused('immutable_admitted_config_changed')
        validate_transport(self.cfg['network'])
        if self.cleanup_deadline is None: check_authority(self.admitted)
        elif self.clock() >= self.cleanup_deadline: raise AdmissionRefused('cleanup_only_window_exhausted')

    def __enter__(self):
        global _ACTIVE
        check_authority(self.admitted);validate_transport(self.cfg['network'])
        if (_ACTIVE is not None or self.active or self.original is not None
                or self.control._transports or self.control._pools or self.control._httpx_transports
                or self.rpc.get_pyqwest_transport is not self.control.get_pyqwest_transport):
            raise AdmissionRefused('fresh_exclusive_SDK_process_required')
        # Durable exclusive consumption BEFORE credential/client/provider use.
        claim=Path(self.admitted.grant.config_path).parent/'launch.claim'
        fd=os.open(claim,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            os.write(fd,canonical({'config_sha256':self.admitted.grant.config_sha256,
                                  'run_id':self.admitted.grant.run_id,'status':'claimed_not_success'}))
            os.fsync(fd)
        finally: os.close(fd)
        directory=os.open(claim.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
        self.original=self.control.get_pyqwest_transport
        _ACTIVE=self;self.active=True
        self.control.get_pyqwest_transport=self._factory
        self.rpc.get_pyqwest_transport=self._factory
        return self

    def __exit__(self,*unused):
        global _ACTIVE
        self.active=False
        if self.original is not None:
            self.control.get_pyqwest_transport=self.original
            self.rpc.get_pyqwest_transport=self.original
        if _ACTIVE is self: _ACTIVE=None
        # Cached wrappers keep this now-closed guard, never a reusable live pool.
        # No claim removal, refund, fallback, or assertion of remote termination.

    def begin_cleanup(self):
        if not self.active: raise AdmissionRefused('SDK_binding_closed')
        if self.cleanup_deadline is None: self.cleanup_deadline=self.clock()+15
        # One cleanup-only window, not extra admitted VM or worker lifetime.

    def options(self):
        """Private in-process SDK args, never serialize/log/transfer this value."""
        self._check()
        if self.cleanup_deadline is not None: raise AdmissionRefused('cleanup_cannot_read_credentials')
        key=read_pin(self.cfg['e2b_key'],private=True,limit=65536).decode().strip()
        if not key or '\n' in key or '\r' in key: raise AdmissionRefused('existing_private_key_invalid')
        return {'api_key':key,'proxy':os.environ['HTTPS_PROXY'],'domain':'e2b.app',
            'api_url':'https://api.e2b.app','debug':False,'retries':0,'http_version':'1.1'}

    def bind_owned(self, sdk):
        """Use exact owned control-plane not-found proof, never generic health 502.

        The SDK's native is_running treats ANY health 502 as False. Do not pass
        the raw SDK to BoundedAsyncRemote: this restricted owned facade supplies
        stronger stop evidence and exposes no connect/resume/extend operations.
        """
        self._check()
        from e2b import AsyncSandbox
        if type(sdk) is not AsyncSandbox or sdk.sandbox_id not in self.owned:
            raise AdmissionRefused('owned_SDK_response_handle_required')
        owner=self
        class Owned:
            def __repr__(self): return '<owned staged SDK facade>'
            @property
            def sandbox_id(self): return sdk.sandbox_id
            @property
            def commands(self): return sdk.commands
            @property
            def files(self): return sdk.files
            async def get_info(self,**kwargs): return await sdk.get_info(**kwargs)
            async def kill(self,**kwargs): return await sdk.kill(**kwargs)
            async def is_running(self,**kwargs):
                from e2b.exceptions import SandboxNotFoundException
                try: await sdk.get_info(**kwargs)
                except SandboxNotFoundException:
                    if sdk.sandbox_id not in owner.stopped:
                        raise AdmissionRefused('owned_control_plane_stop_unproven') from None
                    return False
                return True  # Existing/paused is not stopped; elapsed time is not proof.
        return Owned()

    def _factory(self, proxy, read_timeout=None, *, http_version='2', retry_connect=True):
        self._check()
        # SDK retries=0 disables control-plane retry. Returning a raw guarded
        # pool here bypasses the SDK ConnectionRetryTransport entirely, NOT the
        # ordinary platform proxy. Never fall back to a direct/default pool.
        if (proxy is None or proxy.auth is not None or proxy.headers or sha(proxy.url.encode()) != self.cfg['network']['proxy_sha256']
                or http_version != '1.1' or read_timeout not in (None,60.0)):
            raise AdmissionRefused('exact_ordinary_proxy_SDK_contract_required')
        if read_timeout not in self.pools:
            from pyqwest import HTTPTransport,HTTPVersion,Proxy
            ca=read_pin(self.cfg['network']['ca'],limit=4*1024*1024)
            inner=HTTPTransport(tls_ca_cert=ca,tls_include_system_certs=False,
                proxy=Proxy(os.environ['HTTPS_PROXY'],no_proxy=''),http_version=HTTPVersion.HTTP1,
                follow_redirects=False,connect_timeout=15,read_timeout=read_timeout,
                pool_max_idle_per_host=0,max_connections_per_address=2,enable_otel=False)
            owner=self
            class Guard:
                async def execute(self,request): return await owner._execute(inner,request)
            self.pools[read_timeout]=Guard()
        return self.pools[read_timeout]

    async def _execute(self,inner,request):
        self._check()
        u=urlsplit(request.url);method=request.method
        if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or u.fragment:
            raise AdmissionRefused('SDK_endpoint_refused')
        creating=False
        if u.hostname=='api.e2b.app':
            if method=='POST' and u.path=='/v2/sandboxes' and not u.query:
                check_authority(self.admitted)
                if self.cleanup_deadline is not None or self.uncertain: raise AdmissionRefused('uncertain_or_cleanup_create_refused')
                if self.owned-self.stopped: raise AdmissionRefused('prior_owned_VM_stop_unproven')
                raw=request.content
                if type(raw) is not bytes or len(raw)>8192: raise AdmissionRefused('bounded_create_body_required')
                body=json.loads(raw);meta=body.get('metadata',{});arm=meta.get('pex_arm')
                identity=self.admitted.grant.run_id+'-'+str(arm)
                expected={'templateID':BASE_TEMPLATE,'timeout':330,'autoPause':False,'autoResume':{'enabled':False},
                          'metadata':{'pex_pilot':self.admitted.grant.run_id,'pex_arm':arm},'envVars':{}}
                if (body!=expected or arm not in ('baseline','pex') or arm in self.creates or len(self.creates)>=2
                        or (not self.creates and arm!='baseline')
                        or request.headers.get('idempotency-key')!=identity):
                    raise AdmissionRefused('frozen_single_create_body_required')
                # Existing durable reservation is required BEFORE wire dispatch.
                self.compute.total()
                if self.compute.db.execute('SELECT charged,state FROM calls WHERE id=?',(identity,)).fetchall()!=[(RESERVATION,'uncertain')]:
                    raise AdmissionRefused('durable_full_create_reservation_required')
                self.creates.add(arm);self.uncertain=True;creating=True
            elif method in ('GET','DELETE') and not u.query and u.path.startswith('/sandboxes/') and u.path.count('/')==2:
                if u.path.split('/')[-1] not in self.owned: raise AdmissionRefused('only_owned_control_plane_cleanup_or_info')
                if method=='DELETE':self.kill_attempted.add(u.path.split('/')[-1])
            else: raise AdmissionRefused('SDK_control_plane_route_refused')
        else:
            # Only domains/identities learned from this scope's actual create
            # response. An arbitrary SDK connect/reconnect cannot add ownership.
            identifier=request.headers.get('e2b-sandbox-id')
            owned_direct=any(u.hostname==f'49983-{x}.e2b.app' for x in self.owned)
            if not (owned_direct or (u.hostname=='sandbox.e2b.app' and identifier in self.owned)):
                raise AdmissionRefused('owned_sandbox_endpoint_required')
            if self.cleanup_deadline is not None and (method!='GET' or u.path!='/health'):
                raise AdmissionRefused('cleanup_only_no_worker_or_resume')
        response=await inner.execute(request)
        if u.hostname=='api.e2b.app' and method=='GET' and response.status==404:
            sid=u.path.split('/')[-1]
            if sid in self.owned and sid in self.kill_attempted:self.stopped.add(sid)
        elif u.hostname!='api.e2b.app' and u.path=='/health' and response.status==502:
            # The SDK would turn every 502 into False. Close the response and
            # refuse that inference even if it happens to say 'not found'. Only
            # an authenticated GET of the exact owned control-plane ID counts.
            async with response: pass
            raise AdmissionRefused('generic_health_502_is_not_owned_stop_proof')
        if creating:
            # Retain ownership BEFORE SDK parsing/constructor can fail. Unknown
            # or canceled responses retain the generic reservation permanently.
            chunks=[];size=0
            async with response:
                async for chunk in response.content:
                    size+=len(chunk)
                    if size>65536: raise AdmissionRefused('create_response_bound')
                    chunks.append(bytes(chunk))
            data=b''.join(chunks)
            if 200<=response.status<300:
                value=json.loads(data);sid=value.get('sandboxID')
                if not isinstance(sid,str) or not re.fullmatch('[a-z0-9-]{1,128}',sid):
                    raise AdmissionRefused('owned_response_identity_unproven')
                self.owned.add(sid);self.owned_by_arm[arm]=sid
                if value.get('domain') not in (None,'e2b.app'): raise AdmissionRefused('owned_response_domain_changed')
                # A late response establishes ownership, not successful cancellation
                # or permission for another create. Preserve its full reservation.
                self.uncertain=bool(asyncio.current_task().cancelling())
            from pyqwest import Response
            return Response(status=response.status,headers=response.headers,content=data)
        return response
