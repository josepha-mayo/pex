"""Starter RESP2 codec. Repair it against TASK.md, including fragmented input."""
class CommandError(Exception):
    pass

class ProtocolError(Exception):
    pass

class PoolClosed(Exception):
    pass

NEED_MORE = object()


def encode_command(parts):
    if not isinstance(parts, (tuple, list)) or not parts:
        raise ValueError('command required')
    result = b'*' + str(len(parts)).encode() + b'\r\n'
    for part in parts:
        if isinstance(part, str):
            part = part.encode()
        elif isinstance(part, int):
            part = str(part).encode()
        elif not isinstance(part, bytes):
            raise TypeError('unsupported argument')
        result += b'$' + str(len(part)).encode() + b'\r\n' + part + b'\r\n'
    return result


class Decoder:
    def __init__(self, max_bulk=1048576, max_depth=16):
        self.max_bulk = max_bulk
        self.max_depth = max_depth
        self.buffer = b''

    def feed(self, data):
        self.buffer += data

    def pop(self):
        if b'\r\n' not in self.buffer:
            return NEED_MORE
        header, self.buffer = self.buffer.split(b'\r\n', 1)
        if not header:
            raise ProtocolError('empty header')
        kind, text = header[:1], header[1:]
        if kind == b'+':
            return text
        if kind == b'-':
            return CommandError(text.decode(errors='replace'))
        try:
            size = int(text)
        except ValueError as error:
            raise ProtocolError('bad number') from error
        if kind == b':':
            return size
        if kind == b'$':
            if size == -1:
                return None
            if len(self.buffer) < size + 2:
                return NEED_MORE
            value, self.buffer = self.buffer[:size], self.buffer[size + 2:]
            return value
        if kind == b'*':
            if size == -1:
                return None
            values = []
            for _ in range(size):
                value = self.pop()
                if value is NEED_MORE:
                    return NEED_MORE
                values.append(value)
            return values
        raise ProtocolError('unknown prefix')
