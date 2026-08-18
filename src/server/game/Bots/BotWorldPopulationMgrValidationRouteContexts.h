#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_CONTEXTS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_CONTEXTS_H

#include "ObjectGuid.h"

#include <functional>
#include <string>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
struct TargetingContext
{
    std::function<float(Player*, Unit const*, uint32)> RouteEngageRange;
    std::function<ObjectGuid::LowType()> CurrentTargetSpawnId;
    std::function<bool(Creature const*)> IsFutureCanonicalSource;
    std::function<bool(Creature const*)> WouldPullProtectedFutureSource;
    std::function<bool(uint32)> IsRouteEntry;
    std::function<bool(uint32)> IsRouteAlternateEntry;
    std::function<bool(uint32)> IsRouteCombatEntry;
    std::function<bool(uint32)> IsRoutePackEntry;
    std::function<bool(Creature const*)> IsScriptTarget;
    std::function<bool(Creature const*)> IsCombatTarget;
    std::function<bool(Unit const*)> HasStrictPath;
    std::function<uint32(Creature const*)> ResolvedTransitionAura;
    std::function<bool(Creature const*)> IsPendingScripted;
    std::function<bool(Creature const*)> IsCurrentDiscoveryScripted;
    std::function<bool(Creature const*)> IsEligibleTrash;
    std::function<void(std::function<void(Creature*)> const&)> ForEachActiveCombat;
    std::function<bool(Creature const*)> IsCombatLinked;
    std::function<bool(Creature const*)> IsImmediateNextBoss;
    std::function<bool(Creature const*)> IsImmediateNextEncounter;
    std::function<bool(bool)> PartyHasActiveCombat;
    std::function<bool(Creature const*)> IsBoundedTerminalCombat;
    std::function<Unit*()> FindBoundedTerminalCombat;
    std::function<bool(std::string&, bool&)> TryCanonicalBossRecovery;
    std::function<bool(Creature const*)> IsNaturalForwardHostile;
    std::function<Unit*()> FindForwardDiscovery;
    std::function<bool(Creature const*)> IsObjectiveTarget;
    std::function<Unit*()> FindCurrentDiscoveryScripted;
};

struct PackContext
{
    std::function<bool(Creature const*)> IsNaturalMember;
    std::function<void(Creature const*, bool)> EnrollMember;
    std::function<bool(Creature*)> RecordScriptedTransition;
    std::function<void()> RetireStaleMembers;
    std::function<void()> EnrollEngagedMembers;
    std::function<bool()> HasLiveMembers;
    std::function<Unit*()> ActiveTarget;
    std::function<Unit*()> FindNearestTrash;
    std::function<Unit*()> FindTrashThreat;
};

struct FocusContext
{
    std::function<Unit*(Unit*)> UsableCombatTarget;
    std::function<bool()> FocusMemoryFresh;
    std::function<Unit*(Unit*)> UsableValidationFocus;
    std::function<Unit*()> GroupFocusTarget;
    std::function<ObjectGuid()> TankFocusGuid;
    std::function<void(Unit*)> RememberFocus;
    std::function<Unit*(Creature*)> MakeExistingCombatReady;
    std::function<bool(Unit*, char const*)> TryActivation;
    std::function<Unit*(ObjectGuid)> TankFocusTarget;
    std::function<bool()> AuthoritativeFocusActive;
    std::function<Unit*()> LastKnownFocusTarget;
    std::function<Unit*()> AuthoritativeFocusTarget;
    std::function<bool(char const*)> RecoverAuthoritativeFocus;
    std::function<Unit*(Unit*)> TeacherAssistFocus;
};

struct AnchorContext
{
    uint32 MapId = 0;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    std::string Reason;
    float Distance = 0.0f;
    float CanonicalDistance = 0.0f;
};
}

#endif
