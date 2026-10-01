"""Ordinary self casts retain native ownership and the client's cast identity."""
from .buffer import Reader, Writer, player_high
from . import movement
from .native_objects import guid as native_guid


def packed(w, guid):
    octets = guid.to_bytes(8, "little")
    return w.pack("B", sum(bool(n) << i for i, n in enumerate(octets))).raw(bytes(n for n in octets if n))


def request(owner, body):
    r = Reader(body)
    cast = r.guid()
    misc0, misc1, spell, visual = r.unpack("iiiI")
    pitch, speed = r.unpack("ff")
    crafting = r.guid()
    # Build 60895 has one spell visual and three crafting counts. An extra
    # zero visual used to hide the error by consuming a zero crafting count.
    currencies, reagents, removed, crafting_flags = r.unpack("IIIB")
    if crafting != (0, 0) or any([currencies, reagents, removed, crafting_flags, misc1, pitch, speed]):
        raise ValueError("unsupported crafting/trajectory cast")
    flags, moving, weights, order = r.bits(5), r.bits(1), r.bits(2), r.bits(1)
    r.align()
    target_flags = r.bits(28)
    source, dest, orientation, map_id, name_len = r.bits(1), r.bits(1), r.bits(1), r.bits(1), r.bits(7)
    unit, item = r.guid(), r.guid()
    if any([source, dest, orientation, map_id, name_len, weights, order]) or item != (0, 0):
        raise ValueError("unsupported cast target")
    native_target = owner.character["guid"] if target_flags & 2 else 0
    if target_flags == 2048 and spell == 73979:
        from .gameobjects import owned_native
        native_target = owned_native(owner, Writer().guid(*unit).finish())
        from ..observation.archaeology import FINDS
        if native_target >> 32 & 0xFFFFF not in FINDS:
            raise ValueError("gather target is not an archaeology find")
    elif unit not in {(0, 0), (owner.character["guid"], player_high())} or target_flags & ~2:
        raise ValueError("unsupported or foreign cast target")
    if moving:
        state = movement.parse(r.raw(len(r.data) - r.pos), owner.character["guid"])
        name, encoded = movement.encode("CMSG_MOVE_HEARTBEAT", owner.character["guid"], state)
        owner.native.send(name, encoded)
    r.end()
    if spell <= 0 or cast[1] >> 58 != 47 or flags & 10:
        raise ValueError("invalid cast identity/flags")
    count = getattr(owner, "cast_counter", 0) % 255 + 1
    owner.cast_counter = count
    if not hasattr(owner, "casts"): owner.casts = {}
    serial = getattr(owner, "cast_serial", 0) + 1
    owner.cast_serial = serial
    server = (serial, (47 << 58) | (1 << 42) | (owner.character.get("map", 0) << 29) | (spell << 6) | 3)
    owner.casts[count] = {"guid": cast, "server_guid": server, "spell": spell,
                          "visual": visual, "native_target": native_target}
    w = Writer().pack("BiiBI", count, spell, misc0, flags, target_flags)
    if target_flags & (2 | 2048): packed(w, native_target)
    return w.finish(), spell


def response(owner, name, body):
    if name not in {"SMSG_SPELL_START", "SMSG_SPELL_GO", "SMSG_CAST_FAILED", "SMSG_SPELL_FAILURE", "SMSG_SPELL_FAILED_OTHER"}: return None
    r = Reader(body)
    if name in {"SMSG_SPELL_FAILURE", "SMSG_SPELL_FAILED_OTHER"}:
        caster = native_guid(r)
        counter, spell, reason = r.unpack("BiB"); r.end()
        cast = getattr(owner, "casts", {}).get(counter)
        if caster != owner.character["guid"] or not cast or cast["spell"] != spell: return None
        from .spell_failures import REASONS
        if reason not in REASONS: raise ValueError("unmapped native cast interruption")
        reason = REASONS[reason]
        if name == "SMSG_SPELL_FAILED_OTHER" and reason > 255:
            raise ValueError("cast interruption does not fit modern reason")
        w = Writer().guid(caster, player_high()).guid(*cast["server_guid"]).pack("iI", spell, cast["visual"])
        return w.pack("H" if name == "SMSG_SPELL_FAILURE" else "B", reason).finish()
    if name == "SMSG_CAST_FAILED":
        counter, spell, reason = r.unpack("BiB")
        cast = getattr(owner, "casts", {}).get(counter)
        if not cast or cast["spell"] != spell: return None
        args = list(r.unpack("i" * ((len(body) - r.pos) // 4)))
        r.end()
        from .spell_failures import REASONS
        if reason not in REASONS: raise ValueError("unmapped native cast failure")
        identity = cast["server_guid"] if cast.get("prepared") else cast["guid"]
        return Writer().guid(*identity).pack("iIiii", spell, cast["visual"], REASONS[reason], *(args + [0, 0])[:2]).finish()
    caster, unit = native_guid(r), native_guid(r)
    counter, spell, flags, extra, duration = r.unpack("BiIII")
    cast = getattr(owner, "casts", {}).get(counter)
    if caster != owner.character["guid"] or unit != caster or not cast or cast["spell"] != spell:
        return None
    hits, misses = [], []
    if name == "SMSG_SPELL_GO":
        hits = [r.unpack("Q")[0] for _ in range(r.unpack("B")[0])]
        if r.unpack("B")[0]: raise ValueError("missed self-cast targets are unsupported")
    target_flags, = r.unpack("I")
    target = native_guid(r) if target_flags & (2 | 2048) else 0
    source, dest = None, None
    if target_flags & 32:
        if native_guid(r): raise ValueError("transport source is unsupported")
        source = r.unpack("3f")
    if target_flags & 64:
        if native_guid(r): raise ValueError("transport destination is unsupported")
        dest = r.unpack("3f")
    permitted = {0, caster, cast.get("native_target", caster)}
    if target_flags & ~(98 | 2048) or any(g not in permitted for g in hits) or target not in permitted:
        raise ValueError("unexpected self-cast result targets")
    remaining = r.unpack("I")[0] if flags & 0x800 else None
    dest_index = r.unpack("B")[0] if dest and name == "SMSG_SPELL_GO" else 0
    immunity = r.unpack("ii") if flags & 0x4000000 else (0, 0)
    if r.pos != len(body): raise ValueError("unsupported self-cast result extensions")
    w = Writer().guid(caster, player_high()).guid(unit, player_high()).guid(*cast["server_guid"]).guid()
    # 4.3.4 calls this bit NO_GCD; the modern client uses it to identify a cast
    # initiated by its own input. Preserve the native flags and mark that origin.
    w.pack("iIIII", spell, cast["visual"], flags | 0x40000, extra, duration)
    w.pack("IfBii", 0, 0, dest_index, *immunity)
    w.pack("iB", 0, 0).guid()  # no heal prediction
    w.bits(len(hits), 16).bits(0, 16).bits(0, 16).bits(remaining is not None, 9).bits(0, 1).bits(0, 16).bits(0, 2).flush()
    w.bits(target_flags, 28).bits(source is not None, 1).bits(dest is not None, 1).bits(0, 2).bits(0, 7)
    from .gameobjects import modern_guid
    w.guid(*modern_guid(target, owner.character.get("map", 0))).guid()
    for location in [source, dest]:
        if location is not None: w.guid().pack("3f", *location)
    for hit in hits: w.guid(*modern_guid(hit, owner.character.get("map", 0)))
    if remaining is not None: w.pack("bi", 1, remaining)
    if name == "SMSG_SPELL_GO": w.bits(0, 1).flush()
    return w.finish()


def prepare(owner, body):
    """Acknowledge only a cast that the native server actually started."""
    r = Reader(body)
    caster, unit = native_guid(r), native_guid(r)
    counter, spell = r.unpack("Bi")
    cast = getattr(owner, "casts", {}).get(counter)
    if caster == unit == owner.character["guid"] and cast and cast["spell"] == spell:
        cast["prepared"] = True
        return Writer().guid(*cast["guid"]).guid(*cast["server_guid"]).finish()
    return None


def rejected(body):
    """End the client's predicted animation when an unsupported cast is rejected."""
    r = Reader(body)
    identity = r.guid()
    _, _, spell, visual = r.unpack("iiiI")
    if identity[1] >> 58 != 47 or spell <= 0: return None
    from .spell_failures import REASONS
    return Writer().guid(*identity).pack("iIiii", spell, visual, REASONS[13], 0, 0).finish()


def cancel(owner, body):
    r = Reader(body)
    cast_guid, spell = r.guid(), r.unpack("I")[0]
    r.end()
    for counter, cast in getattr(owner, "casts", {}).items():
        if cast_guid in {cast["guid"], cast["server_guid"]} and cast["spell"] == spell:
            return Writer().pack("BI", counter, spell).finish()
    raise ValueError("cancel does not match an owned cast")
