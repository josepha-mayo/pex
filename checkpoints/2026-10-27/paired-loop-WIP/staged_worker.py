"""WIP staged production-compatible worker composition; LIVE ENTRY CLOSED.

Reuses the pinned real CLI and raw funding receipts. Remote provisioning is an
injected separately admitted lifecycle, not implemented/authorized here. Local
fakes qualify integration; an authored mode label is never live permission.
"""
import asyncio
import json
import time
from pathlib import Path
from staged_envelope import PHASES, SETUP_SECONDS, OBSERVATION_SECONDS, GRADE_MAX_SECONDS
from staged_funding import PhaseFunding
import nebius_worker
from staged_controller import ProtocolInconclusive


class StagedWorker:
    def __init__(self, worker, lifecycle, *, mode='authored-only', clock=time.monotonic):
        if mode=='closed-admitted':
            binding=getattr(worker,'staged_binding',None)
            if binding is None or getattr(getattr(lifecycle,'api',None),'binding',None) is not binding:
                raise PermissionError('closed_staged_worker_lifecycle_binding_required')
            binding._check()
        elif mode!='authored-only' or getattr(worker,'staged_binding',None) is not None:
            raise PermissionError('staged_worker_live_admission_unimplemented')
        self.mode=mode
        if set(worker.funding) != {'baseline','pex'} or any(type(f) is not PhaseFunding for f in worker.funding.values()):
            raise ValueError('trusted_phase_funding_required')
        self.worker=worker;self.lifecycle=lifecycle;self.clock=clock
        self.remotes={};self.deadlines={};self.receipts={};self.released=set();self.unconfirmed=set()

    async def prepare(self, arm, *, deadline):
        c=arm['condition']
        if c not in ('baseline','pex') or c in self.remotes:
            raise ValueError('single_fresh_arm_prepare_required')
        remote=await self.lifecycle.prepare(arm,deadline=deadline)
        self.remotes[c]=remote;self.deadlines[c]=deadline
        if remote.vm_deadline != deadline:
            raise ProtocolInconclusive('unchanged_VM_deadline_required')
        self.worker.remotes[c]=remote
        remote.set_scope_deadline(min(deadline,self.clock()+SETUP_SECONDS))
        try:
            await asyncio.to_thread(self.worker._start,c)
        finally:
            await remote.end_scope()

    def _phase_config(self, condition, index):
        state=self.worker.states[condition];limit=PHASES[index]
        config=state['case']/'opencode.json'
        value=json.loads(config.read_text())
        value['agents']['paired']['steps']=limit.calls
        config.write_text(json.dumps(value))
        cfg={'baseURL':nebius_worker.BASE,'endpoint':nebius_worker.BASE+'/chat/completions','model':nebius_worker.MODEL,
             'funding':state['funding_channel'],'maxCalls':12,'outputPerCall':getattr(self.worker,'output_per_call',4096),
             'maxResponseBytes':self.worker.funding[condition].max_response_bytes,
             'keyPath':self.worker.key_path,'phaseCalls':limit.calls}
        source=Path(__file__).with_name('staged_nebius_guard.ts').read_text()
        (state['case']/'plugins/guard/index.ts').write_text(source.replace('CONFIGURATION',json.dumps(cfg)))

    async def phase(self, arm, *, prompt, session_id, phase_index, limit):
        c=arm['condition']
        if c not in self.remotes or type(phase_index) is not int or phase_index not in (0,1) or limit != PHASES[phase_index]:
            raise ValueError('exact_frozen_prepared_phase_required')
        remote=self.remotes[c];funding=self.worker.funding[c]
        funding.begin(phase_index)
        remote.set_scope_deadline(min(self.deadlines[c],self.clock()+limit.active_seconds))
        failed=False
        try:
            self._phase_config(c,phase_index)
            result=await self.worker.execute_cli(arm,prompt=prompt,session_id=session_id,
                                               remaining={'active_seconds':limit.active_seconds})
            delta=funding.finish(natural_stop=result.get('terminal')=='natural_stop')
            if any(delta[k] != result['usage'][k] for k in ('calls','input_tokens','output_tokens')):
                raise ProtocolInconclusive('CLI_and_raw_ledger_usage_disagree')
            receipt=result.pop('_terminal_receipt')
            self.receipts[c]=(result['receipt'],receipt,phase_index)
            result['phase_stop_policy']='counted_forced_textual_finalization_not_task_completion'
            return result
        except BaseException:
            failed=True;funding.abort();raise
        finally:
            try: await remote.end_scope()
            except BaseException:
                self.unconfirmed.add(c)
                if not failed: raise

    async def observe(self, arm, turn):
        c=arm['condition']
        saved=self.receipts.get(c)
        if saved is None or saved[0] != turn['receipt'] or saved[2] != 0:
            raise ProtocolInconclusive('fresh_first_phase_observation_required')
        remote=self.remotes[c]
        remote.set_scope_deadline(min(self.deadlines[c],self.clock()+OBSERVATION_SECONDS))
        try:
            return await asyncio.to_thread(self.worker.collect_observation,arm,saved[1])
        finally:
            await remote.end_scope()

    async def stop(self, arm):
        c=arm['condition']
        if c not in self.remotes: return
        error=None
        try: await self.remotes[c].end_scope()
        except Exception as exc: error=exc;self.unconfirmed.add(c)
        self.worker.funding[c].abort()
        # Existing stop revokes private MCP/funding servers synchronously; keep
        # that work off the owner loop used by pending async SDK cancellations.
        await asyncio.to_thread(lambda:asyncio.run(self.worker.stop(arm)))
        if error is not None: raise error

    async def release(self, arm):
        c=arm['condition']
        if c not in self.remotes or c in self.released: return
        await self.remotes[c].close()
        if self.remotes[c].closed is not True:
            raise ProtocolInconclusive('owned_VM_release_unconfirmed')
        self.released.add(c)
        if c in self.unconfirmed or getattr(self.remotes[c],'cancellation_unconfirmed',False):
            raise ProtocolInconclusive('VM_stopped_but_operation_cancellation_unconfirmed')

    async def cleanup(self):
        errors=[]
        for c in self.remotes:
            if c in self.released: continue
            try: await self.stop({'condition':c})
            except Exception: errors.append(c)
            try: await self.release({'condition':c})
            except Exception: errors.append(c)
        cleanup=getattr(self.lifecycle,'cleanup',None)
        if callable(cleanup):
            try: await cleanup()
            except Exception: errors.append('lifecycle')
        if errors: raise ProtocolInconclusive('staged_owned_cleanup_unconfirmed')


class StagedGrade:
    """Same post-stop protected grader, with the remaining VM wall deadline."""
    def __init__(self, grade, worker): self.grade_impl=grade;self.worker=worker;self.wall_deadlines={}
    def reserve_wall(self,arm,*,deadline):
        c=arm['condition'];now=self.worker.clock()
        if (c in self.wall_deadlines or type(deadline) not in (int,float)
                or not now<deadline<=min(self.worker.deadlines[c],now+GRADE_MAX_SECONDS)):
            raise ProtocolInconclusive('single_absolute_grade_window_required')
        self.wall_deadlines[c]=deadline
    async def grade(self, arm):
        c=arm['condition'];remote=self.worker.remotes[c]
        deadline=self.wall_deadlines.pop(c,None)
        if deadline is None:raise ProtocolInconclusive('controller_grade_window_required')
        remote.set_scope_deadline(min(self.worker.deadlines[c],deadline))
        try: return await self.grade_impl.grade(arm)
        finally: await remote.end_scope()
