"""WIP production SDK/lifecycle seam behind the CLOSED staged grant.

Not a launcher or worker/supervisor approval. Defaults remain authored-only.
Qualified with actual SDK + local mocked transports, not a live VM/provider.
"""
import asyncio
import math
from staged_admission import AdmissionRefused
from staged_sdk_binding import SDKTransportBinding
from staged_lifecycle import StagedLifecycle
from staged_envelope import SETUP_SECONDS
from staged_async_remote import BoundedRemoteError
from e2b_transport import BASE_TEMPLATE


class SDKLifecycleAPI:
    def __init__(self,binding):
        if type(binding) is not SDKTransportBinding: raise AdmissionRefused('exact_SDK_binding_required')
        binding._check()
        self.binding=binding;self.raw_handles={};self.options=None;self.pending=set()

    async def create(self,**kwargs):
        self.binding._check()
        required={'template','timeout','lifecycle','metadata','idempotency_key','retries','request_timeout'}
        if (set(kwargs)!=required or kwargs['template']!=BASE_TEMPLATE or kwargs['timeout']!=330
                or kwargs['lifecycle']!={'on_timeout':'kill','auto_resume':False} or kwargs['retries']!=0
                or type(kwargs['request_timeout']) not in (int,float) or not math.isfinite(kwargs['request_timeout'])
                or not 0<kwargs['request_timeout']<=SETUP_SECONDS):
            raise AdmissionRefused('frozen_lifecycle_create_contract_required')
        # The binding already consumed an exclusive claim. Only this current
        # process obtains the original private key route, after cumulative reserve.
        self.options=self.binding.options()
        from e2b import AsyncSandbox
        options=dict(self.options);options.pop('retries')
        sdk=await AsyncSandbox.create(**kwargs,**options)
        self.raw_handles[sdk.sandbox_id]=sdk  # BEFORE facade validation can refuse.
        return self.binding.bind_owned(sdk)

    async def cleanup_owned(self):
        """Cleanup only, including IDs retained before SDK constructor failure."""
        self.binding.begin_cleanup()
        if not self.binding.owned: return
        if self.options is None: raise BoundedRemoteError('owned_cleanup_transport_identity_missing')
        from e2b import AsyncSandbox
        from e2b.exceptions import SandboxNotFoundException
        errors=[]
        async def bounded(call):
            remaining=self.binding.cleanup_deadline-self.binding.clock()
            if remaining<=0:raise BoundedRemoteError('shared_cleanup_window_exhausted')
            task=asyncio.create_task(call(min(15,remaining)));self.pending.add(task)
            def done(value):
                self.pending.discard(value)
                if not value.cancelled():value.exception()
            task.add_done_callback(done)
            finished,_=await asyncio.wait([task],timeout=remaining)
            if not finished:
                task.cancel();raise BoundedRemoteError('SDK_cleanup_cancellation_unconfirmed')
            return task.result()
        for sid in self.binding.owned-self.binding.stopped:
            try:
                await bounded(lambda timeout:AsyncSandbox.kill(sid,request_timeout=timeout,**self.options))
                try:await bounded(lambda timeout:AsyncSandbox.get_info(sid,request_timeout=timeout,**self.options))
                except SandboxNotFoundException:
                    if sid not in self.binding.stopped:raise BoundedRemoteError('owned_stop_unproven')
                else:raise BoundedRemoteError('owned_VM_still_present')
            except Exception:errors.append(sid)
        if errors:raise BoundedRemoteError('owned_SDK_cleanup_unconfirmed')


class AdmittedSDKLifecycle(StagedLifecycle):
    def __init__(self,binding,stage_public):
        api=SDKLifecycleAPI(binding)
        super().__init__(api,binding.compute,stage_public,run_id=binding.admitted.grant.run_id,
                         mode='closed-admitted-sdk',clock=binding.clock)

    async def cleanup(self):
        # Parent and adapter share ONE cleanup-only window, never separate15s
        # extensions and never extra admitted worker/VM time.
        self.api.binding.begin_cleanup()
        error=None
        try:await super().cleanup(deadline=self.api.binding.cleanup_deadline)
        except Exception as exc:error=exc
        try:await self.api.cleanup_owned()
        except Exception as exc:error=exc
        for arm,sid in self.api.binding.owned_by_arm.items():
            if sid in self.api.binding.stopped:
                self.raw_stopped.add(arm);self.unknown_creates.discard(arm)
        if error is not None or self.unknown_creates:
            raise BoundedRemoteError('staged_SDK_lifecycle_cleanup_or_cancellation_inconclusive') from None
