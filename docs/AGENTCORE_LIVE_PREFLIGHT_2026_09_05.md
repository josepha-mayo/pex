# AgentCore live prerequisites — 5 September 2026, ~20:01 UTC

This is fresh read-only account/local evidence, not a deployment or model-call receipt. Accepted application source remains `fe34a3a12087aed23a3fd89a1806e0c122e2fc04`; preceding documentation checkpoint is `d98067d251f1fde8235234420b4902d0e2723e6d`. Goal ACTIVE; release NO-GO.

## Later authorization and target-validation repair

The user approved the proposed setup **only if it does not bill their card**. This is conditional approval, not an unconditional USD 10 spend authorization. Read-only inspection of their existing Brave credits page found a general credit whose applicable-services list includes Bedrock, AgentCore, ECR, S3 and CloudWatch. A separate competition-labeled credit is not assumed available for PEX. Private amounts, credit IDs and account identifiers are not retained here. Billing Home says cost data is still being prepared; Console Home's plan-duration field could not load. A hard no-charge account plan was not established. No billing setting, credential, cloud resource or model invocation was changed.

[AWS plan documentation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html) distinguishes the no-charge Free plan from the Paid plan, which can bill usage beyond credits or ineligible services. Service eligibility and estimated credit balance alone do not satisfy the user's no-card-charge condition. Cloud creation/invocation stays paused unless that condition can be established or the user explicitly changes it; do not repeatedly request blanket spending approval.

Sol-low's bounded read-only audit found that invocation target validation omitted region/qualifier checks. Main independently confirmed the bridge's Settings normalization and client target validation, reproduced **5 false-positive cases / 4 valid controls**, and repaired the preflight without invoking AWS. The first test-development run failed because its fixture omitted required `require_auth`; that was corrected before the five product defects were reproduced. New tests compare preflight results against real Settings/client construction with an injected dummy client, while tool availability is mocked. Invalid/mismatched/oversized regions and invalid/empty/oversized endpoint qualifiers now add sanitized invocation blockers; default and normalized valid targets remain accepted. Target values and ARN are not added to the report. Final main gate: **91 passed in 2.45s** across complete preflight/client files, scoped Ruff and whitespace clean. This is not live inference evidence.

Two independently identified preflight limitations remain explicit, not silently certified: `invokable` still inherits deployment-only tool/image checks although SDK invocation of an existing runtime does not need them; `deployable` is a local-tool prerequisite label and does not verify an AgentCore project/config or successful dry-run. Do not use either flag as cloud readiness or billing safety proof. README now discloses those limits. No extra Docker infrastructure was added. The existing-worker endpoint and actual Strands loop remain the core unfinished milestone.

Independent post-repair Sol-low review passed the bounded changed scope and reran **16 preflight tests in 1.40s**. That overlaps the main 91-case gate and is not additional distinct coverage. Main retains responsibility for integration and scoped push; the unowned supervisor `loop.py` remains excluded.

## Browser and existing resources

- The user's existing Personal Brave profile is now connected through the browser extension. No new browser/profile, restart, cookie transfer or native computer input was used. This supersedes the earlier failed auto-connect prerequisite. Native Computer Use remains paused after physical Escape; do not conflate it with browser-extension access.
- The selected AWS Console is signed in under the account the user directed us to use. Account identifiers and unrelated browser tabs are intentionally omitted from this public repository receipt.
- AgentCore Runtime loaded successfully in **us-east-1** and **eu-north-1**. Each displayed **Runtime resources (0)** and **No agents found**, with no search filter entered. This is limited to these two regions at this check, not an account-wide assertion.
- Stockholm was inspected because the repository preflight identifies `eu-north-1` as its preferred region. Navigating there does not authorize deployment or establish model access. No runtime, capacity provider, role, bucket or image was created; no playground/model invocation occurred.

## Local preflight

Command from repository root: `.venv/Scripts/python.exe deploy/agentcore/preflight.py`. Report timestamp `2026-09-05T20:01:14.557111+00:00`. The shell reported nonzero status; the script printed complete JSON with `deployable: false` and `invokable: false`.

| Check | Observed result |
| --- | --- |
| AWS CLI | Installed; preflight STS authentication check false |
| Node | v24.19.0 |
| Current AgentCore CLI / AWS CDK | Not found |
| Docker | CLI found; engine unavailable to preflight |
| ARM64 builder / local image | Not verified; `pex-supervisor:agentcore-arm64` unavailable |
| Secret-safe `.dockerignore` | Passed |
| Runtime ARN | Not configured |

Browser login is not CLI authentication. Failed STS is not proof that no credentials exist anywhere. Docker's failed check does not authorize starting/reconfiguring the user's engine. No credentials or raw STS output were retained. No new backend/frontend test gate was run for this documentation-only update; the accepted source gates remain in `CODEX_CLAIMED_DISPATCH_REVIEW.md`.

## Published article

The existing Brave article tab rendered **Published Sep 5, 2026**, the intended title/author and final short content, including the explicit unverified-cloud/live-loop limitation and AI-assistance disclosure:

[Agents for Humans: Teaching PEX When to Stay Quiet](https://builder.aws.com/content/3IuxELaimn2aM3bayFznibEnnhK/agents-for-humans-teaching-pex-when-to-stay-quiet).

No publish, edit, like or comment was performed. An independent unauthenticated web fetch was refused by the web tool before page retrieval, so logged-out availability/moderation clearance is **not** independently established. No bonus award is claimed. Do not repost; the other two articles remain local drafts.

## Exact next steps and authority

1. Obtain the remaining explicit deployment region and spending cap. The user identified the signed-in account, but did not approve either. Proposed scope is one PEX AgentCore microVM runtime plus required supporting resources and a small bounded Strands/Bedrock smoke test, not Instances/EC2 or broad experiments. A spending cap is an operational stop condition, not a guaranteed AWS billing hard limit.
2. With appropriate authority, establish supported CLI authentication without exporting browser tokens; prepare the current CLI/toolchain and inspect its deployment dry-run before any cloud writes. Confirm actual model/inference-profile availability and pricing first. Do not enable automatic paid fallback or claim current source configuration proves access.
3. Resolve the existing Codex worker's supported shared endpoint and protected executable path separately. Do not weaken the AppData ancestry ACL checks, restart the user's worker, or substitute a new worker without explicit direction.
4. Prove the actual same-worker Strands NOOP, justified correction, observed useful outcome and ten quiet cases, then the actual AgentCore path. Continue the full shipping checklist, including UI, normal release, eight pets and fair visible comparisons. Local fixtures do not complete these gates.

Latest user cost preference supersedes older handoff entries: any **new** subagent must use `gpt-5.6-sol`, **low** reasoning (their “sol light”), with a bounded self-contained assignment and `fork_turns="none"`. No new subagents were needed for this read-only checkpoint. Do not rerun broad accepted suites without a changed-code reason.
