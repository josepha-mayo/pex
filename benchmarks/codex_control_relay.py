"""Codex review routing with the pinned stateless Responses model contract."""

from benchmarks.opencode_control_relay import OpenCodeControlRelay
from benchmarks.responses_relay import PinnedResponsesRelay

REVIEW_SCHEMA = "pex.codex-review.v1"


class CodexControlRelay(OpenCodeControlRelay, PinnedResponsesRelay):
    """Share bounded review routing while selecting Responses validation.

    Cooperative initialization wraps the backend with PinnedResponsesRelay's
    completed-result guard before the common controller creates its budgets.
    Review callbacks must independently inspect the public task and run PEX
    in a separate boundary; worker messages remain untrusted observations.
    """

    review_schema = REVIEW_SCHEMA
