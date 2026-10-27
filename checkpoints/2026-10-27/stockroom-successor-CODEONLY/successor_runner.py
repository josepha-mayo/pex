"""Code-only paired successor composition. No executable CLI or implicit dispatch.
Live use requires root coordination plus a separately reviewed successor supervisor
entry, which is not supplied by this package. Legacy expired pilot stays untouched.
"""
import asyncio
from dataclasses import asdict,is_dataclass
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
from types import SimpleNamespace
from successor_admission import RootAdmission,AdmissionRefused,load,private_read,sha

IMPORTS=('process_adapter','stockroom_task','stockroom_request','stockroom_grade','controller','review','nebius_worker','worker_funding','cumulative_compute','e2b_transport','accounting','remote_mcp','budget_rpc','opencode_cli','opencode_v2_receipt')

def private_write(path,value):
    raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True,default=json_default)+'\n').encode()
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def json_default(x):
    if is_dataclass(x):return asdict(x)
    if hasattr(x,'model_dump'):return x.model_dump(mode='json')
    raise TypeError(type(x).__name__)

def assert_import_sources(cfg):
    for name in IMPORTS:
        spec=importlib.util.find_spec(name)
        if spec is None or Path(spec.origin).resolve()!=Path(cfg['sources'][name]['path']):raise AdmissionRefused('runtime_import_source_mismatch:'+name)
    if Path(cfg['sources']['successor_runner']['path'])!=Path(__file__).resolve():raise AdmissionRefused('runner_not_independently_pinned')
    import successor_admission
    if Path(cfg['sources']['successor_admission']['path'])!=Path(successor_admission.__file__).resolve():raise AdmissionRefused('admission_not_independently_pinned')
    # Adjacent runtime data/scripts are consumed by workers, not module imports.
    for name,parent,suffix in [('nebius_guard','nebius_worker','.ts'),('export_candidate','stockroom_grade','.py'),('public_diff','stockroom_request','.py')]:
        if Path(cfg['sources'][name]['path'])!=Path(cfg['sources'][parent]['path']).with_name(name+suffix):raise AdmissionRefused('runtime_adjacent_source_mismatch')

class PairAdmission:
    def __init__(self,revalidate):self.revalidate=revalidate
    def authorize(self,arms,budget):
        self.revalidate()
        return set(arms)=={'baseline','pex'} and budget.calls==12 and budget.input_tokens is None and budget.output_tokens==49152 and budget.active_seconds==180

async def run_successor(config_path,root_admission):
    """Explicit root-only entry; no CLI exists. Do NOT call for authored qualification.
    No provider/VM construction before all config, source, predecessor, same-exec
    network and separately admitted supervisor gates have succeeded.
    """
    cfg,prior=load(config_path,root_admission)
    if Path(cfg['output_dir']).exists():raise AdmissionRefused('successor_output_already_exists_no_rebind_or_retry')
    assert_import_sources(cfg)
    initialize=importlib.import_module('process_adapter').initialize_process
    initialize() # Fresh process only, before supervisor/model framework import.
    entry_path=Path(cfg['supervisor']['entry']['path'])
    if entry_path.name=='pilot_process.py':raise AdmissionRefused('legacy_supervisor_entry_not_successor_admission')
    spec=importlib.util.spec_from_file_location('root_admitted_successor_supervisor',entry_path)
    entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
    if getattr(entry,'SUCCESSOR_ENTRY_SCHEMA',None)!='pex.managed-supervisor-successor.v1' or not callable(getattr(entry,'admit_successor',None)):
        raise AdmissionRefused('separately_admitted_supervisor_successor_unavailable')
    output=Path(cfg['output_dir']);output.mkdir(mode=0o700,exist_ok=False)
    private_write(output/'admission.json',{'config_sha256':root_admission.config_sha256,'approval_ref':root_admission.approval_ref,'predecessor_sha256':root_admission.predecessor_sha256,'recording':False,'state':'claimed_once'})
    supervisor=None;report=None
    try:
        # This entry must validate config/source/approval/expiry/route/ledger without
        # a provider call; missing/expired admission raises before worker/VM setup.
        supervisor=entry.admit_successor(config_path=cfg['supervisor']['config']['path'],
            expected_config_sha256=cfg['supervisor']['config']['sha256'],approval_ref=cfg['approval_ref'],
            predecessor_sha256=cfg['predecessor']['sha256'],prior_charged_nano_usd=prior['supervisor_charged_nano_usd'],
            ledger_path=str(output/'supervisor.sqlite'),expires_at=cfg['expires_at'])
        for method in ('revalidate','model_factory','summary','close'):
            if not callable(getattr(supervisor,method,None)):raise AdmissionRefused('incomplete_successor_supervisor_contract')
        supervisor.revalidate()
        def revalidate():
            current,current_prior=load(config_path,root_admission)
            if current!=cfg or current_prior!=prior:raise AdmissionRefused('successor_inputs_changed')
            supervisor.revalidate()
        deps=runtime_dependencies()
        report=await _compose(cfg,prior,root_admission.config_sha256,supervisor,revalidate,deps,output,mode='live-pilot')
        return report
    except BaseException as error:
        private_write(output/'terminal-failure.json',{'status':'inconclusive','error_type':type(error).__name__})
        raise
    finally:
        if supervisor is not None:
            try:
                supervisor.close() # Must persist terminal ledger; never reset on failure.
            except Exception:
                private_write(output/'supervisor-cleanup-unconfirmed.json',{'status':'inconclusive'})
                raise
        if report is not None:
            private_write(output/'terminal.json',{'state':'completed','cleanup_confirmed':True,
                'report_sha256':sha((output/'report.json').read_bytes()),
                'comparison_complete':report['comparison_complete']})


def runtime_dependencies():
    # Reached only after explicit admission. Importing SDK is not provisioning.
    from e2b import Sandbox
    from e2b_transport import PilotPool
    from cumulative_compute import ComputeBudget
    from worker_funding import WorkerFunding,PRICING_SHA
    from nebius_worker import NebiusCLIWorker
    from stockroom_task import stage,FILES,PUBLIC_CHECK_COMMAND
    from stockroom_request import make_public_request
    from stockroom_grade import RemoteGrade
    from controller import Budget,run_pair
    from review import OwnedReview
    return SimpleNamespace(Sandbox=Sandbox,Pool=PilotPool,Compute=ComputeBudget,Funding=WorkerFunding,
        pricing_sha=PRICING_SHA,Worker=NebiusCLIWorker,stage=stage,files=FILES,public_check=PUBLIC_CHECK_COMMAND,
        request_builder=make_public_request,Grade=RemoteGrade,Budget=Budget,run_pair=run_pair,Review=OwnedReview)

async def _compose(cfg,prior,config_digest,supervisor,revalidate,deps,output,*,mode):
    """Private composition seam. Authored tests inject inert factories, never live SDKs."""
    revalidate()
    frozen,prompt=deps.stage(Path(cfg['package_path']),output/'staged')
    budget=deps.Budget(calls=12,input_tokens=None,output_tokens=49152,active_seconds=180)
    arms={c:{'condition':c,'workspace':str(output/'staged/workers'/c),'prompt':prompt,
             'public_sha256':frozen['public_sha256'],'worker_identity':'nebius/deepseek-ai/DeepSeek-V4.1-Flash-1017'} for c in ('baseline','pex')}
    private_write(output/'frozen.json',{'task':frozen,'worker_budget_each':asdict(budget),'predecessor':prior,
       'limits':{'worker_per_arm_nano_usd':375000000,'supervisor_nano_usd':250000000,'compute_nano_usd':100000000},
       'recording':False,'remaining_money_may_differ_by_arm':True,'infrastructure_or_exhaustion_is_inconclusive':True})
    compute=pool=worker=None;funding={};remotes={}
    try:
        compute=deps.Compute(output/'compute.sqlite',prior_upper_bound_nano_usd=prior['compute_upper_bound_nano_usd'],evidence_sha256=cfg['predecessor']['sha256'])
        pool=deps.Pool(deps.Sandbox,private_read(cfg['e2b_key']['path']).decode().strip(),approved=True,cumulative_budget=compute)
        for c in arms:
            funding[c]=deps.Funding(output/'worker.sqlite',arm=c,approved_config_digest=config_digest,
                approval_ref=cfg['funding_approval_ref'],pricing_provenance_sha256=deps.pricing_sha,
                prior_charged_nano_usd=prior['worker_charged_nano_usd'],predecessor_sha256=cfg['predecessor']['sha256'])
        def prepare(c):
            revalidate()
            remote=pool.create('baseline' if c=='baseline' else 'supervised');remotes[c]=remote
            if remote.run('python -I -c "import unittest, sqlite3" && git --version')['exit_code']!=0:raise RuntimeError('remote_runtime_preflight_inconclusive')
            dirs=sorted({str(Path(n).parent) for n in deps.files})
            if remote.run('mkdir -p '+' '.join(shlex.quote(n) for n in dirs)+' && git init -q')['exit_code']!=0:raise RuntimeError('remote_setup_inconclusive')
            for n in deps.files:
                content=(output/'staged/workers'/c/n).read_text();remote.write(n,content)
                if remote.read(n)!=content:raise RuntimeError('remote_public_bytes_differ')
            if remote.run('git add . && git -c user.name=PEX -c user.email=pex@example.invalid commit -qm frozen-public-input')['exit_code']!=0:raise RuntimeError('remote_snapshot_inconclusive')
            return remote
        worker=deps.Worker(remotes={c:(lambda c=c:prepare(c)) for c in arms},private_root=output/'cli',
            binary=cfg['binary']['path'],modules=cfg['modules_path'],key_path=cfg['nebius_key']['path'],pool=pool,
            activate=True,funding=funding,task_profile='stockroom-v1',public_check_command=deps.public_check)
        admission=PairAdmission(revalidate)
        def model_factory(role,request,proposal):
            revalidate()
            return supervisor.model_factory(role,request,proposal)
        def record_request(digest,raw):private_write(output/('public-stop-'+digest+'.json'),raw)
        review=deps.Review(deps.request_builder(Path(cfg['package_path'])),model_factory,mode=mode,admission=admission,request_recorder=record_request)
        grade=deps.Grade(remotes=remotes,package=Path(cfg['package_path']),
            stopped=lambda c:worker.states.get(c,{}).get('stopped',False) is True,
            revoked=lambda c:worker.states.get(c,{}).get('mcp_revoked',False) is True)
        report=await deps.run_pair(arms,worker,review,grade,budget=budget,mode=mode,admission=admission)
        # Never treat a returned inconclusive grade as successful comparison.
        for state in report.get('arms',{}).values():
            g=state.get('protected_grade')
            if g is not None and g.get('status')!='graded_with_limits':
                state['prior_terminal_status']=state['status'];state['status']='grading_inconclusive'
        report['worker_funding']=funding['baseline'].summary()
        report['supervisor_funding']=supervisor.summary()
        report['cumulative_compute_upper_bound_nano_usd']=compute.total()
        report['recording']=False;report['pex_lift']=None;report['presentation_eligible']=False
        report['admission_config_sha256']=config_digest
        report['predecessor_sha256']=cfg['predecessor']['sha256']
        report['predecessor_closed_evidence_sha256']=prior['closed_evidence_sha256']
        report['prior_charges']=prior
        report['comparison_complete']=all(report.get('arms',{}).get(c,{}).get('status') in ('natural_stop','no_intervention','verifier_rejected','planner_rejected') and report['arms'][c].get('protected_grade',{}).get('status')=='graded_with_limits' for c in arms)
        private_write(output/'report.json',report)
        return report
    finally:
        errors=[]
        if worker is not None:
            try:await worker.cleanup()
            except Exception:errors.append('worker_cleanup_unconfirmed')
        if pool is not None:
            try:pool.close()
            except Exception:errors.append('pool_cleanup_unconfirmed')
        for ledger in funding.values():
            try:ledger.close()
            except Exception:errors.append('worker_ledger_close_unconfirmed')
        if compute is not None:
            try:compute.close()
            except Exception:errors.append('compute_ledger_close_unconfirmed')
        if errors:
            private_write(output/'cleanup-unconfirmed.json',{'errors':errors})
            raise RuntimeError('successor_cleanup_unconfirmed')
