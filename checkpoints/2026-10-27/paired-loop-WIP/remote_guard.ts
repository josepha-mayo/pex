// WIP: real CLI remote-only tool guard. No keys, endpoints or task solutions.
// Configuration is controller-owned; model tool code runs only behind remote MCP.
import { Plugin } from '@opencode/plugin';
import { readFileSync, writeFileSync } from 'node:fs';
const cfg = CONFIGURATION;
const allowed = new Set(['pex_remote_run','pex_remote_read','pex_remote_write','pex_remote_list']);
export default Plugin.define({id:'pex-remote-only-pilot',async setup(ctx) {
  await ctx.tool.transform(editor=>{for(const t of editor.list()) if(!allowed.has(t.id)) editor.remove(t.id);});
  await ctx.permission.hook('evaluate',e=>{if(!allowed.has(e.action)){e.effect='deny';e.message='Only isolated remote tools are permitted';}});
  await ctx.tool.hook('execute.before',e=>{if(!allowed.has(e.tool)) throw new Error('LOCAL_TOOL_DENIED');});
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
    const ok=e.model.providerID==='opencode'&&e.model.id===cfg.model&&e.kind==='primary';
    e.baseURL=ok?cfg.baseURL:'http://127.0.0.1:1/blocked';
    if(!ok)throw new Error('MODEL_OR_AUXILIARY_DENIED');
  });
  await ctx.session.hook('http.request',async e=>{
    const deny=()=>{e.request=new Request('http://127.0.0.1:1/blocked',{method:'POST'});throw new Error('REQUEST_OR_BUDGET_DENIED');};
    let b;try{b=await e.request.clone().json();}catch{return deny();}
    const u=new URL(e.request.url);
    if(e.kind!=='primary'||e.model.providerID!=='opencode'||e.model.id!==cfg.model||u.href!==cfg.endpoint||
       e.request.method!=='POST'||b.model!==cfg.model||b.max_tokens!==cfg.outputPerCall||
       b.n!==undefined&&b.n!==1||!Array.isArray(b.tools)||!b.tools.length||
       b.tools.some(t=>t.type!=='function'||!allowed.has(t.function?.name)))return deny();
    const ledger=JSON.parse(readFileSync(cfg.ledger,'utf8'));
    if(ledger.calls>=cfg.maxCalls||ledger.model!==cfg.model)return deny();
    ledger.calls++; // reserve BEFORE dispatch; never refund unknown calls/retries
    writeFileSync(cfg.ledger,JSON.stringify(ledger),{mode:0o600});
  });
  await ctx.session.hook('retry',e=>{e.decision={retry:false};});
  await ctx.session.hook('experimental.ws.handshake',e=>{e.url='ws://127.0.0.1:1/blocked';throw new Error('WS_DENIED');});
}});
