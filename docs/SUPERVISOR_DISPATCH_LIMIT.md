# Semantic-dispatch limit

PEX defaults to at most **three** newly reserved semantic dispatches for each
worker session in the bridge database. This bounds fresh-install BYOK usage and
enables the paced trajectory-review path. Set
`PEX_SUPERVISOR_MAX_DISPATCHES_PER_SESSION=20` before starting the bridge only
when a longer session deliberately needs a higher cap. The allowed range is
1–100000; 20 is an example, not a recommended spending budget.

In the current desktop source, Settings → Supervisor also has **Saved review
limit per session**. Enter an integer and choose Save supervisor to persist an
override in the secret-free supervisor configuration. Leave it blank to inherit
the bridge's startup setting (three unless explicitly changed). This does not reset reservations, cancel in-flight
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
- A router that definitively has no local model or configured remote client is
  skipped before reservation (`supervisor_unavailable`). This spends neither
  the cap nor trajectory coalescing key. Later material evidence can be reviewed
  after configuration succeeds; no old event is automatically replayed.
- Exception for local STOP triage: deterministic evidence checks still run without
  a model and can produce exact evidence-backed corrections. That route is frozen
  before dispatch and cannot invoke a provider configured during an await. It
  consumes no semantic reservation. This is not proof of semantic supervision.
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
does not report account spend or native-verified usage.

Inspector now shows each session's remaining review dispatches from the retained
reservation table. Pet and command-deck snapshots include
`supervisor_review_allowance` (`limit`, `reserved`, `remaining`, `observed_at`).
The indexed read batches at most 1000 requested session IDs; it does not derive
counts from events or model narration. Lowering a limit below reservations shows
zero remaining; removing the limit shows null, not an invented unlimited balance.
The UI labels numbers as the last refresh, rejects invalid or older-than-30-second
snapshots and hides numbers when canonical state is unavailable. A delayed pet
snapshot cannot replace a newer allowance from the command deck. Counts cover
only cap-enabled reservations, not historical uncapped dispatches, inner model
calls, tokens or dollars. No extra polling or provider invocation was added.

A finite effective cap enables the bounded repeated-command-failure review in
`TRAJECTORY_SEMANTIC_REVIEW.md`, including durable coalescing and 60-second pacing.
If the cap is removed before a frozen candidate reaches dispatch, the planner
records `trajectory_review_disabled` with no provider call. Aggregate account
limits, native remaining-count validation, exact per-model accounting and broader
trajectory review remain unfinished. Treat the retained planner
receipt as the audit source. When the latest projected action is a budget-skipped
NOOP, the desktop status says "Review skipped" and explains that PEX did not
verify that stop. This replaces worker completion narration, but never hides
offline/stale state, human decisions, blocked workers or drift. Concurrent
working counts remain visible. The notice describes the last review; it is not
an inventory of all exhausted sessions or proof that a limit is still configured.
A later projected action replaces it. There is no automatic spending escalation.
The corresponding unavailable-supervisor status says "Review unavailable",
not verified completion, and preserves concurrent working counts and higher
priority offline/human-decision states.
