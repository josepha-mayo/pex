"""Starter pool: idle transports are reused; callers release their leases."""
import asyncio
from .connection import Connection
from .protocol import PoolClosed

class Lease:
    def __init__(self, pool, connection):
        self.pool = pool
        self.connection = connection
        self.released = False

    def release(self):
        if self.released:
            return
        self.released = True
        self.pool._return(self.connection)

class Pool:
    def __init__(self, factory, max_size=2):
        if max_size <= 0:
            raise ValueError('positive size required')
        self.factory = factory
        self.max_size = max_size
        self.count = 0
        self.idle = asyncio.Queue()
        self.closed = False

    async def acquire(self):
        if self.closed:
            raise PoolClosed('closed')
        if not self.idle.empty():
            connection = self.idle.get_nowait()
        elif self.count < self.max_size:
            connection = Connection(await self.factory())
            self.count += 1
        else:
            connection = await self.idle.get()
        return Lease(self, connection)

    def _return(self, connection):
        if connection.closed or self.closed:
            connection.close()
            self.count -= 1
        else:
            self.idle.put_nowait(connection)

    async def aclose(self):
        self.closed = True
        while not self.idle.empty():
            self.idle.get_nowait().close()
            self.count -= 1
