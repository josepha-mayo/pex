"""Exact public-only batch staging; no create, provider or task execution authority."""
import hashlib
import json
import shlex
import time
from stockroom_task import read_regular,encoded
from wirepool_adapter import PUBLIC_FILES as FILES
ROOT='/vercel/sandbox/pex-task'
MAX_BYTES=262144

# Runs on the already-owned pristine VM, BEFORE any worker. Readback verifies
# every file plus the complete tree; no uploaded Python/task code is imported.
VERIFY = '''import hashlib,json,os,stat,subprocess,sys
import sqlite3,unittest,platform
root=os.getcwd()
assert os.path.realpath(root)==root
expected_runtime=json.loads(sys.argv[2]) if len(sys.argv)>2 else None
actual_runtime={'python_implementation':platform.python_implementation(),'python_version':platform.python_version(),'sqlite_version':sqlite3.sqlite_version,'workspace':root}
if expected_runtime is not None:assert actual_runtime==expected_runtime
expected=json.loads(sys.argv[1])
assert len(expected)==8
allowed_dirs={os.path.dirname(n) for n in expected if os.path.dirname(n)}
seen=set()
for directory,dirs,files in os.walk(root,followlinks=False):
 for name in dirs:
  p=os.path.join(directory,name);rel=os.path.relpath(p,root)
  assert not os.path.islink(p) and rel in allowed_dirs
 for name in files:
  p=os.path.join(directory,name);rel=os.path.relpath(p,root)
  assert rel in expected and os.path.realpath(p)==p
  fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
  try:
   before=os.fstat(fd)
   assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=262144
   data=os.read(fd,262145);after=os.fstat(fd)
   assert (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
   assert len(data)==before.st_size and hashlib.sha256(data).hexdigest()==expected[rel]
   seen.add(rel)
  finally:os.close(fd)
assert seen==set(expected)
env=dict({k:v for k,v in os.environ.items() if not k.startswith('GIT_')},GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null')
for command in (['git','--version'],['git','init','-q'],['git','-c','core.hooksPath=/dev/null','add','--','.'],['git','-c','core.hooksPath=/dev/null','-c','user.name=PEX','-c','user.email=pex@example.invalid','commit','-qm','frozen-public-input']):
 subprocess.run(command,check=True,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
result={'schema':'pex.public-setup.v1','files':expected}
if expected_runtime is not None:result['runtime']=actual_runtime
print(json.dumps(result,sort_keys=True,separators=(',',':')))
'''


def stage_public_files(remote,directory,expected_hashes,record,*,runtime_contract=None):
    """Three bounded logical remote operations; record attempts even on failure.

    Counts are logical bridge operations, not asserted wire request totals. A
    cancelled/late operation is not reported as completed or refunded.
    """
    started=time.monotonic();operations=[];succeeded=False;runtime_verified=None
    def call(name,fn):
        row={'operation':name,'started_after_seconds':time.monotonic()-started,'completed':False}
        operations.append(row)
        try:
            value=fn();row['completed']=True;return value
        finally:row['elapsed_seconds']=time.monotonic()-started-row['started_after_seconds']
    try:
        if runtime_contract is not None and (type(runtime_contract)is not dict or set(runtime_contract)!={'python_implementation','python_version','sqlite_version','workspace'} or any(type(v)is not str or not v for v in runtime_contract.values())):raise ValueError('exact_runtime_contract_required')
        if set(expected_hashes)!=set(FILES):raise ValueError('exact_public_file_set_required')
        values={n:read_regular(directory,n) for n in FILES}
        if any(len(b)>MAX_BYTES for b in values.values()) or sum(map(len,values.values()))>MAX_BYTES:
            raise ValueError('public_batch_size_bound')
        if {n:hashlib.sha256(b).hexdigest() for n,b in values.items()}!=expected_hashes:
            raise ValueError('frozen_public_bytes_changed')
        call('root_mkdir',lambda:remote.make_dir(ROOT))
        call('sdk_batch_write',lambda:remote.write_files(values))
        command='python3 -I -c '+shlex.quote(VERIFY)+' '+shlex.quote(json.dumps(expected_hashes,sort_keys=True,separators=(',',':')))
        if runtime_contract is not None:command+=' '+shlex.quote(json.dumps(runtime_contract,sort_keys=True,separators=(',',':')))
        result=call('digest_readback_and_git_snapshot',lambda:remote.run(command))
        expected={'schema':'pex.public-setup.v1','files':expected_hashes}
        if runtime_contract is not None:expected['runtime']=runtime_contract
        if result['exit_code']!=0 or result['stdout']!=encoded(expected).decode() or result['stderr']:
            raise RuntimeError('remote_public_setup_unproven')
        succeeded=True;runtime_verified=runtime_contract
    finally:
        record({'schema':'pex.public-setup-timing.v1','elapsed_seconds':time.monotonic()-started,
            'logical_remote_operations':operations,'logical_attempt_count':len(operations),
            'logical_completed_count':sum(x['completed'] for x in operations),
            'wire_request_count':None,'public_file_count':len(FILES),'setup_complete':succeeded,
            'runtime_contract_verified':runtime_verified,
            'uncertainty_preserved':True,'setup_deadline_extended':False})
