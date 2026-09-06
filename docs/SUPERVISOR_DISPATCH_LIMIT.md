# Optional semantic-dispatch limit

Set `PEX_SUPERVISOR_MAX_DISPATCHES_PER_SESSION=20` before starting the bridge to
allow at most 20 newly reserved semantic dispatches for each session in that
bridge database. Omit the setting for existing unlimited-dispatch behavior.
The allowed range is 1–100000. The example is not a recommended spending budget.

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

No new mid-task inference is enabled by this setting. A user-facing budget editor,
aggregate account limits, exact per-model accounting and semantic trajectory
review remain separate unfinished requirements. Treat the retained planner
receipt as the audit source. When the latest projected action is a budget-skipped
NOOP, the desktop status says "Review skipped" and explains that PEX did not
verify that stop. This replaces worker completion narration, but never hides
offline/stale state, human decisions, blocked workers or drift. Concurrent
working counts remain visible. The notice describes the last review; it is not
an inventory of all exhausted sessions or proof that a limit is still configured.
A later projected action replaces it. There is no automatic spending escalation.
