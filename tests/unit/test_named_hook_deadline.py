from pex_bridge.app import (
    NAMED_HOOK_EVENT_PIPELINE_TIMEOUT_SECONDS,
    NAMED_HOOK_STOP_PIPELINE_TIMEOUT_SECONDS,
    _named_hook_pipeline_timeout,
)
from pex_protocol.enums import EventType


def test_observe_only_hermes_lifecycle_hooks_do_not_hold_the_bridge_for_stop_budget():
    for hook_name in ("on_session_end", "on_session_finalize"):
        assert (
            _named_hook_pipeline_timeout("hermes", hook_name, EventType.STOP)
            == NAMED_HOOK_EVENT_PIPELINE_TIMEOUT_SECONDS
        )


def test_stop_hooks_with_actionable_responses_keep_the_semantic_budget():
    assert (
        _named_hook_pipeline_timeout("claude_code", "Stop", EventType.STOP)
        == NAMED_HOOK_STOP_PIPELINE_TIMEOUT_SECONDS
    )
    assert (
        _named_hook_pipeline_timeout("qwen", "Stop", EventType.STOP)
        == NAMED_HOOK_STOP_PIPELINE_TIMEOUT_SECONDS
    )
