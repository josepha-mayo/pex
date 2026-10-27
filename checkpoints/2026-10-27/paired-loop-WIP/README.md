# PEX paired live-pilot integration — WIP, no paired score yet

## Fresh verified outcomes (2026-10-27)

28 authored/local tests pass on the code checkpoint `74559a70` (10.33 seconds):
7 paired-controller/full PEX planner-verifier tests; 8 private MCP tests;
2 actual-CLI free-key fail-closed tests; 1 actual-CLI remote worker test;
10 preserved CLI receipt tests against the new optional-step-compatible reader.

The actual OpenCode 2.1.4 binary dispatched a remote MCP tool, consumed its
response, and reached a SQLite-verified natural stop using authored HTTP replies.
The complete CLI worker adapter used only four remote tools; the controller
executed no candidate code. An authored forbidden local-shell call was rejected
`LOCAL_TOOL_DENIED`, and its host marker was absent. These are compatibility and
orchestration checks, NOT real inference or demonstrated PEX effectiveness.

The full PEX prompts, typed planner and independent verifier are used. Request-
bound evidence references and goal boundaries must validate before any model-
authored same-session continuation. There are no canned correction prompts.

## Real provider readiness, separately classified

Two individually authorized no-tools actual-CLI readiness attempts used the
pinned `opencode/deepseek-v4.1-flash-free` model, max output 32 and no retries.
1. Direct-DNS attempt: `EAI_AGAIN opencode.ai`, no HTTP response, 1.159 seconds.
2. After restoring the ordinary platform proxy environment: HTTP 429,
   `provider.free-limit`, 6.878 seconds. The provider reported free usage limit
   reached. No model output or usage/billing evidence was returned.

No successful real worker inference, paired benchmark, PEX lift, live sandbox
transaction, browser UI verification, or video-ready successful demo is claimed.
No E2B worker VM or Nebius inference was started by this lane. The free quota
blocker must be resolved within the user's free-only worker constraint; there is
no paid model, subscription, direct-API spoof or alternate-provider fallback.

## Pilot entry and limits

`pilot.py` is a separate explicit private-go entry, default closed. The existing
production live-denial entry is unchanged. It requires an independently supplied
private configuration SHA, pinned source/key identities and current approval.
Root owns final dispatch; simply importing or constructing a model does not run
it. The runtime is not yet qualified by a real end-to-end pilot.

- Same fixed task `05_uncertain_commit`, same prompt/public bytes and CLI identity.
- 12 free worker requests per arm; max output 4096/request; 180 seconds active CLI
  time each. Actual input usage is measured, not falsely asserted equal/capped.
- Supervisor time and receipts are separate. One shared supervisor ledger has
  $0.25 existing-credit ceiling, 12 attempts, conservative pre-call reservations,
  and actual validated usage settlement. No retries or role-specific duplicate budgets.
- Lazy independent VMs, max two, 330 seconds each, no extension/replacement.
- Each arm's MCP access is revoked before its isolated-VM grade. The baseline
  result stays private and cannot tune the second arm; paired results are emitted
  only after both arms terminate. Both configurations/evaluator are frozen first.
- Same-VM grading is explicitly anti-tamper-limited, NOT the old bwrap guarantee:
  candidate code can inspect its grading process; escaped descendants and default
  sudo remain limitations. Candidate imports never execute on the controller.
- Infrastructure errors, request/output exhaustion, timeout or incomplete grading
  are inconclusive, not manufactured task failures.

## Credential and execution boundaries

The CLI and its SQLite records stay on the trusted controller. Only the private
MCP relay forwards run/read/write/list to the selected E2B worker. Code Mode and
local/delegation/browser tools are withheld and denied. The relay is loopback-only
with a private 0600 descriptor and ephemeral local nonce (Unix sockets are not
available in this execution profile). No provider credentials enter the VM.

The provider configuration contains an inert dummy token. The trusted request
hook injects the real key only after exact free route/model/kind/tool/output and
persistent attempt-reservation checks. Actual-CLI tests prove a disabled plugin
sends only the dummy token, never the synthetic secret. Standard platform proxy
variables are preserved privately; loopback bypass remains explicit. Secrets,
raw runtime databases, request bodies, screenshots and private artifacts are not
included in this source checkpoint.

Redacted runtime recording events contain timestamps, phase/model labels,
counts and terminal status only. Raw provider/CLI artifacts remain private.
Root retains credential revocation and independent sandbox-cleanup ownership.
