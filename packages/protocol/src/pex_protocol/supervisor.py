from typing import Any

from pydantic import BaseModel, Field

from pex_protocol.actions import ProposedAction
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession


class TrajectoryScores(BaseModel):
    drift: float = 0.0
    stagnation: float = 0.0
    premature_completion: float = 0.0
    claim_contradiction: float = 0.0
    features: dict[str, Any] = Field(default_factory=dict)


class SupervisorRequest(BaseModel):
    session: HarnessSession
    goal: Goal | None = None
    event: HarnessEvent
    recent_events: list[HarnessEvent] = Field(default_factory=list)
    scores: TrajectoryScores = Field(default_factory=TrajectoryScores)
    autonomy: str = "manage"
    notes: str = ""


class SupervisorResult(BaseModel):
    action: ProposedAction
    used_llm: bool = False
    model_name: str | None = None
    diagnosis: str = ""
    traces: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    inference_request_id: str | None = None
    backend: str | None = None
