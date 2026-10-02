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
    def array(name, count, floating=False, signed=False):
        values=[(float_value if floating else value)(name, i) for i in range(count)]
        return [n-2**32 if n>=2**31 else n for n in values] if signed else values
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
    for modern,old in {'AttackPower':'UNIT_FIELD_ATTACK_POWER','AttackPowerModPos':'UNIT_FIELD_ATTACK_POWER_MOD_POS',
        'AttackPowerModNeg':'UNIT_FIELD_ATTACK_POWER_MOD_NEG','RangedAttackPower':'UNIT_FIELD_RANGED_ATTACK_POWER',
        'RangedAttackPowerModPos':'UNIT_FIELD_RANGED_ATTACK_POWER_MOD_POS','RangedAttackPowerModNeg':'UNIT_FIELD_RANGED_ATTACK_POWER_MOD_NEG'}.items():
        n=value(old);unit[modern]=n-2**32 if n>=2**31 else n
    for modern, old in {"BoundingRadius": "UNIT_FIELD_BOUNDINGRADIUS", "CombatReach": "UNIT_FIELD_COMBATREACH",
                        "HoverHeight": "UNIT_FIELD_HOVERHEIGHT", "ModCastingSpeed": "UNIT_MOD_CAST_SPEED",
                        "ModSpellHaste": "UNIT_MOD_CAST_HASTE",
                        "MinDamage":"UNIT_FIELD_MINDAMAGE","MaxDamage":"UNIT_FIELD_MAXDAMAGE",
                        "MinOffHandDamage":"UNIT_FIELD_MINOFFHANDDAMAGE","MaxOffHandDamage":"UNIT_FIELD_MAXOFFHANDDAMAGE",
                        "MinRangedDamage":"UNIT_FIELD_MINRANGEDDAMAGE","MaxRangedDamage":"UNIT_FIELD_MAXRANGEDDAMAGE",
                        "AttackPowerMultiplier":"UNIT_FIELD_ATTACK_POWER_MULTIPLIER",
                        "RangedAttackPowerMultiplier":"UNIT_FIELD_RANGED_ATTACK_POWER_MULTIPLIER"}.items():
        unit[modern] = float_value(old)
    unit.update(Power=array("UNIT_FIELD_POWER1", 5), MaxPower=array("UNIT_FIELD_MAXPOWER1", 5),
                Stats=array("UNIT_FIELD_STAT0", 5,signed=True), StatPosBuff=array('UNIT_FIELD_POSSTAT0',5,signed=True),
                StatNegBuff=array('UNIT_FIELD_NEGSTAT0',5,signed=True),Resistances=array("UNIT_FIELD_RESISTANCES", 7,signed=True),
                ResistanceBuffModsPositive=array('UNIT_FIELD_RESISTANCEBUFFMODSPOSITIVE',7,signed=True),
                ResistanceBuffModsNegative=array('UNIT_FIELD_RESISTANCEBUFFMODSNEGATIVE',7,signed=True),
                PowerCostModifier=array('UNIT_FIELD_POWER_COST_MODIFIER',7,signed=True),
                PowerCostMultiplier=array('UNIT_FIELD_POWER_COST_MULTIPLIER',7,floating=True),
                AttackRoundBaseTime=array("UNIT_FIELD_BASEATTACKTIME", 2)+[value('UNIT_FIELD_RANGEDATTACKTIME')])
    bytes1, bytes2 = value("UNIT_FIELD_BYTES_1"), value("UNIT_FIELD_BYTES_2")
    unit.update(StandState=bytes1 & 255, VisFlags=bytes1 >> 16 & 255, AnimTier=bytes1 >> 24 & 255,
                SheatheState=bytes2 & 255, PvpFlags=bytes2 >> 8 & 255, ShapeshiftForm=bytes2 >> 24 & 255)
    player = {"Name": character["name"], "PlayerFlags": value("PLAYER_FLAGS"),
              "NativeSex": character["gender"], "VirtualPlayerRealm": 0x01010001}
    guild = value('OBJECT_FIELD_DATA') | value('OBJECT_FIELD_DATA', 1) << 32
    if snapshot.get('kind') == 4 and guild:
        if guild >> 52 != 0x1ff or guild >> 32 & 0xfffff or not guild & 0xffffffff:
            raise ValueError('invalid native guild identity')
        unit['GuildGUID'] = [guild & 0xffffffff, (28 << 58) | (1 << 42)]
    else:
        unit['GuildGUID'] = [0, 0]
    player.update({modern: value(old) for modern, old in {
        'GuildRankID': 'PLAYER_GUILDRANK', 'GuildDeleteDate': 'PLAYER_GUILDDELETE_DATE',
        'GuildLevel': 'PLAYER_GUILDLEVEL', 'GuildTimeStamp': 'PLAYER_GUILD_TIMESTAMP'}.items()})
    player["VisibleItems"] = [{"ItemID": value("PLAYER_VISIBLE_ITEM_1_ENTRYID", i * 2)} for i in range(19)]
    active = {"XP": value("PLAYER_XP"), "NextLevelXP": value("PLAYER_NEXT_LEVEL_XP"), "MaxLevel": 85,
              "NumBackpackSlots": 16,
              "Coinage": value("PLAYER_FIELD_COINAGE") | value("PLAYER_FIELD_COINAGE", 1) << 32,
              "ProfessionSkillLine": array("PLAYER_PROFESSION_SKILL_LINE_1", 2)}
    active["RestInfo"] = [{"Threshold": value("PLAYER_REST_STATE_EXPERIENCE"),
                           "StateID": value("PLAYER_BYTES_2") >> 24},
                          {"Threshold": 0, "StateID": 2}]
    from .inventory import inventory_slots
    active["InvSlots"] = inventory_slots(native)
    skill = {}
    for modern, old in {"SkillLineID": "PLAYER_SKILL_LINEID_0", "SkillStep": "PLAYER_SKILL_STEP_0",
                        "SkillRank": "PLAYER_SKILL_RANK_0", "SkillMaxRank": "PLAYER_SKILL_MAX_RANK_0",
                        "SkillTempBonus": "PLAYER_SKILL_MODIFIER_0", "SkillPermBonus": "PLAYER_SKILL_TALENT_0"}.items():
        skill[modern] = [(value(old, i // 2) >> (i % 2 * 16)) & 65535 for i in range(128)]
    skill["SkillTempBonus"] = [n - 65536 if n > 32767 else n for n in skill["SkillTempBonus"]]
    skill["SkillStartingRank"] = skill["SkillRank"]
    active["Skill"] = skill
    packed = lambda name: [(value(name, i // 2) >> (i % 2 * 16)) & 65535 for i in range(16)]
    active["ResearchSites"] = [[n for n in packed("PLAYER_FIELD_RESEARCH_SITE_1") if n]]
    active["Research"] = [[{"ResearchProjectID": n} for n in packed("PLAYER_FIELD_RESEARCH_PROJECT_1") if n]]
    return {"ObjectData": {"EntryID": value("OBJECT_FIELD_ENTRY"), "Scale": float_value("OBJECT_FIELD_SCALE_X")},
            "UnitData": unit, "PlayerData": player, "ActivePlayerData": active}


def player_block(snapshot, character, buttons=None):
    guid, move = snapshot["guid"], snapshot["movement"]
    w = Writer().pack("B", 1).guid(guid, player_high()).pack("B", 7)
    for i in range(19):
        w.bits(i in (0, 4, 15, 17), 1)
    from .movement import modern_flags2
    w.guid(guid, player_high()).pack("IIII4fffII", move["flags"], modern_flags2(move["flags2"]), 0,
        move["time"], *move["position"], move["pitch"], 0, 0, 0).bits(0, 8)
    w.pack("9fIf17f", *move["speeds"], 0, 1, 2, 65, 1, 3, 10, 100, 90, 140, 180,
           360, 90, 270, 30, 80, 2.75, 7, .4).bits(0, 1).pack("I", 0)
    w.bits(0, 1).bits(0, 1).bits(buttons is not None, 1).flush()
    if buttons is not None:
        w.pack("I" * 180, *buttons)
    fields = Writer().pack("B", 1).raw(bytes([0, 5, 6, 255, 1]))
    for kind, values in field_values(snapshot, character).items():
        serialize(fields, kind, values, visibility=1)
    w.pack("I", len(fields.finish())).raw(fields.finish())
    return w.finish()


def create(snapshot, character, items=(), buttons=None):
    from .inventory import item_block
    blocks = [item_block(item) for item in items] + [player_block(snapshot, character, buttons)]
    data = b"".join(blocks)
    return Writer().pack("HI", snapshot["map"], len(blocks)).bits(1, 1).bits(0, 1).pack("I", len(data)).raw(data).finish()
