// WIP authored-only staged guard; not wired to any live admission.
// Finalization is a counted request, never an extra call beyond the phase cap.
// Configuration is controller-owned; model tool code runs only behind remote MCP.
import { Plugin } from '@opencode/plugin';
import { readFileSync } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
const cfg = CONFIGURATION;
let pending=null;
let acceptedPhaseRequests=0;
if (![8,4].includes(cfg.phaseCalls)) throw new Error('FIXED_PHASE_REQUIRED');
async function funding(payload){
 const r=await fetch(cfg.funding.url,{method:'POST',headers:{'Authorization':'Bearer '+cfg.funding.token,'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const v=await r.json();if(!r.ok||v.ok!==true)throw new Error('WORKER_FUNDING_DENIED:'+String(v.category||'unknown'));return v;
}
const allowed = new Set(['pex_remote_run','pex_remote_read','pex_remote_write','pex_remote_list']);
export default Plugin.define({id:'pex-remote-only-pilot',async setup(ctx) {
  await ctx.tool.transform(editor=>{for(const t of editor.list()) if(!allowed.has(t.id)) editor.remove(t.id);});
  await ctx.permission.hook('evaluate',e=>{if(!allowed.has(e.action)){e.effect='deny';e.message='Only isolated remote tools are permitted';}});
  await ctx.tool.hook('execute.before',e=>{if(!allowed.has(e.tool) || acceptedPhaseRequests>=cfg.phaseCalls) throw new Error('LOCAL_OR_FINALIZATION_TOOL_DENIED');});
  await ctx.session.hook('prompt',async()=>{
    const until=Date.now()+10000;
    while(Date.now()<until){
      const servers=await ctx.mcp.list();
      const names=(await ctx.tool.list()).map(t=>t.id);
      if(servers.data?.some(s=>s.name==='pex_remote'&&s.status.status==='connected')){await new Promise(r=>setTimeout(r,1000));return;}
      await new Promise(r=>setTimeout(r,50));
    }
    throw new Error('REMOTE_MCP_NOT_READY');
  });
  await ctx.session.hook('context',e=>{
    e.options.maxTokens=cfg.outputPerCall;
    e.tools=Object.fromEntries(Object.entries(e.tools).filter(([n])=>allowed.has(n)));
    if(!e.tools.pex_remote_run)throw new Error('REMOTE_TOOL_NOT_OFFERED');
  });
  await ctx.session.hook('title',e=>{e.result='PEX isolated paired pilot';});
  await ctx.session.hook('model.request',e=>{
    const ok=e.model.providerID==='nebius'&&e.model.id===cfg.model&&e.kind==='primary';
    e.baseURL=ok?cfg.baseURL:'http://127.0.0.1:1/blocked';
    if(!ok)throw new Error('MODEL_OR_AUXILIARY_DENIED');
  });
  await ctx.session.hook('http.request',async e=>{
    const deny=()=>{e.request=new Request('http://127.0.0.1:1/blocked',{method:'POST'});throw new Error('REQUEST_OR_BUDGET_DENIED');};
    let b,body;try{body=await e.request.clone().text();if(Buffer.byteLength(body)>2097152)return deny();b=JSON.parse(body);}catch{return deny();}
    const u=new URL(e.request.url);
    if(e.kind!=='primary'||e.model.providerID!=='nebius'||e.model.id!==cfg.model||u.href!==cfg.endpoint||
       e.request.method!=='POST'||b.model!==cfg.model||b.max_completion_tokens!==cfg.outputPerCall||
       b.n!==undefined&&b.n!==1||!Array.isArray(b.tools)||!b.tools.length||
       b.tools.some(t=>t.type!=='function'||!allowed.has(t.function?.name)))return deny();
    if(pending!==null)return deny();
    if(acceptedPhaseRequests===cfg.phaseCalls-1){
      // Keep allowed tool schemas, but forbid a tool call during finalization.
      // Exact rewritten bytes are reserved and hashed below before dispatch.
      b.tool_choice='none';body=JSON.stringify(b);
      e.request=new Request(e.request,{body});
    }
    const call_id=randomUUID(),request_sha256=createHash('sha256').update(body).digest('hex');
    // Let the trusted phase ledger record cap refusal so the controller retains
    // accepted-call usage/time instead of misclassifying a generic CLI error.
    // PhaseFunding refuses before its underlying ledger or any provider dispatch.
    await funding({operation:'reserve',call_id,request_sha256,request_base64:Buffer.from(body).toString('base64')});
    // Independent fail-closed defense if an incorrectly composed ledger admits it.
    if(acceptedPhaseRequests>=cfg.phaseCalls)return deny();
    acceptedPhaseRequests+=1;
    pending={call_id,request_sha256}; // unknown responses retain full reservation
    const key=readFileSync(cfg.keyPath,'utf8').trim();
    if(!key || /[\r\n]/.test(key))return deny();
    const headers=new Headers(e.request.headers);headers.set('Authorization','Bearer '+key);
    e.request=new Request(e.request,{headers});
  });
  await ctx.session.hook('http.response',async e=>{
    const receipt=pending;pending=null;
    if(!receipt||e.kind!=='primary'||e.model.providerID!=='nebius'||e.model.id!==cfg.model||e.request.url!==cfg.endpoint)throw new Error('RESPONSE_IDENTITY_DENIED');
    const reader=e.response.clone().body?.getReader();if(!reader)return;
    const chunks=[];let size=0;
    try{
      for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>2097152){await reader.cancel();return;}chunks.push(Buffer.from(value));}
      await funding({operation:'settle',...receipt,status:e.response.status,content_type:e.response.headers.get('content-type')||'',raw_base64:Buffer.concat(chunks).toString('base64')});
    }catch{throw new Error('WORKER_USAGE_UNCERTAIN');}
  });
  await ctx.session.hook('retry',e=>{e.decision={retry:false};});
  await ctx.session.hook('experimental.ws.handshake',e=>{e.url='ws://127.0.0.1:1/blocked';throw new Error('WS_DENIED');});
}});
