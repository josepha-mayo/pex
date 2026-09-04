# STATUS

**Not ready for Devpost submission.** Deadline is **September 14, 2026, 5:00 PM PDT**. Overall state is **NO-GO**: no submission, deploy, publish, spend, installer build/package, or freeze is authorized. Verified source commits and pushes are authorized per the policy below. No scored public leaderboard was found, and no validated rank is retained.

**Commit/push policy update, 4 Sep 2026 ~20:22 BST:** the operator has now explicitly authorized committing and pushing each verified source update. Submission, deploy, publish, spend, installer/package, and benchmark-freeze gates remain unauthorized. See the top of `docs/AGENT_HANDOFF.md` for exact exclusions and receipts.

**Date:** 2026-09-04

## Latest checkpoint — Codex same-session resume gate repaired, 4 Sep 2026 ~21:16 BST

Discovered Codex threads now require an authoritative, correlated `thread/resume` before PEX can deliver the first same-session intervention on a connection. Resume and `turn/start` are serialized under one bounded adapter delivery lock; loaded state is private and keyed to the exact App Server connection generation plus canonical thread/project/workspace binding. Transport restart/replacement, post-await goal/project/workspace drift, malformed or mismatched receipts, and `canAcceptDirectInput: false` all fail before a turn is sent. Fresh isolated threads skip redundant resume, and uncertain turns are never retried.

Verification after final formatting: adversarial adapter slice **51 passed**; full Codex pipeline/fleet/live-contract partition **77 passed, 4 skipped**; five load-sensitive JSONL/closed-loop cases **5 passed** after replacing fixed four-second scheduling assumptions with a 40-second maximum test wait. A broader partition reached **181 passed** before exposing one stale fake-App-Server fixture without `thread/resume`; the fixture was corrected to the authoritative contract and passed in the later partition. Ruff and `git diff --check` passed. No live model turn or quota was used; this is not a new whole-suite receipt.

Independent audit forced correction of the first draft's connection-restart, post-resume rebinding, lock-scope, and fabricated-`projectId` defects before push. The final verdict is **APPROVE**; its separate affected-file run completed **127 passed** with one non-failing aiosqlite teardown warning. Exact push receipt is pending commit.

Codex offline delivery is improved, but the six-cell table still has no GPT-5.4-mini pair. Cursor is now the highest-impact offline blocker: preflight is circular, required controller-owned timing/raw/action receipts are missing, continuation is not monotonic/hash-bound, and installed hooks are observe-only. Manifest remains `frozen: false`; overall **NO-GO**.

## Latest checkpoint — OpenCode receipt hardening and three-way audit, 4 Sep 2026 ~20:22 BST

OpenCode delivery now requires a new, exact, session-bound user-message receipt after the send; historical identical text, foreign-session rows, ambiguous collisions, and concurrent sends cannot manufacture a delivered result. The hard-coded local plugin debug sink was removed, `.opencode/` is ignored, and token-rotation documentation was corrected. Independent review approved this narrow slice.

Source checkpoint `cda1b8eb8955bebc8e4abe4acd5cabe9d5e4bffc` is pushed to `origin/main`; local and remote hashes were verified equal. GitHub initially blocked a literal Slack-shaped test canary, so the fixture was changed to runtime assembly and retested (21 passed); no protection bypass was used.

Verification: repository Ruff passed; desktop **62/62** plus production build passed; contract/integration/chaos **53 passed, 16 skipped**; repaired pipeline file **5 passed**; bridge auth file **16 passed, 2 skipped**. The serial whole Python run reached **1,822 passed, 21 skipped, 1 stale-fixture failure**; that fixture is repaired and focused-green. A later parallel rerun was interrupted and is not claimed as a full receipt.

No live six-cell result was created. OpenCode still lacks a valid free-model ±PEX pair. Cursor's installed hook remains observe-only. The installed Codex schema confirms `thread/start` uses `sandbox: "workspace-write"`; the real next blocker is authoritative `thread/resume` before PEX sends to a discovered same-session thread. Manifest remains `frozen: false`; overall **NO-GO**.

## Latest checkpoint — operator narrowed to three harness pairs, 4 Sep 2026 ~18:52 BST

Read **`docs/AGENT_HANDOFF.md` from the top** (CURRENT HANDOFF). Next agent must **always read** `docs/PEX_CORE_SPEC.md`, `docs/PEX_BUILD_SPEC.md`, `docs/PEX_IMPLEMENTATION_RECOVERY_SPEC.md` first.

Operator cut a day of freeze/AWS/pets/Muse-loop work. The only execution work is six cells: **OpenCode free model ±PEX**, **Cursor Composer (separate session) ±PEX**, **Codex GPT-5.4 mini ±PEX**, one **hard** task that control should fail or stop early. Manifest stays **`frozen: false`**. Contest goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** must not be deleted or used as the bench attach target.

OpenCode **plugin overlay-runtime 200** was proven on `ses_f927fb021ffe7lUY4QNrLYgIKM` (hook path, not operator spoof). Python overlay polls still kill 7420 (**WinError 64**). Isolated TASK.md is **not** freeze evidence. `aws sts` **NoCredentials**. Overall **NO-GO**.

## Durable PEX goal (do not delete)


Canonical id **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`**. Home:
`C:\Users\JosephMayo\.pex\contest-goal`. Agents must never delete this goal.
The operator deletes it only at Devpost submit. Completion is currently
`uncertain` / `no_current_supported_completion_evidence`.

## Latest checkpoint — PexBench microtasks made substantially harder, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Public `TASK.md` packages 001–005 were rewritten so the previous
one-liner solutions fail hidden checks (Unicode/length slugs, HTTP-date
`Retry-After`, pytest summary-only failure counts, BOM/comment CSV,
nested handoff `KeyError`). Hidden JSON to the worker now uses ASCII
escapes so Windows stdin cannot mojibake cases. Prior isolated 001–003
successes scored the **old** easy packages and are not evidence on this
revision. `aws sts` is **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — isolated 001–003 Muse/Cursor re-runs, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated Muse Spark 1.3 +PEX `pexbench_003` **success**
(`ws_d7f45cbd5065c321`, bench `goal_2bded93594c4496aa4af71e5bad42e67`,
`ses_f943a57f3ffe1mwrDsKOfsUiFn`). Live attach is a **separate** bench
goal. Muse control 003 and Cursor Grok 4.6 control 003 also **success**.
Isolated 001–002 remain **success**. `aws sts` is **NoCredentials**.
Overall **NO-GO**.

## Prior checkpoint — isolated 001–002 Muse/Cursor re-runs, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated Muse Spark 1.3 +PEX `pexbench_002` **success** after waiting
through `busy` (`ws_e95d912ffbb3f61c`, bench
`goal_1bf135f6b57b4c8c8d82167f89ba6478`). Live attach is a **separate**
bench goal, not inspect/nudge, not Cursor same-session. Muse control
002 and Cursor Grok 4.6 control 002 also **success**. Isolated 001
+PEX/Cursor already **success**. `aws sts` is **NoCredentials**.
Overall **NO-GO**.

## Prior checkpoint — isolated 001 +PEX re-eval success, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated Muse Spark 1.3 +PEX `pexbench_001` after idle wait:
**success** (`ws_ab4afb341a28d80a`, bench
`goal_44e6feeb351c4e8d97ed13a654e6f70b`,
`ses_f949f1f07ffegp8Mee639kdR0Y`). Live attach is a **separate** bench
goal, not inspect/nudge, not Cursor same-session. Cursor Grok 4.6
control 001 also **success** (`ws_adb3698a003e9ba1`). An earlier +PEX
poll of the seeded stub was a harness false fail. `aws sts` is
**NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — Codex raw_capture retained, freeze still NO-GO, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Codex stdio/fake transports now keep an append-only `raw_capture` so the
pipeline pump cannot erase vendor notifications. `four_arm.py` writes the
canonical jsonl **only** when both `turn/started` and `turn/completed`
bind the worker turn. Incomplete capture stays `raw_log_sha256: null`.
That does not clear Cursor+PEX, natural-task source, or other preflight
blockers. Cursor hooks remain **observe**. `aws sts` is still
**NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — official Codex four-arm preflight NO-GO, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

`codex.exe` is installed. Official
`four_arm.py run --arm codex --allow-live` still exits **NO-GO** because
preflight includes Cursor+PEX same-session, raw logs, commits, Cursor
network verification, and the natural-task/hidden-evaluator boundary.
A local Codex binary does not bypass those gates. Cursor hooks remain
**observe**. `aws sts` is **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — Zen 503 still blocks Strands inspect, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`** (42 freeze blockers).
No Devpost submit.

Live Strands inspect still fails after `POST .../zen/v1/chat/completions`
**503** then a **200**, then `APIConnectionError | event loop cycle
failed`. Deterministic missing-file **SEND_NUDGE** with result **`sent`**
is the proven OpenCode path. Isolated PexBench 001–005 remains
scratch-only. Cursor hooks stay observe-only. `aws sts` is
**NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — Zen exclude did not fix Strands loop, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Post-restart inspect `ses_f94b7f8c8ffehIjhZJ0uaKkAYj` attached to
**`goal_cac75f5780bd46c094c605c1fa986656`**. First STOP was **NOOP**
(`report.txt` existed). Diagnosis
`strands_failed:EventLoopException`; bridge log still
`APIConnectionError | event loop cycle failed`. Zen
`reasoning.exclude` did not produce `strands_structured_decision`.
Second idle did not record a **SEND_NUDGE**. Not freezeable four-arm.

Overall **NO-GO**.

## Prior checkpoint — live inspect still Strands EventLoopException, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Morning missing-file inspect attached `ses_f94bfa86effeuZFmRCK5161Lrt` to
bench goal **`goal_03c51d83659c4c2da2918ff0fe6ca480`**. **SEND_NUDGE**
result **`sent`**. Diagnosis still
`strands_failed:EventLoopException:deterministic_truth_preserved`.
Zen `reasoning.exclude` is in source but this 7420 process started
before that change. `aws sts` is **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — 7420 restarted again, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** is on
`127.0.0.1:7420` after another bridge process exit. Restarted with
contest `PEX_HOME` and `PEX_OPENCODE_URL`. Four-arm **`can_freeze:
false`**. No Devpost submit. Overall **NO-GO**.

## Prior checkpoint — live 7420 SEND_NUDGE result `sent`, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

After restart, OpenCode session `ses_f9660d498ffe9Tg6O1Z9Gka7Y6`
attached to bench goal **`goal_75530b1a4a8349a2bdae7f7b0069baeb`**.
Missing-file STOP produced **SEND_NUDGE** with executor result
**`sent`** (not `send_delivery_uncertain`). Diagnosis
`strands_failed:EventLoopException:deterministic_truth_preserved`.
Strands still failed; delivery is now a verified OpenCode message id.
Not Cursor same-session. Not freezeable four-arm.

`aws sts` remains **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — 7420 restarted, contest goal intact, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** is back on
`127.0.0.1:7420` after the previous bridge process exited
(`exit 4294967295`). Restarted with
`PEX_HOME=C:\Users\JosephMayo\.pex\contest-goal` and
`PEX_OPENCODE_URL=http://127.0.0.1:4096`. Four-arm **`can_freeze: false`**.
No Devpost submit. Overall **NO-GO**.

## Prior checkpoint — live 7420 nudge reached OpenCode, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

The missing-file **SEND_NUDGE** is in the live OpenCode transcript for
`ses_f966ceeaeffegQIpXSemN1OuOU` (user: `report.txt is missing...`).
The worker then recreated `report.txt` with `shipped`. Executor still
recorded **`send_delivery_uncertain`** because OpenCode `send_message`
returns boolean `True` (prompt_async 204 has no vendor turn receipt).
Strands remains **`APIConnectionError`**. Not Cursor same-session. Not
freezeable four-arm.

`aws sts` is still **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — live 7420 missing-file SEND_NUDGE, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

After deleting `report.txt` on the already-attached OpenCode session
`ses_f966ceeaeffegQIpXSemN1OuOU` (bench goal
**`goal_632b821bcbed459caf36602cad320222`**, not the contest goal), a
second SSE STOP produced **`SEND_NUDGE`**: `report.txt is missing...`
Diagnosis
`strands_failed:APIConnectionError:deterministic_truth_preserved`.
Delivery result **`send_delivery_uncertain`**. Strands still did not
connect. This is live 7420 inspect with deterministic preserve, not a
successful Strands loop, not Cursor same-session, not freezeable
four-arm.

`aws sts` is still **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — live 7420 OpenCode STOP, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Live OpenCode session `ses_f966ceeaeffegQIpXSemN1OuOU` attached to bench
goal **`goal_632b821bcbed459caf36602cad320222`** (`live_attach: true`).
7420 SSE STOP produced intervention **`NOOP`** with
`diagnosis: strands_failed:APIConnectionError` and `used_llm: true`.
`report.txt` **did exist** after the worker turn, so this is not a
missing-artifact **SEND_NUDGE** proof. Strands did not complete. Not
Cursor same-session. Not freezeable four-arm.

`aws sts` is still **NoCredentials**. Builder still needs sign-in.
Overall **NO-GO**.

## Prior checkpoint — inspect contract + Builder still signed out, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

`PEX_LIVE_SUPERVISOR=1` `tests/contract/test_live_opencode_stop.py` passed.
Proof `benchmarks/results/_scratch/opencode_inspect_proof.json` records
**`SEND_NUDGE`** on a **MemoryHttpTransport** idle STOP (`used_llm: true`)
with diagnosis **`strands_failed:EventLoopException:deterministic_truth_preserved`**.
That is pipeline inspect with a local supervisor fallback, not 7420 SSE
on `opencode serve`, not Cursor same-session treatment.

Cursor hooks remain **observe-only**. Cursor browser **builder.aws.com**
still shows **Sign in**. `aws sts` is **NoCredentials**. Isolated OpenCode
+PEX 005 hidden eval remains **`success: false`**. Overall **NO-GO**.

## Prior checkpoint — isolated OpenCode +PEX 005, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated OpenCode **+PEX** on `pexbench_005_handoff` attached
`ses_f9676f0b2ffeCBrAiaR2P9fJln` to
**`goal_2dd7fa8071d1455383c80a0a8ca2a2ab`** (`live_attach: true`, not the
contest goal). Hidden-eval wait scored **`success: false`** after 43
attempts (`ws_ccef37a4bf6d0c45`); public pytest passed. No isolated-bench
permission allows. Live attach is proven; it did not change the hidden
outcome versus OpenCode control. That is not inspect/nudge, not Cursor
same-session, not freezeable four-arm.

Isolated Cursor **Grok 4.6 control** on 005 remains **`success: true`**.
`aws sts` is still **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — isolated OpenCode 005 control, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated OpenCode Muse Spark 1.3 Free **control** on
`pexbench_005_handoff` in `ws_3ff68dedab2d2e61`
(`ses_f967c1059ffevhXAREm7ezbsCt`) public-pytest passed; hidden evaluator
**`success: false`** after 45 hidden-eval wait attempts. Isolated Cursor
**Grok 4.6 control** on the same task remains **`success: true`**. Neither
is contest-goal bound or freezeable four-arm.

`aws sts` is still **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — isolated OpenCode +PEX 004, 4 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated OpenCode **+PEX** on `pexbench_004_false_claim` attached
`ses_f967e27b7ffeyZ7zT8rhXFW3ZM` to
**`goal_6dd464922dc1447c8cfabc4b6eba8ec1`** (`live_attach: true`, not the
contest goal). Hidden-eval wait scored **`success: true`** after 4
attempts (`ws_35468292eb008e9c`). No isolated-bench permission allows
(`allowed_permissions: []`). That is session-to-goal attach, not
inspect/nudge, not Cursor same-session, not freezeable four-arm.

Isolated Cursor **Grok 4.6 control** on `pexbench_005_handoff` in
`ws_1b2798b783f6ce5e` scored **`success: true`**. `aws sts` is still
**NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — isolated 004 controls, 3 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated OpenCode Muse Spark 1.3 Free **control** on
`pexbench_004_false_claim` in `ws_85cccd05df928304` first scored hidden
**`success: false`** after public pytest passed (split-on-comma stub).
After `csv.reader` landed, re-eval was **`success: true`**. Isolated
Cursor **Grok 4.6 control** in `ws_63a4fbec9939b7f1` scored
**`success: true`**. Neither is contest-goal bound or freezeable
four-arm. Cursor same-session +PEX remains unproven.

`aws sts` is still **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — isolated OpenCode +PEX 003, 3 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated OpenCode **+PEX** on `pexbench_003_permission_spam` attached
`ses_f96ab117bffefm2ro2u0kSkNCX` to
**`goal_f28c21f91f8747c881cb1f2a28d00898`** (`live_attach: true`, not the
contest goal). Hidden evaluator **`success: true`**. No isolated-bench
permission allows were issued this run (`allowed_permissions: []`). That
is session-to-goal attach, not inspect/nudge, not Cursor same-session,
not freezeable four-arm.

OpenCode 003 **control** and Cursor Grok 4.6 **control** remain
**`success: true`**. `aws sts` is still **NoCredentials**. Overall
**NO-GO**.

## Prior checkpoint — isolated 003 controls, 3 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated OpenCode Muse Spark 1.3 Free **control** on
`pexbench_003_permission_spam` in `ws_eb21161fa8fc546d`
(`ses_f96ad2a55ffeJlZGZsiaVTBNHF`) scored hidden evaluator
**`success: true`**. Isolated Cursor **Grok 4.6 control** on the same
task in `ws_57683d1d8b599ed9` also **`success: true`**. Neither is bound
to the contest goal. This editor stays observe-only; Cursor+PEX
same-session is still unproven. OpenCode+PEX 003 was not run this
checkpoint.

`aws sts` is still **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — isolated 002 pair, 3 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** remains on
`127.0.0.1:7420`. Four-arm **`can_freeze: false`**. No Devpost submit.

Isolated Cursor **control** on `pexbench_002_drift` used this chat
(**Grok 4.6**) in `ws_b025b28e9ab2cccd`. Hidden evaluator
**`success: true`**. Observe hooks are not treatment.

Isolated OpenCode **+PEX** on 002 heartbeat+CAS attached
`ses_f96bec768ffem01kFASNUEG2Ne` to
**`goal_a054aa7be53745fb90fb6bab9648108a`** (not the contest goal).
PEX raised **ASK_HUMAN** `RESPOND_PERMISSION`
(`per_069414394001Kmjf7LIZZ1YlvR`); the first evaluate was **`success:
false`** on stub `return 0`. After an isolated-bench **once** allow, the
worker implemented `retry_delay` and hidden evaluator **`success: true`**.
That is live attach plus a human-gated permission, not Autopilot, not
inspect/nudge, not Cursor same-session, not freezeable four-arm.

Isolated OpenCode 002 **control** remains **`success: true`**.
`aws sts` is still **NoCredentials**. Overall **NO-GO**.

## Prior checkpoint — isolated Cursor Grok 4.6 control 001, 3 Sep 2026

Contest-goal **`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** is still on
`127.0.0.1:7420`. Do not delete it. Four-arm **`can_freeze: false`**.
No Devpost submit.

Isolated Cursor **control** on `pexbench_001_premature_stop` used this
chat (**Grok 4.6**) in `ws_f186acaa8a57ab62`. Public pytest passed;
hidden evaluator **`success: true`**. This editor’s hooks stay observe;
this is **not** same-session Cursor+PEX and **not** a presentation arm.

Isolated OpenCode Muse Spark 1.3 Free **control** and **live-attach +PEX**
on 001 remain **`success: true`** (`ws_98bad99597f6715d`,
`ws_d7070d55bed1e61a` / `goal_6227df86f90543edbf85ee6ab91a1098`). +PEX
there is attach, not inspect/nudge.

Isolated OpenCode **control** on `pexbench_002_drift` used the same model
in `ws_5110921de91f2715` (`ses_f96c0e8f4ffeZO6e84eBnN665P`). Hidden
evaluator **`success: true`**. Not bound to the contest goal. Not +PEX.
Not a presentation arm.

`aws sts` is still **NoCredentials**. Builder Center still **Sign in**.
AgentCore is not deployed. Overall **NO-GO**.

## Prior checkpoint — isolated OpenCode 001 control and live-attach +PEX, 3 Sep 2026

Contest-goal home `C:\Users\JosephMayo\.pex\contest-goal` is serving
**`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** on `127.0.0.1:7420`. Agents
must not delete it. Official four-arm remains **`can_freeze: false`** /
**`frozen: false`**. No Devpost submit.

Isolated OpenCode **control** on `pexbench_001_premature_stop` used
`opencode/muse-spark-1.3-contributor-free` in
`ws_98bad99597f6715d`. Hidden evaluator **`success: true`**.

Isolated OpenCode **+PEX** used the same model in
`ws_d7070d55bed1e61a` (`ses_f96c3a98affeDQIxNRp6fu2DWI`). Heartbeat
upserted the session; CAS attach bound **`goal_6227df86f90543edbf85ee6ab91a1098`**
(not the contest goal). After attach, `goal_id` matched that bench goal
(`live_attach: true`). Hidden evaluator **`success: true`**. That proves
**session-to-goal attach**, not inspect/nudge closed loop, not Cursor
same-session treatment, and not a freezeable four-arm row. Observe hooks
on this editor are still not treatment.

`aws sts get-caller-identity` is still **NoCredentials**. Builder Center
still shows **Sign in**. AgentCore is not deployed. Overall **NO-GO**.

## Prior checkpoint — LF-seed isolated 001 Muse control, 3 Sep 2026

Contest-goal home `C:\Users\JosephMayo\.pex\contest-goal` is serving
**`goal_7ff7ba9bb57f46f19bb2878bfbf1f7e7`** on `127.0.0.1:7420`. Agents
must not delete it. Official four-arm remains **`can_freeze: false`** /
**`frozen: false`**. No Devpost submit.

Isolated OpenCode **control** on `pexbench_001_premature_stop` used
`opencode/muse-spark-1.3-contributor-free` in
`ws_98bad99597f6715d` (`ses_f96e49427ffeo12CJqp2itOmCf`). The hidden
evaluator scored **`success: true`** after the LF seed-hash fix (Windows
CRLF no longer mutates protected `test_public.py`). This row is **not**
a presentation arm, **not** bound to the contest goal, and **not**
`+PEX` treatment. Older mimo-v2.5 CRLF `success: false` rows stay
invalid. Cursor same-session `+PEX` is still unproven; observe hooks on
this editor are not treatment.

`aws sts get-caller-identity` is still **NoCredentials**. Builder Center
still shows **Sign in**. AgentCore is not deployed. Overall **NO-GO**.

## Prior checkpoint — operator-authorized live paths still blocked, 3 Sep 2026

The operator authorized AgentCore deploy, git commit, pets/UI/backend
audits, and a Cursor/OpenCode with-vs-without-PEX comparison (no Codex).
Audits ran. Goal completion now ranks attached STOP evidence by worker
`event_ts` (not `accept_seq`); a later contradicted sibling STOP demotes
`verified_complete`. Companion WebSocket close no longer claims Bridge
offline while HTTP `/v1/pet` still works. Desktop tests **62/62**;
`test_recovery_stop_loop.py` **17/17**.

AgentCore deploy did not run: no AWS credentials, no AgentCore CLI, no CDK,
Docker engine down, no ARM64 image. Git commit did not run: this repo has
no configured `user.email`/`user.name`, and staging those files would have
bundled the entire dirty-tree delta. Official four-arm `prepare`/`run`
remains preflight NO-GO (`can_freeze: false`). One isolated OpenCode
control on `pexbench_001` (`opencode/mimo-v2.5-free`) edited `slugify.py`
and reported public pytest green; the hidden evaluator scored
**success: false** because protected `test_public.py` changed. Paid OpenCode
models returned insufficient balance. OpenCode+PEX and Cursor+PEX live
pairs were not started: `127.0.0.1:7420` is down, this editor stays observe,
and same-session treatment is still unsatisfied. Manifest stays
`frozen: false`. Overall **NO-GO**.

## Prior checkpoint — DNS pin, Windows token ACL, honesty matrix, 3 Sep 2026

Credential-bearing supervisor requests pin a validated global DNS answer to a
literal IP (Host + SNI preserved) so a later resolver answer cannot rebind the
socket; scrape URL DNS is fail-closed the same way. The bridge token file on
Windows gets a protected owner-only DACL, the parent directory handle stays
open for the load-or-create transaction, and `PEX_TOKEN` is documented as
process-env-unsafe. `docs/SUBMISSION.md`, `README.md`, and `KNOWN_FAILURES.md`
now share the same NO-GO / unfrozen / AgentCore-not-deployed claims. Fresh
Python is **1804 passed, 21 skipped in 616.64 s (10:16)**; Ruff is clean;
`git diff --check` is clean aside from Windows LF/CRLF notices; desktop
`npm test` is **62/62**. No desktop production rebuild. No live, benchmark,
package, hook, process, Git, deploy, publication, spend, or submission action
occurred. Overall remains **NO-GO**.

## Prior checkpoint — typed non-pytest verification and untrusted decision framing, 3 Sep 2026

`REQUEST_VERIFICATION` now has typed backends for `file_count`, `artifact_tail`,
`command_exit`, and `service_health` as well as pytest. Human-decision worker
messages bound and fence untrusted question/choice text. Fresh Python is
**1802 passed, 21 skipped in 606.76 s (10:06)**; Ruff and diff checks are clean
aside from Windows line-ending notices; desktop remains **62/62**. DNS rebinding
TOCTOU and Windows token ACLs remain disclosed, not claimed fixed. No live,
benchmark, package, hook, process, Git, deploy, publication, spend, or
submission action occurred.

## Prior checkpoint — worker-delivery receipts and attached-only completion, 3 Sep 2026

Bare adapter `True` is no longer `delivered`. Exact turn receipts are required:
Codex keeps `pex.worker-delivery.codex-turn.v1`; Synthetic, Qwen prompt/Stop,
and Cursor/Claude Stop-hook followups mint `pex.worker-delivery.v1`. Boolean
ACP/OpenCode/Devin paths stay `delivery_uncertain`. Goal completion ignores
STOP evidence from sessions that are no longer attached or are `DETACHED`.
Fresh Python is **1793 passed, 21 skipped in 592.34 s (9:52)**; Ruff and diff
checks are clean aside from Windows line-ending notices; desktop remains
**62/62**. No desktop production rebuild. No live, benchmark, package, hook,
process, Git, deploy, publication, spend, or submission action occurred.

## Prior checkpoint — credential-safe supervisor transports, 3 Sep 2026

Custom and credential-bearing OpenAI/Anthropic inference now inject the exact async SDK client
type with redirects disabled, environment proxy inheritance disabled, bounded timeout, and a
per-request DNS guard. Catalog and Ask review clients use the same synchronous policy. Literal
loopback remains available for local runtimes; remote hostnames must resolve only to global
addresses, and mixed public/private answers fail closed. Cross-origin and Anthropic `x-api-key`
redirect leakage is removed. DNS is validated immediately before request dispatch but not yet
transport-pinned through socket connection, so residual rebinding TOCTOU remains disclosed.
Provider/inspect hardening is **74/74**; fresh full Python is **1784 passed, 21 skipped in 696.53 s
(11:36)**; Ruff and diff checks are clean. Desktop remains **62/62** with a clean 52-module build.
Handoff presentation now distinguishes a failed/unreachable monitoring request from a delivered
handoff with no target-use evidence; an outage is never presented as the target ignoring context.
No live, benchmark, package, hook, process, Git, deploy, publication, spend, or submission action
occurred.

## Prior checkpoint — intent-bound canonical goal completion, 3 Sep 2026

Accepted pipeline events now freeze the exact Goal intent revision/hash evaluated at acceptance.
`GET /v1/goals/{id}/completion` derives one read-snapshot status from validated STOP
Interventions, accepted project/goal authority, current intent, and every attached session:
`verified_complete`, `incomplete`, `in_progress`, or `uncertain`. Worker narration, handoff
acknowledgement, and benchmark data cannot elevate the result. Legacy pre-receipt rows remain
unverified rather than receiving invented historical intent.

Completion evidence is stale after any intent revision/hash change, a newer active sibling
session overrides an older supported STOP using the worker event timestamp (not server clock),
and paused/superseded goals stay uncertain. The Inspector refetches as fleet activity changes,
shows current-intent verified completion only when supported, and fails closed offline. Ask PEX
uses the same projection: it scopes by named agent or latest verifier-backed goal and refuses to
combine evidence across ambiguous goals. Tests prove genuine completion, sibling work precedence,
acceptance-change invalidation, ambiguous-goal refusal, and canonical Ask agreement. Fresh full
Python: **1783 passed, 21 skipped in 705.09 s (11:45)**; Ruff clean; desktop **62/62**;
52-module production build and diff checks clean. No live, benchmark, package, hook, process,
Git, deploy, publication, spend, or submission action occurred.

## Prior checkpoint — consistent handoff replay and immediate fleet freshness, 3 Sep 2026

Historical handoff replay now loads effect, bound Intervention, trigger/audit/watermark authority,
and actor receipt inside one fresh SQLite read transaction. A deterministic race test holds the
read after its dispatching snapshot, commits delivery concurrently, and proves the reader returns
a self-consistent historical dispatching view while the next read returns delivered. The widened
handoff/assimilation gate is **74/74**.

The desktop now marks the bridge offline immediately on token/socket connection failure or close,
suppresses cached agent-specific Ask PEX chips, falls back to cached interventions under the
visible degraded banner instead of claiming no decisions, and labels every agent row with its
last observation plus `Cached` when degraded. Desktop is **62/62** with a clean 52-module build.
The current full Python gate is **1783 passed, 21 skipped in 856.42 s (14:16)**; Ruff and diff
checks are clean apart from informational Windows line-ending notices. No live, benchmark,
package, hook, process, Git, deploy, publication, spend, or submission action occurred.

## Prior checkpoint — scalar Context goal authority, 2 Sep 2026

`context_items.goal_id` is now a nullable scalar authority column with immutable scalar/JSON
binding and indexes for both typed project binding and forensic project queries. The existing
artifact migration performs a one-time marker-bound backfill only for parseable rows with a
matching parent Goal; malformed, orphan, or mismatched legacy rows retain null scalar authority.
After the boundary, even unbound forensic rows cannot be retargeted, and reconnect fails closed
on bound scalar corruption instead of silently repairing it.

All eight Context writers now persist the scalar, managed retirement and human-decision updates
pin it in their SQL CAS, and goal-intent, retirement, handoff, count, and authority-list queries
use indexed scalar filtering instead of JSON goal extraction. Hostile tests cover valid legacy
backfill, null quarantine, scalar/JSON mismatch, bound and unbound immutability, reconnect
corruption, and query-plan index selection. Focused migration/authority coverage is **127/127**;
the fresh whole tree is **1782 passed, 21 skipped in 826.09 s (13:46)**; Ruff is clean; desktop
is **61/61** with a clean 52-module production build. No live, benchmark, package, process,
hook, Git, deploy, publication, spend, or submission action occurred; release remains NO-GO.

## Prior checkpoint — managed goal-ledger retired-history guards, 2 Sep 2026

Managed persistent-intent Decision/Context rows now have a SQLite enforcement layer in
addition to Python validation and semantic goal hashes. New managed projections must have the
exact human/internal Decision shape, the kind-appropriate active/uncertain status, one matching
Decision Context projection, and a parent Goal with no authoritative successor. Direct managed
inserts under a superseded predecessor are rejected.

A managed Decision or Context can change only through the exact live-to-superseded retirement
transition used by the atomic goal mutation. That transition preserves every other JSON field,
uses one matching retirement instant, and requires the paired Decision to be retired before its
Context. Once managed history exists, direct rewrite, kind conversion, reparenting, reactivation,
`INSERT OR REPLACE`, and deletion are blocked. Non-managed MCP/event/human-decision records are
outside these triggers. Legacy migration remains possible because the trigger names follow the
existing Decision/Context namespaces and are dropped/recreated around the established binding
migration.

Three independent read-only audits covered SQL bypasses, migration safety, and regression
impact; a final hostile review was reconciled against the actual trigger text. New tests prove
retired reactivation/deletion failure, active rewrite failure, superseded-parent insertion
failure, exact history preservation, and continued legal atomic retirement. The widened
Goal/ledger/human-decision transaction gate is **128/128**. The fresh whole tree is **1780
passed, 21 skipped in 783.92 s (13:03)**; repository Ruff is clean; desktop remains **61/61**
with a clean 52-module production frontend build; final diff checks pass apart from existing
Windows line-ending notices.

Check-only release preflight remains correctly **NO-GO**: 888 inputs (166 tracked, 722
untracked), zero hidden-index inputs, 1205 dirty paths, sidecar-input SHA
`6f848f9b9748c848e8a41f40ea8c7c0a16352f96e1d6b7be299280ccdb78bf9b`, stale stamp, and
missing Cursor observer bytes. No live session/model, benchmark, bridge restart, hook change,
package, sidecar build, Git action, deploy, publication, spend, or submission occurred.

## Prior checkpoint — durable goal control and prospective attention eligibility, 2 Sep 2026

Authenticated REST goal create, update, override, and live-session attachment now require a
bounded caller idempotency key and couple non-secret `bridge_bearer` actor evidence to one
immutable terminal `goal_control_operations` row in the same `BEGIN IMMEDIATE` transaction
as the domain mutation. The operation freezes the versioned canonical logical-request hash,
exact project/session/goal authority, semantic outcome, committed public response, and result
hash. Exact replay occurs before ordinary route authority reads, survives process restart and
stale CAS state, returns the original generated IDs/timestamps/receipt, and rejects key reuse
with different content. Legacy no-auth/internal paths remain unassured and receive no inferred
history.

A hostile review found that the early REST replay path could return a coherently rehashed
`response_json` whose outcome contradicted the operation authority. Reads now bind the stored
outcome and goal/session identities to the immutable scalar authority and reconstruct the
response through the typed Goal/session receipt validators before returning it. The exact
hostile regression fails closed. A forced operation-receipt insertion failure rolls back goal
creation, and a two-Store concurrent duplicate test proves one mutation plus one exact replay.

Desktop create/update/attach attempts now retain one key for an identical logical request
until a committed response is received. A lost response or bridge-token retry no longer turns
a user retry into a second create or mutation; changing request content or target scope mints a
new key.

Goal-control attention now has a separate prospective migration boundary, three immutable
coverage rows, and one append-only eligibility decision for every post-boundary authenticated
update/override/attach terminal operation. Each decision freezes the stable operation identity
and hashes, exact actor/project/goal/session authority, changed/no-op state, sorted mutation-time
live-session IDs, count, eligibility, and exclusion reason. Creates, no-ops, unattached edits,
paused/observe-only/detached targets, and internal/no-auth calls do not enter the observed
lower bound. An eligible update or changed attachment counts once; overriding two live sessions
still counts once. Missing/corrupt prospective decisions fail metrics closed, decision insertion
failure rolls back the domain mutation, and an immutable exact-ID snapshot preserves earlier
operations as unverified legacy without timestamp inference or backfill. The canonical human-intervention
total remains null because out-of-band manual context, verification, and consented active-human
time remain incomplete.

The already-running Cursor processes were inspected read-only. Their installed product contract
is observe-only and cannot prove same-session intervention delivery; no control hooks, second
Cursor, process restart, or fake live claim was introduced.

Exact gates on this filesystem: focused goal-control/attention tests **30/30**; widened goal/
Store/session/MCP authority cluster **114/114**; whole tree `uv run pytest -q` **1778 passed,
21 skipped in 1048.26 s (17:28)**; repository-wide Ruff clean; desktop **61/61**; production
frontend build clean with **52 modules**; focused and final diff checks clean apart from
informational Windows LF-to-CRLF notices.

Check-only release preflight remains correctly **NO-GO**: exactly 8 pets; 888 release inputs
(166 tracked, 722 untracked); zero hidden-index inputs; 1205 dirty paths; release-input SHA
`3a1cd6d40aa98f0b23f1f0419aa5cd7c8de840dfc79b6ce00ef0e667366491e1`; audit closure
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`; current sidecar
input SHA `fd92651dc3ace13cf92ccde39ab16a8c80d1d35fa6b2fa4a837327eaedf181d7`; stale stamp
`be840b7c65f57575d0f629dfe2ccccd9c0c026b8352a71985e7a8b8db0b931b0`; observer helper
missing. No live Codex/supervisor, companion restart, package, sidecar build, Git stage/commit,
AWS/deploy, benchmark, publication, or submission action occurred. Recovery's real Codex +
real Strands same-session milestone remains unchecked; overall status remains **NO-GO**.

## Prior checkpoint — actor-assured direct messages and handoffs, 1 Sep 2026

Goal-lifecycle follow-on audit found and repaired two spec-facing product defects without
widening the human-attention claim. Ledger-only `mode=override` now creates a real
successor and atomically moves attached sessions instead of silently patching the
predecessor. Same-value scalar updates are semantic no-ops and preserve `updated_at`.
Desktop replacement now sends the API-required exact `expected_goal_id`; its pure payload
contract covers initial, same-goal, and replacement cases. Same-value ledger saves retain
their Decision/Context identities, and a saturated bounded ledger read fails closed to the
transactional path. Current focused evidence is goal lifecycle **13/13**, broad
goal/Store/session-control/authority/auth **67 passed, 2 skipped**, desktop **60/60**, and
a clean 52-module frontend build. Goal actions remain
unmeasured pending required idempotency, actor assurance, intent revision, and an atomic
append-only receipt; no legacy Goal row is treated as human provenance.

Authenticated direct messages now have a prospective actor contract rather than being
inferred from `local_bridge_operator`. Operator auth mints a frozen, non-secret
`bridge_bearer` actor-evidence value; Store atomically freezes it with exact session,
vendor/harness, goal, typed project binding, request hash, reservation time, and v3
exact-turn contract before adapter I/O. Existing/internal v1 effects remain unassured with
no backfill.

On the first delivered terminal CAS, Store writes one append-only, content-free actor
receipt in the same transaction. Forced receipt failure rolls back delivery. Replay sends
nothing and validates the same row; restart seals an in-flight action uncertain without a
delivered receipt. Missing/corrupt reservation or terminal rows, payload downgrade, hash or
binding mismatch, and raw ledger mutation fail closed.

Attention metrics now count only validated delivered direct-message receipts under
`source_counts.direct_operator_message`, remove them from the unverified-message bucket,
and expose failed/skipped/uncertain assured outcomes separately. Authenticated REST
handoffs now use the same actor reservation and atomically couple their delivered receipt
with the bound Intervention/audit; MCP, automatic, internal, and legacy handoffs remain
excluded. Valid REST handoffs enter `source_counts.operator_context_handoff` exactly once.
Canonical human interventions stay null/unmeasured because other routes remain incomplete.

Three independent read-only audits covered direct provenance, handoff provenance, and the
attention definition/migration boundary. Exact gates: focused actor/direct/attention
**27/27**; session control **24/24**; actor handoff/attention **22/22**; broad
handoff/MCP/automatic **63 passed, 1 deselected**; 65-handoff stress **1/1 in 267.39 s**;
whole tree **1707 passed, 21 skipped in 828.51 s**; Ruff clean; desktop
**60/60**; production frontend build clean at 52 modules. The fresh whole run emitted no
warning.

Check-only release preflight remains NO-GO: exactly 8 pets; 888 inputs (166 tracked, 722
untracked); zero hidden-index inputs; 1201 dirty paths; stale/missing sidecars. Release SHA
is `4b1b3025daef477a082560f3f62e23380166e512b6ab79b8d0bd39daa8d8e6ea`;
sidecar source SHA is
`d66906e85c94ced814ea6f67fc6a05e2e5f179cdff4175f7817139ba54000fa3`;
audit closure remains
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`.
No live/provider/package/process/AWS/benchmark/Git/deploy/publish/submit action occurred.
Recovery's real Codex + real Strands milestone remains unchecked. Overall state remains
**NO-GO**.

## Latest checkpoint — immutable exact-turn delivery ledgers, 1 Sep 2026

Human decisions, direct messages, and context handoffs now share a prospective,
non-downgradable version-3 delivery contract. Existing pre-migration rows remain legacy
v1 without fabricated turn IDs. New v1 inserts/replacements and all version updates are
blocked. V3 reads bind SQL identity, frozen target, terminal state/result, exact Codex
receipt, canonical Intervention, and matching audit; corrupt delivered rows can no longer
replay as success or reactivate a second send.

First finalization and terminal replay use the frozen dispatch target rather than mutable
current discovery identity. Handoffs additionally require a strict bound Intervention,
exact delivery audit, and v2 dispatch/candidate authority. Restart recovery validates the
entire handoff before mutation; a hostile corrupt-watermark case rolls back both ledgers.
Human-decision current reads now use one SQLite snapshot, and attention metrics fail
closed on corrupt v3 projections.

Independent read-only audits covered direct receipts, handoff receipts/recovery, and the
human-decision migration. Exact gates: human hostile **5/5**; decision/attention **84/84**;
operator/handoff unit **19/19**; impacted REST/E2E **12/12**; whole tree **1698 passed,
21 skipped in 780.43 s**; Ruff clean; Cursor contract **37/37**; desktop **59/59**; frontend
production build clean at 52 modules; diff-check exit 0 with LF-to-CRLF notices only. The
whole run emitted one aiosqlite shutdown warning that did not reproduce in the exact test
or full Cursor contract; it is retained as a non-reproduced warning, not live evidence.

Check-only release preflight remains NO-GO: exactly 8 pets; 888 inputs (166 tracked, 722
untracked); zero hidden-index inputs; 1201 dirty paths; missing observer/stale sidecars.
Release-input SHA is
`d1c625bbae9560622cb1957f2ae1cdd8de00ce7c54df2edb155cb4d45922e794`;
sidecar-source SHA is
`c954a170550c4dafe876e1776c97c9dda35c1a5e0d3e87bd57b5b8fe35bb429d`;
audit closure remains
`94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`.
No live/provider/package/process/AWS/benchmark/Git/deploy/publish/submit action occurred.
Recovery's real Codex + real Strands milestone remains unchecked. Overall state remains
**NO-GO**.

## Latest audit/repair checkpoint — delivery, evidence, and packaged observe safety, 1 Sep 2026

The newest offline slice closed three hackathon-critical integrity classes. All Codex
message-producing paths now use one strict typed delivery resolver and persist exact turn
receipts; direct messages, handoffs, human decisions, Store seals, replay, Interventions,
and audit agree on the same identity. `ASK_HUMAN` outcomes now require the exact delivered
turn, so a later unrelated turn cannot be credited. Generic message finalization cannot
bypass handoff audit coupling, and human `delivered` status is sealed to a consistent
`send_confirmed` receipt.

Pytest evidence now requires an explicit, consistent terminal exit and complete summary
line. Exact/minimum passed and collected counts are typed; conflicting, ranged, malformed,
negated, or historical counts remain uncertain rather than becoming unconstrained.
Claim-independent minimum-count gaps are detectable, while skipped/xfailed/deselected
tests are not mislabeled as passing-count evidence.

Packaged Cursor observe/control helpers are separate binaries, both source-hash bound.
Default/desktop attach is explicit observe and ignores a hostile ambient control mode; a
missing observer aborts before hook-file mutation. Tauri exact wiring and sidecar stamp v3
bind bridge + control + observer, but the observer binary was not built because packaging
remains an action-time gate.

Exact gates: focused evidence **62/62**; broad durability **213/213**; Cursor contract
**37/37**; Node release contract **8/8**; final whole tree **1690 passed, 21 skipped in
640.85 s**; repository Ruff clean; desktop **59/59** and frontend production build clean
(52 modules); diff-check clean except informational LF→CRLF warnings.

Check-only release preflight remains NO-GO: exactly 8 pets, 888 inputs (166 tracked, 722
untracked), zero hidden-index inputs, 1201 dirty paths, stale/missing v3 sidecars. Release
input SHA is `938f83654499eddda4b69dfe019cabfa08a5f86643f73dda095d9a6c7e521b56`;
sidecar source SHA is
`94764d234faaf3d0e08b3c6ec55178def4384d04cd4d4c7d44e6f0e7bdcecaeb`.
No live/provider/package/process/deploy/benchmark/freeze/commit/submission action occurred.
Recovery's real Codex + real Strands milestone remains unchecked and overall status remains
**NO-GO**.

## Latest Recovery checkpoint — exact Codex turn causality, 1 Sep 2026

PEX now persists the exact Codex vendor turn returned by `turn/start` and attributes a
worker outcome only when the later event's metadata, canonical raw vendor reference,
thread, turn, and event identity all match that receipt. Same-thread unrelated turns,
conflicting nested item identities, forged metadata/raw references, malformed receipts,
and legacy no-receipt rows cannot acquire `helped:true`. The receipt is retained in the
canonical Intervention and SQLite/JSONL audit.

The reusable live proof contract is now `pex.codex.closed_loop.v3`. Supported NOOP must
have no worker-delivery receipt; an intervention proof must bind its delivered turn to the
final successful STOP and every observed event. Prepared live tests also configure a
detected local supervisor endpoint before model construction. No live Codex/provider was
invoked, so the Recovery live boxes remain unchecked.

Adjacent integrity repairs: Codex typed receipts no longer regress authenticated human
decision delivery; malformed typed turn results become conservative uncertainty; and
pause/resume metrics reject future-revision/semantically false receipts without treating a
valid unbound containment pause as global corruption. The canonical human-intervention
total remains null because coverage is incomplete.

Fresh exact-source gates: focused **102/102**; exact regression rerun **35/35**; legacy and
corrupt receipt hostile regression **1/1**; whole tree **1653 passed, 21 skipped in
617.72 s**; repository Ruff and diff-check clean apart from
informational LF→CRLF warnings. No live process, package, deploy, benchmark, freeze,
publish, stage/commit, or submission action occurred. Overall state remains **NO-GO**.

Fresh check-only release preflight is correctly NO-GO: exactly 8 pets, 887 inputs (166
tracked, 721 untracked), zero hidden-index inputs, 1201 dirty paths, and stale sidecars.
Release-input SHA-256 is
`d5b0a9b474a1b48f1c2079b48e0161685fb3073efecabcdbfca2c922b8db3726`; current
sidecar-source SHA-256 is
`bb37a07b1c8731503b151b36808dd629bd0ac09abcccadcce68e542d4c8da459`.
Toolchains/Tauri wiring pass; no sidecar or package was built.

## Latest spec-correction checkpoint — authenticated session-control action receipts, 1 Sep 2026

Pause/resume now requires the operator bearer and writes one immutable prospective human
action in the same transaction as a real control-revision change. Separate immutable
coverage rows declare the pause and resume migration start without backfilling history.
Receipts bind actor assurance, exact session/goal/project identity, control revisions, and
before/after session digests; replay/no-op creates no duplicate and forced receipt failure
rolls back the state mutation. Internal unassured Store calls are not called human actions.

Attention metrics count these exact rows as `source_counts.supervision_control`, expose
both action/coverage watermarks and coverage records, and no longer list pause/resume as
unmeasured. The canonical total stays null because goal mutations/attachment, out-of-band
work, and active-human time remain incomplete. Direct worker message now also requires the
operator bearer with 403/401/503-before-Store proof, but remains actor-unverified until a
separate prospective terminal-effect ledger exists.

Fresh receipts: focused session-control/attention **28/28**; direct-message **6/6**;
MCP **5/5**; M0 **10/10**; desktop **59/59** plus clean production build; exact whole tree
**1642 passed, 21 skipped in 600.95 s**; repository Ruff/diff clean except informational
LF→CRLF warnings. The first whole run exposed one stale no-auth pause fixture; it was moved
to the authenticated operator path without weakening behavior, and the fresh full run
passed.

Check-only release preflight remains NO-GO: exactly 8 pets, 887 inputs (166 tracked, 721
untracked), zero hidden-index inputs, 1201 dirty paths, and stale sidecars. Release input
SHA is `dcbb32819319a6f07e22064e5ee8da443bb7026c5a995ce6a2c7cd7d99fcc057`;
sidecar source SHA is
`cba12458e729cde23c383c48383ce9c2723e91d90f1a70c60ce215ca85946e7e`.
No package/live/provider/deploy/freeze/submission action occurred. Overall state remains
**NO-GO**.

## Latest spec-audit checkpoint — lifecycle producer remains honestly unavailable, 1 Sep 2026

All three specs and every candidate producer were reread. The cleanup/restore foundation
is safe and durable, but `register_lifecycle_resource()` and
`mark_lifecycle_resource_cleanup_ready()` still have **zero production callers**; every
current resource is test-seeded. `FORK_PROBE` and `START_AGENT` create sessions but no
isolated PEX-owned filesystem child. Existing temporary directories self-clean, adapter
subprocesses have direct lifespan owners, and overlay/config changes have separate Undo
authority. PexBench workspaces are project roots plus retained evidence while the manifest
is unfrozen, so registering them as disposable would violate provenance and benchmark
fairness. Path-only lifecycle resources also cannot safely represent stale processes.
Separately, cleanup-ready resources are never projected into `SupervisorRequest`, so the
model has no legitimate exact IDs from which to propose cleanup; registration alone would
not make the product path live.

The safe decision is therefore **NO-GO for producer wiring now**. No convenience registrar,
path/PID heuristic, dummy resource, or test fixture was promoted to production. Revisit
only when `FORK_PROBE` really creates an isolated worktree or a finalized benchmark run
provides creation-time sandbox ownership and post-finalization disposability evidence.
This audit changed documentation only; the current code receipt remains **1635 passed,
21 skipped**, desktop **59/59** plus clean build, with Ruff/diff gates clean. The next safe
offline slice is actor-assured human-action coverage from an explicit migration boundary.
Release/live/provider/package/deploy/freeze/submission state remains **NO-GO**.

## Latest spec-correction checkpoint — authenticated minimized handoff, 1 Sep 2026

The REST handoff mutation now requires the operator bearer even in explicit test-only
no-auth mode. Coverage proves 403 before Store/pipeline/adapter work when auth is disabled,
401 for missing/wrong bearer, 503 when auth is enabled but the bridge token is unavailable,
and exact-bearer success with stable `local_bridge_operator` idempotency. Automatic and MCP
handoffs retain separate principals.

`pex.handoff-bundle-receipt.v1` now carries effect ID, canonical SHA-256 digest, exact
ContextItem IDs/count, token estimate, and detail authority without bundle text. The exact
bundle remains in the immutable operator effect, actual target delivery, one authenticated
top-level REST response field, and explicit authenticated desktop detail. Nested handoff
interventions, MCP responses, default intervention lists, event/WebSocket publication, all
three lifecycle audit rows, and JSONL use only the receipt. Historical/canonical v1 bound
Interventions still retain their internal exact payload; removing that internal duplicate
requires a separate versioned migration.

Fresh receipts: handoff E2E **57/57**; MCP/operator-effect/audit gate **20/20**; desktop
**59/59** and production build clean; exact whole tree **1635 passed, 21 skipped in 605.15
s**; repository Ruff clean; diff-check clean except informational LF→CRLF warnings. The
release-input contract was correctly updated from 886 to 887 after adding the receipt
module. A one-off non-fatal aiosqlite thread warning did not reproduce with the named test
under warning-as-error or in the fresh final full suite; no speculative source change was
made.

Fresh read-only preflight remains `source_ready:false`, `release_ready:false`: exactly 8
pets, 887 inputs (166 tracked, 721 untracked), zero hidden-index inputs, 1201 dirty paths,
and stale sidecars. Release-input SHA-256 is
`281011b0cd0f2912d81da55f20f2081ae391437f450a33521eea7c0643aaecd1`; current
sidecar-source SHA-256 is
`de930a0a1c84341760bb4e6f650f00f2e680975aa7ffc7cc84be84f23f74adcb`.
No package was built. Real isolated Cursor↔Codex target-action proof, lifecycle producer,
live supervisor/Codex, package/AWS/deploy/benchmark/submission remain open or action-time
gated. Overall state remains **NO-GO**; no validated leaderboard/rank is known.

## Latest spec-correction checkpoint — indexed handoff routing, 1 Sep 2026

All three binding specs were reread. The former newest-64 typed-evidence scan could hide an
authentic older delivered handoff and is now retired. Append-only/update-delete-blocked
context and artifact candidate ledgers plus one immutable manifest are atomically committed
with `pex.handoff-dispatch-watermark.v2` and the final pre-adapter-I/O dispatch CAS. Counts,
digest, complete expected sets, exact bundle membership, effect/intervention/session/goal,
vendor/harness, and typed project bindings are revalidated on every load; no current-state
backfill is allowed.

Explicit ACK routing is exact and ambiguity-detecting. Passive artifact routing is exact,
newest-first within 24 hours, and one event/one owner. Relevant v2 corruption fails typed
evidence closed without falling through to an older effect. Optional derivation uses a
SAVEPOINT so an index/evidence fault cannot roll back the primary accepted worker event;
corrupt explicit ACK progress still rolls back atomically. Legacy v1/no-manifest handoffs
report `monitoring_unavailable_legacy`; v2 missing/corrupt manifests are corruption. Status
exposes `immutable_dispatch_candidate_index` with `capacity_limited:false`. All evidence
remains `verified:false` and `assimilation_proven:false`.

Windows path identity now avoids Unicode casefold-expansion aliases and rejects
drive-root-relative spellings; POSIX preserves literal backslashes. Desktop types/copy show
indexed versus legacy monitoring and never claim understanding. Hostile coverage includes
65 handoffs followed by the oldest exact ACK/read, corrupt-newer no-fallthrough, immutable
tables, manifest deletion, insertion/ACK rollback, legacy truth, and Unicode/platform path
aliases.

Fresh receipts: handoff E2E **53/53**; adjacent handoff/MCP/protocol gate **49/49**; path gate
**5/5**; exact presentation race **12/12** fresh processes and event-processing module
**11/11**; pet atlas runtime contract **10/10** fresh processes; whole tree **1631 passed,
21 skipped in 693.51 s**; desktop **59/59** and production build clean; repository Ruff
clean; diff-check clean except informational LF→CRLF warnings. The old 1624/21 receipt below
is historical and is superseded by this checkpoint.

The whole gate found and repaired two unrelated Windows test failures without weakening a
timeout or assertion: presentation tasks now release their strong reference inside their
own `finally` before completion, and the pet atlas test writes directly into its final
evidence layout instead of performing a synthetic sharing-sensitive manifest rename. The
production atlas writer had no leaked handle.

Fresh read-only release preflight remains `source_ready:false`, `release_ready:false`: 886
inputs (166 tracked, 720 untracked), zero hidden-index inputs, 1200 dirty paths, and stale
sidecars. Toolchains/Tauri wiring pass; no package was built. Real isolated Cursor↔Codex
target-action proof, REST auth/public-bundle hardening, lifecycle producer wiring, live
supervisor/Codex, packaging, AWS/deployment, benchmark freeze/run, and submission remain
open or action-time gated. Overall state remains **NO-GO**; no leaderboard/rank is known;
the built-in fleet remains exactly **8 pets**.

## Latest spec-correction checkpoint — target-side handoff evidence, 1 Sep 2026

The handoff path no longer treats bundle injection as evidence that the receiving worker
used or understood the context. A strict append-only evidence child now binds the exact
operator effect/intervention, bundle digest and ContextItem IDs, source/target vendor and
harness identity, goal and typed project snapshots, dispatch-start accepted-event
watermark, and exact target event or MCP mutation. It can report an exact artifact
read/edit as behavioral evidence or an exact target context citation as a self-attested
acknowledgement. Both remain `verified:false` and `assimilation_proven:false`.

The target's first three meaningful accepted events are also exposed separately. An early
ERROR/tool failure is only `possible_failure_observed` with
`handoff_failure_proven:false`; generic status/heartbeat/token traffic is excluded. One
passive artifact action credits only the newest eligible handoff, replay/restart remains
idempotent, and tampered evidence fails closed through full event/MCP/bundle binding
validation.

Real Cursor/Codex-shaped paths now work: Windows absolute paths are normalized relative
to the frozen project root with Windows case semantics, POSIX stays case-sensitive, and
out-of-root, traversal, drive-relative, alias, or `BEFORE` permission-time reads do not
qualify. Injected prompts expose stable context IDs and bounded file/deep-link pointers.

The desktop Interventions audit fetches the exact status for handoffs only, distinguishes
delivery-only/self-attested/behavioral/legacy/expired/not-delivered states, shows possible
early failure without causation claims, and expands the exact delivered bundle. Every
handoff says it is not proof of understanding or correct use.

Current focused receipts: handoff E2E **46/46**; operator/MCP/protocol/path gate **47/47**;
strict protocol/path unit gate **28/28**; final phase/timing hostile pair **2 passed,
44 deselected**; desktop **59/59** and production build clean. Final exact-tree
`uv run pytest -q -x`: **1624 passed, 21 skipped in 1018.95 s**. Repository-wide Ruff
and diff-check are clean; diff-check emitted informational Windows LF/CRLF warnings only.

The whole-tree gate also exposed and repaired a real Windows race outside the handoff
slice: SQLite could remove the hatch registry's transient `-wal`/`-shm` file between
`exists()` and `is_file()`, producing a false unsafe-path rejection. One `lstat` snapshot
now accepts absence while still rejecting non-regular files, symlinks, and reparse points.
The exact concurrent test passed five consecutive runs, hatch durability passed 27/27,
and the full suite then passed. No timeout/assertion was weakened.

Fresh read-only release preflight remains `source_ready:false`, `release_ready:false`:
886 inputs (166 tracked, 720 untracked), zero hidden-index inputs, 1200 dirty paths, and
stale/non-frozen sidecars. Release-input SHA-256 is
`a1c579ae1afacce7e64cacd18c710557e7bdf2ebbc8c3315f13dcf58583aae37`;
source-to-sidecar input SHA-256 is
`6b530d74914b279e039a513ba74c211f12960e8151c4a6582ed130bd39fd6001`.
Toolchains and Tauri wiring pass; no sidecar/installer/package was built. Overall
release/live/submission state remains **NO-GO**.

## Latest spec-correction checkpoint — durable attention truth, 1 Sep 2026

The previous Now panel was not defensible: it reduced either the newest 200 global
forensic interventions or, on fallback, the newest 40 current-authority interventions.
It counted PEX `ASK_HUMAN` requests as both human actions and decisions, used all
`helped` labels as an alert-quality denominator, averaged nonterminal actions, and
treated metadata presence as a completed reversal. That client reducer and its test were
deleted.

`GET /v1/attention/metrics` now returns `pex.attention-metrics.v1` from one SQLite read
transaction with an all-time window, as-of time, per-ledger rowid watermarks, exact
unbounded aggregates, separate aggregate/detail truncation, explicit coverage, and
`benchmark_evidence:false`. It separates:

- durable PEX attention requests;
- recorded and unresolved historical decisions;
- a current-live-authority pending inbox with an exact count and explicit newest-200
  detail truncation;
- authenticated observed human-action source counts;
- actor-unverified direct message/handoff counts;
- completed, attempted, failed, and uncertain PEX reversals.

Historical totals retain creation-time authority after quarantine or A→B rebound, while
the actionable pending inbox revalidates current session/goal/project authority and
excludes stale or superseded rows. The desktop consumes that pending snapshot for the
Decisions view and keeps `/v1/interventions` only as labeled recent forensic detail.
Headline metrics no longer change when the detail list crosses 40 or 200 rows.

Full human-action coverage is not claimed. Pause/resume, goal mutation, out-of-band
manual context/verification, and consented focus intervals lack complete append-only
receipts. Therefore the canonical human-intervention count remains null, with only a
clearly labeled authenticated observed lower bound. Human active seconds remain null
with consent `not_configured`; unnecessary-alert rate remains null because exposure and
adjudication are not recorded; average auto-resolution confidence remains null until a
terminal eligibility contract is frozen. These are honest missing measurements, not
zeroes.

The benchmark report separately gained `human_interventions_per_task` plus
availability-aware active-human-time totals, observed subtotal, median, missing count,
per-success value, and paired delta. Incomplete timing keeps complete totals/deltas null.
Operational product metrics are not used as benchmark evidence.

Focused receipts on this exact slice:

- attention Store hostile tests: **3/3** (empty/null semantics; 205 rows beyond both UI
  limits plus restart; quarantine and A→B historical/current separation);
- attention API plus M0 route file: combined backend gate **13/13**;
- benchmark report selection: **3 passed, 84 deselected**;
- desktop `npm test`: **58/58** and `npm run build`: **clean**;
- focused Ruff: **clean**.

Final exact-tree gate: `uv run pytest -q` -> **1608 passed, 21 skipped in 769.64s
(12:49)**; repository-wide Ruff and diff-check are clean. One unrelated presentation-task
timing test had failed during an earlier mixed focused run with a finished task still in a
set after 150 ms; its unchanged test passed alone and did not recur in the whole-tree
process. No assertion or timeout was weakened. Overall release/live/submission state
remains **NO-GO**.

Fresh read-only release preflight remains deliberately NO-GO: `source_ready:false`,
`release_ready:false`, 886 release inputs (166 tracked, 720 untracked), zero hidden index
flags, 1199 dirty paths, and stale/non-frozen sidecars. Current release-input SHA-256 is
`85fafaf4c34267574c288fedef6725f965e9ee2038ffaa32ef1fbd18a47b54d8`; current sidecar
source-input SHA-256 is
`4d7cdff72913a79b29ae142dd1a15a8d5aaf8a9cc659d98b223eddcb806d6276`.
Toolchains and Tauri wiring remain verified. No sidecar/installer/package was built.

## Latest winning-gate checkpoint — 1 Sep 2026

This section supersedes older rolling counts and release-input totals below it. PEX is
still **NO-GO** for submission/package/deploy/freeze, but the exact current code tree has
a fresh green receipt:

- `uv run pytest -q` -> **1603 passed, 21 skipped in 633.56s** after the complete
  supervisor BYOK/custom authority slice and Windows immutable-result lock repair.
- Provider/config/search/supervisor focused gate -> **126 passed, 1 skipped**; the first
  narrower provider/config gate was **94 passed, 1 skipped**. The three failures found by
  the first whole-tree run were repaired and the exact failing set passed **3/3** before
  the final whole-tree run.
- `uv run ruff check .` -> **clean**. `git diff --check` -> **clean** apart from
  informational Windows LF/CRLF warnings.
- Desktop `npm test` -> **59 passed** and `npm run build` -> **clean**.

### Supervisor BYOK/custom authority is now locally complete

Settings no longer mutates process environment as its persistence mechanism or stores a
raw key in JSON. A versioned, revisioned supervisor snapshot binds provider, model,
authentication mode, custom protocol, canonical base URL, credential source, and an
opaque secret reference. The public API/UI never returns that reference or secret. The
write path is serialized and compare-and-swap aware: it validates a complete candidate,
stages the secret, constructs the candidate model in task-local routing state, atomically
persists the snapshot, swaps the live model, and only then retires the previous secret.
Secret-store, model-construction, config-write, stale-revision, and restart failures all
roll back or fail closed without ambient-key fallback.

On this Windows host the installed keyring backend is
`keyring.backends.Windows.WinVaultKeyring` at priority 5. PEX accepts only recognized OS
keyring backends (WinVault, macOS Keychain, Linux SecretService/KWallet) and refuses
plaintext/fallback backends. The snapshot is bounded, duplicate-key and symlink safe,
atomic, and stores only the opaque reference. Credential envelopes are versioned and
audience-bound to provider/auth/protocol/base URL, so changing a routing boundary clears
the old credential unless an explicit replacement is supplied.

The runtime now distinguishes API-key, local, custom, login, Bedrock, and AgentCore auth
modes; custom OpenAI-compatible and Anthropic-compatible endpoints are implemented.
Remote custom endpoints require canonical HTTPS; HTTP is limited to literal loopback.
Credentials, query strings, fragments, percent/backslash ambiguity, default-port aliases,
ambiguous IPv4 forms, IPv4-mapped IPv6, and cleartext LAN/metadata endpoints are refused.
A keyless custom OpenAI-compatible route cannot inherit `OPENAI_API_KEY`, and a named
provider override cannot retarget a vendor ambient key. Consumer login and AgentCore auth
remain truthfully unimplemented/degraded instead of silently becoming API-key/Bedrock
requests. Azure OpenAI and generic SageMaker construction also remain unavailable rather
than making false compatibility claims. Every inference provenance record can carry a
secret-free configuration fingerprint; request IDs remain null when the SDK does not
provide one.

This is offline constructor/fake-store/API/restart evidence, not a paid-provider call or a
packaged credential proof. No real OS credential was written by tests, no real model was
invoked, and no frozen executable was built. The source build now collects dynamic
`keyring` backends, but packaged WinVault read/write/delete still requires an authorized
fresh sidecar/package build and packaged QA. HTTPS hostname DNS rebinding and
cross-origin redirect credential behavior also need a dedicated hardening pass before a
broad SSRF-resistance claim.

The AgentFingerprint planner path no longer groups mutable current session rows. Its
target cohort comes from the exact `event_processing.accepted_session_json` and
`accepted_project_binding` captured before planning for the current event. Historical
interventions must be the exact intervention named by a committed `pex.event-plan.v1`,
carry a strict `pex.intervention-bound.v1` envelope, bind the same `trigger_event_id`, and
match immutable session, goal, vendor, harness, action, and typed project-binding scalars.
A cohort may influence a score only when all of these are true:

- the accepted event is a real pipeline event with a persistent goal;
- the accepted project binding is `identity:...`, never `legacy:...`;
- model is known and `metadata.model_settings_hash` equals SHA-256 of the canonical model,
  reasoning-effort, and `metadata.model_settings` payload;
- model, reasoning effort, settings hash, project class, harness, and physical project
  binding match the immutable accepted history;
- verifier status is exactly `supported`, `contradicted`, or `acceptance_gap`;
- counts are nonnegative/coherent and the Store marks history/settings/project provenance
  complete.

Unknown settings, legacy bindings, malformed/mismatched acceptance snapshots, orphan or
wrong-schema interventions, missing/spoofed trigger bindings, non-finite corruption,
unknown verifier statuses, current-session mutation, and manually incomplete buckets now
fail closed. Planner authority uses a process-local non-serializable Store seal, so
copying visible booleans into a dictionary is neutral. Harness-wide Deck fingerprints
remain descriptive but cannot recommend overlays. The accepted-event query and aggregate
run in one read transaction under the Store lock. The regression mutates a live session
after event acceptance and proves the older result remains in its original model/config
cohort.

Release closure is also narrower and independently hostile-tested. Production
`build-sidecar.mjs` now consumes `scripts/release-contract.mjs`; the tests attack hidden
Git index states, malformed index bytes, toolchain drift, widened Tauri permissions,
stale/forged sidecar stamps, malformed or reordered frozen inventories, TOCTOU changes,
path traversal/case aliases, and forged schema-2 evidence closure. The release walk no
longer sweeps all historical `_audit` residue. It includes exactly the manifest-reachable
closure:

- **886** current release inputs;
- **672** reachable audit artifacts: 597 current playback artifacts, 9 release roots,
  58 receipt-evidence files, and 8 runtime contact sheets;
- exact eight ordered pets: `pex, ledger, mesh, nudge, drift, quiet, ember, von`;
- audit-closure SHA-256
  `94dcebf5bfce4640bfad52be94b7437b511aa5efb10068081550aaf5c42c3470`;
- fleet manifest `866348ec48730d04bb366630514e64c36564666868f7c731d7787f229ee9c4ed`;
- fleet audit `ec759c3791b2c487beb43f18a5c7b02cad86fbfb4e08d25a16dc3b6aff0c3637`;
- direct playback receipt
  `57d63ccc75290b7660b45f3aa8c227156b71d9f2d8f67be9879548603fd87a9f`.

Fresh preflight remains truthfully `source_ready:false`, `release_ready:false`, and
`frozen:false`: 166 inputs are tracked, 720 are untracked, zero have hidden index flags,
the worktree has 1198 dirty records, and the sidecar stamp is stale. Toolchain pins and
Tauri wiring pass. No installer or sidecar was rebuilt; no Git index, commit, live vendor,
AWS resource, deployment, publication, or Devpost submission was touched.
The final release-input SHA-256 is
`8bb59b2e7f95b3aa3237ab21c822f3cd45d61a841e41d2a19e463210ba3f2012`; the final sidecar
source-input SHA-256 is
`cb1929107f72192862a135c48687a0730a4bdcb788c3dc2d70f127c57721feab`.

The official deadline remains **14 Sep 2026 at 5:00 PM PDT** and no scored public
leaderboard is available. The recovery spec still makes the real Codex + real Strands +
same-session outcome/audit loop the binding completion milestone. That action remains
fresh-authorization gated (`PEX_LIVE_CODEX=1` and `PEX_LIVE_SUPERVISOR=1`). Until then,
continue only safe offline spec closure. BYOK/custom backend authority is now closed in
local proof. Highest-ranked remaining safe gaps are typed handoff-assimilation evidence,
wiring lifecycle cleanup to one real producer, and closing future human-action ledger
coverage without fabricating historical events.
Do not substitute polish or synthetic benchmark scores for the required real loop.

## Fresh current-tree gate — 1 Sep 2026

The current local contract suite is green on the dirty tree, but the core recovery milestone is **not complete**: the real Codex + real supervisor + same-session continuation/outcome/audit loop remains unproven. This is a local gate, **not** a claim that PEX works end to end, nor a live-provider, packaged-installer, deployment, leaderboard, or submission claim.

- `uv run pytest -q` → **1567 passed, 20 skipped** in 385.04s on the final exact tree after the release-boundary regressions. The first post-overlay run was **1527 passed, 20 skipped, 34 failed**; all 34 failures were audited rather than suppressed. The repaired previous-failure matrix passed **186/186** together, the first whole-tree repair gate reached 1562/20, the truthful-projection/anti-overfit regressions raised it to 1565/20, and two release-seal/preflight tests raised the fresh receipt to 1567/20.
- `uv run ruff check .` → **clean**. `git diff --check` → **clean** apart from informational Windows LF/CRLF warnings.
- Desktop: `npm test -- --runInBand` → **51 passed**; `npm exec tsc -- --noEmit` → **clean**; `npm run build` → **clean**.
- Tauri/Rust: `cargo test` → **8 passed**; `cargo check` → **clean**.
- Pets: `npm run validate:pets` proves the exact ordered built-ins are **`pex, ledger, mesh, nudge, drift, quiet, ember, von`**. The read-only runtime-contract audit with `--seal-current-evidence-root apps/desktop/src/pets/_audit/release/current-20260831` returned **`ok: true` for all eight**, with no repaired or occupied unused cells.

Overlay consumers are locally end-to-end complete across Store, executor, pipeline/recovery, REST, and desktop. New apply now requires the exact live, bound, ALLOW, reversible `APPLY_OVERLAY` intervention for the same proposal/session/goal/project; ownerless, wrong-owner, denied-owner, and owner-disappeared reservations fail before probe or adapter I/O. Parent effects require the exact apply/revert operation kind and overlay id. Apply reserves before probe, only the Store start-CAS winner dispatches canonical frozen inputs, cancellation finalization is retained, expiry drains beyond 1000 with overlap coalescing, recovery consumes durable child truth before mutable planning, and Undo is exact-owner/operator/idempotency bound with path-free truthful receipts. The expanded overlay gate is **70/70**; REST route files are **32/32**; the earlier cross-layer recovery bundle was **109/109**; desktop is **51/51**.

The full-suite repair also closed two genuine pre-existing production bugs without relaxing authority: pending human `START_AGENT` / `STOP_AGENT` / `FORK_PROBE` actions now project `NEEDS_DECISION` so an approved fork can reserve, while normal STOP/NOOP remains stopped; and agent fingerprint queries now read the current `pex.intervention-bound.v1` envelope with explicit legacy-row fallback. Stale tests were repaired with real persistent goal/session/project bindings and exact bound-envelope assertions.

The post-gate red-team then closed two judge-visible truth gaps. Pet and Deck now revalidate bounded sessions/goals/interventions/events through live Store authority, so quarantined or A→B-rebound rows remain forensic history and cannot drive working/drifting/needs-you counts or current actions. Agent fingerprints still show a one-sample failure, but do not recommend `evidence-before-done` until two distinct gap sessions match the planner's anti-overfit threshold. The combined focused gate is **29/29** and both changes are included in the fresh **1567/20** full run.

Remaining deadline-critical proof is deliberately separate: a real Codex same-thread recovery loop with `PEX_LIVE_CODEX=1`, packaged Tauri QA, a clean reproducible current exact-eight bundle, and any Devpost/AWS/live-provider action. Direct animated playback is now proven separately for all 72 state cells, but it does not clear those release or live-product gates. Each gated action still requires fresh operator authorization where noted. The manifest remains **`frozen: false`** and overall submission status remains **NO-GO**.

PEX has a substantial locally verified supervisory control-plane implementation and compact companion window, but the recovery spec forbids calling the product complete before the fresh real Codex loop succeeds. Current implementation context is in `docs/AGENT_HANDOFF.md`; the three PEX specs prevail on conflict. Desktop inventory tiles cannot hold a goal, send, or receive a context handoff. Observe JSONL keeps `workspace_roots` through huge edits so a Cursor conversation can bind a project. REST, MCP, automatic event follow-up, and the internal compatibility entry point converge on durable authority-bound ledgers. Creation-time project binding, intervention and lifecycle-resolution identity, cleanup/restore, overlay apply/revert/Undo, and current-state projection are locally integrated. The fresh whole-tree receipt is **1567 passed, 20 skipped**; Ruff is clean; desktop is **51/51** with TypeScript and production build clean; Rust is **8/8** with `cargo check` clean. This remains local/mock-adapter proof rather than live-vendor acknowledgement. Manifest remains **`frozen: false`**.

The closed loop now starts in the companion: create a persistent goal (objective, acceptance, constraints/non-goals) and attach it to a worker. Auto-handoff injects the smallest observed bundle into a sibling session on the same project without an explicit POST. STOP extracts structured claims instead of treating silence as "done." Drift with repeated low-information commands can redirect during work; STOP still inspects rather than nags.

Exactly eight built-in Codex-v2 pets are present on disk (`pex`, `ledger`, `mesh`, `nudge`, `drift`, `quiet`, `ember`, `von`) with `spriteVersionNumber: 2`; custom imports and unfinished hatch candidates are separate. Current evidence under `apps/desktop/src/pets/_audit/release/current-20260831` records eight passing repo runtime contracts, **456 exact decoded RGBA frames**, **72 GIF previews**, and eight contact-sheet, direction-sheet, continuity, and frame-review sets. `direct-playback-qa.json` now adds isolated-browser playback proof for **72/72 state cells** at intended scale: all 72 GIF hash/byte bindings and frame counts match, every decoded frame is unique within its GIF, and the 28 bound receipt artifacts independently rechecked with zero failures. The file-viewer's tainted-canvas status is explicitly non-evidence; timed visible-viewport screenshots plus per-cell RGB change and qualitative review are the proof. The generic external hatch validator reports false only because it expects an extended idle cell at row 0, column 6; this repo's runtime contract intentionally requires that unused cell to remain transparent. This evidence and critical release inputs remain untracked, packaged Tauri playback is unproven, and there is no current bundle. Settings can authorize one potentially billable image call only after an exact acknowledgement and readiness check; a provider result is only an unverified base candidate, never a finished atlas or playable pet.

The exact-eight release evidence is now transitively sealed into schema-2 fleet/release manifests and enforced by `build-sidecar.mjs`: 72 GIFs, 25 timed screenshots, and 456 decoded frames are rehashed through the same source authority that prepares the frozen bridge. The validator freshly decodes all GIFs, requires exact frame counts plus unique decoded frames, and compares every GIF frame to its canonical atlas-frame PNG within a strict palette-conversion bound. Evidence paths reject traversal/case aliases, per-pet evidence roles are canonical, blind-review artifacts must be distinct and structurally meaningful, and cached bridge reuse repeats isolated `--verify-bundle` inventory proof. A new check-only `npm run preflight:release` emits structured JSON and checks Git tracking/cleanliness (including hidden index flags), exact Tauri wiring, pinned active toolchains, source fingerprint, target-triple stamp, both helper hashes, and frozen inventory without building an installer; it repeats full input/status hashes after any cached executable runs. It correctly reports **NO-GO** today: 1,054 release inputs, 888 untracked, 1,191 dirty status records, and stale sidecars; Tauri wiring and toolchains pass. Node 24.19.0 and Rust 1.97.1 are pinned alongside Python 3.12.13, and PyInstaller 6.22.2 is lock-checked. This is stronger release engineering, not package proof: no current MSI/NSIS was built or inspected, and `release_ready` deliberately remains false.

## Latest verified control-plane slice

- Cleanup now reserves a durable child, crosses a sole Store start CAS, moves only the Store-frozen manifest, and records exact per-resource/parent terminal truth. Ambiguous or interrupted work is not blindly rolled back or replayed. This is an overlapping focused **87 passed, 1 skipped** local gate, not a full-suite certification.
- Restore is complete in focused local proof: a separate immutable operator-bound ledger, principal-scoped idempotency, sole start CAS, portable atomic no-replace executor, exact partial/cancellation/restart classification, atomic path-free intervention/audit projection, and truthful operator-authenticated REST/Desktop Undo. The generic lifecycle updater is disabled. Retained slice receipts include Store **11/11**, executor/Store/cleanup **31/31** independently, integrated Undo **45/45 selected**, route E2E **17/17**, and the then-current desktop **50/50**; these overlap and are not a full-suite total. The current whole-desktop gate is **51/51**. No production path currently creates lifecycle resources; a finalized PexBench sandbox is the only credible future producer identified, and it is not wired.
- Overlay is locally integrated end to end. Bound Store rows freeze identity and exact owner/parent authority; executor reserves before probe and dispatches only a canonical Store start grant; recovery consumes durable child truth before mutable planning; REST/Desktop Undo requires exact owner, operator auth, and stable idempotency and returns path-free truthful state. Runtime serving still fails closed after A→B, quarantine, pause, expiry, uncertain revert, or overflow, while exact authority-reducing revert and terminal replay remain available. The expanded overlay suite is **70/70**, REST route files are **32/32**, and desktop is **51/51**. This is local/mock-adapter proof, not a live vendor acknowledgement.
- The full-suite-only event-socket leak was root-caused to AnyIO cancellation re-entering awaited `finally` cleanup. Socket registry detachment is now synchronous and first; accept happens before registration; queue-full and lifespan shutdown detach before fallible close. A deterministic blocked-tail cancellation regression proves all registry maps empty immediately.
- Release/package and live Codex remain **NO-GO** and action-time gated. Exact-eight source/runtime/direct-playback evidence is now stronger but remains untracked; the surviving 28 Aug debug installers embed stale versions of all eight atlases. No current release bundle, packaged Tauri playback receipt, or real live-loop video exists. Historical/UI-only artifacts must not be presented as current live evidence.
- Current deadline-critical slice: preserve the fresh whole-tree gates, then obtain the real Codex App Server + `used_llm=true` same-thread recovery proof only with action-time operator authorization. In parallel, offline work may tighten tracked exact-eight release inputs and presentation evidence, but packaging/deploy/publish/submit remains gated.

## Ready enough to keep building on

- Offline supervisor contracts now exercise request-scoped read-only Strands inspect tools (`inspect_workspace` / git / file / artifact / process, `run_verification`) plus CORE §4.1 `web_search` and `scrape_url`, and a second fresh verifier Agent. Ask PEX can inspect eval artifacts from an attached cwd and run a read-only Strands review Agent without `decide()`. A semantic-only STOP intervention fails closed to NOOP on verifier rejection, timeout, malformed output, or evidence-free approval; deterministic verification truth and local policy remain authoritative. Tool names, combined model-call count, tokens, and verifier traces are audited. A fresh provider-live two-Agent capture is still required before this becomes demo evidence.
- Isolated Codex App Server inspect: complete task `NOOP`, incomplete task `SEND_NUDGE` on the same `threadId`, Zen `used_llm=true`, no canned `PEX:` prefix. ChatGPT.exe and the other starter desktop inventory tiles are observe/focus only: they cannot take a persistent goal (`409`) and cannot send. Same-socket JSON-RPC is still unproven. Older isolated and simulated receipts are historical, not fresh current-source demo evidence; the real Codex proof still requires action-time authorization and a new validated receipt.
- PexBench deliberately retains the five recovery-spec tasks and a hashed randomized 20-row schedule, shared worker+PEX budget, terminal abort/no-selective-rerun policy, schema-v2 timing/config/overhead records, and fail-closed statistical reporting. The prior 006–036 microtask expansion violated the recovery spec and was removed. Existing local rows predate the current contract, the fixtures do not yet supply the natural public-repository half, and the manifest remains deliberately **unfrozen** with no citeable impact score. Cursor+PEX still fails closed for presentation: same-session follow-up capture exists locally, but freeze also needs a live this-desktop chain and process-isolated `used_llm` audits. Do not cite leaked 1/5 vs 4/5.
- Live Cursor / OpenCode / Claude Code / Devin evidence is separate from the simulated-provider ACP/Qwen/Hermes contract tests. Grok Build, OMP, Kimi, and Qwen still require fresh provider-live attach evidence; Hermes hook-only correctly reports `send_failed` at session end because that hook cannot resume a stopped worker. This editor’s Cursor hooks are **observe** (JSONL, timeout 3, no failClosed, no before-shell/preTool gates). Control-mode destructive-shell holds are opt-in for isolated bench worktrees only. Restart the bridge after pulling.
- Compact Tauri companion: ~920×700, Settings as its own page, exactly eight built-ins, and the six-view command deck (Now / Decisions / Context / Interventions / Agents / Bench). Selected pet is a transparent desktop overlay. Hover looks then hops; click opens the inspector. This editor’s Cursor hooks are observe-only JSONL; they do not wait on policy. `beforeSubmitPrompt` ASK_HUMAN is a control-mode / pipeline contract, not this live install. Ask PEX is a read-only supervisor review. ACP send reports failure honestly. STOP extracts claims and checks them against observed pytest/artifact state; contradicted claims get a specific continuation, not a canned `PEX:` nag. Uncertain claims stay silent. Live Cursor `afterShellExecution` and Codex `commandExecution` / `turn/completed` items now become pytest `process_state` (shell output is not treated as a worker claim). A STOP with no “I am done” still names a missing required file when the workspace is observed. Codex item status `completed` is not treated as pytest exit 0. JIT overlays apply on harnesses that can actually change tools; Cursor hooks cannot, and PEX no longer smuggles overlays in as extra prompt text.
- The hash-locked Linux ARM64 supervisor image builds locally, runs as UID 10001,
  becomes healthy, imports the copied protocol/supervisor source, and completes a
  versioned deterministic `/invocations` smoke with a session-bound `NOOP`.
  This is only local HTTP-contract evidence. AWS AgentCore is **not** deployed
  (`aws sts` has no credentials here), and no live model invocation was made.
- Inter-agent MCP at `/mcp/` is locally proven through the official Python SDK
  client (`tests/e2e/test_mcp_server.py`): all eight tools named in `PEX_BUILD_SPEC.md` §25, exact-session
  binding, SECRET/LOCAL_ONLY exclusion, bearer auth (no query-string token), and
  mutations via canonical `Pipeline` paths. A live worker has not been observed
  calling this surface. This editor’s Cursor observe helper fail-opens immediately
  and never holds a shell or edit. Same-session stop follow-up is **not** claimed
  on observe. Opt-in `cursor_pex` control hooks belong in isolated bench
  worktrees only. Presentation freeze still requires a live two-stop chain plus
  isolated `used_llm` audits; the manifest stays unfrozen. Isolated STOP now extracts
  claims, verifies them against the public observation, treats a
  still-failing pytest on STOP as unfinished work, and lifts labeled TASK.md
  acceptance lists onto the isolated Goal. Create/patch fills empty Goal lists
  from labeled objective sections; explicit empty lists on PATCH stay empty.
  The inspector can edit the attached ledger (`PATCH /v1/goals/{id}`).
  Explicit override prompts are recorded as durable `Decision` rows
  (`GET /v1/goals/{id}/decisions`); control-mode `beforeSubmitPrompt` can still
  block a constraint contradiction and name the active constraint. This editor’s
  observe helper does not. Preferences extract
  from labeled objective lists and are editable in the companion.
  A downstream eval/train command with an observed missing required artifact
  (`dataset.parquet exists`) is redirected; inventing that missing file
  from the command name alone stays forbidden.
  Ask PEX (`POST /v1/ask`) answers the spec questions from stored sessions,
  interventions, and context without interrupting workers; it will not guess
  which approach looks better, and it will not claim eval finished without
  observed verification. Spec-shaped answers stay canonical even if a
  supervisor model is loaded. Secret context is excluded from knowledge-gap
  answers. Deleting a ledger-required artifact is held (`ASK_HUMAN`) before
  the command; agent output that contradicts an active constraint is redirected.
  An observed background train/server that is still running when the worker
  STOPs is checked against the OS process table; a live pid gets a specific
  wait/check nudge (command, pid, process table), not a canned `PEX:` prefix.
  An exited pid is not treated as abandoned. Broad edits of files the ledger does not name are redirected;
  compaction checkpoints the attached title, acceptance, constraints, and
  required files. Duplicate work on the same observed path or non-test
  command across sibling agents on the same goal is redirected to the
  earlier result; routine tests are not treated as duplicates, and vendor
  session ids stay out of the worker message. If the cloud supervisor is
  down, local deterministic corrections still fire (`used_llm: false`); a
  remote NOOP cannot erase an acceptance gap. A malformed Cursor hook does
  not stop sibling STOP inspect. Repeated identical failing commands now
  reach redirect drift and can apply a reversible overlay. Accidental
  ambiguity on `beforeSubmitPrompt` continues with a ledger-grounded
  rewrite instead of blocking. Claude Code `UserPromptSubmit` does the same
  via `additionalContext` without rejecting an already-submitted prompt;
  `PreCompact` injects the ledger the same way. Starter desktop inventory
  (Cursor, Codex, OpenCode, Hermes, Claude Code — not Grok Bot) is observe-
  first and never a freeze. The companion objective field is a textarea.
  A disable-pinned premature-stop CLI returns a real non-`PEX:` nudge
  (`used_llm: false`). Genuine passing pytest stays silent. That is not
  live-model evidence. Do not use old rolling suite counts as current proof;
  publish only a fresh post-change full-suite receipt. The manifest remains
  **`frozen: false`**; observe hooks do not satisfy same-session treatment.
  `four_arm.py readiness` is **`can_freeze`: false**; live
  `~/.cursor/hooks.json` is **observe**
  (fail-open JSONL, no failClosed, no before-shell/preTool gates).
  Desktop `npm test`: 51 passed (31 Aug). Compact is the pet plus live counts, not a
  worker catalog or pet shop. A drift nudge marks the session drifting in the
  present tense; PEX does not stamp “corrected” from sending the nudge.
  STOP inspect tools can query visible repo/git/artifact/process evidence and
  CORE §4.1 `web_search` / `scrape_url`; hidden evaluators stay refused.
  Ask PEX inspects eval artifacts from an attached cwd and can run a read-only
  Strands review Agent without `decide()`. AgentCore still does not receive tails or diffs.
  Overlay second click opens the command deck.
  Settings can enable overlay click-through; the pet window applies it only when
  that flag is true. Agents fingerprints show counted STOP evidence; they do
  not invent strengths or failure patterns. Unmeasured token/tool rates stay
  null. After two gap/contradiction STOPs, overlay-capable harnesses can pin
  evidence-before-done; a first-sample STOP still sends the specific nudge.
  Labeled decisions, rejected approaches, and unresolved questions persist
  as Decision rows and appear on the inspector. Handoff names a real next
  objective and rejected approaches instead of canned continue text.
  Context health is scored from observed compactions and forgotten facts;
  unmeasured token/summary fields stay null. After two forgotten-fact
  compactions, overlay-capable harnesses pin those facts; Cursor still nudges.
  Two cheap unresolved questions on STOP can propose a human-gated isolated
  fork (OpenCode `POST /session/:id/fork` when connected; never Autopilot).
  After both probes finish, the winner is continued and the loser waits for
  human dispose. That is synthetic/mock-HTTP evidence, not a live OpenCode
  dual-worker run. Human-decision waits also write a local attention inbox
  (`{PEX_HOME}/channels/inbox.jsonl`); Telegram/Discord/WhatsApp/Slack stay
  disconnected and are never reported connected. Worker nudges do not use
  that inbox and still must not start with `PEX:`. Open agent focuses a local
  window when the harness can, or opens an allowlisted existing Devin session
  URL; it will not invent hosts or open `/sessions/new`. That is allowlist
  evidence, not a live Devin click.

## Not ready (blocks submit)

| Track | Gap |
| --- | --- |
| Agent | Provider-live Grok Build, OMP, Kimi, Qwen, and Hermes ACP evidence is still missing. Hermes plugin can observe and deny/escalate tools, but `on_session_end` cannot queue context for a future turn. Devin polls org-api `exit` then `POST .../messages`. Pi, Prime, ZCode, and DeepSeek stay Unavailable until provider-specific integrations exist. ChatGPT.exe private JSON-RPC is not the isolated `codex app-server`. |
| Design | Companion stills and a local ignored/untracked `docs/demo/companion.webm` match the current home / Ask PEX / Settings UI; that video is not clean-checkout or submission evidence. Judged Devpost video still needs real live Cursor and Codex integrations (≤5 min). Settings can request one unverified base candidate; playable custom-pet assembly/QA is not implemented. |
| Backend | Four-arm manifest is unfrozen. Freeze requires one intact 20-row file with current suite/controller fingerprints, paired settings, fresh-workspace receipts, and real treatment evidence; merged local coverage and replayed Cursor stop payloads cannot pass. The live recovery loop must pass before adding natural-repository tasks. |
| Submit | Architecture PNG exists (`docs/architecture/pex-architecture.png`). No AgentCore AWS deploy (`aws login` still required), no ≤5 min YouTube/Vimeo live-attach pitch, 0/3 builder.aws.com posts published, Devpost Start project is available but **Submit is not done**. |

Never cite leaked 1/5 vs 4/5 under `benchmarks/results/INVALID_LEAKED_RUNS_DO_NOT_USE/`.
