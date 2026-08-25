from enum import StrEnum

from pydantic import BaseModel, Field


class ControlGranularity(StrEnum):
    EVENT = "event"
    TURN = "turn"
    SESSION = "session"
    UI_ONLY = "ui_only"


class AdapterSupportLabel(StrEnum):
    DEEP = "deep"
    STRONG = "strong"
    BASIC = "basic"
    OBSERVE_ONLY = "observe_only"
    EXPERIMENTAL = "experimental"
    UNAVAILABLE = "unavailable"


class AdapterCapabilities(BaseModel):
    observe_messages: bool = False
    observe_thought_events: bool = False
    observe_tool_calls: bool = False
    observe_file_edits: bool = False
    observe_shell: bool = False
    observe_context_compaction: bool = False
    observe_tokens: bool = False
    observe_permissions: bool = False
    observe_session_status: bool = False

    send_message: bool = False
    inject_context: bool = False
    approve: bool = False
    deny: bool = False
    start: bool = False
    stop: bool = False
    resume: bool = False
    fork: bool = False
    summarize: bool = False
    modify_config: bool = False
    modify_system_instructions: bool = False
    modify_tools: bool = False
    modify_mcp: bool = False
    modify_model: bool = False
    modify_reasoning_effort: bool = False
    focus_ui: bool = False

    control_granularity: ControlGranularity = ControlGranularity.SESSION
    trust_level: float = Field(default=0.0, ge=0.0, le=1.0)
    support_label: AdapterSupportLabel = AdapterSupportLabel.UNAVAILABLE
    notes: str = ""

    def supports(self, capability: str) -> bool:
        value = getattr(self, capability, False)
        return bool(value)
