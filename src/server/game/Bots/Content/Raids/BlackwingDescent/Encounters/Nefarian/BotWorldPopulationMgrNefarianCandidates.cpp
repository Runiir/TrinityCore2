#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationExport.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationStore.h"

#include "CharmInfo.h"
#include "Creature.h"
#include "GameTime.h"
#include "MotionMaster.h"
#include "MoveSpline.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <string>
#include <utility>
#include <vector>

using BotEncounter::Nefarian::ReportsWarriorWatch;
using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

namespace
{
// The acceptance observations of every cohort: per cohort attempt, the
// bone-warrior watch bound to its map instance and the counters the
// raid_runtime export reads (BotNefarianObservationStore.h).
BotEncounter::Nefarian::ObservationStore& Observations()
{
    static BotEncounter::Nefarian::ObservationStore store;
    return store;
}
}

// Kernel submission of the adaptive Nefarian's End strategy's outputs. The
// strategy (BotAdaptiveNefarianStrategy.h) decides from the encounter
// snapshot and the bot's native facts; this file only turns its typed
// proposals into arbitration candidates:
// - the platform/phase movement leg (a transport-surface Walk, or a native
//   point move on the ground), at hazard priority;
// - exact per-spec casts (Blast Nova interrupts, taunts, bone-warrior
//   controls); the native executor keeps every rule (known spell, cooldown,
//   range, line of sight) and a rejection is retryable, never an effect;
// - offense suppression (before the pull, the airborne dragon's tank, the
//   platform without a prototype, the landing);
// - the typed capability blocker or movement hold of this decision, recorded
//   as a not-applicable reason in the decision trace.
std::string BotEncounter::Nefarian::EncounterObservationsJsonField(std::string const& cohortId,
    ObservationAttempt attempt, std::string const& routeNodeId)
{
    return Observations().JsonField(cohortId, attempt, routeNodeId);
}

void BotWorldPopulationMgr::SubmitAdaptiveNefarianCandidates(BotUpdateContext& context)
{
    // The cohort's observations are live for this attempt (start lifecycle
    // and attempt id) from the first decision the strategy owns; a new
    // attempt starts them clean.
    std::string const cohortId = Cohort().Id;
    BotEncounter::Nefarian::ObservationAttempt const observationAttempt{
        Cohort().CombatLogEpoch, Cohort().AttemptId };
    if (context.AdaptiveNefarianOwnsNode)
        Observations().Begin(cohortId, observationAttempt);

    // Acceptance observation (round 3): a bone warrior active past 45 s or
    // standing on a pillar is recorded once in the reporter's decision trace.
    // The watch is this cohort attempt's, bound to the snapshot's instance.
    // One reporter per cohort, a bot (ReportsWarriorWatch). Active durations
    // run on the game tick's monotonic (steady) time: the snapshot's own
    // ObservedAtMs is system time, which a clock step can move. The reporter
    // decides more often than the blackboard is republished (a system-time
    // throttle, held by a step back of the wall clock), so the snapshot's
    // Revision goes with the observation: a snapshot already observed adds
    // neither state nor time. Its ObservedAtMs (system ms, the combat log's
    // clock) goes with it too: the export's first and last observation times,
    // which the harness holds against the boss window.
    if (context.AdaptiveNefarianOwnsNode && Cohort().EncounterSnapshot
        && ReportsWarriorWatch(*Cohort().EncounterSnapshot, context.Bot->GetGUID()))
    {
        BotEncounter::Blackboard const& board = *Cohort().EncounterSnapshot;
        BotEncounter::Nefarian::EncounterView const view =
            BotEncounter::Nefarian::ObserveEncounter(board);
        std::vector<BotEncounter::Nefarian::WarriorViolation> const violations =
            Observations().ObserveWarriors(cohortId, observationAttempt, board.CurrentScope,
                view, { board.Revision, board.ObservedAtMs },
                BotEncounter::Nefarian::ObservationClockMs(
                    GameTime::GetGameTimeSteadyPoint()));
        for (BotEncounter::Nefarian::WarriorViolation const& violation : violations)
        {
            std::string const name(BotEncounter::Nefarian::WarriorViolationName(violation.Kind));
            RecordDecisionTrace(context.State, "adaptive_nefarian", name.c_str(),
                ObjectAccessor::GetUnit(*context.Bot, violation.Warrior), 0, "observation",
                name.c_str(), false);
        }
    }

    // The movement lease at the bot's own position, renewed by every admitted
    // leg of the plan and every hold: the movement executor preserves it
    // against every lower lane (combat range recovery - MoveBotToProfileRange,
    // CombatRange at Combat priority - chase, formation, healer approach and
    // route walks), and the heal guard reads it as protected movement.
    auto renewLease = [this, &context](BotMovementArbitration::Owner owner,
        BotMovementArbitration::Priority priority)
    {
        Player* bot = context.Bot;
        BotWorldMovement::Intent lease;
        lease.X = bot->GetPositionX();
        lease.Y = bot->GetPositionY();
        lease.Z = bot->GetPositionZ();
        lease.Owner = owner;
        lease.Priority = priority;
        BotMovementArbitration::Apply(context.State.MovementLease,
            BuildMovementRequest(bot, lease, context.DecisionNowMs));
    };

    if (context.AdaptiveNefarianMovement
        && context.AdaptiveNefarianMovement->ExpiresAtMs > context.DecisionNowMs)
    {
        BotNativeAction::Candidate const& proposal = *context.AdaptiveNefarianMovement;
        BotActionArbitration::Candidate movement;
        movement.Key = proposal.Id.Key();
        movement.Source = proposal.Id.Strategy;
        movement.ActionPriority = proposal.ActionPriority;
        movement.UtilityScore = proposal.Utility;
        movement.RequiredResources = proposal.Resources();
        movement.ExpiresAtMs = proposal.ExpiresAtMs;
        // An admitted surface leg publishes its lease: Hazard for a survival
        // escape (fire, breath, warriors), Mechanic for the rest.
        bool const survival = uint8(proposal.ActionPriority)
            >= uint8(BotActionArbitration::Priority::Survival);
        movement.Attempt = [this, &context, renewLease, survival, cohortId, observationAttempt,
            mechanic = proposal.Id.Mechanic,
            intent = BotNativeAction::WithMovementReason(proposal.Action,
                proposal.Id.Mechanic)]()
        {
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                context.State, context.Bot, intent, BotMovementArbitration::Owner::Hazard,
                BotMovementArbitration::Priority::Hazard);
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
            {
                renewLease(survival ? BotMovementArbitration::Owner::Hazard
                        : BotMovementArbitration::Owner::Mechanic,
                    survival ? BotMovementArbitration::Priority::Hazard
                        : BotMovementArbitration::Priority::Mechanic);
                context.Situation = "adaptive_nefarian";
                context.Action = "nefarian_mechanic_movement";
                context.State.LastDecisionHandler = "adaptive_nefarian";
            }
            else if (outcome.Result == BotActionArbitration::Disposition::Retryable
                || outcome.Result == BotActionArbitration::Disposition::Unsafe)
            {
                // Round 3: a refused step is visible in the decision trace
                // (round 2's pillar-1 step-offs were refused every decision
                // with no reason in the evidence). Repeats coalesce.
                std::string const refused = std::string(BotEncounter::Nefarian::MoveRefusedPrefix)
                    + mechanic + ":" + outcome.Reason;
                // Counted for the status export: every refusal, uncoalesced.
                Observations().RecordRefused(cohortId, observationAttempt,
                    context.Bot->GetGUID().GetCounter(),
                    refused.substr(BotEncounter::Nefarian::MoveRefusedPrefix.size()));
                RecordDecisionTrace(context.State, "adaptive_nefarian", refused.c_str(),
                    nullptr, 0, "refused", outcome.Reason.c_str(), true);
            }
            return outcome;
        };
        context.State.DecisionKernel.Submit(std::move(movement));
    }

    for (BotNativeAction::Candidate const& proposal : context.AdaptiveNefarianActions)
    {
        if (proposal.ExpiresAtMs <= context.DecisionNowMs)
            continue;
        BotActionArbitration::Candidate action;
        action.Key = proposal.Id.Key();
        action.Source = proposal.Id.Strategy;
        action.ActionPriority = proposal.ActionPriority;
        action.UtilityScore = proposal.Utility;
        action.RequiredResources = proposal.Resources();
        action.ExpiresAtMs = proposal.ExpiresAtMs;
        action.Attempt = [this, &context, intent = proposal.Action,
            mechanic = proposal.Id.Mechanic]()
        {
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                context.State, context.Bot, intent, BotMovementArbitration::Owner::Mechanic,
                BotMovementArbitration::Priority::Mechanic);
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
            {
                context.Situation = "adaptive_nefarian";
                context.Action = mechanic;
                context.State.LastDecisionHandler = "adaptive_nefarian";
            }
            return outcome;
        };
        context.State.DecisionKernel.Submit(std::move(action));
    }

    if (context.AdaptiveNefarianSuppressOffense)
    {
        std::string const suppressReason = context.AdaptiveNefarianSuppressReason.empty()
            ? std::string("nefarian_offense_suppressed")
            : context.AdaptiveNefarianSuppressReason;
        BotActionArbitration::Candidate suppress;
        suppress.Key = "adaptive_nefarian:" + suppressReason + ":"
            + std::to_string(Party().ValidationRouteGeneration);
        suppress.Source = "adaptive_nefarian";
        suppress.ActionPriority = BotActionArbitration::Priority::Mechanic;
        suppress.UtilityScore = 100.0f;
        suppress.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Pet);
        suppress.Attempt = [this, &context, suppressReason]()
        {
            std::string const intentReason = "adaptive_nefarian_" + suppressReason;
            bool const submitted = SubmitMeleeAutoAttackIntent(context.State,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Mechanic,
                BotActionArbitration::Priority::Mechanic, intentReason.c_str());
            if (Pet* pet = context.Bot->GetPet(); pet && pet->GetCharmInfo())
                ExecuteNativeActionIntent(context.State, context.Bot,
                    BotNativeAction::PetCommand{ pet->GetGUID(), context.Bot->GetGUID(),
                        COMMAND_FOLLOW },
                    BotMovementArbitration::Owner::Mechanic,
                    BotMovementArbitration::Priority::Mechanic);
            context.State.TargetGuid.Clear();
            context.Target = nullptr;
            context.Situation = "adaptive_nefarian";
            context.Action = suppressReason;
            context.State.LastDecisionHandler = "adaptive_nefarian";
            return submitted
                ? BotActionArbitration::Outcome::Committed("melee_autoattack_suppression_submitted")
                : BotActionArbitration::Outcome::Retryable("melee_autoattack_suppression_rejected");
        };
        context.State.DecisionKernel.Submit(std::move(suppress));

        // A damage dealer holding fire before Onyxia is tanked also claims the
        // Target lane, so no trained damage candidate opens on her (the
        // suppression above covers only melee swings and the pet). Heals and
        // consumables claim no Target and go on.
        if (suppressReason == BotEncounter::Nefarian::HoldFirePreEngage
            || suppressReason == BotEncounter::Nefarian::HoldFireForOnyxiaTank)
        {
            BotActionArbitration::Candidate holdFire;
            holdFire.Key = "adaptive_nefarian:hold_fire:" + suppressReason;
            holdFire.Source = "adaptive_nefarian";
            holdFire.ActionPriority = BotActionArbitration::Priority::Mechanic;
            holdFire.UtilityScore = 100.0f;
            holdFire.RequiredResources = BotActionArbitration::Uses(
                BotActionArbitration::Resource::Target);
            holdFire.Attempt = [suppressReason]()
            {
                return BotActionArbitration::Outcome::Committed(
                    "nefarian_hold_fire_" + suppressReason);
            };
            context.State.DecisionKernel.Submit(std::move(holdFire));
        }
    }

    // The movement holds, renewed every decision while the plan asks for
    // them. Each claims the movement lane and renews a movement lease at the
    // bot's own position, so the movement executor preserves it against every
    // lower lane (combat range recovery - MoveBotToProfileRange, CombatRange at
    // Combat priority - chase, formation and route walks) in the same tick and
    // until the lease expires; a controlled effect (fear, knockback, jump) is
    // left alone.
    // - WarriorStopHold: a bot leading warriors with no lawful leg (a running
    //   walk that would take them deeper into Nefarian's front, a refused leg,
    //   the handler cornered). Hazard lease; the native generator of the
    //   active slot (a chase or point path) is cleared and the spline stopped,
    //   as a client releasing its keys.
    // - PlatformHold: a bot on the raised platform with no leg of the plan
    //   (round 7: static navmesh paths walked bots off the transport into the
    //   magma bowl under it). Mechanic lease; stopped the same way.
    // - LegInFlightHold: the plan's own leg is running: Mechanic lease only.
    std::string const& hold = context.AdaptiveNefarianMovementHold;
    bool const warriorStop = hold == BotEncounter::Nefarian::WarriorStopHold;
    // The pillar hold (phase 2, round 3) stops and leases like the platform hold.
    bool const platformStop = BotEncounter::Nefarian::IsPlatformHold(hold)
        || BotEncounter::Nefarian::IsPillarHold(hold);
    bool const legInFlight = hold == BotEncounter::Nefarian::LegInFlightHold;
    if (warriorStop || platformStop || legInFlight)
    {
        BotMovementArbitration::Owner const owner = warriorStop
            ? BotMovementArbitration::Owner::Hazard : BotMovementArbitration::Owner::Mechanic;
        BotMovementArbitration::Priority const priority = warriorStop
            ? BotMovementArbitration::Priority::Hazard
            : BotMovementArbitration::Priority::Mechanic;
        bool const stopMoving = warriorStop || platformStop;
        // Beside a proposed leg the platform hold is the fallback: below every
        // leg (CombatMovement, utility 1), so an admitted leg claims the lane
        // first and a leg that native admission rejects leaves it to the hold.
        bool const fallback = platformStop && context.AdaptiveNefarianMovement
            && context.AdaptiveNefarianMovement->ExpiresAtMs > context.DecisionNowMs;
        BotActionArbitration::Candidate stop;
        stop.Key = "adaptive_nefarian:" + hold;
        stop.Source = "adaptive_nefarian";
        stop.ActionPriority = warriorStop ? BotActionArbitration::Priority::Survival
            : fallback ? BotActionArbitration::Priority::CombatMovement
            : BotActionArbitration::Priority::Mechanic;
        stop.UtilityScore = warriorStop ? 480.0f : fallback ? 1.0f : 250.0f;
        stop.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Movement);
        stop.ExpiresAtMs = context.DecisionNowMs + 1000;
        stop.Attempt = [&context, renewLease, owner, priority, stopMoving, hold]()
        {
            Player* bot = context.Bot;
            MotionMaster* motion = bot->GetMotionMaster();
            if (motion->GetMotionSlot(MOTION_SLOT_CONTROLLED))
                return BotActionArbitration::Outcome::Retryable(
                    "nefarian_movement_hold_controlled_motion");
            if (stopMoving)
            {
                // As SettleRetainedMagmawFormation retires a native path.
                if (!bot->movespline->Finalized())
                    bot->StopMoving();
                motion->Clear(MOTION_SLOT_ACTIVE);
                motion->MoveIdle();
                context.State.ActivePathValid = false;
                context.State.IsMoving = false;
            }
            renewLease(owner, priority);
            context.Situation = "adaptive_nefarian";
            context.Action = hold;
            context.State.LastDecisionHandler = "adaptive_nefarian";
            return BotActionArbitration::Outcome::Committed(
                stopMoving ? "nefarian_movement_held" : "nefarian_leg_lease_renewed");
        };
        context.State.DecisionKernel.Submit(std::move(stop));
    }

    // Claims no resource and never displaces a real action; its only effect
    // is the reason in the decision trace.
    if (!context.AdaptiveNefarianBlocked.empty()
        || !context.AdaptiveNefarianMovementHold.empty())
    {
        std::string const reason = !context.AdaptiveNefarianBlocked.empty()
            ? context.AdaptiveNefarianBlocked
            : context.AdaptiveNefarianMovementHold;
        BotActionArbitration::Candidate hold;
        hold.Key = "adaptive_nefarian:hold:" + reason;
        hold.Source = "adaptive_nefarian";
        hold.ActionPriority = BotActionArbitration::Priority::Idle;
        hold.UtilityScore = 0.0f;
        hold.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::None);
        hold.Attempt = [reason]()
        {
            return BotActionArbitration::Outcome::NotApplicable(reason);
        };
        context.State.DecisionKernel.Submit(std::move(hold));
    }
}

// The route's engagement edge for the kill (round 7). The adaptive Nefarian
// owner replaces the route adapter on the encounter node, so, as Atramedes'
// and Chimaeron's observers do, it carries RememberValidationRouteBossEngagement:
// without it the native death callback rejects the kill
// (gate=combined_rejected), as it did Atramedes' in round 5. Only Nefarian
// (41376, the route target) registers - never Onyxia (41270): the kill credit
// is his - and only while he is landed, in combat and attackable. Observation
// only: it never changes target, focus or movement.
void BotWorldPopulationMgr::SubmitAdaptiveNefarianRouteObservation(BotUpdateContext& context)
{
    auto observe = [this, &context]() -> BotActionArbitration::Outcome
    {
        if (!context.AdaptiveNefarianOwnsNode
            || Cohort().Config.ValidationRouteKind != "boss"
            || Cohort().Config.ValidationRouteNodeId
                != BotEncounter::Nefarian::EncounterNodeId)
            return BotActionArbitration::Outcome::NotApplicable(
                "nefarian_route_observation_not_owned");

        Unit* target = context.Target;
        Creature const* creature = target ? target->ToCreature() : nullptr;
        if (!target || !creature || !target->IsAlive()
            || creature->GetEntry() != BotEncounter::Nefarian::NefarianEntry
            || creature->GetEntry() != Cohort().Config.ValidationRouteTargetEntry
            || !target->IsInCombat()
            || target->IsFlying()
            || !context.Bot->IsValidAttackTarget(target)
            || !IsNativeCombatObserved(context.Bot, target))
            return BotActionArbitration::Outcome::NotApplicable(
                "nefarian_route_observation_wait_for_native_combat");

        RememberValidationRouteBossEngagement(creature);

        bool const targetChanged = context.State.LastDecisionTargetGuid != target->GetGUID();
        bool const firstEngagement = !context.State.WasInCombat;
        if (!targetChanged && !firstEngagement)
            return BotActionArbitration::Outcome::NotApplicable(
                "nefarian_route_observation_already_recorded");

        float const targetHealthPct = UnitHealthPct(target);
        RecordRouteProgress(context.State, context.Bot, target,
            "route_target_combat_progress", targetHealthPct, targetHealthPct, 0, 20);
        Party().ValidationRouteObservedEngagement = true;
        std::string raw = BuildRawJson(context.Bot, target);
        std::string semantic = BuildSemanticJson(context.Bot, target, "adaptive_nefarian",
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
            "adaptive_nefarian_route_observation_recorded");
    };

    BotActionArbitration::Candidate observation;
    observation.Key = "world.validation_route_nefarian_observation";
    observation.Source = "validation_route_observer";
    observation.ActionPriority = BotActionArbitration::Priority::Mechanic;
    observation.UtilityScore = 0.0f;
    observation.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::None);
    observation.Attempt = std::move(observe);
    context.State.DecisionKernel.Submit(std::move(observation));
}
