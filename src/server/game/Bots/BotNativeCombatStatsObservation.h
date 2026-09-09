#ifndef TRINITY_BOT_NATIVE_COMBAT_STATS_OBSERVATION_H
#define TRINITY_BOT_NATIVE_COMBAT_STATS_OBSERVATION_H

#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"

#include <sstream>

namespace BotNativeCombatStatsObservation
{
inline std::string BuildJson(Player const* bot)
{
    Aura const* vengeance = bot
        ? bot->GetAura(76691, bot->GetGUID()) : nullptr;
    AuraEffect const* effect = vengeance ? vengeance->GetEffect(0) : nullptr;
    uint32 const vengeanceCap = bot
        ? CalculatePct(bot->GetCreateHealth(), 10) + bot->GetStat(STAT_STAMINA)
        : 0;
    std::ostringstream json;
    json << "{\"melee_attack_power\":"
         << (bot ? bot->GetTotalAttackPowerValue(BASE_ATTACK) : 0.0f)
         << ",\"vengeance_76691_present\":" << (vengeance ? "true" : "false")
         << ",\"vengeance_76691_effect0_present\":" << (effect ? "true" : "false")
         << ",\"vengeance_76691_effect0_amount\":" << (effect ? effect->GetAmount() : 0)
         << ",\"vengeance_76691_caster_guid\":"
         << (vengeance ? vengeance->GetCasterGUID().GetCounter() : 0)
         << ",\"vengeance_cap_create_health_plus_stamina\":" << vengeanceCap
         << "}";
    return json.str();
}
}

#endif
