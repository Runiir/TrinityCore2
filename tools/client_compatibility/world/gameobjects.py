"""Render only game objects the native session actually made visible."""
import struct

from .buffer import Writer, player_high
from .fields import serialize
from .objects import INDEX


def modern_guid(native, map_id):
    if not native: return (0, 0)
    high = native >> 52
    if high == 0: return native, player_high()
    types = {0xF11: 11, 0xF13: 8, 0xF14: 10, 0xF15: 9}
    if high not in types: raise ValueError("unsupported visible-object identity")
    entry = native >> 32 & 0xFFFFF
    return native & 0xFFFFFFFF, (types[high] << 58) | (1 << 42) | (map_id << 29) | (entry << 6)


def block(snapshot):
    if snapshot["kind"] != 5: raise ValueError("expected a native game object")
    native, m, map_id = snapshot["fields"], snapshot["movement"], snapshot["map"]
    val = lambda name, i=0: native.get(INDEX[name] + i, 0)
    fval = lambda name, i=0: struct.unpack("<f", struct.pack("<I", val(name, i)))[0]
    identity = modern_guid(snapshot["guid"], map_id)
    w = Writer().pack("B", 1).guid(*identity).pack("B", 8)
    for i in range(19): w.bits(i in (0, 6, 11, 13), 1)
    w.pack("I4fQ", 0, *m["position"], m.get("rotation", 0))
    w.pack("I", 0).bits(0, 3).flush()  # ordinary GO, no transport/path extras
    data = Writer().pack("B", 0).raw(bytes([0, 7, 255, 1]))
    serialize(data, "ObjectData", {"EntryID": val("OBJECT_FIELD_ENTRY"), "Scale": fval("OBJECT_FIELD_SCALE_X")}, 0)
    bytefields = val("GAMEOBJECT_BYTES_1")
    created = val("OBJECT_FIELD_CREATED_BY") | val("OBJECT_FIELD_CREATED_BY", 1) << 32
    serialize(data, "GameObjectData", {"DisplayID": val("GAMEOBJECT_DISPLAYID"),
        "CreatedBy": modern_guid(created, map_id), "Flags": val("GAMEOBJECT_FLAGS"),
        "ParentRotation": dict(zip("xyzw", [fval("GAMEOBJECT_PARENTROTATION", i) for i in range(4)])),
        "FactionTemplate": val("GAMEOBJECT_FACTION"), "Level": val("GAMEOBJECT_LEVEL"),
        "State": bytefields & 255, "TypeID": bytefields >> 8 & 255,
        "ArtKit": bytefields >> 16 & 255, "PercentHealth": 100}, 0)
    w.pack("I", len(data.finish())).raw(data.finish())
    return w.finish()


def packet(map_id, blocks=(), removed=(), destroyed=()):
    data = b"".join(blocks)
    w = Writer().pack("HI", map_id, len(blocks)).bits(1, 1).bits(bool(removed or destroyed), 1)
    if removed or destroyed:
        w.pack("HI", len(destroyed), len(removed) + len(destroyed))
        for guid in [*destroyed, *removed]: w.guid(*modern_guid(guid, map_id))
    return w.pack("I", len(data)).raw(data).finish()


def destroy(owner, body):
    from .buffer import Reader
    r = Reader(body)
    native, dead = r.unpack("QB"); r.end()
    record = getattr(owner, "visible_gameobjects", {}).pop(native, None)
    if not record: record = getattr(owner, 'visible_units', {}).pop(native, None)
    if not record: return None
    if getattr(owner, 'taxi_menu', None) and owner.taxi_menu['vendor'] == native: owner.taxi_menu = None
    if getattr(owner, 'gossip_menu', None) and owner.gossip_menu['guid'] == native: owner.gossip_menu = None
    return packet(record["map"], destroyed=[native])


def updates(owner, body):
    from .native_objects import records
    blocks, removed = [], []
    if not hasattr(owner, "visible_gameobjects"): owner.visible_gameobjects = {}
    map_id = owner.character["map"]
    for record in records(body):
        map_id = record["map"]
        if record["update_type"] == 3:
            for guid in record["removed"]:
                if guid in owner.visible_gameobjects:
                    removed.append(guid)
                    del owner.visible_gameobjects[guid]
        elif record.get("kind") == 5 and record["guid"] >> 52 == 0xF11:
            blocks.append(block(record))
            owner.visible_gameobjects[record["guid"]] = record
    return packet(map_id, blocks, removed) if blocks or removed else None


def owned_native(owner, body):
    from .buffer import Reader
    r = Reader(body); target = r.guid(); r.end()
    for native, record in getattr(owner, "visible_gameobjects", {}).items():
        if target == modern_guid(native, record["map"]):
            return native
    raise ValueError("game object is not visible to the native character")
