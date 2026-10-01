"""Translate native currency counts; all amounts remain server authoritative."""
from .buffer import Reader, Writer


def translate(name, body):
    if name == "SMSG_SETUP_CURRENCY":
        r = Reader(body)
        count = r.bits(23)
        if count > 1024: raise ValueError("currency count exceeds bound")
        flags = [(r.bits(1), r.bits(4), r.bits(1), r.bits(1)) for _ in range(count)]
        w = Writer().pack("I", count)
        for weekly, flag, maximum, tracked in flags:
            quantity, = r.unpack("I")
            max_value = r.unpack("I")[0] if maximum else None
            tracked_value = r.unpack("I")[0] if tracked else None
            kind, = r.unpack("I")
            weekly_value = r.unpack("I")[0] if weekly else None
            w.pack("ii", kind, quantity).bits(weekly, 1).bits(maximum, 1).bits(tracked, 1).bits(0, 4).bits(flag, 5).flush()
            for value in [weekly_value, max_value, tracked_value]:
                if value is not None: w.pack("I", value)
        r.end()
        return w.finish()
    if name == "SMSG_SET_CURRENCY":
        r = Reader(body)
        weekly, tracked, suppress = r.bits(1), r.bits(1), r.bits(1)
        tracked_value = r.unpack("i")[0] if tracked else None
        quantity, kind = r.unpack("ii")
        weekly_value = r.unpack("i")[0] if weekly else None
        r.end()
        w = Writer().pack("iiII", kind, quantity, 0, 0)
        for value in [weekly, tracked, 0, 0, suppress, 0, 0, 0, 0, 0, 0, 0]: w.bits(value, 1)
        w.flush()
        for value in [weekly_value, tracked_value]:
            if value is not None: w.pack("i", value)
        return w.finish()
    return None
