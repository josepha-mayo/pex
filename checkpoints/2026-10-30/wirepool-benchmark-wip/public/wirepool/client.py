"""Starter client facade. The server returns one reply per command."""
from .protocol import CommandError, encode_command

class Client:
    def __init__(self, pool):
        self.pool = pool

    async def execute(self, *parts):
        payload = encode_command(parts)
        lease = await self.pool.acquire()
        try:
            values = await lease.connection.exchange(payload, 1)
        except Exception:
            lease.release()
            raise
        lease.release()
        return values[0]

    async def pipeline(self, commands, *, return_exceptions=False):
        if not isinstance(commands, (tuple, list)):
            raise TypeError('list of commands required')
        if not commands:
            return []
        payload = b''.join(encode_command(parts) for parts in commands)
        lease = await self.pool.acquire()
        try:
            return await lease.connection.exchange(payload, len(commands))
        finally:
            lease.release()
