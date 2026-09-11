# Final two-pet source and package audit

Audit checkout: `8cf2ae7` (clean, equal to `origin/main`). Product source in the
current verified installer remains `c3cc44c`; later commits through this audit
are documentation-only.

## Exact assets

The shipping fleet remains exactly Pex and Von. Both source manifests declare
`spriteVersionNumber: 2` and `spritesheetPath: "spritesheet.webp"`.

| Pet | Source spritesheet SHA-256 | Release-manifest binding |
| --- | --- | --- |
| Pex | `ce9a714836353c752a5c1bb794a639f03755e39751ab106b8a2a8c1730c6f1a3` | exact match |
| Von | `ae1d4517c1c172dcf135ed107201daee5ee3bb12e2132fee303df1da7d6a830e` | exact match |

Both hashes occur in `build/pex-package-receipt-c3cc44c.json`, binding the
audited source atlases to the current installer candidate.

## Deterministic hatch-pet validation

The bundled workspace Python and the installed `hatch-pet` validator were used
against each current source atlas with `--require-v2`. Both commands exited 0.

- exact geometry: 1536 x 2288, eight columns, eleven rows
- exact cell geometry: 192 x 208
- format/mode: WebP RGBA
- sprite version: 2
- every required contract cell populated
- every unused cell transparent
- transparent RGB residue: zero pixels
- opaque chroma-key pixels: zero
- chroma fringe pixels: zero
- errors: zero; warnings: zero

Fresh contact sheets and focused direction sheets were generated under
`build/pet-final-audit-8cf2ae7/`. Parent visual review found stable identity,
transparent backgrounds, readable state families, opposite directional gaits,
and coherent clockwise look families with unmistakable cardinals. Pex reads as
a calm navy plush owl; Von reads as the intended dark-navy kitten, with laptop
work/review states. No asset regeneration was justified.

Archived independent direction-review lineage remains hash-bound by
`apps/desktop/src/pets/release-evidence/independent-reviews.json`. This audit did
not fabricate a new independent review or replace that historical record.

## Runtime presentation regression

The complete desktop contract command was rerun after the asset inspection:

```text
cd apps/desktop
npm test -- --test-name-pattern="transparent|overlay|dismiss|pet|hidden webviews"
```

Node's repository test command collected the complete desktop set: 290 tests,
289 passed, zero failed, one intentional Windows symlink-permission skip. The
passing contracts include native transparent canvas configuration, absence of
the mismatched JavaScript background setter, scale-aware fixed hide control,
separate status-message dismissal, calm overlay animation, page-visibility
timer suspension, hidden-view polling/socket cleanup, stale show/hide race
handling, and exactly two release pets.

## Honest boundary

This closes source-art structure, static visual review, package binding, and
runtime presentation contracts. It does **not** prove native WebView
transparency, live animation cadence, real click targets, foreground resource
use, or the visible BYOK/worker journey. Those remain one bounded PEX-only
acceptance pass on the exact `c3cc44c` package when the user yields the screen.

