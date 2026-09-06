# Optional semantic-dispatch limit

Set `PEX_SUPERVISOR_MAX_DISPATCHES_PER_SESSION=20` before starting the bridge to
allow at most 20 newly reserved semantic dispatches for each session in that
bridge database. Omit the setting for existing unlimited-dispatch behavior.
The allowed range is 1–100000. The example is not a recommended spending budget.

In the current desktop source, Settings → Supervisor also has **Saved review
limit per session**. Enter an integer and choose Save supervisor to persist an
override in the secret-free supervisor configuration. Leave it blank to inherit
the bridge's startup setting. This does not reset reservations, cancel in-flight
work, or change the model's credential destination. A stale settings revision,
invalid value or failed config write cannot commit a new override. The existing
startup Settings object remains unchanged; the pipeline computes the effective
cap from the saved override or startup fallback.

This is a **dispatch-count guard, not a dollar, token or inner-model-call cap**.
One dispatch can include multiple Strands/verifier calls. Provider work may
outlive a caller timeout. A free-provider label is not a billing guarantee.

## Behavior

- Only dispatches classified as semantic by the existing eligibility gate count.
  Ordinary deterministic processing does not consume this allowance.
- Reservation and the planner's transition to dispatching occur in one SQLite
  transaction, after claim, ordering and workspace-authority checks.
- Failed, timed-out, cancelled or ambiguous attempts are not refunded.
- Replaying the same durable event does not obtain another reservation.
- Reservations persist across bridge restart. They are retained separately from
  event rows so deleting an event cannot silently replenish the allowance.
- Exhaustion produces a durable skipped planner receipt with
  `supervisor_dispatch_budget_exhausted`, `provider_started=false` and NOOP.
  PEX does not send a correction solely because the budget is exhausted.
- The cap is per session, not shared across all sessions or AWS/API accounts.
  It counts reservations made while the setting is enabled, not unrecorded
  historical calls made before configuration. Increasing the configured limit
  permits additional reservations; there is no automatic reset window.

The authenticated supervisor GET and model-save responses expose the effective
pipeline setting as `max_dispatches_per_session`, and the saved override as
`dispatch_limit_override`. The effective notice distinguishes null (no configured
cap) from missing/invalid/unavailable data (unknown). Editing is disabled when
the bridge does not expose the new override field. A model-only PATCH that omits
the field preserves the saved override. This
does not show remaining reservations, account spend or native-verified usage.

A finite effective cap enables the bounded repeated-command-failure review in
`TRAJECTORY_SEMANTIC_REVIEW.md`, including durable coalescing and 60-second pacing.
If the cap is removed before a frozen candidate reaches dispatch, the planner
records `trajectory_review_disabled` with no provider call. Aggregate account
limits, remaining-count presentation, exact per-model accounting and broader
trajectory review remain unfinished. Treat the retained planner
receipt as the audit source. When the latest projected action is a budget-skipped
NOOP, the desktop status says "Review skipped" and explains that PEX did not
verify that stop. This replaces worker completion narration, but never hides
offline/stale state, human decisions, blocked workers or drift. Concurrent
working counts remain visible. The notice describes the last review; it is not
an inventory of all exhausted sessions or proof that a limit is still configured.
A later projected action replaces it. There is no automatic spending escalation.
