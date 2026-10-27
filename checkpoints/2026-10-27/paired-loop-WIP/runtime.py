"""Credential-free composed-runtime preflight or separately admitted pilot launch.

Uses existing frozen Strands interpreter plus append-only E2B SDK site directory.
No installation, credential read, client construction or network call in check mode.
Run check and launch as separate fresh processes to preserve NoOp-before-Strands.
"""
import argparse
import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
STRANDS=ROOT/'pex-supervisor-model-only-GUARDED-WORKING-20261026-2051'
PYTHON=STRANDS/'.venv/bin/python'
SDK_SITE=Path('/tmp/pex-e2b-sdk-261/lib/python3.12/site-packages')
PATHS=(ROOT/'pex-supervisor-process-WORKING-20261027-0127',
       ROOT/'managed-transport-TOOLS-WORKING-20261026-2126',
       Path(__file__).resolve().parent,
       ROOT/'pex-paired-readiness-WORKING-20261027-0021',
       ROOT/'pex-paired-task-adapter-WORKING-20261027-0100',
       ROOT/'pex-e2b-transport-WIP-20261027-1024',
       STRANDS/'packages/protocol/src',STRANDS/'services/supervisor/src',STRANDS/'services/bridge/src')
PACKAGES={'strands-agents':'1.53.0','httpx':'0.28.1','opentelemetry-api':'1.45.1','e2b':'2.61.0','connectrpc':'0.12.1','pyqwest':'0.12.0'}
PACKAGE=ROOT/'pex-owncloud-recovered-baseline-20261026-2010/archived-packages/pex-benchmark-hardening-20261023-v2/pex-benchmark-hardening/pex_real_pilot'

def configure():
    if Path(sys.prefix).resolve()!=(STRANDS/'.venv').resolve() or sys.version_info[:2]!=(3,12):
        raise RuntimeError('intended_frozen_interpreter_required')
    if not SDK_SITE.is_dir() or any(not p.is_dir() for p in PATHS):raise RuntimeError('composed_module_path_missing')
    sys.path[:0]=[str(p) for p in PATHS]
    sys.path.append(str(SDK_SITE)) # existing frozen dependencies retain precedence
    versions={name:importlib.metadata.version(name) for name in PACKAGES}
    if versions!=PACKAGES:raise RuntimeError('composed_dependency_version_changed')
    return versions

def check_runtime():
    versions=configure()
    from process_adapter import initialize_process
    telemetry=initialize_process()
    names=('e2b','strands','pilot_nebius','nebius_worker','controller','review','public_request',
           'remote_mcp','budget_rpc','remote_grade','task_adapter','e2b_transport','opencode_cli',
           'opencode_v2_receipt','worker_funding','pilot_process')
    modules={name:importlib.import_module(name) for name in names}
    supervisor=modules['pilot_process']
    source_sha={name:hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest() for name in supervisor.SOURCE_MODULES}
    task=modules['task_adapter'];raw=task.read_regular(PACKAGE,'MANIFEST.json')
    if task.digest(raw)!=task.MANIFEST_SHA256:raise RuntimeError('frozen_manifest_changed')
    manifest=json.loads(raw)
    checked=['INITIAL_PROMPT.txt',*[f'public/{task.TASK}/{n}' for n in task.FILES],*task.PROTECTED]
    for name in checked:
        if task.digest(task.read_regular(PACKAGE,name))!=manifest['files'][name]:raise RuntimeError('frozen_benchmark_bytes_changed')
    return {'status':'imports_and_frozen_inputs_verified_no_calls','python':str(PYTHON),'python_version':sys.version.split()[0],
            'module_paths':[str(p) for p in PATHS],'sdk_site_appended':str(SDK_SITE),'versions':versions,'telemetry':telemetry,
            'resolved_modules':{name:str(Path(module.__file__).resolve()) for name,module in modules.items()},
            'benchmark_package':str(PACKAGE),'benchmark_manifest_sha256':task.MANIFEST_SHA256,
            'supervisor_source_sha256':source_sha,
            'pilot_source_sha256':{n:hashlib.sha256((Path(__file__).resolve().parent/n).read_bytes()).hexdigest() for n in modules['pilot_nebius'].FILES},
            'live_gate_open':modules['pilot_nebius'].APPROVAL is not None}

if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check-runtime',action='store_true');group.add_argument('--execute-approved-pilot',action='store_true')
    parser.add_argument('--config',type=Path);parser.add_argument('--sha256');args=parser.parse_args()
    try:
        if args.check_runtime:
            if args.config or args.sha256:raise ValueError('check_mode_never_reads_private_config')
            print(json.dumps(check_runtime(),sort_keys=True,indent=2))
        else:
            if args.config is None or args.sha256 is None:raise ValueError('explicit_config_and_digest_required')
            configure() # no framework import; run_approved owns fresh NoOp init
            from pilot_nebius import run_approved
            print(json.dumps(asyncio.run(run_approved(args.config,args.sha256))))
    except Exception as error:
        print(json.dumps({'status':'inconclusive','category':type(error).__name__}))
        raise SystemExit(1)
