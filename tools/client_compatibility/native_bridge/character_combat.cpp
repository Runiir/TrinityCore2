#include "character_combat.hpp"
#include <algorithm>

namespace bridge
{
namespace
{
struct Percentage { char const *native; char const *modern; unsigned bit; };
constexpr Percentage percentages[] = {
    {"PLAYER_CRIT_PERCENTAGE", "CritPercentage", 50},
    {"PLAYER_RANGED_CRIT_PERCENTAGE", "RangedCritPercentage", 51},
    {"PLAYER_OFFHAND_CRIT_PERCENTAGE", "OffhandCritPercentage", 52},
    {"PLAYER_SHIELD_BLOCK_CRIT_PERCENTAGE", "ShieldBlockCritPercentage", 54}};
}
void combat_creation(Protocol const &p, Value const &s, Object &active)
{
    for (auto const &spec : percentages)
        active[spec.modern] = p.float_field(s, spec.native);
    Array schools;
    for (unsigned i = 0; i < 7; ++i)
        schools.push_back(p.float_field(s, "PLAYER_SPELL_CRIT_PERCENTAGE1", i));
    active["SpellCritPercentage"] = schools;
}
bool CombatChanges::empty() const
{
    return percentages.empty() && std::all_of(schools.begin(), schools.end(), [](auto n) { return !n; });
}
void CombatChanges::mask(std::array<std::uint32_t, 46> &mask) const
{
    auto set = [&](unsigned bit) { mask.at(bit / 32) |= 1u << (bit % 32); };
    for (auto const &[bit, value] : percentages)
    {
        // Scalar combat fields50..54 are gated by38. Bit32 is the
        // AccountBankCoinage child, not the parent of this group.
        set(38);
        set(bit);
    }
    for (unsigned i = 0; i < 7; ++i)
        if (auto parts = schools[i])
        {
            // WPP's whole interleaved school group starts at 281. Bit288
            // is school6's crit child, not the damage-group parent.
            set(281);
            if (parts & 8) set(282 + i);
            if (parts & 1) set(289 + i);
            if (parts & 2) set(296 + i);
            if (parts & 4) set(303 + i);
        }
}
void CombatChanges::write_percentages(Writer &w) const
{
    for (auto const &[bit, value] : percentages) w.put<float>(value);
}
void CombatChanges::write_schools(Writer &w, Protocol const &p, Value const &s) const
{
    for (unsigned i = 0; i < 7; ++i)
    {
        auto parts = schools[i];
        if (parts & 8) w.put<float>(p.float_field(s, "PLAYER_SPELL_CRIT_PERCENTAGE1", i));
        if (parts & 1) w.put<std::int32_t>(p.field(s, "PLAYER_FIELD_MOD_DAMAGE_DONE_POS", i));
        if (parts & 2) w.put<std::int32_t>(p.field(s, "PLAYER_FIELD_MOD_DAMAGE_DONE_NEG", i));
        if (parts & 4) w.put<float>(p.float_field(s, "PLAYER_FIELD_MOD_DAMAGE_DONE_PCT", i));
    }
}
CombatChanges combat_changes(Protocol const &p, Value const &s, Value const &changed, unsigned visibility)
{
    CombatChanges result;
    if (!(visibility & 1)) return result;
    auto has = [&](char const *name, unsigned i = 0)
    { return changed.as_object().contains(std::to_string(p.field_index(name) + i)); };
    for (auto const &spec : percentages)
        if (has(spec.native)) result.percentages[spec.bit] = p.float_field(s, spec.native);
    for (unsigned i = 0; i < 7; ++i)
        result.schools[i] = (has("PLAYER_FIELD_MOD_DAMAGE_DONE_POS", i) ? 1 : 0) |
            (has("PLAYER_FIELD_MOD_DAMAGE_DONE_NEG", i) ? 2 : 0) |
            (has("PLAYER_FIELD_MOD_DAMAGE_DONE_PCT", i) ? 4 : 0) |
            (has("PLAYER_SPELL_CRIT_PERCENTAGE1", i) ? 8 : 0);
    return result;
}
}
