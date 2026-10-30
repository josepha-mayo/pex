// @exec: {"yield_time_ms": 1000, "max_output_tokens": 1000}
/* Trusted controller-only broker. No provider SDK, tokens, eval, or host shell.
 * Native output schemas MUST be qualified against actual receipts before use.
 */
const ROOT='/vercel/sandbox/pex-task';
const HEX=/^[0-9a-f]{64}$/;
const OPS=['create','run','read','write_files','mkdir','list','stop'];
const exact=(o,ks)=>o!==null&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).sort().join('|')===[...ks].sort().join('|');
function insist(v,code){if(!v)throw new Error(code);}
function pathOK(p,privateOK=false){
 if(typeof p!=='string'||p.length>512||p.includes('\\')||p.includes('\0')||p.split('/').some(x=>x==='.'||x==='..')||p.includes('//'))return false;
 return p===ROOT||p.startsWith(ROOT+'/')||(privateOK&&/^\/tmp\/pex-wirepool-evaluation-[0-9a-f]{32}\/[A-Za-z0-9_./-]+$/.test(p));
}
function textBound(v,n){return typeof v==='string'&&v.length<=n&&!v.includes('\0');}
function decodeReceipt(r){
 insist(r&&r.isError!==true,'native_tool_error');
 if(r.structuredContent&&typeof r.structuredContent==='object')return r.structuredContent;
 insist(Array.isArray(r.content),'native_receipt_shape');
 const ts=r.content.filter(x=>x.type==='text').map(x=>x.text);
 insist(ts.length===1,'native_receipt_text_shape');
 try{return JSON.parse(ts[0]);}catch{throw new Error('native_receipt_json_required');}
}
// These are deliberately narrow adapters, not recursive searches for plausible IDs.
function sessionFrom(r){const d=decodeReceipt(r);return d.session??d;}
function commandFrom(r){const d=decodeReceipt(r);return d.command??d;}
function createFrom(r){
 const d=decodeReceipt(r);const s=d.session;const b=d.sandbox;
 insist(s&&b&&textBound(s.id,256)&&s.id&&textBound(b.id,256)&&b.id,'native_create_identity_shape');
 return {session_id:s.id,sandbox_id:b.id,sandbox_name:b.name};
}
function logsFrom(r){
 const d=decodeReceipt(r);const rows=Array.isArray(d)?d:d.logs;
 insist(Array.isArray(rows),'native_logs_shape');let stdout='',stderr='';
 for(const x of rows){insist(x&&['stdout','stderr'].includes(x.stream)&&typeof x.data==='string','native_log_entry_shape');if(x.stream==='stdout')stdout+=x.data;else stderr+=x.data;}
 insist(stdout.length<=1048576&&stderr.length<=1048576,'native_output_bound');return {stdout,stderr};
}
function makeBroker(cfg,io,native,now=()=>Date.now()){
 insist(exact(cfg,['run_id','config_sha256','team_id','project_id','image','deadline_utc','producer_sha256']),'broker_config_shape');
 insist(/^[A-Za-z0-9_-]{1,80}$/.test(cfg.run_id)&&HEX.test(cfg.config_sha256)&&HEX.test(cfg.producer_sha256),'broker_binding');
 insist(cfg.team_id==='team_jhvNBbOx4MhdfPGY8eFf75wB'&&/^prj_[A-Za-z0-9]+$/.test(cfg.project_id),'dedicated_project_required');
 insist(textBound(cfg.image,256)&&cfg.image&&Number.isFinite(Date.parse(cfg.deadline_utc)),'broker_config');
 let sequence=0,poisoned=false;const owned=new Map(),attempted=new Set();
 async function step(envelope){
  const req=envelope.request,sha=envelope.request_sha256;let result=null,error=null,ok=false;const receipts=[];let dispatched=false,commandIndex=0;
  insist(exact(req,['schema','run_id','config_sha256','sequence','arm','operation','args','deadline_utc'])&&HEX.test(sha),'request_shape');
  insist(req.schema==='pex.vercel.rpc-request.v1'&&req.run_id===cfg.run_id&&req.config_sha256===cfg.config_sha256,'request_binding');
  insist(req.sequence===sequence+1&&['baseline','pex'].includes(req.arm)&&OPS.includes(req.operation),'request_sequence_or_operation');
  const prefix=String(req.sequence).padStart(6,'0');const arm=req.arm,op=req.operation,a=req.args;
  await io.put('journal/'+prefix+'.json',{schema:'pex.vercel.rpc-attempt.v1',run_id:cfg.run_id,config_sha256:cfg.config_sha256,sequence:req.sequence,arm,operation:op,request_sha256:sha,started_utc:new Date(now()).toISOString(),retry:'never_automatically'});
  sequence=req.sequence;
  async function call(suffix,args,label){
   dispatched=true;
   let raw;
   try{raw=await native('mcp__codex_apps__vercel_'+suffix,args);}catch(e){
    const h=await io.put('receipts/'+prefix+'-'+label+'-thrown.json',{schema:'pex.vercel.native-throw.v1',tool:suffix,error:'native_call_threw_outcome_unknown'});receipts.push({label:label+'-thrown',sha256:h});
    throw new Error('native_call_threw_outcome_unknown');
   }
   const receipt={schema:'pex.vercel.native-receipt.v1',tool:'mcp__codex_apps__vercel_'+suffix,arguments:args,received_utc:new Date(now()).toISOString(),raw};
   const h=await io.put('receipts/'+prefix+'-'+label+'.json',receipt);receipts.push({label,sha256:h});return {raw,sha256:h};
  }
  function remaining(){return Math.floor(Math.min(Date.parse(req.deadline_utc),Date.parse(cfg.deadline_utc))-now());}
  async function runNative(command,args,cwd=ROOT){
   const label='cmd'+(++commandIndex);
   insist(remaining()>0,'request_deadline');
   const id=owned.get(arm);const base={teamId:cfg.team_id,sessionId:id.session_id};
   const start=await call('run_session_command',{...base,requestBody:{command,args,cwd,sudo:false,wait:false,timeout:Math.min(120000,remaining())}},label+'-start');
   const c=commandFrom(start.raw);insist(textBound(c.id,256)&&c.id,'native_command_id_shape');
   const finish=await call('get_session_command',{...base,cmdId:c.id,wait:'true'},label+'-finish');
   const f=commandFrom(finish.raw);insist(f.id===c.id&&Number.isInteger(f.exitCode),'native_command_not_terminal');
   const logs=await call('get_session_command_logs',{...base,cmdId:c.id},label+'-logs');
   return {exit_code:f.exitCode,...logsFrom(logs.raw)};
  }
  try{
   insist(remaining()>0||op==='stop','request_deadline');insist(!poisoned||op==='stop','broker_poisoned');
   if(op==='create'){
    insist(exact(a,['team_id','project_id','image','persistent','network_policy','vcpus','timeout_ms']),'create_args');
    insist(a.team_id===cfg.team_id&&a.project_id===cfg.project_id&&a.image===cfg.image&&a.persistent===false&&JSON.stringify(a.network_policy)==='{"allow":{}}'&&a.vcpus===1&&a.timeout_ms===750000,'create_frozen_config');
    insist(!attempted.has(arm)&&attempted.size<2&&[...owned.values()].every(v=>v.stopped),'fresh_sequential_arms');attempted.add(arm);
    const sandboxName=cfg.run_id+'-'+arm;
    const cr=await call('create_sandboxes_v4',{teamId:cfg.team_id,requestBody:{projectId:cfg.project_id,name:sandboxName,image:cfg.image,persistent:false,networkPolicy:{allow:{}},resources:{vcpus:1},region:'iad1',timeout:750000,ports:[]}},'create');
    const identity=createFrom(cr.raw);insist(![...owned.values()].some(v=>v.session_id===identity.session_id||v.sandbox_id===identity.sandbox_id),'fresh_native_identity_required');owned.set(arm,{...identity,stopped:false});
    const get=await call('get_session',{teamId:cfg.team_id,sessionId:identity.session_id},'create-get');const s=sessionFrom(get.raw);
    insist(s.id===identity.session_id&&s.status==='running','created_session_not_running');
    // Configuration is pinned by the actual create tool arguments and native receipt.
    await io.put('owned-'+arm+'.json',{schema:'pex.vercel.owned-session.v1',run_id:cfg.run_id,config_sha256:cfg.config_sha256,arm,sequence:req.sequence,request_sha256:sha,team_id:cfg.team_id,project_id:cfg.project_id,sandbox_id:identity.sandbox_id,sandbox_name:sandboxName,session_id:identity.session_id,image:cfg.image,persistent:false,network_policy:{allow:{}},vcpus:1,timeout_ms:750000,create_receipt_sha256:cr.sha256,get_receipt_sha256:get.sha256,producer_sha256:cfg.producer_sha256});
    result={session_id:identity.session_id,sandbox_id:identity.sandbox_id};
   }else{
    const id=owned.get(arm);insist(id&&!id.stopped,'owned_live_session_required');const base={teamId:cfg.team_id,sessionId:id.session_id};
    if(op==='stop'){
     insist(exact(a,[]),'stop_args');const stop=await call('stop_session',base,'stop');decodeReceipt(stop.raw);
     const get=await call('get_session',base,'stop-get');const s=sessionFrom(get.raw);insist(s.id===id.session_id&&s.status==='stopped','stop_not_confirmed');id.stopped=true;
     await io.put('stopped-'+arm+'.json',{schema:'pex.vercel.stop-proof.v1',run_id:cfg.run_id,config_sha256:cfg.config_sha256,arm,sequence:req.sequence,request_sha256:sha,team_id:cfg.team_id,project_id:cfg.project_id,sandbox_id:id.sandbox_id,session_id:id.session_id,stop_receipt_sha256:stop.sha256,get_receipt_sha256:get.sha256,status:'stopped',producer_sha256:cfg.producer_sha256});
     result={session_id:id.session_id,stopped:true};
    }else if(op==='run'){
     insist(exact(a,['command','cwd'])&&a.cwd===ROOT&&textBound(a.command,16384),'run_args');
     insist(!/(^|[\s;&|])sudo(?:\s|$)/.test(a.command),'sudo_disallowed');result=await runNative('/bin/bash',['-c',a.command]);
    }else if(op==='mkdir'){
     insist(exact(a,['path'])&&pathOK(a.path),'mkdir_args');const r=await call('create_session_directory',{...base,requestBody:{path:a.path,recursive:true}},'mkdir');decodeReceipt(r.raw);result=true;
    }else if(op==='read'){
     insist(exact(a,['path'])&&pathOK(a.path),'read_args');
     const r=await runNative('python3',['-I','-c',READ_SCRIPT,a.path]);insist(r.exit_code===0&&!r.stderr,'read_failed');result=JSON.parse(r.stdout);insist(typeof result==='string','read_result');
    }else if(op==='list'){
     insist(exact(a,['path'])&&pathOK(a.path),'list_args');const r=await runNative('python3',['-I','-c',LIST_SCRIPT,a.path]);insist(r.exit_code===0&&!r.stderr,'list_failed');result=JSON.parse(r.stdout);
    }else if(op==='write_files'){
     insist(exact(a,['files_base64'])&&a.files_base64&&typeof a.files_base64==='object'&&!Array.isArray(a.files_base64),'write_args');
     const files=Object.entries(a.files_base64);insist(files.length>0&&files.length<=128,'file_count');let total=0;
     for(const [p,b]of files){insist(pathOK(p,true)&&typeof b==='string'&&/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(b),'file_path_or_base64');total+=b.length;}
     insist(total<=1400000,'write_size');
     for(const [p,b]of files){for(let offset=0;offset<b.length||offset===0;offset+=60000){const chunk=b.slice(offset,offset+60000);const r=await runNative('python3',['-I','-c',WRITE_SCRIPT,p,String(offset/4*3),chunk]);insist(r.exit_code===0&&!r.stderr&&r.stdout==='true\n','write_failed');}}result=true;
    }
   }
   ok=true;
  }catch(e){error={code:/^[a-z0-9_]+$/.test(e.message)?e.message:'broker_internal_error',outcome:dispatched?'uncertain_no_retry':'not_dispatched'};if(dispatched)poisoned=true;}
  const bundle={schema:'pex.vercel.native-receipt-bundle.v1',run_id:cfg.run_id,config_sha256:cfg.config_sha256,sequence:req.sequence,request_sha256:sha,receipts};
  const bundleSha=await io.put('receipts/'+prefix+'-bundle.json',bundle);
  const response={schema:'pex.vercel.rpc-response.v1',run_id:cfg.run_id,config_sha256:cfg.config_sha256,sequence:req.sequence,request_sha256:sha,ok,result:ok?result:null,error:ok?null:error,raw_native_receipt_sha256:bundleSha};
  await io.put('responses/'+prefix+'.json',response);return response;
 }
 return {step,get sequence(){return sequence;},get poisoned(){return poisoned;},get owned(){return [...owned.entries()];}};
}
const READ_SCRIPT=`import os,sys,stat,json
p=sys.argv[1]
assert os.path.realpath(p)==p
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
s=os.fstat(fd)
assert stat.S_ISREG(s.st_mode) and s.st_size<=262144
b=os.read(fd,262145)
assert len(b)==s.st_size
print(json.dumps(b.decode('utf-8')))
`;
const LIST_SCRIPT=`import os,sys,json
p=sys.argv[1]
assert os.path.realpath(p)==p
names=sorted(os.listdir(p))
assert len(names)<=4096
print(json.dumps(names))
`;
const WRITE_SCRIPT=`import os,sys,base64,stat
p=sys.argv[1];offset=int(sys.argv[2]);data=base64.b64decode(sys.argv[3],validate=True)
parts=p.split('/')[1:]
dfd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
try:
 for part in parts[:-1]:
  try:os.mkdir(part,0o700,dir_fd=dfd)
  except FileExistsError:pass
  child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=dfd)
  os.close(dfd);dfd=child
 fd=os.open(parts[-1],os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=dfd)
 try:
  s=os.fstat(fd)
  assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
  if offset==0:os.ftruncate(fd,0)
  else:assert s.st_size==offset
  os.lseek(fd,offset,os.SEEK_SET)
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(data)
 finally:os.close(fd)
finally:os.close(dfd)
print('true')
`;
// Concatenate after core.mjs with `export ` removed, then replace CONFIGURATION.
// Runs only in functions.exec; do not run this file with Node.
const LIVE_QUALIFIED=false; // BLOCKED: provider 402, no actual receipt-shape qualification.
insist(LIVE_QUALIFIED,'native_route_not_qualified');
const BOOT={"rpc_root":"/workspace/scratch/c62c151ada7d/runtime-private/pex-offline-example/native-rpc","config":{"run_id":"offline-example-do-not-run","config_sha256":"0000000000000000000000000000000000000000000000000000000000000000","team_id":"team_jhvNBbOx4MhdfPGY8eFf75wB","project_id":"prj_OfflineOnly","image":"vercel/sandbox/universal","deadline_utc":"2026-10-30T17:00:00Z","producer_sha256":"7c6330ed63b16dcc7dc1f281ba9a5efa26d4b57c4fafb3ec9d70d83dea8c19bd"}};
const HELPER='/workspace/scratch/c62c151ada7d/pex-vercel-paired-WIP-20261030/broker/host_io.py';
function base64utf8(s){
 const bytes=[];for(const c of s){let n=c.codePointAt(0);if(n<128)bytes.push(n);else if(n<2048)bytes.push(192|(n>>6),128|(n&63));else if(n<65536)bytes.push(224|(n>>12),128|((n>>6)&63),128|(n&63));else bytes.push(240|(n>>18),128|((n>>12)&63),128|((n>>6)&63),128|(n&63));}
 const a='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';let out='';for(let i=0;i<bytes.length;i+=3){let x=(bytes[i]<<16)|((bytes[i+1]||0)<<8)|(bytes[i+2]||0);out+=a[(x>>18)&63]+a[(x>>12)&63]+(i+1<bytes.length?a[(x>>6)&63]:'=')+(i+2<bytes.length?a[x&63]:'=');}return out;
}
insist(/^\/workspace\/scratch\/c62c151ada7d\/[A-Za-z0-9_./-]+\/native-rpc$/.test(BOOT.rpc_root)&&!BOOT.rpc_root.split('/').includes('..'),'rpc_root_bound');
async function hostCall(mode,encoded){
 const r=await tools.exec_command({cmd:'python3 '+HELPER+' '+BOOT.rpc_root+' '+mode+" '"+encoded+"'",max_output_tokens:250000,yield_time_ms:1000});
 insist(!r.session_id&&r.exit_code===0,'host_io_failed');const v=JSON.parse(r.output);insist(v.ok===true,'host_io_failed');return v.result;
}
async function host(payload){
 const encoded=base64utf8(JSON.stringify(payload));
 if(encoded.length<=60000)return await hostCall('direct',encoded);
 for(let i=0;i<encoded.length;i+=60000)await hostCall(i===0?'begin':'append',encoded.slice(i,i+60000));
 return await hostCall('finish','');
}
const io={put:async(name,value)=>(await host({op:'put',name,value})).sha256};
const broker=makeBroker(BOOT.config,io,async(name,args)=>{insist(typeof tools[name]==='function','native_tool_unavailable');return await tools[name](args);});
while(Date.now()<Date.parse(BOOT.config.deadline_utc)){
 const envelope=await host({op:'next',sequence:broker.sequence+1});
 if(envelope){const response=await broker.step(envelope);text({sequence:response.sequence,ok:response.ok,error:response.error});}
 else await new Promise(resolve=>setTimeout(resolve,500));
 if(broker.owned.length===2&&broker.owned.every(([,x])=>x.stopped))break;
}
text({broker_terminal:true,sequence:broker.sequence,poisoned:broker.poisoned,owned:broker.owned});
// If a live session remains root MUST stop/reconcile it using native tools; never
// interpret broker end, deadline, or a missing receipt as confirmed destruction.
