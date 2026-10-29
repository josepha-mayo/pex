"""Actual pinned CLI, local authored HTTP only; no provider/VM/key access.

Qualifies forced textual finalization within8+4 accepted reservations and
validated CLI natural stops, not spontaneous task completion. Same-session
resume is exercised through StagedWorker symmetrically for both condition labels.
This does not qualify a live VM adapter or guarantee arbitrary model compliance.
"""
import asyncio
import http.server
import json
from pathlib import Path
import threading
import time
import pytest
from worker_funding import _WorkerLedger, PRICING_SHA
from staged_funding import PhaseFunding
from staged_worker import StagedWorker
from staged_envelope import PHASES
from controller import WorkerBudgetTerminal
import nebius_worker as cw

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('output_per_call',[4096,16384])
@pytest.mark.parametrize('condition',['baseline','pex'])
@pytest.mark.parametrize('finalization',['stop','tool_calls','length'])
def test_actual_cli_natural_checkpoint_finalization_and_same_session(monkeypatch,tmp_path,finalization,condition,output_per_call):
    accepted=[]; remote_calls=[]; stage=[0]; per_stage=[0,0]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            index=stage[0];per_stage[index]+=1; count=per_stage[index]
            accepted.append((index,count))
            assert self.headers.get('Authorization')=='Bearer SYNTHETIC-STAGED-ONLY'
            assert body['max_completion_tokens']==output_per_call
            assert count<=PHASES[index].calls
            assert (body.get('tool_choice')=='none') == (count==PHASES[index].calls)
            if count<PHASES[index].calls or finalization=='tool_calls':
                delta={'role':'assistant','tool_calls':[{'index':0,'id':f'authored-{index}-{count}',
                    'type':'function','function':{'name':'pex_remote_run','arguments':'{"command":"AUTHORED-ONLY"}'}}]}
                finish='tool_calls'
            elif finalization=='length':
                # Authored exhausted reasoning-only finalization, not task success.
                delta={'role':'assistant','reasoning':'Authored private reasoning'};finish='length'
            else:
                delta={'role':'assistant','content':'Authored phase finished'};finish='stop'
            output_tokens=output_per_call if count==PHASES[index].calls and output_per_call==16384 and finalization!='tool_calls' else 1
            used={'prompt_tokens':11,'completion_tokens':output_tokens,'total_tokens':11+output_tokens,
                  'completion_tokens_details':{'reasoning_tokens':output_tokens if finish=='length' else 0}}
            common={'id':f'authored-{index}-{count}','model':cw.MODEL}
            chunks=[{**common,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                {**common,'choices':[{'index':0,'delta':{},'finish_reason':finish}]},
                {**common,'choices':[],'usage':used}]
            raw=(''.join('data: '+json.dumps(x)+'\n\n' for x in chunks)+'data: [DONE]\n\n').encode()
            if output_per_call==16384 and count==PHASES[index].calls and finalization=='stop':
                raw=b':'+b'x'*(2*1024*1024)+b'\n\n'+raw  # New bounded guard/RPC must retain >legacy2MiB.
            self.send_response(200);self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*a): pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    monkeypatch.setattr(cw,'BASE',f'http://127.0.0.1:{server.server_port}/v1')
    class Remote:
        vm_deadline=None
        scope=None
        closed=False
        def set_scope_deadline(self,value):
            assert self.scope is None and value<=self.vm_deadline;self.scope=value
        async def end_scope(self):self.scope=None
        async def close(self):self.closed=True
        def run(self,command): remote_calls.append(command);return {'stdout':'authored','stderr':'','exit_code':0}
        def read(self,*a): return 'authored'
        def write(self,*a): return {'written':True}
        def list(self,*a): return []
    class Pool:
        def close(self): pass
    key=tmp_path/'synthetic.key';key.write_text('SYNTHETIC-STAGED-ONLY');key.chmod(0o600)
    ledgers={c:_WorkerLedger(tmp_path/'funding.sqlite',arm=c,approved_config_digest='a'*64,
        approval_ref='AUTHORED-NOT-APPROVAL',pricing_provenance_sha256=PRICING_SHA,
        output_token_bound=output_per_call,arm_budget_nano_usd=750000000 if output_per_call==16384 else 375000000) for c in ('baseline','pex')}
    funding={c:PhaseFunding(v) for c,v in ledgers.items()}
    worker=cw.NebiusCLIWorker(remotes={c:Remote() for c in funding},private_root=tmp_path/'cli',
        binary=ROOT/'opencode-qualification-20261027/install/node_modules/@opencode/cli-linux-x64/bin/opencode',
        modules=ROOT/'opencode-qualification-20261027/mock/node_modules',key_path=key,pool=Pool(),
        activate=True,funding=funding,authored=True,output_per_call=output_per_call)
    arm=dict(condition=condition,prompt='Authored task',worker_identity='nebius/'+cw.MODEL,public_sha256='a'*64)
    class Lifecycle:
        async def prepare(self,arm,*,deadline):
            remote=worker.remotes[arm['condition']];remote.vm_deadline=deadline;return remote
    adapter=StagedWorker(worker,Lifecycle())
    async def exercise():
        session=None;results=[]
        try:
            await adapter.prepare(arm,deadline=time.monotonic()+330)
            for index,limit in enumerate(PHASES):
                stage[0]=index
                result=await adapter.phase(arm,prompt='Authored first phase' if index==0 else 'Authored same-session continuation',
                    session_id=session,phase_index=index,limit=limit)
                assert result['terminal']=='natural_stop'
                assert result['usage']['calls']==limit.calls
                assert result['usage']['input_tokens']==limit.calls*11
                assert result['usage']['output_tokens']==limit.calls-1+(output_per_call if output_per_call==16384 else 1)
                assert result['phase_stop_policy']=='counted_forced_textual_finalization_not_task_completion'
                if index==0:
                    observation=await adapter.observe(arm,result)
                    assert observation['public_check']['exit_code']==0
                if session is not None: assert result['session_id']==session
                session=result['session_id'];results.append(result)
            assert sum(r['usage']['calls'] for r in results)==12
        finally:
            await adapter.cleanup()
    try:
        if finalization=='length':
            with pytest.raises(WorkerBudgetTerminal) as caught: asyncio.run(exercise())
            assert caught.value.code=='worker_attempt_cap_refused'
            assert caught.value.usage==dict(calls=8,input_tokens=88,output_tokens=7+(output_per_call if output_per_call==16384 else 1),uncertain_calls=0)
            assert caught.value.worker_active_seconds>0
            assert per_stage==[8,0]  # Attempt nine never reaches provider/ledger.
            guard=(worker.states[condition]['case']/'plugins/guard/index.ts').read_text()
            assert f'"outputPerCall": {output_per_call}' in guard
            assert f'"maxResponseBytes": {ledgers[condition].max_response_bytes}' in guard
            assert ledgers[condition].usage_snapshot()==caught.value.usage
            assert not funding[condition].finished
            assert remote_calls.count('AUTHORED-ONLY')==7
            return
        if finalization=='tool_calls':
            with pytest.raises(ValueError): asyncio.run(exercise())
            assert per_stage==[8,0]
            assert not funding[condition].finished
            assert remote_calls.count('AUTHORED-ONLY')==7
            return
        asyncio.run(exercise())
        assert per_stage==[8,4]
        assert ledgers[condition].usage_snapshot()['calls']==12
        assert remote_calls.count('AUTHORED-ONLY')==10
    finally:
        server.shutdown();server.server_close()
        for ledger in ledgers.values(): ledger.close()
