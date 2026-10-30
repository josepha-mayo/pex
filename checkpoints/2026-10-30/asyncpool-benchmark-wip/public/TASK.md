# Cancellation-safe bounded asynchronous pool

Implement `asyncpool.Pool(total_limit, per_key_limit)` in Python 3.11 standard
library only. This is a new implementation task: the supplied module is an honest
stub, not a deliberately defective completed implementation. No network, threads,
external dependencies, filesystem persistence, or background maintenance task is
needed. Only edit/add Python files under `asyncpool/` and add your own tests; do
not alter this specification or supplied tests.

## API
* Both limits are positive integers; bool is invalid. Invalid limits raise
  ValueError. Keys are nonempty strings; invalid keys raise ValueError.
* `await pool.acquire(key)` returns a Lease. Its synchronous `lease.release()`
  releases that lease exactly once; subsequent releases are harmless no-ops.
* `async with pool.slot(key): ...` acquires and always releases a lease, including
  when the body raises or is cancelled. Do not swallow the original exception.
* A pool is used on one asyncio event loop. Cross-loop behavior is out of scope.

## Required behavior
At every point, held leases plus capacity already promised to awakened waiters
must obey BOTH the overall limit and the limit for each key. An arriving caller
must not steal a promised slot or make either limit temporarily exceed its bound.

Waiters whose key has room must make progress when overall capacity is available.
A waiter for a saturated key must not block another eligible key. Among queued
waiters currently eligible for the same released capacity, use arrival order.
Cancellation must not reorder surviving waiters arbitrarily.

An acquisition can be cancelled while queued OR after it has been awakened but
before its task resumes. In either case propagate cancellation, reclaim any slot
promised to that waiter, and make that capacity available to another eligible
waiter. Cancelled waiters must not strand capacity or consume future releases.
After finite cancellations and releases, a fresh acquisition must still succeed.

Do not busy-wait or repeatedly poll capacity: use ordinary asyncio synchronization.
Do not depend on a particular delay, wall clock, or private event-loop internals.
All tests use a single event loop, finite tasks, and explicit synchronization.
They inspect observable progress and concurrent holders, not private attributes.
A watchdog bounds a test hang; elapsed time is not the score.

Run `python -m unittest discover -s tests -v`. Report changes and tests actually
run. Additional independent checks exercise the SAME documented behavior with
other finite cancellation/interleaving schedules. No hidden requirements exist.
