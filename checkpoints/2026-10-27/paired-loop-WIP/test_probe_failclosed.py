"""Actual CLI, authored loopback only. Disabled plugin must never receive key."""
import asyncio
import http.server
import inspect
import json
from pathlib import Path
import threading
import pytest
import probe_free as pf

ROOT=Path(__file__).resolve().parents[1]
BINARY=ROOT/'opencode-qualification-20261027/install/node_modules/@opencode/cli-linux-x64/bin/opencode'
MODULES=ROOT/'opencode-qualification-20261027/mock/node_modules'

@pytest.mark.parametrize('disabled',[False,True])
def test_actual_cli_secret_requires_loaded_guard(tmp_path,disabled):
    calls=[];sentinel='SYNTHETIC-AUTHORDED-PROBE-ONLY'
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'dummy':self.headers.get('Authorization')=='Bearer PEX-INERT-NONSECRET-NOT-A-KEY',
                          'sentinel':self.headers.get('Authorization')=='Bearer '+sentinel,
                          'model':body.get('model'),'max_tokens':body.get('max_tokens'),'tools':len(body.get('tools') or [])})
            chunks=[{'choices':[{'index':0,'delta':{'role':'assistant','content':'READY'},'finish_reason':None}]},
                    {'choices':[{'index':0,'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':5,'completion_tokens':1,'total_tokens':6,'cost':0,'opencode':{'billing_source':'free'}}}]
            raw=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*a):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    key=tmp_path/'synthetic.key';key.write_text(sentinel);key.chmod(0o600)
    function=pf.probe
    if disabled:
        # Reproduce the actual configuration fault, only against inert localhost.
        source=inspect.getsource(pf.probe).replace("'plugins':['./plugins/guard'],", "'plugins':['./plugins/guard'],")
        source=source.replace("'policies':[", "'policies':[{'action':'integration.use','resource':'*','effect':'deny'},")
        namespace=dict(pf.__dict__);exec(source,namespace);function=namespace['probe']
    try:
        result=asyncio.run(function(binary=BINARY,modules=MODULES,key_path=key,output=tmp_path/'run',base=f'http://127.0.0.1:{server.server_port}/v1'))
        assert calls
        if disabled:
            assert all(c['dummy'] and not c['sentinel'] for c in calls)
            assert result['wire']['attempts']==0
        else:
            assert calls==[{'dummy':False,'sentinel':True,'model':pf.MODEL,'max_tokens':32,'tools':0}]
            assert result['wire']['attempts']==1 and result['status']=='natural_stop'
    finally:
        server.shutdown();server.server_close()
