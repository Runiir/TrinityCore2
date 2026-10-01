"""Visible native auras on the owned player, using the 60895 Cata layout."""
from .buffer import Reader, Writer, player_high
from .native_objects import guid


def response(owner, name, body):
    if name not in {"SMSG_AURA_UPDATE", "SMSG_AURA_UPDATE_ALL"}: return None
    r = Reader(body)
    unit = guid(r)
    if unit != owner.character["guid"]: return None
    entries = []
    while r.pos < len(body):
        slot, spell = r.unpack("Bi")
        entry = {"slot": slot, "spell": spell}
        if spell > 0:
            flags, level, applications = r.unpack("HBB")
            caster = unit if flags & 8 else guid(r)
            duration = r.unpack("ii") if flags & 32 else None
            points = [r.unpack("i")[0] for bit in (1, 2, 4) if flags & 64 and flags & bit]
            entry.update(flags=flags, level=level, applications=applications, caster=caster,
                         duration=duration, points=points)
        entries.append(entry)
    r.end()
    if len(entries) > 255: raise ValueError("excessive native aura count")
    if name.endswith("_ALL") or not hasattr(owner, "visible_auras"): owner.visible_auras = {}
    w = Writer().bits(name.endswith("_ALL"), 1).bits(len(entries), 9).flush()
    for entry in entries:
        slot, spell = entry["slot"], entry["spell"]
        w.pack("B", slot).bits(spell > 0, 1).flush()
        if spell <= 0:
            owner.visible_auras.pop(slot, None)
            continue
        owner.visible_auras[slot] = entry
        flags = entry["flags"]
        modern_flags = (1 if entry["caster"] == unit else 0) | (0x102 if flags & 16 else 0)
        modern_flags |= (4 if flags & 32 else 0) | (8 if flags & 64 else 0) | (16 if flags & 128 else 0)
        # An aura has a distinct server identity even when loaded from the database.
        owner.aura_serial = getattr(owner, "aura_serial", 0) + 1
        high = (47 << 58) | (1 << 42) | (owner.character["map"] << 29) | (spell << 6) | 13
        w.guid(owner.aura_serial, high).pack("iiHIHBi", spell, 0, modern_flags,
            flags & 7, entry["level"], entry["applications"], 0)
        known_caster = entry["caster"] in (0, unit)
        has_caster = known_caster and entry["caster"] != unit
        duration = entry["duration"]
        w.bits(has_caster, 1).bits(duration is not None, 1).bits(duration is not None, 1)
        w.bits(0, 1).bits(len(entry["points"]), 6).bits(0, 6).bits(0, 1).flush()
        if has_caster: w.guid()
        if duration: w.pack("ii", *duration)
        for point in entry["points"]: w.pack("f", point)
    return "SMSG_AURA_UPDATE", w.guid(unit, player_high()).finish()


def cancel(owner, body):
    r = Reader(body)
    spell, = r.unpack("I")
    caster = r.guid()
    r.end()
    if caster not in {(0, 0), (owner.character["guid"], player_high())}:
        raise ValueError("aura cancellation caster is not owned")
    if not any(a["spell"] == spell for a in getattr(owner, "visible_auras", {}).values()):
        raise ValueError("aura cancellation is not visible")
    return Writer().pack("I", spell).finish()
