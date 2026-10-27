"""Actual CLI + private MCP + inert remote object; no provider/VM calls."""
import asyncio
import pytest
from worker_funding import _WorkerLedger,PRICING_SHA
import http.server
import json
from pathlib import Path
import threading
import nebius_worker as cw
from public_request import build_public_request

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('joined_ledger',[False,True])
def test_actual_cli_nebius_byok_authored(monkeypatch,tmp_path,joined_ledger):
    calls=[];remote_calls=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            b=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'model':b['model'],'max_tokens':b['max_tokens'],'tools':[t['function']['name'] for t in b.get('tools',[])],
                          'sentinel':self.headers.get('Authorization')=='Bearer SYNTHETIC-CLI-WORKER-ONLY'})
            if len(calls)==1:
                delta={'role':'assistant','tool_calls':[{'index':0,'id':'authored-remote','type':'function','function':{'name':'pex_remote_run','arguments':'{"command":"AUTHORED-REMOTE-ONLY"}'}}]};finish='tool_calls'
            else:delta={'role':'assistant','content':'Authored worker completed'};finish='stop'
            common={'id':'authored-'+str(len(calls)),'model':cw.MODEL}
            chunks=[{**common,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**common,'choices':[{'index':0,'delta':{},'finish_reason':finish}]},{**common,'choices':[],'usage':{'prompt_tokens':11,'completion_tokens':1,'total_tokens':12}}]
            raw=(''.join('data: '+json.dumps(x)+'\n\n' for x in chunks)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*a):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    monkeypatch.setattr(cw,'BASE',f'http://127.0.0.1:{server.server_port}/v1')
    class Remote:
        def run(self,command):remote_calls.append(command);return {'stdout':'Authored only','stderr':'','exit_code':0}
        def read(self,*args):return 'authored'
        def write(self,*args):return {'written':True}
        def list(self,*args):return []
    class Pool:
        closed=False
        def close(self):self.closed=True
    pool=Pool();key=tmp_path/'synthetic.key';key.write_text('SYNTHETIC-CLI-WORKER-ONLY');key.chmod(0o600)
    funding_calls=[]
    class Funding:
        def reserve(self,*args):funding_calls.append(('reserve',args));return {'reserved':319488000}
        def settle_raw(self,*args):funding_calls.append(('settle',args));return {'settled':4500}
    funding={c:(_WorkerLedger(tmp_path/'funding.sqlite',arm=c,approved_config_digest='a'*64,approval_ref='AUTHORED-NOT-APPROVAL',pricing_provenance_sha256=PRICING_SHA) if joined_ledger else Funding()) for c in ('baseline','pex')}
    created=[]
    def make(c):created.append(c);return Remote()
    worker=cw.NebiusCLIWorker(remotes={c:(lambda c=c:make(c)) for c in ('baseline','pex')},private_root=tmp_path/'cli',
                        binary=ROOT/'opencode-qualification-20261027/install/node_modules/@opencode/cli-linux-x64/bin/opencode',
                        modules=ROOT/'opencode-qualification-20261027/mock/node_modules',key_path=key,pool=pool,activate=True,funding=funding,authored=True)
    arm={'condition':'pex','prompt':'Authored protocol task','worker_identity':'nebius/'+cw.MODEL,'public_sha256':'a'*64}
    async def run():
        try:
            result=await worker.turn(arm,prompt=arm['prompt'],session_id=None,remaining={'active_seconds':20})
            assert result['terminal']=='natural_stop' and result['usage']=={'calls':2,'input_tokens':22,'output_tokens':2}
            assert result['worker_active_seconds']>0
            request=build_public_request(arm,result['public_observation'],result['session_id'])
            assert request.session.cwd is None and request.scores.features['verification']['acceptance_status']=='uncertain'
            assert request.session.vendor_session_id==result['session_id']
        finally:await worker.cleanup()
    try:
        asyncio.run(run())
        assert created==['pex'] and pool.closed
        if joined_ledger:
            summary=funding['pex'].summary()
            assert summary['attempts']=={'baseline':0,'pex':2}
            assert summary['charged_nano_usd']=={'baseline':0,'pex':9000}
        else:
            assert [c[0] for c in funding_calls]==['reserve','settle','reserve','settle']
            assert all(c[1][2]==200 for c in funding_calls if c[0]=='settle')
        assert (tmp_path/'cli/pex/turn-0.stderr').stat().st_mode&0o077==0
        assert (tmp_path/'cli/pex/turn-0.jsonl').stat().st_mode&0o077==0
        assert len(calls)==2 and all(c['sentinel'] and c['model']==cw.MODEL and c['max_tokens']==4096 and set(c['tools'])=={'pex_remote_run','pex_remote_read','pex_remote_write','pex_remote_list'} for c in calls)
        assert remote_calls==['AUTHORED-REMOTE-ONLY','python -m unittest discover -s tests -p test_smoke.py','git diff -- .; git status --short']
        config=json.loads((tmp_path/'cli/pex/case/opencode.json').read_text())
        assert config['providers']['nebius']['settings']['apiKey']=='PEX-INERT-NONSECRET-NOT-A-KEY'
    finally:
        server.shutdown();server.server_close()
        if joined_ledger:
            for ledger in funding.values():ledger.close()
