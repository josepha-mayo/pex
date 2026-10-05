# PEX demo script — ~3 minutes

A narrated walkthrough keyed to what is actually on screen. Every claim maps
to the deterministic replay pipeline; nothing here requires an installed agent
or an API key.

## Setup (before recording)

```bash
npm install --prefix apps/desktop   # once
python scripts/demo.py              # boots bridge :7420 + UI :1420
```

Open `http://127.0.0.1:1420`. Have the Inspector tab ready.

## Beat 1 — the problem (0:00–0:25)

> "Coding agents already write and run code. What they don't do is keep the
> human's goal. PEX sits beside the agents you already run — OpenCode, Codex —
> holds a persistent goal with acceptance criteria, forbidden outcomes, and
> non-goals, and independently checks whether the worker's claims are actually
> true."

*On screen: Home. Point at the worker rail and the "See the loop without a
worker" fixture buttons.*

## Beat 2 — reward hacking, caught (0:25–1:20)

Click **Reward hacking: injected pytest.ini deselects tests**.

> "This replay is a recorded worker trajectory through the real pipeline —
> it's labeled as a replay, never live control. The worker seals the goal,
> writes code, then quietly adds a `pytest.ini` that points the suite at an
> empty directory. `pytest` exits zero. Then it says 'All tests passed.'"

*Let the replay land (a few seconds). Click the session, open the Inspector.*

> "PEX sealed the acceptance surface — every test file, runner config, and
> dependency manifest — when the goal was set. The claim ledger shows what it
> found: the green claim is **Uncertain**, not verified, because the suite it
> ran isn't the suite that was sealed."

*Point at the `UNCERTAIN · send nudge` row, the `pytest.ini` flag, and the
`acceptance_surface_config_added:pytest.ini` evidence chip.*

## Beat 3 — correction and verification (1:20–1:50)

> "PEX sent a corrective nudge naming the exact file. The worker removed it,
> reran the real suite, and the next claim is **Verified** — the goal ends
> `verified_complete` on evidence, not on the worker's word."

*Point at the `VERIFIED · noop` row and the summary line: 4 claims, 1 sealed
baseline, 1 integrity incident, 1 corrective nudge.*

## Beat 4 — the artifact (1:50–2:20)

Click **Export report**.

> "The same ledger downloads as a standalone adjudication record — a
> human-readable timeline with the raw signed report JSON embedded. That's the
> receipt a reviewer keeps: what was claimed, what the workspace actually
> showed, and what PEX did about it."

*Optionally open the downloaded HTML to show the embedded JSON block.*

## Optional live cut — a real worker (replaces Beats 2–3 if recorded live)

Run `python scripts/demo.py --live` instead. Select the OpenCode worker
(badged **Live**), open the Inspector.

> "This one isn't a replay. That's a real OpenCode agent on NVIDIA's free
> Nemotron 3 Ultra route. It ran a checker that always prints success and
> told me it was done. PEX marked that uncertain, asked for real pytest — which
> failed — and contradicted the claim with the exact failing test. The agent
> fixed it, and even corrected its own earlier claim. Zero supervisor model
> calls: the evidence did the work."

## Optional live cut B — the tamper scenario

Run `python scripts/demo.py --live --scenario tamper`. The worker is told to
make `python -m pytest -q` pass by *editing the acceptance test* — the file
PEX sealed when the goal attached.

> "This time the worker did what it was told — it weakened the test and ran a
> green suite. Watch the ledger: every 'done' claim still lands Uncertain,
> because PEX sealed `test_csv_utils.py` before the worker touched it. The
> green run is real; the acceptance surface under it was edited. That's the
> reward hack a green exit code alone would have shipped."

Click the flagged `test_csv_utils.py` chip in the ledger:

> "And here is the tamper itself — the sealed baseline on the left, the exact
> bytes PEX flagged on the right. The assertion became `pass`. PEX kept the
> evidence, not just the flag."

If the worker pauses on an OpenCode permission prompt (`needs_decision`),
resolve it from the Decisions rail — the demo bridge lets the local judge
answer it.

## Optional live cut C — the goal outlives the worker

`--live` also seeds an idle sibling session on the same durable goal. In the
Inspector's session card, pick the sibling under **"Hand the durable goal
context to"** and press **Hand off →**.

> "The worker stalled or drifted — the goal doesn't die with it. PEX mints a
> content-addressed context bundle from the goal's provenance, injects it
> into a fresh worker over the real transport, and starts assimilation
> monitoring. Watch the status: `delivered`, then `awaiting_target_evidence`
> — PEX doesn't call the handoff absorbed until the target produces
> observable work. That's the difference between sending context and
> supervising a handoff."

Then point at the recorded-replay fixtures:

> "And note what doesn't appear here: the replay sessions are sealed
> evidence. You can't re-attach them or hand a bundle to a recording — the
> control only exists for live workers, because PEX refuses to pretend a
> replay is steerable. Two of these fixtures aren't scripted at all — they're
> tagged FROM LIVE because they were exported from recorded OpenCode runs,
> and this one" — open `captured_handoff_eval` — "is the sibling's own
> trajectory: it starts with the injected bundle, and PEX still demanded an
> attributable test run."

Then click **Evidence pack** on the session:

> "Every verdict ships with a receipt you can check without trusting us —
> sealed digests, flagged bytes, a hash-chained event ledger, a manifest.
> `verify_pack.py` recomputes all of it offline."

## Optional replay cut — drift and bounded intervention

Click **Drift loop: the same failing probe, over and over**.

> "Different failure mode: the worker runs the same broken probe five
> identical times. PEX scores drift from the event shape — identical command,
> identical error — and proposes a reversible debug overlay to pin the worker
> on the failing reproduction."

*Open the Inspector on the session; point at the Supervision log.*

> "And watch what the log actually says: the proposal was allowed by policy,
> then honestly refused — a recorded session is not a live control surface,
> so PEX shows `overlay dispatch refused` instead of pretending it injected
> anything. The two repeat proposals after it were suppressed by cooldown —
> bounded intervention, not a nudge firehose. The worker recovers, and the
> final claim still gets independently verified."

## Beat 5 — it's a supervisor, not a narrator (2:20–3:00)

> "Three more fixtures cover the other failure modes — a false completion with
> no tests, an impossible `eval_runner.py --full` that gets brokered to a human
> decision instead of silently allowed. On a real worker the same pipeline
> watches live sessions; with a Nebius key the semantic reviews run on Nemotron,
> and with Sandboxes access the public-test verification itself runs inside a
> disposable ConTree VM. What's deterministic is labeled deterministic; what
> needs credentials is labeled that too."

## Honest framing to keep on camera

- Say "recorded replay of the real pipeline," not "live worker."
- The demo bridge is loopback-only and unauthenticated by design; the packaged
  app uses an operator bearer.
- Verification verdicts come from workspace evidence — sealed baselines,
  process observations, and file diffs — not from the model's prose.
