# Inspector routing — historical reconstruction checkpoint

This is a source preservation/review lane, not a replacement for repository root, release or deployment. It is **not the missing full V14/latest application**.

## Provenance and layout

This immediate checkpoint is DELTA-ONLY and NOT self-contained. `source/` contains the three changed text sources against a historical restoration based on public reviewed commit `e50bf764335dc3b86cdc54e402fdf80cb84a1d06` plus archived paired-artifact and terminal-evidence corrections, followed by the three-file Inspector routing reconstruction. It is not claimed to be identical to that commit or current `main`.

`SOURCE_MANIFEST.json` records every selected source SHA-256 and Git blob SHA. `CHANGED_FILES.json` and `CHANGESET.patch` record this lane's three-file delta against the historical restored source. The exact delta is preserved without an opaque archive, but reconstructing a runnable tree requires the historical restored baseline; excluded binaries/dependencies/media and environment setup are not bundled. Missing historical V14, newer UI, owner/auth/CSRF/controller/session hardening remain missing.

## Qualification at checkpoint

- Focused production-handler routing regressions: 4 pass (before fix: 1 pass, 3 fail).
- Frontend tests: 453 pass; TypeScript, normal build and hosted build pass.
- Patch forward/reverse checks pass; dependency lock unchanged.
- Controlled state/history tests only, not a mounted whole-app or real-browser qualification.
- No provider/auth/backend changes, real inference, release or deployment qualification.

## Publication scope

Only the newly changed routing source/tests/config and checkpoint metadata are published here. Environment files (including examples), workflow files, dependencies, runtime databases/state, screenshots/media, raw historical evidence, private benchmark task/answer/oracle material, private Library identifiers and internal continuation/submission notes are omitted. Existing already-public synthetic token-redaction test strings are test fixtures, not credentials. Existing repository root and other branches are preserved.
