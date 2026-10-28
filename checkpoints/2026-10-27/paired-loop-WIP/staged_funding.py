"""WIP authored-only phase gate over an existing private funding ledger.

Never grants money or provider authority. Counts accepted reservations, including
CLI finalization, rather than agent steps. Unknown outcomes stay in the original
ledger; no refund, reset or restart. Not connected to a live admission entry.
"""
import threading
from worker_funding import WorkerBudgetExhausted
from staged_envelope import PHASES
from nebius_worker import funding_usage_delta


class PhaseFunding:
    def __init__(self, ledger, *, mode='authored-only'):
        if mode == 'closed-admitted':
            from staged_accounting import WorkerPhaseLedger
            if type(ledger) is not WorkerPhaseLedger:raise PermissionError('closed_staged_phase_ledger_required')
            ledger.owner.before_reserve()
        elif mode != 'authored-only':
            raise PermissionError('staged_funding_live_not_admitted')
        self.mode=mode
        self.ledger=ledger
        self._lock=threading.RLock()
        self.index=-1
        self.open=False
        self.finished=False
        self.failed=False
        self.before=None

    def begin(self, index):
        with self._lock:
            if (type(index) is not int or index not in (0,1) or index != self.index+1
                    or self.open or self.failed or (index==1 and not self.finished)):
                raise ValueError('phase_transition_refused')
            snapshot=self.ledger.usage_snapshot()
            if index==0 and any(snapshot.values()):
                raise ValueError('fresh_phase_ledger_required_no_restart')
            if snapshot['uncertain_calls']:
                raise ValueError('uncertain_predecessor_phase_refused')
            self.before=snapshot
            self.index=index
            self.open=True
            self.finished=False

    def reserve(self, *args):
        with self._lock:
            if not self.open or self.failed:
                raise PermissionError('worker_phase_closed')
            delta=funding_usage_delta(self.before,self.ledger.usage_snapshot())
            if delta['calls'] >= PHASES[self.index].calls:
                self.failed=True
                raise WorkerBudgetExhausted('worker_attempt_cap_refused')
            # The independently admitted underlying ledger still enforces money,
            # endpoint/model, full4096 output reservation and the total12 attempts.
            try:
                return self.ledger.reserve(*args)
            except BaseException:
                self.failed=True
                raise

    def settle_raw(self, *args):
        with self._lock:
            # Permit settlement of an already accepted request even after abort;
            # never fabricate a refund for an uncertain wire outcome.
            return self.ledger.settle_raw(*args)

    def usage_snapshot(self):
        with self._lock:
            return self.ledger.usage_snapshot()

    def finish(self, *, natural_stop):
        with self._lock:
            if not self.open:
                raise ValueError('worker_phase_not_open')
            self.open=False
            delta=funding_usage_delta(self.before,self.ledger.usage_snapshot())
            if (natural_stop is not True or self.failed or delta['uncertain_calls']
                    or not 1 <= delta['calls'] <= PHASES[self.index].calls
                    or delta['output_tokens'] > PHASES[self.index].output_tokens):
                self.failed=True
                raise ValueError('natural_settled_phase_checkpoint_unproven')
            self.finished=True
            return delta

    def abort(self):
        with self._lock:
            self.open=False
            self.failed=True
