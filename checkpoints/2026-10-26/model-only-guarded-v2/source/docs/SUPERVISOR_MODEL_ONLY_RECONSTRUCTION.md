# Bounded model-only supervision reconstruction

**Local implementation and authored-model SDK tests, not live inference or a
qualified autonomous benchmark. Not deployed. Not V14 parity.**

## Guarded v2: live model-only operation is technically unavailable

`model_only_transport.qualified()` refuses **every production model adapter**.
There is no environment/configuration/provenance flag that can enable one.
Configuring a real provider yields `model_only_transport_unqualified` before
inference dispatch, with no model-dispatch reservation or worker feedback.
The loop, router, SDK wrapper, scheduled dispatch and pending worker-effect
recovery enforce this boundary. Terminal history still replays truthfully.
Supervisor startup/saved-choice/configuration preparation is also refused
before credential-store reads or provider-client construction in this mode.
AgentCore refuses model-only requests before runtime model loading. This does
not promise zero network activity for unrelated, configured worker adapters.

Local tests replace this admission function only for their exact authored
fixture class, under zero-network-attempt sentries. They test the implemented
decision machinery through the actual SDK, **not production transport
qualification**. Separate regressions exercise the unchanged deny-all gate,
including a standard SDK provider class without constructing a client.

The prior dated v1 source is preserved separately. Its documentation excluded
real BYOK but its code still accepted arbitrary stateless SDK providers; v2
closes that admission gap rather than rebuilding the missing managed transport.
Real operation remains blocked until separately reviewed control of provider
retries, dispatch ambiguity and accounting has been reconstructed.

The mode is an opt-in decision policy, separate from transport:
`PEX_SUPERVISOR_DECISION_MODE=supervisor_model_only` with
`PEX_SUPERVISOR_MODE=local`. The default decision policy remains `default`.
This is a source/configuration surface, not new UI functionality.

## Contract

- Under explicit local-test admission, an eligible STOP/material trajectory
  review uses the authored configured model through Strands. Production
  transports are refused. Pause, observation-only work and ineligible events
  remain silent.
- Only model-proposed `SEND_NUDGE` or `CONTINUE_SESSION` can authorize worker
  feedback. A model-selected NOOP stays NOOP. Other actions are vetoed.
- In particular, `REQUEST_VERIFICATION` is refused: its existing execution
  binder deliberately substitutes a bridge-authored probe script. That script
  must not be represented as exclusively model-authored benchmark feedback.
- Automatic sibling-context handoffs are also suppressed, including delayed
  followups from frozen model-only history and default-mode automatic effects
  that encounter a mode switch before worker I/O. Explicit manual operator
  handoffs are separate authority and remain unchanged.
- Main and independent-verifier agents must inspect and cite request-bound
  evidence. Owner/workspace identity, policy, capability, budget, cooldown,
  current session/goal authority and existing execution guards remain intact.
- Missing models, setup/call failures, invalid or absent usage, and uncertain
  transport never produce replacement deterministic feedback.
- The durable request and plan retain the decision mode. Unsent plans cannot
  cross decision modes; mode is rechecked after the inference authority await
  and after worker-effect claim. Completed history remains truthful. A dispatch
  marker is not a retry lease.
- Failed/ambiguous model dispatches retain `delivery_uncertain` reservations.
  Duplicate events and restart recovery do not call the model or resend work.
  Missing configuration is skipped without consuming a model-dispatch attempt.
- AgentCore/hybrid and public-web evidence are not enabled in this mode.
  No bounded-repository/remote-evidence feature is reconstructed here.

## Usage boundary

The local adapter implements the actual Strands `Model` interface and validates
SDK stream usage before Strands aggregation can coerce values (e.g. `0 + True`).
**This is not raw provider-wire validation.** Upstream provider SDKs may already
have normalized values before `Model.stream` emits them; OpenAI SDK 2.54 can
coerce boolean/string/floating usage values into Python integers. The checks
here cannot reconstruct those original wire types. A separately reviewed
managed transport would need validation before that normalization; this is an
additional reason that production admission stays deny-all in guarded v2.
Every stream must provide exactly one complete receipt. Missing, duplicate,
boolean, string, fractional, negative, nonfinite, unknown or oversized counters
fail closed. Input/output are strictly positive, `totalTokens` must equal their
sum, and optional cache counters must be nonnegative integers. Per-cycle,
per-invocation and aggregate input/output/total/cache counters must reconcile.
This intentionally rejects unsupported accounting shapes, including providers
whose cache/total semantics differ. It does not estimate missing values.

Main and verifier usage validation are durably recorded separately. Strands
SDK throttling retries are disabled (`retry_strategy=None`, verified with installed
1.53.0 and a throttling regression); this does not by itself qualify every SDK
recovery path (such as context-overflow handling). Provider-internal retries, transport acceptance,
billing, streaming cancellation and real-provider accounting remain
**unqualified**. This is not an accounting gateway rebuild.

## Evidence and restrictions

Tests use real Strands Agent/Model interfaces, SQLite and the real PEX pipeline,
but an authored model and an in-process synthetic worker. Four successful SDK
streams in a test are **not four external inference calls**. Test network
sentries block and count DNS/connect APIs, and assert zero attempts at teardown,
including caught attempts. Test commands use an empty environment, disposable
HOME, disabled provider loading and disabled AWS metadata discovery.

**Do not expose this recovered baseline publicly or use real BYOK credentials.**
Later owner/auth/origin/session hardening is missing from the restored source.
This guard does not restore it. Public deployment, real worker/provider pilots,
remote evidence, accounting and transport qualification require separate review.
The full backend suite, native desktop packaging, Windows vault runtime and
browser behavior are not newly qualified by these changes.
