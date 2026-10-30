from .protocol import CommandError, encode_command

class Client:
    def __init__(self, pool):
        self.pool = pool

    async def _exchange(self, payload, count):
        lease = await self.pool.acquire()
        try:
            return await lease.connection.exchange(payload, count)
        finally:
            lease.release()

    async def execute(self, *parts):
        payload = encode_command(parts)
        result = (await self._exchange(payload, 1))[0]
        if isinstance(result, CommandError):
            raise result
        return result

    async def pipeline(self, commands, *, return_exceptions=False):
        if not isinstance(commands, (list, tuple)):
            raise TypeError('list/tuple of commands required')
        encoded = [encode_command(parts) for parts in commands]
        if not encoded:
            return []
        values = await self._exchange(b''.join(encoded), len(encoded))
        if not return_exceptions:
            for value in values:
                if isinstance(value, CommandError):
                    raise value
        return values
