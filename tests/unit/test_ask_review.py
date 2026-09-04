from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.session import HarnessSession
from pex_supervisor.ask_review import (
    complete_inspect_review_async,
    is_strands_model,
    review_tool_names,
)
from pex_supervisor.evidence_tools import build_evidence_tools
from strands.models.model import Model
from test_supervisor_loop import _request


class ReviewModel(Model):
    def __init__(self, *, call_inspect: bool = True) -> None:
        self.call_inspect = call_inspect
        self.captured_messages: list[str] = []

    def update_config(self, **model_config: Any) -> None:
        return None

    def get_config(self) -> dict[str, Any]:
        return {"model_id": "fake-review"}

    async def structured_output(
        self,
        output_model,
        prompt,
        system_prompt=None,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if False:
            yield {}

    async def stream(
        self,
        messages,
        tool_specs=None,
        system_prompt=None,
        *,
        tool_choice=None,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        self.captured_messages.append(json.dumps(messages))
        specs = list(tool_specs or [])
        inspect_tool = next(
            (spec for spec in specs if spec["name"] == "inspect_artifact"),
            None,
        )
        review = next(spec for spec in specs if spec["name"] == "ReviewAnswer")
        if self.call_inspect and inspect_tool is not None and len(self.captured_messages) == 1:
            yield {"messageStart": {"role": "assistant"}}
            yield {
                "contentBlockStart": {
                    "start": {
                        "toolUse": {
                            "toolUseId": "ask-inspect-1",
                            "name": inspect_tool["name"],
                        }
                    }
                }
            }
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
            yield {
                "metadata": {
                    "usage": {"inputTokens": 2, "outputTokens": 1, "totalTokens": 3},
                    "metrics": {"latencyMs": 1},
                }
            }
            return
        arguments = {
            "answer": "Inspected results.jsonl. The eval has 3 rows so far.",
            "evidence": ["inspect_artifact"],
        }
        yield {"messageStart": {"role": "assistant"}}
        yield {
            "contentBlockStart": {
                "start": {"toolUse": {"toolUseId": "ask-answer", "name": review["name"]}}
            }
        }
        yield {
            "contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(arguments)}}}
        }
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 3, "outputTokens": 4, "totalTokens": 7},
                "metrics": {"latencyMs": 1},
            }
        }


def test_ask_review_exposes_the_same_inspect_surface_as_stop():
    assert review_tool_names() == tuple(
        item.tool_name for item in build_evidence_tools(_request(0.1), [])
    )


def test_plain_objects_are_not_strands_models():
    assert is_strands_model(object()) is False
    assert is_strands_model(ReviewModel()) is True


@pytest.mark.asyncio
async def test_ask_review_agent_calls_inspect_tools_and_does_not_decide(tmp_path):
    (tmp_path / "results.jsonl").write_text('{"id":1}\n{"id":2}\n{"id":3}\n', encoding="utf-8")
    session = HarnessSession(
        id="codex:review",
        harness_type=HarnessType.CODEX,
        vendor_session_id="review",
        project_id="demo",
        status=SessionStatus.WORKING,
        cwd=str(tmp_path),
        last_activity=datetime.now(UTC),
    )
    model = ReviewModel()
    answer = await complete_inspect_review_async(
        "give a short briefing",
        [session],
        [],
        [],
        model,
    )
    assert answer is not None
    assert "3 rows" in answer
    assert len(model.captured_messages) == 2
    assert "row_count" in model.captured_messages[1]
    assert "SupervisorDecision" not in "".join(model.captured_messages)
    assert "SEND_NUDGE" not in "".join(model.captured_messages)
