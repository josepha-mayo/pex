"""Independent schedules, same public contract. Never sent to models."""
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
    await ready.wait()
    return task

class AcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_woken_waiter_cancelled_before_resume(self):
        pool = Pool(1, 1)
        held = await pool.acquire('a')
        first = await enqueue(pool, 'a'); second = await enqueue(pool, 'a')
        held.release(); first.cancel()  # No await between promise and cancellation.
        with self.assertRaises(asyncio.CancelledError): await first
        (await bounded(second)).release()
        (await bounded(pool.acquire('a'))).release()

    async def test_arrival_cannot_steal_woken_global_slot(self):
        pool = Pool(1, 1)
        held = await pool.acquire('a'); older = await enqueue(pool, 'b')
        gate, ready = asyncio.Event(), asyncio.Event()
        async def arriving():
            ready.set(); await gate.wait(); return await pool.acquire('c')
        newer = asyncio.create_task(arriving()); await ready.wait()
        gate.set(); held.release()  # Newcomer callback precedes old waiter resumption.
        old_lease = await bounded(older)
        self.assertFalse(newer.done())
        old_lease.release(); (await bounded(newer)).release()

    async def test_arrival_cannot_exceed_woken_per_key_slot(self):
        pool = Pool(3, 1)
        held = await pool.acquire('a'); older = await enqueue(pool, 'a')
        gate, ready = asyncio.Event(), asyncio.Event()
        async def arriving():
            ready.set(); await gate.wait(); return await pool.acquire('a')
        newer = asyncio.create_task(arriving()); await ready.wait()
        gate.set(); held.release()  # Acquire occurs after promise but before old resumes.
        old_lease = await bounded(older)
        self.assertFalse(newer.done())
        old_lease.release(); (await bounded(newer)).release()

    async def test_saturated_key_does_not_block_eligible_key(self):
        pool = Pool(2, 1)
        a = await pool.acquire('a'); b = await pool.acquire('b')
        blocked = await enqueue(pool, 'a'); eligible = await enqueue(pool, 'c')
        b.release(); c = await bounded(eligible)
        self.assertFalse(blocked.done())
        c.release(); a.release(); (await bounded(blocked)).release()

    async def test_cancel_chain_preserves_survivor_order(self):
        pool = Pool(1, 1); held = await pool.acquire('a')
        waiters = [await enqueue(pool, 'a') for _ in range(8)]
        held.release(); waiters[0].cancel()
        for index in (2, 4, 6): waiters[index].cancel()
        for index in (0, 2, 4, 6):
            with self.assertRaises(asyncio.CancelledError): await waiters[index]
        for index in (1, 3, 5, 7):
            lease = await bounded(waiters[index])
            self.assertTrue(all(not waiters[j].done() for j in (1, 3, 5, 7) if j > index))
            lease.release()
        (await bounded(pool.acquire('fresh'))).release()

    async def test_cancel_context_holder_releases(self):
        pool = Pool(1, 1); entered = asyncio.Event(); never = asyncio.Event()
        async def holder():
            async with pool.slot('a'):
                entered.set(); await never.wait()
        task = asyncio.create_task(holder()); await entered.wait()
        waiter = await enqueue(pool, 'b'); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        (await bounded(waiter)).release()

    async def test_multiple_releases_and_interleaved_keys(self):
        pool = Pool(3, 2)
        held = [await pool.acquire(k) for k in ('a', 'a', 'b')]
        tasks = [await enqueue(pool, k) for k in ('a', 'b', 'c', 'a', 'c')]
        held[0].release(); held[1].release(); held[2].release()
        leases = [await bounded(tasks[i]) for i in range(3)]
        self.assertFalse(tasks[3].done()); self.assertFalse(tasks[4].done())
        for lease in leases: lease.release()
        for task in tasks[3:]: (await bounded(task)).release()

    async def test_validation(self):
        for limits in ((0, 1), (1, 0), (True, 2), (1, False), (1.5, 2), (1, -1)):
            with self.assertRaises(ValueError): Pool(*limits)
        pool = Pool(1, 1)
        for key in ('', None, 1, False):
            with self.assertRaises(ValueError): await pool.acquire(key)
        (await bounded(pool.acquire('valid'))).release()
