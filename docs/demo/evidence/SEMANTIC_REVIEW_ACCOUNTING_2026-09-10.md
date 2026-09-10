# Quiet-case reporting: failed setup cannot hide behind a prior success

Source inspection found that the tracked OpenCode restraint runner built its
review list using only results with `used_llm is True`. It then required every
result in that filtered list to have completed inference. A previous successful
review plus a later `used_llm=False, inference_status=failed` setup/reconciliation
result could therefore satisfy that predicate. This is a reporting defect found
offline, not an assertion that the archived run exhibited it.

The production supervisor can legitimately report that combination when Strands
setup fails or a semantic effect requires deterministic reconciliation. Silence
after that failure is not a successful model-backed quiet decision.

`semantic_reviews_succeeded` now checks every recorded supervisor result in the
unfiltered processing journal. At least one real completed model review is
required. Explicit deterministic `not_attempted` triage and plan-free record-only
events do not pretend to be inference, but failed, timed-out, contradictory or
malformed results reject the clean-case claim. The worker generation fence,
artifact checks, event settlement and no-followup checks are unchanged.

The runner uses this predicate for `all_semantic_reviews_completed` and the final
pass decision. Its existing model-marked review/token counters retain their
meaning; the new predicate does not fabricate usage for setup failures.

Verification: `tests/unit/test_opencode_completion.py`, **50 passed in 4.90
seconds**, exit 0. Ruff passes for the helper, runner and test file. New tests
cover a real successful review, no review, ordinary deterministic triage,
failed/timeout results with either used_llm value before and after a success,
malformed/contradictory results and the runner's unfiltered-journal wiring.

Read-only inspection of all ten archived case journals under
`build/opencode-quiet-ten-739c8d3-20260910-r1` found 13 completed model-backed
results, zero failed/timeout results and zero unknown inference statuses.
Consequently this issue does not change that report: nine valid quiet cases;
tenth worker recovery observation incomplete after its provider rate limit.
No new live inference, benchmark score, native UI result or cloud deployment is
claimed. No archived receipt was rewritten.
