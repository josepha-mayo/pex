"""Authored model/tool responses exercising actual review composition; no inference."""
import json
import pytest
from process_adapter import fixture_model
from managed_chat import Limits,Route
from test_process import Ledger
from test_managed_chat import ENDPOINT,MODEL,response,rig,no_network
from test_tool_transport import payload
from test_snapshot_protocol_parity import request as snapshot_request
from review import OwnedReview

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['snapshot','acceptance-only','unknown-id','unbound-id','missing-boundary'])
async def test_snapshot_goal_boundary_and_lineage_composition(tmp_path,rig,mode):
    models=[]
    def build(arm,observation,session_id):
        req=snapshot_request();req.session.vendor_session_id=session_id
        req.scores.features['verification']={'status':'unavailable','acceptance_status':'uncertain'}
        return req
    def factory(role,request,proposal):
        route=Route(ENDPOINT,MODEL,role,Limits(max_usage_tokens=10000))
        ledger=Ledger(tmp_path/(str(len(models))+role+'.sqlite'),budget=100000,input_rate=2,output_rate=3,route=route)
        model=fixture_model(route,request,invocation_id='snapshot-'+str(len(models))+role,ledger=ledger,proposal=proposal)
        models.append(model);return model
    def handler(request):
        model=models[-1];n=len(model.observations)
        if n==0:return response(payload('get_goal','{"boundary_page":0}','goal'))
        if n==1:
            name='inspect_acceptance' if mode=='acceptance-only' and model.protocol.role=='verifier' else 'inspect_public_snapshot'
            return response(payload(name,'{}','state'))
        refs=[o.observation_id for o in model.observations]
        if model.protocol.role=='verifier':
            if mode=='unknown-id':refs=['not-a-real-observation']
            if mode=='unbound-id':refs=[o.observation_id for o in models[0].observations]
            if mode=='missing-boundary':refs=refs[1:]
        args={'rationale':'AUTHORED composition fixture','evidence':['AUTHORED static snapshot review'],'evidence_refs':refs}
        if model.protocol.role=='planner':args.update(action_type='CONTINUE_SESSION',message='AUTHORED fixture continuation')
        else:args.update(approved=True)
        return response(payload(model.protocol.final_name,json.dumps(args),'final'))
    rig.handler=handler
    result=await OwnedReview(build,factory).review({}, {'authored':True},session_id='fixture-session')
    assert result['status']==('approved_continuation' if mode=='snapshot' else 'verifier_rejected')
    assert len(models)==2
    assert result['receipt']['verifier_observed']==(mode=='snapshot')
