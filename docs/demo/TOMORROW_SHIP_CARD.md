# PEX tomorrow ship card

This is the shortest honest path from the current verified candidate to a
recordable and submit-ready MVP. Do not add features, rebuild without a code
change, run the unfrozen four-arm benchmark, deploy paid AWS resources, or switch
to a paid model.

## Live Devpost clock and scope — verified 12 September

The authenticated Devpost account is registered for **Agents for Humans** and
the event is accepting submissions. It does **not** yet have a PEX project or
draft submission attached to this hackathon. The official cutoff is
`2026-09-15 00:00 UTC` — **01:00 on 15 September in Lagos** — while Joseph's
working deadline remains tomorrow so recording and form review have margin.

The live requirements make the public YouTube/Vimeo video mandatory (maximum
five minutes), but do not require a website or zip. Strands Agents is required.
Amazon Bedrock AgentCore is optional and must remain described as implemented
and locally tested, not AWS-deployed. The newest organizer announcement says to
prioritize deterministic behavior over adding features. After the cutoff, do
not edit the project, submission, code repository, or video.

## 1. Accept the installed candidate — 10 minutes

Use the already installed NSIS candidate from product source `49385f2`. The
retained installer is:

`build/release-candidate-49385f2/PEX_0.1.0_x64-setup.exe`

Expected SHA-256:

`6fb27ff7d4ec986e5b64209b1f00b70cab6593b67daafa42e08add5bd90c6d92`

The exact installed candidate has cleared bridge startup, native Home and
Supervisor Settings, two-current-worker filtering, transparent Von rendering,
and a bounded resource sample. The unchanged overlay mechanics passed Pex/Von
switch, restrained drag, independent bubble dismissal, anchored `× Hide`,
hide/restore and ordinary-close cleanup immediately before the Home-only repair.
See `evidence/PACKAGE_49385F2_2026-09-12.md`. Concentrate the final recording
rehearsal on the public throwaway OpenCode recovery and quiet cases.

Stop immediately on Retry, freeze, opaque background, flying control, wrong pet,
unbounded growth, or a bridge that survives a normal PEX close. Keep the failure;
do not film around it.

## 2. Prepare the public throwaway demo — 10 minutes

Create two new empty folders outside the PEX repository, one for recovery and
one for quiet completion. Run `git init` in each. Do not reuse private source or
the historical proof sessions.

In the selected folder, start the worker server and attach a separate terminal:

```powershell
opencode serve --port 4096
opencode attach http://127.0.0.1:4096
```

Create the worker session in OpenCode before connecting PEX. In PEX Connections,
connect the same loopback address. In Supervisor Settings, verify Zen,
`muse-spark-1.3-contributor-free`, saved credential, and cap `3` off-camera. The
plain model ID without `-contributor-free` is not the approved route. Verify
auto-reload is disabled and allow no paid fallback.

Attach the exact persistent goal and prompts from `REHEARSAL_CARD.md`. Confirm the
workspace and vendor session identity before starting supervision.

## 3. Rehearse once, then record — 20 to 30 minutes

Run the controlled recovery first. PEX must observe missing `final.txt`, produce
one evidence-grounded Strands decision, deliver one correction to the identical
OpenCode session, observe the exact final bytes, record `helped:true`, and finish
with NOOP. Then run quiet completion in the second folder; require a completed
model-backed NOOP and zero PEX follow-ups.

If either route, credential, worker, delivery, outcome, or review is uncertain,
stop and retain the failed rehearsal. Do not reset budgets repeatedly or paste a
manual correction.

Record the maximum-five-minute take from `RECORDING_RUNBOOK.md`. Show the pet,
goal, same-session correction, exact artifact, Strands receipt, quiet NOOP, local
AgentCore-compatible protocol receipt and architecture. Say AgentCore is
implemented and locally tested but not AWS-deployed. Say the formal benchmark is
unfrozen and show no uplift or leaderboard number.

## 4. Publish and submit — only after the take passes

Before any external write, confirm:

```powershell
git status --short
git rev-parse HEAD
git rev-parse origin/main
Get-FileHash .\build\release-candidate-49385f2\PEX_0.1.0_x64-setup.exe -Algorithm SHA256
```

The worktree must be clean, local and remote main must match, and the installer
hash must equal the value above. Then:

1. complete the explicit Devpost rules-review acknowledgment;
2. create the PEX Devpost project/draft for `agentsforhumans` (registration alone
   did not create one);
3. upload the accepted unsigned installer plus SHA-256 to a public GitHub release;
4. upload the final public YouTube/Vimeo video, maximum five minutes;
5. fill Devpost from `docs/SUBMISSION.md` and `docs/JUDGE_TESTING.md`;
6. add `docs/architecture/pex-architecture.png`, AWS Builder ID, public repo,
   video URL, installer URL and the already-published bonus-post URL;
7. review the rendered entry and only then confirm the final submission action.

External publishing and the final Devpost submit require explicit action-time
authority. The product must not claim a cloud AgentCore deployment, formal
benchmark improvement, Cursor leaderboard result, or more than the two shipping
pets.
