# Completion fence and pet feedback repair — 10 September 2026

## Live-probe integrity

The failed ten-case run is preserved unchanged; see
[its original report](QUIET_BATCH_739C8D3_2026-09-10.md). No provider calls were
made for this repair and the free-route rate limit was not retried.

`benchmarks/opencode_completion.py` requires an idle OpenCode status and the
newest assistant's successful terminal response, linked to the newest user.
Admitted PEX follow-ups must appear in history. Busy/retry, missing completion,
errors, wrong parents/sessions and malformed snapshots do not pass. The twelve
second quiet interval restarts on new events, generations, follow-ups or
unsettled journals. The runner rereads HTTP and journal/action state before
sealing. Timeouts remain incomplete, not proved recovery failures.

OpenCode's [status implementation](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/status.ts)
removes idle sessions from the status map. Only a successfully fetched dictionary
may interpret an absent session as idle; failed requests are not empty maps.
That source was checked on 10 September; this is not a vendor-version pin.

The reproducible runner is now tracked at `scripts/opencode_quiet_ten.py`.
It requires an explicit new `--run-name`, a clean checkout, the exact saved
Zen/Muse configuration and a direct OpenCode executable. It creates a new
directory under `build/`, archives its own source and completion helper, records
their hashes, stops at the first nonpassing case, and closes only its retained
server handle. Do not rerun an archived script or overwrite old evidence.
An example command is intentionally not a direction to start paid/free calls;
verify provider availability, privacy and billing conditions first.

Verification:

- New helper/CLI suite: **36 passed**, exit 0, 4.34 seconds.
- Surrounding OpenCode suite, including the first 33 helper cases:
  **129 passed**, exit 0, 22.19 seconds.
- Ruff and Python compilation pass.
- Offline replay of all ten retained worker histories: the first nine have
  terminal generations; the unfinished tenth is rejected even assuming idle.
  This replay does not establish historical idle status or repair the live run.
- Independent read-only review found the targeted stale-generation path closed.

Limits: HTTP and local-store observations are not atomic. This dedicated probe
does not intentionally admit out-of-band human prompts. The follow-up count is
not a general multi-client high-watermark protocol. Runner final rereads have
not been integration-tested under a concurrently injected external prompt.
There is no new live pass or formal comparative score.

## Native pet check and feedback repair

The existing `06c6b73` package remained responsive during Settings navigation.
Eight built-in pet previews loaded. Showing the selected Von overlay rendered
transparently. Its minus button dismissed only the status bubble; its separate
cross updated the Show desktop pet checkbox to off. The main app stayed open.
One accessibility index lookup failed; a fresh screenshot-based click worked.
Only PEX windows received input; no provider, credential or worker action ran.

This exposed stale Settings feedback: after hiding the pet from its own window,
the old toast still said `Desktop pet shown.` Source now reconciles only pet
visibility confirmations across window events and checks current visibility
after asynchronous show/hide completes. Unrelated errors/feedback are retained.

The first full desktop test run was stopped after its race test waited on a
module imported before its fake Tauri environment existed: **273 passed, one
failed**, exit 1, 207.37 seconds. Only the identity-checked test child was stopped;
not PEX, Codex or another agent. Race tests now import fresh module instances
and have explicit five-second timeouts. Assertions were not weakened.

- Targeted pet suite: **16 passed**, exit 0, 2.39 seconds.
- Fresh full desktop suite: **277 passed**, zero failed, exit 0, 3.83 seconds.
- Production TypeScript/Vite build: exit 0.

The native observation above predates the feedback source fix. The running app
and staged installers remain the earlier package until a new package is built
and checked. No claim of packaged verification for this source repair, fresh-user
installation, long-term freeze clearance, video or submission is made.
