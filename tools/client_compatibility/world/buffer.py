"""Trinity-compatible little-endian values and MSB-first bit fields."""
import struct


class Writer:
    def __init__(self):
        self.data = bytearray()
        self.bit = 0

    def bits(self, value, width):
        if not 0 <= int(value) < 1 << width:
            raise ValueError("bit field overflow")
        for shift in range(width - 1, -1, -1):
            if self.bit == 0:
                self.data.append(0)
            self.data[-1] |= ((int(value) >> shift) & 1) << (7 - self.bit)
            self.bit = (self.bit + 1) % 8
        return self

    def flush(self):
        self.bit = 0
        return self

    def raw(self, value):
        self.flush()
        self.data.extend(value)
        return self

    def pack(self, fmt, *values):
        return self.raw(struct.pack("<" + fmt, *values))

    def guid(self, low=0, high=0):
        octets = struct.pack("<QQ", low, high)
        self.pack("H", sum(bool(value) << index for index, value in enumerate(octets)))
        return self.raw(bytes(value for value in octets if value))

    def finish(self):
        self.flush()
        return bytes(self.data)


class Reader:
    def __init__(self, data):
        self.data, self.pos, self.bit = data, 0, 0

    def bits(self, width):
        value = 0
        for _ in range(width):
            if self.pos >= len(self.data):
                raise ValueError("truncated bit field")
            value = value * 2 + ((self.data[self.pos] >> (7 - self.bit)) & 1)
            self.bit += 1
            if self.bit == 8:
                self.bit, self.pos = 0, self.pos + 1
        return value

    def align(self):
        if self.bit:
            self.pos += 1
            self.bit = 0

    def raw(self, count):
        self.align()
        if count < 0 or self.pos + count > len(self.data):
            raise ValueError("truncated value")
        result = self.data[self.pos:self.pos + count]
        self.pos += count
        return result

    def unpack(self, fmt):
        return struct.unpack("<" + fmt, self.raw(struct.calcsize("<" + fmt)))

    def guid(self):
        mask, = self.unpack("H")
        octets = bytes(self.raw(1)[0] if mask & (1 << i) else 0 for i in range(16))
        return struct.unpack("<QQ", octets)

    def end(self):
        self.align()
        if self.pos != len(self.data):
            raise ValueError("unexpected trailing bytes")


def player_high():
    return (2 << 58) | (1 << 42)
