"""WIP full-owned review request label for a scheduled, possibly forced stop.

No correction text or deterministic supervisor decision. The unchanged owned
planner/verifier independently reads public evidence and chooses its action.
"""


def staged_request_builder(public_builder):
    def build(arm,observation,session_id):
        request=public_builder(arm,observation,session_id)
        request.event.message_delta=(
            'Scheduled worker phase checkpoint. The last counted request may have '
            'forced textual finalization; this is not spontaneous task completion.')
        request.notes=(request.notes or '')+(
            '\nFrozen staged protocol: first phase allows at most8 requests/120 '
            'active seconds, second phase at most4 requests/60 active seconds. '
            'Finalization requests count inside these limits in both arms. '
            'Hidden acceptance remains unknown. Only a validated planner/verifier '
            'decision may authorize PEX continuation in the same worker session.')
        return request
    return build
