"""Authored time-receipt regression only: no model, network, VM or real score."""
import asyncio
import json
import pytest
from controller import Budget, run_pair


class Worker:
    def __init__(self, elapsed):
        self.elapsed = elapsed
        self.stopped = set()
        self.cleaned = False

    async def turn(self, arm, **kwargs):
        return dict(session_id=arm['workspace'], receipt='authored receipt',
                    usage=dict(calls=1, input_tokens=1, output_tokens=1),
                    terminal='natural_stop', worker_active_seconds=self.elapsed,
                    public_observation={})

    async def stop(self, arm):
        self.stopped.add(arm['workspace'])

    async def cleanup(self):
        self.cleaned = True


class Review:
    def __init__(self):
        self.calls = 0

    async def review(self, *args, **kwargs):
        self.calls += 1
        return dict(status='no_intervention', receipt='authored review')


class Grade:
    def __init__(self):
        self.calls = []

    async def grade(self, arm):
        self.calls.append(arm['workspace'])
        return dict(kind='authored placeholder', score=None)


def run(elapsed):
    worker, review, grade = Worker(elapsed), Review(), Grade()
    arms = {c: dict(prompt='identical authored prompt', public_sha256='a'*64,
                    worker_identity='same worker', workspace=c)
            for c in ('baseline', 'pex')}
    report = asyncio.run(run_pair(arms, worker, review, grade,
                                 budget=Budget(active_seconds=90)))
    assert worker.cleaned and worker.stopped == {'baseline', 'pex'}
    json.dumps(report, allow_nan=False)
    return report, review, grade


@pytest.mark.parametrize('elapsed', [-1, float('nan'), float('inf'),
                                    -float('inf'), True, '1', None, 10**400])
def test_invalid_duration_is_infrastructure_not_task_result(elapsed):
    report, review, grade = run(elapsed)
    assert review.calls == 0 and grade.calls == []
    for arm in report['arms'].values():
        assert arm['status'] == 'infrastructure_error'
        assert arm['error_type'] == 'ValueError'
        assert arm['calls'] == 1  # retain already validated usage, not free failure
        assert arm['worker_active_seconds'] == 0
        assert 'protected_grade' not in arm


def test_active_overrun_is_budget_terminal_for_both_arms():
    report, review, grade = run(100)
    assert review.calls == 0 and grade.calls == ['baseline', 'pex']
    assert all(arm['status'] == 'budget_terminal_inconclusive'
               and arm['worker_active_seconds'] == 100
               for arm in report['arms'].values())


@pytest.mark.parametrize('elapsed', [0, 1, .25, 90])
def test_valid_duration_and_exact_boundary_are_preserved(elapsed):
    report, review, grade = run(elapsed)
    assert report['arms']['baseline']['status'] == 'natural_stop'
    assert all(arm['worker_active_seconds'] == elapsed for arm in report['arms'].values())
    assert review.calls == (0 if elapsed == 90 else 1)

