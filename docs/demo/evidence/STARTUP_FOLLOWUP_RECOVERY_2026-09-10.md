# Startup follow-up recovery audit — 10 September 2026

Offline source inspection found inconsistent invalid-row handling in
`Pipeline.recover_unfinished_events`. Main event recovery catches `ValueError`,
logs the invalid event and continues to other sessions. Follow-up recovery did
not have that handling. Its drain revalidates persisted processing inputs and
can raise a validation error before handoff work. Because the application awaits
recovery before yielding its lifespan, such an error can abort startup.

The follow-up loop now applies the same narrow `ValueError` handling. It retains
the invalid row, logs the failure, excludes that event from the recovered list,
and continues to later distinct event IDs. It does not declare the invalid row
successful, change delivery receipts, bypass workspace authority, or swallow
runtime/storage failures. Duplicate follow-up event IDs remain deduplicated.

Verification on the edited source:

- `.venv/Scripts/python.exe -m pytest tests/unit/test_event_processing_pipeline.py -q`:
  **41 passed in 45.57 seconds**, exit 0.
- Ruff on the pipeline and test file: passed.
- `git diff --check`: passed.

The two new tests inject an invalid binding followed by a healthy event and a
separate runtime failure. They prove the recovery-loop behavior, not that the
user's persisted profile contains an invalid binding.

The earlier packaged first-start timeout is **not causally explained or fixed
by this evidence**. Source review also confirmed that saved supervisor activation
runs in a bounded background task, while event recovery is awaited before HTTP
readiness. The existing next-launch phase trace is still needed to distinguish
extraction/import time from database, adapter and recovery time.

No desktop launch, live model invocation, profile edit, heavy build or process
termination occurred. The existing `4de1db8` package does not contain this repair;
rebuild and native acceptance remain pending while the user uses the PC.
