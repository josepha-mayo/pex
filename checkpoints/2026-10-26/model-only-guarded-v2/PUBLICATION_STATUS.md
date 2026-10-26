# Guarded model-only v2 — historical WIP reconstruction checkpoint

This is **not missing full V14/latest recovery**, not public-deployment/BYOK readiness, and not live model qualification. Production model-only admission remains technically deny-all.

## Provenance and layout

This immediate checkpoint is DELTA-ONLY and NOT self-contained. `source/` contains the 15 changed guarded model-only v2 source/test/document files against the separate Inspector routing historical reconstruction checkpoint. The historical source chain starts at public reviewed commit `e50bf764335dc3b86cdc54e402fdf80cb84a1d06`, then archived paired-artifact/terminal-evidence corrections and the Inspector routing delta. Do not overlay this blindly onto current repository root/main.

`SOURCE_MANIFEST.json` records every selected source SHA-256 and Git blob SHA. `CHANGED_FILES.json` and `CHANGESET.patch` preserve 15 source/test/document changes against the Inspector lane; the sixteenth environment-example change is intentionally excluded. No opaque archive is required to inspect the preserved text changes. This is not a complete source snapshot; it requires the separately retained historical restoration. Excluded binaries/dependencies/media/setup are not bundled.

## Qualification at this immediate checkpoint

- 67 new focused tests pass; independent rerun: 67 pass.
- Broader default/operator verification was still being finalized at snapshot. This is a WIP qualification state, not a final full-suite assertion.
- No live transport, provider, model inference, benchmark, budget/accounting or native/public deployment qualification.
- Missing later owner/auth/origin/session and V14 hardening remains missing.
- Standalone managed transport is a separate directory/lane and has not been integrated here.

## Publication scope

Only changed guarded model-only textsource/tests/config/documentation plus checkpoint metadata. Excluded: all environment files/examples, workflow files, dependency bytes, runtime databases/state, screenshots/media, raw historical evidence, private benchmark task/answer/oracle material, private Library IDs and internal continuation/submission notes. Existing already-public synthetic redaction strings remain test fixtures, never credentials. Root/main, submitted snapshots and other branches remain untouched.
