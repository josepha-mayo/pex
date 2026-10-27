"""Data-only exact frozen task adapter. No runtime/provider/resource authority."""
import hashlib
import json
import os
from pathlib import Path
import stat

TASK='stockroom_v2_replay_revision'
MANIFEST_SHA256='c242f9128edd87b34c678e5e0db36527b556f0b2163533577e5c96320c3b5f19'
PUBLIC_CHECK_COMMAND='python -m unittest discover -s tests -v'
FILES=('.gitignore','README.md','TASK.md','stockroom/__init__.py','stockroom/__main__.py','stockroom/db.py','stockroom/records.py','stockroom/service.py','tests/test_legacy.py','tests/test_v2_examples.py')
PROTECTED=('protected/run_grade.py','protected/test_acceptance.py')
def digest(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def read_regular(root,relative):
    root=Path(root).absolute();path=root/relative
    if root.resolve(strict=True)!=root or path.resolve(strict=True)!=path:raise ValueError('linked_source_refused')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>524288:raise ValueError('bounded_regular_source_required')
        data=os.read(fd,524289);after=os.fstat(fd)
        if (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) or len(data)!=before.st_size:raise ValueError('source_changed')
        return data
    finally:os.close(fd)
def load_package(package):
    package=Path(package).absolute();raw=read_regular(package,'MANIFEST.json')
    if digest(raw)!=MANIFEST_SHA256:raise ValueError('frozen_manifest_mismatch')
    manifest=json.loads(raw)['files']
    data={}
    for rel in ['INITIAL_PROMPT.txt','PUBLIC_FILES.json']+['public/'+n for n in FILES]+list(PROTECTED):
        b=read_regular(package,rel)
        if digest(b)!=manifest[rel]:raise ValueError('frozen_source_mismatch')
        data[rel]=b
    if tuple(json.loads(data['PUBLIC_FILES.json']))!=FILES:raise ValueError('public_allowlist_mismatch')
    return data

def exclusive(path,data):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data)

def stage(package,destination):
    data=load_package(package);destination=Path(destination).absolute()
    if destination.parent.resolve(strict=True)!=destination.parent:raise ValueError('linked_destination')
    public={n:data['public/'+n] for n in FILES};hashes={n:digest(b) for n,b in public.items()}
    frozen={'schema':'pex.stockroom-pair-staging.v1','task':TASK,'suite_manifest_sha256':MANIFEST_SHA256,'public_files':hashes,'public_sha256':digest(encoded(hashes)),'prompt_sha256':digest(data['INITIAL_PROMPT.txt']),'execution_boundary_verified':False,'real_inference_calls':0,'quality_measured':False}
    destination.mkdir(mode=0o700,exist_ok=False)
    for condition in ('baseline','pex'):
        for name,b in public.items():exclusive(destination/'workers'/condition/name,b)
    exclusive(destination/'controller/staging.json',encoded(frozen))
    exclusive(destination/'controller/evaluator-inputs.json',encoded({'inputs':{n:digest(data[n]) for n in PROTECTED},'candidate_execution_permitted':False,'requires':['worker stop','MCP revocation','isolated remote grading','immutable candidate hashes']}))
    return frozen,data['INITIAL_PROMPT.txt'].decode()
