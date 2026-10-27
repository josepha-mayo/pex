"""Explicit private, supervisor-only successor diagnostic; no worker or VM access.

Uses remaining original supervisor dollars after a pinned closed predecessor.
The historical request must explicitly mark missing controller evidence uncertain.
No diagnostic output is ever dispatched as a continuation.
"""
import hashlib
import importlib
import json
import os
from contextlib import aclosing
from datetime import datetime, timezone
from pathlib import Path

APPROVAL = 'Sentinel_9df859db703081919786cd38c9678f05'
CONTINUATION = '2026-10-27T13:37:00Z'
APPROVED_RETRY_REF = 'Sentinel_9b519763a9dc8191b55d0519a82d9c52'
# Fresh user direction to continue PEX; original scoped dollar approval above
# remains authoritative. This admits only the synthetic supervisor diagnostic.
SUCCESSOR_SUPERVISOR_POOL = 300000000
ALLOCATION_PROFILE = '350m-350m-300m-v1'
END = '2026-10-27T22:15:00+00:00' # internal window, not new user spending
SOURCES = ('supervisor_diagnostic','cumulative_budget','accounting','managed_chat','managed_tool_chat','strands_bridge','tool_protocol','pilot_process','process_adapter','pex_protocol.actions','pex_protocol.supervisor','pex_supervisor.loop','pex_supervisor.evidence_tools','pex_supervisor.evidence_observations')


def load(path, digest):
    if APPROVED_RETRY_REF is None:raise PermissionError("explicit_retry_approval_pending")
    from pilot_process import _private_bytes
    from cumulative_budget import audit_closed,include_supervisor_diagnostics
    raw=_private_bytes(path,65536)
    if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('independent diagnostic digest required')
    c=json.loads(raw)
    fields={'schema','allocation_profile','retry_approval_ref','approval_ref','continuation_ref','expires_at','predecessor','prior_diagnostics','request_path','request_sha256','key_path','key_sha256','pricing_provenance_sha256','output_dir','source_sha256','platform_proxy'}
    if set(c)!=fields or c['retry_approval_ref']!=APPROVED_RETRY_REF or c['allocation_profile']!=ALLOCATION_PROFILE or c['schema']!=1 or c['approval_ref']!=APPROVAL or c['continuation_ref']!=CONTINUATION:
        raise ValueError('diagnostic admission refused')
    expiry=datetime.fromisoformat(c['expires_at'])
    if expiry.tzinfo is None or not datetime.now(timezone.utc)<expiry<=datetime.fromisoformat(END):
        raise ValueError('diagnostic expired')
    if set(c['source_sha256'])!=set(SOURCES):raise ValueError('source set')
    for name,d in c['source_sha256'].items():
        if hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest()!=d:raise ValueError('source identity changed')
    if set(c['predecessor'])!={'worker_path','worker_sha256','supervisor_path','supervisor_sha256'}:raise ValueError('predecessor binding required')
    audit=include_supervisor_diagnostics(audit_closed(**c['predecessor']),c['prior_diagnostics'],allocation_profile=c['allocation_profile'])
    for name in ('key','request'):
        if hashlib.sha256(_private_bytes(c[name+'_path'],65536)).hexdigest()!=c[name+'_sha256']:raise ValueError(name+' changed')
    from managed_chat import _PilotProxyBinding
    binding=c['platform_proxy']
    _PilotProxyBinding(**binding) # exact supplied proxy/CA only
    if hashlib.sha256(os.environ.get('HTTPS_PROXY','').encode()).hexdigest()!=binding['proxy_sha256'] or os.environ.get('SSL_CERT_FILE')!=binding['ca_path'] or hashlib.sha256(Path(binding['ca_path']).read_bytes()).hexdigest()!=binding['ca_sha256']:
        raise ValueError('provided platform proxy or CA changed')
    output=Path(c['output_dir'])
    if output.parent!=Path(path).parent or output.name!='diagnostic-output' or output.exists():raise ValueError('fresh private diagnostic output required')
    return c,audit


async def run(path,digest):
    c,audit=load(path,digest)
    from pilot_process import _private_bytes,pilot_routes
    from pex_protocol.supervisor import SupervisorRequest
    from managed_chat import _ScopedCredential,_PilotProxyBinding
    from managed_tool_chat import ManagedToolChatCandidate
    from strands_bridge import ManagedPEXModel
    from accounting import Ledger
    request=SupervisorRequest.model_validate_json(_private_bytes(c['request_path'],65536))
    if 'PARTIAL HISTORICAL' not in request.notes or request.scores.features.get('verification',{}).get('acceptance_status')!='uncertain':
        raise ValueError('partial historical uncertainty required')
    output=Path(c['output_dir']);output.mkdir(mode=0o700)
    route=pilot_routes()[0]
    ledger=Ledger(output/'supervisor-diagnostic.sqlite',budget=SUCCESSOR_SUPERVISOR_POOL-audit['charged_nano_usd']['supervisor'],input_rate=300,output_rate=900,route=route,currency='USD',pricing_provenance_sha256=c['pricing_provenance_sha256'],input_token_bound=262144,output_token_bound=4096)
    maximum=min(6,audit['remaining_attempts']['supervisor'])
    def validate():
        if datetime.now(timezone.utc)>=datetime.fromisoformat(c['expires_at']):raise ValueError('diagnostic expired')
        if len(ledger.summary())>=maximum:raise ValueError('diagnostic attempt cap')
    class Candidate(ManagedToolChatCandidate):
        async def _execute_owned(self,invocation,credential):
            validate();ledger.reserve(invocation.invocation_id,self.route)
            try:return await super()._execute_owned(invocation,credential)
            finally:ledger.settle(invocation.invocation_id,self.receipt(invocation.invocation_id))
    class Model(ManagedPEXModel):
        async def invoke_async(self):return await self._invoke_owned_agent()
        async def stream(self,*args,**kwargs):
            raw=_private_bytes(c['key_path'],65536)
            if hashlib.sha256(raw).hexdigest()!=c['key_sha256']:raise ValueError('key changed')
            credential=_ScopedCredential(raw.decode('ascii').strip(),route.fingerprint)
            async with aclosing(self._stream_owned(*args,credential=credential,**kwargs)) as stream:
                async for event in stream:yield event
    model=Model(route,request,invocation_id='partial-historical-diagnostic-01')
    model._candidate=Candidate(route,model.protocol)
    model._candidate._pilot_proxy_binding=_PilotProxyBinding(**c['platform_proxy'])
    status='inconclusive';error=None
    try:
        result=await model.invoke_async()
        (output/'decision-private.json').write_text(result.structured_output.model_dump_json())
        status='real_supervisor_protocol_completed'
    except Exception as exc:error=type(exc).__name__
    finally:
        summary=ledger.summary();ledger.close()
        report={'status':status,'error_category':error,'classification':'partial_historical_diagnostic_not_paired_benchmark','attempts':len(summary),'charged_nano_usd':sum(x['charged'] for x in summary),'prior_supervisor_retained_nano_usd':audit['charged_nano_usd']['supervisor'],'cumulative_nebius_nano_usd':sum(audit['charged_nano_usd'].values())+sum(x['charged'] for x in summary),'worker_or_VM_dispatches':0,'continuation_dispatches':0,'allocation_profile':ALLOCATION_PROFILE,'receipts':[{'outcome':r.outcome,'attempts':r.attempts} for r in model.receipts]}
        (output/'report.json').write_text(json.dumps(report,sort_keys=True))
        for file in output.iterdir():file.chmod(0o600)
    return report
