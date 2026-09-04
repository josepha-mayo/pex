from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pex_protocol.actions import ProposedAction
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession

INDEPENDENT_VERIFIER_EVIDENCE_TOOLS = frozenset(
    {
        "get_context",
        "get_recent_events",
        "get_scores",
        "get_session_state",
        "inspect_workspace",
        "inspect_git",
        "inspect_file",
        "inspect_artifact",
        "inspect_process",
        "run_verification",
    }
)


class TrajectoryScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drift: float = Field(default=0.0, ge=0.0, le=1.0)
    stagnation: float = Field(default=0.0, ge=0.0, le=1.0)
    premature_completion: float = Field(default=0.0, ge=0.0, le=1.0)
    claim_contradiction: float = Field(default=0.0, ge=0.0, le=1.0)
    features: dict[str, Any] = Field(default_factory=dict)


class SupervisorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: HarnessSession
    goal: Goal | None = None
    event: HarnessEvent
    recent_events: list[HarnessEvent] = Field(default_factory=list, max_length=1000)
    scores: TrajectoryScores = Field(default_factory=TrajectoryScores)
    autonomy: Literal["observe", "assist", "nudge", "manage", "autopilot"] = "manage"
    notes: str = Field(default="", max_length=65_536)

    @model_validator(mode="after")
    def require_bound_identity(self) -> "SupervisorRequest":
        if self.event.session_id != self.session.id:
            raise ValueError("event/session identity mismatch")
        if self.event.harness_type != self.session.harness_type:
            raise ValueError("event/session harness identity mismatch")
        _require_project_match(self.event.project_id, self.session.project_id, "event")
        for event in self.recent_events:
            if event.session_id != self.session.id:
                raise ValueError("recent event/session identity mismatch")
            if event.harness_type != self.session.harness_type:
                raise ValueError("recent event/session harness identity mismatch")
            _require_project_match(event.project_id, self.session.project_id, "recent event")
        if self.goal is not None:
            if self.session.goal_id != self.goal.id:
                raise ValueError("goal/session identity mismatch")
            if self.session.project_id is None:
                raise ValueError("goal/session project identity mismatch")
            _require_project_match(self.goal.project_id, self.session.project_id, "goal")
        return self


class IndependentVerifierReceipt(BaseModel):
    """Bounded verifier-only provenance for a semantic intervention decision."""

    model_config = ConfigDict(extra="forbid")

    approved: bool = Field(strict=True)
    status: str = Field(min_length=1, max_length=120)
    rationale: str = Field(default="", max_length=2_000)
    evidence: list[Annotated[str, Field(max_length=1_000)]] = Field(
        default_factory=list,
        max_length=20,
    )
    evidence_tools: list[Annotated[str, Field(max_length=128)]] = Field(
        default_factory=list,
        max_length=20,
    )
    model_call_count: int = Field(default=0, ge=0, le=1_000_000, strict=True)
    input_tokens: int = Field(
        default=0,
        ge=0,
        le=1_000_000_000_000,
        strict=True,
    )
    output_tokens: int = Field(
        default=0,
        ge=0,
        le=1_000_000_000_000,
        strict=True,
    )
    latency_ms: int = Field(default=0, ge=0, le=86_400_000, strict=True)

    def authorizes_intervention(self) -> bool:
        """Return whether this receipt carries minimum independent evidence."""

        return bool(
            self.approved is True
            and self.status == "approved"
            and self.model_call_count >= 1
            and any(item.strip() for item in self.evidence)
            and INDEPENDENT_VERIFIER_EVIDENCE_TOOLS.intersection(self.evidence_tools)
        )


class SupervisorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ProposedAction
    used_llm: bool = False
    model_name: str | None = None
    diagnosis: str = ""
    traces: list[str] = Field(default_factory=list, max_length=256)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    # Provider request ids are only populated when the provider/SDK exposes one.
    # PEX's own correlation id is deliberately separate so it cannot be mistaken
    # for proof that a provider accepted a request.
    inference_request_id: str | None = None
    local_invocation_id: str | None = None
    inference_status: Literal["not_attempted", "completed", "failed", "timeout"] = (
        "not_attempted"
    )
    model_call_count: int = Field(default=0, ge=0)
    runtime: str | None = None
    runtime_version: str | None = None
    model_class: str | None = None
    provider: str | None = None
    base_url: str | None = None
    auth_mode: str | None = None
    config_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    evidence_tools: list[str] = Field(default_factory=list, max_length=128)
    independent_verifier: IndependentVerifierReceipt | None = None
    backend: str | None = None
    # Transport provenance is separate from model inference provenance. An AWS
    # request id proves that AgentCore accepted a transport request; it is not a
    # model provider's inference request id.
    execution_mode: str | None = None
    transport: str | None = None
    # PEX-generated correlation id that binds a response to one exact transport
    # invocation. This is distinct from both the model call id and AWS request id.
    transport_invocation_id: str | None = None
    transport_request_id: str | None = None
    transport_status: Literal["not_attempted", "completed", "failed"] = "not_attempted"


def _project_key(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/").casefold()


def _require_project_match(
    observed: str | None,
    expected: str | None,
    label: str,
) -> None:
    if observed is None:
        return
    if expected is None or _project_key(observed) != _project_key(expected):
        raise ValueError(f"{label}/session project identity mismatch")
