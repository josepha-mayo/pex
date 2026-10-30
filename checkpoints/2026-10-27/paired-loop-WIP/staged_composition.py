"""WIP production-shaped composition, reachable only through CLOSED staged grant.

No CLI entry, environment switch, automatic invocation or legacy grant reuse.
Construction does not create a VM or call a model. A future independently
reviewed grant/config and explicit invocation are required. Mocked constituent
qualification is not a live benchmark or proof of provider termination.
"""
import asyncio
from dataclasses import dataclass
import importlib
import json
import os
from pathlib import Path
import secrets
from types import SimpleNamespace
from staged_admission import AdmissionRefused,read_pin,canonical,sha
from staged_accounting import StagedAccounting
from staged_funding import PhaseFunding
from staged_sdk_lifecycle import AdmittedSDKLifecycle
from staged_supervisor import StagedSupervisor
from staged_worker import StagedWorker,StagedGrade
from staged_review import staged_request_builder
from stockroom_task import stage,PUBLIC_CHECK_COMMAND
from staged_public_setup import stage_public_files
from stockroom_request import make_public_request
from stockroom_grade import RemoteGrade
from asyncpool_adapter import MANIFEST_SHA256 as ASYNCPOOL_MANIFEST
import wirepool_integration
import wirepool_setup
from wirepool_adapter import MANIFEST_SHA256 as WIREPOOL_MANIFEST
from wirepool_grade import RemoteGrade as WirepoolRemoteGrade
import asyncpool_integration
import asyncpool_setup
from asyncpool_grade import RemoteGrade as AsyncpoolRemoteGrade
from nebius_worker import NebiusCLIWorker,MODEL
from review import OwnedReview
from successor_runner import private_write,json_default

SOURCE_MODULES=('wirepool_history','wirepool_adapter','wirepool_integration','wirepool_setup','wirepool_request','wirepool_grade','asyncpool_history','asyncpool_adapter','asyncpool_integration','asyncpool_setup','asyncpool_request','asyncpool_grade','staged_admission','staged_accounting','staged_sdk_binding','staged_sdk_lifecycle',
    'staged_lifecycle','staged_async_remote','staged_public_setup','staged_composition','staged_envelope','staged_controller',
    'staged_funding','staged_worker_admission','staged_worker','staged_supervisor','staged_review',
    'nebius_worker','worker_funding','controller','review','stockroom_task','stockroom_request','stockroom_grade',
    'successor_supervisor','successor_runner','successor_admission','successor_budget',
    'accounting','cumulative_compute','e2b_transport','remote_mcp','budget_rpc','opencode_cli','opencode_v2_receipt',
    'process_adapter','managed_chat','managed_tool_chat','strands_bridge','tool_protocol',
    'pex_protocol.actions','pex_protocol.supervisor','pex_supervisor.loop',
    'pex_supervisor.evidence_tools','pex_supervisor.evidence_observations')
ADJACENT={'wirepool_export_candidate':('wirepool_grade','export_candidate.py'),'wirepool_grade_upload_verify':('wirepool_grade','grade_upload_verify.py'),'wirepool_public_diff':('wirepool_request','public_diff.py'),'asyncpool_export_candidate':('asyncpool_grade','export_candidate.py'),
    'asyncpool_grade_upload_verify':('asyncpool_grade','grade_upload_verify.py'),
    'asyncpool_public_diff':('asyncpool_request','public_diff.py'),'nebius_guard':('nebius_worker','nebius_guard.ts'),
    'staged_nebius_guard':('nebius_worker','staged_nebius_guard.ts'),
    'grade_upload_verify':('stockroom_grade','grade_upload_verify.py'),
    'export_candidate':('stockroom_grade','export_candidate.py'),'public_diff':('stockroom_request','public_diff.py')}
_SEAL=object()


def private_atomic_json(path,value,*,limit=2*1024*1024):
    """Fsync complete private bytes, then publish without replacing old evidence."""
    path=Path(path)
    if (not path.is_absolute() or path.resolve()!=path or not path.parent.is_dir()
            or path.parent.stat().st_mode&0o077):raise ValueError('private_evidence_directory_required')
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),default=json_default,allow_nan=False).encode()
    if len(raw)>limit:raise ValueError('private_evidence_byte_bound')
    temporary=path.with_name('.'+path.name+'.pending-'+secrets.token_hex(8))
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
        os.link(temporary,path,follow_symlinks=False)  # Atomic, exclusive publication.
    finally:
        temporary.unlink(missing_ok=True)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    return {'path':str(path),'sha256':sha(raw)}


def _rows(db,query,parameters=()):
    cursor=db.execute(query,parameters)
    names=[item[0] for item in cursor.description]
    return [dict(zip(names,row)) for row in cursor.fetchall()]


def source_pins():
    """Public code inventory only; caller independently freezes/reviews its hash."""
    files={name:Path(importlib.import_module(name).__file__).resolve() for name in SOURCE_MODULES}
    files.update({name:files[parent].with_name(filename) for name,(parent,filename) in ADJACENT.items()})
    return {name:{'path':str(path),'sha256':sha(path.read_bytes())} for name,path in files.items()}


def _sources(cfg):
    if cfg['sources']!=source_pins():raise AdmissionRefused('complete_installed_composition_sources_required')
    for pin in cfg['sources'].values():read_pin(pin)


@dataclass(frozen=True,repr=False)
class Composition:
    accounting:object
    arms:dict
    worker:object
    review:object
    grader:object
    supervisor:object
    arms_sha256:str
    seal:object
    def __repr__(self):return '<closed staged composition>'
    def verify(self,arms,worker,review,grader):
        if self.seal is not _SEAL or (arms is not self.arms or worker is not self.worker
                or review is not self.review or grader is not self.grader):
            raise AdmissionRefused('owned_composition_identity_required')
        self.accounting.before_reserve();_sources(self.accounting.cfg)
        if sha(canonical(arms))!=self.arms_sha256 or worker.mode!='closed-admitted':
            raise AdmissionRefused('frozen_staged_composition_changed')
        if getattr(review.model_factory,'__self__',None) is not self.supervisor:
            raise AdmissionRefused('owned_supervisor_factory_changed')

    def checkpoint_arm(self,condition,state):
        """Actual partial evidence only; must finish BEFORE another VM prepare."""
        if condition not in ('baseline','pex'):raise AdmissionRefused('exact_arm_checkpoint_required')
        self.accounting.validate_identity();_sources(self.accounting.cfg)
        binding=self.accounting.binding;sid=binding.owned_by_arm.get(condition)
        payload={'schema':'pex.staged.arm-checkpoint.v1','run_id':binding.admitted.grant.run_id,
            'config_sha256':binding.admitted.grant.config_sha256,
            'sources_sha256':binding.admitted.grant.sources_sha256,
            'task_sha256':binding.admitted.grant.task_sha256,'condition':condition,
            'arm_state':state,'grade_was_produced':'protected_grade' in state,
            'worker_receipt_rows':_rows(self.accounting.raw_workers[condition].db,
                'SELECT * FROM calls WHERE arm=? ORDER BY rowid',(condition,)),
            'supervisor_receipt_rows':_rows(self.accounting.supervisor.db,'SELECT * FROM calls ORDER BY rowid') if condition=='pex' else [],
            'owned_cleanup':{'owned_id_known':sid is not None,'control_plane_stop_confirmed':None if sid is None else sid in binding.stopped,
                'create_outcome_unknown':condition in self.worker.lifecycle.unknown_creates},
            'partial_pair_evidence_only':True,'comparison_complete':False,'pex_lift':None,
            'qualification':'Actual observed arm status/receipts only. Missing grade stays missing; this artifact cannot by itself establish a complete paired comparison.'}
        return private_atomic_json(self.accounting.root/'evidence'/('arm-'+condition+'.json'),payload,
                                   limit=80*1024*1024)  # <=12 worker +12 bounded supervisor receipt rows.


def build_composition(accounting):
    if type(accounting) is not StagedAccounting:raise AdmissionRefused('closed_staged_accounting_required')
    accounting.before_reserve();cfg=accounting.cfg;_sources(cfg)
    output=accounting.root;package=Path(cfg['task']['path']).parent
    is_asyncpool=cfg['task']['sha256']==ASYNCPOOL_MANIFEST
    is_wirepool=cfg['task']['sha256']==WIREPOOL_MANIFEST
    stage_task=wirepool_integration.stage if is_wirepool else asyncpool_integration.stage if is_asyncpool else stage
    upload_task=wirepool_setup.stage_public_files if is_wirepool else asyncpool_setup.stage_public_files if is_asyncpool else stage_public_files
    request_task=wirepool_integration.make_public_request if is_wirepool else asyncpool_integration.make_public_request if is_asyncpool else make_public_request
    grade_type=WirepoolRemoteGrade if is_wirepool else AsyncpoolRemoteGrade if is_asyncpool else RemoteGrade
    evidence_root=output/'evidence';evidence_root.mkdir(mode=0o700)
    def grade_evidence(condition,kind,payload):
        if condition not in ('baseline','pex','pex-phase0') or kind not in ('candidate-export','grade-report'):
            raise AdmissionRefused('exact_private_grade_artifact_required')
        accounting.validate_identity()
        return private_atomic_json(evidence_root/(condition+'-'+kind+'.json'),{
            'schema':'pex.staged.grade-artifact.v1','run_id':accounting.binding.admitted.grant.run_id,
            'config_sha256':accounting.binding.admitted.grant.config_sha256,
            'sources_sha256':accounting.binding.admitted.grant.sources_sha256,
            'task_sha256':accounting.binding.admitted.grant.task_sha256,
            'condition':condition,'kind':kind,'payload':payload,'partial_pair_evidence_only':True})
    frozen,prompt=stage_task(package,output/'staged')
    arms={c:{'condition':c,'workspace':str(output/'staged/workers'/c),'prompt':prompt,
             'public_sha256':frozen['public_sha256'],'worker_identity':'nebius/'+MODEL} for c in ('baseline','pex')}
    private_write(output/'frozen-staged-inputs.json',{'task':frozen,'profile':cfg['profile'],
        'config_sha256':accounting.binding.admitted.grant.config_sha256,'predecessor':cfg['predecessor']['sha256'],
        'stage_finalization':'symmetric_counted_tool_choice_none_not_spontaneous_task_completion',
        'state':'frozen_not_dispatched','presentation_eligible':False})
    async def stage_public(arm,remote):
        accounting.before_reserve()
        def upload():
            upload_task(remote,output/'staged/workers'/arm['condition'],frozen['public_files'],
                lambda evidence:private_write(output/('setup-timing-'+arm['condition']+'.json'),evidence),
                runtime_contract=cfg['profile']['runtime_contract'])
        await asyncio.to_thread(upload)
    life=AdmittedSDKLifecycle(accounting.binding,stage_public)
    funding={c:PhaseFunding(ledger,mode='closed-admitted') for c,ledger in accounting.workers.items()}
    inner=NebiusCLIWorker(remotes={c:None for c in arms},private_root=output/'cli',
        binary=cfg['cli']['binary']['path'],modules=cfg['cli']['modules_path'],key_path=cfg['nebius_key']['path'],
        pool=SimpleNamespace(close=lambda:None),activate=True,funding=funding,task_profile='wirepool-v1' if is_wirepool else 'asyncpool-v1' if is_asyncpool else 'stockroom-v1',
        public_check_command=PUBLIC_CHECK_COMMAND,staged_binding=accounting.binding,
        capture_public_snapshot=cfg['profile']['public_snapshot_inspection'])
    worker=StagedWorker(inner,life,mode='closed-admitted')
    supervisor=StagedSupervisor(accounting)
    review=OwnedReview(staged_request_builder(request_task(package)),supervisor.model_factory,
        mode='live-pilot',admission=accounting.binding.admitted,
        request_recorder=lambda digest,raw:private_write(output/('public-observation-'+digest+'.json'),raw))
    def saved_phase0(condition):
        accounting.validate_identity()
        if condition!='pex':raise AdmissionRefused('only_pex_pre_intervention_checkpoint')
        capture=inner.public_checkpoints.get(condition)
        if type(capture)is not dict or 'durable_pin' not in capture:raise AdmissionRefused('durable_public_checkpoint_required')
        pin=capture['durable_pin']
        if pin.get('path')!=str(evidence_root/(condition+'-public-checkpoint.json')):raise AdmissionRefused('exact_public_checkpoint_path_required')
        value=json.loads(read_pin(pin,private=True,limit=512*1024))
        if (set(value)!={'schema','condition','capture_boundary','public_export','snapshot_sha256','config_sha256'}
                or value['schema']!='pex.public-pre-intervention-checkpoint.v1' or value['condition']!=condition
                or value['capture_boundary']!='after_phase0_before_monitor_before_any_protected_upload'
                or value['config_sha256']!=accounting.binding.admitted.grant.config_sha256
                or value['snapshot_sha256']!=capture['snapshot_sha256']):raise AdmissionRefused('public_checkpoint_identity_changed')
        return value['public_export']
    grade=grade_type(remotes=worker.remotes,package=package,
        stopped=lambda c:inner.states.get(c,{}).get('stopped') is True,
        revoked=lambda c:inner.states.get(c,{}).get('mcp_revoked') is True,evidence_sink=grade_evidence,
        saved_phase0=saved_phase0 if cfg['profile']['grade_phase0_after_final'] else None)
    return Composition(accounting,arms,worker,review,StagedGrade(grade,worker,grade_phase0_after_final=cfg['profile']['grade_phase0_after_final']),supervisor,sha(canonical(arms)),_SEAL)


async def run_composition(composition):
    """Explicit call only; never reads a grant from caller/env or opens None gate."""
    if type(composition) is not Composition:raise AdmissionRefused('closed_composition_required')
    composition.verify(composition.arms,composition.worker,composition.review,composition.grader)
    from staged_controller import run_staged_pair
    report=None
    try:
        report=await run_staged_pair(composition.arms,composition.worker,composition.review,composition.grader,
                                    mode='closed-admitted',_composition=composition)
        report['cumulative_accounting']=composition.accounting.summary()
        report['config_sha256']=composition.accounting.binding.admitted.grant.config_sha256
        report['comparison_complete']=all(report.get('arms',{}).get(c,{}).get('status')=='staged_natural_stop'
            and report['arms'][c].get('protected_grade',{}).get('status')=='graded_with_limits' for c in ('baseline','pex'))
        report['comparison_complete']=report['comparison_complete'] and report.get('cleanup_confirmed') is True and report['arms']['pex']['supervisor_observed'] is True
        private_write(composition.accounting.root/'report.json',report)
        return report
    finally:
        composition.supervisor.close()
        private_write(composition.accounting.root/'setup-lifecycle-timing.json',composition.worker.lifecycle.setup_timing)
        private_write(composition.accounting.root/'remote-diagnostics.json',
            {'schema':'pex.remote-typed-diagnostics.v1','raw_error_strings_retained':False,
             'arms':{c:{'poisoned':r.poisoned,'closed':r.closed,
                        'cancellation_unconfirmed':r.cancellation_unconfirmed,'typed_evidence':r.diagnostics}
                     for c,r in composition.worker.lifecycle.remotes.items()}})
        # Accounting/binding lifetimes belong to the explicit owning launcher;
        # no auto-retry, no pool replacement and no claim removal here.
