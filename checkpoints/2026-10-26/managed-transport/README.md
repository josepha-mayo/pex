# PEX managed Chat Completions transport candidate

**Standalone local candidate. 149 offline tests passed. Public live dispatch is denied.**

This is concrete transport implementation, not a new production admission flag. It is not integrated with PEX, its provider loader, Strands, the planner/verifier pipeline, or a public deployment. No provider credentials or inference were used. Default PEX paths and existing production refusals are unchanged.

## API

```python
from managed_chat import Invocation, Limits, ManagedChatCandidate, Route

route = Route(
    endpoint="https://managed-fixture.invalid/v1/chat/completions",
    model_id="fixture/exact-model",
    role="planner",  # or verifier: fixed trusted role prompt, not a user override
    limits=Limits(max_output_tokens=512),
)
candidate = ManagedChatCandidate(route)
result = await candidate.invoke(Invocation("opaque-invocation-1", "bounded evidence"))
assert result.receipt.reason == "live_not_authorized"
```

Public `invoke` refuses before credential resolution, DNS or client creation. It takes no key, client, transport, generic parameter dictionary, headers, extra body, or retry configuration. No environment/provenance flag opens this gate.

The implemented private `_execute_owned` path is exercised by tests only with synthetic endpoint-scoped credentials and an internal MockTransport constructor substitution. It is **not an authorized live API**. Python private members are not a sandbox against arbitrary in-process code. A later reviewed integration must bind the approved route and credential source, owner/policy/workspace/evidence vetoes, durable reservations and current live-run authorization; it must not expose this private method to untrusted callers.

## Implemented controls

- Frozen, canonical HTTPS endpoint/model/role/caps; exact configured request and response model, no aliases, redirects or endpoint fallback.
- Direct HTTPX implementation: **no OpenAI SDK execution**, thus no SDK usage coercion, ambient OpenAI headers or workload-auth retry layer. No Strands retry/overflow loop exists in this standalone path.
- Owned `AsyncHTTPTransport(retries=0, trust_env=False, verify=True, http2=False)` with one connection and no keepalive; owned AsyncClient has redirects disabled and finite total/request timeouts. Every private invocation has a one-dispatch boundary and fresh closed client.
- Exact outbound method/URL/header/body checks before dispatch, identity encoding, no caller/ambient headers. Validated globally routable unicast DNS answers are pinned while retaining original TLS SNI/Host. Private, mapped, multicast and site-local addresses are refused.
- Bounded raw response bytes before strict JSON parsing. Compressed responses are rejected **before reading/decompression**. Duplicate keys, nonfinite numbers, invalid UTF-8/Unicode and malformed counters are refused.
- Raw usage counters use exact integer types; booleans, strings, integer-valued/fractional floats, missing/negative/oversized values and inconsistent totals/cache counters fail closed. Cached input and reasoning output counts are checked against their enclosing totals; counts are never added twice. Nonzero audio, predicted-output and cache-write counters are unsupported in this narrow mode and refuse, rather than inventing cost/overlap semantics.
- Immutable sanitized per-invocation receipt: zero attempts only before dispatch; timeout/error/cancellation/status/invalid-response after dispatch is uncertain and may have incurred charges. Valid known usage remains recorded even if later content validation fails. Unknown usage remains `None`, never a fabricated zero.
- Duplicate/private concurrent invocation refusal; cancellation rethrows after retaining its safe receipt. Keys, prompts, headers, exception text and raw provider bodies are absent from receipts/logging; repr for credentials, prompts and completions is redacted.

## Intentionally limited

- **One non-streaming, buffered text-only Chat Completions call.** Tool calls, legacy function calls, refusal messages, multiple choices and non-stop finishes are rejected. There is no tool-call assembly or Strands adapter yet. No TTFT, native SSE, inference-quality or speed claim follows from these tests.
- Receipts are in-memory evidence, **not durable budget accounting**. No crash recovery, ledger reconciliation, production owner admission or automatic retries/resume is implemented. Production integration must preserve unresolved/ambiguous reservations.
- Byte limits and provider-reported token counters are not a tokenizer guarantee, provider invoice or hard money ceiling. Nonzero provider-internal work cannot be inferred solely from HTTP counts; one HTTP dispatch does not prove one internal inference.
- This does not restore missing historical web authentication or make PEX publicly deployable.

## Verification

Execution used the separate research environment, without modifying either PEX working tree:

```sh
/workspace/scratch/c62c151ada7d/managed-transport-research-20261026/.venv/bin/python -m pytest -q
```

Result: **149 passed**. DNS/socket-connect sentries count and assert zero actual attempts, including caught exceptions. Fake DNS fixtures return fixed synthetic answers without calling network resolution. Tests cover headers/environment contamination, request identity mutation, malformed usage/cache data, compressed/oversized/broken bodies, HTTP 3xx/401/429/5xx, connection/read/write failures, timeouts, cancellation, closure and uncertainty. `evidence/` contains sanitized test/lint/version results and independent review.

Runtime dependencies are pinned HTTPX 0.28.1 and httpcore 1.0.9. All actual resolved test versions are recorded. No `.venv`, secret, runtime database, provider payload, or actual header capture belongs in the compact backup.

## Next authorized implementation step

Review this source/evidence before considering any integration. A later local candidate can add a bounded typed tool-call/Strands formatter and durable reservation/receipt plumbing while keeping public live admission closed. Only a separately authorized bounded real-provider benchmark can establish live compatibility. No code or test here grants that authority.
