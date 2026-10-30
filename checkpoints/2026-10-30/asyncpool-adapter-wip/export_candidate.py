"""Trusted export program. Executed only inside remote VM, not imported by host.
Exports all implementation/tests files, including newly added helpers/resources.
"""
import base64
import json
import os
from pathlib import Path
import stat
ROOT=Path.cwd()
MAX_FILES=128
MAX_TOTAL=131072
names=['TASK.md']+[n for n in ('.gitignore','README.md') if (ROOT/n).exists()]
for directory in ('asyncpool','tests'):
    top=ROOT/directory
    if top.is_symlink() or not top.is_dir():raise ValueError('required_plain_directory')
    for parent,dirs,files in os.walk(top,followlinks=False):
        for d in dirs:
            if (Path(parent)/d).is_symlink():raise ValueError('symlink_directory_refused')
        dirs[:]=[d for d in dirs if d!='__pycache__']
        for name in files:
            if not name.endswith('.py'):continue
            names.append(str((Path(parent)/name).relative_to(ROOT)))
if len(names)>MAX_FILES:raise ValueError('file_count_bound')
files={};total=0
for name in sorted(names):
    p=ROOT/name
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>MAX_TOTAL:raise ValueError('plain_bounded_file_required')
        b=os.read(fd,MAX_TOTAL+1);after=os.fstat(fd)
        if (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) or len(b)!=before.st_size:raise ValueError('file_changed')
    finally:os.close(fd)
    total+=len(b)
    if total>MAX_TOTAL:raise ValueError('aggregate_byte_bound')
    files[name]=base64.b64encode(b).decode('ascii')
print(json.dumps({'schema':'pex.asyncpool-export.v1','files':files},sort_keys=True))
