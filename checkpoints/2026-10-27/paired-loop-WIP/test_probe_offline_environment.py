"""Pure launch-environment check; real binary/process/network never used."""
import asyncio
import hashlib
import json
from types import SimpleNamespace
import probe_free as pf

def test_probe_declares_catalog_update_and_background_disabled(tmp_path,monkeypatch):
    binary=tmp_path/'inert-not-executable';binary.write_bytes(b'authored inert binary bytes')
    monkeypatch.setattr(pf,'PIN',hashlib.sha256(binary.read_bytes()).hexdigest())
    modules=tmp_path/'inert-modules';modules.mkdir()
    key=tmp_path/'synthetic.key';key.write_text('SYNTHETIC-NO-PROVIDER');key.chmod(0o600)
    observed=[]
    async def never_launch(**kwargs):
        env=kwargs['environment'];observed.append(env)
        for name in ('OPENCODE_DISABLE_MODELS_FETCH','OPENCODE_DISABLE_AUTOUPDATE','OPENCODE_DISABLE_FREE_MODELS'):
            assert env[name]=='1'
        return SimpleNamespace(messages=['authored'],stdout_sha256='a'*64)
    monkeypatch.setattr(pf,'run_turn',never_launch)
    output=tmp_path/'run'
    result=asyncio.run(pf.probe(binary=binary,modules=modules,key_path=key,output=output,base='http://127.0.0.1:1/v1'))
    cfg=json.loads((output/'case/opencode.json').read_text())
    assert observed and cfg['update']=='disable' and cfg['warming'] is False and cfg['share']=='disabled'
    assert result['wire']['attempts']==0 and result['live'] is False
