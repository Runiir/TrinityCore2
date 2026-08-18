#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <functional>

Unit* BotWorldPopulationMgr::ResolveUsableValidationRouteCombatTarget(
    Player* bot, bool discoveryLeg, Unit* candidate,
    std::function<bool(Creature const*)> const& isValidationRouteCombatTarget,
    std::function<bool(Creature const*)> const& isEligibleTrashClusterMob,
    std::function<bool(Unit const*)> const& hasStrictPathToValidationRouteTarget,
    std::function<bool(Creature const*)> const& isBoundedTerminalPartyCombatTarget,
    std::function<bool(Creature const*)> const& isCurrentDiscoveryScriptedEventTarget)
{
    bot,
    discoveryLeg,
    &isValidationRouteCombatTarget,
    &isEligibleTrashClusterMob,
    &hasStrictPathToValidationRouteTarget,
    &isBoundedTerminalPartyCombatTarget,
    &isCurrentDiscoveryScriptedEventTarget
](Unit* candidate) -> Unit*
{
    if (!candidate || !candidate->IsAlive() || !candidate->GetHealth() || !bot || !bot->IsValidAttackTarget(candidate))
        return nullptr;

    Creature const* creature = candidate->ToCreature();
    if (!creature || Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRouteFinalTransitionGuids.end())
        return nullptr;

    if (Cohort().Config.ValidationRouteKind != "boss")
    {
        if (isEligibleTrashClusterMob(creature))
            return candidate;
        // A discovery node has no static pack-entry list.  Once a
        // current-node scripted actor has been observed in native combat,
        // the persisted pack ledger is the authority that keeps it
        // targetable (the pending-scripted guard above must still prevent
        // unobserved/future actors from being pulled).  Without this
        // exception activeValidationRoutePackTarget can find Millhouse,
        // but the later common target gate silently discards it.
        bool currentDiscoveryPackMember = discoveryLeg
            && Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
            && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID()) != Party().ValidationRoutePackMemberGuids.end()
            && Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID()) == Party().ValidationRoutePackTransitionGuids.end()
            && hasStrictPathToValidationRouteTarget(creature);
        if (currentDiscoveryPackMember
            || (isCurrentDiscoveryScriptedEventTarget(creature)
                && hasStrictPathToValidationRouteTarget(creature)))
            return candidate;
        bool explicitTerminalCombatFocus = !Party().ValidationRouteFocusGuid.IsEmpty()
            && candidate->GetGUID() == Party().ValidationRouteFocusGuid
            && isBoundedTerminalPartyCombatTarget(creature);
        return explicitTerminalCombatFocus ? candidate : nullptr;
    }

    // Rerun196 reached Azil's final route generation with no party combat,
    // but one passive Devout Follower remained in the dedicated add focus
    // while another was refreshed as the generic boss-route focus.  The
    // generic focus path therefore alternated with the add handler for 127
    // seconds and never reached the boss anchor.  Passive declared adds are
    // owned exclusively by the dedicated add handler; admit them here only
    // after native combat or victim state proves an actual handoff.  This
    // does not suppress an engaged follower or any configured boss target.
    bool unengagedListedBossAdd = Cohort().Config.ValidationRouteKind == "boss"
        && std::find(
            Cohort().Config.ValidationRouteAddTargetEntries.begin(),
            Cohort().Config.ValidationRouteAddTargetEntries.end(),
            creature->GetEntry())
            != Cohort().Config.ValidationRouteAddTargetEntries.end()
        && !candidate->IsInCombat() && !candidate->GetVictim();
    if (unengagedListedBossAdd)
        return nullptr;

    if (isValidationRouteCombatTarget(creature))
        return candidate;

    if (creature->IsDungeonBoss() || creature->isWorldBoss())
        return nullptr;

    float routeProximity = candidate->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
    return routeProximity <= 120.0f ? candidate : nullptr;
}

