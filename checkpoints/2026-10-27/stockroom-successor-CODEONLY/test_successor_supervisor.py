"""Owned planner/verifier with authored in-memory HTTP wire responses only.
External sockets/DNS forbidden by autouse no_network fixture.
"""
from datetime import datetime,timezone,timedelta
import hashlib
import importlib
import json
from pathlib import Path
import pytest
import successor_supervisor as ss
from test_managed_chat import no_network as no_network,rig as rig,response
from test_tool_protocol import final_arguments,ProposedAction,InterventionType
from test_tool_transport import payload
from stockroom_task import load_package,FILES,digest,encoded
from stockroom_request import make_public_request
TASK=Path(__file__).resolve().parent.parent/'pex-hard-task-candidate-20261027-1421'

@pytest.fixture
def configured(tmp_path,monkeypatch,rig):
    tmp_path.chmod(0o700);monkeypatch.setattr(ss,'APPROVED_RETRY_REF','AUTHORED-NOT-LIVE')
    key=tmp_path/'key';key.write_text('fixture-no-provider-credential');key.chmod(0o600)
    ca=tmp_path/'ca';ca.write_text('fixture-ca-no-network')
    proxy='http://authored.invalid:8080';monkeypatch.setenv('HTTPS_PROXY',proxy);monkeypatch.setenv('SSL_CERT_FILE',str(ca))
    data=load_package(TASK);public=digest(encoded({n:digest(data['public/'+n]) for n in FILES}))
    config={'schema':'pex.supervisor-successor.v1','approval_ref':'AUTHORED-NOT-LIVE','run_id':'authored-successor','expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'endpoint':ss.ENDPOINT,'model':ss.MODEL,'budget_nano_usd':300000000,'max_attempts':12,'input_rate':300,'output_rate':900,'pricing_provenance_sha256':'d'*64,'key':{'path':str(key),'sha256':digest(key.read_bytes())},'ledger_path':str(tmp_path/'supervisor.sqlite'),'source_sha256':{name:digest(Path(importlib.import_module(name).__file__).read_bytes()) for name in ss.SOURCE_MODULES},'package_path':str(TASK),'public_sha256':public,'predecessor_sha256':'e'*64,'prior_charged_nano_usd':10000000,'platform_proxy':{'proxy_sha256':digest(proxy.encode()),'ca_path':str(ca),'ca_sha256':digest(ca.read_bytes())}}
    path=tmp_path/'supervisor.json'
    def save():path.write_text(json.dumps(config,sort_keys=True));path.chmod(0o600);return digest(path.read_bytes())
    sha=save()
    args=dict(config_path=path,expected_config_sha256=sha,approval_ref=config['approval_ref'],predecessor_sha256=config['predecessor_sha256'],prior_charged_nano_usd=config['prior_charged_nano_usd'],ledger_path=config['ledger_path'],expires_at=config['expires_at'])
    arm=dict(public_sha256=public,worker_identity=ss.WORKER,prompt=data['INITIAL_PROMPT.txt'].decode())
    obs=dict(assistant_final='Authored public final',public_diff='Authored public diff',receipt_sha256='a'*64,public_check=dict(command='python -m unittest discover -s tests -v',exit_code=0,output='Authored public tests',receipt_sha256='b'*64))
    request=make_public_request(TASK)(arm,obs,'authored-vendor')
    import managed_chat
    monkeypatch.setattr(managed_chat._PilotProxyBinding,'transport',lambda self,endpoint:rig.factory())
    runtimes=[]
    def admit():
        r=ss.admit_successor(**args);runtimes.append(r);return r
    yield config,args,save,admit,request
    for r in runtimes:
        if not r.closed:r.close()

def test_default_gate_precedes_everything(monkeypatch,rig):
    monkeypatch.setattr(ss,'APPROVED_RETRY_REF',None)
    with pytest.raises(PermissionError,match='not_approved'):
        ss.admit_successor(config_path='/does/not/exist',expected_config_sha256=None,approval_ref='any',predecessor_sha256=None,prior_charged_nano_usd=0,ledger_path='/no',expires_at='invalid')
    assert not rig.created and not rig.calls

def test_admission_no_transport_and_closed_cannot_reopen(configured,rig):
    cfg,args,save,admit,request=configured
    runtime=admit();assert not rig.created and not rig.calls
    assert runtime.summary()['charged_nano_usd']==10000000
    runtime.close()
    with pytest.raises(ValueError,match='closed'):admit()
    assert not rig.created and not rig.calls

@pytest.mark.asyncio
async def test_full_owned_planner_verifier_authored_wire_cumulative_ledger(configured,rig):
    cfg,args,save,admit,request=configured;runtime=admit()
    for role in ('planner','verifier'):
        proposal=None if role=='planner' else ProposedAction(type=InterventionType.NOOP,session_id=request.session.id,goal_id=request.goal.id,rationale='Authored')
        model=runtime.model_factory(role,request,proposal)
        before=len(rig.calls)
        def handle(wire):
            body=json.loads(wire.content)
            assert body['model']==ss.MODEL and body['n']==1 and body['max_completion_tokens']==(1200 if role=='planner' else 900)
            assert 'service_tier' not in body
            data=payload('inspect_acceptance','{}') if len(rig.calls)-before==1 else payload(model.protocol.final_name,json.dumps(final_arguments(role)),'final')
            data['model']=ss.MODEL
            return response(data)
        rig.handler=handle
        result=await model.invoke_async()
        assert result.structured_output is not None and len(model.receipts)==2
        assert all(r.outcome=='succeeded' and r.attempts==1 for r in model.receipts)
    summary=runtime.summary()
    assert summary['prior_charged_nano_usd']==10000000
    assert summary['charged_nano_usd']==10025200
    assert summary['attempts_current_successor']==4 and len(rig.calls)==4

@pytest.mark.parametrize('field,value', [('endpoint','https://other.invalid/v1/chat/completions'),('model','other/model'),('budget_nano_usd',300000001),('max_attempts',13),('input_rate',301),('source_sha256',{}),('public_sha256','0'*64)])
def test_config_variants_refused_no_transport(configured,rig,field,value):
    cfg,args,save,admit,request=configured;cfg[field]=value;args['expected_config_sha256']=save()
    with pytest.raises((ValueError,PermissionError)):admit()
    assert not rig.created and not rig.calls

def test_supplied_prior_and_predecessor_cannot_reset(configured,rig):
    cfg,args,save,admit,request=configured;args['prior_charged_nano_usd']=0
    with pytest.raises(ValueError,match='admission_mismatch'):admit()
    assert not rig.created

def test_request_session_and_task_binding(configured,rig):
    cfg,args,save,admit,request=configured;runtime=admit()
    runtime.model_factory('planner',request,None)
    request.session.vendor_session_id='other'
    with pytest.raises(ValueError,match='outside_frozen'):runtime.model_factory('planner',request,None)
    assert not rig.created and not rig.calls

def test_verifier_cannot_precede_bound_planner(configured,rig):
    cfg,args,save,admit,request=configured;runtime=admit()
    proposal=ProposedAction(type=InterventionType.NOOP,session_id=request.session.id,goal_id=request.goal.id,rationale='Authored')
    with pytest.raises(ValueError,match='planner_binding_required_first'):runtime.model_factory('verifier',request,proposal)
    assert not rig.created

@pytest.mark.asyncio
async def test_uncertain_prior_reservation_blocks_without_transport(configured,rig):
    from accounting import PilotBudgetExhausted
    cfg,args,save,admit,request=configured;runtime=admit()
    for i in range(3):runtime.ledger.reserve('uncertain-'+str(i),runtime.routes[i%2])
    model=runtime.model_factory('planner',request,None)
    with pytest.raises(PilotBudgetExhausted):await model.invoke_async()
    assert runtime.summary()['charged_nano_usd']==10000000+3*82329600
    assert not rig.created and not rig.calls

@pytest.mark.asyncio
async def test_changed_key_never_dispatch(configured,rig):
    cfg,args,save,admit,request=configured;runtime=admit();model=runtime.model_factory('planner',request,None)
    Path(cfg['key']['path']).write_text('changed')
    with pytest.raises(ValueError,match='credential_identity'):await model.invoke_async()
    # Restore key so fixture can use validated summary; close never rereads it.
    assert not rig.created and not rig.calls

def test_proxy_changed_after_admission_refused(configured,rig,monkeypatch):
    cfg,args,save,admit,request=configured;runtime=admit();monkeypatch.setenv('HTTPS_PROXY','http://other.invalid:8080')
    with pytest.raises(ValueError,match='proxy_changed'):runtime.model_factory('planner',request,None)
    assert not rig.created

@pytest.mark.asyncio
async def test_actual_controller_owned_review_authored_continuation(configured,rig,tmp_path):
    """Actual controller/reviewer/models, inert worker/grader. No task score claimed."""
    from controller import run_pair,Budget
    from review import OwnedReview
    cfg,args,save,admit,request=configured;runtime=admit();models=[];saved=[]
    def factory(role,req,proposal):
        model=runtime.model_factory(role,req,proposal);models.append(model);return model
    def handle(wire):
        model=models[-1]
        if not model.observations:
            data=payload('inspect_acceptance','{}','observe')
        else:
            refs=[o.observation_id for o in model.observations]
            final=dict(rationale='Authored protocol only',evidence=['Authored public observation'],evidence_refs=refs)
            if model.protocol.role=='verifier':final.update(approved=True)
            elif len(models)==1:final.update(action_type='CONTINUE_SESSION',message='Authored protocol continuation; no task solution supplied')
            else:final.update(action_type='NOOP')
            data=payload(model.protocol.final_name,json.dumps(final),'final')
        data['model']=ss.MODEL;return response(data)
    rig.handler=handle
    review=OwnedReview(lambda arm,obs,session_id:request,factory,request_recorder=lambda d,r:saved.append((d,r)))
    class Worker:
        def __init__(self):self.turns=[];self.stopped=set();self.cleaned=False
        async def turn(self,arm,*,prompt,session_id,remaining):
            self.turns.append((arm['condition'],prompt))
            return dict(session_id='authored-vendor',receipt={'authored':True},usage=dict(calls=1,input_tokens=1,output_tokens=1),terminal='natural_stop',public_observation={})
        async def stop(self,arm):self.stopped.add(arm['condition'])
        async def cleanup(self):self.cleaned=True
    worker=Worker()
    class Grade:
        async def grade(self,arm):
            assert arm['condition'] in worker.stopped
            return {'status':'graded_with_limits','authored_fixture_only':True}
    arms={c:dict(condition=c,workspace=str(tmp_path/c),prompt='Authored identical worker prompt',public_sha256=cfg['public_sha256'],worker_identity=ss.WORKER) for c in ('baseline','pex')}
    result=await run_pair(arms,worker,review,Grade(),budget=Budget(calls=3,input_tokens=100,output_tokens=100,active_seconds=30))
    assert result['arms']['baseline']['status']=='natural_stop'
    assert result['arms']['pex']['status']=='no_intervention'
    assert [c for c,p in worker.turns]==['baseline','pex','pex']
    assert worker.turns[-1][1]=='Authored protocol continuation; no task solution supplied'
    assert len(models)==3 and len(rig.calls)==6 and len(saved)==2 and worker.cleaned
    assert runtime.summary()['attempts_current_successor']==6
    assert result['pex_lift'] is None and not result['presentation_eligible']


@pytest.mark.asyncio
async def test_mutated_request_and_proposal_never_dispatch(configured,rig):
    cfg,args,save,admit,request=configured;runtime=admit()
    model=runtime.model_factory('planner',request,None)
    request.notes+=' changed'
    with pytest.raises(ValueError,match='request_mutated'):await model.invoke_async()
    # Bind the current public request via a new planner before verifier construction.
    runtime.model_factory('planner',request,None)
    proposal=ProposedAction(type=InterventionType.NOOP,session_id=request.session.id,goal_id=request.goal.id,rationale='Authored')
    verifier=runtime.model_factory('verifier',request,proposal)
    proposal.rationale='changed after binding'
    with pytest.raises(ValueError,match='proposal_mutated'):await verifier.invoke_async()
    assert not rig.created and not rig.calls


def test_key_change_between_validation_and_credential_read_refused(configured,rig,monkeypatch):
    import successor_admission
    cfg,args,save,admit,request=configured;runtime=admit()
    original=successor_admission.private_read;key_reads=[]
    def changing_read(path,*a,**kw):
        raw=original(path,*a,**kw)
        if str(path)==cfg['key']['path']:
            key_reads.append(1)
            if len(key_reads)==2:return b'different-fixture-key'
        return raw
    monkeypatch.setattr(successor_admission,'private_read',changing_read)
    with pytest.raises(ValueError,match='credential_identity'):runtime.credential(runtime.routes[0])
    assert len(key_reads)==2 and not rig.created and not rig.calls
