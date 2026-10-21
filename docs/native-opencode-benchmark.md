# Native OpenCode benchmark integration (not yet admitted)

Status: offline implemented and synthetic-tested component; no live inference,
no genuine paired result, no deployment or publication. The existing relay
executor and its admission/provenance rules are unchanged. `admit_native_attempt`
refuses execution, rather than silently granting host networking or reusing a
relay provenance label. Normal native V1 and V2 probes previously returned 403;
this change does not retry or work around that denial.

## Version and evidence

Supported component pin: OpenCode **1.19.3**, Linux x64 binary SHA-256
`179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9`.
The installed binary returned `1.19.3` in a fresh secret-free temporary HOME.
The only admitted model string at the component level is
`opencode/deepseek-v4.1-flash-free`. There is no `controlled/` provider, custom
provider implementation, replacement endpoint, header override or paid fallback.
Both main and small model configuration use this same reference. The unsuffixed
name does **not** verify a provider-side 1017 snapshot. V2 2.1.2 is intentionally
rejected rather than treated as schema-compatible.

Version-tagged upstream evidence:

- [CLI invocation and JSON emission](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/cli/cmd/run.ts): `run --format json --model provider/model`, same-session `--session`; local in-process server when no attach target is supplied; terminal text/tool/step events.
- [SDK/session event schemas](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/schema/src/v1/session.ts): step start/finish, text/reasoning, terminal tool parts, per-step cost and token fields.
- [V1 shell naming](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/tool/shell/id.ts): the V1 tool and permission key remains `bash`.

## Component contract and remaining limits

`benchmarks/opencode_native.py` provides native configuration, binary identity
checking, strict JSONL parsing, a same-session review/resume component and an
explicitly unavailable controller admission entry point. The session component
uses the same absolute monotonic deadline for initial turn, review and repairs.
Fresh state and log directories are separate from the candidate directory. All
subprocess environment values are explicitly constructed, not inherited.

The current settings are only suitable **inside an independently owned worker
boundary**. They allow native coding tools. They are NOT the host-plugin design
below and must never be used outside a boundary as an isolation substitute.
Configuration alone cannot prevent malicious generated code from changing local
configuration, accessing state or escaping into a host process. In particular,
these settings do not certify an effective config or make raw workspace inputs
trusted. The existing network-isolated relay sandbox cannot execute the native
provider transport. No wrapper here claims otherwise.

The parser is deliberately narrower than the upstream general-purpose schema:
unknown fields/types, unknown finish reasons, missing counters, non-finite or
negative accounting, duplicate parts, duplicate JSON keys, cross-session data,
unmatched steps, partial stops and nonterminal tool states are rejected. Tool
attachments are not currently supported and fail closed. A real successful
native transcript still needs compatibility qualification; synthetic tests do
not establish that qualification.

Every receipt says `native_cli_worker_reported_not_provider_wire` and leaves
`provider_model_verified` and `quality_measured` false. Per-step counters are
preserved without inventing totals or adding potentially overlapping categories.
Even an explicit zero in OpenCode output may come from upstream defaulting, so
this is **OpenCode-reported accounting**, not proof that provider usage was
present. CLI output lacks authenticated provider/model response identity.
Independent hidden-test grading and provider-side attribution remain separate.

The native CLI does not expose this runner's relay-enforced hard request/token
budgets. `agent.build.steps` is a per-invocation configuration, not a trustworthy
aggregate hard call cap across repairs, retries, titles or compaction. A native
protocol must declare shared wall-clock budget plus separately established
call/token accounting/enforcement; do not pretend old relay budget identity is
preserved by simply reusing the old run plan. Both arms must share pinned binary,
model reference, task seed, tool definitions, initial workspace manifest,
configuration, deadline policy, per-turn limits and condition-independent grading.
Follow-up count is an explicit treatment-specific capacity, not a reset deadline.
The native protocol needs a new run ID and must not pool native accounting with
relay-wire rows.

## Alternative under review: trusted native client, sandbox-backed tools

This is a proposal, not an implemented or qualified boundary. It can preserve
native provider transport without exposing the worker's shell to host networking:

1. Run the pinned trusted OpenCode client from a fresh control-only directory,
   with separate clean HOME/XDG roots. Never use the task checkout as cwd, a
   parent, a config directory or a plugin search path. Never pass task files via
   host-side attachments or commands. Keep the evaluator, credentials, supervisor
   internals and controller plan outside all candidate mounts.
2. Set `OPENCODE_DISABLE_PROJECT_CONFIG=1`. The tagged config loader and paths
   module honor it for project JSON and `.opencode` discovery, but still include
   global and home directories. Those directories must contain only measured,
   controller-owned files and the explicitly reviewed plugin. An environment
   flag alone is insufficient.
3. Deny all built-ins and permit only unique `sandbox_*` custom tools. The
   reviewed plugin's `tool.execute.before` allowlist must reject any other tool;
   custom tool functions must independently enforce their own scope and use
   validated arguments. Do not rely on model-visible schemas or permission
   filtering alone. Avoid built-in overrides/naming collisions.
4. Each custom read/write/search/test action must enter the existing
   `linux_sandbox.worker_command` boundary with `--unshare-all`. No arbitrary
   user-controlled command executes through a host shell. Fixed sandbox process
   argument vectors may carry bounded data; any actual shell runs only inside
   the sandbox. Task paths never select host paths. Bound output, runtime,
   process count and file resources; kill the full boundary before grading.
5. No auth/provider/chat-header plugin hooks. Supported native provider selection
   remains unchanged. No promise that this resolves the free-tier 403.
6. Include only public task/tool observations in PEX IPC. Independent grader
   keeps its separate mounts; PEX cannot see hidden tests. Both conditions use
   exactly the same plugin/tool profile and native client, with only supervision
   differing. Record plugin, launcher, config and runtime digests.

Evidence and cautions:

- [Plugin API](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/plugin/src/index.ts) supports custom tools and before-execution hooks. Plugins also have powerful host APIs; loading unreviewed plugin code would invalidate the boundary.
- [Tool registry](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/tool/registry.ts) executes plugin functions in-process and discovers JS/TS from config directories, including symlink-aware scanning. Permission settings do not sandbox those imports.
- [Config paths](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/config/paths.ts) and [config loader](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/config/config.ts) establish project-disable behavior and remaining home/global sources.
- [Instruction discovery](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/session/instruction.ts) separately reads instruction files. Neutral cwd and clean homes are necessary even when project config is disabled.
- [Prompt implementation](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/session/prompt.ts) includes subtask, shell and command paths. The reviewed host must expose only the intended plain prompt/resume entry point, not an unauthenticated shared server or arbitrary command endpoint.

Required adversarial qualification, without provider calls: task-generated
`.opencode` plugins/tools/configs, AGENTS/CLAUDE instructions, LSP/formatters/MCP,
package hooks, git hooks, shell/subagent/command escape, malicious tool names,
path traversal, symlink/hardlink swaps, output flooding, cancellation and surviving
children, session resume config drift, tool errors, and attempts to read the
hidden checker/controller files or reach the network. Audit all host filesystem
reads and process spawns in the pinned runtime, not just success of intended tool
calls. A hook exception and a deny map are defense in depth, not sufficient proof.

## Secret-free GitHub Actions qualification proposal

[GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
documents standard public-repository runners as free, fresh VMs (except the
single-CPU container runner). A standard `ubuntu-24.04` review-branch job is a
reasonable place to attempt offline namespace/runtime qualification; it is not
proof bubblewrap/user namespaces are enabled on the actual image.

Before publication or dispatch, verify repository visibility, applicable included
compute and Actions permissions. Use no secrets, OIDC, provider keys, paid/larger
runner, package publication, release environment or deployment. Set minimal
permissions (`contents: read` only if needed), disable persisted checkout
credentials, pin actions by commit, use the exact reviewed commit and explicit
manual trigger. The runner's automatically issued token and artifact transport
are still trust inputs, not model-accessible secrets. Keep them out of every
sandbox and child environment. Capture image/bwrap/kernel/runtime hashes and
actual confinement probes. Stop on missing bwrap or namespace denial; do not
change sysctls, AppArmor, setuid bits or privilege settings to make it pass.

An offline job can qualify process/mount/network isolation and deterministic
fixtures. It cannot establish provider access, model performance or availability
of a real PEX supervisor. No workflow was added, published or dispatched by this
change. No live provider request should be embedded in an offline qualification
job, especially while access remains denied.

## Independent deny-precedence audit

The proposed host-client boundary remains unqualified even with a controller-owned
base deny map. Tagged-source review established these additional acceptance gates:

- [Permission evaluator](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/permission/index.ts): evaluation uses the last matching rule, merge concatenates arrays, and config conversion preserves entry order. This is not deny-wins policy. The controller must inspect the final ordered rules, not simply verify that a wildcard deny exists.
- [Agent construction](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/agent/agent.ts): per-agent permission overrides follow global rules. An external-directory allow for the truncation-output glob is appended unless that exact glob already has an explicit deny. Audit this exception explicitly rather than claiming all paths remain denied.
- [Session tools](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/session/tools.ts): permission checks merge session permissions after agent permissions. Fresh-session admission and every resume need effective-session-policy verification; a global config hash alone is insufficient.
- [Config initialization](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/config/config.ts): directory dependency installation and discovery occur before inline config is merged. Account-organization and managed configuration can merge afterward. Clean immutable discovery roots, dependency provenance, final effective configuration and absence of unexpected override sources need separate checks. A deny map does not prevent these startup effects.
- [Tool registry](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/tool/registry.ts): discovered custom-tool modules are dynamically imported during registry construction. Denying invocation does not prevent import-time code execution. No task-controlled discovery root may reach the host registry.

The native component now rejects prior-turn message/part identities during resume,
checks binary identity before and after each invocation, and rejects executable
paths under writable task/state/log roots. These checks detect replay and drift;
they do not replace immutable mounts or establish a race-free host boundary.

No phantom built-in tools, misleading tool declarations, authentication hooks or
transport changes may be added to bypass the free-tier access denial. Containment
qualification and provider-recognized native-client compatibility are independent
requirements. The accepted unsuffixed DeepSeek model name is not a blocker; exact
requested identity is pinned and independent returned-model provenance remains
unverified.
