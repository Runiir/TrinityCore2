"""Translate the native active player into the pinned Classic create layout."""
import json
from pathlib import Path
import struct

from .buffer import Writer, player_high
from .fields import serialize

INDEX = json.loads(Path(__file__).with_name("native_fields.json").read_text())


def field_values(snapshot, character):
    native = snapshot["fields"]
    def value(name, offset=0):
        return native.get(INDEX[name] + offset, 0)
    def float_value(name, offset=0):
        return struct.unpack("<f", struct.pack("<I", value(name, offset)))[0]
    def array(name, count, floating=False):
        return [(float_value if floating else value)(name, i) for i in range(count)]
    identity = value("UNIT_FIELD_BYTES_0")
    unit = {"Race": identity & 255, "ClassId": identity >> 8 & 255,
            "PlayerClassId": identity >> 8 & 255, "Sex": identity >> 16 & 255,
            "DisplayPower": identity >> 24 & 255, "DisplayScale": 1.0,
            "NativeXDisplayScale": 1.0, "ModTimeRate": 1.0,
            "EffectiveLevel": value("UNIT_FIELD_LEVEL")}
    names = {"Health": "UNIT_FIELD_HEALTH", "MaxHealth": "UNIT_FIELD_MAXHEALTH",
             "DisplayID": "UNIT_FIELD_DISPLAYID", "NativeDisplayID": "UNIT_FIELD_NATIVEDISPLAYID",
             "Level": "UNIT_FIELD_LEVEL", "FactionTemplate": "UNIT_FIELD_FACTIONTEMPLATE",
             "Flags": "UNIT_FIELD_FLAGS", "Flags2": "UNIT_FIELD_FLAGS_2",
             "AuraState": "UNIT_FIELD_AURASTATE", "MountDisplayID": "UNIT_FIELD_MOUNTDISPLAYID",
             "BaseMana": "UNIT_FIELD_BASE_MANA", "BaseHealth": "UNIT_FIELD_BASE_HEALTH",
             "EmoteState": "UNIT_NPC_EMOTESTATE", "NpcFlags": "UNIT_NPC_FLAGS"}
    unit.update({modern: value(old) for modern, old in names.items()})
    for modern, old in {"BoundingRadius": "UNIT_FIELD_BOUNDINGRADIUS", "CombatReach": "UNIT_FIELD_COMBATREACH",
                        "HoverHeight": "UNIT_FIELD_HOVERHEIGHT", "ModCastingSpeed": "UNIT_MOD_CAST_SPEED",
                        "ModSpellHaste": "UNIT_MOD_CAST_HASTE"}.items():
        unit[modern] = float_value(old)
    unit.update(Power=array("UNIT_FIELD_POWER1", 5), MaxPower=array("UNIT_FIELD_MAXPOWER1", 5),
                Stats=array("UNIT_FIELD_STAT0", 5), Resistances=array("UNIT_FIELD_RESISTANCES", 7),
                AttackRoundBaseTime=array("UNIT_FIELD_BASEATTACKTIME", 2))
    bytes1, bytes2 = value("UNIT_FIELD_BYTES_1"), value("UNIT_FIELD_BYTES_2")
    unit.update(StandState=bytes1 & 255, VisFlags=bytes1 >> 16 & 255, AnimTier=bytes1 >> 24 & 255,
                SheatheState=bytes2 & 255, PvpFlags=bytes2 >> 8 & 255)
    player = {"Name": character["name"], "PlayerFlags": value("PLAYER_FLAGS"),
              "NativeSex": character["gender"], "VirtualPlayerRealm": 0x01010001}
    active = {"XP": value("PLAYER_XP"), "NextLevelXP": value("PLAYER_NEXT_LEVEL_XP"), "MaxLevel": 85,
              "Coinage": value("PLAYER_FIELD_COINAGE") | value("PLAYER_FIELD_COINAGE", 1) << 32}
    return {"ObjectData": {"EntryID": value("OBJECT_FIELD_ENTRY"), "Scale": float_value("OBJECT_FIELD_SCALE_X")},
            "UnitData": unit, "PlayerData": player, "ActivePlayerData": active}


def create(snapshot, character):
    guid, move = snapshot["guid"], snapshot["movement"]
    w = Writer().pack("B", 1).guid(guid, player_high()).pack("B", 7)
    for i in range(19):
        w.bits(i in (0, 4, 15, 17), 1)
    w.guid(guid, player_high()).pack("IIII4fffII", move["flags"], move["flags2"], 0,
        move["time"], *move["position"], move["pitch"], 0, 0, 0).bits(0, 8)
    w.pack("9fIf17f", *move["speeds"], 0, 1, 2, 65, 1, 3, 10, 100, 90, 140, 180,
           360, 90, 270, 30, 80, 2.75, 7, .4).bits(0, 1).pack("I", 0)
    w.bits(0, 3).flush()  # no scene IDs, runes or action buttons in movement trial
    fields = Writer().pack("B", 1).raw(bytes([0, 5, 6, 255, 1]))
    for kind, values in field_values(snapshot, character).items():
        serialize(fields, kind, values, visibility=1)
    w.pack("I", len(fields.finish())).raw(fields.finish())
    data = w.finish()
    return Writer().pack("HI", snapshot["map"], 1).bits(1, 1).bits(0, 1).pack("I", len(data)).raw(data).finish()
