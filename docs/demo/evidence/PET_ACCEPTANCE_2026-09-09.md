# Pex and Von pet acceptance — 9 September 2026

This receipt records a fresh, read-only acceptance pass over the two pets selected for the
submission story. No atlas or manifest was changed during this pass.

## Structural validation

The bundled Codex workspace Python ran the `hatch-pet` v2 atlas validator against the current
repository files:

```powershell
python validate_atlas.py apps\desktop\src\pets\pex\spritesheet.webp --require-v2
python validate_atlas.py apps\desktop\src\pets\von\spritesheet.webp --require-v2
```

Both commands returned `ok: true`, `errors: []`, and `warnings: []`. Each image is a
1536x2288 RGBA WebP laid out as 8 columns by 11 rows with sprite version 2 and zero transparent
RGB residue pixels. Their current SHA-256 values match `apps/desktop/src/pets/release-manifest.json`:

- Pex: `CE9A714836353C752A5C1BB794A639F03755E39751AB106B8A2A8C1730C6F1A3`
- Von: `AE1D4517C1C172DCF135ED107201DAEE5EE3BB12E2132FEE303DF1DA7D6A830E`

The first desktop validation invocation stopped before validating because `rustc` was absent
from the ambient `PATH`; it is excluded from the result. After prepending the repository's
pinned Rust 1.97.1 toolchain, the actual validation completed successfully:

```powershell
$env:PATH = 'C:\Users\JosephMayo\.rustup\toolchains\1.97.1-x86_64-pc-windows-msvc\bin;' + $env:PATH
npm --prefix apps\desktop run validate:pets
```

Result: `ok: true`, with exactly the required ordered built-ins `pex`, `ledger`, `mesh`,
`nudge`, `drift`, `quiet`, `ember`, and `von`.

## Original-resolution visual review

The generated contact and 16-direction sheets were inspected at original resolution for both
pets.

- Pex is a clean navy-and-cream owl with a stable silhouette and readable idle, locomotion,
  wave, jump, failure, waiting, work, review, and look states.
- Von is a small fluffy dark-navy cat with coherent state changes and especially legible laptop
  work/review frames.
- Both direction sets progress coherently through the full circle; their gaze and head/body
  orientation visibly change instead of repeating one neutral pose.
- Transparency is clean. The checkerboard visible in the contact sheets is the review surface,
  not a baked pet background.

No visual defect found in this pass justifies last-minute sprite regeneration. That restraint
also preserves the already-bound package hashes.

## Claim boundary

This is source-atlas structure and static visual evidence. It does not prove native Tauri
animation timing, transparency composition, drag/click behavior, message dismissal, pet
hide/restore persistence, or idle resource stability. Those remain inside the separately
guarded bounded native smoke because the user previously reported a whole-PC freeze while PEX
was idle.
