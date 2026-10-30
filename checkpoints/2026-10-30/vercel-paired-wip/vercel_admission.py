"""Separate default-closed Vercel admission; never an E2B binding or credential.
Native connector broker owns Vercel authentication. Only Nebius key pins remain
on this controller; candidate VM receives no key or ambient environment.
"""
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json,os,time,threading
from types import SimpleNamespace
from staged_admission import AdmissionRefused,read_pin,canonical,sha,validate_transport
from staged_envelope import PHASES,VM_SECONDS,WALL_PROFILE
from wirepool_adapter import MANIFEST_SHA256
import vercel_history

PRIOR_PROVIDER=3_244_879_800
PRIOR_E2B_COMPUTE=1_258_432_500
PROVIDER_ENVELOPE=5_094_879_800
APPROVED_VERCEL_GRANT=None
_SEAL=object()
@dataclass(frozen=True)
class Grant:
 approval_ref:str
 run_id:str
 config_path:str
 config_sha256:str
 profile_sha256:str
 predecessor_sha256:str
 sources_sha256:str
 task_sha256:str
 expires_at:str
@dataclass(frozen=True)
class GrantGate:
 approval_ref:str
 run_id:str
 config_path:str
 expires_at:str
 @classmethod
 def identity(cls,g):return cls(g.approval_ref,g.run_id,g.config_path,g.expires_at)
@dataclass(frozen=True)
class Admitted:
 grant:Grant
 raw:bytes
 seal:object
 def config(self):
  if self.seal is not _SEAL:raise AdmissionRefused('vercel_admission_seal')
  return json.loads(self.raw)

def inspect_candidate(raw,grant,*,initial=True):
 if type(grant)is not Grant or type(raw)is not bytes or sha(raw)!=grant.config_sha256:raise AdmissionRefused('vercel_config_identity')
 cfg=json.loads(raw)
 if set(cfg)!={'schema','approval_ref','run_id','expires_at','profile','predecessor','sources','task','network','output_dir','nebius_key','cli','vercel'}or cfg['schema']!='pex.vercel.closed-candidate.v1':raise AdmissionRefused('vercel_separate_config_schema')
 if (cfg['run_id']!=grant.run_id or not grant.run_id.startswith('wirepool-vercel-pair-')or cfg['approval_ref']!=grant.approval_ref or cfg['expires_at']!=grant.expires_at):raise AdmissionRefused('vercel_exact_run')
 expiry=datetime.fromisoformat(grant.expires_at)
 if expiry.tzinfo is None or datetime.now(timezone.utc)+timedelta(seconds=2*VM_SECONDS+30 if initial else 0)>=expiry:raise AdmissionRefused('vercel_execution_window')
 p=cfg['profile']
 expected_profile={'provider_cap','worker_model','supervisor_model','phases','vm_seconds','wall_profile','equal_worker_fresh','worker_output_per_call','supervisor_fresh','supervisor_attempts','forced_textual_finalization','public_snapshot_inspection','grade_phase0_after_final','runtime_contract','supervisor_pricing_sha256'}
 if type(p)is not dict or set(p)!=expected_profile:raise AdmissionRefused('vercel_exact_profile_fields')
 if p['worker_model']!='deepseek-ai/DeepSeek-V4.1-Flash-1017' or p['supervisor_model']!='nvidia/nemotron-3-super-120b-a12b':raise AdmissionRefused('vercel_frozen_models')
 if sha(canonical(p))!=grant.profile_sha256:raise AdmissionRefused('vercel_profile_pin')
 for k,v in {'provider_cap':PROVIDER_ENVELOPE,'equal_worker_fresh':750000000,'worker_output_per_call':16384,'supervisor_fresh':350000000,'supervisor_attempts':12,'phases':[vars(x)for x in PHASES],'vm_seconds':VM_SECONDS,'wall_profile':dict(WALL_PROFILE),'public_snapshot_inspection':True,'grade_phase0_after_final':True,'forced_textual_finalization':True}.items():
  if p.get(k)!=v:raise AdmissionRefused('vercel_equal_frozen_budgets')
 v=cfg['vercel']
 if set(v)!={'team_id','project_id','image','persistent','network_policy','vcpus','timeout_ms','metered_limit_usd','qualification','prior_usage'}or v['persistent']is not False or v['network_policy']!={'allow':{}}or v['vcpus']!=1 or v['timeout_ms']!=750000 or v['metered_limit_usd']!=5:raise AdmissionRefused('vercel_deny_all_ephemeral_scope')
 if not all(type(v[k])is str and v[k]for k in ('team_id','project_id','image')):raise AdmissionRefused('vercel_owned_project_identity')
 for k in ('qualification','prior_usage'):read_pin(v[k],private=True)
 qualification=json.loads(read_pin(v['qualification'],private=True))
 if qualification.get('schema')!='pex.vercel.qualification.v1' or qualification.get('passed')is not True or qualification.get('project_id')!=v['project_id']or qualification.get('runtime_contract')!=p.get('runtime_contract'):raise AdmissionRefused('vercel_actual_runtime_qualification')
 usage=json.loads(read_pin(v['prior_usage'],private=True))
 if usage.get('schema')!='pex.vercel.usage.v1' or usage.get('metered_limit_nano_usd')!=5000000000 or type(usage.get('reserved_nano_usd'))is not int or not 0<=usage['reserved_nano_usd']<5000000000:raise AdmissionRefused('vercel_separate_usage_ledger')
 prior=json.loads(read_pin(cfg['predecessor'],private=True))
 if prior.get('provider_nano_usd')!=PRIOR_PROVIDER or prior.get('compute_nano_usd')!=PRIOR_E2B_COMPUTE or prior.get('uncertain_reservations_retained')is not True:raise AdmissionRefused('vercel_prior_liabilities_retained')
 if cfg['predecessor']['sha256']!=grant.predecessor_sha256:raise AdmissionRefused('vercel_prior_pin')
 if set(prior['ledgers'])!=vercel_history.required_predecessors():raise AdmissionRefused('vercel_complete_historical_pins')
 for pin in prior['ledgers'].values():read_pin(pin,private=True,limit=32*1024*1024)
 if cfg['task']['sha256']!=MANIFEST_SHA256 or grant.task_sha256!=MANIFEST_SHA256:raise AdmissionRefused('vercel_task_identity')
 read_pin(cfg['task'])
 if not cfg['sources']or sha(canonical(cfg['sources']))!=grant.sources_sha256:raise AdmissionRefused('vercel_source_set')
 for pin in cfg['sources'].values():read_pin(pin)
 validate_transport(cfg['network'])
 config=Path(grant.config_path);output=Path(cfg['output_dir'])
 if not config.is_absolute()or config.resolve()!=config or config.name!='pair.json' or config.parent.stat().st_mode&0o077 or output!=config.parent/'run':raise AdmissionRefused('vercel_private_output')
 for name in ('nebius_key',):
  if set(cfg[name])!={'path','sha256'}or type(cfg[name]['path'])is not str or len(cfg[name]['sha256'])!=64:raise AdmissionRefused('vercel_existing_key_pin')
 if initial and ((Path(grant.config_path).parent/'launch.claim').exists()or Path(cfg['output_dir']).exists()):raise AdmissionRefused('vercel_fresh_claim_required')
 return cfg

def load(grant):
 if APPROVED_VERCEL_GRANT is None or type(grant)is not Grant or GrantGate.identity(grant)!=APPROVED_VERCEL_GRANT:raise AdmissionRefused('vercel_approval_pending')
 raw=read_pin({'path':grant.config_path,'sha256':grant.config_sha256},private=True)
 inspect_candidate(raw,grant)
 return Admitted(grant,raw,_SEAL)

class VercelBinding:
 """Owns only a native-connector RPC queue; no Vercel or E2B tokens."""
 def __init__(self,admitted):
  if type(admitted)is not Admitted or admitted.seal is not _SEAL:raise AdmissionRefused('vercel_admitted_required')
  self.admitted=admitted;self.cfg=admitted.config();self.clock=time.monotonic;self.active=False;self.cleanup_only=False
  self.owned=set();self.stopped=set();self.uncertain=set();self.owned_by_arm={};self.lock=threading.RLock()
  self.compute=SimpleNamespace(total=lambda:PRIOR_E2B_COMPUTE)
  self.rpc_root=Path(admitted.grant.config_path).parent/'native-rpc'
 def __enter__(self):
  inspect_candidate(self.admitted.raw,self.admitted.grant)
  p=Path(self.admitted.grant.config_path).parent/'launch.claim'
  fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb')as f:f.write(canonical({'schema':'pex.vercel.claim.v1','run_id':self.admitted.grant.run_id,'config_sha256':self.admitted.grant.config_sha256}));f.flush();os.fsync(f.fileno())
  self.rpc_root.mkdir(mode=0o700);(self.rpc_root/'requests').mkdir(mode=0o700);(self.rpc_root/'responses').mkdir(mode=0o700)
  self.active=True;return self
 def _check(self):
  if not self.active or self.cleanup_only:raise AdmissionRefused('vercel_binding_closed')
  if APPROVED_VERCEL_GRANT!=GrantGate.identity(self.admitted.grant):raise AdmissionRefused('vercel_gate_revoked')
  if sha(Path(self.admitted.grant.config_path).read_bytes())!=self.admitted.grant.config_sha256:raise AdmissionRefused('vercel_config_changed')
  inspect_candidate(self.admitted.raw,self.admitted.grant,initial=False)
 def begin_cleanup(self):self.cleanup_only=True
 def vercel_usage(self):
  p=self.rpc_root/'usage.json'
  return json.loads(read_pin({'path':str(p),'sha256':sha(p.read_bytes())},private=True))if p.exists()else {'status':'not_dispatched','metered_limit_usd':5,'invoice_verified':False}
 def proof_pins(self):
  result={}
  for arm in ('baseline','pex'):
   for kind in ('owned','stopped'):
    p=self.rpc_root/f'{kind}-{arm}.json'
    if p.exists():result[f'{kind}-{arm}']={'path':str(p),'sha256':sha(p.read_bytes())}
  return result
 def __exit__(self,*args):self.active=False
