"""One explicit root-approved live pilot entry; no implicit runs or production gate changes.

Run only in a fresh controller interpreter with trusted source paths installed.
Default invocation cannot dispatch: exact private-config digest and --execute are
required. Optional paid worker route: fixed $0.375 per arm, $0.25 supervisor, $0.10 VM. No activation before exact new approval.
"""
import argparse
import asyncio
from datetime import datetime,timezone,timedelta
from dataclasses import asdict,is_dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path
import uuid

APPROVAL=None  # Set only after exact new owner funding approval.
FILES=('pilot_nebius.py','nebius_worker.py','nebius_guard.ts','budget_rpc.py','remote_mcp.py','controller.py','review.py','public_request.py','opencode_v2_receipt.py')


def read_private(path):
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path or path.stat().st_mode&0o077 or path.parent.stat().st_mode&0o077:
        raise ValueError('private_config_or_key_permissions')
    if path.stat().st_size>65536: raise ValueError('private_config_bound')
    return path.read_bytes()


def load(path,digest):
    if APPROVAL is None: raise PermissionError('paid_worker_pilot_not_authorized')
    raw=read_private(path)
    if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('independent_go_digest_mismatch')
    cfg=json.loads(raw)
    required={'schema','approval_ref','expires_at','source_sha256','nebius_key_path','nebius_key_sha256',
              'e2b_key_path','e2b_key_sha256','supervisor_template_path','supervisor_template_sha256',
              'package_path','output_dir','binary_path','modules_path'}
    if set(cfg)!=required or cfg['schema']!=1 or cfg['approval_ref']!=APPROVAL: raise ValueError('pilot_go_schema')
    expiry=datetime.fromisoformat(cfg['expires_at'])
    if expiry.tzinfo is None or expiry>datetime(2026,10,27,14,tzinfo=timezone.utc) or datetime.now(timezone.utc)+timedelta(seconds=330)>=expiry:
        raise ValueError('pilot_execution_window_insufficient')
    own=Path(__file__).resolve().parent
    if set(cfg['source_sha256'])!=set(FILES): raise ValueError('pilot_source_set')
    for name,sha in cfg['source_sha256'].items():
        if hashlib.sha256((own/name).read_bytes()).hexdigest()!=sha: raise ValueError('pilot_source_changed')
    for key in ('nebius','e2b'):
        if hashlib.sha256(read_private(cfg[key+'_key_path'])).hexdigest()!=cfg[key+'_key_sha256']: raise ValueError('pilot_key_identity_changed')
    if hashlib.sha256(read_private(cfg['supervisor_template_path'])).hexdigest()!=cfg['supervisor_template_sha256']:
        raise ValueError('supervisor_template_changed')
    return cfg


class Admission:
    def __init__(self,path,digest): self.path,self.digest=path,digest
    def authorize(self,arms,budget):
        load(self.path,self.digest)
        return budget.calls==12 and budget.output_tokens==49152 and budget.input_tokens is None and budget.active_seconds==180


def json_default(value):
    if is_dataclass(value): return asdict(value)
    if hasattr(value,'model_dump'): return value.model_dump(mode='json')
    raise TypeError(type(value).__name__)


async def run_approved(path,digest):
    cfg=load(path,digest)
    # Fresh process only: configure telemetry BEFORE importing Strands.
    from process_adapter import initialize_process
    initialize_process()
    from e2b import Sandbox
    from e2b_transport import PilotPool
    from task_adapter import stage,FILES as PUBLIC_FILES
    from controller import Budget,run_pair
    from nebius_worker import NebiusCLIWorker
    from worker_funding import WorkerFunding,PRICING_SHA
    from review import OwnedReview
    from public_request import build_public_request
    from pilot_process import pilot_model,close_pilot
    from remote_grade import RemoteGrade
    output=Path(cfg['output_dir']);output.mkdir(mode=0o700,parents=False,exist_ok=False)
    event_path=output/'events.jsonl'
    def emit(**event):
        record={'ts':datetime.now(timezone.utc).isoformat(),'worker_model':'nebius/deepseek-ai/DeepSeek-V4.1-Flash-1017',
                'supervisor_model':'nvidia/nemotron-3-super-120b-a12b',**event}
        with event_path.open('a',encoding='utf8') as f:
            os.chmod(event_path,0o600);f.write(json.dumps(record,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
    package=Path(cfg['package_path']).resolve();staging=output/'staged'
    frozen,prompt=stage(package,staging)
    budget=Budget(calls=12,input_tokens=None,output_tokens=49152,active_seconds=180)
    arms={c:{'condition':c,'workspace':str(staging/'workers'/c),'prompt':prompt,'public_sha256':frozen['public_sha256'],
             'worker_identity':'nebius/deepseek-ai/DeepSeek-V4.1-Flash-1017'} for c in ('baseline','pex')}
    (output/'frozen.json').write_text(json.dumps({'task':frozen,'worker_budget_each':asdict(budget),
       'funding_split_nano_usd':{'baseline':375000000,'pex':375000000,'supervisor':250000000},'go_sha256':digest,'grading_order':'per_arm_after_MCP_revocation_hidden_until_both_terminal',
       'scope':'actual CLI remote-tools engine pilot; not web UI E2E; same VM grading anti-tamper limited'},sort_keys=True))
    external_sources={name:hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest() for name in ('remote_grade','task_adapter','e2b_transport','opencode_cli','worker_funding')}
    (output/'external-source-sha256.json').write_text(json.dumps(external_sources,sort_keys=True))
    pool=PilotPool(Sandbox,read_private(cfg['e2b_key_path']).decode().strip(),approved=True)
    remotes={}
    def prepare(condition):
        load(path,digest)
        remote=pool.create('baseline' if condition=='baseline' else 'supervised');remotes[condition]=remote
        emit(event='isolated_workspace_created',arm=condition)
        if remote.run('mkdir -p tests; git init -q')['exit_code']!=0: raise ValueError('remote_setup_failed')
        for name in PUBLIC_FILES:
            data=(staging/'workers'/condition/name).read_text();remote.write(name,data)
            if remote.read(name)!=data: raise ValueError('remote_public_bytes_differ')
        if remote.run('git add . && git -c user.name=PEX -c user.email=pex@example.invalid commit -qm frozen-public-input')['exit_code']!=0:
            raise ValueError('remote_initial_snapshot_failed')
        return remote
    admission=Admission(path,digest)
    supervisor_path=output/'supervisor.json';supervisor_digest=None
    def model_factory(role,request,proposal):
        nonlocal supervisor_digest
        load(path,digest)
        if supervisor_digest is None:
            template=json.loads(read_private(cfg['supervisor_template_path']))
            template['request_binding']={'goal_id':request.goal.id,'session_id':request.session.id,'vendor_session_id':request.session.vendor_session_id}
            template['ledger_path']=str(output/'supervisor-pilot.sqlite')
            raw=json.dumps(template,sort_keys=True,separators=(',',':')).encode()
            fd=os.open(supervisor_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(raw)
            supervisor_digest=hashlib.sha256(raw).hexdigest()
        return pilot_model(supervisor_path,request,invocation_id='paired-'+uuid.uuid4().hex,
                           proposal=proposal,expected_config_sha256=supervisor_digest)
    worker=None;funding={}
    try:
        for condition in arms:
            funding[condition]=WorkerFunding(output/'worker-funding.sqlite',arm=condition,approved_config_digest=digest,approval_ref=cfg['approval_ref'],pricing_provenance_sha256=PRICING_SHA)
        worker=NebiusCLIWorker(remotes={c:(lambda c=c:prepare(c)) for c in arms},private_root=output/'cli',
                         binary=cfg['binary_path'],modules=cfg['modules_path'],key_path=cfg['nebius_key_path'],pool=pool,activate=True,funding=funding)
        review=OwnedReview(build_public_request,model_factory,mode='live-pilot',admission=admission)
        grader=RemoteGrade(remotes=remotes,package=package,stopped=lambda condition: worker.states.get(condition,{}).get('stopped',False))
        report=await run_pair(arms,worker,review,grader,budget=budget,mode='live-pilot',admission=admission,emit=emit)
        report['worker_funding']=next(iter(funding.values())).summary()
        (output/'report.json').write_text(json.dumps(report,default=json_default,sort_keys=True,indent=2))
        os.chmod(output/'report.json',0o600)
        # Only after BOTH arms terminal is a coarse paired score exposed.
        emit(event='paired_results_available',terminal='recorded',arms={c:{'status':v['status'],'grade':v.get('protected_grade',{}).get('summary')} for c,v in report['arms'].items()})
        return {'report_path':str(output/'report.json'),'event_path':str(event_path),'status':'terminal'}
    finally:
        cleanup_errors=[]
        try:
            if supervisor_digest is not None: close_pilot(supervisor_path,expected_config_sha256=supervisor_digest)
        except Exception as error:
            cleanup_errors.append('supervisor:'+type(error).__name__)
        finally:
            try: pool.close()
            except Exception as error: cleanup_errors.append('VM:'+type(error).__name__)
        for ledger in funding.values():
            try: ledger.close()
            except Exception as error: cleanup_errors.append('funding:'+type(error).__name__)
        if cleanup_errors:
            emit(event='cleanup_unconfirmed',terminal=';'.join(cleanup_errors))
            raise RuntimeError('cleanup_unconfirmed:'+','.join(cleanup_errors))


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);parser.add_argument('--sha256',required=True)
    parser.add_argument('--execute-approved-pilot',action='store_true');args=parser.parse_args()
    if not args.execute_approved_pilot: raise SystemExit('Default closed: explicit root execution required')
    try:
        print(json.dumps(asyncio.run(run_approved(args.config,args.sha256))))
    except Exception as error:
        # Raw SDK/request exceptions may contain secrets; public output is type only.
        print(json.dumps({'status':'pilot_inconclusive','category':type(error).__name__}))
        raise SystemExit(1)
