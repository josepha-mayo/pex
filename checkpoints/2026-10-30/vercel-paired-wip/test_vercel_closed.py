"""AUTHORED local capability/transport fixtures; no provider/VM/model calls."""
import json,hashlib,threading,time
from pathlib import Path
import pytest
import vercel_admission as a
import vercel_history as h
from vercel_composition import source_pins,build_composition
from vercel_accounting import StagedAccounting
from vercel_remote import VercelRemote,BoundedRemoteError,call,atomic

@pytest.fixture
def admitted(tmp_path,monkeypatch):
 tmp_path.chmod(0o700)
 from test_staged_admission import candidate as unused
 def pin(p):return {'path':str(p),'sha256':a.sha(p.read_bytes())}
 old=json.loads(Path('/tmp/pex-paired-live-20261030/wirepool-staged-pair-20261030-04/pair.json').read_bytes())
 profile=dict(old['profile']);profile.pop('compute_cap');profile['provider_cap']=a.PROVIDER_ENVELOPE
 profile['runtime_contract']={'python_implementation':'CPython','python_version':'3.14.0','sqlite_version':'3.50.0','workspace':'/vercel/sandbox/pex-task'}
 ledgers={}
 for n in h.required_predecessors():
  p=tmp_path/n;p.write_bytes(b'AUTHORED_HISTORY_NOT_REAL');p.chmod(0o600);ledgers[n]=pin(p)
 prior={'schema':'pex.staged.predecessors.v1','provider_nano_usd':a.PRIOR_PROVIDER,'compute_nano_usd':a.PRIOR_E2B_COMPUTE,'uncertain_reservations_retained':True,'ledgers':ledgers}
 p=tmp_path/'prior.json';p.write_bytes(a.canonical(prior));p.chmod(0o600)
 q=tmp_path/'qualification.json';q.write_bytes(a.canonical({'schema':'pex.vercel.qualification.v1','passed':True,'project_id':'AUTHORED-PROJECT','runtime_contract':profile['runtime_contract']}));q.chmod(0o600)
 u=tmp_path/'usage.json';u.write_bytes(a.canonical({'schema':'pex.vercel.usage.v1','metered_limit_nano_usd':5000000000,'reserved_nano_usd':0}));u.chmod(0o600)
 key=tmp_path/'AUTHORED-KEY';key.write_text('AUTHORED-NOT-A-CREDENTIAL');key.chmod(0o600)
 import os
 for alias in ('HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','https_proxy','http_proxy','all_proxy'):monkeypatch.setenv(alias,'http://127.0.0.1:1')
 ca=tmp_path/'CA';ca.write_text('AUTHORED');ca.chmod(0o600)
 monkeypatch.setenv('SSL_CERT_FILE',str(ca))
 cfg={'schema':'pex.vercel.closed-candidate.v1','approval_ref':'AUTHORED-NOT-LIVE','run_id':'wirepool-vercel-pair-authored','expires_at':'2099-01-01T00:00:00+00:00','profile':profile,'predecessor':pin(p),'sources':source_pins(),'task':old['task'],'network':{'proxy_sha256':a.sha(os.environ['HTTPS_PROXY'].encode()),'ca':pin(ca)},'output_dir':str(tmp_path/'run'),'nebius_key':pin(key),'cli':old['cli'],'vercel':{'team_id':'AUTHORED-TEAM','project_id':'AUTHORED-PROJECT','image':'AUTHORED-IMAGE','persistent':False,'network_policy':{'allow':{}},'vcpus':1,'timeout_ms':750000,'metered_limit_usd':5,'qualification':pin(q),'prior_usage':pin(u)}}
 raw=a.canonical(cfg);p=tmp_path/'pair.json';p.write_bytes(raw);p.chmod(0o600)
 grant=a.Grant(cfg['approval_ref'],cfg['run_id'],str(p),a.sha(raw),a.sha(a.canonical(profile)),cfg['predecessor']['sha256'],a.sha(a.canonical(cfg['sources'])),cfg['task']['sha256'],cfg['expires_at'])
 monkeypatch.setattr(a,'APPROVED_VERCEL_GRANT',a.GrantGate.identity(grant))
 return a.load(grant)

def test_closed_before_reads(monkeypatch):
 monkeypatch.setattr(a,'APPROVED_VERCEL_GRANT',None)
 monkeypatch.setattr(a,'read_pin',lambda *x,**k:pytest.fail('closed before reads'))
 with pytest.raises(a.AdmissionRefused,match='approval_pending'):a.load(None)

def test_real_composition_with_authored_admission_no_dispatch(admitted):
 with a.VercelBinding(admitted)as binding:
  accounting=StagedAccounting(binding);composition=build_composition(accounting)
  try:
   composition.verify(composition.arms,composition.worker,composition.review,composition.grader)
   assert composition.worker.worker.vercel_binding is binding
   assert composition.grader.grade_impl.check_count==8
   assert accounting.summary()['provider_cumulative_nano_usd']==a.PRIOR_PROVIDER
   assert accounting.summary()['compute_cumulative_bound_nano_usd']==a.PRIOR_E2B_COMPUTE
   assert not list((binding.rpc_root/'requests').iterdir())
  finally:composition.supervisor.close();accounting.close()

def test_single_claim_no_resume(admitted):
 with a.VercelBinding(admitted):pass
 with pytest.raises(a.AdmissionRefused,match='fresh_claim'):a.VercelBinding(admitted).__enter__()

@pytest.mark.parametrize('path',['../x','/etc/passwd','wirepool/../x','.secret','wirepool//x','x\\y'])
def test_public_paths_refuse_escape(path):
 with pytest.raises(BoundedRemoteError):VercelRemote.path(path)

def test_rpc_exact_request_response_and_no_host_candidate_execution(admitted):
 with a.VercelBinding(admitted)as b:
  def broker():
   p=b.rpc_root/'requests/000001.json'
   while not p.exists():time.sleep(.01)
   raw=p.read_bytes();v=json.loads(raw)
   assert v['operation']=='run' and v['args']=={'command':'AUTHORED-NOT-EXECUTED','cwd':'/vercel/sandbox/pex-task'}
   atomic(b.rpc_root/'responses/000001.json',{'schema':'pex.vercel.rpc-response.v1','run_id':v['run_id'],'config_sha256':v['config_sha256'],'sequence':1,'request_sha256':a.sha(raw),'ok':True,'result':{'exit_code':0,'stdout':'AUTHORED','stderr':''},'error':None,'raw_native_receipt_sha256':'a'*64})
  t=threading.Thread(target=broker);t.start();r=VercelRemote(b,'baseline',{'session_id':'AUTHORED'},time.monotonic()+10);r.set_scope_deadline(time.monotonic()+2)
  assert r.run('AUTHORED-NOT-EXECUTED')['stdout']=='AUTHORED';t.join();assert not r.poisoned

def test_unknown_rpc_poison_preserves_request(admitted):
 with a.VercelBinding(admitted)as b:
  r=VercelRemote(b,'baseline',{'session_id':'AUTHORED'},time.monotonic()+10);r.set_scope_deadline(time.monotonic()+.05)
  with pytest.raises(BoundedRemoteError,match='unconfirmed'):r.run('AUTHORED-NOT-EXECUTED')
  assert r.poisoned and (b.rpc_root/'uncertain-000001.json').exists()
  with pytest.raises(BoundedRemoteError,match='scope_closed'):r.run('NO-RETRY')
  assert len(list((b.rpc_root/'requests').iterdir()))==1
