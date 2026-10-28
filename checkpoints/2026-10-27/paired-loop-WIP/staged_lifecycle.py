"""WIP production-shaped async lifecycle; authored fake SDK ONLY.

No credential files, live entry, retry, replacement VM or budget increase.
A future live binding must separately admit fresh predecessor/source/config
identities and the ordinary transport; this constructor cannot do that.
"""
import asyncio
import inspect
import re
import time
from e2b_transport import BASE_TEMPLATE, ROOT
from staged_envelope import VM_SECONDS, SETUP_SECONDS
from staged_async_remote import BoundedAsyncRemote, BoundedRemoteError, validate_provider_lifetime


class StagedLifecycle:
    def __init__(self, sdk_api, compute, stage_public, *, run_id, mode='authored-only', clock=time.monotonic):
        if (mode != 'authored-only' or getattr(sdk_api,'AUTHORED_FAKE_ONLY',False) is not True
                or getattr(sdk_api,'__module__','').startswith('e2b')):
            raise PermissionError('staged_live_lifecycle_not_admitted')
        if not inspect.iscoroutinefunction(stage_public) or not re.fullmatch('[a-z0-9-]{1,128}',run_id):
            raise ValueError('bounded_async_public_stager_and_run_identity_required')
        self.api=sdk_api;self.compute=compute;self.stage_public=stage_public;self.run_id=run_id;self.clock=clock
        self.attempts=set();self.remotes={};self.pending=set();self.uncertain=False;self.deadlines={}
        self.provider_evidence={};self.unknown_create=False

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
        identity=self.run_id+'-'+c
        self.compute.reserve(identity)
        self.attempts.add(c);self.deadlines[c]=deadline
        async def create():
            sdk=await self.api.create(template=BASE_TEMPLATE,timeout=VM_SECONDS,
                lifecycle={'on_timeout':'kill','auto_resume':False},
                metadata={'pex_pilot':self.run_id,'pex_arm':c},idempotency_key=identity,
                api_key='AUTHORED-NOT-A-CREDENTIAL',retries=0,
                request_timeout=max(.001,setup_deadline-self.clock()))
            # Retain even a late owned response so cleanup can still find it.
            remote=BoundedAsyncRemote(sdk,vm_deadline=deadline,clock=self.clock)
            self.remotes[c]=remote
            if self.uncertain:
                try: await self._bounded(remote.close(),min(deadline,self.clock()+15))
                except Exception: pass
                raise BoundedRemoteError('late_create_after_uncertainty_no_resume')
            return sdk,remote
        try:
            sdk,remote=await self._bounded(create(),setup_deadline)
            info=await self._bounded(sdk.get_info(request_timeout=max(.001,setup_deadline-self.clock())),setup_deadline)
            evidence=validate_provider_lifetime(info)
            self.provider_evidence[c]=evidence
            # Only exact provider allocation/lifetime validation settles generic
            # create reservation. Cleanup success alone never refunds uncertainty.
            self.compute.settle_verified_allocation(identity,cpu=info.cpu_count,memory_mb=info.memory_mb,max_seconds=VM_SECONDS)
            remote.set_scope_deadline(setup_deadline)
            try:
                await self._bounded(self.stage_public(arm,remote),setup_deadline)
            finally:
                await remote.end_scope()
            return remote
        except BaseException:
            self.uncertain=True
            if c not in self.remotes: self.unknown_create=True
            # The owner's finally path calls cleanup; don't make setup timeout
            # wait indefinitely for SDK cancellation/cleanup inside this handler.
            raise

    async def cleanup(self):
        errors=[]
        cleanup_deadline=min([self.clock()+15,*self.deadlines.values()])
        for task in list(self.pending): task.cancel()
        if self.pending:
            _,still=await asyncio.wait(list(self.pending),timeout=max(0,min(1,cleanup_deadline-self.clock())))
            if still: errors.append('lifecycle_cancellation_unconfirmed')
        for remote in self.remotes.values():
            try: await self._bounded(remote.close(),cleanup_deadline)
            except Exception: errors.append('owned_VM_cleanup_unconfirmed')
        if self.unknown_create: errors.append('unknown_create_outcome_no_refund')
        if errors: raise BoundedRemoteError('staged_lifecycle_cleanup_unconfirmed')
