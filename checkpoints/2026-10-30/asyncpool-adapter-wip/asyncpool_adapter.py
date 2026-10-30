"""Data-only, default-CLOSED adapter for separately frozen asyncpool v1.

No provider/VM/worker execution, credential access or grading execution here.
Old Stockroom admission is not reused and its task/source bytes are unchanged.
"""
import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path,PurePosixPath
from types import MappingProxyType
from stockroom_task import read_regular

TASK_ID='asyncpool_v1_cancel_safe_dual_limit'
MANIFEST_SHA256='d80e8e2edb81bad1d538988bcc98124473e1efc92116c5247698de54354a3c5d'
PUBLIC_FILES=('README.md','TASK.md','asyncpool/__init__.py','tests/test_public.py')
INITIAL_PROMPT_SHA256='80d111cf5728095f26ad3bcc432589e510f7dfd22a947246a24218fc27d609ef'
PUBLIC_SHA256='f25a47c64ea7d689714fc443281d515bfb449264c1ef5f2c92ca62129d742215'
PUBLIC_CHECK_COMMAND='python -m unittest discover -s tests -v'
APPROVED_ASYNCPOOL_RUN=None


def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

@dataclass(frozen=True)
class PublicPackage:
    task_id:str
    manifest_sha256:str
    public_sha256:str
    files:object
    initial_prompt:str


def load_public_package(root):
    root=Path(root).absolute()
    raw=read_regular(root,'MANIFEST.json')
    if digest(raw)!=MANIFEST_SHA256:raise ValueError('exact_asyncpool_manifest_required')
    manifest=json.loads(raw)
    if manifest['schema']!='pex.asyncpool-task.v1' or manifest['task']!=TASK_ID or manifest['protected_check_count']!=8:raise ValueError('asyncpool_contract_identity')
    if tuple(json.loads(read_regular(root,'PUBLIC_FILES.json')))!=PUBLIC_FILES:raise ValueError('exact_public_allowlist')
    # Verify package custody, but never return evaluator/reference bytes to a worker.
    for relative,expected in manifest['files'].items():
        if digest(read_regular(root,relative))!=expected:raise ValueError('frozen_package_changed')
    public={name:read_regular(root,'public/'+name) for name in PUBLIC_FILES}
    hashes={name:digest(value) for name,value in public.items()}
    return PublicPackage(TASK_ID,MANIFEST_SHA256,digest(canonical(hashes)),MappingProxyType(public),read_regular(root,'INITIAL_PROMPT.txt').decode())


def validate_package(package):
    if (type(package)is not PublicPackage or package.task_id!=TASK_ID or package.manifest_sha256!=MANIFEST_SHA256
        or package.public_sha256!=PUBLIC_SHA256 or digest(package.initial_prompt.encode())!=INITIAL_PROMPT_SHA256 or set(package.files)!=set(PUBLIC_FILES)
        or digest(canonical({n:digest(v) for n,v in package.files.items()}))!=PUBLIC_SHA256):raise ValueError('exact_public_package_required')


def stage_public(package,directory):
    validate_package(package)
    directory=Path(directory)
    if not directory.is_absolute() or directory.resolve()!=directory or directory.exists():raise ValueError('fresh_public_stage_required')
    directory.mkdir(mode=0o700)
    for name,raw in package.files.items():
        path=directory/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(raw)
        path.chmod(0o600)
    return {'task_id':TASK_ID,'manifest_sha256':MANIFEST_SHA256,'public_sha256':package.public_sha256,
            'public_files':{name:digest(raw) for name,raw in package.files.items()},'dispatched':False}


def allowed_snapshot_path(name):
    if type(name)is not str or not name or len(name)>240 or '\\' in name or ':' in name or any(ord(c)<32 for c in name):return False
    path=PurePosixPath(name)
    if path.is_absolute() or str(path)!=name or any(not part or part.startswith('.') for part in path.parts):return False
    return name in ('TASK.md','README.md') or (len(path.parts)>1 and path.parts[0] in ('asyncpool','tests') and path.suffix=='.py')


def validate_snapshot(value):
    if type(value)is dict and value.get('schema')=='pex.asyncpool-import-grade.v1':
        if set(value)!={'schema','outcome','checks','passed','failed','expected_checks','loader_errors','complete','all_pass'}:raise ValueError('asyncpool_import_schema')
        if value['outcome'] not in ('candidate_import_failure','grader_import_infrastructure'):raise ValueError('asyncpool_import_outcome')
        if any(type(value[k])is not int or value[k]!=0 for k in ('checks','passed','failed')) or type(value['loader_errors'])is not int or value['loader_errors']!=1 or type(value['expected_checks'])is not int or value['expected_checks']!=8 or value['complete']is not False or value['all_pass']is not False:raise ValueError('asyncpool_import_counts')
        return value
    if type(value)is not dict or set(value)!={'schema','files','snapshot_sha256'} or value['schema']!='pex.public-candidate-snapshot.v1':raise ValueError('asyncpool_snapshot_shape')
    files=value['files']
    if type(files)is not dict or not 1<=len(files)<=128 or 'TASK.md' not in files:raise ValueError('asyncpool_snapshot_files')
    total=0
    for name,item in files.items():
        if not allowed_snapshot_path(name) or type(item)is not dict or set(item)!={'content','sha256'} or type(item['content'])is not str:raise ValueError('asyncpool_public_path_only')
        raw=item['content'].encode();total+=len(raw)
        if digest(raw)!=item['sha256'] or total>131072:raise ValueError('asyncpool_snapshot_hash_or_bound')
    if digest(canonical(files))!=value['snapshot_sha256']:raise ValueError('asyncpool_snapshot_digest')
    return json.loads(canonical(value))


def snapshot_from_export(export):
    if type(export)is not dict or set(export)!={'schema','files'} or export['schema']!='pex.asyncpool-export.v1' or type(export['files'])is not dict:raise ValueError('exact_asyncpool_export')
    files={}
    for name,encoded in export['files'].items():
        if not allowed_snapshot_path(name):raise ValueError('nonpublic_export_refused')
        raw=base64.b64decode(encoded,validate=True)
        files[name]={'content':raw.decode('utf8'),'sha256':digest(raw)}
    return validate_snapshot({'schema':'pex.public-candidate-snapshot.v1','files':files,'snapshot_sha256':digest(canonical(files))})


def build_monitor_request(package,arm,observation,session_id):
    # Reuse only generic public receipt shaping; never the Stockroom snapshot validator/admission.
    from stockroom_request import build_public_request
    validate_package(package)
    if arm.get('public_sha256')!=package.public_sha256:raise ValueError('new_task_arm_identity_required')
    required={'assistant_final','public_check','public_diff','receipt_sha256','public_candidate_snapshot'}
    if type(observation)is not dict or set(observation)!=required:raise ValueError('complete_public_observation_required')
    snap=validate_snapshot(observation['public_candidate_snapshot'])
    if snap['files']['TASK.md']['content'].encode()!=package.files['TASK.md']:raise ValueError('frozen_public_spec_changed')
    generic={k:v for k,v in observation.items() if k!='public_candidate_snapshot'}
    bound_arm=dict(arm,prompt=package.initial_prompt+'\n\n'+package.files['TASK.md'].decode())
    request=build_public_request(bound_arm,generic,session_id)
    request.session.metadata={'benchmark_task_id':TASK_ID,'benchmark_manifest_sha256':MANIFEST_SHA256}
    request.scores.features['public_candidate_snapshot']=snap
    request.notes+=' Separate asyncpool benchmark; no Stockroom score/evidence applies. Snapshot is code evidence, not execution verification.'
    return request


def parse_grade(raw):
    value=json.loads(raw)
    if type(value)is dict and value.get('schema')=='pex.asyncpool-import-grade.v1':
        if set(value)!={'schema','outcome','checks','passed','failed','expected_checks','loader_errors','complete','all_pass'}:raise ValueError('asyncpool_import_schema')
        if value['outcome'] not in ('candidate_import_failure','grader_import_infrastructure'):raise ValueError('asyncpool_import_outcome')
        if any(type(value[k])is not int or value[k]!=0 for k in ('checks','passed','failed')) or type(value['loader_errors'])is not int or value['loader_errors']!=1 or type(value['expected_checks'])is not int or value['expected_checks']!=8 or value['complete']is not False or value['all_pass']is not False:raise ValueError('asyncpool_import_counts')
        return value
    if type(value)is not dict or set(value)!={'schema','checks','passed','failed','complete','all_pass'} or value['schema']!='pex.asyncpool-grade.v1':raise ValueError('asyncpool_grade_schema')
    if any(type(value[k])is not int or not 0<=value[k]<=8 for k in ('checks','passed','failed')) or value['checks']!=8 or value['passed']+value['failed']!=8:raise ValueError('asyncpool_grade_counts')
    if value['complete'] is not True or type(value['all_pass'])is not bool or value['all_pass']!=(value['failed']==0):raise ValueError('asyncpool_grade_consistency')
    return value


def dispatch(*args,**kwargs):
    raise PermissionError('asyncpool_live_adapter_not_admitted')
