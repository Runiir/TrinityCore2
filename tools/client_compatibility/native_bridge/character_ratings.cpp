#include "character_ratings.hpp"
#include <algorithm>

namespace bridge
{
namespace
{
struct Stat { char const *native; char const *modern; unsigned bit; bool native_float; char format='f'; };
constexpr Stat stats[] = {
    {"PLAYER_EXPERTISE", "MainhandExpertise", 41, false},
    {"PLAYER_OFFHAND_EXPERTISE", "OffhandExpertise", 42, false},
    {"PLAYER_BLOCK_PERCENTAGE", "BlockPercentage", 45, true},
    {"PLAYER_DODGE_PERCENTAGE", "DodgePercentage", 46, true},
    {"PLAYER_PARRY_PERCENTAGE", "ParryPercentage", 48, true},
    {"PLAYER_SHIELD_BLOCK", "ShieldBlock", 53, false, 'i'},
    {"PLAYER_MASTERY", "Mastery", 55, true}};
// Unit.h26 slots versus installed Cata PaperDollFrame.lua32-slot schema.
// Obsolete defense/weapon-skill/armor-penetration slots and repurposed
// corruption/speed/avoidance/sturdiness slots have no Cataclysm mapping.
constexpr unsigned supported[] = {2,3,4,5,6,7,8,9,10,14,15,17,18,19,23,25};
Value value(Protocol const &p, Value const &s, Stat const &spec)
{
    if (spec.native_float) return p.float_field(s,spec.native);
    if (spec.format=='i') return static_cast<std::int32_t>(p.field(s,spec.native));
    return static_cast<double>(p.field(s,spec.native));
}
}
void rating_creation(Protocol const &p, Value const &s, Object &unit, Object &active)
{
    for (auto const &[modern,native] : std::initializer_list<std::pair<char const*,char const*>>{
        {"ModHaste","PLAYER_FIELD_MOD_HASTE"},
        {"ModRangedHaste","PLAYER_FIELD_MOD_RANGED_HASTE"},
        {"ModHasteRegen","PLAYER_FIELD_MOD_HASTE_REGEN"}})
    {
        bool present=get(s,"fields").as_object().contains(std::to_string(p.field_index(native)));
        unit[modern]=present ? p.float_field(s,native) : 1.0;
    }
    for (auto const &spec : stats) active[spec.modern]=value(p,s,spec);
    Array ratings(32,Value(0));
    for (auto index : supported)
        ratings[index]=static_cast<std::int32_t>(p.field(s,"PLAYER_FIELD_COMBAT_RATING_1",index));
    active["CombatRatings"]=ratings;
}
void rating_changes(Protocol const &p, Value const &s, Value const &changed, CombatChanges &result)
{
    auto has=[&](char const *name,unsigned i=0)
    {return changed.as_object().contains(std::to_string(p.field_index(name)+i));};
    for (auto const &spec : stats)
        if (has(spec.native)) result.scalars[spec.bit]={spec.format,value(p,s,spec)};
    for (auto index : supported)
        if (has("PLAYER_FIELD_COMBAT_RATING_1",index))
            result.ratings[index]=static_cast<std::int32_t>(p.field(s,"PLAYER_FIELD_COMBAT_RATING_1",index));
}
}
