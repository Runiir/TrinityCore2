#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAdaptiveAtramedesStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesIceBlockGuard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationExport.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationStore.h"

#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <string>
#include <utility>

using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

namespace
{
// The acceptance observation of every cohort: per cohort attempt, the Sound
// of the player the Reverberating Flame chases, bound to its map instance,
// and the counters the raid_runtime export reads
// (BotAtramedesObservationStore.h).
BotEncounter::Atramedes::ObservationStore& Observations()
{
    static BotEncounter::Atramedes::ObservationStore store;
    return store;
}
}

std::string BotEncounter::Atramedes::EncounterObservationsJsonField(std::string const& field,
    std::string const& cohortId, ObservationAttempt attempt, std::string const& routeNodeId)
{
    return Observations().JsonField(field, cohortId, attempt, routeNodeId);
}

// The adaptive Atramedes owner replaces the route adapter on the encounter
// node, so it must also carry the route's engagement edge, as Magmaw's and
// Chimaeron's observers do. Round 5 killed Atramedes (26,110,798 damage, no
// death) but the native death callback rejected the kill
// (gate=combined_rejected, engaged_guid_expected empty): nothing had called
// RememberValidationRouteBossEngagement, the route never recorded the clear
// and the shard sat at bwd.atramedes.encounter until the plateau watchdog.
// Observation only: it never changes target, focus or movement.
void BotWorldPopulationMgr::SubmitAdaptiveAtramedesRouteObservation(BotUpdateContext& context)
{
    // Acceptance observation (round 3, user decision 2026-09-30 "Bound kiter
    // Sound"): the observations are live for this cohort attempt (start
    // lifecycle and attempt id) from the first decision the plan owns, and
    // every decision offers the cohort's snapshot; the store samples each
    // snapshot once. Observation only, before the route observer below.
    BotEncounter::Atramedes::ObservationAttempt const observationAttempt{
        Cohort().CombatLogEpoch, Cohort().AttemptId };
    if (context.AdaptiveAtramedesOwnsNode)
        Observations().Begin(Cohort().Id, observationAttempt);
    if (Cohort().EncounterSnapshot)
    {
        Observations().Observe(Cohort().Id, observationAttempt, *Cohort().EncounterSnapshot);
        // Ice Block is strictly once per fight: the strategy reads this
        // attempt-scoped memory (BotAtramedesIceBlockGuard.h). It records
        // only for a snapshot on Atramedes' encounter node.
        BotEncounter::Atramedes::ProcessIceBlockGuard().Observe(Cohort().Id,
            observationAttempt, *Cohort().EncounterSnapshot);
    }

    auto observe = [this, &context]() -> BotActionArbitration::Outcome
    {
        if (!context.AdaptiveAtramedesOwnsNode
            || Cohort().Config.ValidationRouteKind != "boss"
            || Cohort().Config.ValidationRouteNodeId
                != BotEncounter::Atramedes::EncounterNode)
            return BotActionArbitration::Outcome::NotApplicable(
                "atramedes_route_observation_not_owned");

        // The plan's damage target is Atramedes for everyone the air phase
        // does not keep off him (melee and the tank), so one ranged member's
        // tick binds the engagement. Atramedes himself must be in combat:
        // the plan owns the node from the first non-PrePull snapshot, and a
        // bot still fighting the intro's leftovers (or one that has just
        // wiped) is never taken for the engagement.
        Unit* target = context.Target;
        Creature const* creature = target ? target->ToCreature() : nullptr;
        if (!target || !creature || !target->IsAlive()
            || creature->GetEntry() != BotEncounter::Atramedes::BossEntry
            || creature->GetEntry() != Cohort().Config.ValidationRouteTargetEntry
            || !target->IsInCombat()
            || !context.Bot->IsValidAttackTarget(target)
            || !IsNativeCombatObserved(context.Bot, target))
            return BotActionArbitration::Outcome::NotApplicable(
                "atramedes_route_observation_wait_for_native_combat");

        RememberValidationRouteBossEngagement(creature);

        bool const targetChanged = context.State.LastDecisionTargetGuid != target->GetGUID();
        bool const firstEngagement = !context.State.WasInCombat;
        if (!targetChanged && !firstEngagement)
            return BotActionArbitration::Outcome::NotApplicable(
                "atramedes_route_observation_already_recorded");

        float const targetHealthPct = UnitHealthPct(target);
        RecordRouteProgress(context.State, context.Bot, target,
            "route_target_combat_progress", targetHealthPct, targetHealthPct, 0, 20);
        Party().ValidationRouteObservedEngagement = true;
        std::string raw = BuildRawJson(context.Bot, target);
        std::string semantic = BuildSemanticJson(context.Bot, target, "adaptive_atramedes",
            &context.Power, context.Stage, context.ChosenActivity.Activity);
        RecordEvent(context.State, context.Bot, "validation_target_priority", target,
            "native_combat_observed", raw.c_str(), semantic.c_str(),
            context.Bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, 0);
        RecordEvent(context.State, context.Bot, "boss_action", target,
            "native_combat_observed", raw.c_str(), semantic.c_str(),
            context.Bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, 0);
        if (firstEngagement)
            RecordEvent(context.State, context.Bot, "boss_started", target,
                "native_combat_observed", raw.c_str(), semantic.c_str(),
                context.Bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, 0);
        context.State.WasInCombat = true;
        return BotActionArbitration::Outcome::NotApplicable(
            "adaptive_atramedes_route_observation_recorded");
    };

    BotActionArbitration::Candidate observation;
    observation.Key = "world.validation_route_atramedes_observation";
    observation.Source = "validation_route_observer";
    observation.ActionPriority = BotActionArbitration::Priority::Mechanic;
    observation.UtilityScore = 0.0f;
    observation.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::None);
    observation.Attempt = std::move(observe);
    context.State.DecisionKernel.Submit(std::move(observation));
}
