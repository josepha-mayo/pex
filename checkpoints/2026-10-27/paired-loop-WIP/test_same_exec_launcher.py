"""Authored same-exec derivation; no keys, clients, network or resources."""
import asyncio
import hashlib
import json
from pathlib import Path
import pytest
import pilot_nebius
from same_exec_launcher import bind_root_policy,validate_platform_proxy,sha

def private(path,value):
    raw=json.dumps(value,sort_keys=True).encode();path.write_bytes(raw);path.chmod(0o600);return sha(raw)

@pytest.fixture
def setup(monkeypatch,tmp_path):
    tmp_path.chmod(0o700)
    ca=tmp_path/'ca.pem';ca.write_text('AUTHORED CA BYTES')
    proxy='http://127.0.0.1:51234'
    monkeypatch.setenv('HTTPS_PROXY',proxy);monkeypatch.setenv('SSL_CERT_FILE',str(ca))
    template={'endpoint':'https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions','model':'nvidia/nemotron-3-super-120b-a12b','budget_nano_usd':250000000,'max_attempts':12,'platform_proxy':{'proxy_sha256':'a'*64,'ca_path':str(ca),'ca_sha256':sha(ca.read_bytes())}}
    t=tmp_path/'template.json';td=private(t,template)
    cfg={'output_dir':str(tmp_path/'new-uncreated-run'),'supervisor_template_path':str(t),'supervisor_template_sha256':td,
         'source_sha256':{'same_exec_launcher.py':sha(Path(__file__).with_name('same_exec_launcher.py').read_bytes())}}
    driver=tmp_path/'static.json';driver_sha=private(driver,cfg)
    def load(path,digest):
        assert path==driver and digest==driver_sha
        return dict(cfg)
    monkeypatch.setattr(pilot_nebius,'load',load)
    policy=tmp_path/'policy.json';policy_sha=private(policy,{'schema':1,'mode':'same_exec_provided_platform_proxy','driver_config_path':str(driver),'driver_config_sha256':driver_sha})
    return policy,policy_sha,tmp_path/'derived',cfg,template,proxy

def test_exact_delegation_preserves_every_other_field(setup):
    policy,digest,dest,cfg,template,proxy=setup
    bound=bind_root_policy(policy,digest,dest);bound.assert_same_execution_environment()
    derived=json.loads(bound.path.read_bytes());t=json.loads(Path(derived['supervisor_template_path']).read_bytes())
    assert {k:v for k,v in derived.items() if k not in {'supervisor_template_path','supervisor_template_sha256'}}=={k:v for k,v in cfg.items() if k not in {'supervisor_template_path','supervisor_template_sha256'}}
    assert {k:v for k,v in t.items() if k!='platform_proxy'}=={k:v for k,v in template.items() if k!='platform_proxy'}
    assert t['platform_proxy']=={**template['platform_proxy'],'proxy_sha256':sha(proxy.encode())}
    assert sha(bound.path.read_bytes())==bound.digest
    assert all(f.stat().st_mode&0o077==0 and proxy.encode() not in f.read_bytes() for f in dest.iterdir())
    assert not Path(cfg['output_dir']).exists()

def test_static_policy_tamper_rejected_before_derivation(setup):
    policy,digest,dest,*_=setup
    with pytest.raises(ValueError,match='static_policy'):bind_root_policy(policy,'b'*64,dest)
    assert not dest.exists()

def test_existing_closed_run_cannot_be_rebound(setup):
    policy,digest,dest,cfg,*_=setup;Path(cfg['output_dir']).mkdir()
    with pytest.raises(ValueError,match='existing_run'):bind_root_policy(policy,digest,dest)
    assert not dest.exists()

def test_changed_tool_exec_proxy_refused(setup,monkeypatch):
    policy,digest,dest,*_=setup;bound=bind_root_policy(policy,digest,dest)
    monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:51235')
    with pytest.raises(ValueError,match='same_execution'):bound.assert_same_execution_environment()
    with pytest.raises(ValueError,match='before_resources'):validate_platform_proxy(json.loads(bound.path.read_bytes()),pilot_nebius.read_private)

def test_CA_change_cannot_be_rebound(setup,monkeypatch):
    policy,digest,dest,*_=setup;monkeypatch.setenv('SSL_CERT_FILE','/different/CA')
    with pytest.raises(ValueError,match='ca_path'):bind_root_policy(policy,digest,dest)

def test_paid_entry_rejects_changed_proxy_before_framework_or_resources(setup):
    policy,digest,dest,cfg,*_=setup
    # Static old-proxy template is intentionally not launchable across executions.
    with pytest.raises(ValueError,match='before_resources'):
        asyncio.run(pilot_nebius.run_approved(Path(json.loads(policy.read_bytes())['driver_config_path']),json.loads(policy.read_bytes())['driver_config_sha256']))
