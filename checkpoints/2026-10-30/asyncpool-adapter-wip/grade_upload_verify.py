"""Trusted VM-only snapshot readback; never imports candidate on controller.

Public tests execute BEFORE protected inputs are uploaded. Both test commands
and all8 acceptance checks are unchanged. Hash checks are not a claim of
adversarial isolation; the same-VM grader's explicit limitations still apply.
"""
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import sys

# Marker is used by authored serializer mocks, not as execution evidence.
SCHEMA='pex.asyncpool-upload-verified.v1'
spec=json.loads(sys.argv[1]);root=spec['root'];expected=spec['files'];mode=spec['mode']
assert set(spec)=={'root','files','mode'} and mode in ('public','protected')
assert re.fullmatch(r'/tmp/pex-asyncpool-evaluation-[0-9a-f]{32}',root)
assert os.path.realpath(root)==root and type(expected)is dict and 1<=len(expected)<=130
allowed=set()
for name,sha in expected.items():
 p=PurePosixPath(name)
 assert not p.is_absolute() and '..' not in p.parts and str(p)==name
 assert re.fullmatch('[0-9a-f]{64}',sha)
 assert name.startswith('candidate/') or (mode=='protected' and name in ('run_grade.py','test_acceptance.py'))
 allowed.update(str(parent) for parent in p.parents if str(parent)!='.')
seen=set();total=0
for directory,dirs,files in os.walk(root,followlinks=False):
 for name in dirs:
  path=os.path.join(directory,name);relative=os.path.relpath(path,root)
  assert not os.path.islink(path) and relative in allowed
 for name in files:
  path=os.path.join(directory,name);relative=os.path.relpath(path,root)
  assert relative in expected and os.path.realpath(path)==path
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
  try:
   before=os.fstat(fd)
   assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=262144
   data=os.read(fd,262145);after=os.fstat(fd)
   assert (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
   assert len(data)==before.st_size and hashlib.sha256(data).hexdigest()==expected[relative]
   total+=len(data);assert total<=262144
   seen.add(relative)
  finally:os.close(fd)
assert seen==set(expected)
receipt=hashlib.sha256((json.dumps(expected,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
print('PEX_SNAPSHOT_VERIFIED:'+receipt,flush=True)
if mode=='public':
 os.chdir(root+'/candidate')
 os.execv(sys.executable,[sys.executable,'-B','-m','unittest','discover','-s','tests','-v'])
else:
 assert {'run_grade.py','test_acceptance.py'}<=seen
 os.chdir(root)
 os.execv(sys.executable,[sys.executable,'-I','-B','run_grade.py','candidate'])
