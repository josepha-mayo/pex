from .protocol import Decoder, NEED_MORE

class Connection:
    def __init__(self, transport):
        self._transport = transport
        self._decoder = Decoder()
        self.closed = False

    def close(self):
        if not self.closed:
            self.closed = True
            self._transport.close()

    async def exchange(self, payload, count):
        if self.closed:
            raise ConnectionError('closed connection')
        try:
            await self._transport.send(payload)
            replies = []
            while len(replies) < count:
                value = self._decoder.pop()
                if value is NEED_MORE:
                    chunk = await self._transport.recv()
                    if not chunk:
                        raise ConnectionError('unexpected EOF')
                    self._decoder.feed(chunk)
                else:
                    replies.append(value)
            return replies
        except BaseException:
            self.close()
            raise
