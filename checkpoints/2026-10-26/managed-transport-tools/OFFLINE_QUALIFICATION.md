# Offline PEX tool-enabled transport evidence

## Result and boundary

299 authored offline tests pass. The concrete candidate now supports the existing PEX planner/verifier tool protocol over an owned, nonstreaming HTTPX path and a buffered Strands bridge. It is not a generic SDK shim, permanent provider stub, inference benchmark, production integration, or live authorization. Public `ManagedChatCandidate.invoke`, `ManagedToolChatCandidate.invoke`, and `ManagedPEXModel.invoke_async/stream/structured_output` remain denied. The PEX guarded production admission and default providers were not edited.

Functional source checkpoint: `ee60f1bd58f22385a74a626471cfeaa1912ff83c` on `wip/reconstruction-checkpoints-20261026`, repository directory `checkpoints/2026-10-26/managed-transport-tools`. Subsequent changes in this evidence set are tests/documentation/manifests only. Reviewed `strands_bridge.py` SHA256: `bcbe547026a9343633d6e8292e084b51081278cd3d7ace88ed0d55402138823b`.

## Owned interfaces

- `Route(endpoint, model_id, role, limits, output_field)`: immutable, canonical trusted configuration; no arbitrary per-call endpoint/model/client/headers/body or alias fallback.
- `bind_existing_pex(request, role, invocation_id, proposal)`: copies typed request/proposal, then binds complete existing PEX prompts and authoritative Pydantic schemas to code-owned evidence tools.
- `ManagedToolChatCandidate`: one buffered raw JSON exchange, no tool execution. Raw usage validates before any executable reply. Exact required/named tool choice and argument schemas are enforced.
- `ManagedPEXModel(route, request, invocation_id, proposal)`: internally builds the protocol; no supplied tool registry/callback/client. Public entries deny before Agent construction. Private owned execution is exercised only by authored fixture subclasses using synthetic credentials and HTTPX MockTransport.
- Private bridge execution owns the committed transcript, correlates every tool result, enforces three calls including forced-final, and becomes terminal on errors/cancellation/early close. Receipts remain available even when consumption stops before emitted metadata.

No caller/environment/provenance flag promotes this candidate into guarded PEX admission.

## Installed primary-source contracts

Exact versions and file hashes are in `DEPENDENCY_SOURCE_MANIFEST.json`.

- `strands/models/model.py`: `Model.stream` protocol and heuristic token-estimation default. This candidate does not claim tokenizer accuracy and overrides token estimation with refusal.
- `strands/agent/agent.py:474-492`: explicit `retry_strategy=None` creates `ModelRetryStrategy(max_attempts=1)`, not the default six attempts.
- `strands/agent/conversation_manager/null_conversation_manager.py`: `NullConversationManager.reduce_context` re-raises overflow rather than retrying with compressed context.
- `strands/event_loop/streaming.py`: assistant blank-text normalization, sequential tool block assembly, and parser fallback on malformed argument text. Candidate validates complete raw JSON before yielding any block and omits whitespace-only tool preambles.
- `strands/tools/registry.py:196-227`, `strands/tools/tools.py`: registry normalizes presentation copies (including empty required arrays/property descriptions). Candidate accepts only immutable exact original or pinned-normalized presentations; the authoritative PEX schemas sent on the wire remain unchanged.
- `strands/event_loop/event_loop.py:250-282,873` and `strands/tools/executors/_executor.py:155-165`: framework runtime metadata and compatibility fields. Candidate binds these to its own Agent/model/messages/current trace/cycle IDs and never transmits them as HTTP parameters.
- `strands/tools/structured_output/_structured_output_context.py` and `structured_output_tool.py`: forced-final prompt/tool mode and Pydantic structured output. Exact final tool is alone and terminal, and strict raw primitive/schema validation precedes the SDK's coercive output tool.
- Guarded PEX `loop.py`: authoritative `SupervisorDecision`/`IndependentVerifierDecision`, full prompts, request formatting and three-turn limits. `evidence_observations.py` records hashes of exact returned text; `evidence_tools.py` owns tools and selection. Complete prompts are loaded, never shortened.

Direct HTTPX deliberately avoids OpenAI SDK execution: earlier isolated SDK research reproduced raw-usage coercion, ambient header override and independent workload-auth retry concerns. This candidate makes no claim those SDK behaviors were fixed globally.

## Test accounting

-149 base raw transport regressions.
-56 source-bound PEX contract/schema/serializer tests.
-37 raw tool-response transport tests.
-57 buffered Strands bridge tests.
- Total299; test transcript is `pytest-offline.txt`.

Coverage includes exact model/route/body/header identity, environment override refusal/canonicalization, zero retries/redirects, response bounds/compression refusal, raw bool/string/fraction/negative/missing/aggregate/cache usage inconsistencies, one-attempt401/429/5xx/timeouts and uncertain receipts, external schema reference refusal, exact primitive types, tool IDs/arguments/choice, escaped current-credential echoes in known embedded JSON, full prompt identity, real bound PEX evidence observations, parallel result reordering, typed planner/verifier finals, forced-final accounting, terminal causal history, cancellation and early consumer close.

The transport tests use only synthetic credentials and internal MockTransport substitution, never a public custom-client parameter. Socket/DNS sentries assert zero attempts even if an exception could otherwise be swallowed. The isolated public-denial telemetry regression uses a fresh process with its own in-memory exporter, a minimal child environment and socket/DNS sentries; it does not modify application-global tracing configuration.

## Independent review and repaired findings

Independent review reproduced and drove fixes for required/named tool-choice enforcement and escaped credential echoes inside embedded tool-argument/evidence JSON. It independently reran242 tests after those fixes.

The first buffered bridge was deliberately checkpointed as broken WIP:267 passes/14 failures. Independent review additionally reproduced public high-level invoke emitting three in-memory telemetry spans before denial, and a public Agent factory allowing injected assistant toolUse to execute one evidence tool with zero transport receipts. Both public boundaries were repaired: public invoke now denies immediately and the Agent factory is private.

Independent review of the exact repaired functional snapshot reran292 tests successfully, then verified zero spans and zero tool executions at all public entries using an in-memory exporter. Six additional real-Strands MockTransport probes covered both roles with tools→plain→forced-final, tools→tools→final, and tools→tools→plain; each had exactly three dispatches, the last sequence ended without structured output, and none made a fourth. These seven independent probes are now included as reproducible authored tests in the299 suite. The latest test-only addition had not yet received an independent full rerun when this report was written. No source edits or network attempts were made by the reviewer.

## Remaining gates before a real benchmark

1. Isolate/qualify framework telemetry for the private Agent execution path without mutating global environment/tracing in a multithreaded application. Public denial is fixed; ambient private execution is NOT qualified.
2. Integrate only after separate review of existing owner/policy/workspace/evidence vetoes, durable invocation reservations and receipts, ambiguous-dispatch accounting, cancellation/resume identity and finite supervisor budgets. This candidate's receipts are in-memory only.
3. Verify exact trusted provider route/model/schema compatibility and current credential/transmission authorization, then use one bounded live qualification call before any benchmark. There are no real provider credentials or inference results here.
4. Keep benchmark quality/effectiveness separate from protocol fixture success. Static pricing/byte caps do not prove hard money/token guarantees. Buffered event timing is not native TTFT/SSE.
5. Historical web authentication hardening remains outside this work; public deployment is still blocked.

## Reproduction

Use the pinned optional bridge/test dependencies and the exact guarded PEX source revision hashed in the dependency manifest. From this candidate directory, set `PEX_REQUIRE_PROTOCOL_TESTS=1` and add guarded `services/supervisor/src` and `packages/protocol/src` to `PYTHONPATH`, then run `python -m pytest -q --tb=short`. Without that source-bound environment some PEX tests skip; skipped tests are not equivalent to the299-pass qualification. Run `ruff check .` and `ruff format --check .` separately.

The artifact allowlist contains only source, authored protocol tests, manifests and sanitized evidence. It excludes virtual environments, caches, credentials, runtime databases, raw response/header captures, screenshots and private benchmark tasks/oracles.
