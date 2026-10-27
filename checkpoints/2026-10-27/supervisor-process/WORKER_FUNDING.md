# Optional paid-worker funding — preparation only

Public `WorkerFunding` is CLOSED: `APPROVED_WORKER_REF = None`. The existing free
OpenCode route and NVIDIA supervisor ledger are unchanged. No paid inference,
credential creation, sandbox creation or activation occurred for this module.
The private `_WorkerLedger` exists for authored accounting/guard qualification;
it is not a substitute for the missing owner approval.

Proposed fixed pools: baseline worker375,000,000 nano-USD, PEX worker375,000,000,
existing shared supervisor250,000,000 = one USD total, with no cross-arm subsidy.
Worker route is exactly canonical Nebius `/v1/chat/completions`, dated model
`deepseek-ai/DeepSeek-V4.1-Flash-1017`. Each attempt reserves319,488,000 nano-USD
(1,048,576 input ×300 +4096 output ×1200), at most12attempts per arm. Actual
validated usage may settle lower; unknown/malformed/missing usage retains full
reservation. No automatic retry/refund exists. An uncertain first call normally
prevents another call in that arm. Budget exhaustion is inconclusive, not failure.

Trusted guard-only interface:
- constructor(path, arm, approved_config_digest, approval_ref, pricing_provenance_sha256)
- reserve(call_id, request_sha256, request_body_bytes)
- settle_raw(call_id, request_sha256, status, content_type, raw_response_bytes)
- summary(); close()

Both arms must use the SAME private ledger path and configuration digest. Root
must pin the exact new approval before enabling the public constructor. Remote
candidate/model code must never access the funding RPC descriptor, credential,
ledger, or settlement method. Only trusted local CLI guard reads the actual wire
response clone and sends authenticated bounded IPC. Request body admission checks
output/model/tier/completion-count/remote-tools before reservation/key injection.
Raw requests/responses are never persisted: only hashes and numeric receipts.

SSE settlement requires one exact-model stream, a terminal choice, exactly one
final usage chunk and [DONE]. Complete JSON requires exact model, one properly
typed choice, terminal finish reason and consistent usage. Reasoning tokens are
already part of completion; cached input is conservatively charged at full rate.
Internal RLock plus SQLite immediate transactions support controller IPC threads
without duplicate settlement or overspending across independent connections.

Fresh authored verification:31 focused checks passed in0.11s;405 combined
transport/process/pilot/worker-funding checks passed in4.79s. Tests include both
arms, concurrent reservation, same-instance IPC threads, reopening, attempt caps,
unknown/429/malformed/duplicate usage, request mismatch, closed public admission,
and body privacy. Two initial malformed JSON choice tests failed; strict choice
object/index checks fixed the defect before requalification. All responses are
authored, not measured provider inference/billing. No benchmark gain claimed.

Provenance: public pricing snapshot SHA256
50e7bb6a6548514fbfe49c25148234644b39a29a2f3caf5cd6b85cd6fc8f20a4,
from https://tokenfactory.nebius.com/api/public/models_info . This pricing snapshot
is not authorization. The separate $1 request remains pending at this checkpoint.


11:30 UTC actual CLI feedback: the OpenAI-compatible SDK emits
`max_completion_tokens`, not `max_tokens`. Admission now requires exactly
`max_completion_tokens=4096` (including reasoning) and rejects `max_tokens` to
avoid ambiguous dual limits. Existing free and NVIDIA paths remain untouched.
Fresh rerun on these changed bytes:31 focused passed in0.12s and405 combined
passed in4.93s. Joined actual CLI qualification is owned by the controller lane;
no live provider response or paid authorization is implied here.
