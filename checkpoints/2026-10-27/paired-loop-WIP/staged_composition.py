"""WIP production-shaped composition, reachable only through CLOSED staged grant.

No CLI entry, environment switch, automatic invocation or legacy grant reuse.
Construction does not create a VM or call a model. A future independently
reviewed grant/config and explicit invocation are required. Mocked constituent
qualification is not a live benchmark or proof of provider termination.
"""
import asyncio
from dataclasses import dataclass
import importlib
from pathlib import Path
import shlex
from types import SimpleNamespace
from staged_admission import AdmissionRefused,read_pin,canonical,sha
from staged_accounting import StagedAccounting
from staged_funding import PhaseFunding
from staged_sdk_lifecycle import AdmittedSDKLifecycle
from staged_supervisor import StagedSupervisor
from staged_worker import StagedWorker,StagedGrade
from staged_review import staged_request_builder
from stockroom_task import stage,FILES,PUBLIC_CHECK_COMMAND
from stockroom_request import make_public_request
from stockroom_grade import RemoteGrade
from e2b_transport import ROOT
from nebius_worker import NebiusCLIWorker,MODEL
from review import OwnedReview
from successor_runner import private_write

SOURCE_MODULES=('staged_admission','staged_accounting','staged_sdk_binding','staged_sdk_lifecycle',
    'staged_lifecycle','staged_async_remote','staged_composition','staged_envelope','staged_controller',
    'staged_funding','staged_worker_admission','staged_worker','staged_supervisor','staged_review',
    'nebius_worker','worker_funding','controller','review','stockroom_task','stockroom_request','stockroom_grade',
    'successor_supervisor','successor_runner','successor_admission','successor_budget',
    'accounting','cumulative_compute','e2b_transport','remote_mcp','budget_rpc','opencode_cli','opencode_v2_receipt',
    'process_adapter','managed_chat','managed_tool_chat','strands_bridge','tool_protocol',
    'pex_protocol.actions','pex_protocol.supervisor','pex_supervisor.loop',
    'pex_supervisor.evidence_tools','pex_supervisor.evidence_observations')
ADJACENT={'nebius_guard':('nebius_worker','nebius_guard.ts'),
    'staged_nebius_guard':('nebius_worker','staged_nebius_guard.ts'),
    'export_candidate':('stockroom_grade','export_candidate.py'),'public_diff':('stockroom_request','public_diff.py')}
_SEAL=object()


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


def build_composition(accounting):
    if type(accounting) is not StagedAccounting:raise AdmissionRefused('closed_staged_accounting_required')
    accounting.before_reserve();cfg=accounting.cfg;_sources(cfg)
    output=accounting.root;package=Path(cfg['task']['path']).parent
    frozen,prompt=stage(package,output/'staged')
    arms={c:{'condition':c,'workspace':str(output/'staged/workers'/c),'prompt':prompt,
             'public_sha256':frozen['public_sha256'],'worker_identity':'nebius/'+MODEL} for c in ('baseline','pex')}
    private_write(output/'frozen-staged-inputs.json',{'task':frozen,'profile':cfg['profile'],
        'config_sha256':accounting.binding.admitted.grant.config_sha256,'predecessor':cfg['predecessor']['sha256'],
        'stage_finalization':'symmetric_counted_tool_choice_none_not_spontaneous_task_completion',
        'state':'frozen_not_dispatched','presentation_eligible':False})
    async def stage_public(arm,remote):
        accounting.before_reserve()
        def upload():
            remote._sandbox.files.make_dir(ROOT,user='user',request_timeout=15)
            if remote.run('python -I -c "import unittest, sqlite3" && git --version')['exit_code']!=0:
                raise RuntimeError('remote_runtime_preflight_inconclusive')
            dirs=sorted({str(Path(n).parent) for n in FILES})
            if remote.run('mkdir -p '+' '.join(shlex.quote(n) for n in dirs)+' && git init -q')['exit_code']!=0:
                raise RuntimeError('remote_setup_inconclusive')
            for name in FILES:
                content=(output/'staged/workers'/arm['condition']/name).read_text()
                remote.write(name,content)
                if remote.read(name)!=content:raise RuntimeError('remote_public_bytes_differ')
            if remote.run('git add . && git -c user.name=PEX -c user.email=pex@example.invalid commit -qm frozen-public-input')['exit_code']!=0:
                raise RuntimeError('remote_snapshot_inconclusive')
        await asyncio.to_thread(upload)
    life=AdmittedSDKLifecycle(accounting.binding,stage_public)
    funding={c:PhaseFunding(ledger,mode='closed-admitted') for c,ledger in accounting.workers.items()}
    inner=NebiusCLIWorker(remotes={c:None for c in arms},private_root=output/'cli',
        binary=cfg['cli']['binary']['path'],modules=cfg['cli']['modules_path'],key_path=cfg['nebius_key']['path'],
        pool=SimpleNamespace(close=lambda:None),activate=True,funding=funding,task_profile='stockroom-v1',
        public_check_command=PUBLIC_CHECK_COMMAND,staged_binding=accounting.binding)
    worker=StagedWorker(inner,life,mode='closed-admitted')
    supervisor=StagedSupervisor(accounting)
    review=OwnedReview(staged_request_builder(make_public_request(package)),supervisor.model_factory,
        mode='live-pilot',admission=accounting.binding.admitted,
        request_recorder=lambda digest,raw:private_write(output/('public-observation-'+digest+'.json'),raw))
    grade=RemoteGrade(remotes=worker.remotes,package=package,
        stopped=lambda c:inner.states.get(c,{}).get('stopped') is True,
        revoked=lambda c:inner.states.get(c,{}).get('mcp_revoked') is True)
    return Composition(accounting,arms,worker,review,StagedGrade(grade,worker),supervisor,sha(canonical(arms)),_SEAL)


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
        # Accounting/binding lifetimes belong to the explicit owning launcher;
        # no auto-retry, no pool replacement and no claim removal here.
