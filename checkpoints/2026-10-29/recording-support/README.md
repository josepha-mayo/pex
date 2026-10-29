# Private current-run status recording support

This utility is **not a benchmark launcher** and makes no provider calls. It has
not started recording. Root owns CUA, reservation of a dedicated safe window, the
approved feed producer, excerpt privacy review, and capture launch/stop. Do not
film waiting before a fresh run has actually been admitted.

## Evidence / privacy contract

- `follow` reads only a root-approved current-run `safe-display.jsonl`; it does
  **not** inspect raw request/response files, credentials, databases, workspace
  source, or hidden grading artifacts. Nonempty prior feed, wrong run, old time,
  malformed record, unknown field, or unapproved excerpt stops/refuses display.
- It presents **live status recording, not a full model-output video**. Real
  model calls must be evidenced by actual validated receipts written by the
  approved producer. Existence of a file, waiting, admission, or a zero counter
  alone is not evidence of inference. No authored test event may enter a real
  feed. UTCs are acquisition/observation times, not invented provider timings.
- Required feed fields: `schema="pex-safe-display/v1"`, exact `run_id`, strictly
  increasing `seq` beginning at 1, `at_utc`, enumerated `event`, enumerated
  `qualification`, and SHA256 of the actual current source artifact. Counts
  require `counts_validated=true`; no uncertain reservation is called usage.
  Unknown scalar strings/errors/IDs are never displayed. See code for all enum
  values. Do not put credentials, VMIDs, URLs, raw errors or private paths in
  feed filenames or run IDs either.
- Model/tool prose is optional. An exact current response excerpt must first be
  reviewed by root to exclude credentials, private source/paths, hidden tests,
  database content, auth/proxy data, and private IDs. Select exact contiguous
  safe bytes, **not authored replacements or corrected prose**; omissions must
  remain explicit. Root must verify provenance from the current raw artifact.
  Feed records contain `model_excerpt` plus its SHA256; a separate approvals
  file must authorize that exact `(run_id, source_sha256, model_excerpt_sha256)`.
  Changing bytes or lineage invalidates it. This is human-reviewed whitelisting,
  not a claim that regex redaction can prove a model response safe.
- All outputs remain private. Do not push feed, trace, approvals, screenshot,
  media or runtime evidence. Only this generic utility/tests/docs are potential
  secret-free source-checkpoint candidates. Never reuse historical frames.

## Root launch sequence (not run by preparer)

1. Obtain the newly admitted run ID/prefix and root-approved feed producer.
   Create a private parent directory; choose fresh nonexistent `display` and
   `video` child directories and a nonexistent/empty `safe-display.jsonl`.
2. Open/reserve **one separate clean terminal**, clear old output and scrollback,
   and run the `follow` command below there. Root must verify that only the safe
   header is visible. The utility sets its title to `PEX Live Evidence` (the
   native terminal may report `Terminal - PEX Live Evidence`). Both exact forms
   are accepted; no title prefix/substring matching is used.
3. Obtain the actual window ID using root's documented UI inventory. Keep this
   window unobstructed for the entire recording. No auth/private UI, notifications
   or overlapping window may appear on top. Do not resize, minimize, switch tabs,
   or reuse it. X11 occlusion may contaminate pixels; inspect the capture before
   any sharing. There is **no whole-desktop fallback**.
4. From an offscreen executor (not the safe window), invoke `capture` with the
   verified window ID. It rejects the X root window, unexpected title, oversized
   or unmapped window, reused output, and insufficient disk. It caps media to
   about 30 MiB, leaving at least 256 MiB workspace reserve, and checks disk while
   running. It records actual pixels at 3fps; it does not render log text into
   fake screen frames. Max duration is a safety cap, not proof of completion.
5. Verify `capture-control.json`, process liveness, and `capture-ready.json`
   privately. Ready is written only after ffmpeg reports at least two encoded
   frames; it is **not** a substitute for root's privacy/visual review. Do not
   dispatch the benchmark on a PID alone. Then start the authorized benchmark.
   Feed only real newly observed sanitized status records.
6. After the real terminal outcome/cleanup evidence has appeared on screen,
   allow it to remain visible briefly, send SIGINT to the exact recorder wrapper
   PID from `capture-control.json`, and wait for `capture-terminal.json`. Do not
   kill unrelated processes or close the safe terminal while recording.
7. Inspect media (including first/last frame and event transitions) and compare
   UTCs and artifact hashes with `safe-trace.jsonl`. Keep any blocked/error
   outcome labeled. `ffmpeg_exit_code=255` can mean an intentional SIGINT; it is
   not proof of corruption or success. Use ffprobe/read-only decode to check the
   actual file. If capture stops early, retain/report the gap, do not simulate it.

Commands (replace placeholders privately; never run them on an auth window):

```sh
python3 record_support.py follow --run-id NEW-RUN-ID \
  --feed PRIVATE-PARENT/safe-display.jsonl \
  --output-dir PRIVATE-PARENT/display \
  --approvals PRIVATE-PARENT/reviewed-excerpts.json --max-seconds 1800

python3 record_support.py capture --window-id VERIFIED-NONROOT-ID \
  --output-dir PRIVATE-PARENT/video --max-seconds 1800
```

Approvals file shape (a placeholder is **not** a usable approval):

```json
{"schema":"pex-excerpt-approvals/v1","approvals":[{"run_id":"EXACT-CURRENT-RUN","source_sha256":"EXACT_CURRENT_ARTIFACT_SHA256","model_excerpt_sha256":"EXACT_REVIEWED_EXCERPT_SHA256"}]}
```

## Testing / supported evidence

`safe_feed_writer.SafeFeedWriter(run_id=..., feed_path=...,
follower_start_path=...)` is the owner-facing metadata sink. Import it from this
directory. Construct it only after the follower's start receipt exists; it
verifies the run, fresh start, follower source hash and exact feed-path hash,
then creates a new empty0600 file without inventing any event. Call
`writer.emit(event=..., qualification=..., source_sha256=...,
**typed_metadata)` with real owner-derived measurements. UTC and increasing
sequence are generated at append time; records are validated and fsynced.
Use `with SafeFeedWriter(...) as writer:` or call `close()`. It does not access
raw DBs, credentials, network or providers; it intentionally cannot add prose.
The owner-reviewed producer must derive validated usage from actual current-run
receipts and save its private provenance snapshot before passing that snapshot's
SHA256. Unknown counts stay absent. A pending request is not settled usage;
partial settled counts must not be labeled complete totals. A report file alone
is not terminal proof: owner must supply its independently bound launcher and
cleanup outcome. After `run_terminal`, further appends are refused.

`python3 -B -m unittest discover -s . -p test_record_support.py -v` runs tiny,
authored, offline unit tests only. It does not call ffmpeg, manipulate UI, start
capture, call providers, or produce real benchmark evidence. Available local
ffmpeg advertises x11grab `window_id` and libx264; **actual capture is untested**
until root reserves a window and explicitly launches it.

The sanitized append-only trace is text evidence, not screen video. If root later
renders a trace visualization, label it **later-rendered visualization**, never
live recording. `screen-window.mkv` is the separate actual live pixel artifact.

## Minimal native launch and read-only ledger sidecar

When the ordinary executor lacks DISPLAY, do not copy/inject display or browser
authentication environment. Root may run `native_session.py --run-prefix NEW_PREFIX
--run-id NEW_ID --window-id VERIFIED_ID` in the reserved native terminal. It
creates fresh `NEW_PREFIX/recording-live`, starts the sanitized follower there,
and waits for root's `recording-live/START_CAPTURE` marker after header review.
Capture runs with the native environment inherited, with private logs and no
second visible/private terminal. Root's `recording-live/STOP_CAPTURE` marker stops
only owned subprocess handles; no guessed cross-namespace PID is used. Marker
waiting is bounded to 300 seconds and capture to 1800 seconds. Native capture
must still pass its own exact-title/nonroot guards and firstframe review.

The separate ordinary executor can run `ledger_sidecar.py --run-prefix NEW_PREFIX
--run-id NEW_ID --config-sha256 ROOT_APPROVED_CONFIG_SHA --follower-start
NEW_PREFIX/recording-live/display/follower-start.json --max-seconds 1800` after
the follower starts. This creates the safe feed but emits no invented startup or
phase event. It waits for an exact bound launcher admission and accounting
identity, uses SQLite mode=ro + query_only + bounded explicit transactions to
validate current receipt metadata, and writes private per-measurement provenance.
No model prompts, raw requests, CLI content, hidden grades or model excerpts are
displayed. Unknown/uncertain or absent aggregate usage stays absent, not zero.
The source hash binds the saved measurement, including exact transaction-row
digests; a separately labeled after-transaction database-file hash is not falsely
called a transaction snapshot. There is no phase inference from file existence.

Only the actual bound launcher-terminal artifact (including its exact report
hash when present) permits a terminal feed record. Observer failures/timeouts
never manufacture a benchmark terminal. Failure classes map to fixed generic
categories, not arbitrary exception prose. These utilities grant no benchmark
authority: root independently reviews the actual firstframes, recording-ready
handshake and original resource admission before dispatch.
