"""One root-authorized actual-CLI no-tools free-model readiness call, not benchmark."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
from dataclasses import asdict
from opencode_cli import run_turn

MODEL='deepseek-v4.1-flash-free'
BASE='https://opencode.ai/inference/openai/v1'
PIN='ca9b3ee262e33bb4e7aa0e1230dc61086a474c8c8016b980081d0719712fd2e7'
GUARD=r'''
import { Plugin } from '@opencode/plugin';
import { writeFileSync, readFileSync } from 'node:fs';
const cfg=CONFIG;
export default Plugin.define({id:'pex-free-readiness',async setup(ctx){
 let calls=0;
 await ctx.tool.transform(e=>{for(const t of e.list())e.remove(t.id);});
 await ctx.permission.hook('evaluate',e=>{e.effect='deny';});
 await ctx.tool.hook('execute.before',()=>{throw new Error('ALL_TOOLS_DENIED');});
 await ctx.session.hook('context',e=>{e.options.maxTokens=32;e.tools={};});
 await ctx.session.hook('title',e=>{e.result='PEX free readiness';});
 await ctx.session.hook('model.request',e=>{
  const ok=e.model.providerID==='opencode'&&e.model.id===cfg.model&&e.kind==='primary';
  e.baseURL=ok?cfg.base:'http://127.0.0.1:1/blocked';if(!ok)throw new Error('MODEL_DENIED');
 });
 await ctx.session.hook('http.request',async e=>{
  const deny=()=>{e.request=new Request('http://127.0.0.1:1/blocked',{method:'POST'});throw new Error('REQUEST_DENIED');};
  let b;try{b=await e.request.clone().json();}catch{return deny();}
  if(e.kind!=='primary'||e.request.url!==cfg.base+'/chat/completions'||b.model!==cfg.model||b.max_tokens!==32||b.tools?.length||++calls!==1)return deny();
  writeFileSync(cfg.receipt,JSON.stringify({attempts:calls,model:cfg.model,tools:0,max_tokens:32}),{mode:0o600});
  const key=readFileSync(cfg.keyPath,'utf8').trim();if(!key||/[\r\n]/.test(key))return deny();
  const headers=new Headers(e.request.headers);headers.set('Authorization','Bearer '+key);e.request=new Request(e.request,{headers});
 });
 await ctx.session.hook('http.response',async e=>{
  let usage=null,finish_reason=null;const text=await e.response.clone().text();
  if(text.length<=65536){for(const line of text.split('\n')){if(line.startsWith('data: ')){try{const v=JSON.parse(line.slice(6));if(v.usage)usage=v.usage;if(v.choices?.[0]?.finish_reason)finish_reason=v.choices[0].finish_reason;}catch{}}}}
  writeFileSync(cfg.receipt,JSON.stringify({attempts:calls,model:cfg.model,tools:0,max_tokens:32,status:e.response.status,usage,finish_reason}),{mode:0o600});
 });
 await ctx.session.hook('retry',e=>{e.decision={retry:false};});
 await ctx.session.hook('experimental.ws.handshake',e=>{e.url='ws://127.0.0.1:1/blocked';throw new Error('WS_DENIED');});
}});
'''

async def probe(*,binary,modules,key_path,output,base=BASE,live=False):
    if base==BASE and live is not True: raise PermissionError('live_probe_default_closed')
    if base!=BASE and not base.startswith('http://127.0.0.1:'):raise ValueError('unapproved_probe_endpoint')
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=PIN:raise ValueError('CLI_identity_changed')
    if key_path.is_symlink() or key_path.stat().st_mode&0o077:raise ValueError('private_key_required')
    key=key_path.read_text().strip()
    if not key:raise ValueError('empty_key')
    output.mkdir(mode=0o700,parents=False,exist_ok=False)
    case=output/'case';(case/'plugins/guard').mkdir(parents=True)
    (output/'node_modules').symlink_to(modules,target_is_directory=True)
    receipt=output/'wire-usage.json'
    (case/'plugins/guard/index.ts').write_text(GUARD.replace('CONFIG',json.dumps({'base':base,'model':MODEL,'receipt':str(receipt),'keyPath':str(key_path.resolve())})))
    config={'update':'disable','warming':False,'share':'disabled','model':'opencode/'+MODEL,'default_agent':'probe','plugins':['./plugins/guard'],
            'policies':[{'action':'provider.use','resource':'*','effect':'deny'},{'action':'provider.use','resource':'opencode','effect':'allow'},{'action':'tool.use','resource':'*','effect':'deny'}],
            'providers':{'opencode':{'settings':{'baseURL':base,'apiKey':'PEX-INERT-NONSECRET-NOT-A-KEY'},'models':{MODEL:{'body':{'max_tokens':32},'capabilities':{'tools':False,'input':['text'],'output':['text']}}}}},
            'agents':{'probe':{'mode':'primary','model':'opencode/'+MODEL,'steps':1,'permissions':[{'action':'*','resource':'*','effect':'deny'}]}}}
    path=case/'opencode.json';path.write_text(json.dumps(config));path.chmod(0o600)
    env={'PATH':'/usr/bin:/bin','HOME':str(output/'home'),'XDG_CONFIG_HOME':str(output/'config'),'XDG_DATA_HOME':str(output/'data'),'XDG_CACHE_HOME':str(output/'cache'),'XDG_STATE_HOME':str(output/'state'),'LANG':'C.UTF-8','TERM':'dumb'}
    env.update({'OPENCODE_DISABLE_MODELS_FETCH':'1','OPENCODE_DISABLE_AUTOUPDATE':'1','OPENCODE_DISABLE_FREE_MODELS':'1'})
    for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy'):
        if name in os.environ:env[name]=os.environ[name]
    env['NO_PROXY']=env.get('NO_PROXY','')+',127.0.0.1,localhost'
    env['no_proxy']=env.get('no_proxy',env['NO_PROXY'])+',127.0.0.1,localhost'
    start=time.monotonic();result={'kind':'provider-readiness-only','benchmark':False,'live':live,'model':'opencode/'+MODEL}
    try:
        turn=await run_turn(executable=binary,workspace=case,model='opencode/'+MODEL,prompt='Reply READY',environment=env,
                            stdout_path=output/'stdout.jsonl',stderr_path=output/'stderr.txt',deadline=start+30,standalone=True,agent='probe',terminal_database=output/'data/opencode/opencode.db')
        result.update(status='natural_stop',response=list(turn.messages),stdout_sha256=turn.stdout_sha256)
    except Exception as error:
        result.update(status='infrastructure_error',error_type=type(error).__name__)
    finally:
        result['seconds']=round(time.monotonic()-start,3)
        result['wire']=json.loads(receipt.read_text()) if receipt.exists() else {'attempts':0}
        config['providers']['opencode']['settings']['apiKey']='REMOVED-AFTER-PROBE';path.write_text(json.dumps(config));path.chmod(0o600)
        (output/'result.json').write_text(json.dumps(result,sort_keys=True,indent=2))
    return result
