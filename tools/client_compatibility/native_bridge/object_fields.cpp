#include "protocol.hpp"

namespace bridge
{
Value Protocol::field_values(Value const &s, Value const &c) const
{
    auto val = [&](auto name, unsigned offset = 0) { return field(s, name, offset); };
    auto arr = [&](auto name, unsigned count, bool floating = false)
    {
        Array a;
        for (unsigned i = 0; i < count; ++i)
            a.push_back(floating ? Value(float_field(s, name, i)) : Value(val(name, i)));
        return a;
    };
    auto identity = val("UNIT_FIELD_BYTES_0");
    Object unit{{"Race", identity & 255},
                {"ClassId", (identity >> 8) & 255},
                {"PlayerClassId", (identity >> 8) & 255},
                {"Sex", (identity >> 16) & 255},
                {"DisplayPower", identity >> 24},
                {"DisplayScale", 1.0},
                {"NativeXDisplayScale", 1.0},
                {"ModTimeRate", 1.0},
                {"EffectiveLevel", val("UNIT_FIELD_LEVEL")}};
    for (auto const &[modern, old] : std::initializer_list<std::pair<char const *, char const *>>{
             {"Health", "UNIT_FIELD_HEALTH"},
             {"MaxHealth", "UNIT_FIELD_MAXHEALTH"},
             {"DisplayID", "UNIT_FIELD_DISPLAYID"},
             {"NativeDisplayID", "UNIT_FIELD_NATIVEDISPLAYID"},
             {"Level", "UNIT_FIELD_LEVEL"},
             {"FactionTemplate", "UNIT_FIELD_FACTIONTEMPLATE"},
             {"Flags", "UNIT_FIELD_FLAGS"},
             {"Flags2", "UNIT_FIELD_FLAGS_2"},
             {"AuraState", "UNIT_FIELD_AURASTATE"},
             {"MountDisplayID", "UNIT_FIELD_MOUNTDISPLAYID"},
             {"BaseMana", "UNIT_FIELD_BASE_MANA"},
             {"BaseHealth", "UNIT_FIELD_BASE_HEALTH"},
             {"EmoteState", "UNIT_NPC_EMOTESTATE"},
             {"NpcFlags", "UNIT_NPC_FLAGS"}})
        unit[modern] = val(old);
    for (auto const &[modern, old] : std::initializer_list<std::pair<char const *, char const *>>{
             {"BoundingRadius", "UNIT_FIELD_BOUNDINGRADIUS"},
             {"CombatReach", "UNIT_FIELD_COMBATREACH"},
             {"HoverHeight", "UNIT_FIELD_HOVERHEIGHT"},
             {"ModCastingSpeed", "UNIT_MOD_CAST_SPEED"},
             {"ModSpellHaste", "UNIT_MOD_CAST_HASTE"}})
        unit[modern] = float_field(s, old);
    unit["Power"] = arr("UNIT_FIELD_POWER1", 5);
    unit["MaxPower"] = arr("UNIT_FIELD_MAXPOWER1", 5);
    unit["Stats"] = arr("UNIT_FIELD_STAT0", 5);
    unit["Resistances"] = arr("UNIT_FIELD_RESISTANCES", 7);
    unit["AttackRoundBaseTime"] = arr("UNIT_FIELD_BASEATTACKTIME", 2);
    auto bytes1 = val("UNIT_FIELD_BYTES_1"), bytes2 = val("UNIT_FIELD_BYTES_2");
    unit["StandState"] = bytes1 & 255;
    unit["VisFlags"] = (bytes1 >> 16) & 255;
    unit["AnimTier"] = bytes1 >> 24;
    unit["SheatheState"] = bytes2 & 255;
    unit["PvpFlags"] = (bytes2 >> 8) & 255;
    unit["ShapeshiftForm"] = bytes2 >> 24;
    Object player{{"Name", get(c, "name")},
                  {"PlayerFlags", val("PLAYER_FLAGS")},
                  {"NativeSex", get(c, "gender")},
                  {"VirtualPlayerRealm", 0x01010001}};
    Array visible;
    for (unsigned i = 0; i < 19; ++i)
        visible.push_back(Object{{"ItemID", val("PLAYER_VISIBLE_ITEM_1_ENTRYID", i * 2)}});
    player["VisibleItems"] = visible;
    Object active{{"XP", val("PLAYER_XP")},
                  {"NextLevelXP", val("PLAYER_NEXT_LEVEL_XP")},
                  {"MaxLevel", 85},
                  {"NumBackpackSlots", 16},
                  {"Coinage", static_cast<std::uint64_t>(val("PLAYER_FIELD_COINAGE")) |
                                  (static_cast<std::uint64_t>(val("PLAYER_FIELD_COINAGE", 1)) << 32)},
                  {"ProfessionSkillLine", arr("PLAYER_PROFESSION_SKILL_LINE_1", 2)}};
    Array slots;
    for (unsigned i = 0; i < 146; ++i)
        slots.push_back(Array{0, 0});
    for (unsigned old = 0; old < 86; ++old)
    {
        auto slot = old < 19 ? old : old < 23 ? old + 11 : old < 39 ? old + 12 : old + 20;
        auto native = static_cast<std::uint64_t>(val("PLAYER_FIELD_INV_SLOT_HEAD", old * 2)) |
                      (static_cast<std::uint64_t>(val("PLAYER_FIELD_INV_SLOT_HEAD", old * 2 + 1)) << 32);
        slots[slot] = inventory_guid(native);
    }
    active["InvSlots"] = slots;
    Object skill;
    for (auto const &[modern, old] : std::initializer_list<std::pair<char const *, char const *>>{
             {"SkillLineID", "PLAYER_SKILL_LINEID_0"},
             {"SkillStep", "PLAYER_SKILL_STEP_0"},
             {"SkillRank", "PLAYER_SKILL_RANK_0"},
             {"SkillMaxRank", "PLAYER_SKILL_MAX_RANK_0"},
             {"SkillTempBonus", "PLAYER_SKILL_MODIFIER_0"},
             {"SkillPermBonus", "PLAYER_SKILL_TALENT_0"}})
    {
        Array a;
        for (unsigned i = 0; i < 128; ++i)
        {
            auto n = (val(old, i / 2) >> ((i % 2) * 16)) & 65535;
            a.push_back(std::string_view(modern) == "SkillTempBonus" && n > 32767
                            ? Value(static_cast<int>(n) - 65536)
                            : Value(n));
        }
        skill[modern] = a;
    }
    skill["SkillStartingRank"] = skill["SkillRank"];
    active["Skill"] = skill;
    Array sites, projects;
    for (unsigned i = 0; i < 16; ++i)
    {
        auto site = (val("PLAYER_FIELD_RESEARCH_SITE_1", i / 2) >> ((i % 2) * 16)) & 65535;
        auto project = (val("PLAYER_FIELD_RESEARCH_PROJECT_1", i / 2) >> ((i % 2) * 16)) & 65535;
        if (site)
            sites.push_back(site);
        if (project)
            projects.push_back(Object{{"ResearchProjectID", project}});
    }
    active["ResearchSites"] = Array{sites};
    active["Research"] = Array{projects};
    return Object{{"ObjectData", Object{{"EntryID", val("OBJECT_FIELD_ENTRY")},
                                        {"Scale", float_field(s, "OBJECT_FIELD_SCALE_X")}}},
                  {"UnitData", unit},
                  {"PlayerData", player},
                  {"ActivePlayerData", active}};
}
Bytes Protocol::player_block(Value const &snapshot, Value const &character, Array const *buttons) const
{
    auto guid = integer(get(snapshot, "guid"));
    auto const &move = get(snapshot, "movement");
    Writer w;
    w.pack("B", {1}).guid(guid, player_high()).pack("B", {7});
    for (unsigned i = 0; i < 19; ++i)
        w.bits(i == 0 || i == 4 || i == 15 || i == 17, 1);
    w.guid(guid, player_high())
        .pack("IIII",
              {get(move, "flags"), modern_flags2(integer(get(move, "flags2"))), 0, get(move, "time")});
    w.pack("4f", get(move, "position").as_array()).pack("ffII", {get(move, "pitch"), 0, 0, 0}).bits(0, 8);
    w.pack("9f", get(move, "speeds").as_array())
        .pack("If17f", {0, 1, 2, 65, 1, 3, 10, 100, 90, 140, 180, 360, 90, 270, 30, 80, 2.75, 7, .4})
        .bits(0, 1)
        .pack("I", {0});
    w.bits(0, 1).bits(0, 1).bits(buttons != nullptr, 1).flush();
    if (buttons)
        w.pack("180I", *buttons);
    Writer data;
    data.pack("B", {1}).raw(Bytes{0, 5, 6, 255, 1});
    auto values = field_values(snapshot, character);
    for (auto kind : {"ObjectData", "UnitData", "PlayerData", "ActivePlayerData"})
        fields.serialize(data, kind, get(values, kind), 1);
    return w.put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
Bytes Protocol::create(Value const &snapshot, Value const &character, std::vector<Value> const &items,
                       Array const *buttons) const
{
    std::vector<Bytes> blocks;
    for (auto const &item : items)
        blocks.push_back(item_block(item));
    blocks.push_back(player_block(snapshot, character, buttons));
    return object_packet(integer(get(snapshot, "map")), blocks);
}
Bytes Protocol::item_block(Value const &snapshot) const
{
    auto val = [&](auto name, unsigned offset = 0) { return field(snapshot, name, offset); };
    auto pair = [&](auto name)
    {
        return inventory_guid(static_cast<std::uint64_t>(val(name)) |
                              (static_cast<std::uint64_t>(val(name, 1)) << 32));
    };
    auto entry = val("OBJECT_FIELD_ENTRY");
    auto kind = integer(get(snapshot, "kind"));
    Writer w;
    w.pack("B", {1})
        .guid(inventory_guid(integer(get(snapshot, "guid"))))
        .pack("B", {kind})
        .bits(0, 19)
        .pack("I", {0});
    Writer data;
    data.pack("B", {1}).raw(Bytes{0, 1});
    if (kind == 2)
        data.raw(Bytes{2});
    data.raw(Bytes{255, 1});
    fields.serialize(data, "ObjectData",
                     Object{{"EntryID", entry}, {"Scale", float_field(snapshot, "OBJECT_FIELD_SCALE_X")}}, 1);
    Object item{{"Owner", pair("ITEM_FIELD_OWNER")},
                {"ContainedIn", pair("ITEM_FIELD_CONTAINED")},
                {"Creator", pair("ITEM_FIELD_CREATOR")},
                {"GiftCreator", pair("ITEM_FIELD_GIFTCREATOR")},
                {"StackCount", val("ITEM_FIELD_STACK_COUNT")},
                {"Expiration", val("ITEM_FIELD_DURATION")},
                {"DynamicFlags", val("ITEM_FIELD_FLAGS")},
                {"Durability", val("ITEM_FIELD_DURABILITY")},
                {"MaxDurability", val("ITEM_FIELD_MAXDURABILITY")},
                {"CreatePlayedTime", val("ITEM_FIELD_CREATE_PLAYED_TIME")},
                {"PropertySeed", static_cast<std::int32_t>(val("ITEM_FIELD_PROPERTY_SEED"))},
                {"RandomPropertiesID", static_cast<std::int32_t>(val("ITEM_FIELD_RANDOM_PROPERTIES_ID"))},
                {"ItemBonusKey", Object{{"ItemID", entry}}}};
    Array charges;
    for (unsigned i = 0; i < 5; ++i)
        charges.push_back(static_cast<std::int32_t>(val("ITEM_FIELD_SPELL_CHARGES", i)));
    item["SpellCharges"] = charges;
    Array enchants;
    for (unsigned i = 0; i < 13; ++i)
        enchants.push_back(Object{{"ID", val("ITEM_FIELD_ENCHANTMENT_1_1", i * 3)},
                                  {"Duration", val("ITEM_FIELD_ENCHANTMENT_1_1", i * 3 + 1)},
                                  {"Charges", val("ITEM_FIELD_ENCHANTMENT_1_1", i * 3 + 2) & 65535}});
    item["Enchantment"] = enchants;
    fields.serialize(data, "ItemData", item, 1);
    if (kind == 2)
    {
        Array slots;
        for (unsigned i = 0; i < 36; ++i)
            slots.push_back(
                inventory_guid(static_cast<std::uint64_t>(val("CONTAINER_FIELD_SLOT_1", i * 2)) |
                               (static_cast<std::uint64_t>(val("CONTAINER_FIELD_SLOT_1", i * 2 + 1)) << 32)));
        fields.serialize(data, "ContainerData",
                         Object{{"NumSlots", val("CONTAINER_FIELD_NUM_SLOTS")}, {"Slots", slots}}, 1);
    }
    return w.put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
Bytes Protocol::gameobject_block(Value const &s) const
{
    if (integer(get(s, "kind")) != 5)
        throw std::runtime_error("expected a native game object");
    auto const &m = get(s, "movement");
    auto map = integer(get(s, "map"));
    auto val = [&](auto n, unsigned i = 0) { return field(s, n, i); };
    Writer w;
    w.pack("B", {1}).guid(modern_guid(integer(get(s, "guid")), map)).pack("B", {8});
    for (unsigned i = 0; i < 19; ++i)
        w.bits(i == 0 || i == 6 || i == 11 || i == 13, 1);
    w.pack("I", {0})
        .pack("4f", get(m, "position").as_array())
        .pack("Q", {get(m, "rotation")})
        .pack("I", {0})
        .bits(0, 3)
        .flush();
    Writer data;
    data.pack("B", {0}).raw(Bytes{0, 7, 255, 1});
    fields.serialize(
        data, "ObjectData",
        Object{{"EntryID", val("OBJECT_FIELD_ENTRY")}, {"Scale", float_field(s, "OBJECT_FIELD_SCALE_X")}}, 0);
    auto identity = val("GAMEOBJECT_BYTES_1");
    auto creator = static_cast<std::uint64_t>(val("OBJECT_FIELD_CREATED_BY")) |
                   (static_cast<std::uint64_t>(val("OBJECT_FIELD_CREATED_BY", 1)) << 32);
    Object rotation;
    unsigned i = 0;
    for (auto n : {"x", "y", "z", "w"})
        rotation[n] = float_field(s, "GAMEOBJECT_PARENTROTATION", i++);
    fields.serialize(data, "GameObjectData",
                     Object{{"DisplayID", val("GAMEOBJECT_DISPLAYID")},
                            {"CreatedBy", modern_guid(creator, map)},
                            {"Flags", val("GAMEOBJECT_FLAGS")},
                            {"ParentRotation", rotation},
                            {"FactionTemplate", val("GAMEOBJECT_FACTION")},
                            {"Level", val("GAMEOBJECT_LEVEL")},
                            {"State", identity & 255},
                            {"TypeID", (identity >> 8) & 255},
                            {"ArtKit", (identity >> 16) & 255},
                            {"PercentHealth", 100}},
                     0);
    return w.put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
Bytes Protocol::unit_block(Value const &s, Value const &character) const
{
    auto const &m = get(s, "movement");
    auto identity = modern_guid(integer(get(s, "guid")), integer(get(s, "map")));
    Writer w;
    w.pack("B", {1}).guid(identity).pack("B", {5});
    for (unsigned i = 0; i < 19; ++i)
        w.bits(i == 0 || i == 4, 1);
    w.guid(identity).pack("IIII",
                          {get(m, "flags"), modern_flags2(integer(get(m, "flags2"))), 0, get(m, "time")});
    w.pack("4f", get(m, "position").as_array()).pack("ffII", {get(m, "pitch"), 0, 0, 0}).bits(0, 8);
    w.pack("9f", get(m, "speeds").as_array())
        .pack("If17f", {0, 1, 2, 65, 1, 3, 10, 100, 90, 140, 180, 360, 90, 270, 30, 80, 2.75, 7, .4})
        .bits(0, 1)
        .pack("I", {0});
    Writer data;
    data.pack("B", {0}).raw(Bytes{0, 5, 255, 1});
    auto values = field_values(s, character);
    for (auto kind : {"ObjectData", "UnitData"})
        fields.serialize(data, kind, get(values, kind), 0);
    return w.put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
Bytes Protocol::scalar_block(Value const &s, Value const &character, Value const &changed,
                             unsigned visibility) const
{
    struct Scalar
    {
        char const *name;
        unsigned index;
        char fmt;
        char const *native;
    };
    static Scalar const specs[] = {{"Health", 5, 'q', "UNIT_FIELD_HEALTH"},
                                   {"MaxHealth", 6, 'q', "UNIT_FIELD_MAXHEALTH"},
                                   {"DisplayID", 7, 'i', "UNIT_FIELD_DISPLAYID"},
                                   {"Flags", 41, 'I', "UNIT_FIELD_FLAGS"},
                                   {"Flags2", 42, 'I', "UNIT_FIELD_FLAGS_2"},
                                   {"MountDisplayID", 52, 'i', "UNIT_FIELD_MOUNTDISPLAYID"},
                                   {"StandState", 57, 'B', "UNIT_FIELD_BYTES_1"},
                                   {"VisFlags", 59, 'B', "UNIT_FIELD_BYTES_1"},
                                   {"AnimTier", 60, 'B', "UNIT_FIELD_BYTES_1"},
                                   {"SheatheState", 78, 'B', "UNIT_FIELD_BYTES_2"},
                                   {"PvpFlags", 79, 'B', "UNIT_FIELD_BYTES_2"},
                                   {"ShapeshiftForm", 81, 'B', "UNIT_FIELD_BYTES_2"}};
    std::array<std::uint32_t, 8> masks{};
    std::vector<Scalar> selected;
    for (auto const &spec : specs)
        if (changed.as_object().contains(std::to_string(field_index(spec.native))))
        {
            selected.push_back(spec);
            masks[spec.index / 32] |= (1u << (spec.index % 32)) | 1;
        }
    if (selected.empty())
        return {};
    Writer data;
    data.pack("BBBI", {visibility, 0, 3, 1u << 5});
    unsigned presence = 0;
    for (unsigned i = 0; i < 8; ++i)
        if (masks[i])
            presence |= 1u << i;
    data.bits(presence, 8);
    for (auto mask : masks)
        if (mask)
            data.bits(mask, 32);
    data.flush();
    auto values = field_values(s, character);
    auto const &unit = get(values, "UnitData");
    for (auto const &spec : selected)
        data.pack(std::string(1, spec.fmt), {get(unit, spec.name)});
    return Writer()
        .pack("B", {0})
        .guid(modern_guid(integer(get(s, "guid")), integer(get(s, "map"))))
        .put<std::uint32_t>(data.data().size())
        .raw(data.data())
        .finish();
}
} // namespace bridge
