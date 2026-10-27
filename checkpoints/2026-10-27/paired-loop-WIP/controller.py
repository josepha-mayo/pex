"""Authored-only paired control flow; live admission deliberately absent.

Worker adapter owns isolated execution and receipts. Review adapter owns full PEX
planner + verifier and returns only an admitted, model-authored continuation.
Neither sees the protected grader or the other arm's privately held result. This module contains no correction prompts.
"""
from dataclasses import dataclass, asdict
import time


class PublicEvidenceInfrastructureError(RuntimeError):
    pass

class WorkerBudgetTerminal(ValueError):
    def __init__(self,code):
        if code not in {'worker_budget_reservation_refused','worker_attempt_cap_refused'}: raise ValueError('invalid_worker_budget_code')
        self.code=code
        super().__init__(code)

@dataclass(frozen=True)
class Budget:
    calls: int = 4
    input_tokens: int | None = 16000
    output_tokens: int = 2000
    active_seconds: float = 90.0


async def run_pair(arms, worker, review, grader, *, budget=Budget(), mode="authored-only", clock=time.monotonic, admission=None, emit=lambda **event: None):
    if mode not in {"authored-only", "live-pilot"}:
        raise PermissionError("unknown_mode")
    if mode == "live-pilot":
        if admission is None or admission.authorize(arms,budget) is not True:
            raise PermissionError("live_authority_isolation_and_receipts_not_admitted")
    if set(arms) != {"baseline", "pex"}:
        raise ValueError("exactly_two_arms_required")
    a, b = arms["baseline"], arms["pex"]
    if any(a[k] != b[k] for k in ("prompt", "public_sha256", "worker_identity")):
        raise ValueError("unequal_initial_conditions")
    if a["workspace"] == b["workspace"]:
        raise ValueError("independent_pristine_workspaces_required")
    if min(v for v in (budget.calls, budget.input_tokens, budget.output_tokens, budget.active_seconds) if v is not None) <= 0:
        raise ValueError("positive_resource_limits_required")
    report = {"mode": mode, "real_inference_calls": 0, "presentation_eligible": False,
              "worker_budget_each": asdict(budget), "arms": {}, "pex_lift": None}
    try:
        for condition in ("baseline", "pex"):
            arm = arms[condition]
            state = {"status": "running", "calls": 0, "input_tokens": 0, "output_tokens": 0,
                     "worker_active_seconds": 0.0, "supervisor_seconds": 0.0,
                     "reviews": [], "turn_receipts": []}
            report["arms"][condition] = state
            emit(event="arm_started",arm=condition)
            session, prompt = None, arm["prompt"]
            try:
                while True:
                    remaining = {"calls": budget.calls - state["calls"],
                                 "input_tokens": None if budget.input_tokens is None else budget.input_tokens - state["input_tokens"],
                                 "output_tokens": budget.output_tokens - state["output_tokens"],
                                 "active_seconds": budget.active_seconds - state["worker_active_seconds"]}
                    if min(v for v in remaining.values() if v is not None) <= 0:
                        state["status"] = "budget_terminal_inconclusive"
                        break
                    started = clock()
                    turn = await worker.turn(arm, prompt=prompt, session_id=session, remaining=remaining)
                    state["worker_active_seconds"] += turn.get("worker_active_seconds",clock() - started)
                    state["turn_receipts"].append(turn["receipt"])
                    for name in ("calls", "input_tokens", "output_tokens"):
                        value = turn["usage"][name]
                        if type(value) is not int or value < 0 or (name == "calls" and value < 1):
                            raise ValueError("invalid_usage_receipt")
                        state[name] += value
                    if not turn["session_id"] or (session and session != turn["session_id"]):
                        raise ValueError("worker_session_changed")
                    session = turn["session_id"]
                    if any(getattr(budget,k) is not None and state[k] > getattr(budget,k) for k in ("calls", "input_tokens", "output_tokens")):
                        raise ValueError("worker_budget_enforcement_failed")
                    if turn["terminal"] == "budget":
                        state["status"] = "budget_terminal_inconclusive"
                        break
                    if turn["terminal"] != "natural_stop":
                        raise ValueError("worker_not_naturally_stopped")
                    emit(event="worker_natural_stop",arm=condition,worker_calls=state["calls"])
                    if condition == "baseline":
                        state["status"] = "natural_stop"
                        break
                    if any(getattr(budget,k) is not None and state[k] >= getattr(budget,k) for k in ("calls", "input_tokens", "output_tokens")) or state["worker_active_seconds"] >= budget.active_seconds:
                        state["status"] = "budget_terminal_inconclusive"
                        break
                    started = clock()
                    emit(event="review_started",arm=condition,worker_calls=state["calls"])
                    decision = await review.review(arm, turn["public_observation"], session_id=session)
                    state["supervisor_seconds"] += clock() - started
                    state["reviews"].append(decision["receipt"])
                    emit(event="review_finished",arm=condition,terminal=decision["status"],worker_calls=state["calls"])
                    if decision["status"] != "approved_continuation":
                        state["status"] = decision["status"]
                        break
                    prompt = decision["text"]
                    if type(prompt) is not str or not prompt.strip():
                        raise ValueError("empty_model_continuation")
            except Exception as exc:
                from accounting import PilotBudgetExhausted
                cause=exc;budget_error=False;worker_budget_error=None
                for _ in range(8):
                    if isinstance(cause,WorkerBudgetTerminal): worker_budget_error=cause;break
                    if isinstance(cause,PilotBudgetExhausted): budget_error=True;break
                    cause=getattr(cause,'__cause__',None)
                    if cause is None: break
                state["status"] = "supervisor_budget_terminal_inconclusive" if budget_error else "infrastructure_error"
                if worker_budget_error is not None:
                    state["status"]="worker_budget_terminal_inconclusive"
                    state["budget_terminal_reason"]=worker_budget_error.code
                if isinstance(exc,PublicEvidenceInfrastructureError): state["status"]="infrastructure_inconclusive"
                state["error_type"] = type(exc).__name__
            finally:
                await worker.stop(arm)
            # Grade after this arm is stopped; NEVER expose its grade to the
            # next worker/reviewer or tune the pre-frozen second arm from it.
            if state["status"] in {"natural_stop", "no_intervention", "verifier_rejected", "budget_terminal_inconclusive", "supervisor_budget_terminal_inconclusive", "worker_budget_terminal_inconclusive"}:
                try:
                    state["protected_grade"] = await grader.grade(arm)
                    if state["protected_grade"].get("status") in {"inconclusive","public_contract_changed"}:
                        state["status"] = "grading_inconclusive"
                    state["grade_qualification"] = ("same_VM_post_stop_anti_tamper_limited" if mode=="live-pilot"
                                                    else "authored_orchestration_only_not_real_score")
                except Exception as exc:
                    state["grade_error"] = type(exc).__name__
                    state["status"] = "grading_inconclusive"
            emit(event="arm_terminal",arm=condition,terminal=state["status"],worker_calls=state["calls"])
        if mode == "live-pilot":
            report["real_worker_inference_calls"] = sum(s["calls"] for s in report["arms"].values())
            report["real_inference_calls"] = None  # combined count requires validated supervisor receipts
        emit(event="paired_terminal",terminal="finished",worker_calls=sum(s["calls"] for s in report["arms"].values()))
        return report
    finally:
        await worker.cleanup()
