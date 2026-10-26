# PEX tool-enabled managed transport candidate — WIP

**WIP contract tests added: 162 pass / 43 fail. No live admission.**

This separate candidate preserves the reviewed text-only v1 unchanged. Its copied transport and original tests come from checkpoint `92d550afb3374b97a6ba3fecc29514c41624712f`; that snapshot's 149-test qualification does not apply to this new tool-enabled work.

The contract increment adds `tool_protocol.py`: immutable role/request binding to COMPLETE existing PEX prompts and authoritative evidence/final-output schemas; exact primitive schema validation with external references refused; immutable bounded call/history types; exact evidence-result text serialization and tool-ID correlation. PEX code-owned tools are constructed but never executed during binding. No custom registry/client/transport/provider parameters are accepted by the PEX binder.

No tool-capable HTTP response path, Strands bridge, model call or production integration exists in this increment. Public live invoke remains denied. Next increments are offline serializer tests, then buffered bridge and actual PEX/Strands synthetic protocol tests. Every edit is checkpointed before further source changes.

The current authored goal fixture omits matching session goal/project identity; PEX correctly refuses it before most new cases run. Repair is queued after this checkpoint. Request snapshots, full initial-prompt binding, terminal-final history refusal and strict typed-message checks have been added; this candidate is not qualified.
