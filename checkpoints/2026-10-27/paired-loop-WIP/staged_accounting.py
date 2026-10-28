"""WIP closed staged cumulative ledger composition; never model authority.

Every historical liability is retained by the immutable predecessor total.
Fresh worker ledgers are phase-only (zero internal historical seed), so history
is neither dropped nor counted twice. Supervisor history uses the unchanged
reviewed original supervisor pool; new supervisor receipts are separate overhead.
No old WorkerFunding/supervisor approval is reopened by this module.
"""
from pathlib import Path
import json
import os
from staged_admission import AdmissionRefused,canonical,sha,read_pin
from staged_sdk_binding import SDKTransportBinding
from worker_funding import _WorkerLedger,ARM_BUDGET,PRICING_SHA
from accounting import Ledger
from managed_chat import Limits,Route

# Unchanged reviewed supervisor pool and historical seed, NOT new spending.
SUPERVISOR_OUTER=1_180_535_400
SUPERVISOR_PRIOR=659_514_900
SUPERVISOR_FRESH=SUPERVISOR_OUTER-SUPERVISOR_PRIOR
ENDPOINT='https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions'
MODEL='nvidia/nemotron-3-super-120b-a12b'


class StagedAccounting:
    def __init__(self,binding):
        if type(binding) is not SDKTransportBinding: raise AdmissionRefused('closed_claimed_binding_required')
        binding._check()
        self.binding=binding;self.closed=False;self.cfg=binding.admitted.config()
        prior=json.loads(read_pin(self.cfg['predecessor'],private=True))
        profile=self.cfg['profile'];fresh=profile['equal_worker_fresh']
        if (type(fresh) is not int or not 0<fresh<=ARM_BUDGET or profile['supervisor_fresh']!=SUPERVISOR_FRESH
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
        try:
            for arm in ('baseline','pex'):
                self.raw_workers[arm]=_WorkerLedger(self.root/'workers.sqlite',arm=arm,
                    approved_config_digest=binding.admitted.grant.config_sha256,
                    approval_ref=binding.admitted.grant.approval_ref,pricing_provenance_sha256=PRICING_SHA,
                    predecessor_sha256=self.cfg['predecessor']['sha256'],phase_limit_nano_usd=fresh)
            self.routes=tuple(Route(ENDPOINT,MODEL,role,Limits(max_output_tokens=cap,max_usage_tokens=266240,timeout_seconds=60))
                              for role,cap in (('planner',1200),('verifier',900)))
            self.supervisor=Ledger(self.root/'supervisor.sqlite',budget=SUPERVISOR_OUTER,input_rate=300,output_rate=900,
                route=self.routes[0],currency='USD',pricing_provenance_sha256=profile['supervisor_pricing_sha256'],
                input_token_bound=262144,output_token_bound=4096,approved_routes=self.routes,max_attempts=12,
                prior_charged_nano_usd=SUPERVISOR_PRIOR,predecessor_sha256=self.cfg['predecessor']['sha256'])
            self.workers={arm:WorkerPhaseLedger(self,raw) for arm,raw in self.raw_workers.items()}
            self.supervisor_ledger=SupervisorPhaseLedger(self)
        except BaseException:
            self.close();raise

    def validate_identity(self):
        if self.closed or self.identity_path.read_bytes()!=self.identity:
            raise AdmissionRefused('staged_accounting_identity_closed_or_changed')
        if sha(canonical(self.cfg))!=self.binding.admitted.grant.config_sha256:
            raise AdmissionRefused('staged_accounting_config_changed')

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
                'provider_cumulative_nano_usd':total,'compute_cumulative_bound_nano_usd':self.binding.compute.total(),
                'qualification':'durable_reservations_and_validated_receipts_not_provider_invoice'}

    def close(self):
        if self.closed:return
        for ledger in self.raw_workers.values():ledger.close()
        if self.supervisor is not None:self.supervisor.close()
        self.closed=True


class WorkerPhaseLedger:
    """Exact fresh-phase accounting capability. Settlement never opens a call."""
    def __init__(self,owner,raw):self.owner=owner;self.raw=raw;self.arm=raw.arm
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
