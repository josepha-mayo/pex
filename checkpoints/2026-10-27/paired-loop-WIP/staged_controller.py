"""WIP staged baseline versus PEX; authored collaborators ONLY, no live admission.

Hard phase reservation enforcement and natural-stop CLI receipts are adapter
obligations. A cap refusal/error is never relabeled a checkpoint. Async timeout
is not proof that a synchronous SDK call was interrupted: live adapters still
need bounded cancellable operations and the unchanged provider VM deadline.
"""
import asyncio
from dataclasses import asdict
import hashlib
import json
import math
import time
from controller import WorkerBudgetTerminal
from staged_envelope import (PHASES, TOTAL, Lifetime, WallBudgetExhausted,
    SETUP_SECONDS, OBSERVATION_SECONDS, REVIEW_SECONDS, GRADE_SECONDS, CLEANUP_SECONDS,
    WALL_PROFILE,grade_allowance)

BASELINE_RESUME = 'Continue the same task in this session using the remaining phase allowance.'


class ProtocolInconclusive(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def review_observed(decision, observation_digest, session_id):
    receipt = decision.get('receipt', {})
    if (type(receipt) is not dict or receipt.get('observation_sha256') != observation_digest
            or receipt.get('worker_session_id') != session_id
            or receipt.get('planner_observed') is not True
            or not receipt.get('planner_evidence_refs') or not receipt.get('planner_receipts')):
        raise ProtocolInconclusive('supervisor_observation_unproven')
    if decision.get('status') == 'approved_continuation' and (
            receipt.get('verifier_observed') is not True
            or not receipt.get('verifier_evidence_refs') or not receipt.get('verifier_receipts')):
        raise ProtocolInconclusive('independent_verifier_observation_unproven')
    return receipt


def add_usage(state, usage, elapsed, limit):
    if (type(usage) is not dict or set(usage) != {'calls','input_tokens','output_tokens'}
            or any(type(v) is not int or v < 0 for v in usage.values())
            or usage['calls'] < 1):
        raise ProtocolInconclusive('phase_usage_invalid_or_over_cap')
    if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ProtocolInconclusive('phase_time_invalid_or_over_cap')
    for field, value in usage.items():
        state[field] += value
    state['worker_active_seconds'] += elapsed
    if (usage['calls'] > limit.calls or usage['output_tokens'] > limit.output_tokens
            or elapsed > limit.active_seconds):
        raise ProtocolInconclusive('phase_enforcement_failed')


async def run_staged_pair(arms, worker, review, grader, *, mode='authored-only', clock=time.monotonic, _composition=None):
    if mode=='closed-admitted':
        from staged_composition import Composition
        if type(_composition) is not Composition:raise PermissionError('closed_owned_composition_required')
        _composition.verify(arms,worker,review,grader)
    elif mode!='authored-only' or _composition is not None or getattr(worker,'mode','authored-only')!='authored-only':
        raise PermissionError('staged_live_entry_not_implemented_or_authorized')
    if set(arms) != {'baseline','pex'}:
        raise ValueError('exactly_two_arms_required')
    if any(arms['baseline'][k] != arms['pex'][k] for k in ('prompt','public_sha256','worker_identity')):
        raise ValueError('unequal_initial_conditions')
    if arms['baseline']['workspace'] == arms['pex']['workspace']:
        raise ValueError('independent_pristine_workspaces_required')
    report = {'mode':mode,'protocol':'staged-8+4-WIP','worker_budget_each':asdict(TOTAL),
              'phases_each':[asdict(p) for p in PHASES], 'wall_profile':dict(WALL_PROFILE),'arms':{},
              'required_worker_adapter_policy':'symmetric_counted_final_request_tool_choice_none_not_spontaneous_task_completion',
              'real_inference_calls':0 if mode=='authored-only' else None,'pex_lift':None,'presentation_eligible':False}
    life = None
    try:
        for condition in ('baseline','pex'):
            arm = arms[condition]
            life = Lifetime(clock())  # BEFORE prepare/create, includes every pause.
            state = {'status':'running','calls':0,'input_tokens':0,'output_tokens':0,
                     'worker_active_seconds':0.0,'supervisor_seconds':0.0,
                     'supervisor_observed':False,'phases':[],'reviews':[],
                     'worker_usage_exact':True,'worker_active_time_exact':True}
            report['arms'][condition] = state
            session = None
            prompt = arm['prompt']
            cleanup_elapsed = 0.0
            cleanup_failed = False
            pending_worker_phase = False
            current_limit = None

            async def bounded(call, seconds, retain=0, *, setup=False):
                if _composition is not None:_composition.verify(arms,worker,review,grader)
                now = clock()
                if setup:
                    seconds = min(seconds, life.deadline - now - retain)
                allowance = life.allowance(now, seconds, retain=retain)
                started = clock()
                result = await asyncio.wait_for(call(), timeout=allowance)
                if clock() - started > allowance:
                    raise WallBudgetExhausted('stage_wall_deadline_exceeded')
                return result

            try:
                await bounded(lambda:worker.prepare(arm, deadline=life.deadline), SETUP_SECONDS,
                              retain=TOTAL.active_seconds+OBSERVATION_SECONDS+REVIEW_SECONDS+GRADE_SECONDS+CLEANUP_SECONDS, setup=True)
                for index, limit in enumerate(PHASES):
                    current_limit = limit
                    retain = (OBSERVATION_SECONDS+REVIEW_SECONDS+PHASES[1].active_seconds+GRADE_SECONDS+CLEANUP_SECONDS
                              if index == 0 else GRADE_SECONDS+CLEANUP_SECONDS)
                    pending_worker_phase = True
                    turn = await bounded(lambda:worker.phase(arm, prompt=prompt, session_id=session,
                                        phase_index=index, limit=limit), limit.active_seconds, retain)
                    add_usage(state, turn['usage'], turn['worker_active_seconds'], limit)
                    pending_worker_phase = False
                    state['phases'].append(turn['receipt'])
                    if turn.get('terminal') != 'natural_stop':
                        raise ProtocolInconclusive('phase_not_naturally_stopped')
                    current = turn.get('session_id')
                    if type(current) is not str or not current or (session is not None and current != session):
                        raise ProtocolInconclusive('worker_session_changed')
                    session = current
                    if index == 1:
                        state['status'] = 'staged_natural_stop'
                        break
                    observation = await bounded(lambda:worker.observe(arm, turn), OBSERVATION_SECONDS,
                                                 retain=REVIEW_SECONDS+PHASES[1].active_seconds+GRADE_SECONDS+CLEANUP_SECONDS)
                    observation_digest = digest(observation)
                    state['checkpoint_sha256'] = observation_digest
                    if condition == 'baseline':
                        prompt = BASELINE_RESUME
                    else:
                        started = clock()
                        try:
                            decision = await bounded(lambda:review.review(arm, observation, session_id=session),
                                                     REVIEW_SECONDS, retain=PHASES[1].active_seconds+GRADE_SECONDS+CLEANUP_SECONDS)
                        finally:
                            # Includes failed/timeout review; never subtract from worker time.
                            state['supervisor_seconds'] += clock() - started
                        if digest(observation) != observation_digest:
                            raise ProtocolInconclusive('checkpoint_observation_mutated')
                        receipt = review_observed(decision, observation_digest, session)
                        state['reviews'].append(receipt)
                        state['supervisor_observed'] = True
                        if decision['status'] != 'approved_continuation':
                            if decision['status'] not in {'no_intervention','planner_rejected','verifier_rejected'}:
                                raise ProtocolInconclusive('unknown_supervisor_terminal')
                            state['status'] = decision['status']
                            break
                        prompt = decision.get('text')
                        if type(prompt) is not str or not prompt.strip():
                            raise ProtocolInconclusive('empty_model_continuation')
            except WorkerBudgetTerminal as error:
                state['status']='worker_budget_terminal_inconclusive'
                state['budget_terminal_reason']=error.code
                if error.usage is None:
                    state['worker_usage_exact']=False
                else:
                    for field in ('calls','input_tokens','output_tokens'):
                        state[field] += error.usage[field]
                    state['worker_uncertain_calls']=error.usage['uncertain_calls']
                    state['worker_usage_exact']=error.usage['uncertain_calls']==0
                if error.worker_active_seconds is None:
                    state['worker_active_time_exact']=False
                else:
                    state['worker_active_seconds'] += error.worker_active_seconds
                partial=error.usage
                if (current_limit is None
                        or (partial is not None and (partial['calls'] > current_limit.calls
                            or partial['output_tokens'] > current_limit.output_tokens))
                        or (error.worker_active_seconds is not None and error.worker_active_seconds > current_limit.active_seconds)
                        or state['calls'] > TOTAL.calls or state['output_tokens'] > TOTAL.output_tokens
                        or state['worker_active_seconds'] > TOTAL.active_seconds):
                    state['status']='protocol_inconclusive'
                    state['error_type']='worker_phase_enforcement_failed'
            except (TimeoutError, WallBudgetExhausted) as error:
                state['status']='wall_budget_terminal_inconclusive'
                state['error_type']=type(error).__name__
                # Interrupted worker receipts may be unavailable; zero is not proof.
                if pending_worker_phase:
                    state['worker_usage_exact']=False
                    state['worker_active_time_exact']=False
            except Exception as error:
                state['status']='protocol_inconclusive' if isinstance(error,ProtocolInconclusive) else 'infrastructure_inconclusive'
                state['error_type']=type(error).__name__
                if pending_worker_phase:
                    state['worker_usage_exact']=False
                    state['worker_active_time_exact']=False
            finally:
                started = clock()
                try:
                    # Stop/revoke before protected grading; teardown shares15s.
                    stop_window = min(CLEANUP_SECONDS, max(0,life.deadline-clock()))
                    await asyncio.wait_for(worker.stop(arm), timeout=stop_window)
                    if clock()-started > stop_window:
                        raise TimeoutError('stop_exceeded_absolute_deadline')
                except Exception:
                    cleanup_failed = True
                cleanup_elapsed += max(0,clock()-started)
            if not cleanup_failed and state['status'] in {'staged_natural_stop','no_intervention','planner_rejected','verifier_rejected'}:
                try:
                    cleanup_remaining=max(0,CLEANUP_SECONDS-cleanup_elapsed)
                    grade_seconds=grade_allowance(life,clock(),cleanup_remaining)
                    state['grade_wall_allowance_seconds']=grade_seconds
                    reserve_wall=getattr(grader,'reserve_wall',None)
                    if callable(reserve_wall):reserve_wall(arm,deadline=clock()+grade_seconds)
                    state['protected_grade'] = await bounded(lambda:grader.grade(arm), grade_seconds,
                                              retain=cleanup_remaining)
                    state['grade_qualification']='authored_only_not_task_success' if mode=='authored-only' else 'same_VM_grade_with_explicit_anti_tamper_limits'
                except Exception as error:
                    state['status']='grading_inconclusive'
                    state['grade_error']=type(error).__name__
            try:
                remaining = min(CLEANUP_SECONDS - cleanup_elapsed, life.deadline-clock())
                if remaining <= 0:
                    raise TimeoutError('shared_cleanup_window_exhausted')
                started = clock()
                await asyncio.wait_for(worker.release(arm), timeout=remaining)
                if clock()-started > remaining:
                    raise TimeoutError('release_exceeded_absolute_deadline')
            except Exception:
                cleanup_failed = True
            if cleanup_failed:
                state['status']='cleanup_unconfirmed'
                break  # Never create the next VM on ambiguous cleanup.
        return report
    finally:
        # This is an authored contract, not a proof that blocking SDK work obeys
        # cancellation. A future live adapter also needs provider-side expiry.
        # A bounded cleanup-only grace is allowed even AFTER worker expiry.
        # It may kill/query owned resources, never create/resume/extend them.
        remaining = CLEANUP_SECONDS
        report['cleanup_only_after_worker_deadline'] = life is not None and clock() >= life.deadline
        started = clock()
        try:
            await asyncio.wait_for(worker.cleanup(), timeout=remaining)
            if clock()-started > remaining:
                raise TimeoutError('final_cleanup_exceeded_absolute_deadline')
            report['cleanup_confirmed'] = all(s['status'] != 'cleanup_unconfirmed' for s in report['arms'].values())
        except Exception as error:
            report['cleanup_confirmed'] = False
            report['cleanup_error'] = type(error).__name__

