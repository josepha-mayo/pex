"""Starter single-owner connection. Callers obtain ownership through Pool."""
from .protocol import Decoder, NEED_MORE, CommandError

class Connection:
    def __init__(self, transport):
        self.transport = transport
        self.decoder = Decoder()
        self.closed = False

    def close(self):
        if not self.closed:
            self.closed = True
            self.transport.close()

    async def exchange(self, payload, count):
        if self.closed:
            raise ConnectionError('closed')
        await self.transport.send(payload)
        results = []
        try:
            for _ in range(count):
                value = self.decoder.pop()
                while value is NEED_MORE:
                    chunk = await self.transport.recv()
                    if not chunk:
                        raise ConnectionError('EOF')
                    self.decoder.feed(chunk)
                    value = self.decoder.pop()
                if isinstance(value, CommandError):
                    raise value
                results.append(value)
            return results
        except OSError:
            self.close()
            raise
