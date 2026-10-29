"""WIP, code-only staged resource contracts; no admission, SDK or network.

An idle/paused worker still owns a billable VM. No deadline or monetary
allowance is extended when entering review or moving between worker phases.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Phase:
    calls: int
    output_tokens: int
    active_seconds: int


WORKER_OUTPUT_PER_CALL = 16384
PHASES = (Phase(8, 131072, 360), Phase(4, 65536, 180))
TOTAL = Phase(12, 196608, 540)
VM_SECONDS = 750
SETUP_SECONDS = 60
OBSERVATION_SECONDS = 10
REVIEW_SECONDS = 90
GRADE_SECONDS = 30
GRADE_MAX_SECONDS = 60
CLEANUP_SECONDS = 20
WALL_PROFILE = {'setup_seconds':SETUP_SECONDS,'worker_active_seconds':TOTAL.active_seconds,
    'observation_seconds':OBSERVATION_SECONDS,'review_seconds':REVIEW_SECONDS,
    'grade_guaranteed_seconds':GRADE_SECONDS,'grade_unused_slack_max_seconds':GRADE_MAX_SECONDS,
    'cleanup_shared_seconds':CLEANUP_SECONDS,
    'grade_borrow_rule':'actual_unused_prior_wall_only_absolute_VM_deadline_cleanup_retained'}

assert tuple(sum(getattr(p, k) for p in PHASES) for k in ('calls', 'output_tokens', 'active_seconds')) == (12, 196608, 540)
assert TOTAL.active_seconds + SETUP_SECONDS + OBSERVATION_SECONDS + REVIEW_SECONDS + GRADE_SECONDS + CLEANUP_SECONDS == VM_SECONDS


class WallBudgetExhausted(RuntimeError):
    pass


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('finite_nonnegative_wall_time_required')
    return float(value)


@dataclass(frozen=True)
class Lifetime:
    """Start BEFORE VM creation, not after setup; never pause/reset this clock."""
    started: float

    def __post_init__(self):
        _number(self.started)

    @property
    def deadline(self):
        return self.started + VM_SECONDS

    def allowance(self, now, requested, *, retain=0):
        now, requested, retain = _number(now), _number(requested), _number(retain)
        if now < self.started or requested <= 0:
            raise ValueError('invalid_wall_window')
        # Never shrink an arm's frozen worker phase to fit a late review.
        if self.deadline - now < requested + retain:
            raise WallBudgetExhausted('insufficient_unchanged_VM_lifetime')
        return requested


def reservation_envelope(*, prior_provider, equal_worker_fresh, supervisor_fresh,
                         provider_ceiling, prior_compute, verified_vm_bound,
                         uncertain_create_reserve, compute_ceiling):
    """Pure prospective accounting, not a quote or authority to spend.

    Caller must include EVERY predecessor and uncertain reservation. Sequential
    peak includes the first VM's entire admitted lifetime plus the second VM's
    generic create reservation. Unknown creation must stop, never be refunded.
    """
    values = (prior_provider, equal_worker_fresh, supervisor_fresh, provider_ceiling,
              prior_compute, verified_vm_bound, uncertain_create_reserve, compute_ceiling)
    if any(type(v) is not int or v < 0 for v in values):
        raise ValueError('nonnegative_integer_nanoUSD_required')
    if not equal_worker_fresh or not supervisor_fresh or not verified_vm_bound:
        raise ValueError('positive_fresh_reservations_required')
    if uncertain_create_reserve < verified_vm_bound:
        raise ValueError('generic_reservation_below_verified_lifetime')
    provider = prior_provider + 2 * equal_worker_fresh + supervisor_fresh
    final = prior_compute + 2 * verified_vm_bound
    peak = prior_compute + verified_vm_bound + uncertain_create_reserve
    if provider > provider_ceiling or max(final, peak) > compute_ceiling:
        raise ValueError('cumulative_ceiling_exceeded')
    return {'provider_reserved_ceiling': provider, 'compute_sequential_peak': peak,
            'compute_final_lifetime_bound': final, 'paused_VM_seconds_discounted': False}


def grade_allowance(lifetime,now,cleanup_remaining):
    """Prospectively frozen rule, never score/outcome-dependent wall tuning."""
    now=_number(now);cleanup_remaining=_number(cleanup_remaining)
    if cleanup_remaining>CLEANUP_SECONDS:raise ValueError('shared_cleanup_bound')
    available=lifetime.deadline-now-cleanup_remaining
    if available<GRADE_SECONDS:raise WallBudgetExhausted('guaranteed_grade_window_unavailable')
    return min(GRADE_MAX_SECONDS,available)
