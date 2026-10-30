"""Separate Vercel native-MCP route. No E2B authority or identity reuse. WIP."""
"""WIP closed staged cumulative ledger composition; never model authority.

Every historical liability is retained by the immutable predecessor total.
Fresh worker ledgers are phase-only (zero internal historical seed), so history
is neither dropped nor counted twice. Supervisor history remains fully retained; a new reviewed fresh supervisor
envelope is separate overhead and never reopens the original pool.
No old WorkerFunding/supervisor approval is reopened by this module.
"""
from pathlib import Path
import base64
import json
import os
from datetime import datetime,timezone
from vercel_admission import AdmissionRefused,canonical,sha,read_pin
from vercel_admission import VercelBinding
from worker_funding import _WorkerLedger,STAGED_ARM_BUDGET,STAGED_OUTPUT_BOUND,PRICING_SHA
from accounting import Ledger
from managed_chat import Limits,Route

# Prospective NEW-run allocation only; all old ledger budgets stay immutable.
SUPERVISOR_PRIOR=659_514_900
SUPERVISOR_FRESH=350_000_000
SUPERVISOR_OUTER=SUPERVISOR_PRIOR+SUPERVISOR_FRESH
ENDPOINT='https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions'
MODEL='nvidia/nemotron-3-super-120b-a12b'


class StagedAccounting:
    def __init__(self,binding):
        if type(binding) is not VercelBinding: raise AdmissionRefused('closed_claimed_binding_required')
        binding._check()
        self.binding=binding;self.closed=False;self.cfg=binding.admitted.config()
        prior=json.loads(read_pin(self.cfg['predecessor'],private=True))
        profile=self.cfg['profile'];fresh=profile['equal_worker_fresh']
        if (type(fresh) is not int or fresh!=STAGED_ARM_BUDGET or profile.get('worker_output_per_call')!=STAGED_OUTPUT_BOUND or profile['supervisor_fresh']!=SUPERVISOR_FRESH
                or prior['provider_nano_usd']<SUPERVISOR_PRIOR):
            raise AdmissionRefused('staged_fresh_pool_or_prior_incompatible')
        self.prior=prior['provider_nano_usd'];self.fresh=fresh
        # Exclusive new directory prevents a partially used accounting bundle
        # being resumed/reopened under the same consumed grant.
        self.root=Path(self.cfg['output_dir']);self.root.mkdir(mode=0o700,parents=False,exist_ok=False)
        self.identity=canonical({'config':binding.admitted.grant.config_sha256,
            'predecessor':self.cfg['predecessor']['sha256'],'profile':binding.admitted.grant.profile_sha256,
            'prior_provider_nano_usd':self.prior,'equal_worker_fresh':fresh,'supervisor_fresh':SUPERVISOR_FRESH})
        self.identity_path=self.root/'accounting-identity.json'
        fd=os.open(self.identity_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:os.write(fd,self.identity);os.fsync(fd)
        finally:os.close(fd)
        self.raw_workers={};self.supervisor=None
        wire_root=self.root/'worker-wire';wire_root.mkdir(mode=0o700)
        def wire_evidence(arm,call_id,request_sha,status,content_type,rawbytes,validation_code):
            self.validate_identity()  # No supervisor SQLite access on RPC threads.
            from vercel_composition import private_atomic_json
            return private_atomic_json(wire_root/(sha(canonical([arm,call_id]))+'.json'),{
                'schema':'pex.staged.private-worker-wire.v1','config_sha256':binding.admitted.grant.config_sha256,
                'run_id':binding.admitted.grant.run_id,'arm':arm,'call_id':call_id,'request_sha256':request_sha,
                'HTTP_status':status if type(status)is int else None,
                'content_type':content_type if type(content_type)is str else None,
                'raw_response_base64':base64.b64encode(rawbytes).decode('ascii'),
                'response_sha256':sha(rawbytes),'usage_validation_code':validation_code,
                'request_body_or_headers_captured':False,
                'qualification':'Private bounded response evidence, not a settlement or permission to display model content.'},
                limit=12*1024*1024)
        try:
            for arm in ('baseline','pex'):
                self.raw_workers[arm]=_WorkerLedger(self.root/'workers.sqlite',arm=arm,
                    approved_config_digest=binding.admitted.grant.config_sha256,
                    approval_ref=binding.admitted.grant.approval_ref,pricing_provenance_sha256=PRICING_SHA,
                    predecessor_sha256=self.cfg['predecessor']['sha256'],phase_limit_nano_usd=fresh,
                    wire_evidence_sink=wire_evidence,arm_budget_nano_usd=fresh,
                    output_token_bound=profile['worker_output_per_call'])
            self.routes=tuple(Route(ENDPOINT,MODEL,role,Limits(max_output_tokens=cap,max_usage_tokens=266240,timeout_seconds=60))
                              for role,cap in (('planner',1200),('verifier',900)))
            self.supervisor=Ledger(self.root/'supervisor.sqlite',budget=SUPERVISOR_OUTER,input_rate=300,output_rate=900,
                route=self.routes[0],currency='USD',pricing_provenance_sha256=profile['supervisor_pricing_sha256'],
                input_token_bound=262144,output_token_bound=4096,approved_routes=self.routes,max_attempts=12,
                prior_charged_nano_usd=SUPERVISOR_PRIOR,predecessor_sha256=self.cfg['predecessor']['sha256'])
            (self.root/'supervisor-wire').mkdir(mode=0o700)
            self.supervisor.db.execute('CREATE TABLE vercel_supervisor_wire(invocation_id TEXT,kind TEXT,role TEXT,route TEXT,body_sha256 TEXT,artifact_path TEXT,artifact_sha256 TEXT,PRIMARY KEY(invocation_id,kind))')
            self.workers={arm:WorkerPhaseLedger(self,raw) for arm,raw in self.raw_workers.items()}
            self.supervisor_ledger=SupervisorPhaseLedger(self)
        except BaseException:
            self.close();raise

    def archive_supervisor_wire(self,kind,invocation_id,route,body,status):
        """Complete bounded bodies BEFORE strict parsing; never headers/keys.

        Auxiliary immutable hashes bind the capture to an existing reservation.
        A captured response is NOT a settled/validated response. Publication
        failure leaves the original full uncertain reservation intact.
        """
        self.validate_identity()
        if (kind not in ('request','response') or route not in self.routes or type(body)is not bytes
                or len(body)>(route.limits.max_request_bytes if kind=='request' else route.limits.max_response_bytes)
                or (kind=='request' and status is not None) or (kind=='response' and status!=200)):
            raise AdmissionRefused('supervisor_wire_capture_shape_refused')
        db=self.supervisor.db;db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('SELECT route,state FROM calls WHERE id=?',(invocation_id,)).fetchall()!=[(route.fingerprint,'reserved_uncertain')]:
                raise AdmissionRefused('supervisor_wire_reserved_identity_required')
            if kind=='response' and db.execute("SELECT role,route FROM vercel_supervisor_wire WHERE invocation_id=? AND kind='request'",(invocation_id,)).fetchall()!=[(route.role,route.fingerprint)]:
                raise AdmissionRefused('supervisor_wire_request_capture_required')
            from vercel_composition import private_atomic_json
            pin=private_atomic_json(self.root/'supervisor-wire'/(sha(canonical([invocation_id,kind]))+'.json'),{
                'schema':'pex.staged.private-supervisor-wire.v1','kind':kind,
                'run_id':self.binding.admitted.grant.run_id,'config_sha256':self.binding.admitted.grant.config_sha256,
                'role':route.role,'invocation_id':invocation_id,'route_fingerprint':route.fingerprint,
                'model_id':route.model_id,'endpoint':route.endpoint,'body_sha256':sha(body),
                'raw_body_base64':base64.b64encode(body).decode('ascii'),'HTTP_status':status,
                'content_type':'application/json','captured_at_utc':datetime.now(timezone.utc).isoformat(),
                'complete_bounded_body':True,'request_headers_captured':False,
                'qualification':'Private complete bounded body captured before strict response parsing; not settlement or display approval. Content type is normalized, capture UTC is owner observation, not server time.'},
                limit=2*max(len(body),4096)+4096)
            db.execute('INSERT INTO vercel_supervisor_wire VALUES (?,?,?,?,?,?,?)',
                (invocation_id,kind,route.role,route.fingerprint,sha(body),pin['path'],pin['sha256']))
            db.execute('COMMIT');return pin
        except BaseException:
            if db.in_transaction:db.execute('ROLLBACK')
            raise

    def validate_identity(self):
        if self.closed or self.identity_path.read_bytes()!=self.identity:
            raise AdmissionRefused('vercel_accounting_identity_closed_or_changed')
        if sha(canonical(self.cfg))!=self.binding.admitted.grant.config_sha256:
            raise AdmissionRefused('vercel_accounting_config_changed')

    def before_reserve(self):
        self.validate_identity();self.binding._check()
        # Worker funding RPCs execute on their own threads. Do not touch the
        # supervisor's owner-thread SQLite connection here. Independent strict
        # fresh pools plus this immutable sum bound the cumulative envelope.
        if self.prior+2*self.fresh+SUPERVISOR_FRESH>self.cfg['profile']['provider_cap']:
            raise AdmissionRefused('immutable_cumulative_reservation_exceeded')

    def summary(self):
        self.validate_identity()
        # Both worker handles refer to the same DB. Read it ONCE, never sum the
        # duplicate all-arm summary returned by each handle.
        workers=self.raw_workers['baseline'].summary()
        if any(self.raw_workers[c].prior!={'baseline':0,'pex':0} or self.raw_workers[c].phase_limit!=self.fresh for c in self.raw_workers):
            raise AdmissionRefused('fresh_worker_ledger_binding_changed')
        self.supervisor._validate_stored()
        rows=self.supervisor.summary();overhead=sum(row['charged'] for row in rows)
        total=self.prior+sum(workers['charged_nano_usd'].values())+overhead
        if total>self.cfg['profile']['provider_cap'] or overhead>SUPERVISOR_FRESH:
            raise AdmissionRefused('staged_cumulative_provider_ceiling_exceeded')
        return {'prior_provider_nano_usd':self.prior,'worker_fresh_nano_usd':workers['charged_nano_usd'],
                'supervisor_fresh_overhead_nano_usd':overhead,'supervisor_wire_attempts':len(rows),
                'provider_cumulative_nano_usd':total,'compute_cumulative_bound_nano_usd':self.binding.compute.total(),'vercel_usage':self.binding.vercel_usage(),
                'qualification':'durable_reservations_and_validated_receipts_not_provider_invoice'}

    def close(self):
        if self.closed:return
        for ledger in self.raw_workers.values():ledger.close()
        if self.supervisor is not None:self.supervisor.close()
        self.closed=True


class WorkerPhaseLedger:
    """Exact fresh-phase accounting capability. Settlement never opens a call."""
    def __init__(self,owner,raw):self.owner=owner;self.raw=raw;self.arm=raw.arm
    @property
    def output_token_bound(self):return self.raw.output_token_bound
    @property
    def max_response_bytes(self):return self.raw.max_response_bytes
    def reserve(self,*args):self.owner.before_reserve();return self.raw.reserve(*args)
    def settle_raw(self,*args):self.owner.validate_identity();return self.raw.settle_raw(*args)
    def usage_snapshot(self):self.owner.validate_identity();return self.raw.usage_snapshot()


class SupervisorPhaseLedger:
    def __init__(self,owner):self.owner=owner
    @property
    def db(self):return self.owner.supervisor.db
    def reserve(self,*args):self.owner.before_reserve();return self.owner.supervisor.reserve(*args)
    def settle(self,*args):self.owner.validate_identity();return self.owner.supervisor.settle(*args)
    def summary(self):self.owner.validate_identity();return self.owner.supervisor.summary()
