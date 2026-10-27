"""One actual OpenCode2 CLI turn against an authored loopback fixture only.

No credential reader, live flag, private tasks, evaluator or supervisor fallback.
This is startup/wire compatibility, NEVER inference or a paired score.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import http.server
import json
import threading
import time
from dataclasses import asdict
from pathlib import Path
from opencode_cli import run_turn

PIN = "ca9b3ee262e33bb4e7aa0e1230dc61086a474c8c8016b980081d0719712fd2e7"
MODEL = "deepseek-v4.1-flash-free"
SYNTHETIC = "SYNTHETIC-NONSECRET-INVALID"
GUARD = r'''
import { Plugin } from '@opencode/plugin';
export default Plugin.define({id:'paired-readiness-mock-only', async setup(ctx) {
 const base=BASE, model=MODEL;
 await ctx.session.hook('context', e=>{e.options.maxTokens=256;e.tools={};});
 await ctx.session.hook('title', e=>{e.result='Authored startup fixture';});
 await ctx.session.hook('model.request', e=>{
  const ok=e.model.providerID==='opencode'&&e.model.id===model&&e.kind==='primary';
  e.baseURL=base;if(!ok)throw new Error('MOCK_ONLY_MODEL_DENIED');
 });
 let requests=0;
 await ctx.session.hook('http.request',async e=>{
  const u=new URL(e.request.url);const b=await e.request.clone().json();
  const ok=u.origin===new URL(base).origin&&u.pathname==='/v1/chat/completions'&&e.kind==='primary'&&b.model===model&&b.max_tokens===256&&!b.tools?.length&&++requests===1;
  if(!ok){e.request=new Request(base+'/blocked',{method:'POST',body:'blocked'});throw new Error('MOCK_ONLY_HTTP_DENIED');}
 });
 await ctx.session.hook('experimental.ws.handshake',e=>{e.url=base.replace('http:','ws:')+'/blocked';throw new Error('MOCK_ONLY_WS_DENIED');});
 await ctx.session.hook('retry',e=>{e.decision={retry:false};});
}});
'''

async def preflight(binary: Path, modules: Path, output: Path, continuation: bool = False):
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=PIN:
        raise ValueError("OpenCode2.1.4 binary identity mismatch")
    plugin=json.loads((modules/'@opencode/plugin/package.json').read_text())
    if plugin.get('version')!='2.1.4':raise ValueError('plugin version mismatch')
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    case=output/'case';case.mkdir();(case/'plugins/guard').mkdir(parents=True)
    (output/'node_modules').symlink_to(modules,target_is_directory=True)
    requests=[]
    class Mock(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=1000000:self.send_error(413);return
            data=json.loads(self.rfile.read(size))
            requests.append({'path':self.path,'model':data.get('model'),'max_tokens':data.get('max_tokens'),
                             'stream':data.get('stream'),'tools':len(data.get('tools',[])),
                             'synthetic_auth':self.headers.get('Authorization')=='Bearer '+SYNTHETIC})
            if len(requests)>(2 if continuation else 1) or requests[-1]!={'path':'/v1/chat/completions','model':MODEL,'max_tokens':256,'stream':True,'tools':0,'synthetic_auth':True}:
                self.send_error(400);return
            chunks=[{'choices':[{'index':0,'delta':{'role':'assistant','content':'qualification'},'finish_reason':None}]},
                    {'choices':[{'index':0,'delta':{},'finish_reason':'stop'}],
                     'usage':{'prompt_tokens':11,'completion_tokens':1,'total_tokens':12}}]
            wire=b''
            for chunk in chunks:
                chunk.update(id='authored-only',object='chat.completion.chunk',created=1,model=MODEL)
                wire+=b'data: '+json.dumps(chunk).encode()+b'\n\n'
            wire+=b'data: [DONE]\n\n'
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(wire)));self.end_headers();self.wfile.write(wire)
        def log_message(self,*_):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Mock)
    base=f'http://127.0.0.1:{server.server_port}/v1'
    (case/'plugins/guard/index.ts').write_text(GUARD.replace('BASE',json.dumps(base)).replace('MODEL',json.dumps(MODEL),1))
    config={'model':'opencode/'+MODEL,'default_agent':'qualification','plugins':['./plugins/guard'],
            'policies':[{'action':'provider.use','resource':'*','effect':'deny'},{'action':'provider.use','resource':'opencode','effect':'allow'},{'action':'tool.use','resource':'*','effect':'deny'}],
            'providers':{'opencode':{'package':'@opencode/ai/providers/openai-compatible','settings':{'baseURL':base,'apiKey':SYNTHETIC},
                'models':{MODEL:{'modelID':MODEL,'body':{'max_tokens':256},'limit':{'context':8192,'output':256},'capabilities':{'tools':False,'input':['text'],'output':['text']}}}}},
            'agents':{'qualification':{'mode':'primary','model':'opencode/'+MODEL,'steps':1,'permissions':[{'action':'*','resource':'*','effect':'deny'}]}}}
    (case/'opencode.json').write_text(json.dumps(config,indent=2)+'\n')
    environment={'PATH':'/usr/bin:/bin','HOME':str(output/'home'),'XDG_CONFIG_HOME':str(output/'config'),
                 'XDG_DATA_HOME':str(output/'data'),'XDG_CACHE_HOME':str(output/'cache'),'XDG_STATE_HOME':str(output/'state'),'LANG':'C.UTF-8','TERM':'dumb'}
    threading.Thread(target=server.serve_forever,daemon=True).start()
    started=time.monotonic();receipt={'kind':'authored_actual_cli_preflight','real_inference':False,'paired_score':None,'binary_sha256':PIN}
    try:
        turn=await run_turn(executable=binary,workspace=case,model='opencode/'+MODEL,
                            prompt='Return the word qualification. This is an authored local wire fixture, not a benchmark task.',
                            environment=environment,stdout_path=output/'stdout.jsonl',stderr_path=output/'stderr.txt',
                            deadline=started+45,standalone=True,agent='qualification',
                            terminal_database=output/'data/opencode/opencode.db')
        receipt.update(status='passed',turn=asdict(turn))
        if continuation:
            second=await run_turn(executable=binary,workspace=case,model='opencode/'+MODEL,
                prompt='Return qualification again. This is an authored same-session transport check only.',
                environment=environment,stdout_path=output/'continuation.jsonl',stderr_path=output/'continuation.stderr.txt',
                deadline=started+45,standalone=True,agent='qualification',session_id=turn.session_id,
                terminal_database=output/'data/opencode/opencode.db')
            receipt.update(continuation=asdict(second),same_session=second.session_id==turn.session_id)
    except Exception as error:
        receipt.update(status='blocked',error_type=type(error).__name__,error=str(error))
    finally:
        server.shutdown();server.server_close()
        receipt.update(seconds=round(time.monotonic()-started,3),requests=requests)
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
    return 0 if receipt['status']=='passed' and len(requests)==(2 if continuation else 1) else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);p.add_argument('--plugin-modules',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--continuation',action='store_true')
    a=p.parse_args();raise SystemExit(asyncio.run(preflight(a.binary.resolve(),a.plugin_modules.resolve(),a.output.absolute(),a.continuation)))
