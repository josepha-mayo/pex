"""WIP production-shaped async lifecycle; authored fake SDK ONLY.

No credential files, live entry, retry, replacement VM or budget increase.
A future live binding must separately admit fresh predecessor/source/config
identities and the ordinary transport; this constructor cannot do that.
"""
import asyncio
import inspect
import re
import time
from e2b_transport import BASE_TEMPLATE
from staged_envelope import VM_SECONDS, SETUP_SECONDS
from staged_async_remote import BoundedAsyncRemote, BoundedRemoteError, validate_provider_lifetime


class StagedLifecycle:
    def __init__(self, sdk_api, compute, stage_public, *, run_id, mode='authored-only', clock=time.monotonic):
        if mode == 'closed-admitted-sdk':
            from staged_sdk_lifecycle import SDKLifecycleAPI
            if type(sdk_api) is not SDKLifecycleAPI or compute is not sdk_api.binding.compute or run_id != sdk_api.binding.admitted.grant.run_id:
                raise PermissionError('exact_closed_admitted_SDK_binding_required')
            sdk_api.binding._check()
        elif (mode != 'authored-only' or getattr(sdk_api,'AUTHORED_FAKE_ONLY',False) is not True
                or getattr(sdk_api,'__module__','').startswith('e2b')):
            raise PermissionError('staged_live_lifecycle_not_admitted')
        self.mode=mode
        if not inspect.iscoroutinefunction(stage_public) or not re.fullmatch('[a-z0-9-]{1,128}',run_id):
            raise ValueError('bounded_async_public_stager_and_run_identity_required')
        self.api=sdk_api;self.compute=compute;self.stage_public=stage_public;self.run_id=run_id;self.clock=clock
        self.attempts=set();self.remotes={};self.pending=set();self.uncertain=False;self.deadlines={}
        self.provider_evidence={};self.unknown_creates=set();self.setup_timing={}
        self.raw_owned={};self.raw_stopped=set();self.cleanup_evidence={}

    async def _bounded(self, awaitable, deadline):
        task=asyncio.create_task(awaitable);self.pending.add(task)
        def done(value):
            self.pending.discard(value)
            if not value.cancelled(): value.exception()
        task.add_done_callback(done)
        try:
            done,_=await asyncio.wait([task],timeout=max(0,deadline-self.clock()))
            if not done: raise TimeoutError('lifecycle_deadline')
            return task.result()
        except BaseException:
            task.cancel();self.uncertain=True
            # No uncertain create reservation is ever reduced here.
            raise

    async def prepare(self, arm, *, deadline):
        c=arm['condition']
        if (self.uncertain or c not in ('baseline','pex') or c in self.attempts or len(self.attempts)>=2
                or any(not r.closed for r in self.remotes.values())):
            raise BoundedRemoteError('sequential_single_create_admission_refused')
        if deadline-self.clock() <= 0:
            raise BoundedRemoteError('VM_deadline_already_exhausted')
        setup_deadline=min(deadline,self.clock()+SETUP_SECONDS)
        started=self.clock()
        timing={'schema':'pex.lifecycle-setup-timing.v1','setup_cap_seconds':SETUP_SECONDS,
            'logical_operations':[],'setup_complete':False,'wire_request_count':None}
        self.setup_timing[c]=timing
        async def timed(name,awaitable):
            before=self.clock();row={'operation':name,'started_after_seconds':before-started,'completed':False}
            timing['logical_operations'].append(row)
            try:
                value=await self._bounded(awaitable,setup_deadline);row['completed']=True;return value
            finally:row['elapsed_seconds']=self.clock()-before
        identity=self.run_id+'-'+c
        self.compute.reserve(identity)
        self.attempts.add(c);self.deadlines[c]=deadline
        async def create():
            sdk=await self.api.create(template=BASE_TEMPLATE,timeout=VM_SECONDS,
                lifecycle={'on_timeout':'kill','auto_resume':False},
                metadata={'pex_pilot':self.run_id,'pex_arm':c},idempotency_key=identity,
                **({'api_key':'AUTHORED-NOT-A-CREDENTIAL'} if self.mode=='authored-only' else {}),retries=0,
                request_timeout=max(.001,setup_deadline-self.clock()))
            # Store the raw owned handle BEFORE validating a worker deadline.
            # A late response must remain cleanable even when no worker wrapper
            # can be constructed. Cleanup never grants a continuation or refund.
            self.raw_owned[c]=sdk;self.unknown_creates.discard(c)
            if self.uncertain or deadline<=self.clock():
                self.uncertain=True
                try: await self._cleanup_raw(c,self.clock()+15)
                except Exception: pass
                raise BoundedRemoteError('late_create_after_deadline_or_uncertainty_no_resume')
            remote=BoundedAsyncRemote(sdk,vm_deadline=deadline,clock=self.clock)
            self.remotes[c]=remote
            return sdk,remote
        try:
            sdk,remote=await timed('create_owned_VM',create())
            info=await timed('verify_allocation_lifetime',sdk.get_info(request_timeout=max(.001,setup_deadline-self.clock())))
            evidence=validate_provider_lifetime(info)
            self.provider_evidence[c]=evidence
            # Only exact provider allocation/lifetime validation settles generic
            # create reservation. Cleanup success alone never refunds uncertainty.
            self.compute.settle_verified_allocation(identity,cpu=info.cpu_count,memory_mb=info.memory_mb,max_seconds=VM_SECONDS)
            remote.set_scope_deadline(setup_deadline)
            try:
                await timed('public_batch_setup',self.stage_public(arm,remote))
            finally:
                await remote.end_scope()
            timing['setup_complete']=True
            return remote
        except BaseException:
            self.uncertain=True
            if c not in self.raw_owned: self.unknown_creates.add(c)
            # The owner's finally path calls cleanup; don't make setup timeout
            # wait indefinitely for SDK cancellation/cleanup inside this handler.
            raise
        finally:
            timing['elapsed_seconds']=self.clock()-started
            timing['setup_deadline_extended']=False

    async def _cleanup_raw(self, condition, cleanup_deadline):
        if condition in self.raw_stopped: return
        sdk=self.raw_owned[condition]
        proof=self.cleanup_evidence.setdefault(condition,{'kill_attempted':False,'stopped_confirmed':False,
            'cleanup_only_after_worker_deadline':self.clock()>=self.deadlines[condition]})
        async def stop():
            remaining=cleanup_deadline-self.clock()
            if remaining<=0: raise BoundedRemoteError('cleanup_only_window_exhausted')
            proof['kill_attempted']=True
            await sdk.kill(request_timeout=min(15,remaining))
            remaining=cleanup_deadline-self.clock()
            if remaining<=0: raise BoundedRemoteError('cleanup_stop_proof_window_exhausted')
            if await sdk.is_running(request_timeout=min(15,remaining)) is not False:
                raise BoundedRemoteError('owned_VM_still_running')
            proof['stopped_confirmed']=True
            self.raw_stopped.add(condition)
            if condition in self.remotes: self.remotes[condition].closed=True
        await self._bounded(stop(),cleanup_deadline)

    async def cleanup(self, *, deadline=None):
        errors=[]
        # Explicit cleanup-only window: closed arms' old worker deadlines do not
        # prevent killing another owned VM. No create/worker/review/resume/extend
        # is permitted here, including after a worker deadline has expired.
        cleanup_deadline=min(self.clock()+15,deadline) if deadline is not None else self.clock()+15
        for task in list(self.pending): task.cancel()
        if self.pending:
            _,still=await asyncio.wait(list(self.pending),timeout=max(0,min(1,cleanup_deadline-self.clock())))
            if still: errors.append('lifecycle_cancellation_unconfirmed')
        for c in list(self.raw_owned):
            remote=self.remotes.get(c)
            if remote is not None and remote.closed:
                self.raw_stopped.add(c)
                continue
            if remote is not None:
                try: await self._bounded(remote.end_scope(),min(cleanup_deadline,self.clock()+1))
                except Exception: errors.append('operation_cancellation_unconfirmed')
            # Always attempt independent owned kill, even after drain ambiguity.
            try: await self._cleanup_raw(c,cleanup_deadline)
            except Exception: errors.append('owned_VM_cleanup_unconfirmed')
        if self.unknown_creates: errors.append('unknown_create_outcome_no_refund')
        if errors: raise BoundedRemoteError('staged_lifecycle_cleanup_unconfirmed')
