#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_MOVEMENT_CHECK_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_MOVEMENT_CHECK_H

#include "Bots/BotMovementArbiter.h"

#include <functional>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
struct MovementLease
{
    BotMovementArbitration::Owner Owner;
    BotMovementArbitration::Priority Priority;
};

// A configured route-node hazard is still lethal-safety movement. Preserve
// the compatibility adapter's current classification for the adjacent
// ordinary in-combat case, and leave its non-combat default unresolved.
constexpr MovementLease SelectValidationRouteMovementOwner(
    bool configuredHazard, bool inCombat)
{
    if (configuredHazard)
        return { BotMovementArbitration::Owner::Hazard,
            BotMovementArbitration::Priority::Hazard };
    if (inCombat)
        return { BotMovementArbitration::Owner::CombatRange,
            BotMovementArbitration::Priority::Combat };
    return { BotMovementArbitration::Owner::None,
        BotMovementArbitration::Priority::Idle };
}

// Configured marker creatures may be native summons rather than natural pack
// members. Admit their exit authority only when the marker itself or its
// native summoner is an active member of the current route-pack generation.
// This keeps a marker owned by a future encounter fail closed.
constexpr bool OwnsActiveCurrentPackHazardExit(
    bool configuredHazard, bool packGenerationCurrent,
    bool sourceIsActivePackMember, bool summonerIsActivePackMember)
{
    return configuredHazard && packGenerationCurrent
        && (sourceIsActivePackMember || summonerIsActivePackMember);
}

// The route movement lane only observes the two neighboring policy services it
// needs. Keeping those edges typed prevents the movement lease from reaching
// into the objective's local lambda captures or the independent DPS/cast lane.
struct MovementCheckCallbacks
{
    std::function<bool(Creature const*)> IsCombatLinked;
    std::function<bool(Player*, Unit*, bool, bool)> TryGroupHeal;
};
}

#endif
