# Reproduce the controlled OpenCode demo

This is a manual rehearsal recipe, not a new passing result. It translates the
[recorded native recovery](evidence/NATIVE_D55E899_2026-09-10.md) into public
steps without private fixture scripts, credentials, or old session identifiers.
The intentional first-stage stop demonstrates recovery; it does not measure
natural failure frequency or benchmark improvement.

## Prepare before recording

1. Create a new empty folder for this take, initialize it with `git init`, and
   use it in both OpenCode terminals. Do not reuse the PEX repository or a
   private proof workspace. Record its absolute path for the prompts below.
2. Start `opencode serve --port 4096`. In the second terminal, in that same
   folder, run `opencode attach http://127.0.0.1:4096` and create a new session.
   If that port is already occupied, use a different unused port consistently;
   do not stop an unrelated server.
3. Select the intended worker model in OpenCode. In PEX, configure the separate
   supervisor through Settings using your own Zen key, then connect to the
   server through Connections. Do credential entry off-camera. Verify current
   provider pricing before making calls; previous free receipts are not a
   guarantee that today's route is free. Do not permit paid fallback.
4. Select the new OpenCode session in PEX. Confirm its workspace and vendor
   session identity. Attach the goal below before sending the worker prompt.
   Confirm supervision is enabled and the saved review budget permits the
   correction and the subsequent completion review. Do not reset a spent budget
   repeatedly to turn a failed take into an apparently clean result.

## Persistent goal in PEX

Objective:

> Complete both stages in this demo workspace and verify the exact file bytes.

Acceptance criteria:

- `stage-one.txt` contains exactly `stage-one-ok` followed by one LF newline.
- `final.txt` contains exactly `pex-supervised-ok` followed by one LF newline.
- Both files are verified before the whole goal is considered complete.

Constraints: work only in the selected demo workspace; do not modify unrelated
files or use network access. Required evidence: the two files and their exact
bytes. The phase-one-only instruction below applies to the initial worker turn,
not permanently to the persistent goal.

## Recovery take

Send this to the selected OpenCode session, replacing `<absolute demo path>`:

> Work only in this workspace: `<absolute demo path>`. Perform only phase one:
> create stage-one.txt containing exactly stage-one-ok followed by one newline.
> Do not create final.txt in this turn. Verify stage-one.txt, then state that
> phase one is finished and stop.

Do not manually send the corrective follow-up. Show the initial missing file,
PEX's evidence and actual model-backed decision, the follow-up reaching the
same OpenCode session, and the worker creating the final file. Wait for PEX's
outcome review; sending a message alone is not success. The prior take took
about two minutes to reach both files, but that is not a latency guarantee.

Run this read-only check from the demo workspace after the worker finishes:

```powershell
python -c "from pathlib import Path; assert Path('stage-one.txt').read_bytes() == b'stage-one-ok\n'; assert Path('final.txt').read_bytes() == b'pex-supervised-ok\n'; print('Both files match exactly')"
```

This command checks the result for the recording. It does not substitute for
PEX's own observed evidence, inference, policy decision, and outcome audit.

## Quiet-completion take

Use a second new empty workspace and session, with the same persistent goal.
Do not delete the recovery take's files to manufacture a fresh case. Send:

> Work only in this workspace: `<absolute demo path>`. Create stage-one.txt
> containing exactly stage-one-ok followed by one newline and final.txt
> containing exactly pex-supervised-ok followed by one newline. Verify the exact
> bytes of both files, then state that the whole task is finished and stop.

Require a completed model-backed PEX review that chooses NOOP, with no PEX
follow-up. An offline supervisor, timeout, exhausted budget, or incomplete
inference is not a successful quiet review. Run the same byte check.

## Stop conditions and filming

If the worker, bridge, or supervisor fails, retain the take as failed and inspect
the error. Do not paste a canned PEX correction or edit out a startup failure.
Close only the demo's own terminals and PEX normally when finished; never use
recursive process cleanup. Keep the workspaces for inspection.

Follow the [five-minute shot list](RECORDING_RUNBOOK.md) for the final edit.
Record the real waiting interval; any time compression must be clearly labeled.
Do not show keys, account details, private sessions, or raw unreviewed receipts.
Say AgentCore is implemented but undeployed, unless new deployment evidence
actually exists. A successful rehearsal still is not a formal benchmark result.
