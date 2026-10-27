"""Trusted remote public diff collector; no imports of candidate code."""
from pathlib import Path,PurePosixPath
import subprocess
LIMIT=15900
root=Path.cwd()
parts=[]
tracked=subprocess.run(['git','diff','--','.'],capture_output=True,check=True).stdout
status=subprocess.run(['git','status','--short'],capture_output=True,check=True).stdout
untracked=subprocess.run(['git','ls-files','--others','--exclude-standard','-z','--','stockroom','tests'],capture_output=True,check=True).stdout
parts.append(b'PUBLIC git status:\n'+status+b'\nPUBLIC new-file contents:\n')
for raw in untracked.split(b'\0'):
    if not raw:continue
    name=raw.decode('utf8');p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or p.parts[0] not in ('stockroom','tests'):raise ValueError('invalid_public_file')
    path=root/name
    if path.resolve()!=path or not path.is_file():
        parts.append(b'\n[nonregular public file omitted] '+raw+b'\n');continue
    parts.append(b'\n--- NEW '+raw+b' ---\n')
    with path.open('rb') as f: data=f.read(LIMIT+1)
    if len(data)>LIMIT:data=data[:LIMIT]+b'\n[file contents truncated]\n'
    parts.append(data+b'\n')
    if sum(map(len,parts))>LIMIT:break
parts.append(b'\nPUBLIC tracked diff:\n'+tracked)
data=b''.join(parts)
if len(data)>LIMIT:data=data[:LIMIT]+b'\n[public diff truncated; not a complete review]\n'
print(data.decode('utf8','replace'))
