#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_RAID_COOLDOWN_RESERVATION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_RAID_COOLDOWN_RESERVATION_H

#include "Bots/BotCombatActionCatalog.h"

#include <initializer_list>
#include <string_view>

namespace BotRaidCooldownReservation
{
// This is deliberately a small, value-only view of route state. The policy
// does not inspect spell ids, class ids, or live cooldown timers; those remain
// native/profile concerns. The boss-defensive rule receives the spell's
// native cooldown duration from its caller. A route contract may explicitly
// release the reservation when it owns a special cooldown mechanic.
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

// A boss's first scheduled major tank hit after the pull, and the spell id
// under which the boss publishes its native timer to that hit.  The value is
// the boss script's own first schedule, never an estimate from a log.
struct BossOpeningHit
{
    std::string_view NodeId;
    uint32 AfterPullMs = 0;
    uint32 TimerSpellId = 0;
};

// boss_magmaw.cpp JustEngagedWith: EVENT_MANGLE, 1min + 30s; the Mangle ->
// Massive Crash timer is published under Massive Crash 88253.
constexpr BossOpeningHit BossOpeningHits[] = {
    { "bwd.magmaw.encounter", 90000, 88253 },
};

inline BossOpeningHit const* FindBossOpeningHit(std::string_view nodeId)
{
    for (BossOpeningHit const& hit : BossOpeningHits)
        if (hit.NodeId == nodeId)
            return &hit;
    return nullptr;
}

inline uint32 BossOpeningHitAfterPullMs(std::string_view nodeKind,
    std::string_view nodeId)
{
    BossOpeningHit const* hit = nodeKind == "boss"
        ? FindBossOpeningHit(nodeId) : nullptr;
    return hit ? hit->AfterPullMs : 0;
}

// Below this health a reserved defensive is released on the boss node: an
// immediate death is worse than facing the next big hit without it.
constexpr float BossHitEmergencyHealthPct = 0.35f;

// The trash-node release is lower.  In the fid16-8586fdd Magmaw batch the
// Blood tank fell to 33.1% and 29.0% on the Drudges in kills 1 and 5; the 35%
// release spent Icebound Fortitude there, it was still on cooldown at the
// 90 s Mangle, and kill 5's tank died to Mangle. The raid accepts a
// recovered trash death; Icebound for Mangle is decisive.
constexpr float TrashBeforeBossEmergencyHealthPct = 0.25f;

// On the trash node right before a boss, keep a defensive whose own cooldown
// would still be running at that boss's opening hit even if the pull came
// immediately.  The raid accepts a recovered trash death; a death in the
// boss window is the failure that matters.  Defensives that return in time
// stay available to trash emergencies, and every defensive is released at
// TrashBeforeBossEmergencyHealthPct or less.
inline char const* BossDefensiveReservationReason(RouteContext const& route,
    uint32 nextBossOpeningHitMs, float healthPct,
    BotCombatActionCategory category, uint32 cooldownMs)
{
    if (!route.ValidationRouteEnabled || !route.RaidInstance
        || route.RouteKind != "trash" || !nextBossOpeningHitMs
        || healthPct <= TrashBeforeBossEmergencyHealthPct
        || category != BotCombatActionCategory::Defensive
        || cooldownMs <= nextBossOpeningHitMs)
        return nullptr;
    return "raid_boss_defensive_reserved";
}

struct BossHitTimer
{
    bool Running = false;      // the boss publishes a native timer
    bool HitInProgress = false; // timer at 0, or the tank is held by the boss
};

// On the boss node itself, a defensive whose cooldown is longer than the
// boss's big-hit spacing cannot cover two big hits.  While the native timer
// runs toward the next one, it is kept for that hit; the encounter helper
// casts it.  Released while the hit is in progress and in an emergency.
inline char const* BossHitDefensiveReservationReason(RouteContext const& route,
    uint32 bigHitSpacingMs, BossHitTimer timer, float healthPct,
    BotCombatActionCategory category, uint32 cooldownMs)
{
    if (!route.ValidationRouteEnabled || !route.RaidInstance
        || route.RouteKind != "boss" || !route.EncounterInProgress
        || !bigHitSpacingMs || !timer.Running || timer.HitInProgress
        || healthPct <= BossHitEmergencyHealthPct
        || category != BotCombatActionCategory::Defensive
        || cooldownMs <= bigHitSpacingMs)
        return nullptr;
    return "raid_boss_big_hit_defensive_reserved";
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
