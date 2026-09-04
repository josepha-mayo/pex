from datetime import datetime
from typing import Annotated, Any, Literal, Self
from unicodedata import category, normalize

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pex_protocol.enums import ContextKind, EventType, HarnessType, Sensitivity, SourceKind


class ProgressEvidenceReference(BaseModel):
    """A closed, bounded reference to evidence already stored by PEX."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["event", "context"]
    id: str = Field(min_length=1, max_length=512)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if value != value.strip() or any(category(char).startswith("C") for char in value):
            raise ValueError("evidence reference id must be a non-control string")
        return value


class ProgressReport(BaseModel):
    """Idempotent, evidence-linked progress accepted by the MCP boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Deliberately distinct from MCP's per-call JSON-RPC request ID: callers
    # reuse this value when retrying the same logical progress report.
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    summary: str = Field(min_length=1, max_length=4_000)
    evidence_refs: tuple[ProgressEvidenceReference, ...] = Field(
        min_length=1,
        max_length=24,
    )

    @model_validator(mode="after")
    def reject_duplicate_evidence_refs(self) -> Self:
        keys = [(item.type, item.id) for item in self.evidence_refs]
        if len(set(keys)) != len(keys):
            raise ValueError("progress evidence references must be unique by type and id")
        return self


class ClaimVerificationRequest(BaseModel):
    """Idempotent, bounded request to verify one worker-authored claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    claim: str = Field(min_length=1, max_length=4_000)


class HumanDecisionRequest(BaseModel):
    """Idempotent, bounded request to route one judgment to the human."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    question: str = Field(min_length=1, max_length=4_000)
    options: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(
        default_factory=tuple,
        max_length=16,
    )
    urgency: Literal["normal", "high", "blocking"] = "normal"
    context: str = Field(default="", max_length=4_000)

    @field_validator("question", "context")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if value != value.strip() or any(category(char).startswith("C") for char in value):
            raise ValueError("decision text must be trimmed and contain no controls")
        return value

    @field_validator("options")
    @classmethod
    def validate_options(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for value in values:
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 500
                or value != value.strip()
                or any(category(char).startswith("C") for char in value)
            ):
                raise ValueError(
                    "decision options must be nonblank trimmed strings of at most 500 characters"
                )
            normalized.append(normalize("NFKC", value).casefold())
        if len(normalized) != len(set(normalized)):
            raise ValueError(
                "decision options must be distinct after Unicode normalization and case folding"
            )
        return values


class ContextHandoffRequest(BaseModel):
    """Idempotent, bounded request to route context to one existing session."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    target_session_id: str = Field(min_length=1, max_length=512)
    token_budget: int = Field(default=2_000, ge=256, le=12_000)

    @field_validator("target_session_id")
    @classmethod
    def validate_target_session_id(cls, value: str) -> str:
        if value != value.strip() or any(category(char).startswith("C") for char in value):
            raise ValueError("target session id must be trimmed and contain no controls")
        return value


class ContextItem(BaseModel):
    id: str
    project_id: str
    goal_id: str | None = None
    kind: ContextKind
    content: str
    source_refs: list[str] = Field(default_factory=list)
    provenance: SourceKind = SourceKind.PEX
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_tags: list[str] = Field(default_factory=list)
    valid_from: datetime
    stale_after: datetime | None = None
    supersedes: str | None = None
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextBundle(BaseModel):
    goal_id: str
    target_session_id: str
    source_session_ids: list[str] = Field(default_factory=list)
    goal_summary: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    critical_decisions: list[str] = Field(default_factory=list)
    relevant_artifacts: list[str] = Field(default_factory=list)
    direct_evidence: list[str] = Field(default_factory=list)
    recent_progress: list[str] = Field(default_factory=list)
    next_objective: str = ""
    do_not_redo: list[str] = Field(default_factory=list)
    deep_links: list[str] = Field(default_factory=list)
    items: list[ContextItem] = Field(default_factory=list)
    token_estimate: int = 0
    created_at: datetime


class HandoffAssimilationEvidence(BaseModel):
    """Immutable evidence that a handoff target acted on exact transferred context.

    This is intentionally evidence, not a correctness or comprehension verdict.  A
    worker-authored acknowledgement remains unverified, while an exact artifact
    read/edit is only behavioral evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)

    schema_id: Literal["pex.handoff-assimilation-evidence.v1"] = Field(
        default="pex.handoff-assimilation-evidence.v1",
        alias="schema",
    )
    evidence_id: str = Field(min_length=1, max_length=128)
    effect_id: str = Field(min_length=1, max_length=128)
    handoff_intervention_id: str = Field(min_length=1, max_length=128)
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    dispatch_started_at: datetime
    dispatch_version: int = Field(ge=1)
    dispatch_target_accept_seq_through: int = Field(ge=0)
    source_session_id: str = Field(min_length=1, max_length=512)
    source_vendor_session_id: str = Field(min_length=1, max_length=512)
    source_harness_type: HarnessType
    target_session_id: str = Field(min_length=1, max_length=512)
    target_vendor_session_id: str = Field(min_length=1, max_length=512)
    target_harness_type: HarnessType
    source_project_id: str = Field(min_length=1, max_length=4_096)
    target_project_id: str = Field(min_length=1, max_length=4_096)
    source_project_binding: str = Field(min_length=1, max_length=512)
    target_project_binding: str = Field(min_length=1, max_length=512)
    goal_project_binding: str = Field(min_length=1, max_length=512)
    goal_id: str = Field(min_length=1, max_length=512)
    target_event_id: str = Field(min_length=1, max_length=512)
    target_event_type: EventType
    target_event_accept_seq: int | None = Field(default=None, ge=1)
    target_mutation_id: str | None = Field(default=None, min_length=1, max_length=128)
    evidence_kind: Literal["artifact_read", "artifact_edit", "target_acknowledgement"]
    evidence_strength: Literal["behavioral", "self_attested"]
    matched_context_item_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    matched_artifact_paths: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    target_event_ts: datetime
    observed_at: datetime
    status: Literal["observed"] = "observed"
    verified: Literal[False] = False
    assimilation_proven: Literal[False] = False

    @model_validator(mode="after")
    def validate_evidence_shape(self) -> Self:
        if len(set(self.matched_context_item_ids)) != len(self.matched_context_item_ids):
            raise ValueError("matched handoff context item ids must be unique")
        if len(set(self.matched_artifact_paths)) != len(self.matched_artifact_paths):
            raise ValueError("matched handoff artifact paths must be unique")
        if self.evidence_kind in {"artifact_read", "artifact_edit"}:
            if (
                self.evidence_strength != "behavioral"
                or not self.matched_artifact_paths
                or self.target_event_accept_seq is None
                or self.target_mutation_id is not None
            ):
                raise ValueError("artifact action evidence requires behavioral path evidence")
        elif (
            self.evidence_strength != "self_attested"
            or self.matched_artifact_paths
            or self.target_mutation_id is None
            or self.target_event_accept_seq is not None
        ):
            raise ValueError(
                "explicit context reference evidence cannot claim artifact action paths"
            )
        return self
