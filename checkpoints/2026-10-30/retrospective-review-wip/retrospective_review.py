"""Default-CLOSED snapshot-only diagnostic; never a paired/live-worker review.

Reuse existing owned semantic models, tool schemas, citations and accounting.
No E2B import/key, worker adapter/control, candidate execution or grading.
"""
import base64
from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

QUALIFICATION='RETROSPECTIVE_CODE_REVIEW_NOT_PAIRED_BENCHMARK'
APPROVED_DIAGNOSTIC=None
FRESH_NANO_USD=350_000_000
PRIOR_PROVIDER=2_809_730_700
PRIOR_COMPUTE=610_245_000
ALLOWED_TOOLS={'inspect_acceptance','inspect_public_snapshot','get_goal'}
REQUIRED_SOURCES={'retrospective_review','successor_supervisor','accounting','managed_chat','managed_tool_chat','strands_bridge','tool_protocol','stockroom_request','review','pex_protocol.actions','pex_protocol.enums','pex_protocol.goal','pex_protocol.session','pex_protocol.supervisor','pex_protocol.redaction','pex_supervisor.loop','pex_supervisor.evidence_tools','pex_supervisor.evidence_observations'}


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read_pin(pin,limit=16*1024*1024,private=False):
    if type(pin)is not dict or set(pin)!={'path','sha256'}:raise ValueError('exact_pin_required')
    p=Path(pin['path'])
    if not p.is_absolute() or p.resolve()!=p or not p.is_file() or p.stat().st_size>limit:raise ValueError('bounded_regular_pin_required')
    if private and p.stat().st_mode&0o077:raise ValueError('private_pin_required')
    raw=p.read_bytes()
    if sha(raw)!=pin['sha256']:raise ValueError('pin_changed')
    return raw

def write_new(path,value):
    raw=canonical(value);fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
    return {'path':str(path),'sha256':sha(raw)}


def build_request(checkpoint_raw,*,run_id,created_utc):
    """Pure public export decoding. No source execution or invented test receipt."""
    from stockroom_request import snapshot_path_allowed,snapshot_digest,validate_public_snapshot
    from pex_protocol.enums import HarnessType,SessionStatus,EventType
    from pex_protocol.session import HarnessSession,HarnessEvent
    from pex_protocol.goal import Goal
    from pex_protocol.supervisor import SupervisorRequest
    d=json.loads(checkpoint_raw)
    if (d.get('schema')!='pex.public-pre-intervention-checkpoint.v1' or d.get('condition')!='baseline'
        or d.get('capture_boundary')!='after_phase0_before_monitor_before_any_protected_upload'
        or set(d.get('public_export',{}))!={'schema','files'}
        or d['public_export']['schema']!='pex.stockroom-export.v1'):raise ValueError('authentic_phase0_public_export_required')
    if type(run_id)is not str or not re.fullmatch('retrospective-[a-z0-9-]{1,65}',run_id):raise ValueError('diagnostic_namespace_required')
    when=datetime.fromisoformat(created_utc)
    if when.tzinfo is None:raise ValueError('explicit_UTC_required')
    files={}
    for name,encoded in d['public_export']['files'].items():
        if snapshot_path_allowed(name):
            raw=base64.b64decode(encoded,validate=True)
            files[name]={'content':raw.decode('utf8'),'sha256':sha(raw)}
    snapshot=validate_public_snapshot({'schema':'pex.public-candidate-snapshot.v1','files':files,'snapshot_sha256':snapshot_digest(files)})
    if snapshot['snapshot_sha256']!=d['snapshot_sha256']:raise ValueError('original_snapshot_identity_changed')
    gid=run_id+'-goal';pid=run_id+'-diagnostic'
    session=HarnessSession(id=run_id,harness_type=HarnessType.SYNTHETIC,vendor_session_id=run_id,project_id=pid,goal_id=gid,
        status=SessionStatus.STOPPED,cwd=None,repo=None,external_url=None,
        metadata={'qualification':QUALIFICATION,'synthetic_envelope_only':'archived candidate code is authentic, model responses must be real',
                  'live_worker':False,'source_config_sha256':d['config_sha256'],'source_arm':'baseline','source_phase':0})
    goal=Goal(id=gid,project_id=pid,title='Retrospective static review of authentic captured code',objective=files['TASK.md']['content'],
        constraints=['Snapshot-only retrospective code review; no live worker or intervention.',
          'Only supplied public TASK and captured public source; no hidden grading, filesystem, execution or web.',
          'Public test results were not captured here; execution verification and acceptance remain unknown.'],
        non_goals=['Paired benchmark, worker correction, PEX benefit or execution-success claims'],created_at=when,updated_at=when)
    event=HarnessEvent(event_id=run_id+'-review-trigger',ts=when,harness_type=HarnessType.SYNTHETIC,session_id=run_id,project_id=pid,goal_id=gid,
        event_type=EventType.STOP,message_delta='Retrospective diagnostic trigger for an archived phase0 public snapshot. This is not a new live worker stop.',
        metadata={'retrospective':True,'source_sha256':sha(checkpoint_raw)})
    request=SupervisorRequest(session=session,goal=goal,event=event,recent_events=[],supervisor_decision_mode='supervisor_model_only',
        notes=QUALIFICATION+'. No execution, live failure/correction, or benefit claim. No worker controls exist.')
    request.scores.features={'public_candidate_snapshot':snapshot,'verification':{'status':'unavailable','acceptance_status':'uncertain',
        'reason':'phase0 public-test result not retained in this artifact; no tests executed for this diagnostic'}}
    return request


@dataclass(frozen=True)
class Grant:
    run_id:str
    config_sha256:str
    request_sha256:str
    predecessor_sha256:str
    sources_sha256:str


def inspect(config_raw,grant):
    """Closed before credentials, ledger, claim, transport or model construction."""
    if APPROVED_DIAGNOSTIC is None or type(grant)is not Grant or grant.run_id!=APPROVED_DIAGNOSTIC:raise PermissionError('retrospective_root_review_pending')
    if sha(config_raw)!=grant.config_sha256:raise ValueError('exact_config_required')
    cfg=json.loads(config_raw)
    fields={'schema','qualification','run_id','approval_ref','expires_utc','created_utc','source_checkpoint','source_backup','request',
            'predecessor','sources','key','platform_proxy','pricing_provenance_sha256','output_dir','fresh_nano_usd','max_attempts'}
    if set(cfg)!=fields or cfg['schema']!='pex.retrospective-config.v1' or cfg['qualification']!=QUALIFICATION or cfg['run_id']!=grant.run_id:raise ValueError('diagnostic_config_scope')
    if cfg['fresh_nano_usd']!=FRESH_NANO_USD or cfg['max_attempts']!=12 or not cfg['approval_ref']:raise ValueError('diagnostic_exact_budget')
    expiry=datetime.fromisoformat(cfg['expires_utc'])
    if expiry.tzinfo is None or (expiry-datetime.now(timezone.utc)).total_seconds()<400:raise ValueError('diagnostic_expired')
    raw=read_pin(cfg['source_checkpoint'],private=True);backup=read_pin(cfg['source_backup'],private=True)
    if raw!=backup:raise ValueError('original_backup_mismatch')
    request=build_request(raw,run_id=cfg['run_id'],created_utc=cfg['created_utc'])
    serialized=request.model_dump_json().encode()
    if read_pin(cfg['request'],private=True)!=serialized or sha(serialized)!=grant.request_sha256:raise ValueError('exact_request_required')
    pred_raw=read_pin(cfg['predecessor'],private=True)
    if sha(pred_raw)!=grant.predecessor_sha256:raise ValueError('predecessor_binding')
    pred=json.loads(pred_raw)
    if pred['provider_nano_usd']!=PRIOR_PROVIDER or pred['compute_nano_usd']!=PRIOR_COMPUTE:raise ValueError('historical_charges_retained')
    if not pred.get('ledgers'):raise ValueError('historical_evidence_required')
    for pin in pred['ledgers'].values():read_pin(pin,private=True,limit=32*1024*1024)
    if sha(canonical(cfg['sources']))!=grant.sources_sha256:raise ValueError('source_manifest_binding')
    if set(cfg['sources'])!=REQUIRED_SOURCES:raise ValueError('exact_source_set_required')
    for name,pin in cfg['sources'].items():
        if str(Path(importlib.import_module(name).__file__).resolve())!=pin['path']:raise ValueError('executed_source_path_changed')
        read_pin(pin)
    from pex_supervisor.evidence_tools import select_evidence_tool_names
    if set(select_evidence_tool_names(request))-ALLOWED_TOOLS:raise ValueError('no_external_evidence_tools')
    net=cfg['platform_proxy'];proxy=os.environ.get('HTTPS_PROXY','');parts=urlsplit(proxy)
    if parts.scheme not in ('http','https') or not parts.hostname or parts.path not in ('','/') or parts.query or parts.fragment:raise ValueError('ordinary_proxy_shape')
    if set(net)!={'proxy_sha256','ca_path','ca_sha256'} or sha(proxy.encode())!=net['proxy_sha256'] or not proxy:raise ValueError('ordinary_proxy_identity')
    if os.environ.get('SSL_CERT_FILE')!=net['ca_path']:raise ValueError('ordinary_CA_identity')
    read_pin({'path':net['ca_path'],'sha256':net['ca_sha256']})
    return cfg,request,pred


# Existing owned semantic model path is reused, not its old live admission.
from successor_supervisor import ManagedSuccessor,_routes,_telemetry


class RetrospectiveRuntime(ManagedSuccessor):
    def __init__(self,config_raw,grant):
        cfg,request,pred=inspect(config_raw,grant)
        _telemetry()
        self.raw=config_raw;self.grant=grant;self.cfg=cfg;self.request=request;self.closed=False
        root=Path(cfg['output_dir'])
        if not root.is_absolute() or root.resolve()!=root or root.name!=grant.run_id or root.exists() or root.parent.stat().st_mode&0o077:raise ValueError('fresh_private_diagnostic_output_required')
        root.mkdir(mode=0o700);self.root=root
        write_new(root/'launch.claim',{'config_sha256':grant.config_sha256,'request_sha256':grant.request_sha256,'qualification':QUALIFICATION})
        from accounting import Ledger
        self.routes=_routes()
        self.config={'key':cfg['key'],'platform_proxy':cfg['platform_proxy']}
        self.objective=request.goal.objective
        self.ledger=Ledger(root/'supervisor.sqlite',budget=PRIOR_PROVIDER+FRESH_NANO_USD,input_rate=300,output_rate=900,
            route=self.routes[0],currency='USD',pricing_provenance_sha256=cfg['pricing_provenance_sha256'],
            input_token_bound=262144,output_token_bound=4096,approved_routes=self.routes,max_attempts=12,
            prior_charged_nano_usd=PRIOR_PROVIDER,predecessor_sha256=grant.predecessor_sha256)
        self.ledger.db.execute('CREATE TABLE retrospective_binding(request TEXT PRIMARY KEY,planner_created INTEGER,verifier_created INTEGER)')
        self.ledger.db.execute('INSERT INTO retrospective_binding VALUES (?,0,0)',(grant.request_sha256,))
        (root/'wire').mkdir(mode=0o700)
        write_new(root/'admission.json',{'qualification':QUALIFICATION,'grant':vars(grant),'prior_provider_nano_usd':PRIOR_PROVIDER,
            'fresh_supervisor_envelope_nano_usd':FRESH_NANO_USD,'compute_retained_nano_usd':PRIOR_COMPUTE,'VMs_created':0,
            'worker_actions_available':False,'execution_verification_available':False})

    def revalidate(self):
        if self.closed:raise ValueError('retrospective_closed')
        cfg,request,_=inspect(self.raw,self.grant)
        if cfg!=self.cfg or request.model_dump_json()!=self.request.model_dump_json():raise ValueError('retrospective_inputs_changed')
        self.ledger._validate_stored();_telemetry()
        return self.config

    def _bind(self,role,request,proposal):
        self.revalidate()
        if role not in ('planner','verifier') or (role=='planner')!=(proposal is None):raise ValueError('role_proposal_mismatch')
        if sha(request.model_dump_json().encode())!=self.grant.request_sha256:raise ValueError('retrospective_request_changed')
        if proposal is not None and (proposal.session_id!=request.session.id or proposal.goal_id!=request.goal.id):raise ValueError('retrospective_proposal_identity')
        db=self.ledger.db;db.execute('BEGIN IMMEDIATE')
        try:
            rows=db.execute('SELECT request,planner_created,verifier_created FROM retrospective_binding').fetchall()
            required=(self.grant.request_sha256,0,0) if role=='planner' else (self.grant.request_sha256,1,0)
            if rows!=[required]:raise ValueError('single_main_then_optional_verifier_required')
            column='planner_created' if role=='planner' else 'verifier_created'
            db.execute('UPDATE retrospective_binding SET '+column+'=1');db.execute('COMMIT')
        except BaseException:db.execute('ROLLBACK');raise
        from pex_protocol.supervisor import supervisor_request_digest
        return supervisor_request_digest(request)

    def archive_wire(self,kind,invocation_id,route,body,status):
        self.revalidate()
        if kind not in ('request','response') or route not in self.routes or type(body)is not bytes:raise ValueError('bounded_wire_scope')
        limit=route.limits.max_request_bytes if kind=='request' else route.limits.max_response_bytes
        if len(body)>limit or (status is not None if kind=='request' else status!=200):raise ValueError('wire_bounds')
        if self.ledger.db.execute('SELECT route,state FROM calls WHERE id=?',(invocation_id,)).fetchall()!=[(route.fingerprint,'reserved_uncertain')]:raise ValueError('wire_without_reservation')
        return write_new(self.root/'wire'/(sha(canonical([invocation_id,kind]))+'.json'),{
            'schema':'pex.retrospective-wire.v1','qualification':QUALIFICATION,'config_sha256':self.grant.config_sha256,
            'request_sha256':self.grant.request_sha256,'kind':kind,'invocation_id':invocation_id,'role':route.role,
            'route_fingerprint':route.fingerprint,'model':route.model_id,'endpoint':route.endpoint,'HTTP_status':status,
            'body_sha256':sha(body),'raw_body_base64':base64.b64encode(body).decode(),'headers_captured':False})

    def summary(self):
        rows=self.ledger.summary()
        return {'qualification':QUALIFICATION,'prior_provider_nano_usd':PRIOR_PROVIDER,
            'fresh_supervisor_charged_nano_usd':sum(r['charged']for r in rows),
            'provider_cumulative_nano_usd':PRIOR_PROVIDER+sum(r['charged']for r in rows),
            'compute_retained_nano_usd':PRIOR_COMPUTE,'calls':rows,'VMs_created':0,'worker_interventions':0}

    def close(self):
        if self.closed:return
        write_new(self.root/'accounting-terminal.json',self.summary())
        self.ledger.close();self.closed=True


async def review_once(runtime):
    """Real main+optional verifier, with NO action dispatcher or worker."""
    from pex_supervisor import loop
    from pex_protocol.actions import InterventionType
    from review import evidence
    request=runtime.request
    result={'qualification':QUALIFICATION,'request_sha256':runtime.grant.request_sha256,'execution_verified':False,
            'worker_intervention':False,'paired_comparison':False,'benefit_claim':False}
    planner=runtime.model_factory('planner',request,None)
    decision=(await planner.invoke_async()).structured_output
    if type(decision)is not loop.SupervisorDecision:raise ValueError('main_schema_mismatch')
    refs,valid,tools=evidence(request,planner,decision,'planner')
    result['main']={'decision':decision.model_dump(mode='json'),'receipts':list(planner.receipts),
        'observations':[o.model_dump(mode='json')for o in planner.observations],'resolved_evidence_refs':refs,'lineage_valid':valid}
    proposal=loop._decision_proposal(decision)
    if not proposal['evidence'] and valid:proposal['evidence']=refs
    action=loop._action_from_proposal(request,proposal)
    if action.type==InterventionType.NOOP:result['status']='main_noop_no_verifier'
    elif not valid:result['status']='main_evidence_unqualified_no_verifier'
    else:
        # Proposal is reviewed as data only. No action is executed, regardless of type.
        verifier=runtime.model_factory('verifier',request,action)
        verdict=(await verifier.invoke_async()).structured_output
        if type(verdict)is not loop.IndependentVerifierDecision:raise ValueError('verifier_schema_mismatch')
        vrefs,vvalid,vtools=evidence(request,verifier,verdict,'verifier')
        result['verifier']={'verdict':verdict.model_dump(mode='json'),'receipts':list(verifier.receipts),
            'observations':[o.model_dump(mode='json')for o in verifier.observations],'resolved_evidence_refs':vrefs,
            'lineage_valid':vvalid,'snapshot_cited':'inspect_public_snapshot' in vtools}
        result['status']='retrospective_review_complete_not_execution_verified'
    write_new(runtime.root/'review-result.json',result)
    return result
