# PEX tool-enabled managed transport candidate — WIP

**WIP: 207 offline tests pass; 25 new test fixture setup errors. No live admission.**

This separate candidate preserves reviewed text-only v1 unchanged. Its copied transport comes from checkpoint `92d550afb3374b97a6ba3fecc29514c41624712f`; that snapshot's qualification does not apply to this tool-enabled work.

`tool_protocol.py` binds immutable role/request snapshots to COMPLETE existing PEX prompts and authoritative evidence/final-output schemas. It rejects external schema references and non-exact primitive types, validates bounded tool arguments and causal history, and preserves evidence-result text exactly. Fingerprints hash full validated prompts, without truncating or changing the wire prompts. PEX code-owned tools are constructed but never executed during binding.

The new `managed_tool_chat.py` increment adds strict raw tool-response validation only after raw usage validation, exact offered-tool/schema/ID checks, final-tool isolation, complete authoritative request serialization, and forced-final catalog/choice/prompt coupling. Core transport hooks preserve the text-only path and scan complete request JSON for credential leakage. This increment is not yet qualified: lint auto-fix removed shared pytest fixture imports, causing 25 setup errors. The 205 prior tests and two new pure protocol regressions pass; lint and format checks pass. The next atomic edit repairs test fixture registration before transport validation.

No Strands bridge, provider inference or production integration exists. Public live invoke remains denied. Default provider paths and existing owner/policy/workspace/evidence/budget vetoes are unchanged. Public deployment remains blocked. Every atomic edit is checkpointed before further source changes. Tests contain only authored synthetic protocol fixtures, not private benchmark oracles.
