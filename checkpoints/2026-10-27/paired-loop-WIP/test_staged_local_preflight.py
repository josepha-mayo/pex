# ruff: noqa: F401,F811
"""Actual pinned CLI --version and exact local admission; no provider/VM call."""
import hashlib
import pytest
from test_staged_admission import candidate
from staged_worker_admission import preflight_worker_configuration
from staged_admission import AdmissionRefused
from test_staged_cli_transport import BINARY,MODULES,PIN


def actual_CLI(cfg):
    package=MODULES/'@opencode/plugin/package.json'
    cfg['cli']={'binary':{'path':str(BINARY),'sha256':PIN},'modules_path':str(MODULES),
        'plugin_package':{'path':str(package),'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}}
    return cfg


def test_actual_local_preflight_passes_before_any_claim_or_VM(candidate,tmp_path,monkeypatch):
    cfg,_=candidate;actual_CLI(cfg)
    monkeypatch.setenv('ALL_PROXY','http://127.0.0.1:1');monkeypatch.setenv('all_proxy','http://127.0.0.1:2')
    tmp_path.chmod(0o700)
    result=preflight_worker_configuration(cfg,tmp_path,check_credentials=False)
    assert result['status']=='passed' and result['CLI_version']=='2.1.4'
    assert result['SDK_clients_or_claims_created']==result['provider_or_model_calls']==0
    assert result['canonical_HTTPS_proxy_identity_preserved'] and result['ALL_PROXY_fallbacks_not_inherited']
    assert not(tmp_path/'launch.claim').exists() and not(tmp_path/'run').exists()


def test_preflight_route_mismatch_refuses_before_CLI_or_VM(candidate,tmp_path,monkeypatch):
    import subprocess
    cfg,_=candidate;actual_CLI(cfg);tmp_path.chmod(0o700)
    monkeypatch.setenv('HTTPS_PROXY','http://AUTHORED-WRONG.invalid')
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:pytest.fail('CLI must not start after admission mismatch'))
    with pytest.raises(AdmissionRefused,match='proxy_changed'):preflight_worker_configuration(cfg,tmp_path)
    assert not(tmp_path/'launch.claim').exists() and not(tmp_path/'run').exists()
