"""Exact closed builder -> runner, actual CLI/SDK serializers, MOCK WIRE ONLY.

The CLI fetch seam is test-only and leaves the production guard/URL unchanged.
SDK storage/commands and protected grade results are scripted, not executed.
No real provider, VM, task score, expiry proof, or PEX-lift claim is made.
"""
import asyncio
import base64
from datetime import datetime,timedelta,timezone
from email.parser import BytesParser
from email.policy import default
import http.server
import json
from pathlib import Path
import shlex
import threading
from urllib.parse import urlsplit,parse_qs
import pytest
from pyqwest import Response,Headers
from test_staged_accounting import funded
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
from test_managed_chat import rig,no_network,response
from test_tool_transport import payload
from staged_composition import build_composition,run_composition
from successor_runner import json_default
from staged_supervisor import StagedSupervisor
from staged_worker import StagedWorker
from stockroom_task import FILES,PROTECTED,load_package
from e2b_transport import ROOT
import nebius_worker as cw


@pytest.mark.asyncio
@pytest.mark.parametrize('bound',['composition'],indirect=True)
@pytest.mark.parametrize('interrupt_second_create',[False,True])
async def test_exact_builder_runner_CLI_SDK_public_and_protected_boundaries(funded,bound,monkeypatch,rig,interrupt_second_create):
    accounting,scope=funded;_,_,sdk_wire,pools,behavior=bound
    workers=[];models=[];reviews=[];uploaded=[];files={};composition=None
    task=load_package(Path(accounting.cfg['task']['path']).parent)
    protected={Path(n).name for n in PROTECTED}
    original=scope._execute
    class AuthoredSecondCreateInterruption(BaseException):pass
    def reply(value,status=200):
        return Response(status=status,headers=Headers({'content-type':'application/json'}),content=json.dumps(value).encode())
    async def execute(inner,request):
        class WorkflowMock:
            async def execute(self,req):
                u=urlsplit(req.url);path=u.path
                if u.hostname=='api.e2b.app':
                    if req.method=='POST' and path=='/v2/sandboxes' and json.loads(req.content)['metadata']['pex_arm']=='pex':
                        checkpoint=json.loads((accounting.root/'evidence/arm-baseline.json').read_bytes())
                        assert checkpoint['condition']=='baseline' and checkpoint['partial_pair_evidence_only']
                        assert checkpoint['owned_cleanup']['control_plane_stop_confirmed'] is True
                        assert checkpoint['arm_state']['VM_release_result']['status']=='confirmed'
                        assert len(checkpoint['worker_receipt_rows'])==12
                        assert (accounting.root/'evidence/baseline-candidate-export.json').is_file()
                        assert (accounting.root/'evidence/baseline-grade-report.json').is_file()
                        if interrupt_second_create:raise AuthoredSecondCreateInterruption()
                    sid=path.split('/')[-1]
                    if req.method=='GET' and sid in scope.owned and sid not in scope.kill_attempted:
                        sdk_wire.append((req.method,req.url,req.content));now=datetime.now(timezone.utc)
                        return reply({'templateID':'rki5dems9wqfm4r03t7g','sandboxID':sid,'clientID':'authored',
                            'startedAt':now.isoformat(),'endAt':(now+timedelta(seconds=accounting.cfg['profile']['vm_seconds'])).isoformat(),
                            'envdVersion':'0.5.7','cpuCount':2,'memoryMB':512,'diskSizeMB':1024,'state':'running'})
                    return await inner.execute(req)
                arm=next(c for c,sid in scope.owned_by_arm.items() if sid in (u.hostname or '') or sid==req.headers.get('e2b-sandbox-id'))
                sdk_wire.append((req.method,req.url,req.content))
                if path.endswith('/MakeDir'):return reply({})
                if path=='/files':
                    query=parse_qs(u.query)
                    if req.method=='GET':return Response(status=200,content=files[(arm,query['path'][0])])
                    assert req.method=='POST'
                    raw=req.content
                    if not isinstance(raw,bytes):raw=b''.join([bytes(chunk) async for chunk in raw])
                    assert len(raw)<262144
                    message=BytesParser(policy=default).parsebytes(('Content-Type: '+req.headers['content-type']+'\r\n\r\n').encode()+raw)
                    parts=list(message.iter_parts());assert 1<=len(parts)<=128
                    results=[]
                    for part in parts:
                        name=part.get_filename();assert name
                        if len(parts)==1:assert name==query['path'][0]
                        data=part.get_payload(decode=True);files[(arm,name)]=data;uploaded.append((arm,name,data))
                        if Path(name).name in protected:
                            assert len(parts)==2
                            state=composition.worker.worker.states[arm]
                            assert state['stopped'] and state['mcp_revoked']
                            assert accounting.workers[arm].usage_snapshot()['calls']==12
                            assert not name.startswith(ROOT+'/')
                        else:assert Path(name).name not in protected
                        results.append({'name':Path(name).name,'path':name,'type':'file'})
                    if any(p.get_filename().startswith(ROOT+'/') for p in parts):assert {p.get_filename() for p in parts}=={ROOT+'/'+n for n in FILES}
                    return reply(results)
                if path.endswith('/Start'):
                    from protobuf import Oneof
                    from e2b.envd.process import process_pb as pb
                    raw=req.content
                    if not isinstance(raw,bytes):raw=b''.join([bytes(chunk) async for chunk in raw])
                    assert len(raw)<65536
                    body=json.loads(raw if raw.startswith(b'{') else raw[5:])
                    command=shlex.split(body['process']['args'][-1])[-1]
                    output='AUTHORED command receipt';code=0
                    if command.startswith('python3 -I -c ') and 'pex.public-setup.v1' in command:
                        parts=shlex.split(command)
                        expected=json.loads(parts[-2]);runtime=json.loads(parts[-1])
                        assert runtime==accounting.cfg['profile']['runtime_contract']
                        assert set(expected)==set(FILES)
                        import hashlib
                        assert expected=={n:hashlib.sha256(files[(arm,ROOT+'/'+n)]).hexdigest() for n in FILES}
                        output=json.dumps({'schema':'pex.public-setup.v1','files':expected,'runtime':runtime},sort_keys=True,separators=(',',':'))+'\n'
                    elif 'pex.stockroom-export.v1' in command:
                        output=json.dumps({'schema':'pex.stockroom-export.v1','files':{
                            n:base64.b64encode(files[(arm,ROOT+'/'+n)]).decode() for n in FILES}})
                    elif 'pex.stockroom-upload-verified.v1' in command and json.loads(shlex.split(command)[-1])['mode']=='protected':
                        state=composition.worker.worker.states[arm]
                        assert state['stopped'] and state['mcp_revoked']
                        spec=json.loads(shlex.split(command)[-1])
                        import hashlib
                        assert all(hashlib.sha256(files[(arm,spec['root']+'/'+n)]).hexdigest()==h for n,h in spec['files'].items())
                        output=json.dumps({'schema':'stockroom.grade.v1','checks':17,'passed':0,'failed':17,
                                           'failure_instances':17,'complete':True,'all_pass':False});code=1
                    if 'pex.stockroom-upload-verified.v1' in command:
                        import hashlib
                        spec=json.loads(shlex.split(command)[-1])
                        assert all(hashlib.sha256(files[(arm,spec['root']+'/'+n)]).hexdigest()==h for n,h in spec['files'].items())
                        if spec['mode']=='public':
                            assert not any(n in spec['files'] for n in ('run_grade.py','test_acceptance.py'))
                        receipt='PEX_SNAPSHOT_VERIFIED:'+hashlib.sha256((json.dumps(spec['files'],sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()+'\n'
                        output=receipt+output
                    values=[pb.StartResponse(event=pb.ProcessEvent(event=Oneof('start',pb.ProcessEvent.StartEvent(pid=123)))),
                        pb.StartResponse(event=pb.ProcessEvent(event=Oneof('data',pb.ProcessEvent.DataEvent(output=Oneof('stdout',output.encode()))))),
                        pb.StartResponse(event=pb.ProcessEvent(event=Oneof('end',pb.ProcessEvent.EndEvent(exit_code=code,exited=True))))]
                    def frame(raw,flag=0):return bytes([flag])+len(raw).to_bytes(4,'big')+raw
                    data=b''.join(frame(v.to_json().encode()) for v in values)+frame(b'{}',2)
                    return Response(status=200,headers=Headers({'content-type':'application/connect+json'}),content=data)
                if path.endswith('/SendSignal'):return reply({})
                if path.endswith('/List'):return reply({'processes':[]})
                raise AssertionError('unmocked SDK route')
        return await original(WorkflowMock(),request)
    monkeypatch.setattr(scope,'_execute',execute)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            n=len(workers)+1;final=n in (8,12,20,24)
            assert self.headers.get('Authorization')=='Bearer AUTHORED-NOT-A-CREDENTIAL'
            assert (body.get('tool_choice')=='none')==final
            assert body['max_completion_tokens']==accounting.cfg['profile']['worker_output_per_call']==16384
            assert all(json.dumps(task[n].decode())[1:-1] not in json.dumps(body) for n in PROTECTED)
            workers.append(body)
            if final:delta={'role':'assistant','content':'Authored forced phase finalization'};finish='stop'
            else:
                delta={'role':'assistant','tool_calls':[{'index':0,'id':f'authored-{n}','type':'function',
                    'function':{'name':'pex_remote_run','arguments':'{"command":"AUTHORED-ONLY"}'}}]};finish='tool_calls'
            common={'id':f'authored-{n}','model':cw.MODEL}
            chunks=[{**common,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                {**common,'choices':[{'index':0,'delta':{},'finish_reason':finish}]},
                {**common,'choices':[],'usage':{'prompt_tokens':11,'completion_tokens':1,'total_tokens':12}}]
            raw=(''.join('data: '+json.dumps(x)+'\n\n' for x in chunks)+'data: [DONE]\n\n').encode()
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*unused):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    phase_config=StagedWorker._phase_config
    def local_fetch_only(self,condition,index):
        phase_config(self,condition,index)
        state=self.worker.states[condition];file=state['case']/'plugins/guard/index.ts'
        # Test-only mock below the unchanged endpoint/body/funding guard. Native
        # fetch may reach ONLY exact loopback funding or local SSE fixture URLs.
        fixture={'endpoint':cw.BASE+'/chat/completions','funding':state['funding_channel']['url'],
                 'mock':f'http://127.0.0.1:{server.server_port}/v1/chat/completions'}
        prefix='''const mockConfig=MOCK_CONFIG;
const fixtureFetch=globalThis.fetch;
globalThis.fetch=async(input,init)=>{
 const r=new Request(input,init);
 if(r.url===mockConfig.endpoint){return fixtureFetch(new Request(mockConfig.mock,r));}
 if(r.url===mockConfig.funding){return fixtureFetch(r);}
 throw new Error('AUTHORED_FIXTURE_EXTERNAL_FETCH_FORBIDDEN');
};
'''.replace('MOCK_CONFIG',json.dumps(fixture))
        file.write_text(prefix+file.read_text())
    monkeypatch.setattr(StagedWorker,'_phase_config',local_fetch_only)
    import managed_chat
    monkeypatch.setattr(managed_chat._PilotProxyBinding,'transport',lambda self,endpoint:rig.factory())
    model_factory=StagedSupervisor.model_factory
    def tracked(self,role,request,proposal):
        assert 'not spontaneous task completion' in request.event.message_delta
        assert task['public/TASK.md'].decode() in request.goal.objective
        assert all(json.dumps(task[n].decode())[1:-1] not in request.model_dump_json() for n in PROTECTED)
        reviews.append((role,len(workers)))
        model=model_factory(self,role,request,proposal);models.append(model);return model
    monkeypatch.setattr(StagedSupervisor,'model_factory',tracked)
    def handler(request):
        model=models[-1]
        if not model.observations:data=payload('inspect_acceptance','{}','state')
        else:
            args={'rationale':'Authored continuation','evidence':['Authored public observation'],
                  'evidence_refs':[x.observation_id for x in model.observations]}
            if model.protocol.role=='planner':args.update(action_type='CONTINUE_SESSION',message='Authored non-answer continuation')
            else:args['approved']=True
            data=payload(model.protocol.final_name,json.dumps(args),'final')
        data['model']=composition.supervisor.routes[0].model_id
        return response(data)
    rig.handler=handler
    from review import OwnedReview
    from staged_admission import Admitted,check_authority
    original_review_init=OwnedReview.__init__
    admissions=[]
    def checked_review(self,*args,**kwargs):
        admitted=kwargs.get('admission')
        assert type(admitted) is Admitted and admitted is scope.admitted
        check_authority(admitted);admissions.append(admitted)
        original_review_init(self,*args,**kwargs)
    monkeypatch.setattr(OwnedReview,'__init__',checked_review)
    try:
        composition=build_composition(accounting)
        assert composition.worker.mode=='closed-admitted' and composition.review.mode=='live-pilot'
        assert composition.review.model_factory.__self__ is composition.supervisor
        assert admissions==[scope.admitted]
        assert not sdk_wire and not rig.calls and not workers
        if interrupt_second_create:
            with pytest.raises(AuthoredSecondCreateInterruption):await run_composition(composition)
            checkpoint=json.loads((accounting.root/'evidence/arm-baseline.json').read_bytes())
            assert checkpoint['grade_was_produced'] is True
            assert checkpoint['arm_state']['protected_grade']['summary']['passed']==0  # Scripted, not task evidence.
            assert not checkpoint['comparison_complete'] and checkpoint['pex_lift'] is None
            assert all(row['state']=='settled_raw_wire' for row in checkpoint['worker_receipt_rows'])
            exported=json.loads((accounting.root/'evidence/baseline-candidate-export.json').read_bytes())['payload']
            assert {n:base64.b64decode(b) for n,b in exported['files_base64'].items()}=={n:task['public/'+n] for n in FILES}
            assert not (accounting.root/'report.json').exists()
            assert not (accounting.root/'evidence/arm-pex.json').exists()
            assert len(workers)==12 and not rig.calls
            return
        report=await run_composition(composition)
        assert all(s['status']=='staged_natural_stop' and s['calls']==12 for s in report['arms'].values()),report
        assert reviews==[('planner',20),('verifier',20)] and len(workers)==24 and len(rig.calls)==4
        assert report['comparison_complete'] and report['cleanup_confirmed'] and report['pex_lift'] is None
        assert report['real_inference_calls'] is None  # closed mode never fabricates actual call count
        for c in ('baseline','pex'):
            checkpoint=json.loads((accounting.root/'evidence'/('arm-'+c+'.json')).read_bytes())
            assert checkpoint['condition']==c and checkpoint['config_sha256']==scope.admitted.grant.config_sha256
            assert checkpoint['grade_was_produced'] and not checkpoint['comparison_complete']
            assert checkpoint['owned_cleanup']['control_plane_stop_confirmed'] is True
            assert all(files[(c,ROOT+'/'+n)]==task['public/'+n] for n in FILES)
            grade=report['arms'][c]['protected_grade']
            assert grade['status']=='graded_with_limits' and grade['summary']['passed']==0 and not grade['task_success']
            assert {Path(n).name for arm,n,data in uploaded if arm==c and Path(n).name in protected}==protected
        assert scope.owned==scope.stopped and len(scope.creates)==2
        summary=report['cumulative_accounting']
        assert summary['worker_fresh_nano_usd']['baseline']==summary['worker_fresh_nano_usd']['pex']>0
        assert summary['supervisor_wire_attempts']==4 and summary['supervisor_fresh_overhead_nano_usd']>0
        assert json.loads((accounting.root/'report.json').read_bytes())==json.loads(json.dumps(report,default=json_default))
        assert len(list(accounting.root.glob('public-observation-*.json')))==1
    finally:
        if composition is not None:
            try:await composition.worker.cleanup()
            except Exception:
                if not interrupt_second_create:raise
            composition.supervisor.close()
        server.shutdown();server.server_close()
