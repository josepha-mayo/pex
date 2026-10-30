// Concatenate after core.mjs with `export ` removed, then replace CONFIGURATION.
// Runs only in functions.exec; do not run this file with Node.
const LIVE_QUALIFIED=false; // BLOCKED: provider 402, no actual receipt-shape qualification.
insist(LIVE_QUALIFIED,'native_route_not_qualified');
const BOOT=CONFIGURATION;
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
