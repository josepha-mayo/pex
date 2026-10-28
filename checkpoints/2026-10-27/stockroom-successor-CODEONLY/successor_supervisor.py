"""Default-CLOSED successor managed supervisor. No legacy loader changes.
Only root may pin an exact future approval after user approval; no env/config flag
can open the None gate. Authored tests patch it in memory with synthetic approval.
Admission constructs no transport and performs no model/provider call.
"""
import hashlib
import importlib
from importlib.metadata import version
import json
import os
from pathlib import Path
from contextlib import aclosing
from datetime import datetime,timezone
import uuid
from urllib.parse import urlsplit
from successor_budget import SUPERVISOR_CUMULATIVE, PRIOR_SUPERVISOR

SUCCESSOR_ENTRY_SCHEMA='pex.managed-supervisor-successor.v1'
APPROVED_RETRY_REF=None  # One authorized pair consumed; no additional dispatch.
ENDPOINT='https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions'
MODEL='nvidia/nemotron-3-super-120b-a12b'
WORKER='nebius/deepseek-ai/DeepSeek-V4.1-Flash-1017'
PACKAGES={'strands-agents':'1.53.0','httpx':'0.28.1','opentelemetry-api':'1.45.1'}
SOURCE_MODULES=('successor_budget','successor_supervisor','successor_admission','stockroom_task','stockroom_request','process_adapter','accounting','managed_chat','managed_tool_chat','strands_bridge','tool_protocol','pex_protocol.actions','pex_protocol.supervisor','pex_supervisor.loop','pex_supervisor.evidence_tools','pex_supervisor.evidence_observations')

def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError('duplicate_successor_field')
        out[k]=v
    return out

def _telemetry():
    from opentelemetry import metrics,trace
    if type(trace.get_tracer_provider()) is not trace.NoOpTracerProvider or type(metrics.get_meter_provider()) is not metrics.NoOpMeterProvider:raise RuntimeError('fresh_NoOp_process_required')

def _load(path,expected,approval,predecessor,prior,ledger_path,expires_at):
    # Default gate is before imports, key reads, database construction or transport.
    if APPROVED_RETRY_REF is None or approval!=APPROVED_RETRY_REF:raise PermissionError('successor_retry_not_approved')
    from successor_admission import private_read,sha,digest,timestamp
    _telemetry()
    if not digest(expected) or not digest(predecessor):raise ValueError('independent_successor_digests_required')
    raw=private_read(path)
    if sha(raw)!=expected:raise ValueError('successor_config_digest_mismatch')
    cfg=json.loads(raw,object_pairs_hook=_pairs)
    required={'schema','approval_ref','run_id','expires_at','endpoint','model','budget_nano_usd','max_attempts','input_rate','output_rate','pricing_provenance_sha256','key','ledger_path','source_sha256','package_path','public_sha256','predecessor_sha256','prior_charged_nano_usd','platform_proxy'}
    if type(cfg)is not dict or set(cfg)!=required:raise ValueError('successor_supervisor_schema')
    exact={'schema':'pex.supervisor-successor.v1','approval_ref':approval,'endpoint':ENDPOINT,'model':MODEL,'budget_nano_usd':SUPERVISOR_CUMULATIVE,'max_attempts':12,'input_rate':300,'output_rate':900,'predecessor_sha256':predecessor,'prior_charged_nano_usd':prior,'ledger_path':str(ledger_path),'expires_at':expires_at}
    if any(type(cfg[k])is not type(v) or cfg[k]!=v for k,v in exact.items()):raise ValueError('successor_supervisor_admission_mismatch')
    if type(prior)is not int or prior!=PRIOR_SUPERVISOR or datetime.now(timezone.utc)>=timestamp(expires_at):raise ValueError('successor_expired_or_prior_invalid')
    if type(cfg['run_id'])is not str or not cfg['run_id'] or len(cfg['run_id'])>80 or not digest(cfg['pricing_provenance_sha256']):raise ValueError('run_or_pricing_identity_required')
    sources=cfg['source_sha256']
    if type(sources)is not dict or set(sources)!=set(SOURCE_MODULES):raise ValueError('complete_successor_source_pins_required')
    for name,expected_source in sources.items():
        source=Path(__file__).resolve() if name=='successor_supervisor' else Path(importlib.import_module(name).__file__)
        if not digest(expected_source) or source.resolve()!=source or sha(source.read_bytes())!=expected_source:raise ValueError('successor_source_identity_changed')
    if any(version(name)!=v for name,v in PACKAGES.items()):raise ValueError('successor_dependency_identity_changed')
    ledger=Path(ledger_path)
    if not ledger.is_absolute() or ledger.resolve()!=ledger or ledger.name!='supervisor.sqlite' or ledger.parent.stat().st_mode&0o077:raise ValueError('private_successor_ledger_required')
    if ledger.exists():private_read(ledger,16*1024*1024)
    key=cfg['key']
    if type(key)is not dict or set(key)!={'path','sha256'} or not digest(key['sha256']) or sha(private_read(key['path'],16384))!=key['sha256']:raise ValueError('successor_credential_identity_changed')
    net=cfg['platform_proxy']
    if type(net)is not dict or set(net)!={'proxy_sha256','ca_path','ca_sha256'} or not digest(net['proxy_sha256']) or not digest(net['ca_sha256']):raise ValueError('platform_binding_required')
    proxy=os.environ.get('HTTPS_PROXY','');parts=urlsplit(proxy)
    if sha(proxy.encode())!=net['proxy_sha256'] or not proxy or parts.scheme not in ('http','https') or not parts.hostname or parts.path not in ('','/') or parts.query or parts.fragment:raise ValueError('same_execution_proxy_changed')
    ca=Path(net['ca_path'])
    if os.environ.get('SSL_CERT_FILE')!=str(ca) or not ca.is_absolute() or ca.resolve()!=ca or not ca.is_file() or ca.stat().st_size>4*1024*1024 or sha(ca.read_bytes())!=net['ca_sha256']:raise ValueError('fixed_platform_CA_changed')
    from stockroom_task import load_package,FILES,digest as task_digest,encoded
    task=load_package(cfg['package_path'])
    expected_public=task_digest(encoded({n:task_digest(task['public/'+n]) for n in FILES}))
    if cfg['public_sha256']!=expected_public:raise ValueError('frozen_public_task_mismatch')
    objective=task['INITIAL_PROMPT.txt'].decode()+'\n\nFrozen PUBLIC TASK.md:\n'+task['public/TASK.md'].decode()
    return cfg,objective

def _routes():
    from managed_chat import Limits,Route
    return tuple(Route(ENDPOINT,MODEL,role,Limits(max_output_tokens=cap,max_usage_tokens=266240,timeout_seconds=60)) for role,cap in (('planner',1200),('verifier',900)))

class ManagedSuccessor:
    def __init__(self,args,cfg,objective):
        from accounting import Ledger
        self.args=args;self.config=cfg;self.objective=objective;self.closed=False
        self.routes=_routes()
        self.ledger=Ledger(Path(args['ledger_path']),budget=SUPERVISOR_CUMULATIVE,input_rate=300,output_rate=900,
            route=self.routes[0],currency='USD',pricing_provenance_sha256=cfg['pricing_provenance_sha256'],
            input_token_bound=262144,output_token_bound=4096,approved_routes=self.routes,max_attempts=12,
            prior_charged_nano_usd=args['prior_charged_nano_usd'],predecessor_sha256=args['predecessor_sha256'])
        db=self.ledger.db
        self.identity=(args['expected_config_sha256'],cfg['run_id'],cfg['approval_ref'],args['predecessor_sha256'])
        try:
            db.execute('CREATE TABLE IF NOT EXISTS successor_admission(digest TEXT,run_id TEXT,approval TEXT,predecessor TEXT,state TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS successor_binding(goal TEXT,session TEXT,vendor TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS successor_reviews(request_sha TEXT PRIMARY KEY)')
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('SELECT * FROM successor_admission').fetchall()
            if not rows:
                if db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]:raise ValueError('unbound_prior_successor_spend')
                db.execute('INSERT INTO successor_admission VALUES (?,?,?,?,?)',(*self.identity,'active'))
            elif rows!=[(*self.identity,'active')]:raise ValueError('successor_admission_closed_or_changed')
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:db.execute('ROLLBACK')
            self.ledger.close();raise
    def revalidate(self):
        if self.closed:raise ValueError('successor_closed')
        cfg,objective=_load(**self._load_args())
        if cfg!=self.config or objective!=self.objective:raise ValueError('successor_inputs_changed')
        if self.ledger.db.execute('SELECT * FROM successor_admission').fetchall()!=[(*self.identity,'active')]:raise ValueError('successor_admission_closed_or_changed')
        self.ledger._validate_stored()
        return cfg
    def _load_args(self):
        a=self.args
        return dict(path=a['config_path'],expected=a['expected_config_sha256'],approval=a['approval_ref'],predecessor=a['predecessor_sha256'],prior=a['prior_charged_nano_usd'],ledger_path=a['ledger_path'],expires_at=a['expires_at'])
    def _bind(self,role,request,proposal):
        from pex_protocol.supervisor import supervisor_request_digest
        from pex_protocol.enums import HarnessType
        if role not in ('planner','verifier') or (role=='planner')!=(proposal is None):raise ValueError('successor_role_proposal_mismatch')
        vendor=request.session.vendor_session_id
        if type(vendor)is not str or not vendor or len(vendor)>256:raise ValueError('vendor_session_required')
        public=self.config['public_sha256'];identity=hashlib.sha256((public+vendor).encode()).hexdigest()[:24]
        expected=('goal-'+identity,'bench-'+identity,vendor)
        if request.goal is None or (request.goal.id,request.session.id,vendor)!=expected or request.session.project_id!='pair-'+public[:24] or request.goal.project_id!='pair-'+public[:24] or request.session.goal_id!=expected[0] or request.session.model!=WORKER or request.session.harness_type!=HarnessType.OPENCODE or request.goal.objective!=self.objective or request.supervisor_decision_mode!='supervisor_model_only':raise ValueError('request_outside_frozen_successor_task')
        if proposal is not None and (proposal.goal_id!=expected[0] or proposal.session_id!=expected[1]):raise ValueError('proposal_outside_bound_session')
        digest=supervisor_request_digest(request);db=self.ledger.db
        db.execute('BEGIN IMMEDIATE')
        try:
            rows=db.execute('SELECT * FROM successor_binding').fetchall()
            if not rows:
                if role!='planner':raise ValueError('planner_binding_required_first')
                db.execute('INSERT INTO successor_binding VALUES (?,?,?)',expected)
            elif rows!=[expected]:raise ValueError('successor_session_binding_changed')
            if role=='planner':db.execute('INSERT OR IGNORE INTO successor_reviews VALUES (?)',(digest,))
            elif db.execute('SELECT 1 FROM successor_reviews WHERE request_sha=?',(digest,)).fetchone() is None:raise ValueError('verifier_request_not_previously_planned')
            db.execute('COMMIT')
        except BaseException:db.execute('ROLLBACK');raise
        return digest
    def credential(self,route):
        from managed_chat import _ScopedCredential
        from successor_admission import private_read
        self.revalidate()
        raw=private_read(self.config['key']['path'],16384)
        if hashlib.sha256(raw).hexdigest()!=self.config['key']['sha256']:raise ValueError('successor_credential_identity_changed')
        return _ScopedCredential(raw.decode('ascii').strip(),route.fingerprint)
    def model_factory(self,role,request,proposal):
        self.revalidate();request_digest=self._bind(role,request,proposal)
        from managed_tool_chat import ManagedToolChatCandidate
        from strands_bridge import ManagedPEXModel
        from managed_chat import _PilotProxyBinding
        from pex_protocol.supervisor import supervisor_request_digest
        runtime=self;route=self.routes[0 if role=='planner' else 1]
        proposal_digest=None if proposal is None else hashlib.sha256(proposal.model_dump_json().encode()).hexdigest()
        def assert_model_binding():
            if supervisor_request_digest(request)!=request_digest:raise ValueError('successor_request_mutated')
            if proposal is not None and hashlib.sha256(proposal.model_dump_json().encode()).hexdigest()!=proposal_digest:raise ValueError('successor_proposal_mutated')
        class AccountedCandidate(ManagedToolChatCandidate):
            async def _execute_owned(self,invocation,credential):
                runtime.revalidate()
                runtime.ledger.reserve(invocation.invocation_id,self.route)
                try:return await super()._execute_owned(invocation,credential)
                finally:runtime.ledger.settle(invocation.invocation_id,self.receipt(invocation.invocation_id))
        class SuccessorModel(ManagedPEXModel):
            async def invoke_async(self):
                runtime.revalidate()
                assert_model_binding()
                return await self._invoke_owned_agent()
            async def stream(self,*args,**kwargs):
                runtime.revalidate()
                assert_model_binding()
                credential=runtime.credential(route)
                async with aclosing(self._stream_owned(*args,credential=credential,**kwargs)) as stream:
                    async for event in stream:yield event
        model=SuccessorModel(route,request,invocation_id='successor-'+uuid.uuid4().hex,proposal=proposal)
        model._candidate=AccountedCandidate(route,model.protocol)
        model._candidate._pilot_proxy_binding=_PilotProxyBinding(**self.config['platform_proxy'])
        return model
    def summary(self):
        self.revalidate();rows=self.ledger.summary()
        total=self.args['prior_charged_nano_usd']+sum(r['charged'] for r in rows)
        return {'prior_charged_nano_usd':self.args['prior_charged_nano_usd'],'charged_nano_usd':total,'cap_nano_usd':SUPERVISOR_CUMULATIVE,'predecessor_sha256':self.args['predecessor_sha256'],'attempts_current_successor':len(rows),'calls':rows}
    def close(self):
        if self.closed:return
        db=self.ledger.db
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('SELECT * FROM successor_admission').fetchall()!=[(*self.identity,'active')]:raise ValueError('cannot_confirm_terminal_successor_identity')
            db.execute("UPDATE successor_admission SET state='closed'")
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:db.execute('ROLLBACK')
            raise
        self.ledger.close();self.closed=True

def admit_successor(*,config_path,expected_config_sha256,approval_ref,predecessor_sha256,prior_charged_nano_usd,ledger_path,expires_at):
    args=locals().copy()
    cfg,objective=_load(config_path,expected_config_sha256,approval_ref,predecessor_sha256,prior_charged_nano_usd,ledger_path,expires_at)
    return ManagedSuccessor(args,cfg,objective)
