"""Real owned supervisor protocol, exact routes, synthetic credentials/mock HTTP only."""
import json
import base64
from datetime import datetime
from pathlib import Path
import pytest
from test_staged_accounting import funded
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
from test_managed_chat import rig,no_network,response
from test_tool_transport import payload
from test_tool_protocol import ProposedAction,InterventionType
from staged_supervisor import *
from staged_admission import sha
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
    db=runtime.ledger.db
    rows=db.execute('SELECT invocation_id,kind,role,route,body_sha256,artifact_path,artifact_sha256 FROM staged_supervisor_wire').fetchall()
    assert len(rows)==8
    for call,kind,role,route,body_sha,path,artifact_sha in rows:
        p=Path(path);raw=p.read_bytes();artifact=json.loads(raw)
        assert p.parent==runtime.accounting.root/'supervisor-wire' and p.stat().st_mode&0o077==0
        assert p.stat().st_nlink==1 and sha(raw)==artifact_sha
        assert artifact['schema']=='pex.staged.private-supervisor-wire.v1'
        assert artifact['config_sha256']==runtime.accounting.binding.admitted.grant.config_sha256
        assert artifact['run_id']==runtime.accounting.binding.admitted.grant.run_id
        assert artifact['kind']==kind and artifact['invocation_id']==call
        assert artifact['role']==role and artifact['route_fingerprint']==route
        body=base64.b64decode(artifact['raw_body_base64'],validate=True)
        assert sha(body)==body_sha==artifact['body_sha256']
        assert artifact['request_headers_captured'] is False and artifact['complete_bounded_body'] is True
        assert artifact['content_type']=='application/json'
        assert datetime.fromisoformat(artifact['captured_at_utc']).utcoffset().total_seconds()==0
        assert db.execute('SELECT state FROM calls WHERE id=?',(call,)).fetchone()==('settled_raw_wire',)
        receipt=json.loads(db.execute('SELECT receipt FROM calls WHERE id=?',(call,)).fetchone()[0])
        assert receipt['outcome']=='succeeded' and receipt['route_fingerprint']==route
        if kind=='response':assert artifact['HTTP_status']==200 and json.loads(body)['model']==MODEL
        else:
            assert artifact['HTTP_status'] is None and b'authorization' not in body.lower()
            assert body in [item.content for item in rig.calls]


@pytest.mark.asyncio
@pytest.mark.parametrize('bound',['stockroom'],indirect=True)
@pytest.mark.parametrize('case',['valid','invalid_usage','malformed_json','secret','escaped_secret','nested_secret','capture_failure','request_capture_failure','partial_body','oversized_body','status_refused'])
async def test_private_supervisor_wire_precedes_parser_and_keeps_failure_reservation(supervisor,rig,monkeypatch,case):
    import managed_chat as mc
    import httpx
    from managed_tool_chat import ToolInvocation
    from test_tool_protocol import initial
    runtime,request=supervisor
    model=runtime.model_factory('planner',request,None);contract=model.protocol
    invocation=ToolInvocation('authored-wire-once',contract,(initial(contract),),
        json.dumps([json.loads(x.advertised_spec_json) for x in contract.definitions]),'null')
    credential=runtime.credential(model._candidate.route)
    value=payload('inspect_acceptance','{}');value['model']=MODEL
    if case=='invalid_usage':value['usage']['total_tokens']=999
    if case in ('secret','escaped_secret','nested_secret'):
        secret=credential._value
        value['private_echo']=secret if case=='secret' else ''.join('\\u%04x'%ord(c) for c in secret)
        if case=='nested_secret':value['private_echo']=json.dumps({'echo':value['private_echo']})
    body=json.dumps(value,separators=(',',':')).encode()
    if case=='malformed_json':body=b'{"model":'
    original=mc._strict_json;checked=[]
    def strict(raw):
        if raw==body:
            row=runtime.ledger.db.execute("SELECT artifact_path FROM staged_supervisor_wire WHERE kind='response'").fetchone()
            assert row is not None and base64.b64decode(json.loads(Path(row[0]).read_bytes())['raw_body_base64'])==body
            checked.append(True)
        return original(raw)
    monkeypatch.setattr(mc,'_strict_json',strict)
    if case in ('capture_failure','request_capture_failure'):
        original_sink=runtime.archive_wire
        def failed(kind,*args):
            if kind==('request' if case=='request_capture_failure' else 'response'):
                raise OSError('synthetic private write failure')
            return original_sink(kind,*args)
        monkeypatch.setattr(runtime,'archive_wire',failed)
    if case=='partial_body':rig.handler=lambda wire:response(chunks=[body[:20],httpx.ReadError('synthetic')])
    elif case=='oversized_body':rig.handler=lambda wire:response(raw=b'x'*(model._candidate.route.limits.max_response_bytes+1))
    elif case=='status_refused':rig.handler=lambda wire:response(raw=body,status=403)
    else:rig.handler=lambda wire:response(raw=body)
    result=await model._candidate._execute_owned(invocation,credential)
    rows=runtime.ledger.db.execute('SELECT kind,artifact_path FROM staged_supervisor_wire').fetchall()
    assert len(rig.calls)==(0 if case=='request_capture_failure' else 1)
    assert len(rows)==(2 if case in ('valid','invalid_usage','malformed_json') else 0 if case=='request_capture_failure' else 1)
    assert bool(checked)==(case in ('valid','invalid_usage','malformed_json'))
    charged,state=runtime.ledger.db.execute('SELECT charged,state FROM calls').fetchone()
    if case=='valid':assert result.receipt.outcome=='succeeded' and state=='settled_raw_wire'
    else:
        assert result.receipt.outcome==('refused' if case=='request_capture_failure' else 'uncertain')
        assert state=='uncertain' and charged==runtime.accounting.supervisor.reservation
    if case in ('secret','escaped_secret','nested_secret'):
        assert result.receipt.reason=='credential_in_wire_archive_refused'
    for _,path in rows:
        assert credential._value.encode() not in Path(path).read_bytes()
    # The inherited PUBLIC entry still cannot dispatch or publish evidence.
    before=len(rows);denied=await model._candidate.invoke(invocation)
    assert denied.receipt.reason=='live_not_authorized' and len(rig.calls)==(0 if case=='request_capture_failure' else 1)
    assert runtime.ledger.db.execute('SELECT COUNT(*) FROM staged_supervisor_wire').fetchone()[0]==before


@pytest.mark.parametrize('bound',['stockroom'],indirect=True)
def test_supervisor_archive_cannot_orphan_replace_or_cross_bind_call(supervisor):
    runtime,_=supervisor;bundle=runtime.accounting;route=bundle.routes[0]
    with pytest.raises(AdmissionRefused):bundle.archive_supervisor_wire('request','not-reserved',route,b'{}',None)
    bundle.supervisor_ledger.reserve('authored-capture',route)
    with pytest.raises(AdmissionRefused):bundle.archive_supervisor_wire('response','authored-capture',route,b'{}',200)
    with pytest.raises(AdmissionRefused):bundle.archive_supervisor_wire('request','authored-capture',bundle.routes[1],b'{}',None)
    first=bundle.archive_supervisor_wire('request','authored-capture',route,b'{}',None)
    original=Path(first['path']).read_bytes()
    with pytest.raises(FileExistsError):bundle.archive_supervisor_wire('request','authored-capture',route,b'{"changed":true}',None)
    assert Path(first['path']).read_bytes()==original
    assert bundle.supervisor.db.execute('SELECT COUNT(*) FROM staged_supervisor_wire').fetchone()[0]==1


def test_private_wire_secret_screen_is_conservative_without_semantic_parsing():
    from managed_chat import _screen_private_wire,Refusal
    secret='authored-secret-only'
    # Malformed JSON may be diagnosed without running the strict JSON parser.
    _screen_private_wire(b'{"malformed":',secret)
    with pytest.raises(Refusal,match='utf8'): _screen_private_wire(b'\xff',secret)
    value=''.join('\\u%04x'%ord(c) for c in secret)
    for _ in range(4):
        with pytest.raises(Refusal,match='credential_in_wire_archive_refused'):
            _screen_private_wire(value.encode(),secret)
        value=json.dumps(value)
    value='\\u0061'
    for _ in range(12):value=json.dumps(value)
    with pytest.raises(Refusal,match='escape_depth'): _screen_private_wire(value.encode(),secret)

@pytest.mark.parametrize('bound',['stockroom'],indirect=True)
def test_mutated_request_and_wrong_session_refused(supervisor,rig):
    runtime,request=supervisor
    model=runtime.model_factory('planner',request,None)
    request.session.vendor_session_id='wrong'
    with pytest.raises(ValueError):runtime.model_factory('planner',request,None)
    assert not rig.calls
