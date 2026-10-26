# PEX tool-enabled managed transport candidate — WIP

**WIP strict contract/serializer: 205 offline tests pass. No live admission.**

This separate candidate preserves the reviewed text-only v1 unchanged. Its copied transport and original tests come from checkpoint `92d550afb3374b97a6ba3fecc29514c41624712f`; that snapshot's 149-test qualification does not apply to this new tool-enabled work.

The contract increment adds `tool_protocol.py`: immutable role/request binding to COMPLETE existing PEX prompts and authoritative evidence/final-output schemas; exact primitive schema validation with external references refused; immutable bounded call/history types; exact evidence-result text serialization and tool-ID correlation. PEX code-owned tools are constructed but never executed during binding. No custom registry/client/transport/provider parameters are accepted by the PEX binder.

No tool-capable HTTP response path, Strands bridge, model call or production integration exists in this increment. Public live invoke remains denied. Next increments are offline serializer tests, then buffered bridge and actual PEX/Strands synthetic protocol tests. Every edit is checkpointed before further source changes.

The authored goal fixture now matches session goal/project identity without weakening PEX validation. The 149 base transport regressions and 56 source-bound PEX protocol tests pass (205 total), with lint/format checks passing. Full request/proposal snapshots, exact initial prompts, terminal-final history and strict primitive/typed-message checks are tested. No tool-response transport or Strands bridge exists yet; this is not production qualification.
