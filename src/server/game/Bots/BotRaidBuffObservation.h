#ifndef TRINITY_BOT_RAID_BUFF_OBSERVATION_H
#define TRINITY_BOT_RAID_BUFF_OBSERVATION_H

#include "Define.h"

#include <cstddef>
#include <sstream>
#include <string>

// Round 6: the raid buff auras a bot carries, for `.botauto diagnose`.
//
// The round 5 batch was read as "Blessing of Might never landed": no report
// or snapshot listed 79101/79102, and paladin_blessing_ready was false on
// every bot. Both were observation gaps. The snapshot's modifier ledger only
// covers primary stats (Might changes attack power and mana per 5 s), and
// paladin_blessing_ready looked for Blessing of Kings 20217 and Mark of the
// Wild 1126: dummy spells whose script applies 79062/79063 and 79060/79061,
// so no bot ever carried them and the predicate was false in every run. The
// characters database saved at each clear shows Blessing of Might 79102 on
// all ten bots of all six shards.
//
// Every id below is an aura-applying spell, never the dummy that casts it
// (tests/test_raid_buff_observation.py checks the DBC).
namespace BotRaidBuffObservation
{
struct TrackedAura
{
    uint32 AuraId;
    char const* Name;
};

inline constexpr TrackedAura RaidBuffAuras[] =
{
    { 79060, "mark_of_the_wild" },
    { 79061, "mark_of_the_wild_raid" },
    { 79062, "blessing_of_kings" },
    { 79063, "blessing_of_kings_raid" },
    { 79101, "blessing_of_might" },
    { 79102, "blessing_of_might_raid" },
    { 79104, "power_word_fortitude" },
    { 79105, "power_word_fortitude_raid" },
    { 79057, "arcane_brilliance" },
    { 79058, "arcane_brilliance_raid" },
    { 465, "devotion_aura" },
    { 7294, "retribution_aura" },
    { 19746, "concentration_aura" },
    { 19891, "resistance_aura" },
};

// A paladin blessing on the bot: Kings or Might, single or raid, any caster.
inline constexpr uint32 BlessingAuras[] = { 79062, 79063, 79101, 79102 };

// A paladin aura: Devotion, Retribution, Concentration, Resistance, Crusader.
inline constexpr uint32 PaladinAuras[] = { 465, 7294, 19746, 19891, 32223 };

template <std::size_t Count, typename HasAuraProbe>
bool AnyOf(uint32 const (&auraIds)[Count], HasAuraProbe&& hasAura)
{
    for (uint32 auraId : auraIds)
        if (hasAura(auraId))
            return true;
    return false;
}

// The tracked raid buff auras the probe finds, as a JSON array of ids in
// RaidBuffAuras order.
template <typename HasAuraProbe>
std::string Json(HasAuraProbe&& hasAura)
{
    std::ostringstream json;
    json << '[';
    bool first = true;
    for (TrackedAura const& aura : RaidBuffAuras)
        if (hasAura(aura.AuraId))
        {
            if (!first)
                json << ',';
            first = false;
            json << aura.AuraId;
        }
    json << ']';
    return json.str();
}
}

#endif
