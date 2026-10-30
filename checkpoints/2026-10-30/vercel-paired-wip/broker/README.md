# PEX Vercel native file-RPC broker — OFFLINE WIP ONLY

**Not qualified for live use.** Root's qualification was blocked by provider HTTP
402 `resource_creation_blocked` (team fair-use/resource restriction). This agent
made no external-resource calls. No sandbox, session, command receipt, runtime
result, cleanup proof, billing receipt, or Vercel performance result is asserted.
`driver.js` has `LIVE_QUALIFIED=false` and throws before invoking any tool. Do not
remove the gate without an authorized, successfully qualified provider route
and independent review of real native response shapes. Do not bypass the block.

## Files and checks

- `core.mjs`: portable broker state machine. Only injected `native` can call
  providers; only injected `io.put` can publish evidence. Authored mock fixtures
  in tests are NOT observed provider formats.
- `driver.js`: functions.exec driver using global `tools`; no eval/require/SDK,
  credential extraction, or model calls. Fixed helper host command receives only
  base64 data, not candidate commands. Large outgoing payloads are chunked.
- `host_io.py`: fixed host-only bounded file IO; atomic no-overwrite publication,
  no-follow file reads, private canonical directory checks, SHA256 of exact bytes.
- `build_exec.py`: combines core + driver and injects a reviewed boot JSON. It
  emits source only and never executes or invokes a resource.
- `native-tool-contracts.json`: actual tool declaration metadata discovered from
  ALL_TOOLS, not provider receipts. No undocumented provider credential route.

Run local tests:

```
node --test broker/test_core.mjs
python3 broker/test_host_io.py
```

Result on 2026-10-30: **31 Node tests + 9 Python tests passed**, offline only.

## Controller contract

Private canonical `native-rpc` directory, requests/responses `000001.json` etc.
Request exact fields: schema=`pex.vercel.rpc-request.v1`, run_id,
config_sha256, sequence, arm (`baseline` or `pex`), operation, args, deadline_utc.
Response exact fields: schema=`pex.vercel.rpc-response.v1`, run_id,
config_sha256, sequence, request_sha256, ok, result, error,
raw_native_receipt_sha256. Request SHA is from original file bytes, not re-encoding.

Operations:

- create: exact team_id/project_id/image/persistent=false/network_policy={allow:{}}/
  vcpus=1/timeout_ms=750000. Fixed iad1, empty ports, no env/source/mounts.
  Returns `{session_id,sandbox_id}` only from native create response.
- run: `{command,cwd:'/vercel/sandbox/pex-task'}` → `{exit_code,stdout,stderr}`.
  Native `/bin/bash -c` runs ONLY in owned VM, sudo=false; start/get/logs retained.
- read: `{path}` → UTF-8 string; VM-only regular/no-follow bounded reader.
- list: `{path}` → sorted name array; VM-only bounded list.
- mkdir: `{path}` → true after native mkdir receipt.
- write_files: `{files_base64:{absolute_path:base64}}` → true. Restricted public
  tree or `/tmp/pex-wirepool-evaluation-<32hex>/...`; chunked VM Python writes,
  no-follow directory descent, regular single-link files. No archive extraction.
- stop: `{}` → `{session_id,stopped:true}` only after native stop + get status.

A run may attempt at most two creates, one per arm, sequentially after previous
stop proof. Request cannot select session IDs, credentials, sudo, env, ports,
network policy, extra operations, or resource sizes. Native IDs live only in the
broker-owned map. Native uncertain errors poison subsequent work; cleanup is
still available for known owned sessions. Every attempt is durably journaled
before dispatch. Restart with a journal refuses automatically; it is not a retry.
Unknown create must be reconciled manually by root with normal authorized tools;
a missing response is never proof that creation did not happen.

## Evidence and provisional formats

All artifact SHA256 values hash exact UTF-8 file bytes. Receipt paths:
`receipts/NNNNNN-<label>.json` (create, create-get, cmd1-start, cmd1-finish,
cmd1-logs, stop, stop-get, etc). Each native receipt wrapper has schema
`pex.vercel.native-receipt.v1`, tool, arguments, received_utc, raw. Raw is the
unmodified native tool result object. Throws have a separate finite throw record,
not a fabricated native result. `receipts/NNNNNN-bundle.json` links every receipt
SHA and request SHA; its SHA is response.raw_native_receipt_sha256.

`owned-<arm>.json` exact fields:
schema=`pex.vercel.owned-session.v1`, run_id,config_sha256,arm,sequence,
request_sha256,team_id,project_id,sandbox_id,sandbox_name,session_id,image,
persistent,network_policy,vcpus,timeout_ms,create_receipt_sha256,
get_receipt_sha256,producer_sha256.

`stopped-<arm>.json` exact fields:
schema=`pex.vercel.stop-proof.v1`, run_id,config_sha256,arm,sequence,
request_sha256,team_id,project_id,sandbox_id,session_id,stop_receipt_sha256,
get_receipt_sha256,status=`stopped`,producer_sha256.

Producer SHA is core.mjs; review/freeze **all source hashes in SHA256SUMS**, not
only core. Report/launcher proof-SHA pinning remains controller/recorder owner's
responsibility. The proof's configuration currently derives from exact actual
create TOOL ARGUMENTS, not an unobserved claim about provider-returned fields.
V12 must remain closed until actual provider receipts independently establish
identity/configuration/terminal state.

Provisional narrow adapters (NOT real response observations): MCP structuredContent
or a single JSON text content; create `{sandbox:{id,name},session:{id}}`;
get `{session:{id,status}}`; commands `{command:{id,exitCode}}`; logs
`{logs:[{stream:'stdout'|'stderr',data:string}]}`. Unsupported shape fails closed.

## Remaining live-qualification work / limitations

1. Provider block must be resolved by an authorized route, without bypass.
2. Independently review actual native response shapes; adapt parsers and tests.
3. Verify backend applies deny-all/nonpersistent/1CPU/750s and actual image.
4. Verify functions.exec host output-size and tool-latency budgets with real
   payloads. A truncated host output fails closed; it is never parsed as success.
5. Benchmark uses 3 native calls per run and 3 per write chunk. Equal budget
   accounting must include this route's latency; no runtime promise is made.
6. Driver reaching deadline is not destruction proof. Root must reconcile/stop
   remaining known sessions; server timeout is a bound, not a stop receipt.
7. Shell commands run in isolated VM but are not an OS security boundary inside
   that VM. sudo flag/explicit sudo commands are rejected; do not claim arbitrary
   code cannot indirectly invoke other VM programs. No credentials enter VM.
8. Model API costs/overall $5 admission are controller-owned; this broker bounds
   VM count/lifetime but does not fabricate metered billing proof.

Boot JSON fields: rpc_root plus config containing exactly run_id,config_sha256,
team_id,project_id,image,deadline_utc,producer_sha256. Project is existing approved
project selected by root, not an unrelated project silently reused. Boot config
is trusted owner input, not model input. Example generation (does NOT run):
`python3 broker/build_exec.py /private/boot.json /private/broker-exec.js`.
