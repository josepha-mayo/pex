from pydantic import BaseModel, Field


class AgentFingerprint(BaseModel):
    harness: str
    model: str
    model_settings_hash: str = ""
    project_class: str | None = None
    observed_sessions: int = 0
    strengths: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    premature_stop_rate: float = 0.0
    repeated_tool_rate: float = 0.0
    context_degradation_profile: dict[str, float] = Field(default_factory=dict)
    approval_behavior: dict[str, float] = Field(default_factory=dict)
    token_efficiency: float = 0.0
    verified_success_rate: float = 0.0
    recommended_overlays: list[str] = Field(default_factory=list)
    sample_count: int = 0
    confidence: float = 0.0
