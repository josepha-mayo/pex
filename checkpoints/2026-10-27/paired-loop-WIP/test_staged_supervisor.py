"""Real owned supervisor protocol, exact routes, synthetic credentials/mock HTTP only."""
import json
from pathlib import Path
import pytest
from test_staged_accounting import funded
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
from test_managed_chat import rig,no_network,response
from test_tool_transport import payload
from test_tool_protocol import ProposedAction,InterventionType
from staged_supervisor import *
from stockroom_request import make_public_request
from successor_supervisor import WORKER,MODEL

@pytest.fixture
def supervisor(funded,monkeypatch,rig):
    accounting,scope=funded
    import managed_chat
    monkeypatch.setattr(managed_chat._PilotProxyBinding,'transport',lambda self,endpoint:rig.factory())
    runtime=StagedSupervisor(accounting)
    task=load_package(Path(accounting.cfg['task']['path']).parent)
    arm={'public_sha256':runtime.config['public_sha256'],'worker_identity':WORKER,'prompt':task['INITIAL_PROMPT.txt'].decode()}
    obs={'assistant_final':'Authored final','public_diff':'Authored public diff','receipt_sha256':'a'*64,
         'public_check':{'command':'python -m unittest discover -s tests -v','exit_code':0,'output':'Authored public check','receipt_sha256':'b'*64}}
    request=make_public_request(Path(accounting.cfg['task']['path']).parent)(arm,obs,'authored-vendor')
    try:yield runtime,request
    finally:runtime.close()

def test_default_no_supervisor_or_key_read():
    with pytest.raises(AdmissionRefused):StagedSupervisor(None)

@pytest.mark.parametrize('bound',['stockroom'],indirect=True)
def test_closed_runtime_no_transport_and_no_reopen(supervisor,rig):
    runtime,request=supervisor
    assert not rig.created and not rig.calls
    runtime.close()
    with pytest.raises(AdmissionRefused):runtime.model_factory('planner',request,None)
    with pytest.raises(AdmissionRefused):StagedSupervisor(runtime.accounting)

@pytest.mark.asyncio
@pytest.mark.parametrize('bound',['stockroom'],indirect=True)
async def test_full_owned_supervisor_shared_fresh_accounting(supervisor,rig):
    runtime,request=supervisor
    for role in ('planner','verifier'):
        proposal=None if role=='planner' else ProposedAction(type=InterventionType.NOOP,session_id=request.session.id,goal_id=request.goal.id,rationale='Authored')
        model=runtime.model_factory(role,request,proposal)
        def handler(wire):
            body=json.loads(wire.content)
            assert body['model']==MODEL and body['n']==1
            if len(model.observations)==0:result=payload('inspect_acceptance','{}','state')
            else:
                args={'rationale':'Authored decision','evidence':['Authored public evidence'],
                      'evidence_refs':[x.observation_id for x in model.observations]}
                if role=='planner':args['action_type']='NOOP'
                else:args['approved']=True
                result=payload(model.protocol.final_name,json.dumps(args),'final')
            result['model']=MODEL
            return response(result)
        rig.handler=handler
        result=await model.invoke_async()
        assert result is not None
    summary=runtime.summary()
    assert summary['supervisor_wire_attempts']==4 and summary['supervisor_fresh_overhead_nano_usd']>0
    assert summary['worker_fresh_nano_usd']=={'baseline':0,'pex':0}
    assert summary['provider_cumulative_nano_usd']==summary['prior_provider_nano_usd']+summary['supervisor_fresh_overhead_nano_usd']

@pytest.mark.parametrize('bound',['stockroom'],indirect=True)
def test_mutated_request_and_wrong_session_refused(supervisor,rig):
    runtime,request=supervisor
    model=runtime.model_factory('planner',request,None)
    request.session.vendor_session_id='wrong'
    with pytest.raises(ValueError):runtime.model_factory('planner',request,None)
    assert not rig.calls
