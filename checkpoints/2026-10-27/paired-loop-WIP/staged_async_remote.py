"""WIP async-SDK bridge for an ALREADY owned VM; no create/key/admission code.

Synchronous MCP/grader threads submit cancellable async SDK operations to the
owner loop. Every operation shares the current stage and immutable VM deadline.
Cancellation ambiguity poisons the bridge; only owned-resource cleanup remains.
Local fakes qualify the contract, not actual provider cancellation behavior.
"""
import asyncio
import concurrent.futures
from datetime import datetime
import inspect
import math
import shlex
import threading
import time
from types import SimpleNamespace
from e2b_transport import ROOT, MAX_BYTES, BASE_TEMPLATE, EXPECTED_ALLOCATION, path
from staged_envelope import VM_SECONDS


class BoundedRemoteError(RuntimeError):
    pass


def validate_provider_lifetime(info):
    """Full provider lifetime, including idle/review time; never discount pauses."""
    start,end=info.started_at,info.end_at
    if (type(start) is not datetime or type(end) is not datetime
            or start.tzinfo is None or end.tzinfo is None
            or not 0 < (end-start).total_seconds() <= VM_SECONDS
            or type(info.cpu_count) is not int or type(info.memory_mb) is not int
            or (info.cpu_count,info.memory_mb) != EXPECTED_ALLOCATION
            or info.template_id != BASE_TEMPLATE):
        raise BoundedRemoteError('provider_lifetime_or_allocation_unproven')
    return {'provider_lifetime_seconds':(end-start).total_seconds(),
            'admitted_full_lifetime_seconds':VM_SECONDS,'paused_time_discounted':False}


class BoundedAsyncRemote:
    def __init__(self, sandbox, *, vm_deadline, clock=time.monotonic):
        if type(vm_deadline) not in (int,float) or not math.isfinite(vm_deadline) or vm_deadline <= clock():
            raise ValueError('future_finite_VM_deadline_required')
        self._sdk=sandbox;self.clock=clock;self.vm_deadline=vm_deadline
        self.loop=asyncio.get_running_loop();self.owner_thread=threading.get_ident()
        self.deadline=None;self.poisoned=False;self.closed=False;self.active=set()
        self.cancellation_unconfirmed=False;self.cleanup_evidence={}
        self._sandbox=SimpleNamespace(files=SimpleNamespace(make_dir=self._make_dir,write=self._write_absolute))

    def set_scope_deadline(self, deadline):
        if self.closed or self.poisoned or self.active or self.deadline is not None:
            raise BoundedRemoteError('scope_not_clean')
        if type(deadline) not in (int,float) or not math.isfinite(deadline) or not self.clock() < deadline <= self.vm_deadline:
            raise BoundedRemoteError('stage_outside_VM_lifetime')
        self.deadline=deadline

    def remaining(self):
        if self.closed or self.poisoned or self.deadline is None:
            raise BoundedRemoteError('remote_scope_closed_or_uncertain')
        remaining=min(self.deadline,self.vm_deadline)-self.clock()
        if remaining <= 0: raise BoundedRemoteError('remote_deadline_exhausted')
        return remaining

    def _track(self, task):
        self.active.add(task)
        def done(value):
            self.active.discard(value)
            if not value.cancelled(): value.exception()  # Consume late failures.
        task.add_done_callback(done)
        return task

    async def _invoke(self, factory):
        # wait_for waits for cancellation to finish and therefore is not a hard
        # return bound when an SDK suppresses cancellation. Track the underlying
        # task separately and retain ambiguity instead of awaiting it forever.
        timeout=self.remaining()
        task=self._track(asyncio.create_task(factory()))
        try:
            done,_=await asyncio.wait([task],timeout=timeout)
            if not done: raise TimeoutError('SDK_stage_deadline')
            return task.result()
        except BaseException:
            task.cancel();self.poisoned=True
            raise

    def _call(self, factory):
        if threading.get_ident()==self.owner_thread:
            raise BoundedRemoteError('blocking_SDK_bridge_on_owner_loop_forbidden')
        timeout=self.remaining()
        future=asyncio.run_coroutine_threadsafe(self._invoke(factory),self.loop)
        try:
            return future.result(timeout=timeout)
        except BaseException:
            future.cancel();self.poisoned=True
            raise BoundedRemoteError('remote_operation_inconclusive') from None

    async def end_scope(self):
        self.deadline=None  # Revoke new thread submissions before cancellation.
        tasks=list(self.active)
        for task in tasks: task.cancel()
        if tasks:
            _,pending=await asyncio.wait(tasks,timeout=max(0,min(1,self.vm_deadline-self.clock())))
            if pending:
                self.poisoned=True;self.cancellation_unconfirmed=True
                raise BoundedRemoteError('SDK_cancellation_unconfirmed')

    def run(self, command, timeout=60):
        if type(command) is not str or not command or len(command)>32768 or '\0' in command:
            raise ValueError('invalid_remote_command')
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=120:
            raise ValueError('invalid_command_timeout')
        async def execute():
            limit=min(timeout,self.remaining());size=0;output={'stdout':[],'stderr':[]}
            def capture(stream):
                def take(chunk):
                    nonlocal size
                    size+=len(chunk.encode())
                    if size>MAX_BYTES: raise BoundedRemoteError('remote_output_bound')
                    output[stream].append(chunk)
                return take
            command_line=f'timeout --signal=TERM --kill-after=1s {limit}s bash -lc {shlex.quote(command)}'
            handle=None
            try:
                handle=await self._sdk.commands.run(command_line,cwd=ROOT,user='user',background=True,
                    on_stdout=capture('stdout'),on_stderr=capture('stderr'),timeout=limit,
                    request_timeout=min(15,self.remaining()))
                try: result=await handle.wait()
                except Exception as error:
                    from e2b import CommandExitException
                    if not isinstance(error,CommandExitException): raise
                    result=error
                return dict(stdout=''.join(output['stdout']),stderr=''.join(output['stderr']),exit_code=result.exit_code)
            finally:
                if handle is not None:
                    left=min(self.vm_deadline,self.deadline or self.vm_deadline)-self.clock()
                    if left>0:
                        try: await asyncio.wait_for(handle.kill(),timeout=min(1,left))
                        except BaseException: self.poisoned=True
        return self._call(execute)

    def read(self, relative):
        async def read_all():
            reader=await self._sdk.files.read(path(relative),format='stream',user='user',request_timeout=min(15,self.remaining()))
            chunks=[];size=0
            try:
                async for chunk in reader:
                    size+=len(chunk)
                    if size>MAX_BYTES: raise BoundedRemoteError('file_size_bound')
                    chunks.append(bytes(chunk))
                return b''.join(chunks).decode()
            finally:
                await reader.aclose()
        return self._call(read_all)

    def _write_absolute(self, name, content, *, user='user', request_timeout=15):
        if user!='user' or not isinstance(content,(str,bytes)) or len(content.encode() if isinstance(content,str) else content)>MAX_BYTES:
            raise ValueError('bounded_user_file_required')
        return self._call(lambda:self._sdk.files.write(name,content,user=user,request_timeout=min(15,self.remaining())))

    def _make_dir(self, name, *, user='user', request_timeout=15):
        if user!='user': raise ValueError('unprivileged_user_required')
        return self._call(lambda:self._sdk.files.make_dir(name,user=user,request_timeout=min(15,self.remaining())))

    def write(self, relative, content):
        self._write_absolute(path(relative),content)
        return {'written':relative,'bytes':len(content.encode())}

    def list(self, relative='.'):
        rows=self._call(lambda:self._sdk.files.list(path(relative),depth=1,user='user',request_timeout=min(15,self.remaining())))
        if len(rows)>1024: raise BoundedRemoteError('directory_bound')
        return [{'name':r.name,'type':str(r.type)} for r in rows]

    async def close(self):
        if self.closed: return
        scope_error=None
        try:
            await self.end_scope()
        except BoundedRemoteError as error:
            # A stuck operation must NEVER prevent an independent owned-VM kill.
            scope_error=type(error).__name__
        left=self.vm_deadline-self.clock()
        self.cleanup_evidence={'cancellation_unconfirmed':self.cancellation_unconfirmed,
                               'scope_error':scope_error,'kill_attempted':False,'stopped_confirmed':False}
        if left<=0: raise BoundedRemoteError('cleanup_deadline_exhausted_not_confirmed')
        async def cleanup():
            self.cleanup_evidence['kill_attempted']=True
            await self._sdk.kill(request_timeout=min(15,self.vm_deadline-self.clock()))
            remaining=self.vm_deadline-self.clock()
            if remaining<=0: raise BoundedRemoteError('cleanup_confirmation_deadline_exhausted')
            if await self._sdk.is_running(request_timeout=min(15,remaining)) is not False:
                raise BoundedRemoteError('owned_VM_cleanup_unconfirmed')
            self.cleanup_evidence['stopped_confirmed']=True
        task=self._track(asyncio.create_task(cleanup()))
        try:
            done,_=await asyncio.wait([task],timeout=left)
            if not done: raise BoundedRemoteError('cleanup_return_deadline_exhausted')
            task.result()
        except BaseException:
            task.cancel();self.poisoned=True
            raise
        self.closed=True  # Independent stop confirmation, not cancellation success.
