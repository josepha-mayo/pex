"""Authored local Model for SDK contract tests; never performs inference or I/O."""

import json
import re

from strands.models.model import Model


class AuthoredSupervisorModel(Model):
    def __init__(self, *, action="SEND_NUDGE", failure=None, bad_usage=None, bad_call=1):
        self.action = action
        self.failure = failure
        self.bad_usage = bad_usage
        self.bad_call = bad_call
        self.calls = 0
        self.inputs = []

    def get_config(self):
        return {"model_id": "local-authored-test-not-inference"}

    def update_config(self, **kwargs):
        pass

    async def structured_output(self, *args, **kwargs):
        raise AssertionError("Strands must use its actual structured-output tool interface")
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.calls += 1
        self.inputs.append(messages)
        if self.failure:
            raise self.failure
        names = {spec["name"] for spec in tool_specs}
        is_verifier = "IndependentVerifierDecision" in names
        refs = []
        for message in messages:
            for item in message.get("content", []):
                if "toolResult" in item:
                    refs.extend(re.findall(r"pexobs_[a-f0-9]{32}", json.dumps(item)))
        refs = list(dict.fromkeys(refs))
        if not refs:
            tool_name, payload = (
                ("get_scores" if "get_scores" in names else "inspect_acceptance"),
                {},
            )
        elif is_verifier:
            tool_name = "IndependentVerifierDecision"
            payload = {
                "approved": True,
                "rationale": "Authored verifier accepts the observed gap for this test.",
                "evidence": ["The request-bound score receipt was inspected."],
                "evidence_refs": refs,
            }
        else:
            tool_name = "SupervisorDecision"
            payload = {
                "action_type": self.action,
                "rationale": "Authored test decision after observing request-bound evidence.",
                "evidence": ["The request-bound score receipt was inspected."],
                "evidence_refs": refs,
                "message": (
                    "Inspect the unresolved acceptance evidence, then choose your own next step."
                ),
                "risk": "low",
                "confidence": 0.9,
            }
        yield {"messageStart": {"role": "assistant"}}
        yield {
            "contentBlockStart": {
                "contentBlockIndex": 0,
                "start": {"toolUse": {"toolUseId": f"authored-{self.calls}", "name": tool_name}},
            }
        }
        yield {
            "contentBlockDelta": {
                "contentBlockIndex": 0,
                "delta": {"toolUse": {"input": json.dumps(payload)}},
            }
        }
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "tool_use"}}
        usage = {"inputTokens": 20, "outputTokens": 10, "totalTokens": 30}
        if self.calls == self.bad_call:
            if self.bad_usage == "missing":
                return
            if self.bad_usage is not None:
                usage["inputTokens"] = self.bad_usage
        yield {"metadata": {"usage": usage, "metrics": {"latencyMs": 1}}}
