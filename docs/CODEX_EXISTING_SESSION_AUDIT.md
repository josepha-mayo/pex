# Codex existing-session shared App Server audit

## Latest installed-runtime refresh — after `decc74b`, 5 September 2026

The original design/source snapshot below is historical. Shared observation and separately authorized claimed text delivery are now implemented and locally tested; see `CODEX_CLAIMED_DISPATCH_REVIEW.md`. Actual installed-worker supervision is still unverified.

Fresh read-only checks resolved `C:\Users\JosephMayo\AppData\Local\OpenAI\Codex\bin\27d6a192e9c98618\codex.exe`, SHA256 `A1CF6360CA71918D5466BC3A32D9F18B7044C9128756D1949E715D277B88C9B6`. Two running `codex.exe` processes were identified as App Servers (PIDs 13564 and 8188). Neither command line advertised an explicit Unix/WebSocket listener or remote client; a TCP listening-socket query returned no listener owned by either. A top-level `.codex` filename-only check found no socket/daemon/server candidate. These bounded checks do not prove no endpoint exists elsewhere. Command-line credential values and unrelated session content were not printed.

Installed `app-server --help` confirms stdio is the default and advertises Unix/WebSocket listening plus the `proxy --sock` helper. Help is not a listener launch or live protocol test. Installed `app-server daemon version`, selected as a read-only status query, failed with **daemon lifecycle is only supported on Unix platforms**. Do not try `start`, `bootstrap`, `restart`, or enable remote control as a substitute for that failed diagnostic.

Current [official App Server documentation](https://learn.chatgpt.com/docs/app-server) was searched and opened under the OpenAI Docs skill. It describes separate initialized clients connecting to a shared listener, not retroactive attachment to another client's stdio pipe. The next live step needs an actual supported user-owned shared endpoint, or explicit user approval to establish a separate visible demo session on one while preserving the current sessions. Such a demo must be labeled honestly; it would not prove attachment to the current desktop task. Do not weaken ACLs or start a substitute worker silently. No worker, proxy, listener, provider call, model invocation or cloud resource was started in this refresh.

The user's cloud approval remains conditional on **no card charges**; credit eligibility did not establish a hard no-charge protection. Keep this separate from the local worker connection prerequisite. Full goal ACTIVE, release NO-GO; the original three-spec completion bar is unchanged.

## Historical design audit

Date: 2026-09-05 (Africa/Lagos)

Status: design evidence only. No App Server, bridge, provider, model, or desktop process was started or changed for this audit. No live same-session proof has been run.

## Executive finding

PEX's current Codex attachment is not an attachment to the App Server process that owns a user's live Codex session. `CodexStdioTransport` starts another `codex app-server --listen stdio://` process. Listing or reading persisted threads through that process doesn't subscribe PEX to events produced by the user's process, and resuming through it can fail because the original process holds the active writer.

Current official documentation and upstream source support the architecture PEX actually needs: the user's Codex CLI and PEX can be separate initialized connections to one shared App Server listener. They describe a `unix://` remote endpoint, `thread/resume` subscription on that same server, and thread events routed to subscribed connection IDs. The installed binary contains matching interface markers, but its runtime behavior has not been tested here. This is a candidate path to an authoritative live event stream from a user-started CLI thread without PEX starting or replacing the harness, not an installed-version live receipt.

This does not make intervention race-safe. `turn/start` has no expected-turn or idle compare-and-swap parameter. A concurrent user request can turn an intended new PEX turn into steering of an already active turn. The first shared-connection slice must therefore remain observation-only. Mutation and permission responses must remain disabled until a separately reviewed cooperative ownership fence exists.

## Installed artifact, not inferred from upstream

The active Windows executable resolved by PowerShell is:

`C:\Users\JosephMayo\AppData\Local\OpenAI\Codex\bin\994e8469124a0d31\codex.exe`

Observed without executing it:

- size: `295530800` bytes
- last write UTC: `2026-09-02T22:54:50.6619822Z`
- SHA-256: `DACB96688B155E20DBBBC0BFD18BBA7CE7920F1B239AB08A1627917F23B8D9CD`
- PE file/product version resources: blank
- bounded printable-string search: `0.153.0`

The same hash is present at `C:\Users\JosephMayo\.codex\plugins\.plugin-appserver\codex.exe`.

The installed binary contains the relevant protocol/help markers: `thread/read`, `thread/list`, `thread/loaded/list`, `thread/resume`, `thread/start`, `thread/turns/list`, `thread/items/list`, `turn/start`, `turn/completed`, `thread/status/changed`, `thread/unsubscribe`, `canAcceptDirectInput`, `--remote`, `unix://`, `websocket`, and `already has an active writer`.

These observations establish the installed surface. They do not prove that the installed `0.153.0` implementation is byte-for-byte identical to the current `openai/codex` `main` branch. Upstream source references below were retrieved on 2026-09-05 and are behavioral corroboration; a future source revision can drift.

## Official documentation and current OpenAI source references

Official OpenAI documentation:

- Codex App Server: <https://learn.chatgpt.com/docs/app-server>
  - `codex --remote` accepts `ws://`, `wss://`, `unix://`, and `unix://PATH`.
  - Unix transport is WebSocket over the local socket using a standard HTTP Upgrade handshake.
  - every connection must send exactly one `initialize` request and then `initialized` before other requests.
  - `thread/start` automatically subscribes the connection.
  - `thread/read` reads stored state without resuming or subscribing.
  - after a thread is started or resumed, the connection receives thread, turn, and item event notifications.
  - `thread/unsubscribe` removes only the current connection's subscription.

Current OpenAI source, retrieved from `openai/codex` `main`:

- App Server protocol and proxy contract: <https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md>
- Remote App Server client: <https://github.com/openai/codex/blob/main/codex-rs/app-server-client/src/remote.rs>
  - `RemoteAppServerEndpoint::UnixSocket` is a first-class client endpoint.
  - it connects with `codex_uds::UnixStream`.
  - it performs the WebSocket HTTP Upgrade using `ws://localhost/rpc`; bytes still travel over the Unix socket.
  - it initializes the connection before starting its request/event worker.
- Unix App Server transport: <https://github.com/openai/codex/blob/main/codex-rs/app-server-transport/src/transport/unix_socket.rs>
- Cross-platform Unix transport tests: <https://github.com/openai/codex/blob/main/codex-rs/app-server-transport/src/transport/unix_socket_tests.rs>
  - Windows-specific tests exist.
  - source comments state that `uds_windows` uses a regular path as a rendezvous point on Windows rather than a POSIX socket filesystem node.
- Cross-platform UDS rationale: <https://github.com/openai/codex/blob/main/codex-rs/stdio-to-uds/README.md>
  - `codex-uds` supplies the cross-platform async API and is backed by `uds_windows` on Windows.
- Per-thread connection membership: <https://github.com/openai/codex/blob/main/codex-rs/app-server/src/thread_state.rs>
  - each thread entry owns a set of connection IDs.
  - `try_ensure_connection_subscribed` adds the initialized connection to the thread.
  - disconnect and unsubscribe remove only that connection's membership.
- Listener attachment and broadcast: <https://github.com/openai/codex/blob/main/codex-rs/app-server/src/request_processors/thread_lifecycle.rs>
  - `ensure_conversation_listener` calls `try_ensure_connection_subscribed`.
  - the listener obtains `subscribed_connection_ids` and constructs a thread-scoped outgoing sender for each translated event.
- Resume/read behavior: <https://github.com/openai/codex/blob/main/codex-rs/app-server/src/request_processors/thread_processor.rs>
- Turn start/steer behavior: <https://github.com/openai/codex/blob/main/codex-rs/app-server/src/request_processors/turn_processor.rs>
- Generated v2 turn-start schema: <https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/typescript/v2/TurnStartParams.ts>
- Separate-writer regression: <https://github.com/openai/codex/blob/main/codex-rs/app-server/tests/suite/v2/thread_resume.rs>

## Why a Windows Unix endpoint is real, and the Python limitation

The Codex Rust implementation intentionally supports its UDS abstraction on Windows through `uds_windows`. The Windows-specific App Server transport tests and `codex-uds` documentation are direct source evidence. The installed Windows PE also advertises `unix://` endpoints and the official CLI documentation says `codex --remote unix://PATH` is accepted.

However, PEX cannot simply call `websockets.unix_connect()` in its current Python runtime:

```text
platform=win32
socket.AF_UNIX present=False
event loop=ProactorEventLoop
.NET Socket.OSSupportsUnixDomainSockets=True
```

The installed `websockets 16.1.1` async Unix connector calls `loop.create_unix_connection`; the Python build cannot represent an AF_UNIX address because `socket.AF_UNIX` is absent. Therefore a direct Python Unix connector would be an unsupported claim even though the Codex Rust client/server support the endpoint.

There are three honest connector choices:

1. **Recommended deadline path: official Codex proxy connector.** Start only `codex app-server proxy --sock <absolute-existing-socket>`. Per the official README, this opens exactly one raw connection to the existing App Server and proxies bytes between the socket and stdin/stdout. It does not start, stop, replace, restart, or configure the App Server. PEX must perform the WebSocket HTTP Upgrade and masking/framing over that raw stream. The already installed `websockets` Sans-I/O `ClientProtocol` can supply validated handshake and frame handling; PEX should not hand-roll RFC 6455.
2. **Native Rust connector.** Add a small packaged Rust connector using the same `codex-uds`/`uds_windows` approach as upstream. This avoids the connector subprocess but expands build, packaging, signing, and audit scope; it is not the smallest deadline slice.
3. **Loopback TCP WebSocket.** Python can connect directly to `ws://127.0.0.1:<port>`, and it still provides the required shared-process semantics. Official documentation labels TCP WebSocket experimental and unsupported, so it is suitable only as an explicitly marked development/live-proof path, not the preferred release claim.

If “no process lifecycle management” means no helper process of any kind, option 1 is excluded and option 2 is required. If it means PEX must never own the user's harness lifecycle, option 1 is the smallest implementation: the transport owns only its short-lived connector and never issues `--listen`, `daemon`, start, restart, stop, or kill against the App Server.

## Original CLI visibility

The supported flow is:

```text
one user-owned App Server listener
  |-- connection A: codex --remote unix://<socket>
  `-- connection B: PEX shared transport -> same socket
```

Connection A starts or resumes the user's thread and is subscribed. Connection B initializes and resumes the exact same thread, causing the server to add B to the same thread's connection-ID set. The listener routes later thread/turn/item notifications to all subscribed IDs. Consequently, a future PEX turn through B would be visible in the original remote CLI on A.

This conclusion applies only when both clients use the same App Server process and remain subscribed. There is no supported claim that a Codex Desktop window backed by another process will receive those live events. A separately running App Server can at most read persisted history and can be rejected on resume by the active-writer lock.

## Current PEX mismatch

- `services/bridge/src/pex_bridge/adapters/codex.py:254`: `CodexStdioTransport` owns a new `codex app-server --listen stdio://` child.
- `services/bridge/src/pex_bridge/adapters/codex.py:580`: `_ensure_thread_loaded` resumes only immediately before mutation.
- `services/bridge/src/pex_bridge/adapters/codex.py:993`: `start_turn` has no authoritative idle/expected-turn fence.
- `services/bridge/src/pex_bridge/adapters/codex.py:1385`: discovery only lists stored threads; it doesn't subscribe.
- `services/bridge/src/pex_bridge/adapters/codex.py:1608`: the pump drains notifications from PEX's isolated transport only.
- `services/bridge/src/pex_bridge/app.py:3161` and `:3319`: both attach routes select the stdio child path; no shared endpoint route exists.

## Proposed shared-transport state machine

### Endpoint configuration

1. Accept an explicit endpoint kind and absolute path. Do not silently discover, create, delete, chmod, rebind, or replace a socket.
2. Require the socket parent to be an existing private user-controlled directory. On Windows, reject reparse-point traversal and paths outside an explicitly permitted root. Do not log the full path outside bounded diagnostics.
3. Resolve the exact Codex executable by the existing trusted binary resolver if using `app-server proxy`; never accept an unvalidated shell command.
4. Spawn no App Server. The only allowed proxy command is the fixed argv form `codex.exe app-server proxy --sock <path>`, with no shell.

### Connection and initialization

1. Open one bounded raw channel to the existing socket.
2. Perform the HTTP Upgrade for `ws://localhost/rpc` with the library's Sans-I/O client implementation.
3. Send exactly one `initialize` request with PEX `clientInfo`; validate a matching response ID and bounded object result.
4. Send `initialized`.
5. Increment `connection_generation` only after the full initialization handshake succeeds.
6. Start one reader/router task. It must classify JSON-RPC responses, notifications, and server requests with the same size, ID, retention, and secret-redaction bounds as the stdio transport.

### Authoritative subscription

1. Read the requested thread identity without mutation and bind the expected thread ID, `sessionId`, cwd, project ID, source/originator, model/provider, and history mode.
2. Require explicit user authorization to resume/subscribe because resume can load config and required MCP servers.
3. Call `thread/resume` with only the exact thread ID—no model, cwd, personality, or tool overrides.
4. Validate the response against the pre-read identity and the selected project/session binding.
5. Keep the reader active while resuming. After subscription succeeds, reconcile history with `thread/read includeTurns=true` or supported pagination. This closes the read-before-subscribe gap; stable turn/item IDs deduplicate notifications that arrived during reconciliation.
6. Record a subscription receipt bound to endpoint identity, connection generation, thread ID, root `sessionId`, project/cwd, resume response, and reconciliation watermark. It is not a delivery receipt.

### Reconnection

1. EOF, malformed handshake, oversized frame, protocol error, or proxy exit invalidates initialization and every cached subscription immediately.
2. Increment generation only after a fresh successful initialize; never reuse old subscription bindings.
3. Read-only reconnect may use bounded backoff. It must never start/restart the App Server.
4. On reconnect: initialize, resume/subscribe, then reconcile persisted history while buffering live notifications; emit each event once.
5. Any disconnect after a future mutation request is written makes delivery uncertain. Never retry that mutation.

### Read-only gate for the first slice

The first shared-transport implementation slice must support observation only; that intermediate slice cannot satisfy the final supervisor release gate:

- `send_message`: disabled before any `turn/start` request
- permission response: disabled
- interrupt: disabled
- fork/new thread: disabled
- App Server lifecycle: absent
- socket replacement/deletion: absent

`canAcceptDirectInput=false` is a hard rejection. `null` is unavailable, not permission. Even `true` is not enough to enable mutation while the `turn/start` race remains unresolved.

## Mutation race and future cooperative fence

`TurnStartParams` has no `expectedTurnId`, expected status, sequence, lease, or control revision. Current server behavior can route start-or-steer depending on live state. Checking `idle` immediately before the call is still a time-of-check/time-of-use race with the original CLI.

The server response and subsequent event stream can detect some bad outcomes—for example, a returned ID equal to the previously active turn or no matching `turn/started`—but detection occurs after input may already have been appended. It is not prevention.

A later intervention slice therefore needs an explicit cooperative ownership window tied to:

- endpoint and connection generation
- exact thread ID and root `sessionId`
- latest terminal turn ID and event watermark
- PEX control revision and action/intervention ID
- user-visible statement that the original CLI must not submit input during the window

PEX must re-read same-process status and direct-input capability immediately before delivery. This still remains cooperative rather than a protocol-enforced mutex, and the receipt/report must say so. If OpenAI adds an atomic expected-state or queue ownership API later, use that instead.

## Proposed code ownership for the next slice

Keep the change narrow and separable:

1. **New `services/bridge/src/pex_bridge/adapters/codex_shared.py`**
   - `CodexSharedEndpoint` validated configuration.
   - `CodexSharedAppServerTransport` request router, notification queue, initialization, generation invalidation, and subscribe/reconcile state machine.
   - an injected raw-channel factory for tests.
   - optional `CodexProxyUnixChannel` production connector, only if owning the connector child is authorized.
2. **Minimal `services/bridge/src/pex_bridge/adapters/codex.py` changes**
   - reuse the existing normalization/pump logic.
   - attach shared transport metadata and subscription receipt.
   - make the shared mode explicitly observation-only; do not route it through `_ensure_thread_loaded`/`start_turn`.
3. **Minimal `services/bridge/src/pex_bridge/app.py` changes**
   - add an explicit shared-endpoint attach request, separately named from stdio attach.
   - require authenticated mutation/CAS conventions already used by bridge routes.
   - never fall back to stdio or start a listener if shared connection fails.
4. **New `tests/unit/test_codex_shared_transport.py`**
   - transport and subscription state-machine tests with in-memory/mock raw channels only.
5. **New `tests/contract/test_codex_shared_attach.py`**
   - authenticated route, endpoint validation, truthful capability/status, and no-fallback tests using a fake transport factory.

Do not change desktop UI, installer, benchmark manifests, global hooks, or existing App Server lifecycle in this slice.

## Required non-live tests

- exact WebSocket Upgrade request, successful `101`, text-frame parsing, ping/pong/close, masking, fragmented/oversized/malformed frames
- initialize once per generation; no method before initialization; duplicate/mismatched response IDs rejected
- response and notification multiplexing under concurrency
- two logical clients subscribed to one fake server both receive the same turn events
- unsubscribe/close removes only the PEX subscription
- resume response must match thread ID, `sessionId`, cwd/project, and selected binding
- `canAcceptDirectInput=false` and `null` remain non-mutable
- observer never invokes `turn/start`, permission response, interrupt, thread start/fork, or lifecycle commands
- reconnect invalidates subscription; resume plus replay closes event gaps and deduplicates stable IDs
- disconnect after a write is delivery-uncertain and never retried
- writer-conflict response remains blocked and is not converted to a new isolated server
- missing socket, stale rendezvous path, reparse traversal, proxy early exit, stderr content, timeout, and cancellation fail closed without leaking prompt/path/credential data
- an effect spy proves no `--listen`, daemon, restart, stop, kill, provider call, workspace write, or benchmark mutation occurs

## Pending live proof and authority

The following remain unproven and require a separate, explicit live authorization:

1. The installed `0.153.0` Windows CLI successfully serves and connects through the selected shared Unix socket on this machine.
2. A user-started `codex --remote unix://...` thread and PEX both receive the same exact terminal event stream.
3. Reconnect/replay closes gaps without duplicates against the installed server.
4. The original CLI visibly renders an eventual PEX-started turn.
5. The cooperative intervention window is understandable and prevents concurrent human input in the demo.

No live proof should begin until the transport-only code and non-live tests pass independent review. Starting the listener, attaching the user's CLI, sending a model turn, or attempting intervention are separate user-authorized actions. Until then the same-session product and benchmark cells remain unproven.
