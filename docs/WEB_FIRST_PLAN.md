# PEX web-first transition

Status: local work in progress, 20 October 2026. Not deployed.

## What already works structurally

The main React app already runs in a browser. `scripts/demo.py` starts Vite
and a loopback bridge; Tauri is optional. The desktop directory name does not
mean the UI requires a desktop installation. Keep that UI and supervisor.

## First safe, installation-free increment

`docs/explore/` is a read-only browser explorer over the committed October 18
suite receipt. It derives case counts from that receipt, provides outcome and
text filters, and shows evidence plus intervention sequences. It has no
worker endpoint, credentials, model call, or workspace access. Its labels
explicitly distinguish inspection from a fresh replay or cryptographic check.
It can accompany the existing Pages site after publication is approved and
browser QA is complete. It is not the finished hosted application.

Verification:

- `node --test tests/unit/test_web_explorer.mjs`
- `node --check docs/explore/app.mjs`
- `node --check docs/explore/receipts.mjs`

## Full hosted application: gates before publication

1. Reuse the React UI, but introduce a distinct hosted replay mode with no
   operator-control affordances or credential entry. Do not pretend that
   static receipts execute the pipeline.
2. Give every visitor a separate, disposable store and sandbox. The bridge
   currently has process-global state; a shared instance would mix visitor
   goals, decisions, and session data. A per-visitor isolated service is the
   safer initial deployment boundary than patching tenant checks everywhere.
3. Allow only bundled replay fixtures initially. No arbitrary inline workspace,
   shell command, file path, network adapter, provider setting, credential
   bootstrap, or live-control endpoint on the public replay surface.
4. Authenticate the service-to-bridge hop, enforce allowed origins, and avoid
   forwarding public traffic through the Vite development origin rewrite.
   Browser mode currently returns no operator bearer. The unauthenticated
   `Settings.for_test` demo is not a production authentication design.
5. Bound concurrent runs, request size, CPU, disk, visitor lifetime and total
   spending. Clear the disposable workspace on expiration. Use no provider
   credentials for deterministic replays.
6. Test cross-visitor isolation, expired sessions, repeated requests, denied
   routes, cleanup, runtime caps, replay labels, and mobile/browser navigation.
7. For real personal workspace control, use an explicitly connected,
   authenticated local bridge. Do not make a public judge session a route
   into the owner's computer. Keep the existing packaged desktop intact.

## Remaining decisions

A public compute-backed replay app needs a confirmed hosting account and
approved resource/cost limits. No infrastructure, credentials, access grants,
paid calls, public upload or deployment were created by this change.
