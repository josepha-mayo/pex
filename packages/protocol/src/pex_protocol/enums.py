from enum import StrEnum


class HarnessType(StrEnum):
    CURSOR = "cursor"
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"
    DEVIN = "devin"
    GROK_BUILD = "grok_build"
    GROK_BOT = "grok_bot"
    PI = "pi"
    OMP = "omp"
    HERMES = "hermes"
    PRIME = "prime"
    ZCODE = "zcode"
    KIMI = "kimi"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    SYNTHETIC = "synthetic"
    UNKNOWN = "unknown"


class SessionStatus(StrEnum):
    DISCOVERED = "discovered"
    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    NEEDS_DECISION = "needs_decision"
    DRIFTING = "drifting"
    VERIFYING = "verifying"
    STOPPED = "stopped"
    ERROR = "error"
    DETACHED = "detached"


class EventType(StrEnum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    MESSAGE_DELTA = "message_delta"
    AGENT_THOUGHT = "agent_thought"
    AGENT_RESPONSE = "agent_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_FAILURE = "tool_failure"
    FILE_EDIT = "file_edit"
    FILE_READ = "file_read"
    SHELL = "shell"
    PERMISSION_REQUEST = "permission_request"
    STOP = "stop"
    COMPACTION = "compaction"
    USER_PROMPT = "user_prompt"
    STATUS = "status"
    TOKEN_USAGE = "token_usage"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class EventPhase(StrEnum):
    BEFORE = "before"
    AFTER = "after"
    DURING = "during"
    TERMINAL = "terminal"


class DecisionSource(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    INFERRED = "inferred"
    PEX = "pex"


class DecisionStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    UNCERTAIN = "uncertain"


class ContextKind(StrEnum):
    FACT = "fact"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    ARTIFACT = "artifact"
    RESULT = "result"
    HYPOTHESIS = "hypothesis"
    WARNING = "warning"
    CLAIM = "claim"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SECRET = "secret"
    LOCAL_ONLY = "local_only"


class SourceKind(StrEnum):
    HUMAN = "human"
    HARNESS = "harness"
    WORKSPACE = "workspace"
    TEST = "test"
    GIT = "git"
    PEX = "pex"


class AutonomyLevel(StrEnum):
    OBSERVE = "observe"
    ASSIST = "assist"
    NUDGE = "nudge"
    MANAGE = "manage"
    AUTOPILOT = "autopilot"


class PolicyVerdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK_HUMAN = "ask_human"


class Authority(StrEnum):
    LOCAL_POLICY = "local_policy"
    HUMAN = "human"
    SUPERVISOR_PROPOSAL = "supervisor_proposal"
