"""Ongoing native player fields, including mount display and mounted state."""
from .buffer import Writer, player_high
from .objects import INDEX, field_values
from .native_objects import records
from .gameobjects import packet

# Indices and group bits in the pinned UnitData::WriteUpdate serializer.
SCALARS = {"Health": (5, "q", "UNIT_FIELD_HEALTH"), "MaxHealth": (6, "q", "UNIT_FIELD_MAXHEALTH"),
    "DisplayID": (7, "i", "UNIT_FIELD_DISPLAYID"), "Flags": (41, "I", "UNIT_FIELD_FLAGS"),
    "Flags2": (42, "I", "UNIT_FIELD_FLAGS_2"), "MountDisplayID": (52, "i", "UNIT_FIELD_MOUNTDISPLAYID"),
    "StandState": (57, "B", "UNIT_FIELD_BYTES_1"), "VisFlags": (59, "B", "UNIT_FIELD_BYTES_1"),
    "AnimTier": (60, "B", "UNIT_FIELD_BYTES_1"), "SheatheState": (78, "B", "UNIT_FIELD_BYTES_2"),
    "PvpFlags": (79, "B", "UNIT_FIELD_BYTES_2"), "ShapeshiftForm": (81, "B", "UNIT_FIELD_BYTES_2")}


def updates(owner, body):
    if not hasattr(owner, "self_snapshot"): return None
    blocks = []
    for record in records(body):
        if record["update_type"] != 0 or record["guid"] != owner.character["guid"]: continue
        snapshot = owner.self_snapshot
        changed = record["fields"]
        snapshot["fields"].update(changed)
        unit = field_values(snapshot, owner.character)["UnitData"]
        selected = {name: spec for name, spec in SCALARS.items() if INDEX[spec[2]] in changed}
        if not selected: continue
        masks = [0] * 8
        for index, _, _ in selected.values():
            masks[index // 32] |= (1 << (index % 32)) | 1
        fields = Writer().pack("BBBI", 1, 0, 3, 1 << 5)  # owner, same fragments, CGObject active + changed, Unit type
        fields.bits(sum(bool(m) << i for i, m in enumerate(masks)), 8)
        for mask in masks:
            if mask: fields.bits(mask, 32)
        fields.flush()
        for name, (_, fmt, _) in sorted(selected.items(), key=lambda pair: pair[1][0]):
            fields.pack(fmt, unit[name])
        data = fields.finish()
        blocks.append(Writer().pack("B", 0).guid(owner.character["guid"], player_high()).pack("I", len(data)).raw(data).finish())
    return packet(owner.character["map"], blocks) if blocks else None
