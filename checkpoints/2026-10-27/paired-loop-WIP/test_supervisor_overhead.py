"""Authored clocks and inert collaborators only; no provider or worker execution."""
import asyncio
import pytest
from controller import run_pair
from accounting import PilotBudgetExhausted

@pytest.mark.parametrize('failure,status', [
    (ConnectionError('authored infrastructure failure'), 'infrastructure_error'),
    (PilotBudgetExhausted('budget_reservation_refused'), 'supervisor_budget_terminal_inconclusive'),
])
def test_failed_supervisor_time_is_retained_separately(failure,status):
    class Worker:
        async def turn(self,arm,**kwargs):
            return dict(session_id=arm['workspace'],receipt='authored',
                        usage=dict(calls=1,input_tokens=1,output_tokens=1),
                        terminal='natural_stop',public_observation={})
        async def stop(self,arm): pass
        async def cleanup(self): pass
    class Reviewer:
        async def review(self,*args,**kwargs): raise failure
    class Grader:
        async def grade(self,*args): return {'status':'graded_with_limits','authored':True}
    arms={c:dict(prompt='same',public_sha256='a'*64,worker_identity='same',workspace=c)
          for c in ('baseline','pex')}
    ticks=iter([0,1,1,2,2,72])
    report=asyncio.run(run_pair(arms,Worker(),Reviewer(),Grader(),clock=lambda:next(ticks)))
    assert report['arms']['pex']['status']==status
    assert report['arms']['pex']['supervisor_seconds']==70
    assert report['arms']['pex']['worker_active_seconds']==1
    assert report['arms']['baseline']['supervisor_seconds']==0
    assert report['pex_lift'] is None and not report['presentation_eligible']
