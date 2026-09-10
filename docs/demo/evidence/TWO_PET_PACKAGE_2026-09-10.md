# Two-pet MVP package: verified contents, native checks pending

Source: `4de1db89b0c00fd1d3d92460614093ca3b20fd09`. The source checkout was clean
through build and verification. Both changes were pushed to main.

## Scope and behavior

Only Pex (owl) and Von (cat) are shipped, catalogued, selectable, and served as
pet spritesheets. Their existing reviewed atlas pixels are unchanged. Current
structural evidence and release manifest bind the two pets; original eight-pet
review archives remain historical provenance, not a current eight-pet claim.

The picker has two larger previews and a Selected label. Custom generation,
imports, duplicate custom roster and their background polling were removed from
the desktop. Import POST rejects with 409. Hatch POST rejects with
`hatch_disabled_for_mvp` before provider resolution, job creation or background
dispatch. Capability is false; authenticated historical hatch-job reads remain.
Legacy imported-pet metadata is preserved. Startup no longer scans Codex pets;
retired selections fall back to Pex without dropping appearance preferences.

The staged sidecar pet resources contain only `pex` and `von`, excluding
14,779,958 bytes of the other six spritesheets. This is uncompressed source-art
savings, not a measured RAM or final installer-size reduction.

## Verification

- Desktop tests: 279 passed, zero failures.
- Combined targeted Python tests: 113 passed in 74.51 seconds, exit 0.
  Includes pet catalog/geometry, preserved review lineage, migration, startup
  trace and bridge roundtrip tests.
- After disabling the remaining hatch write API: hatch API plus bridge roundtrip
  tests, 19 passed in 27.71 seconds, exit 0.
- TypeScript/Vite production build: exit 0.
- `npm run validate:pets`: exit 0, exact IDs `["pex", "von"]`.
- Tauri release build: exit 0; MSI and NSIS both produced.
- `npm run verify:package -- --receipt .../build/pex-package-receipt-4de1db8.json`:
  exit 0 after explicitly adding the pinned Rust 1.97.1 toolchain to PATH.
  Both embedded executable inventories and the two-pet runtime inventory passed.

Retained nonpassing attempts: the first Python run had two obsolete eight-pet
or Ledger-selection expectations (110 passed, two failed); corrected expectations
and new rejection tests passed afterward. Initial desktop source-wiring tests
still expected removed hatch polling/controls; replaced with absence checks while
retaining legacy helper contract tests. An initial verifier invocation stopped at
`rust_toolchain_unavailable` before inspecting installers; rerunning with the
pinned PATH passed. No failure was reclassified as a passing observation.

## Artifact bindings

| Artifact | SHA-256 |
| --- | --- |
| `build/pex-package-receipt-4de1db8.json` | `440d01de07cdd340ab6ae8c7606041b73b93b0747ad7b46ab724bb6ceb71932e` |
| Canonical desktop | `ddb111af9dc94f948b59d0781158ff51610b3eac1f096092152d4ade244fed7c` |
| Bundled bridge | `37dd55982ecc278939ecd4a882fc2018faff8578e2ef98114ae6b4e6c3fe8fe2` |
| MSI | `1199b34c7dbe31a8732b9f3529850859a88ff98b40d9d26bba6193d27625a491` |
| NSIS | `9f264d41a5220dc662e7599775ba1878edd7df5f316e2b0fe7e1461cc987349c` |

Both installer signatures remain `NotSigned`. No fresh-user installation or
public release was performed. Receipt `release_ready:true` is the integrity
gate's result, not proof that all product/submission requirements are fulfilled.

## Native verification boundary and next work

The older PEX build was closed normally using its own Close button. Its desktop
and bridge processes exited. At 13:59 Africa/Lagos, the computer-use tool rejected
the new launch because the user pressed physical Escape. No PEX desktop/bridge
process was present in the immediate read-only check. **No new-package native
startup, appearance, two-pet switching, or dismissal pass is claimed.**

The user subsequently asked to use the computer. Keep mouse/keyboard control,
PEX launching, isolated startup execution and heavy builds paused until suitable
renewed permission; lightweight source review/documentation can continue.

The earlier first-start timeout remains unresolved. New package includes local
fixed-phase startup diagnostics, not a timeout fix. Once resumed, first inspect
current process identity, then check first startup and trace phases, both pets,
independent bubble/pet dismissal and restored visibility. Do not weaken bridge
identity checks, extend deadlines to conceal a stall, alter security settings,
or terminate unrelated applications.

No provider calls, worker benchmark runs, AWS deployment or model regeneration
were performed during this two-pet pass. Existing live recovery/quiet evidence
retains its original source/artifact scope; the incomplete tenth live case and
provider rate limit are not cleared by these package tests.
