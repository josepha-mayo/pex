"""Public observable invariants; no implementation-private inspection."""
import asyncio
import unittest
from asyncpool import Pool

async def bounded(awaitable):
    return await asyncio.wait_for(awaitable, 2)

async def enqueue(pool, key):
    ready = asyncio.Event()
    async def acquire():
        ready.set()
        return await pool.acquire(key)
    task = asyncio.create_task(acquire())
    await ready.wait()  # Acquirer runs to its first blocked await before parent resumes.
    return task

class PublicTests(unittest.IsolatedAsyncioTestCase):
    async def test_basic_and_idempotent_release(self):
        pool = Pool(1, 1)
        first = await bounded(pool.acquire('a'))
        waiting = await enqueue(pool, 'b')
        self.assertFalse(waiting.done())
        first.release(); first.release()
        second = await bounded(waiting)
        third = await enqueue(pool, 'c')
        self.assertFalse(third.done())
        second.release(); (await bounded(third)).release()

    async def test_context_exception_releases(self):
        pool = Pool(1, 1)
        error = LookupError('original')
        with self.assertRaises(LookupError) as caught:
            async with pool.slot('a'):
                raise error
        self.assertIs(caught.exception, error)
        (await bounded(pool.acquire('b'))).release()

    async def test_global_and_per_key_limits(self):
        pool = Pool(2, 1)
        a = await bounded(pool.acquire('a'))
        blocked_a = await enqueue(pool, 'a')
        b = await bounded(pool.acquire('b'))
        c = await enqueue(pool, 'c')
        self.assertFalse(blocked_a.done()); self.assertFalse(c.done())
        a.release(); a2 = await bounded(blocked_a)
        self.assertFalse(c.done())
        b.release(); (await bounded(c)).release(); a2.release()

    async def test_cancel_queued_then_progress(self):
        pool = Pool(1, 1)
        first = await pool.acquire('a')
        cancelled = await enqueue(pool, 'a')
        survivor = await enqueue(pool, 'a')
        cancelled.cancel()
        with self.assertRaises(asyncio.CancelledError): await cancelled
        first.release(); (await bounded(survivor)).release()
        (await bounded(pool.acquire('new'))).release()
