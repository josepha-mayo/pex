import hashlib
import ipaddress
import json
from pathlib import Path
import pytest
import supervisor_diagnostic as sd
from test_managed_chat import no_network as no_network,rig as rig,response
from test_tool_protocol import request_fixture,final_arguments
from test_tool_transport import payload

@pytest.mark.asyncio
async def test_remaining_budget_real_protocol_authored_only(tmp_path,rig,monkeypatch):
    import managed_chat
    tmp_path.chmod(0o700)
    request=request_fixture(with_boundaries=True)
    request.notes='PARTIAL HISTORICAL: not exact controller evidence'
    request.scores.features['verification']={'acceptance_status':'uncertain'}
    p=tmp_path/'request.json';p.write_text(request.model_dump_json());p.chmod(0o600)
    key=tmp_path/'key';key.write_text('fixture-no-provider-credential');key.chmod(0o600)
    c={'request_path':str(p),'output_dir':str(tmp_path/'diagnostic-output'),'key_path':str(key),'key_sha256':hashlib.sha256(key.read_bytes()).hexdigest(),'pricing_provenance_sha256':'a'*64,'expires_at':'2026-10-27T16:00:00+00:00','platform_proxy':{}}
    monkeypatch.setattr(sd,'load',lambda *args:(c,{'remaining_nano_usd':{'supervisor':167670400},'remaining_attempts':{'supervisor':11},'charged_nano_usd':{'supervisor':82329600,'baseline':10081800,'pex':9382800}}))
    monkeypatch.setattr(managed_chat,'_PilotProxyBinding',lambda **kw:None)
    async def resolve(*args):return ipaddress.ip_address('93.184.216.34')
    monkeypatch.setattr(managed_chat,'_resolve_public_address',resolve)
    def handler(wire):
        data=payload('get_goal','{"boundary_page":0}') if len(rig.calls)==1 else payload('SupervisorDecision',json.dumps(final_arguments('planner')),'final')
        data['model']='nvidia/nemotron-3-super-120b-a12b'
        return response(data)
    rig.handler=handler
    result=await sd.run(tmp_path/'config.json','a'*64)
    assert result['status']=='real_supervisor_protocol_completed'
    assert result['attempts']==2 and result['charged_nano_usd']==12600
    assert result['worker_or_VM_dispatches']==result['continuation_dispatches']==0
    assert result['cumulative_nebius_nano_usd']==101806800
