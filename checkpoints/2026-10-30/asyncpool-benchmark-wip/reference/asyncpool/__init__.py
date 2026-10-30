"""Authored clean-room reference; never provided to benchmark worker/monitor."""
import asyncio
from collections import deque
from contextlib import asynccontextmanager


class Lease:
    def __init__(self, pool, key):
        self._pool, self._key, self._released = pool, key, False

    def release(self):
        if self._released:
            return
        self._released = True
        self._pool._release(self._key)


class _Waiter:
    def __init__(self, key, future):
        self.key, self.future, self.granted = key, future, False


class Pool:
    def __init__(self, total_limit, per_key_limit):
        if any(type(v) is not int or v <= 0 for v in (total_limit, per_key_limit)):
            raise ValueError('positive integer limits required')
        self._total_limit, self._key_limit = total_limit, per_key_limit
        self._held, self._keys, self._waiters = 0, {}, deque()

    def _grant(self, waiter):
        # Promises count immediately, BEFORE the awakened task can run.
        self._held += 1
        self._keys[waiter.key] = self._keys.get(waiter.key, 0) + 1
        waiter.granted = True
        waiter.future.set_result(None)

    def _drain(self):
        for waiter in tuple(self._waiters):
            if waiter.future.cancelled():
                self._waiters.remove(waiter)
                continue
            if self._held >= self._total_limit:
                break
            if self._keys.get(waiter.key, 0) >= self._key_limit:
                continue  # Other keys can still be eligible.
            self._waiters.remove(waiter)
            self._grant(waiter)

    def _release(self, key):
        self._held -= 1
        self._keys[key] -= 1
        if self._keys[key] == 0:
            del self._keys[key]
        self._drain()

    async def acquire(self, key):
        if not isinstance(key, str) or not key:
            raise ValueError('nonempty string key required')
        waiter = _Waiter(key, asyncio.get_running_loop().create_future())
        self._waiters.append(waiter)
        self._drain()
        try:
            await waiter.future
        except BaseException:
            if waiter.granted:
                self._release(key)  # Reclaim the promise, not just queue membership.
            elif waiter in self._waiters:
                self._waiters.remove(waiter)
                self._drain()
            raise
        return Lease(self, key)

    @asynccontextmanager
    async def slot(self, key):
        lease = await self.acquire(key)
        try:
            yield lease
        finally:
            lease.release()
