"""Read native object snapshots. Unsupported movement layouts fail explicitly."""
from .buffer import Reader
from .native_transport import Transport


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
    m = {"flags": 0, "flags2": 0, "position": (0, 0, 0, 0), "pitch": 0, "time": 0}
    if f["movement"]:
        no_flags, no_o = r.bits(1), r.bits(1)
        present = {i: r.bits(1) for i in [7, 3, 2]}
        if not no_flags: m["flags"] = r.bits(30)
        npc_spline, no_pitch, spline, fall, no_elevation = [r.bits(1) for _ in range(5)]
        present[5] = r.bits(1)
        transport, no_time = r.bits(1), r.bits(1)
        unit_transport=Transport(r) if transport else None
        present[4] = r.bits(1)
        spline_info = None
        if spline:
            spline_info = {"active": r.bits(1)}
            if spline_info["active"]:
                r.bits(2)
                spline_info.update(effect=r.bits(1), nodes=r.bits(22), facing=r.bits(2))
                if spline_info["nodes"] > 10000: raise ValueError("native spline exceeds bound")
                if spline_info["facing"] == 2:
                    spline_info["target"] = [r.bits(1) for _ in range(8)]
                spline_info["acceleration"] = r.bits(1)
                r.bits(25)
        present[6] = r.bits(1)
        fall_direction = r.bits(1) if fall else False
        present[0], present[1] = r.bits(1), r.bits(1)
        r.bits(1)
        if not r.bits(1): m["flags2"] = r.bits(12)
        def octet(i):
            if present[i]: r.raw(1)
    go_transport=Transport(r,gameobject=True) if f['transport'] else None
    victim = [r.bits(1) for _ in range(8)] if f["victim"] else []
    animkits = [not r.bits(1) for _ in range(3)] if f["animkit"] else []
    r.align()
    if pauses > 10000: raise ValueError("native pause times exceed bound")
    r.raw(pauses * 4)
    if f["movement"]:
        octet(4)
        run_back, = r.unpack("f")
        if fall:
            if fall_direction: r.raw(12)
            r.raw(8)
        swim_back, = r.unpack("f")
        if not no_elevation: r.raw(4)
        if spline:
            if spline_info["active"]:
                if spline_info["acceleration"]: r.raw(4)
                r.raw(4)
                if spline_info["facing"] == 0: r.raw(4)
                if spline_info["facing"] == 2: r.raw(sum(spline_info["target"]))
                r.raw(spline_info["nodes"] * 12)
                if spline_info["facing"] == 1: r.raw(12)
                r.raw(8)
                if spline_info["effect"]: r.raw(4)
                r.raw(4)
            r.raw(16)
        z, = r.unpack("f"); octet(5)
        if unit_transport:m['transport']=unit_transport.read(r)
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
    if f["vehicle"]:
        facing,vehicle=r.unpack('fI');m['vehicle']={'id':vehicle,'facing':facing}
    if go_transport:m['transport']=go_transport.read(r)
    if f["rotation"]: m["rotation"], = r.unpack("Q")
    if f["area"]: r.raw(65)
    if f["stationary"]:
        o, x, y, z = r.unpack("4f"); m["position"] = (x, y, z, o)
    r.raw(sum(victim))
    r.raw(sum(animkits) * 2)
    if f["time"]: r.raw(4)
    return m, f


def player_bundle(data, wanted):
    r = Reader(data)
    map_id, count = r.unpack("HI")
    items = []
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
        snapshot = {"guid": object_guid, "map": map_id, "movement": move, "fields": fields, "kind": kind}
        if kind in (1, 2):
            items.append(snapshot)
        if object_guid == wanted and kind == 4 and flags["self"]:
            return snapshot, items
    return None, []


def find_self(data, wanted):
    return player_bundle(data, wanted)[0]


def records(data):
    r = Reader(data)
    map_id, count = r.unpack("HI")
    if count > 10000: raise ValueError("native update count exceeds bound")
    result = []
    for _ in range(count):
        update_type, = r.unpack("B")
        if update_type == 3:
            removed_count, = r.unpack("I")
            if removed_count > 10000: raise ValueError("native removal count exceeds bound")
            result.append({"update_type": 3, "removed": [guid(r) for _ in range(removed_count)], "map": map_id})
            continue
        object_guid = guid(r)
        record = {"guid": object_guid, "map": map_id, "update_type": update_type}
        if update_type in (1, 2):
            record["kind"], = r.unpack("B")
            record["movement"], record["flags"] = movement(r)
        elif update_type != 0:
            raise ValueError("unsupported native object update type")
        record["fields"] = values(r)
        result.append(record)
    r.end()
    return result
