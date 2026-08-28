#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_RAID_COOLDOWN_RESERVATION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_RAID_COOLDOWN_RESERVATION_H

#include "Bots/BotCombatActionCatalog.h"

#include <initializer_list>
#include <string_view>

namespace BotRaidCooldownReservation
{
// This is deliberately a small, value-only view of route state. The policy
// does not inspect spell ids, class ids, or cooldown timers; those remain
// native/profile concerns. A route contract may explicitly release the
// reservation when it owns a special cooldown mechanic.
struct RouteContext
{
    bool ValidationRouteEnabled = false;
    bool RaidInstance = false;
    bool EncounterInProgress = false;
    bool ContractAllowsReservedCooldowns = false;
    std::string_view RouteKind;
    std::string_view NodeKind;
    std::string_view EncounterPhase;
};

struct CandidateContext
{
    BotCombatActionCategory Category = BotCombatActionCategory::Wait;
    std::string_view MechanicTags;
};

inline bool HasTag(std::string_view tags, std::string_view required)
{
    size_t start = 0;
    while (start <= tags.size())
    {
        size_t end = tags.find(',', start);
        size_t length = end == std::string_view::npos ? tags.size() - start : end - start;
        if (tags.substr(start, length) == required)
            return true;
        if (end == std::string_view::npos)
            break;
        start = end + 1;
    }
    return false;
}

inline bool HasAnyTag(std::string_view tags, std::initializer_list<std::string_view> required)
{
    for (std::string_view tag : required)
        if (HasTag(tags, tag))
            return true;
    return false;
}

inline bool IsReservationWindow(RouteContext const& route)
{
    if (!route.ValidationRouteEnabled || !route.RaidInstance
        || route.ContractAllowsReservedCooldowns)
        return false;

    if (route.RouteKind == "trash" || route.RouteKind == "regroup"
        || route.RouteKind == "prepull" || route.NodeKind == "prepull"
        || route.NodeKind == "pre_pull")
        return true;

    // A boss node is a reservation window only while the party is staging.
    // Once the native encounter enters combat, the normal profile and
    // encounter contract may spend the cooldown.
    return route.RouteKind == "boss"
        && !route.EncounterInProgress
        && route.EncounterPhase != "combat";
}

inline bool IsEmergencyOrSurvival(CandidateContext const& candidate)
{
    switch (candidate.Category)
    {
        case BotCombatActionCategory::Defensive:
        case BotCombatActionCategory::Mitigation:
        case BotCombatActionCategory::HealEfficient:
        case BotCombatActionCategory::HealFast:
        case BotCombatActionCategory::HealAoe:
        case BotCombatActionCategory::ExternalDefensive:
        case BotCombatActionCategory::ResurrectRecover:
        case BotCombatActionCategory::DispelCleanse:
            return true;
        default:
            break;
    }

    return HasAnyTag(candidate.MechanicTags, {
        "emergency", "survival", "survival_cooldown", "defensive",
        "mitigation", "healing_cooldown", "guardian_spirit",
        "spirit_link_totem"});
}

inline bool IsBloodlust(CandidateContext const& candidate)
{
    return HasAnyTag(candidate.MechanicTags, {
        "bloodlust", "heroism", "time_warp", "ancient_hysteria",
        "primal_rage", "raid_lust", "lust"});
}

inline bool IsCombatPotion(CandidateContext const& candidate)
{
    if (candidate.Category != BotCombatActionCategory::UseItem
        || HasAnyTag(candidate.MechanicTags, {"health_potion", "healing_potion", "survival"}))
        return false;
    return HasAnyTag(candidate.MechanicTags, {
        "combat_potion", "potion", "volcanic_potion", "prepot"});
}

inline bool IsOffensiveGuardian(CandidateContext const& candidate)
{
    return HasAnyTag(candidate.MechanicTags, {
        "guardian", "fire_elemental_totem", "greater_fire_elemental",
        "summon_gargoyle", "summon_doomguard", "treants"});
}

inline char const* ReservationReason(RouteContext const& route,
    CandidateContext const& candidate)
{
    if (!IsReservationWindow(route) || IsEmergencyOrSurvival(candidate))
        return nullptr;

    if (IsBloodlust(candidate))
        return "raid_bloodlust_reserved";
    if (IsCombatPotion(candidate))
        return "raid_combat_potion_reserved";
    if (IsOffensiveGuardian(candidate))
        return "raid_offensive_guardian_reserved";
    if (candidate.Category == BotCombatActionCategory::OffensiveCooldown)
        return "raid_offensive_cooldown_reserved";
    return nullptr;
}
}

#endif
