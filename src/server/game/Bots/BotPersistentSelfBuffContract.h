#ifndef TRINITY_BOT_PERSISTENT_SELF_BUFF_CONTRACT_H
#define TRINITY_BOT_PERSISTENT_SELF_BUFF_CONTRACT_H

#include "SharedDefines.h"
#include <string>

namespace BotPersistentSelfBuffContract
{
struct SelfBuff
{
    uint8 ClassId;
    char const* Role;
    char const* SpecTag;
    uint32 SpellId;
    uint32 AuraId;
    uint32 AlternateAuraId;
    char const* Name;
};
inline constexpr SelfBuff Buffs[] =
{
    { CLASS_WARRIOR, "tank", "protection_warrior", 71, 71, 0, "defensive_stance" },
    { CLASS_WARRIOR, "dps", "arms_warrior", 2457, 2457, 0, "battle_stance" },
    { CLASS_WARRIOR, "dps", "fury_warrior", 2458, 2458, 0, "berserker_stance" },
    { CLASS_PALADIN, "tank", nullptr, 25780, 25780, 0, "righteous_fury" },
    { CLASS_PALADIN, "tank", nullptr, 31801, 31801, 0, "seal_of_truth" },
    { CLASS_PALADIN, "tank", nullptr, 465, 465, 0, "devotion_aura" },
    { CLASS_DEATH_KNIGHT, "tank", "blood_death_knight", 48263, 48263, 0, "blood_presence" },
    { CLASS_DEATH_KNIGHT, "dps", "frost_death_knight", 48265, 48265, 0, "unholy_presence" },
    { CLASS_DEATH_KNIGHT, "dps", "unholy_death_knight", 48265, 48265, 0, "unholy_presence" },
    { CLASS_DRUID, "tank", "feral_druid_tank", 5487, 5487, 0, "bear_form" },
    { CLASS_DRUID, "dps", "feral_druid_dps", 768, 768, 0, "cat_form" },
    { CLASS_DRUID, "dps", "balance_druid", 24858, 24858, 0, "moonkin_form" },
    { CLASS_PALADIN, nullptr, nullptr, 20217, 20217, 79063, "blessing_of_kings" },
    { CLASS_MAGE, nullptr, nullptr, 1459, 1459, 79058, "arcane_brilliance" },
    { CLASS_MAGE, nullptr, nullptr, 30482, 30482, 6117, "class_armor" },
    { CLASS_HUNTER, nullptr, nullptr, 13165, 13165, 0, "aspect_of_the_hawk" },
    { CLASS_WARLOCK, nullptr, nullptr, 28176, 28176, 0, "fel_armor" },
    { CLASS_SHAMAN, "healer", nullptr, 52127, 52127, 0, "water_shield" },
    { CLASS_SHAMAN, "dps", nullptr, 324, 324, 0, "lightning_shield" },
};

inline bool Matches(SelfBuff const& buff, uint8 classId,
    std::string const& role, std::string const& spec)
{
    return buff.ClassId == classId && (!buff.Role || role == buff.Role)
        && (!buff.SpecTag || spec == buff.SpecTag);
}
}
#endif
