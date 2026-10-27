"""WIP optional funded Nebius BYOK worker; existing free worker stays separate.

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
from budget_rpc import serve_budget
from worker_funding import WorkerFunding

PIN='ca9b3ee262e33bb4e7aa0e1230dc61086a474c8c8016b980081d0719712fd2e7'
MODEL='deepseek-ai/DeepSeek-V4.1-Flash-1017'
BASE='https://api.tokenfactory.nebius.com/v1'
TOOLS=['pex_remote_run','pex_remote_read','pex_remote_write','pex_remote_list']


class NebiusCLIWorker:
    def __init__(self, *, remotes, private_root, binary, modules, key_path, pool,
                 max_calls=12, output_per_call=4096, activate=False, funding=None, authored=False):
        if activate is not True: raise PermissionError('pilot_not_activated')
        if set(funding or {})!={'baseline','pex'}: raise PermissionError('worker_funding_required')
        if authored:
            if not BASE.startswith('http://127.0.0.1:'): raise PermissionError('authored_loopback_only')
        elif any(type(v) is not WorkerFunding for v in funding.values()):
            raise PermissionError('independently_admitted_worker_funding_required')
        self.funding=funding
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
        self.key_path=str(key_path.resolve())

    def _start(self,condition):
        if condition in self.states: return
        remote=self.remotes[condition]() if callable(self.remotes[condition]) else self.remotes[condition]
        self.remotes[condition]=remote
        profile=self.root/condition;profile.mkdir(mode=0o700)
        case=profile/'case';case.mkdir(mode=0o700)
        (case/'plugins/guard').mkdir(parents=True)
        (profile/'node_modules').symlink_to(self.modules,target_is_directory=True)
        cm=serve_remote(remote,profile/'rpc');sock=cm.__enter__()
        budget_cm=serve_budget(self.funding[condition]);funding_rpc=budget_cm.__enter__()
        cfg={'baseURL':BASE,'endpoint':BASE+'/chat/completions','model':MODEL,'funding':funding_rpc,
             'maxCalls':self.max_calls,'outputPerCall':self.output_per_call,'keyPath':self.key_path}
        guard=Path(__file__).with_name('nebius_guard.ts').read_text().replace('CONFIGURATION',json.dumps(cfg))
        (case/'plugins/guard/index.ts').write_text(guard)
        conf={'model':'nebius/'+MODEL,'default_agent':'paired','plugins':['./plugins/guard'],
              'mcp':{'servers':{'pex_remote':{'type':'local','command':['/usr/bin/python3',str(Path(__file__).with_name('remote_mcp.py').resolve()),'--socket',str(sock)],'codemode':False,'protocol':'legacy','timeout':{'startup':10000,'catalog':10000,'execution':65000}}}},
              'policies':[{'action':'provider.use','resource':'*','effect':'deny'},{'action':'provider.use','resource':'nebius','effect':'allow'},
                          {'action':'tool.use','resource':'*','effect':'deny'}]+[{'action':'tool.use','resource':n+':*','effect':'allow'} for n in TOOLS],
              'providers':{'nebius':{'package':'@opencode/ai/providers/openai-compatible','settings':{'baseURL':BASE,'apiKey':'PEX-INERT-NONSECRET-NOT-A-KEY','provider':'nebius','transport':'http','encoding':'none'},'models':{MODEL:{'modelID':MODEL,'body':{'max_tokens':self.output_per_call,'stream_options':{'include_usage':True}},'capabilities':{'tools':True,'input':['text'],'output':['text']}}}}},
              'agents':{'paired':{'mode':'primary','model':'nebius/'+MODEL,'steps':self.max_calls,
                  'system':'Work on the user task autonomously using only pex_remote tools. All task files and commands belong to that isolated remote workspace, not this controller. Do not use local tools.',
                  'permissions':[{'action':'*','resource':'*','effect':'deny'}]+[{'action':n,'resource':'*','effect':'allow'} for n in TOOLS]}}}
        config=case/'opencode.json';config.write_text(json.dumps(conf));config.chmod(0o600)
        self.states[condition]={'profile':profile,'case':case,'cm':cm,'budget_cm':budget_cm,'seq':0,'stopped':False}


    async def turn(self,arm,*,prompt,session_id,remaining):
        condition=arm['condition'];self._start(condition);state=self.states[condition]
        if state['stopped']: raise ValueError('worker_already_stopped')
        profile=state['profile'];db=profile/'data/opencode/opencode.db'
        before=prior_sequence(db,session_id)
        index=state['seq'];state['seq']+=1
        env={'PATH':'/usr/bin:/bin','HOME':str(profile/'home'),'XDG_CONFIG_HOME':str(profile/'config'),
             'XDG_DATA_HOME':str(profile/'data'),'XDG_CACHE_HOME':str(profile/'cache'),'XDG_STATE_HOME':str(profile/'state'),'LANG':'C.UTF-8','TERM':'dumb'}
        for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy'):
            if name in os.environ: env[name]=os.environ[name]
        env['NO_PROXY']=env.get('NO_PROXY','')+',127.0.0.1,localhost'
        env['no_proxy']=env.get('no_proxy',env['NO_PROXY'])+',127.0.0.1,localhost'
        # run_turn exclusively creates its files; restrictive umask preserves that contract.
        os.umask(0o077)
        cli_started=time.monotonic()
        receipt=await run_turn(executable=self.binary,workspace=state['case'],model='nebius/'+MODEL,prompt=prompt,
                              environment=env,stdout_path=profile/f'turn-{index}.jsonl',stderr_path=profile/f'turn-{index}.stderr',
                              deadline=time.monotonic()+remaining['active_seconds'],session_id=session_id,standalone=True,
                              agent='paired',terminal_database=db)
        cli_seconds=time.monotonic()-cli_started
        usage={'calls':0,'input_tokens':0,'output_tokens':0}
        with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
            for (data,) in conn.execute("SELECT data FROM session_message WHERE session_id=? AND seq>? AND type='assistant' ORDER BY seq",(receipt.session_id,before)):
                row=json.loads(data);tokens=row.get('tokens',{});model=row.get('model',{})
                if model.get('providerID')!='nebius' or model.get('id')!=MODEL: raise ValueError('worker_model_changed')
                values=[tokens.get('input'),tokens.get('output'),tokens.get('reasoning'),tokens.get('cache',{}).get('read'),tokens.get('cache',{}).get('write')]
                if any(type(v) is not int or v<0 for v in values): raise ValueError('worker_usage_unproven')
                usage['calls']+=1;usage['input_tokens']+=values[0]+values[3]+values[4];usage['output_tokens']+=values[1]+values[2]
        remote=self.remotes[condition]
        check=remote.run('python -m unittest discover -s tests -p test_smoke.py')
        public_check={'command':'python -m unittest discover -s tests -p test_smoke.py','exit_code':check['exit_code'],
                      'output':(check['stdout']+'\n'+check['stderr'])[:8000]}
        public_check['receipt_sha256']=hashlib.sha256(json.dumps(public_check,sort_keys=True).encode()).hexdigest()
        diff=remote.run('git diff -- .; git status --short')
        observation={'assistant_final':'\n'.join(receipt.messages)[-16000:],'public_check':public_check,
                     'public_diff':diff['stdout'][:16000],'receipt_sha256':receipt.stdout_sha256}
        return {'session_id':receipt.session_id,'receipt':asdict(receipt),'usage':usage,
                'terminal':'natural_stop','public_observation':observation,'worker_active_seconds':cli_seconds}

    async def stop(self,arm):
        if arm['condition'] not in self.states: return
        state=self.states[arm['condition']]
        if not state['stopped']:
            state['stopped']=True
            try: state['cm'].__exit__(None,None,None)
            finally: state['budget_cm'].__exit__(None,None,None)
        # Remote background processes are NOT proven quiescent by MCP revocation.
        # The isolated protected grader must enforce its own post-stop boundary.

    async def cleanup(self):
        for condition,state in self.states.items():
            if not state['stopped']: await self.stop({'condition':condition})
        self.pool.close()
