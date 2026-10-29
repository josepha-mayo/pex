"""Authored inert collaborators; no real worker, provider or VM execution."""
import asyncio
import copy
import pytest
from staged_controller import *


def arms():
    return {c:dict(condition=c,prompt='same task',public_sha256='a'*64,
        worker_identity='same worker',workspace=c) for c in ('baseline','pex')}


class Worker:
    def __init__(self): self.events=[]; self.cleaned=False
    async def prepare(self,arm,**kw): self.events.append(('prepare',arm['condition']))
    async def phase(self,arm,**kw):
        c=arm['condition']; self.events.append(('phase',c,kw))
        limit=kw['limit']
        return dict(session_id=c+'session',receipt='authored',terminal='natural_stop',
            worker_active_seconds=1,usage=dict(calls=limit.calls,input_tokens=10,output_tokens=limit.calls))
    async def observe(self,arm,turn): return {'public':'authored observation'}
    async def stop(self,arm): self.events.append(('stop',arm['condition']))
    async def release(self,arm): self.events.append(('release',arm['condition']))
    async def cleanup(self): self.cleaned=True


class Review:
    def __init__(self,worker): self.worker=worker
    async def review(self,arm,observation,*,session_id):
        self.worker.events.append(('review',arm['condition']))
        return dict(status='approved_continuation',text='Authored non-answer continuation',receipt={
            'observation_sha256':digest(observation),'worker_session_id':session_id,
            'planner_observed':True,'verifier_observed':True,
            'planner_receipts':['authored'],'verifier_receipts':['authored'],
            'planner_evidence_refs':['authored'],'verifier_evidence_refs':['authored']})


class Grade:
    async def grade(self,arm): return {'authored':True}


def run(w=None,r=None,**kw):
    w=w or Worker()
    return w,asyncio.run(run_staged_pair(arms(),w,r or Review(w),Grade(),**kw))


def test_exact_equal_phases_review_order_same_session_and_neutral_baseline():
    w,report=run()
    turns=[e for e in w.events if e[0]=='phase']
    assert [e[2]['limit'] for e in turns]==list(PHASES)*2
    assert [e[2]['session_id'] for e in turns]==[None,'baselinesession',None,'pexsession']
    assert turns[1][2]['prompt']==BASELINE_RESUME
    assert w.events.index(('review','pex')) < w.events.index(turns[3])
    assert w.events.index(('release','baseline')) < w.events.index(('prepare','pex'))
    assert all(s['calls']==12 for s in report['arms'].values())
    assert report['arms']['pex']['supervisor_observed'] and not report['arms']['baseline']['supervisor_observed']
    assert w.cleaned and report['pex_lift'] is None and not report['presentation_eligible']


@pytest.mark.parametrize('mode',['live-pilot','live',None])
def test_no_live_admission_before_callbacks(mode):
    with pytest.raises(PermissionError): asyncio.run(run_staged_pair(arms(),None,None,None,mode=mode))


@pytest.mark.parametrize('field,value',[('planner_observed',False),('verifier_observed',False),
    ('observation_sha256','wrong'),('worker_session_id','other'),('planner_receipts',[]),('verifier_evidence_refs',[])])
def test_missing_or_unbound_review_forbids_second_phase(field,value):
    w=Worker()
    class Bad(Review):
        async def review(self,*args,**kw):
            d=await super().review(*args,**kw); d['receipt'][field]=value; return d
    _,r=run(w,Bad(w))
    assert r['arms']['pex']['status']=='protocol_inconclusive'
    assert len([e for e in w.events if e[:2]==('phase','pex')])==1
    assert w.cleaned


@pytest.mark.parametrize('terminal',['budget','error','checkpoint'])
def test_failed_phase_is_not_a_checkpoint(terminal):
    class Bad(Worker):
        async def phase(self,*args,**kw):
            d=await super().phase(*args,**kw); d['terminal']=terminal; return d
    w,r=run(Bad())
    assert not any(e[0]=='review' for e in w.events)
    assert all(s['status']=='protocol_inconclusive' for s in r['arms'].values())


def test_mutated_observation_forbids_continuation():
    w=Worker()
    class Bad(Review):
        async def review(self,arm,observation,**kw):
            d=await super().review(arm,observation,**kw); observation['public']='changed'; return d
    _,r=run(w,Bad(w)); assert r['arms']['pex']['status']=='protocol_inconclusive'


def test_review_timeout_overhead_is_not_worker_time_and_no_continuation():
    ticks=[0.0]
    w=Worker()
    class Bad(Review):
        async def review(self,*a,**kw):
            ticks[0]+=61
            raise TimeoutError('authored timeout')
    _,r=run(w,Bad(w),clock=lambda:ticks[0])
    p=r['arms']['pex']; assert p['supervisor_seconds']==61 and p['worker_active_seconds']==1
    assert p['status']=='wall_budget_terminal_inconclusive'
    assert len([e for e in w.events if e[:2]==('phase','pex')])==1


def test_cleanup_failure_never_starts_second_arm():
    class Bad(Worker):
        async def release(self,arm): raise ConnectionError('authored cleanup ambiguity')
    w,r=run(Bad()); assert list(r['arms'])==['baseline']
    assert r['arms']['baseline']['status']=='cleanup_unconfirmed' and w.cleaned


def test_budget_exception_preserves_partial_receipt_without_review():
    class Bad(Worker):
        async def phase(self,*a,**kw):
            raise WorkerBudgetTerminal('worker_attempt_cap_refused',usage=dict(calls=8,
                input_tokens=10,output_tokens=4,uncertain_calls=0),worker_active_seconds=9)
    w,r=run(Bad())
    assert all(s['calls']==8 and s['worker_active_seconds']==9 for s in r['arms'].values())
    assert not any(e[0]=='review' for e in w.events)


def test_unused_phase_allowance_never_rolls_into_second_phase():
    class Early(Worker):
        async def phase(self,*a,**kw):
            d=await super().phase(*a,**kw)
            if kw['phase_index']==0: d['usage']['calls']=1
            return d
    w,r=run(Early())
    assert all(s['calls']==5 for s in r['arms'].values())
    assert all(e[2]['limit']==PHASES[1] for e in w.events if e[0]=='phase' and e[2]['phase_index']==1)


def test_unknown_phase_error_never_claims_zero_usage_exact():
    class Bad(Worker):
        async def phase(self,*a,**kw): raise ConnectionError('unknown partial progress')
    _,r=run(Bad())
    assert all(not s['worker_usage_exact'] and not s['worker_active_time_exact'] for s in r['arms'].values())


def test_review_does_not_reset_wall_headroom_or_worker_counters():
    ticks=[0.0]; w=Worker()
    class Bad(Review):
        async def review(self,*a,**kw):
            d=await super().review(*a,**kw); ticks[0]+=211; return d
    _,r=run(w,Bad(w),clock=lambda:ticks[0])
    p=r['arms']['pex']
    assert p['status']=='wall_budget_terminal_inconclusive' and p['calls']==8
    assert p['worker_usage_exact'] and p['worker_active_seconds']==1
    assert len([e for e in w.events if e[:2]==('phase','pex')])==1


def test_release_and_global_cleanup_share_absolute_VM_deadline():
    ticks=[0.0]
    class Slow(Worker):
        async def release(self,arm):
            await super().release(arm)
            ticks[0]=331
    w,r=run(Slow(),clock=lambda:ticks[0])
    assert list(r['arms'])==['baseline']
    assert r['arms']['baseline']['status']=='cleanup_unconfirmed'
    assert r['cleanup_confirmed'] is False


def test_final_cleanup_is_bounded_and_failure_retained():
    ticks=[0.0]
    class Slow(Worker):
        async def cleanup(self): ticks[0]+=16
    _,r=run(Slow(),clock=lambda:ticks[0])
    assert r['cleanup_confirmed'] is False and r['cleanup_error']=='TimeoutError'


@pytest.mark.parametrize('phase,calls,output,seconds',[(0,9,1,1),(1,5,1,1),
    (0,8,32769,1),(1,4,16385,1),(0,8,1,121),(1,4,1,61)])
def test_partial_overrun_is_retained_but_not_ordinary_budget_exhaustion(phase,calls,output,seconds):
    class Overrun(Worker):
        async def phase(self,*a,**kw):
            if kw['phase_index']==phase:
                raise WorkerBudgetTerminal('worker_attempt_cap_refused',usage=dict(calls=calls,
                    input_tokens=10,output_tokens=output,uncertain_calls=0),worker_active_seconds=seconds)
            return await super().phase(*a,**kw)
    _,r=run(Overrun())
    for s in r['arms'].values():
        assert s['status']=='protocol_inconclusive'
        assert s['error_type']=='worker_phase_enforcement_failed'
        assert s['calls']==calls+(8 if phase else 0)
        assert s['worker_active_seconds']==seconds+(1 if phase else 0)


def test_partial_second_phase_does_not_duplicate_first_phase_usage():
    class Partial(Worker):
        async def phase(self,*a,**kw):
            if kw['phase_index']==1:
                raise WorkerBudgetTerminal('worker_attempt_cap_refused',usage=dict(calls=4,
                    input_tokens=20,output_tokens=2,uncertain_calls=0),worker_active_seconds=2)
            return await super().phase(*a,**kw)
    _,r=run(Partial())
    assert all(s['calls']==12 and s['input_tokens']==30 and s['worker_active_seconds']==3 for s in r['arms'].values())
    assert all(s['status']=='worker_budget_terminal_inconclusive' for s in r['arms'].values())


def test_expired_worker_deadline_still_attempts_cleanup_only_callback():
    ticks=[0.0]
    class Expired(Worker):
        async def release(self,arm): ticks[0]=331
    w,r=run(Expired(),clock=lambda:ticks[0])
    assert w.cleaned and r['cleanup_only_after_worker_deadline']
    assert r['cleanup_confirmed'] is False  # Release proof was not supplied.


def test_measured_style_startup_latency_and_all_maxima_fit_frozen330s():
    # Authored virtual-clock latency regression, NOT a real provider assertion.
    #18.9s create/info +3x3s public setup fits40, not old20. Both arms still
    # receive complete120+60 worker caps and the SAME minimum25s grade budget.
    ticks=[0.0];windows=[]
    class Latency(Worker):
        async def prepare(self,arm,**kw):
            await super().prepare(arm,**kw);ticks[0]+=18.9+3*3
        async def phase(self,arm,**kw):
            result=await super().phase(arm,**kw)
            ticks[0]+=kw['limit'].active_seconds;result['worker_active_seconds']=kw['limit'].active_seconds
            return result
        async def observe(self,arm,turn):ticks[0]+=10;return await super().observe(arm,turn)
        async def stop(self,arm):ticks[0]+=3;await super().stop(arm)
        async def release(self,arm):ticks[0]+=12;await super().release(arm)
    class FullReview(Review):
        async def review(self,*a,**kw):ticks[0]+=60;return await super().review(*a,**kw)
    class CaptureGrade:
        def reserve_wall(self,arm,*,deadline):windows.append((arm['condition'],deadline-ticks[0]))
        async def grade(self,arm):ticks[0]+=25;return {'authored_only':True}
    worker=Latency();report=asyncio.run(run_staged_pair(arms(),worker,FullReview(worker),CaptureGrade(),clock=lambda:ticks[0]))
    assert all(x['status']=='staged_natural_stop' and x['worker_active_seconds']==180 for x in report['arms'].values())
    assert report['cleanup_confirmed'] and len(windows)==2 and all(25<=seconds<=45 for _,seconds in windows)
    assert windows[1][1]==pytest.approx(37.1)  # Unused setup12.1s, not borrowed worker allowance.


def test_allowlisted_local_admission_reason_is_not_hidden_as_class_only():
    from staged_admission import AdmissionRefused
    class Refused(Worker):
        async def phase(self,*a,**kw):raise AdmissionRefused('ambiguous_child_proxy_alias_refused')
    _,report=run(Refused())
    assert all(x['local_admission_reason_code']=='ambiguous_child_proxy_alias_refused' for x in report['arms'].values())
    assert report['cleanup_confirmed']
