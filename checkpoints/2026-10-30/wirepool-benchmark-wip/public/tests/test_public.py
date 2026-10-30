"""Eight public examples. ScriptTransport is an AUTHORED transport double."""
import asyncio
import unittest
from wirepool import (Client, Connection, Pool, PoolClosed, Decoder, NEED_MORE,
                      encode_command, CommandError, ProtocolError)


async def turn():
    """An event-loop barrier, never a wall-clock timing assumption."""
    future = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(future.set_result, None)
    await future


class ScriptTransport:
    def __init__(self, replies=(), send_gate=None):
        self.replies = list(replies)
        self.queue = asyncio.Queue()
        self.sent = []
        self.sending = asyncio.Event()
        self.receiving = asyncio.Event()
        self.send_gate = send_gate
        self.closed = False
        self.close_count = 0

    async def send(self, payload):
        if self.closed:
            raise ConnectionError('transport closed')
        self.sent.append(payload)
        self.sending.set()
        if self.replies:
            for chunk in self.replies.pop(0):
                self.queue.put_nowait(chunk)
        if self.send_gate is not None:
            await self.send_gate.wait()

    async def recv(self):
        self.receiving.set()
        return await self.queue.get()

    def close(self):
        if not self.closed:
            self.closed = True
            self.close_count += 1
            self.queue.put_nowait(b'')


class PublicTests(unittest.IsolatedAsyncioTestCase):
    async def test_codec_fragmentation_and_multiple_frames(self):
        self.assertEqual(encode_command(('SET', b'a\x00', 19)),
            b'*3\r\n$3\r\nSET\r\n$2\r\na\x00\r\n$2\r\n19\r\n')
        decoder = Decoder()
        frame = b'*3\r\n$3\r\na\r\n\r\n*-1\r\n*2\r\n:7\r\n-ERR nested\r\n'
        for byte in frame[:-1]:
            decoder.feed(bytes([byte]))
            self.assertIs(decoder.pop(), NEED_MORE)
        decoder.feed(frame[-1:] + b'+tail\r\n')
        value = decoder.pop()
        self.assertEqual(value[:2], [b'a\r\n', None])
        self.assertEqual(value[2][0], 7)
        self.assertIsInstance(value[2][1], CommandError)
        self.assertEqual(str(value[2][1]), 'ERR nested')
        self.assertEqual(decoder.pop(), b'tail')
        self.assertIs(decoder.pop(), NEED_MORE)

    async def test_invalid_input_is_validated_before_acquisition(self):
        calls = []
        async def factory():
            calls.append(1)
            return ScriptTransport()
        pool = Pool(factory)
        client = Client(pool)
        for operation in (lambda: client.execute('SET', True),
                          lambda: client.pipeline([('PING',), ('GET', object())])):
            with self.assertRaises((TypeError, ValueError)):
                await asyncio.wait_for(operation(), 2)
        self.assertEqual(await client.pipeline([]), [])
        self.assertEqual(calls, [])
        await pool.aclose()

    async def test_capacity_reuse_and_idempotent_release(self):
        created = []
        async def factory():
            t = ScriptTransport(); created.append(t); return t
        pool = Pool(factory, max_size=1)
        lease = await pool.acquire()
        waiter = asyncio.create_task(pool.acquire())
        await turn()
        self.assertFalse(waiter.done())
        lease.release(); lease.release()
        second = await asyncio.wait_for(waiter, 2)
        self.assertIs(second.connection, lease.connection)
        self.assertEqual(len(created), 1)
        second.release()
        await pool.aclose(); await pool.aclose()
        self.assertEqual(created[0].close_count, 1)

    async def test_server_errors_drain_pipeline_and_preserve_reuse(self):
        t = ScriptTransport([[b':1\r\n-ERR bad\r\n:3\r\n'], [b'+next\r\n']])
        async def factory(): return t
        pool = Pool(factory, 1); client = Client(pool)
        with self.assertRaisesRegex(CommandError, 'ERR bad'):
            await asyncio.wait_for(client.pipeline([('A',), ('B',), ('C',)]), 2)
        self.assertEqual(await asyncio.wait_for(client.execute('D'), 2), b'next')
        self.assertEqual(len(t.sent), 2)
        self.assertFalse(t.closed)
        await pool.aclose()

    async def test_cancel_ordinary_read_retires_connection(self):
        first = ScriptTransport()
        second = ScriptTransport([[b'+own\r\n']])
        transports = iter([first, second])
        async def factory(): return next(transports)
        pool = Pool(factory, 1); client = Client(pool)
        request = asyncio.create_task(client.execute('OLD'))
        await asyncio.wait_for(first.receiving.wait(), 2)
        request.cancel()
        with self.assertRaises(asyncio.CancelledError): await request
        self.assertTrue(first.closed)
        self.assertEqual(await asyncio.wait_for(client.execute('NEW'), 2), b'own')
        await pool.aclose()

    async def test_cancel_accepted_send_retires_connection(self):
        gate = asyncio.Event(); t = ScriptTransport(send_gate=gate)
        async def factory(): return t
        pool = Pool(factory, 1)
        request = asyncio.create_task(Client(pool).execute('SIDE_EFFECT'))
        await asyncio.wait_for(t.sending.wait(), 2)
        request.cancel()
        with self.assertRaises(asyncio.CancelledError): await request
        self.assertTrue(t.closed)
        self.assertEqual(len(t.sent), 1)
        await pool.aclose()

    async def test_shutdown_wakes_waiter_but_leased_connection_finishes(self):
        t = ScriptTransport()
        async def factory(): return t
        pool = Pool(factory, 1)
        lease = await pool.acquire()
        waiter = asyncio.create_task(pool.acquire()); await turn()
        await pool.aclose()
        with self.assertRaises(PoolClosed): await asyncio.wait_for(waiter, 2)
        with self.assertRaises(PoolClosed): await pool.acquire()
        self.assertFalse(t.closed)
        lease.release()
        self.assertTrue(t.closed)

    async def test_protocol_fault_and_eof_close_connection(self):
        for chunks, exception in (([b'$2\r\nabXX'], ProtocolError),
                                  ([b'$3\r\nab', b''], ConnectionError)):
            with self.subTest(chunks=chunks):
                t = ScriptTransport([chunks]); conn = Connection(t)
                with self.assertRaises(exception):
                    await conn.exchange(encode_command(('READ',)), 1)
                self.assertTrue(t.closed)
