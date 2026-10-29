"""WIP full-owned review request label for a scheduled, possibly forced stop.

No correction text or deterministic supervisor decision. The unchanged owned
planner/verifier independently reads public evidence and chooses its action.
"""


from staged_envelope import PHASES


def staged_request_builder(public_builder):
    def build(arm,observation,session_id):
        request=public_builder(arm,observation,session_id)
        request.event.message_delta=(
            'Scheduled worker phase checkpoint. The last counted request may have '
            'forced textual finalization; this is not spontaneous task completion.')
        request.notes=(request.notes or '')+(
            f'\nFrozen staged protocol: first phase allows at most{PHASES[0].calls} requests/{PHASES[0].active_seconds} '
            f'active seconds, second phase at most{PHASES[1].calls} requests/{PHASES[1].active_seconds} active seconds. '
            'Finalization requests count inside these limits in both arms. '
            'Hidden acceptance remains unknown. Only a validated planner/verifier '
            'decision may authorize PEX continuation in the same worker session.')
        return request
    return build
