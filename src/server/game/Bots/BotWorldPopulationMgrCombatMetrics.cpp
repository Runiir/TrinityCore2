#include "Bots/BotWorldPopulationMgr.h"

#include <algorithm>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string>

namespace
{
struct ActorCombatMetrics
{
    std::string Name;
    std::string Role;
    uint64 Damage = 0;
    uint64 RawEventDamage = 0;
    uint64 Healing = 0;
    uint64 PetDamage = 0;
    uint64 RawEventPetDamage = 0;
};

template <typename AbilityMap, typename Perspective>
void AccumulateCombatMetrics(AbilityMap const& abilities, uint64 generation,
    Perspective damageDone, Perspective healingDone,
    std::map<uint32, ActorCombatMetrics>& actors, uint64& partyDamage,
    uint64& rawEventDamage, uint64& partyHealing, std::string& routeNodeId)
{
    for (auto const& [key, aggregate] : abilities)
    {
        if (key.RouteGeneration != generation)
            continue;

        ActorCombatMetrics& actor = actors[key.ActorGuid];
        if (actor.Name.empty())
            actor.Name = aggregate.ActorName;
        if (actor.Role.empty())
            actor.Role = aggregate.ActorRole;
        if (routeNodeId.empty())
            routeNodeId = aggregate.RouteNodeId;

        if (key.Perspective == damageDone)
        {
            actor.Damage += aggregate.OriginatedAmount;
            actor.RawEventDamage += aggregate.Amount;
            partyDamage += aggregate.OriginatedAmount;
            rawEventDamage += aggregate.Amount;
            if (aggregate.SourceIsPet)
            {
                actor.PetDamage += aggregate.OriginatedAmount;
                actor.RawEventPetDamage += aggregate.Amount;
            }
        }
        else if (key.Perspective == healingDone)
        {
            actor.Healing += aggregate.Amount;
            partyHealing += aggregate.Amount;
        }
    }
}

template <typename BucketMap, typename Perspective>
std::set<uint64> CollectPartyDamageSeconds(BucketMap const& buckets,
    uint64 generation, Perspective damageDone)
{
    std::set<uint64> seconds;
    for (auto const& [key, bucket] : buckets)
    {
        if (!bucket.OriginatedAmount || std::get<0>(key) != generation
            || std::get<1>(key) != damageDone)
            continue;
        seconds.insert(std::get<4>(key));
    }
    return seconds;
}

template <typename BucketMap, typename Perspective>
std::set<uint64> CollectRawEventDamageSeconds(BucketMap const& buckets,
    uint64 generation, Perspective damageDone)
{
    std::set<uint64> seconds;
    for (auto const& [key, bucket] : buckets)
    {
        if (!bucket.RawAmount || std::get<0>(key) != generation
            || std::get<1>(key) != damageDone)
            continue;
        seconds.insert(std::get<4>(key));
    }
    return seconds;
}
}

std::string BotWorldPopulationMgr::BuildCombatMetricsJson() const
{
    uint64 const generation = Party().ValidationRouteGeneration;
    std::map<uint32, ActorCombatMetrics> actors;
    uint64 partyDamage = 0;
    uint64 rawEventDamage = 0;
    uint64 partyHealing = 0;
    std::string routeNodeId = Cohort().Config.ValidationRouteNodeId;
    AccumulateCombatMetrics(Party().CombatLogAbilities, generation,
        CombatLogPerspective::DamageDone, CombatLogPerspective::HealingDone,
        actors, partyDamage, rawEventDamage, partyHealing, routeNodeId);
    std::set<uint64> const partyDamageSeconds = CollectPartyDamageSeconds(
        Party().CombatLogSecondBuckets, generation, CombatLogPerspective::DamageDone);
    std::set<uint64> const rawEventDamageSeconds = CollectRawEventDamageSeconds(
        Party().CombatLogSecondBuckets, generation, CombatLogPerspective::DamageDone);

    uint64 const originatedDamageSeconds = partyDamageSeconds.size();
    uint64 const rawEventCombatSeconds = rawEventDamageSeconds.size();
    // Retain the historical active-combat denominator for HPS and elapsed
    // comparability. Provenance changes the damage numerator only.
    uint64 const activePartyDamageSeconds = rawEventCombatSeconds;
    uint64 const combatSeconds = std::max<uint64>(1, activePartyDamageSeconds);
    double const denominator = double(combatSeconds);
    double const rawEventDenominator = double(std::max<uint64>(1, rawEventCombatSeconds));
    std::ostringstream json;
    json << std::fixed << std::setprecision(3)
         << "{\"schema\":\"bot_combat_metrics_v2\""
         << ",\"measurement_basis\":\"originated_damage\""
         << ",\"raw_event_basis\":\"all_landed_damage_callbacks\""
         << ",\"route_generation\":" << generation
         << ",\"route_node_id\":\"" << JsonEscape(routeNodeId) << "\""
         << ",\"available\":" << (!actors.empty() ? "true" : "false")
         << ",\"active_party_damage_seconds\":" << activePartyDamageSeconds
         << ",\"combat_seconds\":" << combatSeconds
         << ",\"originated_damage_seconds\":" << originatedDamageSeconds
         << ",\"raw_event_damage_seconds\":" << rawEventCombatSeconds
         << ",\"party_damage\":" << partyDamage
         << ",\"party_dps\":" << (partyDamage / denominator)
         << ",\"raw_event_damage\":" << rawEventDamage
         << ",\"raw_event_dps\":" << (rawEventDamage / rawEventDenominator)
         << ",\"party_healing\":" << partyHealing
         << ",\"party_hps\":" << (partyHealing / denominator)
         << ",\"pet_damage_included_in_owner\":true"
         << ",\"actors\":[";

    bool first = true;
    for (auto const& [guid, actor] : actors)
    {
        if (!first)
            json << ',';
        first = false;
        json << "{\"bot_guid\":" << guid
             << ",\"bot_name\":\"" << JsonEscape(actor.Name) << "\""
             << ",\"role\":\"" << JsonEscape(actor.Role) << "\""
             << ",\"damage\":" << actor.Damage
             << ",\"dps\":" << (actor.Damage / denominator)
             << ",\"raw_event_damage\":" << actor.RawEventDamage
             << ",\"raw_event_dps\":" << (actor.RawEventDamage / rawEventDenominator)
             << ",\"healing\":" << actor.Healing
             << ",\"hps\":" << (actor.Healing / denominator)
             << ",\"pet_damage\":" << actor.PetDamage
             << ",\"pet_damage_share\":"
             << (actor.Damage ? double(actor.PetDamage) / double(actor.Damage) : 0.0)
             << ",\"raw_event_pet_damage\":" << actor.RawEventPetDamage
             << ",\"raw_event_pet_damage_share\":"
             << (actor.RawEventDamage ? double(actor.RawEventPetDamage) / double(actor.RawEventDamage) : 0.0)
             << '}';
    }
    json << "]}";
    return json.str();
}
