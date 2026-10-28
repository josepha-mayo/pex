"""Actual pinned CLI + local scripted HTTP + full owned mocked supervisor + fake SDK.

No real provider, VM or task score. Exercises complete staged ordering/cleanup,
not actual paid model behavior or provider cancellation/expiry guarantees.
"""
import http.server
import json
from pathlib import Path
import threading
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
import nebius_worker as cw
from worker_funding import _WorkerLedger,PRICING_SHA
from staged_funding import PhaseFunding
from staged_worker import StagedWorker,StagedGrade
from staged_lifecycle import StagedLifecycle
from staged_controller import run_staged_pair
from staged_review import staged_request_builder
from e2b_transport import BASE_TEMPLATE
from review import OwnedReview
from process_adapter import fixture_model
from managed_chat import Limits,Route
from test_process import Ledger as SupervisorLedger
from test_managed_chat import ENDPOINT,MODEL,response,rig,no_network
from test_tool_protocol import request_fixture
from test_tool_transport import payload
from test_staged_sdk_lifecycle import lifecycle
from test_staged_sdk_binding import bound
from test_staged_admission import candidate

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
@pytest.mark.parametrize('remote_kind',['authored-fake','actual-sdk-mocked'])
async def test_composed_pinned_CLI_owned_review_fake_SDK(monkeypatch,tmp_path,rig,request,remote_kind):
    wire=[];events=[];models=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            number=len(wire)+1;final=number in (8,12,20,24)
            assert self.headers.get('Authorization')=='Bearer SYNTHETIC-COMPOSED-ONLY'
            assert (body.get('tool_choice')=='none')==final
            wire.append(number)
            if final:delta={'role':'assistant','content':'Authored phase finalization'};finish='stop'
            else:
                delta={'role':'assistant','tool_calls':[{'index':0,'id':f'authored-{number}',
                    'type':'function','function':{'name':'pex_remote_run','arguments':'{"command":"AUTHORED-ONLY"}'}}]};finish='tool_calls'
            common={'id':f'authored-{number}','model':cw.MODEL}
            chunks=[{**common,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                {**common,'choices':[{'index':0,'delta':{},'finish_reason':finish}]},
                {**common,'choices':[],'usage':{'prompt_tokens':11,'completion_tokens':1,'total_tokens':12}}]
            raw=(''.join('data: '+json.dumps(x)+'\n\n' for x in chunks)+'data: [DONE]\n\n').encode()
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*a):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    monkeypatch.setattr(cw,'BASE',f'http://127.0.0.1:{server.server_port}/v1')
    class SDK:
        def __init__(self,c):self.c=c;self.dead=False;self.commands=SimpleNamespace(run=self.run)
        async def run(self,command,**kw):
            events.append(('remote',self.c));kw['on_stdout']('Authored output')
            async def wait():return SimpleNamespace(exit_code=0)
            async def kill():return True
            return SimpleNamespace(wait=wait,kill=kill)
        async def get_info(self,**kw):
            now=datetime.now(timezone.utc)
            return SimpleNamespace(started_at=now,end_at=now+timedelta(seconds=330),cpu_count=2,memory_mb=512,template_id=BASE_TEMPLATE)
        async def kill(self,**kw):self.dead=True;events.append(('kill',self.c))
        async def is_running(self,**kw):return not self.dead
    class API:
        AUTHORED_FAKE_ONLY=True
        async def create(self,**kw):
            c=kw['metadata']['pex_arm'];events.append(('create',c));return SDK(c)
    class Compute:
        def reserve(self,*a):events.append(('compute_reserve',a[0]))
        def settle_verified_allocation(self,*a,**kw):events.append(('compute_verified',a[0]))
    async def stage(arm,remote):events.append(('stage',arm['condition']))
    if remote_kind=='actual-sdk-mocked':
        lifecycle,sdk_bound,stage_events=request.getfixturevalue('lifecycle')
    else:
        lifecycle=StagedLifecycle(API(),Compute(),stage,run_id='authored-composed')
    key=tmp_path/'synthetic.key';key.write_text('SYNTHETIC-COMPOSED-ONLY');key.chmod(0o600)
    ledgers={c:_WorkerLedger(tmp_path/'workers.sqlite',arm=c,approved_config_digest='a'*64,
        approval_ref='AUTHORED-NOT-APPROVAL',pricing_provenance_sha256=PRICING_SHA) for c in ('baseline','pex')}
    inner=cw.NebiusCLIWorker(remotes={c:None for c in ledgers},private_root=tmp_path/'cli',
        binary=ROOT/'opencode-qualification-20261027/install/node_modules/@opencode/cli-linux-x64/bin/opencode',
        modules=ROOT/'opencode-qualification-20261027/mock/node_modules',key_path=key,pool=SimpleNamespace(close=lambda:None),
        activate=True,funding={c:PhaseFunding(l) for c,l in ledgers.items()},authored=True)
    worker=StagedWorker(inner,lifecycle)
    def build(arm,observation,session_id):
        r=request_fixture(with_boundaries=True);r.session.vendor_session_id=session_id
        r.scores.features['verification']={'status':'contradicted','acceptance_status':'uncertain'}
        return r
    def factory(role,request,proposal):
        assert 'not spontaneous task completion' in request.event.message_delta
        events.append(('review',role,len(wire)))
        route=Route(ENDPOINT,MODEL,role,Limits(max_usage_tokens=10000))
        ledger=SupervisorLedger(tmp_path/(role+'.sqlite'),budget=100000,input_rate=2,output_rate=3,route=route)
        model=fixture_model(route,request,invocation_id='authored-'+role,ledger=ledger,proposal=proposal)
        models.append(model);return model
    def handler(request):
        m=models[-1];n=len(m.observations)
        if n==0:return response(payload('get_goal','{"boundary_page":0}','goal'))
        if n==1:return response(payload('inspect_acceptance','{}','state'))
        args=dict(rationale='Authored decision',evidence=['Authored public observation'],evidence_refs=[x.observation_id for x in m.observations])
        if m.protocol.role=='planner':args.update(action_type='CONTINUE_SESSION',message='Authored non-answer continuation')
        else:args.update(approved=True)
        return response(payload(m.protocol.final_name,json.dumps(args),'final'))
    rig.handler=handler
    review=OwnedReview(staged_request_builder(build),factory)
    class Grade:
        async def grade(self,arm):
            assert inner.states[arm['condition']]['stopped'] and inner.states[arm['condition']]['mcp_revoked']
            return {'authored':True,'status':'graded_with_limits','score':None}
    arms={c:dict(condition=c,prompt='Same authored public task',public_sha256='a'*64,
        worker_identity='nebius/'+cw.MODEL,workspace=c) for c in ('baseline','pex')}
    try:
        report=await run_staged_pair(arms,worker,review,StagedGrade(Grade(),worker))
        assert all(s['status']=='staged_natural_stop' and s['calls']==12 for s in report['arms'].values())
        assert report['arms']['pex']['supervisor_observed'] and report['cleanup_confirmed']
        assert len(wire)==24 and len(rig.calls)==6
        assert all(e[2]==20 for e in events if e[0]=='review')
        if remote_kind=='actual-sdk-mocked':
            from urllib.parse import urlsplit
            from cumulative_compute import VERIFIED_FULL_LIFETIME
            scope,compute,sdk_wire,pools,behavior=sdk_bound
            baseline_kill=next(i for i,(method,url,body) in enumerate(sdk_wire) if method=='DELETE' and url.endswith('/authored-baseline'))
            pex_create=next(i for i,(method,url,body) in enumerate(sdk_wire) if method=='POST' and urlsplit(url).path=='/v2/sandboxes' and json.loads(body)['metadata']['pex_arm']=='pex')
            assert baseline_kill<pex_create and scope.owned==scope.stopped
            assert compute.total()==100+2*VERIFIED_FULL_LIFETIME
            assert stage_events==[('stage','baseline'),('stage','pex')]
        else:
            assert events.index(('kill','baseline'))<events.index(('create','pex'))
        assert report['real_inference_calls']==0 and report['pex_lift'] is None
        assert all(r.closed for r in lifecycle.remotes.values())
    finally:
        await worker.cleanup();server.shutdown();server.server_close()
        for ledger in ledgers.values():ledger.close()
