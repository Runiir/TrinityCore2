"""Game-object templates come from the same native session as their creates."""
from .buffer import Reader, Writer
from . import gameobjects


def request(owner, body):
    r = Reader(body)
    entry, = r.unpack("I")
    identity = r.guid(); r.end()
    native = gameobjects.owned_native(owner, Writer().guid(*identity).finish())
    if entry != native >> 32 & 0xFFFFF: raise ValueError("game-object template identity mismatch")
    if not hasattr(owner, "gameobject_queries"): owner.gameobject_queries = {}
    owner.gameobject_queries.setdefault(entry, []).append(identity)
    return Writer().pack("IQ", entry, native).finish()


def response(owner, body):
    r = Reader(body)
    marker, = r.unpack("I")
    entry, allow = marker & 0x7FFFFFFF, not marker & 0x80000000
    pending = getattr(owner, "gameobject_queries", {}).get(entry, [])
    if not pending: return None
    identity = pending.pop(0)
    stats = Writer()
    if allow:
        stats.raw(r.raw(8))  # native type and display
        for _ in range(7):
            terminator = body.find(b"\x00", r.pos)
            if terminator < 0 or terminator - r.pos > 4096: raise ValueError("invalid game-object query string")
            stats.raw(r.raw(terminator - r.pos + 1))
        stats.raw(r.raw(32 * 4)).raw(bytes(3 * 4))  # Classic has 35 data fields
        stats.raw(r.raw(4))
        quest_items = [n for n in r.unpack("6I") if n]
        stats.pack("B", len(quest_items)).pack("I" * len(quest_items), *quest_items)
        r.unpack("i")  # native RequiredLevel has no ContentTuningID equivalent
        stats.pack("i", 0)
    r.end()
    return Writer().pack("I", entry).guid(*identity).bits(allow, 1).pack("I", len(stats.finish())).raw(stats.finish()).finish()
