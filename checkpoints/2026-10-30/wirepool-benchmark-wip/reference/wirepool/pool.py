import asyncio
from collections import deque
from .connection import Connection
from .protocol import PoolClosed

_CREATE = object()

class Lease:
    def __init__(self, pool, connection):
        self._pool = pool
        self.connection = connection
        self._released = False

    def release(self):
        if self._released:
            return
        self._released = True
        self._pool._put(self.connection)

class Pool:
    def __init__(self, factory, max_size=2):
        if type(max_size) is not int or max_size <= 0:
            raise ValueError('positive exact integer max_size required')
        self._factory, self._limit = factory, max_size
        self._total = 0
        self._idle, self._waiters = deque(), deque()
        self._closed = False

    def _dispatch(self):
        while self._waiters and not self._closed:
            if self._waiters[0].done():
                self._waiters.popleft()
                continue
            while self._idle and self._idle[0].closed:
                self._idle.popleft()
                self._total -= 1
            if self._idle:
                value = self._idle.popleft()
            elif self._total < self._limit:
                self._total += 1  # Reserve before publishing the factory promise.
                value = _CREATE
            else:
                return
            self._waiters.popleft().set_result(value)

    def _put(self, connection):
        if self._closed or connection.closed:
            connection.close()
            self._total -= 1
        else:
            self._idle.append(connection)
        self._dispatch()

    async def acquire(self):
        if self._closed:
            raise PoolClosed('pool closed')
        future = asyncio.get_running_loop().create_future()
        self._waiters.append(future)
        self._dispatch()
        try:
            item = await future
        except BaseException:
            if future.done() and not future.cancelled() and future.exception() is None:
                item = future.result()
                if item is _CREATE:
                    self._total -= 1
                else:
                    self._put(item)
            else:
                future.cancel()
            self._dispatch()
            raise
        if item is _CREATE:
            try:
                transport = await self._factory()
            except BaseException:
                self._total -= 1
                self._dispatch()
                raise
            connection = Connection(transport)
            if self._closed:
                connection.close()
                self._total -= 1
                raise PoolClosed('pool closed during connection creation')
        else:
            connection = item
        return Lease(self, connection)

    async def aclose(self):
        if self._closed:
            return
        self._closed = True
        while self._idle:
            self._idle.popleft().close()
            self._total -= 1
        while self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_exception(PoolClosed('pool closed'))
