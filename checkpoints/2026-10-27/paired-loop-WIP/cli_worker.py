"""Pilot-only actual OpenCode worker with remote-only MCP tools.

No candidate code executes here. Requires root-admitted remote workers, private
key, exact CLI binary, and explicit activation. No VM creation occurs here.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from dataclasses import asdict
from opencode_cli import run_turn
from opencode_v2_receipt import prior_sequence
from remote_mcp import serve_remote

PIN='ca9b3ee262e33bb4e7aa0e1230dc61086a474c8c8016b980081d0719712fd2e7'
MODEL='deepseek-v4.1-flash-free'
BASE='https://opencode.ai/zen/v1'
TOOLS=['pex_remote_run','pex_remote_read','pex_remote_write','pex_remote_list']


class CLIWorker:
    def __init__(self, *, remotes, private_root, binary, modules, key_path, pool,
                 max_calls=12, output_per_call=4096, activate=False):
        if activate is not True: raise PermissionError('pilot_not_activated')
        self.binary=Path(binary).resolve();self.modules=Path(modules).resolve()
        if hashlib.sha256(self.binary.read_bytes()).hexdigest()!=PIN: raise ValueError('CLI_identity_changed')
        if json.loads((self.modules/'@opencode/plugin/package.json').read_text())['version']!='2.1.4': raise ValueError('plugin_identity_changed')
        key_path=Path(key_path)
        if key_path.is_symlink() or key_path.stat().st_mode&0o077: raise ValueError('private_key_permissions')
        key=key_path.read_text().strip()
        if not key: raise ValueError('empty_key')
        if set(remotes)!={'baseline','pex'} or max_calls!=12 or output_per_call!=4096: raise ValueError('fixed_pilot_envelope')
        self.pool=pool;self.remotes=remotes;self.states={}
        self.root=Path(private_root);self.root.mkdir(mode=0o700,parents=False,exist_ok=False)
        self.max_calls=max_calls;self.output_per_call=output_per_call
        for condition,remote in remotes.items():
            profile=self.root/condition;profile.mkdir(mode=0o700)
            case=profile/'case';case.mkdir(mode=0o700)
            (case/'plugins/guard').mkdir(parents=True)
            (profile/'node_modules').symlink_to(self.modules,target_is_directory=True)
            cm=serve_remote(remote,profile/'rpc');sock=cm.__enter__()
            ledger=profile/'calls.json';ledger.write_text(json.dumps({'calls':0,'model':MODEL}));ledger.chmod(0o600)
            cfg={'baseURL':BASE,'endpoint':BASE+'/chat/completions','model':MODEL,'ledger':str(ledger),
                 'maxCalls':max_calls,'outputPerCall':output_per_call}
            guard=Path(__file__).with_name('remote_guard.ts').read_text().replace('CONFIGURATION',json.dumps(cfg))
            (case/'plugins/guard/index.ts').write_text(guard)
            conf={'model':'opencode/'+MODEL,'default_agent':'paired','plugins':['./plugins/guard'],
                  'mcp':{'servers':{'pex_remote':{'type':'local','command':['/usr/bin/python3',str(Path(__file__).with_name('remote_mcp.py').resolve()),'--socket',str(sock)],'codemode':False,'protocol':'legacy','timeout':{'startup':10000,'catalog':10000,'execution':65000}}}},
                  'policies':[{'action':'provider.use','resource':'*','effect':'deny'},{'action':'provider.use','resource':'opencode','effect':'allow'},
                              {'action':'integration.use','resource':'*','effect':'deny'},{'action':'integration.use','resource':'mcp:pex_remote','effect':'allow'},
                              {'action':'tool.use','resource':'*','effect':'deny'}]+[{'action':'tool.use','resource':n+':*','effect':'allow'} for n in TOOLS],
                  'providers':{'opencode':{'settings':{'baseURL':BASE,'apiKey':key},'models':{MODEL:{'body':{'max_tokens':output_per_call},'capabilities':{'tools':True,'input':['text'],'output':['text']}}}}},
                  'agents':{'paired':{'mode':'primary','model':'opencode/'+MODEL,'steps':max_calls,
                      'system':'Work on the user task autonomously using only pex_remote tools. All task files and commands belong to that isolated remote workspace, not this controller. Do not use local tools.',
                      'permissions':[{'action':'*','resource':'*','effect':'deny'}]+[{'action':n,'resource':'*','effect':'allow'} for n in TOOLS]}}}
            config=case/'opencode.json';config.write_text(json.dumps(conf));config.chmod(0o600)
            self.states[condition]={'profile':profile,'case':case,'cm':cm,'seq':0,'stopped':False,'ledger':ledger}
        del key

    async def turn(self,arm,*,prompt,session_id,remaining):
        condition=arm['condition'];state=self.states[condition]
        if state['stopped']: raise ValueError('worker_already_stopped')
        profile=state['profile'];db=profile/'data/opencode/opencode.db'
        before=prior_sequence(db,session_id)
        index=state['seq'];state['seq']+=1
        env={'PATH':'/usr/bin:/bin','HOME':str(profile/'home'),'XDG_CONFIG_HOME':str(profile/'config'),
             'XDG_DATA_HOME':str(profile/'data'),'XDG_CACHE_HOME':str(profile/'cache'),'XDG_STATE_HOME':str(profile/'state'),'LANG':'C.UTF-8','TERM':'dumb'}
        receipt=await run_turn(executable=self.binary,workspace=state['case'],model='opencode/'+MODEL,prompt=prompt,
                              environment=env,stdout_path=profile/f'turn-{index}.jsonl',stderr_path=profile/f'turn-{index}.stderr',
                              deadline=time.monotonic()+remaining['active_seconds'],session_id=session_id,standalone=True,
                              agent='paired',terminal_database=db)
        usage={'calls':0,'input_tokens':0,'output_tokens':0}
        with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
            for (data,) in conn.execute("SELECT data FROM session_message WHERE session_id=? AND seq>? AND type='assistant' ORDER BY seq",(receipt.session_id,before)):
                row=json.loads(data);tokens=row.get('tokens',{});model=row.get('model',{})
                if model.get('providerID')!='opencode' or model.get('id')!=MODEL: raise ValueError('worker_model_changed')
                values=[tokens.get('input'),tokens.get('output'),tokens.get('reasoning'),tokens.get('cache',{}).get('read'),tokens.get('cache',{}).get('write')]
                if any(type(v) is not int or v<0 for v in values): raise ValueError('worker_usage_unproven')
                usage['calls']+=1;usage['input_tokens']+=values[0]+values[3]+values[4];usage['output_tokens']+=values[1]+values[2]
        remote=self.remotes[condition]
        check=remote.run('python -m pytest -q tests/test_smoke.py')
        public_check={'command':'python -m pytest -q tests/test_smoke.py','exit_code':check['exit_code'],
                      'output':(check['stdout']+'\n'+check['stderr'])[:8000]}
        public_check['receipt_sha256']=hashlib.sha256(json.dumps(public_check,sort_keys=True).encode()).hexdigest()
        diff=remote.run('git diff -- .; git status --short')
        observation={'assistant_final':'\n'.join(receipt.messages)[-16000:],'public_check':public_check,
                     'public_diff':diff['stdout'][:16000],'receipt_sha256':receipt.stdout_sha256}
        return {'session_id':receipt.session_id,'receipt':asdict(receipt),'usage':usage,
                'terminal':'natural_stop','public_observation':observation}

    async def stop(self,arm):
        state=self.states[arm['condition']]
        if not state['stopped']:
            state['stopped']=True;state['cm'].__exit__(None,None,None)
        # Remote background processes are NOT proven quiescent by MCP revocation.
        # The isolated protected grader must enforce its own post-stop boundary.

    async def cleanup(self):
        for condition,state in self.states.items():
            if not state['stopped']: await self.stop({'condition':condition})
        self.pool.close()
