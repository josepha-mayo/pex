from datetime import datetime
from typing import Annotated, Any, Literal, Self
from unicodedata import category

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pex_protocol.actions import ProposedAction
from pex_protocol.enums import (
    ContextKind,
    DecisionSource,
    DecisionStatus,
    Sensitivity,
    SourceKind,
)
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession

INDEPENDENT_VERIFIER_EVIDENCE_TOOLS = frozenset(
    {
        "get_context",
        "get_context_items",
        "get_decisions",
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

_ContextId = Annotated[str, Field(min_length=1, max_length=512)]


def _validate_context_id(value: str) -> str:
    if value != value.strip() or any(category(char).startswith("C") for char in value):
        raise ValueError("supervisor context identifiers must be trimmed and contain no controls")
    return value


def _aware(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


class SupervisorContextItem(BaseModel):
    """A bounded, already-selected durable context record visible to the supervisor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: _ContextId
    project_id: str = Field(min_length=1, max_length=4_096)
    goal_id: str | None = Field(default=None, min_length=1, max_length=512)
    kind: ContextKind
    content: str = Field(min_length=1, max_length=2_000)
    semantic_kind: str | None = Field(default=None, min_length=1, max_length=80)
    status: str = Field(default="active", min_length=1, max_length=80)
    source_refs: tuple[_ContextId, ...] = Field(default_factory=tuple, max_length=16)
    source_session_id: str | None = Field(default=None, min_length=1, max_length=512)
    provenance: SourceKind
    confidence: float = Field(ge=0.0, le=1.0)
    verified: bool = Field(default=False, strict=True)
    relevance_tags: tuple[Annotated[str, Field(min_length=1, max_length=120)], ...] = Field(
        default_factory=tuple,
        max_length=16,
    )
    valid_from: datetime
    stale_after: datetime | None = None
    supersedes: str | None = Field(default=None, min_length=1, max_length=512)
    sensitivity: Literal[Sensitivity.PUBLIC, Sensitivity.INTERNAL]

    @field_validator(
        "id",
        "project_id",
        "goal_id",
        "semantic_kind",
        "status",
        "source_session_id",
        "supersedes",
    )
    @classmethod
    def validate_ids(cls, value: str | None) -> str | None:
        return _validate_context_id(value) if value is not None else value

    @field_validator("source_refs")
    @classmethod
    def validate_source_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _validate_context_id(value)
        if len(values) != len(set(values)):
            raise ValueError("supervisor context source references must be unique")
        return values

    @field_validator("relevance_tags")
    @classmethod
    def validate_relevance_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("supervisor context relevance tags must be unique")
        for value in values:
            _validate_context_id(value)
        return values

    @model_validator(mode="after")
    def validate_validity(self) -> Self:
        _aware(self.valid_from, label="supervisor context valid_from")
        if self.verified and self.provenance not in {SourceKind.TEST, SourceKind.WORKSPACE}:
            raise ValueError(
                "verified supervisor context requires test or workspace provenance"
            )
        if self.stale_after is not None:
            _aware(self.stale_after, label="supervisor context stale_after")
            if self.stale_after <= self.valid_from:
                raise ValueError("supervisor context stale_after must follow valid_from")
        return self


class SupervisorDecisionItem(BaseModel):
    """A bounded active or unresolved durable decision visible to the supervisor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: _ContextId
    goal_id: str = Field(min_length=1, max_length=512)
    statement: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(default="", max_length=1_000)
    alternatives_rejected: tuple[Annotated[str, Field(min_length=1, max_length=1_000)], ...] = (
        Field(default_factory=tuple, max_length=12)
    )
    scope: str = Field(default="", max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    source: DecisionSource
    status: Literal[DecisionStatus.ACTIVE, DecisionStatus.UNCERTAIN]
    created_at: datetime
    source_refs: tuple[_ContextId, ...] = Field(default_factory=tuple, max_length=16)
    source_session_id: str | None = Field(default=None, min_length=1, max_length=512)
    sensitivity: Literal[Sensitivity.PUBLIC, Sensitivity.INTERNAL]

    @field_validator("id", "goal_id", "source_session_id")
    @classmethod
    def validate_ids(cls, value: str | None) -> str | None:
        return _validate_context_id(value) if value is not None else value

    @field_validator("source_refs")
    @classmethod
    def validate_source_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _validate_context_id(value)
        if len(values) != len(set(values)):
            raise ValueError("supervisor decision source references must be unique")
        return values

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _aware(value, label="supervisor decision created_at")


class SupervisorContextEnvelope(BaseModel):
    """Request-bound context selected from PEX's durable project/goal state."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_id: Literal["pex.supervisor-context.v1"] = Field(
        default="pex.supervisor-context.v1",
        alias="schema",
    )
    target_session_id: str = Field(min_length=1, max_length=512)
    project_id: str | None = Field(default=None, min_length=1, max_length=4_096)
    goal_id: str | None = Field(default=None, min_length=1, max_length=512)
    observed_at: datetime
    context_items: tuple[SupervisorContextItem, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )
    decisions: tuple[SupervisorDecisionItem, ...] = Field(default_factory=tuple, max_length=24)
    offered_context_ids: tuple[_ContextId, ...] = Field(default_factory=tuple, max_length=32)
    offered_decision_ids: tuple[_ContextId, ...] = Field(default_factory=tuple, max_length=24)

    @field_validator("target_session_id", "project_id", "goal_id")
    @classmethod
    def validate_ids(cls, value: str | None) -> str | None:
        return _validate_context_id(value) if value is not None else value

    @field_validator("offered_context_ids", "offered_decision_ids")
    @classmethod
    def validate_selected_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _validate_context_id(value)
        if len(values) != len(set(values)):
            raise ValueError("supervisor context selection identifiers must be unique")
        return values

    @model_validator(mode="after")
    def require_bound_selection(self) -> Self:
        _aware(self.observed_at, label="supervisor context observed_at")
        if self.offered_context_ids != tuple(item.id for item in self.context_items):
            raise ValueError("supervisor offered context ids do not match context items")
        if self.offered_decision_ids != tuple(item.id for item in self.decisions):
            raise ValueError("supervisor offered decision ids do not match decisions")
        if (self.project_id is None or self.goal_id is None) and (
            self.context_items or self.decisions
        ):
            raise ValueError("unbound supervisor context must be empty")
        for item in self.context_items:
            if not _project_matches(item.project_id, self.project_id):
                raise ValueError("supervisor context item project identity mismatch")
            if item.goal_id not in {None, self.goal_id}:
                raise ValueError("supervisor context item goal identity mismatch")
            if item.valid_from > self.observed_at or (
                item.stale_after is not None and item.stale_after <= self.observed_at
            ):
                raise ValueError("supervisor context item is not valid at observation time")
        for decision in self.decisions:
            if decision.goal_id != self.goal_id:
                raise ValueError("supervisor decision goal identity mismatch")
            if decision.created_at > self.observed_at:
                raise ValueError("supervisor decision postdates context observation")
        total_text = sum(len(item.content) for item in self.context_items) + sum(
            len(item.statement)
            + len(item.rationale)
            + sum(len(value) for value in item.alternatives_rejected)
            for item in self.decisions
        )
        if total_text > 48_000:
            raise ValueError("supervisor context text exceeds the aggregate size limit")
        return self


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
    supervisor_context: SupervisorContextEnvelope | None = None
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
        if self.supervisor_context is not None:
            context = self.supervisor_context
            if context.target_session_id != self.session.id:
                raise ValueError("supervisor context/session identity mismatch")
            if not _project_matches(context.project_id, self.session.project_id):
                raise ValueError("supervisor context/session project identity mismatch")
            expected_goal_id = self.goal.id if self.goal is not None else None
            if context.goal_id != expected_goal_id:
                raise ValueError("supervisor context/request goal identity mismatch")
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


def _project_matches(observed: str | None, expected: str | None) -> bool:
    if observed is None or expected is None:
        return observed is expected
    return _project_key(observed) == _project_key(expected)


def _require_project_match(
    observed: str | None,
    expected: str | None,
    label: str,
) -> None:
    if observed is None:
        return
    if expected is None or _project_key(observed) != _project_key(expected):
        raise ValueError(f"{label}/session project identity mismatch")
