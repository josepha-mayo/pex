"""Authored-only paired control flow; live admission deliberately absent.

Worker adapter owns isolated execution and receipts. Review adapter owns full PEX
planner + verifier and returns only an admitted, model-authored continuation.
Neither sees the protected grader. This module contains no correction prompts.
"""
from dataclasses import dataclass, asdict
import time


@dataclass(frozen=True)
class Budget:
    calls: int = 4
    input_tokens: int = 16000
    output_tokens: int = 2000
    active_seconds: float = 90.0


async def run_pair(arms, worker, review, grader, *, budget=Budget(), mode="authored-only", clock=time.monotonic):
    if mode != "authored-only":
        raise PermissionError("live_authority_isolation_and_receipts_not_admitted")
    if set(arms) != {"baseline", "pex"}:
        raise ValueError("exactly_two_arms_required")
    a, b = arms["baseline"], arms["pex"]
    if any(a[k] != b[k] for k in ("prompt", "public_sha256", "worker_identity")):
        raise ValueError("unequal_initial_conditions")
    if a["workspace"] == b["workspace"]:
        raise ValueError("independent_pristine_workspaces_required")
    if min(budget.calls, budget.input_tokens, budget.output_tokens, budget.active_seconds) <= 0:
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
            session, prompt = None, arm["prompt"]
            try:
                while True:
                    remaining = {"calls": budget.calls - state["calls"],
                                 "input_tokens": budget.input_tokens - state["input_tokens"],
                                 "output_tokens": budget.output_tokens - state["output_tokens"],
                                 "active_seconds": budget.active_seconds - state["worker_active_seconds"]}
                    if min(remaining.values()) <= 0:
                        state["status"] = "budget_terminal_inconclusive"
                        break
                    started = clock()
                    turn = await worker.turn(arm, prompt=prompt, session_id=session, remaining=remaining)
                    state["worker_active_seconds"] += clock() - started
                    state["turn_receipts"].append(turn["receipt"])
                    for name in ("calls", "input_tokens", "output_tokens"):
                        value = turn["usage"][name]
                        if type(value) is not int or value < 0 or (name == "calls" and value < 1):
                            raise ValueError("invalid_usage_receipt")
                        state[name] += value
                    if not turn["session_id"] or (session and session != turn["session_id"]):
                        raise ValueError("worker_session_changed")
                    session = turn["session_id"]
                    if any(state[k] > getattr(budget, k) for k in ("calls", "input_tokens", "output_tokens")):
                        raise ValueError("worker_budget_enforcement_failed")
                    if turn["terminal"] == "budget":
                        state["status"] = "budget_terminal_inconclusive"
                        break
                    if turn["terminal"] != "natural_stop":
                        raise ValueError("worker_not_naturally_stopped")
                    if condition == "baseline":
                        state["status"] = "natural_stop"
                        break
                    started = clock()
                    decision = await review.review(arm, turn["public_observation"], session_id=session)
                    state["supervisor_seconds"] += clock() - started
                    state["reviews"].append(decision["receipt"])
                    if decision["status"] != "approved_continuation":
                        state["status"] = decision["status"]
                        break
                    prompt = decision["text"]
                    if type(prompt) is not str or not prompt.strip():
                        raise ValueError("empty_model_continuation")
            except Exception as exc:
                state["status"] = "infrastructure_error"
                state["error_type"] = type(exc).__name__
            finally:
                await worker.stop(arm)
        # Both workers stopped before any protected acceptance result is opened.
        for condition, state in report["arms"].items():
            if state["status"] in {"natural_stop", "no_intervention", "verifier_rejected", "budget_terminal_inconclusive"}:
                state["protected_grade"] = await grader.grade(arms[condition])
                state["grade_qualification"] = "authored_orchestration_only_not_real_score"
        return report
    finally:
        await worker.cleanup()
