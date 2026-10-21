# Unpublished native containment qualification draft

Prepared locally only. No GitHub publication, workflow dispatch, model request,
credential use, privilege escalation or security-setting change was performed.
The YAML lives outside `.github/workflows`, so committing it does not activate a
workflow. Its eventual publication and the automatic push-triggered run require explicit
review/approval together.

## Verified repository facts, 2026-10-21

The connected GitHub repository API identified `josepha-mayo/pex` (ID1346706097)
as public and not archived. The Actions runs API returned an actual successful
[Windows/Linux checks run39436861738](https://github.com/josepha-mayo/pex/actions/runs/39436861738)
for commit3d4901003b2cdff9acd1b2a997a0d0e214fc9e35. Thus Actions are demonstrably in
use; neither a future dispatch authorization nor namespace availability follows.
GitHub documents standard public Linux runners as free; the draft selects only
`ubuntu-24.04`, not a paid/larger/self-hosted runner. Recheck visibility and current
billing/runner policy before dispatch; this was not an account-billing inspection.

The checkout action SHA was resolved from the official `actions/checkout`
`v4.2.2` Git reference. The native binary/package hashes match the separately
installed official `opencode-linux-x64@1.19.3` package. Package bytes are downloaded
from the official npm registry and verified before extracting exactly one regular
file; no package lifecycle script or dependency installer runs.

## What the draft actually tests

`scripts/qualify_native_offline.py` puts the real pinned OpenCode binary inside the
existing network-unshared bwrap boundary, with runtime read-only and only a
synthetic candidate task writable. It executes `--version` and `debug config`,
never `run`, a prompt, a provider API or an inference endpoint. It checks that a
candidate's malicious project config does not override the selected model/deny
rule, then runs direct offline candidate-code probes for hidden controller-file
access, host `/proc` access, writeability, native-runtime modification, host
loopback reachability and inherited credential environment.

This is genuine runtime startup and containment testing **if executed**, but not
full native session/tool qualification. Session/API escape, resume freshness,
plugin/skill execution during startup, process-tree/resource exhaustion and
native egress remain explicit untested gates in the emitted JSON. A successful
job emits `partial_offline_qualification_passed`, never benchmark eligibility.
No live model or performance result can be inferred from it.

The draft requires an existing root-owned bwrap binary and namespaces to work.
Missing or denied support stops the job. There is no apt/sudo, sysctl/AppArmor
change, setuid modification, privileged container or host-network fallback.
Locally `/usr/bin/bwrap` is owned by `nobody`, so the existing trusted-binary guard
rejects it. We did not weaken that guard or retry native execution elsewhere.

## Host-plugin architecture rejected for activation

An early disabled custom-tool prototype was considered but is not included in
this candidate. Tagged upstream source shows:

- Plugin initialization errors can be caught and config-hook errors ignored.
- Project plugin/tool discovery and dependency installation can precede inline
  config. Managed/org configuration can merge later.
- Permission precedence is last match; agent/session overrides and automatically
  appended rules can change effective permissions after global deny rules.

Therefore deny-all settings plus a hook are not a proven host boundary. Saved
read-only source audit copies are available separately to the reviewers; upstream
links are in `docs/native-opencode-benchmark.md`. These findings do not invalidate
an actual OS-isolated native runtime, but such a runtime must contain startup
code as well as model-driven tools, with its own controlled provider egress.

A separate compatibility blocker also remains:
[#51241](https://github.com/anomalyco/opencode/issues/51241),
[#50627](https://github.com/anomalyco/opencode/issues/50627) and
[#51193](https://github.com/anomalyco/opencode/issues/51193) report free-model
rejections when read/shell permissions are denied. The
[#56324 discussion](https://github.com/anomalyco/opencode/issues/56324) links those
reports but also describes failures despite login and no deny rules. They are
first-party issue reports/triage, not a provider specification or a confirmed
explanation for our403. Do not remove protections, disguise tool identities or
make retry inference calls to test this theory. Either a genuinely isolated
native client retaining supported tools, or provider clarification/fix permitting
the restricted configuration, needs to be established before further live work.

Native wall-clock budgeting remains distinct from relay-enforced aggregate
request/token caps. Neither this offline job nor a `steps` setting establishes
aggregate inference enforcement, native model identity or independent grading.


## Feasible review-only publish/run action (still not performed)

GitHub's [official event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
requires a default-branch workflow for initial manual dispatch. The earlier
manual-only draft cannot satisfy review-only publication, so it is superseded.

After approval of the exact final diff and one offline run:

1. After publication/run approval, create the reviewed source tree on the verified
   public parent using the authorized publishing route. A connector-created
   commit can have a different SHA than the local Git commit. Read back the
   returned PUBLIC source SHA and verify every reviewed file's bytes/tree hash.
   Do not treat an unpushed local SHA as an accessible remote revision.
2. Only after that readback succeeds, replace
   `REPLACE_WITH_VERIFIED_PUBLIC_SOURCE_COMMIT_SHA` in the inert YAML with the
   actual returned source SHA. Review the activating diff and publish it ONLY on
   `review/native-offline-qualification-20261021`, copying the draft YAML to
   `.github/workflows/native-offline-qualification.yml`. The placeholder is
   intentionally unusable until authorized publication and verification.
3. That push, which changes the exact workflow path, starts the job. It does not
   need default-branch registration, a separate dispatch or a PR. Main is never
   updated. Do not publish the activating commit before both publication and its
   automatic execution are authorized. The workflow checks out the verified
   public source SHA, not a moving branch tip.
4. Stop after the one requested run; further triggering pushes or reruns need
   authority. Do not use another branch or relax trigger filters. A blocked
   publication route is not permission to call it again or switch publishers.

The existing checked-in checks workflow only triggers branch pushes on main;
other checked-in release/replay workflows are manual. No PR is created, so this
proposal does not intentionally trigger the existing PR suite or releases.
Repository rules, current Actions policy and credentials capable of publishing
workflow files still need verification at publication time. If those block the
approved action, report the blocker rather than changing main or permissions.

The native config loader starts background installation of
`@opencode-ai/plugin` even with fresh config roots. With networking unshared,
that may fail or delay startup. The script retains a90-second per-probe timeout,
reports explicit background-install failure, and labels timeouts as possibly
(but not conclusively) dependency-related. It will not install dependencies by
relaxing the namespace or silently classify unavailable startup as a pass.


## Independent review integration

The qualification runner now limits combined stdout/stderr to2MiB while reading,
uses its own process group, kills/reaps on timeout, overflow or uncertain exit,
and rejects overlapping task/runtime trees. Reports include exact qualifier,
sandbox-source and native-binary hashes plus Python/kernel runtime provenance.
These are measured local runtime facts, not provider-wire or benchmark evidence.
Ten mocked/negative-path qualification tests pass; the combined native, CLI,
session and qualification selection has76 tests. No native execution occurred in
this review. Original qualification draft had3 tests, then5 after timeout/install
diagnostics, before the independent-review additions.
