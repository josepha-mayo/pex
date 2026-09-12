# PEX 0.1.0 RC1 — Windows judge build

This unsigned Windows release candidate is built from exact product source
[`49385f2`](https://github.com/josepha-mayo/pex/commit/49385f2). It is intended
for hackathon judging and evaluation, not broad production deployment.

## What is included

- Exactly two desktop companions: Pex and Von.
- OpenCode HTTP and isolated Codex App Server worker support.
- Zen BYOK with `muse-spark-1.3-contributor-free` as the first suggestion.
- Bounded Strands supervision with local deterministic verification and policy.
- Same-session evidence-specific intervention and quiet `NOOP` behavior.
- A locally tested AgentCore Runtime-compatible protocol; no AWS deployment is
  claimed.

## Downloads

- `PEX_0.1.0_x64-setup.exe` — recommended NSIS installer.
- `PEX_0.1.0_x64_en-US.msi` — MSI alternative.

Both packages are unsigned. Windows may display a publisher warning. Verify the
hash before running:

```text
PEX_0.1.0_x64-setup.exe
SHA-256 6FB27FF7D4EC986E5B64209B1F00B70CAB6593B67DAAFA42E08ADD5BD90C6D92

PEX_0.1.0_x64_en-US.msi
SHA-256 5C60B8FB322E8F8A187CBB103B58FF852CA09BBC79C7104483836F8E550747D5
```

Post-publication verification on 12 September followed the anonymous NSIS asset
redirect to HTTP 200 with `Content-Length: 101680803`. GitHub's asset metadata
reports the same SHA-256 digests shown above for both uploaded files.

## Judge path

Follow [`docs/JUDGE_TESTING.md`](../JUDGE_TESTING.md). PEX ships without a
provider credential. A semantic run requires the evaluator's own key and
provider account. Saving a key does not itself prove model inference.

## Honest boundaries

- Windows only for this candidate.
- Cursor is observe-only in the focused MVP.
- AgentCore is implemented and locally tested, not deployed.
- PexBench is unfrozen; no comparative productivity score is claimed.
