"""Inert handoff checks. execv is intercepted; no process/provider/VM is run."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import pytest
import same_exec_handoff as h

class HandedOff(BaseException):
    pass

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    tmp_path.chmod(0o700)
    ca=tmp_path/'ca';ca.write_bytes(b'AUTHORED NOT A CERTIFICATE');ca.chmod(0o600)
    launcher=tmp_path/'launch_once.py';launcher.write_bytes(b'# inert launcher');launcher.chmod(0o600)
    proxy='http://authored.invalid:8080';monkeypatch.setenv('HTTPS_PROXY',proxy);monkeypatch.setenv('SSL_CERT_FILE',str(ca));monkeypatch.setenv('AUTHORED_HANDOFF_MARKER','same-environment')
    cfg={'network':{'proxy_sha256':h.sha(proxy.encode()),'ca':{'path':str(ca),'sha256':h.sha(ca.read_bytes())}}}
    config=tmp_path/'pair.json';config.write_text(json.dumps(cfg));config.chmod(0o600)
    return {'config_path':config,'config_sha256':h.sha(config.read_bytes()),'launcher_sha256':h.sha(launcher.read_bytes())},ca,launcher

def test_execv_inherits_environment_without_replacing_it(fixture):
    args,ca,launcher=fixture;before=dict(os.environ)
    with patch.object(h.os,'execv',side_effect=HandedOff) as called:
        with pytest.raises(HandedOff):h.exec_verified_launcher(**args)
    called.assert_called_once_with(sys.executable,[sys.executable,str(launcher),'--execute-exact-approved-pair',args['config_sha256']])
    assert dict(os.environ)==before

@pytest.mark.parametrize('change',['config','proxy','ca_path','ca_bytes','launcher'])
def test_changed_identity_prevents_handoff(fixture,monkeypatch,change):
    args,ca,launcher=fixture
    if change=='config':args['config_path'].write_text('{}')
    elif change=='proxy':monkeypatch.setenv('HTTPS_PROXY','http://different.invalid:8080')
    elif change=='ca_path':monkeypatch.setenv('SSL_CERT_FILE',str(ca)+'-other')
    elif change=='ca_bytes':ca.write_bytes(b'CHANGED')
    elif change=='launcher':launcher.write_bytes(b'CHANGED')
    with patch.object(h.os,'execv',side_effect=AssertionError('must not run')):
        with pytest.raises(h.AdmissionRefused):h.exec_verified_launcher(**args)

def test_empty_proxy_prevents_handoff(fixture,monkeypatch):
    args,_,_=fixture;monkeypatch.delenv('HTTPS_PROXY')
    with patch.object(h.os,'execv',side_effect=AssertionError('must not run')):
        with pytest.raises(h.AdmissionRefused):h.exec_verified_launcher(**args)

def test_unexpected_execv_return_is_not_success(fixture):
    args,_,_=fixture
    with patch.object(h.os,'execv',return_value=None):
        with pytest.raises(RuntimeError,match='unexpectedly_returned'):h.exec_verified_launcher(**args)
