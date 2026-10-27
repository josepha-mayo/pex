"""Separate one-shot supervisor candidate. Public live admission remains denied.

Call initialize_process before importing Strands in a fresh isolated process.
The private fixture path exercises owned full prompts/tools, never web startup.
"""
import sys


def initialize_process():
    if any(n == 'strands' or n.startswith('strands.') for n in sys.modules):
        raise RuntimeError('telemetry initialization must precede framework import')
    from opentelemetry import trace, metrics
    if type(trace.get_tracer_provider()).__name__ != 'ProxyTracerProvider':
        raise RuntimeError('ambient tracer provider refused')
    if type(metrics.get_meter_provider()).__name__ != '_ProxyMeterProvider':
        raise RuntimeError('ambient meter provider refused')
    trace.set_tracer_provider(trace.NoOpTracerProvider())
    metrics.set_meter_provider(metrics.NoOpMeterProvider())
    return {'trace': type(trace.get_tracer_provider()).__name__,
            'metrics': type(metrics.get_meter_provider()).__name__}


def invoke_live(*args, **kwargs):
    # No env flag, caller assertion or fixture receipt grants provider authority.
    raise RuntimeError('live_authority_pricing_budget_isolation_not_admitted')


def fixture_model(route, request, *, invocation_id, ledger, proposal=None):
    """PRIVATE authored-response testing only; exact invalid host/model/credential.

    No supplied callbacks/tools, no script corrections, no deterministic planner.
    Existing owned Strands protocol and evidence closures remain authoritative.
    """
    from opentelemetry import trace, metrics
    if type(trace.get_tracer_provider()) is not trace.NoOpTracerProvider or type(metrics.get_meter_provider()) is not metrics.NoOpMeterProvider:
        raise RuntimeError('clean process telemetry required')
    if route.endpoint != 'https://managed-fixture.invalid/v1/chat/completions' or route.model_id != 'fixture/exact-model':
        raise RuntimeError('authored fixture route only')
    from contextlib import aclosing
    from managed_chat import _ScopedCredential
    from managed_tool_chat import ManagedToolChatCandidate
    from strands_bridge import ManagedPEXModel

    class AccountedCandidate(ManagedToolChatCandidate):
        async def _execute_owned(self, invocation, credential):
            ledger.reserve(invocation.invocation_id, self.route)
            try:
                return await super()._execute_owned(invocation,credential)
            finally:
                ledger.settle(invocation.invocation_id,self.receipt(invocation.invocation_id))

    class FixtureProcessModel(ManagedPEXModel):
        async def invoke_async(self):
            return await self._invoke_owned_agent()

        async def stream(self,*args,**kwargs):
            credential = _ScopedCredential('fixture-no-provider-credential',route.fingerprint)
            async with aclosing(self._stream_owned(*args,credential=credential,**kwargs)) as stream:
                async for event in stream:
                    yield event

    model = FixtureProcessModel(route,request,invocation_id=invocation_id,proposal=proposal)
    model._candidate = AccountedCandidate(route,model.protocol)
    return model
