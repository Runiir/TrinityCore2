"""Read native object snapshots. Unsupported movement layouts fail explicitly."""
from .buffer import Reader


def guid(r):
    mask, = r.unpack("B")
    return sum((r.raw(1)[0] if mask & 1 << i else 0) << (i * 8) for i in range(8))


def values(r):
    count, = r.unpack("B")
    masks = r.unpack("I" * count)
    return {i * 32 + bit: r.unpack("I")[0]
            for i, mask in enumerate(masks) for bit in range(32) if mask & (1 << bit)}


def movement(r):
    names = ["hover", "greeting", "rotation", "animkit", "victim", "self", "vehicle", "movement"]
    f = {name: r.bits(1) for name in names}
    pauses = r.bits(24)
    f.update({name: r.bits(1) for name in ["birth", "transport", "stationary", "area", "portals", "time"]})
    if f["transport"] or f["victim"] or f["animkit"]:
        raise ValueError("unsupported native object transport/victim/animkit")
    m = {"flags": 0, "flags2": 0, "position": (0, 0, 0, 0), "pitch": 0, "time": 0}
    if f["movement"]:
        no_flags, no_o = r.bits(1), r.bits(1)
        present = {i: r.bits(1) for i in [7, 3, 2]}
        if not no_flags: m["flags"] = r.bits(30)
        npc_spline, no_pitch, spline, fall, no_elevation = [r.bits(1) for _ in range(5)]
        present[5] = r.bits(1)
        transport, no_time = r.bits(1), r.bits(1)
        if transport or spline:
            raise ValueError("unsupported native object spline/transport")
        present[4], present[6] = r.bits(1), r.bits(1)
        fall_direction = r.bits(1) if fall else False
        present[0], present[1] = r.bits(1), r.bits(1)
        r.bits(1)
        if not r.bits(1): m["flags2"] = r.bits(12)
        def octet(i):
            if present[i]: r.raw(1)
        r.align()
        r.raw(pauses * 4)
        octet(4)
        run_back, = r.unpack("f")
        if fall:
            if fall_direction: r.raw(12)
            r.raw(8)
        swim_back, = r.unpack("f")
        if not no_elevation: r.raw(4)
        z, = r.unpack("f"); octet(5)
        x, pitch_rate = r.unpack("ff"); octet(3); octet(0)
        swim, y = r.unpack("ff"); octet(7); octet(1); octet(2)
        walk, = r.unpack("f")
        if not no_time: m["time"], = r.unpack("I")
        turn_rate, = r.unpack("f"); octet(6)
        flight, = r.unpack("f")
        orientation = r.unpack("f")[0] if not no_o else 0
        run, = r.unpack("f")
        if not no_pitch: m["pitch"], = r.unpack("f")
        flight_back, = r.unpack("f")
        m.update(position=(x, y, z, orientation), speeds=(walk, run, run_back, swim, swim_back, flight, flight_back, turn_rate, pitch_rate))
    else:
        r.align(); r.raw(pauses * 4)
    if f["vehicle"]: r.raw(8)
    if f["rotation"]: r.raw(8)
    if f["area"]: r.raw(65)
    if f["stationary"]:
        o, x, y, z = r.unpack("4f"); m["position"] = (x, y, z, o)
    if f["time"]: r.raw(4)
    return m, f


def find_self(data, wanted):
    r = Reader(data)
    map_id, count = r.unpack("HI")
    for _ in range(count):
        update_type, = r.unpack("B")
        if update_type == 3:
            for _ in range(r.unpack("I")[0]): guid(r)
            continue
        object_guid = guid(r)
        if update_type == 0:
            values(r)
            continue
        if update_type not in (1, 2):
            raise ValueError("unsupported native object update type")
        kind, = r.unpack("B")
        move, flags = movement(r)
        fields = values(r)
        if object_guid == wanted and kind == 4 and flags["self"]:
            return {"guid": object_guid, "map": map_id, "movement": move, "fields": fields}
    return None
