"""Separate Vercel native-MCP route. No E2B authority or identity reuse. WIP."""
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
from opencode_cli import CliCleanupUnconfirmed, run_turn
from opencode_v2_receipt import prior_sequence
from remote_mcp import serve_remote
from controller import PublicEvidenceInfrastructureError
from budget_rpc import serve_budget
from worker_funding import WorkerFunding,WorkerBudgetExhausted
from controller import WorkerBudgetTerminal

PIN='ca9b3ee262e33bb4e7aa0e1230dc61086a474c8c8016b980081d0719712fd2e7'
MODEL='deepseek-ai/DeepSeek-V4.1-Flash-1017'
BASE='https://api.tokenfactory.nebius.com/v1'
TOOLS=['pex_remote_run','pex_remote_read','pex_remote_write','pex_remote_list']


def raise_funding_terminal(channel,*,usage=None,worker_active_seconds=None):
    error=getattr(channel,'last_error',None)
    if isinstance(error,WorkerBudgetExhausted):
        raise WorkerBudgetTerminal(error.code,usage=usage,
                                  worker_active_seconds=worker_active_seconds) from error


def funding_usage_delta(before,after):
    if before is None or after is None: return None
    fields={'calls','input_tokens','output_tokens','uncertain_calls'}
    if (set(before)!=fields or set(after)!=fields
            or any(type(v) is not int or v < 0 for obj in (before,after) for v in obj.values())):
        raise ValueError('invalid_funding_usage_snapshot')
    delta={k:after[k]-before[k] for k in fields}
    if any(v < 0 for v in delta.values()) or delta['uncertain_calls'] > delta['calls']:
        raise ValueError('funding_usage_snapshot_regressed')
    return delta

class NebiusCLIWorker:
    def __init__(self, *, remotes, private_root, binary, modules, key_path, pool,
                 max_calls=12, output_per_call=None, activate=False, funding=None, authored=False,
                 public_check_command="python -m unittest discover -s tests -p test_smoke.py", task_profile="legacy-task05", vercel_binding=None, capture_public_snapshot=False):
        if vercel_binding is None or task_profile!='wirepool-v1':raise PermissionError('separate_vercel_wirepool_binding_required')
        if task_profile not in ("legacy-task05","stockroom-v1","asyncpool-v1","wirepool-v1"):raise ValueError("frozen_task_profile_required")
        if task_profile in ("stockroom-v1","asyncpool-v1","wirepool-v1") and public_check_command!="python -m unittest discover -s tests -v":raise ValueError("stockroom_public_check_required")
        if type(capture_public_snapshot)is not bool or (capture_public_snapshot and task_profile not in ('stockroom-v1','asyncpool-v1','wirepool-v1')):raise ValueError('explicit_public_snapshot_profile_required')
        self.capture_public_snapshot=capture_public_snapshot
        self.public_checkpoints={}
        self.task_profile=task_profile
        if public_check_command not in ("python -m unittest discover -s tests -p test_smoke.py", "python -m unittest discover -s tests -v"):
            raise ValueError("frozen_public_check_command_required")
        self.public_check_command = public_check_command
        if activate is not True: raise PermissionError('pilot_not_activated')
        if set(funding or {})!={'baseline','pex'}: raise PermissionError('worker_funding_required')
        self.vercel_binding=vercel_binding
        if vercel_binding is not None:
            if authored or BASE!='https://api.tokenfactory.nebius.com/v1' or task_profile not in ('stockroom-v1','asyncpool-v1','wirepool-v1'):
                raise PermissionError('closed_vercel_worker_exact_route_required')
            from vercel_worker_admission import validate_worker
            cfg=validate_worker(vercel_binding,funding,private_root=private_root,binary=binary,modules=modules,key_path=key_path)
            from asyncpool_adapter import MANIFEST_SHA256 as ASYNCPOOL_MANIFEST
            from wirepool_adapter import MANIFEST_SHA256 as WIREPOOL_MANIFEST
            if (task_profile=='asyncpool-v1')!=(cfg['task']['sha256']==ASYNCPOOL_MANIFEST) or (task_profile=='wirepool-v1')!=(cfg['task']['sha256']==WIREPOOL_MANIFEST):raise PermissionError('task_profile_manifest_mismatch')
            if capture_public_snapshot is not cfg['profile'].get('public_snapshot_inspection',False):raise PermissionError('frozen_public_snapshot_profile_required')
            expected_output=cfg['profile']['worker_output_per_call']
            if output_per_call is None:output_per_call=expected_output
            if type(output_per_call)is not int or output_per_call!=expected_output:
                raise PermissionError('frozen_vercel_worker_output_required')
            from vercel_worker_admission import prepare_child_environment
            # Same production projection is checked locally BEFORE any VM.
            for arm in ('baseline','pex'):prepare_child_environment(cfg,Path(private_root)/arm)
        elif task_profile in ('asyncpool-v1','wirepool-v1'):raise PermissionError('asyncpool_requires_new_staged_admission')
        elif authored:
            if not BASE.startswith('http://127.0.0.1:'): raise PermissionError('authored_loopback_only')
        elif any(type(v) is not WorkerFunding for v in funding.values()):
            raise PermissionError('independently_admitted_worker_funding_required')
        if output_per_call is None:output_per_call=4096
        if (type(output_per_call)is not int or output_per_call not in (4096,16384)
                or any(getattr(v,'output_token_bound',4096)!=output_per_call for v in funding.values())):
            raise ValueError('worker_output_funding_profile_mismatch')
        if output_per_call==16384 and vercel_binding is None and not authored:
            raise PermissionError('new_output_profile_requires_closed_vercel_binding')
        self.funding=funding
        self.binary=Path(binary).resolve();self.modules=Path(modules).resolve()
        if hashlib.sha256(self.binary.read_bytes()).hexdigest()!=PIN: raise ValueError('CLI_identity_changed')
        if json.loads((self.modules/'@opencode/plugin/package.json').read_text())['version']!='2.1.4': raise ValueError('plugin_identity_changed')
        key_path=Path(key_path)
        if key_path.is_symlink() or key_path.stat().st_mode&0o077: raise ValueError('private_key_permissions')
        key=key_path.read_text().strip()
        if not key: raise ValueError('empty_key')
        if set(remotes)!={'baseline','pex'} or max_calls!=12: raise ValueError('fixed_pilot_envelope')
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
        # Retain ownership before each entered context. Startup errors must not
        # leave private MCP/budget servers invisible to stop()/cleanup().
        state={'profile':profile,'case':case,'seq':0,'stopped':False,
               'remote_entered':False,'budget_entered':False,'startup_complete':False}
        self.states[condition]=state
        try:
            cm=serve_remote(remote,profile/'rpc');state['cm']=cm;state['remote_enter_attempted']=True
            sock=cm.__enter__();state['remote_entered']=True
            budget_cm=serve_budget(self.funding[condition]);state['budget_cm']=budget_cm;state['budget_enter_attempted']=True
            funding_rpc=budget_cm.__enter__();state['budget_entered']=True
            cfg={'baseURL':BASE,'endpoint':BASE+'/chat/completions','model':MODEL,'funding':funding_rpc,
                 'maxCalls':self.max_calls,'outputPerCall':self.output_per_call,
                 'maxResponseBytes':getattr(self.funding[condition],'max_response_bytes',2*1024*1024),'keyPath':self.key_path}
            guard=Path(__file__).with_name('nebius_guard.ts').read_text().replace('CONFIGURATION',json.dumps(cfg))
            (case/'plugins/guard/index.ts').write_text(guard)
            conf={'update':'disable','warming':False,'share':'disabled','model':'nebius/'+MODEL,'default_agent':'paired','plugins':['./plugins/guard'],
                  'mcp':{'servers':{'pex_remote':{'type':'local','command':['/usr/bin/python3',str(Path(__file__).with_name('remote_mcp.py').resolve()),'--socket',str(sock)],'codemode':False,'protocol':'legacy','timeout':{'startup':10000,'catalog':10000,'execution':65000}}}},
                  'policies':[{'action':'provider.use','resource':'*','effect':'deny'},{'action':'provider.use','resource':'nebius','effect':'allow'},
                              {'action':'tool.use','resource':'*','effect':'deny'}]+[{'action':'tool.use','resource':n+':*','effect':'allow'} for n in TOOLS],
                  'providers':{'nebius':{'package':'@opencode/ai/providers/openai-compatible','settings':{'baseURL':BASE,'apiKey':'PEX-INERT-NONSECRET-NOT-A-KEY','provider':'nebius','transport':'http','encoding':'none'},'models':{MODEL:{'modelID':MODEL,'body':{'max_completion_tokens':self.output_per_call,'stream_options':{'include_usage':True}},'capabilities':{'tools':True,'input':['text'],'output':['text']}}}}},
                  'agents':{'paired':{'mode':'primary','model':'nebius/'+MODEL,'steps':self.max_calls,
                      'system':'Work on the user task autonomously using only pex_remote tools. All task files and commands belong to that isolated remote workspace, not this controller. Do not use local tools.',
                      'permissions':[{'action':'*','resource':'*','effect':'deny'}]+[{'action':n,'resource':'*','effect':'allow'} for n in TOOLS]}}}
            config=case/'opencode.json';config.write_text(json.dumps(conf));config.chmod(0o600)
            state['funding_channel']=funding_rpc;state['startup_complete']=True
        except BaseException:
            state['startup_failed']=True
            try:self._stop_state(state)
            except BaseException:pass  # Flags retain unconfirmed custody; preserve original setup error.
            raise

    @staticmethod
    def _stop_state(state):
        if state.get('stopped'):
            if state.get('local_cleanup_unconfirmed'):raise RuntimeError('local_worker_cleanup_unconfirmed')
            return
        state['stopped']=True
        errors=[]
        for name,entered,attempted,confirmed in (
                ('cm','remote_entered','remote_enter_attempted','mcp_revoked'),
                ('budget_cm','budget_entered','budget_enter_attempted','funding_revoked')):
            cm=state.get(name)
            if state.get(entered,cm is not None):
                try:cm.__exit__(None,None,None);state[confirmed]=True
                except BaseException as error:state[confirmed]=False;errors.append(type(error).__name__)
            else:
                state[confirmed]=not state.get(attempted,False)
                if not state[confirmed]:errors.append('context_enter_unconfirmed')
        state['local_cleanup_unconfirmed']=bool(errors)
        if errors:
            state['local_cleanup_error_types']=errors
            raise RuntimeError('local_worker_cleanup_unconfirmed')



    async def turn(self,arm,*,prompt,session_id,remaining):
        result=await self.execute_cli(arm,prompt=prompt,session_id=session_id,remaining=remaining)
        receipt=result.pop('_terminal_receipt')
        result['public_observation']=self.collect_observation(arm,receipt)
        return result

    async def execute_cli(self,arm,*,prompt,session_id,remaining):
        """CLI-only measured phase; staged orchestration collects public evidence later."""
        condition=arm['condition'];self._start(condition);state=self.states[condition]
        if state['stopped']: raise ValueError('worker_already_stopped')
        profile=state['profile'];db=profile/'data/opencode/opencode.db'
        before=prior_sequence(db,session_id)
        index=state['seq'];state['seq']+=1
        env={'PATH':'/usr/bin:/bin','HOME':str(profile/'home'),'XDG_CONFIG_HOME':str(profile/'config'),
             'XDG_DATA_HOME':str(profile/'data'),'XDG_CACHE_HOME':str(profile/'cache'),'XDG_STATE_HOME':str(profile/'state'),'LANG':'C.UTF-8','TERM':'dumb'}
        env.update({'OPENCODE_DISABLE_MODELS_FETCH':'1','OPENCODE_DISABLE_AUTOUPDATE':'1','OPENCODE_DISABLE_FREE_MODELS':'1'})
        for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy'):
            if name in os.environ: env[name]=os.environ[name]
        env['NO_PROXY']=env.get('NO_PROXY','')+',127.0.0.1,localhost'
        env['no_proxy']=env.get('no_proxy',env['NO_PROXY'])+',127.0.0.1,localhost'
        if self.vercel_binding is not None:
            from vercel_worker_admission import bind_child_environment
            from vercel_worker_admission import prepare_child_environment
            env=prepare_child_environment(self.vercel_binding.admitted.config(),profile)
            env=bind_child_environment(self.vercel_binding,env)
        # run_turn exclusively creates its files; restrictive umask preserves that contract.
        os.umask(0o077)
        funding=getattr(self,'funding',{}).get(condition)
        snapshot=getattr(funding,'usage_snapshot',None)
        usage_before=snapshot() if callable(snapshot) else None
        cli_started=time.monotonic()
        try:
            receipt=await run_turn(executable=self.binary,workspace=state['case'],model='nebius/'+MODEL,prompt=prompt,
                                  environment=env,stdout_path=profile/f'turn-{index}.jsonl',stderr_path=profile/f'turn-{index}.stderr',
                                  deadline=time.monotonic()+remaining['active_seconds'],session_id=session_id,standalone=True,
                                  agent='paired',terminal_database=db)
        except CliCleanupUnconfirmed:
            # Never hide uncertain process ownership behind an earlier funding
            # refusal. Staged orchestration must stop before the next VM.
            raise
        except Exception:
            elapsed=time.monotonic()-cli_started
            channel=state['funding_channel']
            if isinstance(getattr(channel,'last_error',None),WorkerBudgetExhausted):
                usage_after=snapshot() if callable(snapshot) else None
                raise_funding_terminal(channel,usage=funding_usage_delta(usage_before,usage_after),
                                       worker_active_seconds=elapsed)
            raise
        cli_seconds=time.monotonic()-cli_started
        usage={'calls':0,'input_tokens':0,'output_tokens':0}
        with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
            for (data,) in conn.execute("SELECT data FROM session_message WHERE session_id=? AND seq>? AND type='assistant' ORDER BY seq",(receipt.session_id,before)):
                row=json.loads(data);tokens=row.get('tokens',{});model=row.get('model',{})
                if model.get('providerID')!='nebius' or model.get('id')!=MODEL: raise ValueError('worker_model_changed')
                values=[tokens.get('input'),tokens.get('output'),tokens.get('reasoning'),tokens.get('cache',{}).get('read'),tokens.get('cache',{}).get('write')]
                if any(type(v) is not int or v<0 for v in values): raise ValueError('worker_usage_unproven')
                usage['calls']+=1;usage['input_tokens']+=values[0]+values[3]+values[4];usage['output_tokens']+=values[1]+values[2]
        return {'session_id':receipt.session_id,'receipt':asdict(receipt),'usage':usage,
                'terminal':'natural_stop','worker_active_seconds':cli_seconds,'_terminal_receipt':receipt}

    def collect_observation(self,arm,receipt):
        remote=self.remotes[arm['condition']]
        if getattr(self,'task_profile','legacy-task05') in ('stockroom-v1','asyncpool-v1','wirepool-v1'):
            if self.task_profile=='wirepool-v1':
                from wirepool_request import collect_public_observation
            elif self.task_profile=='asyncpool-v1':
                from asyncpool_request import collect_public_observation
            else:
                from stockroom_request import collect_public_observation
            def capture(export,snapshot):
                if arm['condition'] in self.public_checkpoints:raise ValueError('single_first_phase_public_checkpoint_required')
                item={'schema':'pex.public-pre-intervention-checkpoint.v1','condition':arm['condition'],
                      'capture_boundary':'after_phase0_before_monitor_before_any_protected_upload',
                      'public_export':export,'snapshot_sha256':snapshot['snapshot_sha256']}
                if self.vercel_binding is not None:
                    from vercel_composition import private_atomic_json
                    item['config_sha256']=self.vercel_binding.admitted.grant.config_sha256
                    item['durable_pin']=private_atomic_json(self.root.parent/'evidence'/(arm['condition']+'-public-checkpoint.json'),item,limit=512*1024)
                self.public_checkpoints[arm['condition']]=item
            observation=collect_public_observation(remote,receipt,capture_public_snapshot=getattr(self,'capture_public_snapshot',False),snapshot_sink=capture)
            return observation
        command=getattr(self,'public_check_command','python -m unittest discover -s tests -p test_smoke.py')
        check=remote.run(command)
        if type(check.get('exit_code')) is not int or check['exit_code'] not in (0,1):
            raise PublicEvidenceInfrastructureError('public_check_non_test_terminal')
        public_check={'command':command,'exit_code':check['exit_code'],
                      'output':(check['stdout']+'\n'+check['stderr'])[:8000]}
        public_check['receipt_sha256']=hashlib.sha256(json.dumps(public_check,sort_keys=True).encode()).hexdigest()
        diff=remote.run('git diff -- . && git status --short')
        if type(diff.get('exit_code')) is not int or diff['exit_code']!=0:
            raise PublicEvidenceInfrastructureError('public_diff_failed')
        observation={'assistant_final':'\n'.join(receipt.messages)[-16000:],'public_check':public_check,
                     'public_diff':diff['stdout'][:16000],'receipt_sha256':receipt.stdout_sha256}
        return observation

    async def stop(self,arm):
        if arm['condition'] not in self.states: return
        self._stop_state(self.states[arm['condition']])
        # Remote background processes are NOT proven quiescent by MCP revocation.
        # The isolated protected grader must enforce its own post-stop boundary.

    async def cleanup(self):
        errors=[]
        for condition in self.states:
            try:await self.stop({'condition':condition})
            except Exception as error:errors.append(type(error).__name__)
        try:self.pool.close()
        except Exception as error:errors.append(type(error).__name__)
        if errors:raise RuntimeError('local_worker_cleanup_unconfirmed')
