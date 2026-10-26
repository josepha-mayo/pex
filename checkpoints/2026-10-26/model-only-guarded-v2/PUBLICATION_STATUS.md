# Guarded model-only v2 — reconstruction checkpoint

This is a selected delta plus source-bound verification aids, NOT a self-contained app, missing full V14 recovery, public deployment or live-BYOK qualification. Production model-only admission remains technically deny-all.

The 15 changed application/test/document files preserved at source checkpoint 5aad2abcb6b25c10b8ed83438fc3ac95c1951e79 are unchanged. SOURCE_MANIFEST.json describes that original delta. FINAL_EVIDENCE_MANIFEST.json separately describes the nine final public report/audit/reproduction files added under source/. The historical base and Inspector routing restoration are still required; do not overlay this blindly onto main.

## Final bounded evidence

- 67 focused tests passed with zero network attempts; independently repeated by reviewer and parent.
- Expanded pytest assertions: 556 passed and 3 skipped. The strict process-wide audit intentionally exits 1 because it blocks 10 legacy default-mode teardown DNS attempts to loopback ports 11434/1234. No socket connect or provider inference occurred. This is NOT an all-tests zero-attempt success.
- Exact skip IDs, effective dependency versions, SDK-observed-versus-raw-wire usage limits and uncertain reservation behavior are in source/model-only-verification/PUBLIC_QUALIFICATION.json and NETWORK_AUDIT.json.
- Runtime, auth/origin/session hardening, managed live transport, raw-wire billing, remote evidence and deployment remain unqualified. No new live inference or benchmark is claimed.
- Raw private test logs, environment bytes, private path inventories, browser state, credentials, screenshots and private oracles are excluded.

No merge, release, deployment or extra resource job is authorized by this source checkpoint.
