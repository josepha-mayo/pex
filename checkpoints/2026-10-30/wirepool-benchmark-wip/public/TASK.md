# Wirepool: repair a cancellation-safe pooled RESP client

Implement/repair the Python 3.11+ standard-library-only `wirepool` package. The
starter is a small, flawed client, not Redis itself. This is a clean-room task
inspired by redis-py issues #2624/#2665: after cancellation, a pooled connection
can deliver an earlier caller's unread response to a later caller. No Redis
server, sockets, third-party packages, or timing-sensitive network are needed.
The tests' transport is an explicitly authored, deterministic transport double.

Keep this specification and supplied tests unchanged. You may change/add Python
modules under `wirepool/`, and add your own tests. The public tests are examples,
not the complete contract. Every acceptance requirement is specified below.

## 1. Public API and wire codec

Export `Client`, `Pool`, `Lease`, `Connection`, `Decoder`, `NEED_MORE`,
`encode_command`, `CommandError`, `ProtocolError`, and `PoolClosed` from
`wirepool`. The three exceptions inherit `Exception`.

`encode_command(parts)` accepts a nonempty list/tuple of bytes, str, or int
(exact int; bool is invalid). Strings use UTF-8, integers ASCII decimal. Return
one RESP2 array of bulk strings, preserving embedded CR/LF and NUL bytes.
Invalid container, empty command, or invalid part raises `TypeError` or
`ValueError`. Validate *all* commands before acquiring a connection or sending
anything. Inputs are never mutated.

`Decoder(max_bulk=1048576, max_depth=16)` has `feed(bytes)` and `pop()`.
`pop()` returns one complete value, or the singleton `NEED_MORE` if incomplete;
incomplete parsing must not consume any part of the pending frame. It retains
subsequent bytes/frames. Any byte boundary (including CR/LF and bulk trailers)
may divide a frame. Support these RESP2 reply types:

* `+text\r\n` -> bytes; `-text\r\n` -> CommandError whose str is UTF-8 text
  decoded with replacement; `:decimal\r\n` -> int.
* `$n\r\n<data>\r\n` -> bytes of exactly n bytes; `$-1\r\n` -> None.
* `*n\r\n<values...>` -> list; `*-1\r\n` -> None. Nested errors remain
  CommandError values, not automatically raised; empty arrays are supported.

Decimal grammar is an optional minus then one or more ASCII digits (no plus,
whitespace, or underscores); lengths/counts below -1 are invalid. Unknown
prefix, invalid decimal, invalid bulk trailer, bulk length over max_bulk, or
array nesting over max_depth raises ProtocolError, as soon as enough bytes
establish the violation. The outermost array has depth 1; null and empty arrays also count as array nesting. Limits are positive
exact ints, otherwise ValueError. `feed` accepts bytes only. No RESP3 support,
line-size cap, aggregate memory quota, or performance asymptotic is required.

## 2. Transport and connection

A factory is an async zero-argument callable returning a new transport. Each
transport supports `await send(payload: bytes)`, `await recv() -> bytes`, and
synchronous, idempotent, non-raising `close()`. send may already have accepted
some/all bytes before suspending or failing. recv may return arbitrary chunks;
b'' means EOF. A cancelled factory cleans up its own partial resources, and
no transport is returned on factory failure. Do not access transport internals.

`Connection(transport)` exposes `.closed`, synchronous idempotent `.close()`,
and `async exchange(payload: bytes, count: int) -> list`. exchange sends exactly
once, then reads exactly count top-level replies through a persistent Decoder.
A closed connection raises ConnectionError. Callers provide positive count and
valid encoded payload. Top-level server CommandError replies are returned as
values by exchange, not raised. EOF raises ConnectionError. Protocol errors,
send/recv errors, and *any BaseException including cancellation* once exchange
begins must close the transport synchronously before propagating, without
retrying or waiting for the missing response. No detached I/O task may remain.
The pool guarantees exclusive use; direct overlapping exchange is out of scope.

## 3. Exclusive bounded pool and graceful shutdown

`Pool(factory, max_size=2)` requires a positive exact int limit (else ValueError).
`await pool.acquire()` returns `Lease` with `.connection` and synchronous,
idempotent `.release()`. A healthy release reuses the same connection; a closed
connection is discarded and its capacity reclaimed. Never hand one connection
to two live leases. Capacity includes **factory calls in progress and assigned
handoffs not yet resumed**, not merely existing transports. At most max_size
connections/reservations may exist at once.

When full, acquisitions are FIFO, skipping cancelled waiters; new arrivals
cannot steal a connection/slot already promised to an older waiter. Cancelling
an acquisition while queued, after handoff but before resumption, or during a
factory call must reclaim exactly its own resources/reservation, promptly and
without disturbing another lease. A cancelled successful handoff must return a
healthy assigned connection to the pool (not discard it), unless the pool is
closed. If cancellation is delivered before acquire returns, it propagates as
CancelledError even if shutdown has already signaled that waiter.
Factory exceptions propagate unchanged and
restore capacity. There must be no lost wakeup after cancellation/failure.

`await pool.aclose()` is idempotent and nonblocking graceful shutdown: reject
new acquisitions and wake queued waiters with PoolClosed; close idle transports
immediately. Existing leases may finish, but close on release. An assigned connection handoff not yet resumed counts as an existing lease.
An assigned capacity reservation is not a connection lease: a factory that completes
after shutdown must close its returned transport and raise PoolClosed rather
than returning a lease. Shutdown must not wait for or cancel a blocked factory or lease.

## 4. Client operations and reply ownership

`Client(pool)` exposes `async execute(*parts)` and
`async pipeline(commands, *, return_exceptions=False)`. commands is a list/tuple
of commands (each a list/tuple as above); an empty pipeline returns [] without
acquiring/sending. execute returns one reply, raising a top-level CommandError.
pipeline sends all commands in **one** payload, returns replies in input order,
and consumes **all** responses even if an earlier response is a CommandError.
With return_exceptions=False it raises the first top-level CommandError *after*
all responses have been consumed. With True it returns those exceptions at
their indices. Fully consumed server errors leave the connection reusable;
transport/protocol failures or cancellation retire it. Always release leases,
including BaseException exits. Do not retry/replay requests automatically.

Cancellation must propagate promptly as CancelledError, not a fabricated
result or generic error; do not shield request I/O until completion. A cancelled
wait for pool capacity sends nothing and does not close someone else's lease.
A cancelled partial send/read/pipeline must not leave replies available to a
later request. Independent concurrent clients sharing one pool must preserve
request/reply ownership and pool bounds across these interleavings.

## Commands and evaluation

Run `python -m unittest discover -s tests -v` from the public workspace. The
withheld suite tests only the public requirements above, using different
fragmentations, reply contents, event-gated cancellations, and interleavings.
Watchdog timeouts diagnose hangs; no correctness assertion depends on sleeps.
All local starter/reference/mutation results are authored software checks, not
real model-inference results. No particular baseline outcome is guaranteed.
