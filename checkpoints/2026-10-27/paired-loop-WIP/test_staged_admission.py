"""Synthetic admission fixtures only; no real credentials or runtime evidence."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import json
from pathlib import Path
import pytest
import staged_admission as a

@pytest.fixture
def candidate(tmp_path,monkeypatch):
    tmp_path.chmod(0o700)
    def pin(name,raw=b'authored'):
        p=tmp_path/name;p.write_bytes(raw);p.chmod(0o600)
        return {'path':str(p),'sha256':a.sha(raw)}
    prior={'schema':'pex.staged.predecessors.v1','provider_nano_usd':100,'compute_nano_usd':100,
           'uncertain_reservations_retained':True,'ledgers':{n:pin(n) for n in a.REQUIRED_PREDECESSORS}}
    profile={'provider_cap':a.PROVIDER_CAP,'compute_cap':a.COMPUTE_CAP,'worker_model':a.WORKER_MODEL,
        'supervisor_model':a.SUPERVISOR_MODEL,'phases':[vars(p) for p in a.PHASES],'vm_seconds':a.VM_SECONDS,
        'supervisor_attempts':12,'forced_textual_finalization':True,'equal_worker_fresh':400000000,'supervisor_fresh':500000000}
    ca=pin('synthetic-ca');proxy='http://authored.invalid:8888'
    monkeypatch.setenv('HTTPS_PROXY',proxy);monkeypatch.setenv('SSL_CERT_FILE',ca['path'])
    for n in ('E2B_API_URL','E2B_SANDBOX_URL','E2B_DOMAIN','E2B_DEBUG'):monkeypatch.delenv(n,raising=False)
    cfg={'schema':'pex.staged.closed-candidate.v1','approval_ref':'AUTHORED-NOT-LIVE','run_id':'authored-new',
        'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'profile':profile,
        'predecessor':pin('prior.json',a.canonical(prior)),'sources':{'synthetic':pin('source.py')},
        'sdk_sources':{'synthetic':pin('sdk.py')},'task':pin('task-manifest'),'network':{'proxy_sha256':a.sha(proxy.encode()),'ca':ca},
        'output_dir':str(tmp_path/'run'),'e2b_key':{'path':str(tmp_path/'KEY-MUST-NOT-EXIST'),'sha256':'a'*64}}
    def freeze():
        raw=a.canonical(cfg);pin('pair.json',raw)
        grant=a.Grant(cfg['approval_ref'],cfg['run_id'],str(tmp_path/'pair.json'),a.sha(raw),a.sha(a.canonical(profile)),
            cfg['predecessor']['sha256'],a.sha(a.canonical({k:cfg[k] for k in ('sources','sdk_sources')})),cfg['task']['sha256'],cfg['expires_at'])
        return raw,grant
    return cfg,freeze

def test_default_gate_before_any_read(monkeypatch):
    monkeypatch.setattr(a,'read_pin',lambda *x,**k:pytest.fail('must not read'))
    with pytest.raises(a.AdmissionRefused,match='approval_pending'):a.load()

def test_inspection_is_not_authority_or_key_read(candidate):
    cfg,freeze=candidate;raw,grant=freeze()
    assert a.inspect_candidate(raw,grant)['provider_reserved_ceiling']==1300000100
    with pytest.raises(a.AdmissionRefused):a.check_authority(a.Admitted(grant,raw,object()))
    assert not Path(cfg['e2b_key']['path']).exists()

@pytest.mark.parametrize('field',['profile','sources','sdk_sources','task','predecessor'])
def test_changed_bytes_refused(candidate,field):
    cfg,freeze=candidate;raw,grant=freeze()
    if field=='profile':cfg[field]['equal_worker_fresh']+=1
    elif field in ('sources','sdk_sources'):Path(next(iter(cfg[field].values()))['path']).write_bytes(b'changed')
    else:Path(cfg[field]['path']).write_bytes(b'changed')
    with pytest.raises((a.AdmissionRefused,ValueError)):a.inspect_candidate(a.canonical(cfg),grant)

@pytest.mark.parametrize('change',['proxy','ca','override','claim','output','expiry','budget','missing_prior','unequal'])
def test_semantic_admission_refusals(candidate,monkeypatch,change):
    cfg,freeze=candidate
    if change=='proxy':monkeypatch.setenv('HTTPS_PROXY','http://changed.invalid:9')
    elif change=='ca':Path(cfg['network']['ca']['path']).write_text('changed')
    elif change=='override':monkeypatch.setenv('E2B_API_URL','http://localhost:1')
    elif change=='claim':(Path(cfg['output_dir']).parent/'launch.claim').touch()
    elif change=='output':Path(cfg['output_dir']).mkdir()
    elif change=='expiry':cfg['expires_at']=datetime.now(timezone.utc).isoformat()
    elif change=='budget':cfg['profile']['equal_worker_fresh']=1000000000
    elif change=='unequal':cfg['profile']['pex_worker_fresh']=1
    else:
        p=Path(cfg['predecessor']['path']);v=json.loads(p.read_bytes());v['ledgers'].pop('null_function06')
        p.write_bytes(a.canonical(v));cfg['predecessor']['sha256']=a.sha(p.read_bytes())
    raw,grant=freeze()
    with pytest.raises((a.AdmissionRefused,ValueError)):a.inspect_candidate(raw,grant)

def test_synthetic_gate_exact_config_revalidation(candidate,monkeypatch):
    cfg,freeze=candidate;raw,grant=freeze();monkeypatch.setattr(a,'APPROVED_STAGED_GRANT',grant)
    admitted=a.load();copy=admitted.config();copy['run_id']='changed'
    assert admitted.config()['run_id']=='authored-new'
    monkeypatch.setattr(a,'APPROVED_STAGED_GRANT',None)
    with pytest.raises(a.AdmissionRefused):admitted.config()
