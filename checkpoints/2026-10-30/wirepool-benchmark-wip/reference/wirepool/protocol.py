"""Authored clean-room RESP2 codec; not copied from a production client."""
import re

class CommandError(Exception):
    pass

class ProtocolError(Exception):
    pass

class PoolClosed(Exception):
    pass

class _Incomplete(Exception):
    pass

NEED_MORE = object()
_DECIMAL = re.compile(rb'-?[0-9]+\Z')


def encode_command(parts):
    if not isinstance(parts, (list, tuple)) or not parts:
        raise ValueError('nonempty list/tuple command required')
    values = []
    for part in parts:
        if isinstance(part, bytes):
            value = part
        elif isinstance(part, str):
            value = part.encode('utf-8')
        elif type(part) is int:
            value = str(part).encode('ascii')
        else:
            raise TypeError('command parts must be bytes, str, or int')
        values.append(b'$' + str(len(value)).encode() + b'\r\n' + value + b'\r\n')
    return b'*' + str(len(values)).encode() + b'\r\n' + b''.join(values)


class Decoder:
    def __init__(self, max_bulk=1048576, max_depth=16):
        if any(type(v) is not int or v <= 0 for v in (max_bulk, max_depth)):
            raise ValueError('positive exact integer limits required')
        self.max_bulk, self.max_depth = max_bulk, max_depth
        self._buffer = bytearray()

    def feed(self, data):
        if not isinstance(data, bytes):
            raise TypeError('bytes required')
        self._buffer.extend(data)

    def pop(self):
        try:
            value, end = self._parse(0, 0)
        except _Incomplete:
            return NEED_MORE
        del self._buffer[:end]
        return value

    def _number(self, raw):
        if not _DECIMAL.fullmatch(raw):
            raise ProtocolError('invalid decimal')
        try:
            return int(raw)
        except ValueError as error:
            raise ProtocolError('invalid decimal') from error

    def _parse(self, pos, depth):
        buf = self._buffer
        if pos >= len(buf):
            raise _Incomplete
        kind = buf[pos]
        if kind not in b'+-:$*':
            raise ProtocolError('unknown prefix')
        end = buf.find(b'\r\n', pos + 1)
        if end < 0:
            raise _Incomplete
        raw = bytes(buf[pos + 1:end])
        pos = end + 2
        if kind == ord('+'):
            return raw, pos
        if kind == ord('-'):
            return CommandError(raw.decode('utf-8', errors='replace')), pos
        number = self._number(raw)
        if kind == ord(':'):
            return number, pos
        if number < -1:
            raise ProtocolError('invalid negative length')
        if kind == ord('$'):
            if number == -1:
                return None, pos
            if number > self.max_bulk:
                raise ProtocolError('bulk too large')
            trailer = bytes(buf[pos + number:pos + number + 2])
            if trailer and not b'\r\n'.startswith(trailer):
                raise ProtocolError('bad bulk trailer')
            if len(buf) < pos + number + 2:
                raise _Incomplete
            return bytes(buf[pos:pos + number]), pos + number + 2
        if depth + 1 > self.max_depth:
            raise ProtocolError('array too deep')
        if number == -1:
            return None, pos
        values = []
        for _ in range(number):
            value, pos = self._parse(pos, depth + 1)
            values.append(value)
        return values, pos
