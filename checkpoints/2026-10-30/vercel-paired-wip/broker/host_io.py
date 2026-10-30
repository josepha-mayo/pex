"""Fixed local file-RPC IO. Never executes request contents or provider commands."""
import base64,hashlib,json,os,re,stat,sys
from pathlib import Path
MAX=8*1024*1024

def digest(b):return hashlib.sha256(b).hexdigest()
def wire(v):return json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()
def read(p,limit=MAX):
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  s=os.fstat(fd)
  if not stat.S_ISREG(s.st_mode)or s.st_nlink!=1 or s.st_size>limit:raise ValueError('regular_bounded_file_required')
  b=os.read(fd,limit+1)
  if len(b)!=s.st_size:raise ValueError('changed_file')
  return b
 finally:os.close(fd)
def publish(p,b):
 if len(b)>MAX:raise ValueError('output_bound')
 t=p.with_name('.'+p.name+'.tmp')
 fd=os.open(t,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb')as f:f.write(b);f.flush();os.fsync(f.fileno())
  os.link(t,p,follow_symlinks=False)
 finally:t.unlink(missing_ok=True)
 return digest(b)
def main(root,payload):
 root=Path(root)
 if not root.is_absolute()or root.is_symlink()or root.resolve()!=root:raise ValueError('canonical_private_root_required')
 if not root.is_dir()or root.stat().st_mode&0o077:raise ValueError('private_rpc_root_required')
 for name in ('requests','responses','receipts','journal'):
  p=root/name
  p.mkdir(mode=0o700,exist_ok=True)
  if p.is_symlink()or p.resolve()!=p:raise ValueError('canonical_child_required')
 a=json.loads(base64.b64decode(payload,validate=True));op=a['op']
 if op=='next':
  n=a['sequence'];assert type(n)is int and 1<=n<=999999
  name=f'{n:06d}.json';p=root/'requests'/name
  if (root/'journal'/name).exists():raise ValueError('prior_attempt_requires_manual_reconciliation')
  if (root/'responses'/name).exists():raise ValueError('prior_response_requires_manual_reconciliation')
  if not p.exists():return None
  b=read(p,2*1024*1024)
  return {'request':json.loads(b),'request_sha256':digest(b)}
 if op=='put':
  name=a['name']
  if not re.fullmatch(r'(?:receipts/[0-9]{6}-[a-z0-9-]+\.json|journal/[0-9]{6}\.json|responses/[0-9]{6}\.json|(?:owned|stopped)-(?:baseline|pex)\.json)',name):raise ValueError('output_path_bound')
  return {'sha256':publish(root/name,wire(a['value']))}
 raise ValueError('unknown_io_operation')
def entry(root,mode,payload):
 if mode=='direct':return main(root,payload)
 r=Path(root)
 if not r.is_absolute()or r.resolve()!=r or not r.is_dir()or r.stat().st_mode&0o077:raise ValueError('private_root_required')
 p=r/'.bridge-input'
 if mode in ('begin','append'):
  if len(payload)>60000 or not re.fullmatch('[A-Za-z0-9+/=]*',payload):raise ValueError('chunk_bound')
  flags=os.O_WRONLY|os.O_NOFOLLOW|(os.O_CREAT|os.O_EXCL if mode=='begin' else os.O_APPEND)
  fd=os.open(p,flags,0o600)
  try:
   st=os.fstat(fd)
   if not stat.S_ISREG(st.st_mode)or st.st_nlink!=1 or st.st_size+len(payload)>12*1024*1024:raise ValueError('input_bound')
   with os.fdopen(fd,'wb',closefd=False)as f:f.write(payload.encode())
  finally:os.close(fd)
  return True
 if mode=='finish':
  try:return main(root,read(p,12*1024*1024).decode())
  finally:p.unlink(missing_ok=True)
 raise ValueError('input_mode')
if __name__=='__main__':
 try:print(json.dumps({'ok':True,'result':entry(sys.argv[1],sys.argv[2],sys.argv[3])},separators=(',',':')))
 except Exception as e:print(json.dumps({'ok':False,'error':str(e)[:160]},separators=(',',':')));sys.exit(1)
