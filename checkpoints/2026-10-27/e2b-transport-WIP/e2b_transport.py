"""WIP E2B transport only; no provider/model calls, CLI, grader or credentials in VM.

Inject e2b.Sandbox from pinned SDK 2.61.0. Caller owns explicit approval,
stdio MCP and protected evaluation. Never print API keys or SDK exceptions.
"""
from __future__ import annotations
from decimal import Decimal
from pathlib import PurePosixPath
import shlex
import uuid

ROOT = '/home/user/pex-task'
TIMEOUT = 330
MAX_BYTES = 262144
SDK_VERSION = '2.61.0'
BASE_TEMPLATE = 'rki5dems9wqfm4r03t7g'
CATALOG_BUILD_SNAPSHOT = '9bdf19ae-7960-412d-8518-aff4bcafb8bc'
EXPECTED_ALLOCATION = (2, 512)
CPU_SECOND = Decimal('0.000014')
GIB_SECOND = Decimal('0.0000045')
MAX_TOTAL = Decimal('0.10')
# Worst-case Hobby allocation: 8 vCPU + 8 GiB, even if base changes.
RESERVATION = Decimal('0.04884')

class TransportError(RuntimeError):
    pass


def path(value):
    if not isinstance(value, str) or '\x00' in value:
        raise TransportError('invalid public path')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts:
        raise TransportError('public path must be relative')
    return str(PurePosixPath(ROOT) / p)


class RemoteWorker:
    def __init__(self, sandbox, info):
        self._sandbox = sandbox
        self.info = info
        self.closed = False

    def _open(self):
        if self.closed:
            raise TransportError('worker closed')

    def run(self, command, timeout=60):
        self._open()
        if not isinstance(command, str) or not command or len(command) > 32768 or '\x00' in command:
            raise TransportError('invalid remote command')
        if type(timeout) not in (int, float) or not 0 < timeout <= 120:
            raise TransportError('invalid command timeout')
        output = {'stdout': [], 'stderr': []}
        total = 0
        def capture(stream):
            def append(chunk):
                nonlocal total
                total += len(chunk.encode('utf-8'))
                if total > MAX_BYTES:
                    raise TransportError('remote output bound exceeded')
                output[stream].append(chunk)
            return append
        handle = None
        try:
            # Command is interpreted only inside the isolated VM, never on host.
            wrapped = f'timeout --signal=TERM --kill-after=1s {timeout}s bash -lc {shlex.quote(command)}'
            handle = self._sandbox.commands.run(wrapped, cwd=ROOT, user='user', background=True,
                timeout=timeout+2, request_timeout=15)
            try:
                result = handle.wait(on_stdout=capture('stdout'), on_stderr=capture('stderr'))
            except Exception as error:
                from e2b import CommandExitException
                if not isinstance(error, CommandExitException):
                    raise
                result = error
            return {'stdout': ''.join(output['stdout']), 'stderr': ''.join(output['stderr']),
                    'exit_code': result.exit_code}
        except Exception as error:
            # SDK errors can contain request details; expose only stable classification.
            raise TransportError('remote command failed or exceeded bound') from None
        finally:
            if handle is not None:
                try:
                    handle.kill()
                except Exception:
                    pass  # VM lifetime/close remains the resource backstop.

    def read(self, relative):
        self._open()
        chunks, size = [], 0
        try:
            for chunk in self._sandbox.files.read(path(relative), format='stream', user='user', request_timeout=15):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise TransportError('remote file exceeds bound')
                chunks.append(bytes(chunk))
            return b''.join(chunks).decode('utf-8')
        except Exception:
            raise TransportError('remote public file read failed') from None

    def write(self, relative, content):
        self._open()
        if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_BYTES:
            raise TransportError('remote file exceeds bound')
        try:
            self._sandbox.files.write(path(relative), content, user='user', request_timeout=15)
        except Exception:
            raise TransportError('remote public file write failed') from None
        return {'written': relative, 'bytes': len(content.encode('utf-8'))}

    def list(self, relative='.'):
        self._open()
        try:
            rows = self._sandbox.files.list(path(relative), depth=1, user='user', request_timeout=15)
            if len(rows) > 1024:
                raise TransportError('remote directory exceeds bound')
            return [{'name': row.name, 'type': str(row.type)} for row in rows]
        except Exception:
            raise TransportError('remote public directory list failed') from None

    def close(self):
        if self.closed:
            return
        try:
            self._sandbox.kill(request_timeout=15)
            if self._sandbox.is_running(request_timeout=15):
                raise TransportError('sandbox still running')
            self.closed = True
        except Exception:
            raise TransportError('sandbox cleanup not confirmed; timeout remains backstop') from None


class PilotPool:
    """At most two create attempts, including ambiguous failures; never retry create.

    Failed create retains full reservation and marks pool uncertain. Reconcile by
    metadata through read-only list and kill, never reconnect/resume/recreate.
    """
    def __init__(self, sandbox_api, api_key, *, approved=False, cumulative_budget=None):
        self._api, self._key, self.approved = sandbox_api, api_key, approved
        self.run_id = 'pex-pilot-' + uuid.uuid4().hex
        self.attempts = 0
        self.workers = []
        self.arms = set()
        self.uncertain = False
        self.allocation = None
        self.cumulative_budget = cumulative_budget

    def create(self, arm):
        if not self.approved or self.uncertain:
            raise TransportError('live pilot not admitted')
        if arm not in ('baseline', 'supervised') or arm in self.arms or self.attempts >= 2:
            raise TransportError('pilot create bound exceeded')
        if RESERVATION * (self.attempts+1) > MAX_TOTAL:
            raise TransportError('compute reservation exceeded')
        reservation_id = self.run_id+'-'+arm
        if self.cumulative_budget is not None:
            self.cumulative_budget.reserve(reservation_id)
        self.attempts += 1
        self.arms.add(arm)
        sandbox = None
        try:
            sandbox = self._api.create(template=BASE_TEMPLATE, timeout=TIMEOUT,
                lifecycle={'on_timeout':'kill', 'auto_resume':False},
                metadata={'pex_pilot':self.run_id, 'pex_arm':arm},
                idempotency_key=self.run_id+'-'+arm, api_key=self._key,
                retries=0, request_timeout=30)
            info = sandbox.get_info(request_timeout=15)
            cpu, memory = info.cpu_count, info.memory_mb
            lifetime = (info.end_at-info.started_at).total_seconds()
            if type(cpu) is not int or type(memory) is not int or not 0 < cpu <= 8 or not 0 < memory <= 8192:
                raise TransportError('unapproved sandbox allocation')
            if not 0 < lifetime <= TIMEOUT:
                raise TransportError('unapproved sandbox lifetime')
            cost = TIMEOUT * (CPU_SECOND*cpu+GIB_SECOND*Decimal(memory)/1024)
            if cost > RESERVATION:
                raise TransportError('allocation exceeds compute reservation')
            allocation = (cpu, memory)
            if info.template_id != BASE_TEMPLATE or allocation != EXPECTED_ALLOCATION:
                raise TransportError('verified template/allocation changed')
            if self.allocation is not None and allocation != self.allocation:
                raise TransportError('paired allocations differ')
            self.allocation = allocation
            if self.cumulative_budget is not None:
                self.cumulative_budget.settle_verified_allocation(reservation_id, cpu=cpu, memory_mb=memory, max_seconds=TIMEOUT)
            sandbox.files.make_dir(ROOT, user='user', request_timeout=15)
            worker = RemoteWorker(sandbox, {'sandbox_id':info.sandbox_id, 'cpu':cpu,
                'memory_mb':memory, 'template_id':info.template_id,
                'catalog_build_snapshot':CATALOG_BUILD_SNAPSHOT, 'immutable_build_pin':False,
                'max_seconds':TIMEOUT, 'reserved_usd':str(cost), 'arm':arm})
            self.workers.append(worker)
            return worker
        except Exception:
            self.uncertain = True
            if sandbox is not None:
                try:
                    sandbox.kill(request_timeout=15)
                except Exception:
                    pass
            raise TransportError('create/admission uncertain or failed; no replacement permitted') from None

    def reconcile_uncertain(self):
        """Explicit cleanup-only reconciliation. Never creates or resumes a VM."""
        if not self.uncertain:
            return []
        killed = []
        try:
            from e2b import SandboxQuery
            pager = self._api.list(query=SandboxQuery(metadata={'pex_pilot':self.run_id}),
                api_key=self._key, retries=0, request_timeout=15)
            while pager.has_next:
                for info in pager.next_items():
                    if info.metadata.get('pex_pilot') != self.run_id:
                        raise TransportError('reconciliation identity mismatch')
                    self._api.kill(info.sandbox_id, api_key=self._key, retries=0, request_timeout=15)
                    killed.append(info.sandbox_id)
            return killed
        except Exception:
            raise TransportError('uncertain sandbox cleanup unconfirmed; no new creates') from None

    def close(self):
        failed = False
        for worker in self.workers:
            try:
                worker.close()
            except TransportError:
                failed = True
        if self.uncertain:
            try:
                self.reconcile_uncertain()
            except TransportError:
                failed = True
        if failed:
            raise TransportError('pilot cleanup not fully confirmed')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
