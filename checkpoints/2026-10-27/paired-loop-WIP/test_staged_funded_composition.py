"""Closed full composition: actual CLI/SDK/protocol + synthetic local transports.

No paid inference, actual VM, provider lifetime proof, authored live correction,
or task-success/PEX-lift claim. Tests frozen stage ordering and durable accounting.
"""
import asyncio
from datetime import datetime,timedelta,timezone
import http.server
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit
import pytest
from pyqwest import Response,Headers
from test_staged_accounting import funded
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
from test_managed_chat import rig,no_network,response
from test_tool_transport import payload
import nebius_worker as cw
from staged_funding import PhaseFunding
from staged_worker import StagedWorker,StagedGrade
from staged_sdk_lifecycle import AdmittedSDKLifecycle
from staged_supervisor import StagedSupervisor
from staged_controller import run_staged_pair
from staged_review import staged_request_builder
from review import OwnedReview
from stockroom_request import make_public_request
from stockroom_task import load_package
from cumulative_compute import VERIFIED_FULL_LIFETIME

ROOT=Path(__file__).resolve().parents[1]
TASK=ROOT/'pex-hard-task-candidate-20261027-1421'

@pytest.mark.asyncio
@pytest.mark.parametrize('bound',['stockroom'],indirect=True)
async def test_closed_funded_CLI_SDK_and_full_supervisor(funded,bound,monkeypatch,tmp_path,rig):
    accounting,scope=funded;_,_,sdk_wire,pools,behavior=bound
    worker_wire=[];models=[];reviews=[];stages=[]
    original=scope._execute
    async def execute(inner,request):
        class InfoMock:
            async def execute(self,req):
                path=urlsplit(req.url).path;sid=path.split('/')[-1]
                if req.method=='GET' and path.startswith('/sandboxes/') and sid not in scope.kill_attempted:
                    sdk_wire.append((req.method,req.url,req.content));now=datetime.now(timezone.utc)
                    value={'templateID':'rki5dems9wqfm4r03t7g','sandboxID':sid,'clientID':'authored',
                        'startedAt':now.isoformat(),'endAt':(now+timedelta(seconds=330)).isoformat(),
                        'envdVersion':'0.5.7','cpuCount':2,'memoryMB':512,'diskSizeMB':1024,'state':'running'}
                    return Response(status=200,headers=Headers({'content-type':'application/json'}),content=json.dumps(value).encode())
                return await inner.execute(req)
        return await original(InfoMock(),request)
    monkeypatch.setattr(scope,'_execute',execute)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            n=len(worker_wire)+1;final=n in (8,12,20,24)
            assert self.headers.get('Authorization')=='Bearer SYNTHETIC-COMPOSED-ONLY'
            assert (body.get('tool_choice')=='none')==final
            worker_wire.append(n)
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
    monkeypatch.setattr(cw,'BASE',f'http://127.0.0.1:{server.server_port}/v1')
    async def stage(arm,remote):
        assert (await asyncio.to_thread(remote.run,'printf authored',.5))['exit_code']==0
        stages.append(arm['condition'])
    life=AdmittedSDKLifecycle(scope,stage)
    key=tmp_path/'synthetic-worker.key';key.write_text('SYNTHETIC-COMPOSED-ONLY');key.chmod(0o600)
    inner=cw.NebiusCLIWorker(remotes={'baseline':None,'pex':None},private_root=tmp_path/'cli',
        binary=ROOT/'opencode-qualification-20261027/install/node_modules/@opencode/cli-linux-x64/bin/opencode',
        modules=ROOT/'opencode-qualification-20261027/mock/node_modules',key_path=key,pool=SimpleNamespace(close=lambda:None),
        activate=True,funding={c:PhaseFunding(l) for c,l in accounting.workers.items()},authored=True,
        public_check_command='python -m unittest discover -s tests -v',task_profile='stockroom-v1')
    worker=StagedWorker(inner,life)
    import managed_chat
    monkeypatch.setattr(managed_chat._PilotProxyBinding,'transport',lambda self,endpoint:rig.factory())
    supervisor=StagedSupervisor(accounting)
    def model_factory(role,request,proposal):
        assert 'not spontaneous task completion' in request.event.message_delta
        reviews.append((role,len(worker_wire)))
        model=supervisor.model_factory(role,request,proposal);models.append(model);return model
    def handler(request):
        model=models[-1]
        if not model.observations:data=payload('inspect_acceptance','{}','state')
        else:
            args={'rationale':'Authored test continuation','evidence':['Authored public observation'],
                  'evidence_refs':[x.observation_id for x in model.observations]}
            if model.protocol.role=='planner':args.update(action_type='CONTINUE_SESSION',message='Authored non-answer continuation')
            else:args['approved']=True
            data=payload(model.protocol.final_name,json.dumps(args),'final')
        data['model']=supervisor.routes[0].model_id
        return response(data)
    rig.handler=handler
    review=OwnedReview(staged_request_builder(make_public_request(TASK)),model_factory)
    class Grade:
        async def grade(self,arm):
            state=inner.states[arm['condition']]
            assert state['stopped'] and state['mcp_revoked']
            return {'status':'graded_with_limits','score':None,'qualification':'mock_no_task_execution'}
    task=load_package(TASK)
    arms={c:{'condition':c,'prompt':task['INITIAL_PROMPT.txt'].decode(),'public_sha256':supervisor.config['public_sha256'],
             'worker_identity':'nebius/'+cw.MODEL,'workspace':c} for c in ('baseline','pex')}
    try:
        report=await run_staged_pair(arms,worker,review,StagedGrade(Grade(),worker))
        assert all(s['status']=='staged_natural_stop' and s['calls']==12 for s in report['arms'].values())
        assert report['arms']['pex']['supervisor_observed'] and report['cleanup_confirmed']
        assert reviews==[('planner',20),('verifier',20)] and len(worker_wire)==24 and len(rig.calls)==4
        assert stages==['baseline','pex'] and scope.owned==scope.stopped
        summary=accounting.summary()
        assert summary['worker_fresh_nano_usd']['baseline']==summary['worker_fresh_nano_usd']['pex']>0
        assert summary['supervisor_wire_attempts']==4 and summary['supervisor_fresh_overhead_nano_usd']>0
        assert summary['provider_cumulative_nano_usd']==summary['prior_provider_nano_usd']+sum(summary['worker_fresh_nano_usd'].values())+summary['supervisor_fresh_overhead_nano_usd']
        assert summary['compute_cumulative_bound_nano_usd']==100+2*VERIFIED_FULL_LIFETIME
        assert report['real_inference_calls']==0 and report['pex_lift'] is None
    finally:
        await worker.cleanup();supervisor.close();server.shutdown();server.server_close()
