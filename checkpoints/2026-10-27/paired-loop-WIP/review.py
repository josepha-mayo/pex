"""Connect owned full-prompt planner/verifier to same-session continuation.

Offline orchestration only. Factories must use existing owned process models;
there is no live provider, credential, or execution admission here.
"""
from pex_supervisor import loop
from pex_protocol.actions import InterventionType
from pex_protocol.supervisor import supervisor_request_digest


def evidence(request, model, decision, role):
    observations = list(model.observations)
    raw = list(decision.evidence_refs)
    if not raw:
        ids = {o.observation_id for o in observations}
        raw = list(dict.fromkeys(x for x in decision.evidence if x in ids))
    refs, valid = loop._resolve_evidence_refs(
        request, observations=observations, raw_refs=raw,
        stage="main" if role == "planner" else "verifier",
        invocation_id=model.protocol.invocation_id)
    boundaries = loop._goal_boundaries_observed(request, observations, refs)
    tools = {o.tool_name for o in observations if o.observation_id in refs}
    return refs, bool(valid and refs and boundaries), tools


class OwnedReview:
    def __init__(self, request_builder, model_factory, *, mode="authored-only", admission=None, request_recorder=None):
        if mode not in {"authored-only","live-pilot"} or (mode=="live-pilot" and admission is None):
            raise PermissionError("live_review_not_admitted")
        self.request_recorder=request_recorder
        self.mode=mode
        self.request_builder = request_builder
        self.model_factory = model_factory

    async def review(self, arm, observation, *, session_id):
        request = self.request_builder(arm, observation, session_id)
        if request.session.vendor_session_id != session_id:
            raise ValueError("request_worker_session_mismatch")
        if request.supervisor_decision_mode != "supervisor_model_only":
            raise ValueError("model_only_required")
        digest = supervisor_request_digest(request)
        if self.request_recorder is not None:
            self.request_recorder(digest,request.model_dump_json().encode("utf-8"))
        planner = self.model_factory("planner", request, None)
        result = await planner.invoke_async()
        decision = result.structured_output
        if type(decision) is not loop.SupervisorDecision:
            raise ValueError("planner_schema_mismatch")
        receipt = {"request_digest": digest, "planner_receipts": list(planner.receipts),
                   "planner_invocation": planner.protocol.invocation_id,
                   "verifier_receipts": [], "mode": self.mode}
        refs, valid, _ = evidence(request, planner, decision, "planner")
        proposal = loop._decision_proposal(decision)
        if not proposal["evidence"] and valid:
            proposal["evidence"] = refs
        action = loop._action_from_proposal(request, proposal)
        if action.type == InterventionType.NOOP:
            return {"status": "no_intervention", "receipt": receipt}
        # Deliberately narrower than the app: no shell, overlays, permissions,
        # new sessions or copied solutions. Only model-authored continuation.
        if action.type not in {InterventionType.SEND_NUDGE, InterventionType.CONTINUE_SESSION} or not valid:
            return {"status": "planner_rejected", "receipt": receipt}
        verifier = self.model_factory("verifier", request, action)
        verdict = (await verifier.invoke_async()).structured_output
        if type(verdict) is not loop.IndependentVerifierDecision:
            raise ValueError("verifier_schema_mismatch")
        receipt["verifier_receipts"] = list(verifier.receipts)
        receipt["verifier_invocation"] = verifier.protocol.invocation_id
        vrefs, valid, tools = evidence(request, verifier, verdict, "verifier")
        observed = tools & {"get_context", "get_recent_events", "get_scores", "get_session_state",
                            "inspect_acceptance", "inspect_workspace", "inspect_git", "inspect_file",
                            "inspect_artifact", "inspect_process", "run_verification"}
        if (not verdict.approved or not verdict.evidence or not valid or not observed
                or loop._uncertain_verification_only(request, tools)):
            return {"status": "verifier_rejected", "receipt": receipt}
        if supervisor_request_digest(request) != digest:
            raise ValueError("request_mutated_during_review")
        text = action.payload.get("text")
        if type(text) is not str or not text.strip():
            raise ValueError("missing_model_authored_text")
        receipt["planner_evidence_refs"], receipt["verifier_evidence_refs"] = refs, vrefs
        return {"status": "approved_continuation", "text": text, "receipt": receipt}
