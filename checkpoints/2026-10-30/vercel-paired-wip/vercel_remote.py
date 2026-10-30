"""Native-MCP file RPC only. No provider SDK, credential, socket or host execution.
The independently reviewed broker performs actual Vercel operations and writes
raw native receipts. Unknown operations poison work; cleanup stays available.
"""
import asyncio,base64,json,os,re,threading,time
from datetime import datetime,timezone,timedelta
from pathlib import Path,PurePosixPath
from types import SimpleNamespace
from vercel_admission import AdmissionRefused,VercelBinding,canonical,sha
from staged_envelope import SETUP_SECONDS,VM_SECONDS
ROOT='/vercel/sandbox/pex-task'
class BoundedRemoteError(RuntimeError):pass

def atomic(path,value):
 raw=canonical(value);fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb')as f:f.write(raw);f.flush();os.fsync(f.fileno())

def call(binding,arm,operation,args,deadline,*,cleanup=False):
 if type(binding)is not VercelBinding:raise AdmissionRefused('vercel_binding_type')
 if not cleanup:binding._check()
 if arm not in ('baseline','pex')or operation not in ('create','run','read','write_files','mkdir','list','stop'):raise BoundedRemoteError('vercel_rpc_operation')
 with binding.lock:
  remaining=deadline-time.monotonic()
  if remaining<=0:raise BoundedRemoteError('vercel_rpc_deadline')
  sequence=getattr(binding,'rpc_sequence',0)+1;binding.rpc_sequence=sequence
  value={'schema':'pex.vercel.rpc-request.v1','run_id':binding.admitted.grant.run_id,'config_sha256':binding.admitted.grant.config_sha256,'sequence':sequence,'arm':arm,'operation':operation,'args':args,'deadline_utc':(datetime.now(timezone.utc)+timedelta(seconds=remaining)).isoformat()}
  raw=canonical(value)
  if len(raw)>2*1024*1024:raise BoundedRemoteError('vercel_rpc_request_bound')
  request=binding.rpc_root/'requests'/f'{sequence:06d}.json';atomic(request,value)
  response=binding.rpc_root/'responses'/f'{sequence:06d}.json'
  while not response.exists():
   if time.monotonic()>=deadline:
    atomic(binding.rpc_root/f'uncertain-{sequence:06d}.json',{'request_sha256':sha(raw),'operation':operation,'arm':arm,'outcome':'unknown_no_retry'})
    raise BoundedRemoteError('vercel_native_operation_unconfirmed')
   time.sleep(.05)
  if response.is_symlink()or response.stat().st_size>3*1024*1024:raise BoundedRemoteError('vercel_rpc_response_bound')
  result=json.loads(response.read_bytes())
  if set(result)!={'schema','run_id','config_sha256','sequence','request_sha256','ok','result','error','raw_native_receipt_sha256'}or result['schema']!='pex.vercel.rpc-response.v1' or result['run_id']!=value['run_id']or result['config_sha256']!=value['config_sha256']or result['sequence']!=sequence or result['request_sha256']!=sha(raw)or type(result['ok'])is not bool or not re.fullmatch('[0-9a-f]{64}',result['raw_native_receipt_sha256']):raise BoundedRemoteError('vercel_rpc_response_identity')
  if result['ok']is not True:raise BoundedRemoteError('vercel_native_operation_failed')
  return result['result']

class VercelRemote:
 def __init__(self,binding,arm,identity,deadline):
  self.binding=binding;self.arm=arm;self.identity=identity;self.vm_deadline=deadline;self.deadline=None
  self.poisoned=False;self.closed=False;self.cancellation_unconfirmed=False;self.diagnostics={'provider':'vercel-native-mcp','operations':0};self.cleanup_evidence={}
 def set_scope_deadline(self,deadline):
  if self.poisoned or self.closed or self.deadline is not None or not time.monotonic()<deadline<=self.vm_deadline:raise BoundedRemoteError('vercel_scope_deadline')
  self.deadline=deadline
 async def end_scope(self):self.deadline=None
 def _call(self,op,args,timeout=None):
  if self.closed or self.poisoned or self.deadline is None:raise BoundedRemoteError('vercel_scope_closed')
  deadline=min(self.vm_deadline,self.deadline,time.monotonic()+timeout if timeout else self.deadline)
  try:
   result=call(self.binding,self.arm,op,args,deadline);self.diagnostics['operations']+=1;return result
  except BaseException:self.poisoned=True;raise
 @staticmethod
 def path(name):
  if type(name)is not str or not name or '\\'in name or '\0'in name:raise BoundedRemoteError('vercel_public_path')
  p=PurePosixPath(name)
  if p.is_absolute()or str(p)!=name or any(x in ('..','.')or x.startswith('.')for x in p.parts):raise BoundedRemoteError('vercel_public_path')
  return ROOT+'/'+name
 def run(self,command,timeout=None):
  if type(command)is not str or len(command.encode())>16384 or '\0'in command:raise BoundedRemoteError('vercel_command_bound')
  r=self._call('run',{'command':command,'cwd':ROOT},timeout)
  if type(r)is not dict or set(r)!={'exit_code','stdout','stderr'}or type(r['exit_code'])is not int or any(type(r[k])is not str or len(r[k].encode())>1048576 for k in ('stdout','stderr')):raise BoundedRemoteError('vercel_command_receipt')
  return r
 def read(self,path):return self._call('read',{'path':self.path(path)})
 def write(self,path,text):
  if type(text)is not str or len(text.encode())>262144:raise BoundedRemoteError('vercel_write_bound')
  return self._files({self.path(path):text.encode()})
 def list(self,path='.'):
  return self._call('list',{'path':ROOT if path in ('','.')else self.path(path)})
 def make_dir(self,path):
  if path!=ROOT:raise BoundedRemoteError('vercel_setup_root')
  return self._call('mkdir',{'path':ROOT})
 def _files(self,values):
  if type(values)is not dict or not values or len(values)>128:raise BoundedRemoteError('vercel_files_shape')
  files={};total=0
  for name,data in values.items():
   if type(name)is not str or type(data)is not bytes or not(name.startswith(ROOT+'/')or re.fullmatch(r'/tmp/pex-wirepool-evaluation-[0-9a-f]{32}/[^\\]+',name))or '..'in PurePosixPath(name).parts:raise BoundedRemoteError('vercel_exact_upload_scope')
   total+=len(data)
   if total>1048576:raise BoundedRemoteError('vercel_upload_bound')
   files[name]=base64.b64encode(data).decode()
  return self._call('write_files',{'files_base64':files})
 def write_files(self,values):return self._files({self.path(n):b for n,b in values.items()})
 def write_private_files(self,values):return self._files(values)
 async def close(self):
  if self.closed:return
  result=await asyncio.to_thread(call,self.binding,self.arm,'stop',{},time.monotonic()+30,cleanup=True)
  if type(result)is not dict or result.get('session_id')!=self.identity['session_id']or result.get('stopped')is not True:raise BoundedRemoteError('vercel_stop_unproven')
  self.closed=True;self.binding.stopped.add(self.identity['session_id']);self.cleanup_evidence={'stopped_confirmed':True,'provider':'vercel-native-mcp'}

class VercelLifecycle:
 def __init__(self,binding,stage_public):
  if type(binding)is not VercelBinding:raise AdmissionRefused('vercel_lifecycle_binding')
  self.api=SimpleNamespace(binding=binding);self.binding=binding;self.stage_public=stage_public;self.remotes={};self.unknown_creates=set();self.setup_timing={}
 async def prepare(self,arm,*,deadline):
  c=arm['condition'];self.binding._check()
  if c in self.remotes or c not in ('baseline','pex')or(c=='pex'and self.binding.owned-self.binding.stopped):raise AdmissionRefused('vercel_sequential_fresh_arms')
  started=time.monotonic();self.unknown_creates.add(c);v=self.binding.cfg['vercel']
  identity=await asyncio.to_thread(call,self.binding,c,'create',{'team_id':v['team_id'],'project_id':v['project_id'],'image':v['image'],'persistent':False,'network_policy':{'allow':{}},'vcpus':1,'timeout_ms':750000},min(deadline,started+SETUP_SECONDS))
  if type(identity)is not dict or not all(type(identity.get(k))is str and identity[k]for k in ('session_id','sandbox_id')):raise AdmissionRefused('vercel_actual_create_identity')
  self.unknown_creates.remove(c);self.binding.owned.add(identity['session_id']);self.binding.owned_by_arm[c]=identity['session_id']
  remote=VercelRemote(self.binding,c,identity,deadline);self.remotes[c]=remote
  remote.set_scope_deadline(min(deadline,started+SETUP_SECONDS))
  try:await self.stage_public(arm,remote)
  finally:await remote.end_scope()
  self.setup_timing[c]={'provider':'vercel-native-mcp','duration_seconds':time.monotonic()-started,'session_id':identity['session_id']}
  return remote
 async def cleanup(self):
  errors=[]
  for c,r in self.remotes.items():
   try:await r.close()
   except BaseException:errors.append(c)
  if errors or self.unknown_creates:raise BoundedRemoteError('vercel_cleanup_unconfirmed')
