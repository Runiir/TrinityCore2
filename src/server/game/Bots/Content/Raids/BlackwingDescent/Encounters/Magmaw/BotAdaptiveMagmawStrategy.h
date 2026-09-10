#ifndef TRINITY_BOT_ADAPTIVE_MAGMAW_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_MAGMAW_STRATEGY_H
#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawParasitePolicy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCrashSideMovement.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDirectionalMobilityPolicy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMangleSupportGeometry.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementIntents.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawObservations.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPersonalParasiteEscapeTask.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawSupportTargetOpportunity.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <string>
#include <string_view>
#include <vector>
namespace BotEncounter
{
struct MagmawRetainedFormationPath
{
    bool PurposeValid = false;
    std::string_view Purpose;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    std::string_view NodeId;
};

struct AdaptiveMagmawPlan
{
    bool OwnsNode = false;
    bool ReleaseRetainedRangedFormation = false;
    bool ClearOptionalDamageTarget = false;
    bool SuppressOffense = false;
    std::string_view SuppressReason;
    MagmawParasiteCombatContract ParasiteCombat;
    ObjectGuid DamageTarget;
    ObjectGuid PriorityHealTarget;
    MagmawMovementIntentCollection Movement;
    std::optional<BotNativeAction::Candidate> DirectionalMobility;
    std::optional<BotNativeAction::Candidate> Interaction;
};
class AdaptiveMagmawStrategy
{
public:
    using MovementProducerOrder = std::array<MagmawMovementProposalOrigin, 4>;
    static constexpr MovementProducerOrder DefaultMovementProducerOrder{
        MagmawMovementProposalOrigin::Hazard,
        MagmawMovementProposalOrigin::HookPreposition,
        MagmawMovementProposalOrigin::HookApproach,
        MagmawMovementProposalOrigin::FormationRestore };
    static constexpr uint32 BossEntry = 41570;
    static constexpr uint32 HeadEntry = 42347;
    static constexpr uint32 PillarEntry = 41843;
    static constexpr uint32 ParasiteEntry = 41806;
    static constexpr uint32 ParasiteAltEntry = 42321;
    static constexpr uint32 PersistentCrashDummyEntry = 47330;
    static constexpr uint32 RoomStalkerEntry = 47196;
    static constexpr uint32 PincerLeftEntry = 41620;
    static constexpr uint32 PincerRightEntry = 41789;
    static constexpr uint32 SpikeEntry = 41767;
    static constexpr float HookInteractionDistance = 5.0f;
    static constexpr float RangedStackDistance = 30.0f;
    // Keep the fixed bait corridor outside the support/boss stack.  The
    // support anchor is intentionally close to Magmaw; with a 30-yard lane
    // center and 24-yard lateral offset this leaves 22 yards of clearance
    // across the complete left/right chord instead of only at its endpoints.
    static constexpr float SupportStackDistance = 8.0f;
    // The two bait endpoints must be outside the support stack while still
    // leaving a full left/right lane for the mobile team to cross.
    static constexpr float RangedStackLateralOffset = 24.0f;
    static constexpr float RangedStackTolerance = 4.0f;
    static constexpr float MangleSupportMaxDistance = 35.0f;
    static constexpr float ParasiteKiteLeadDistance =
        MagmawParasitePolicy::KiteLeadDistance;
    static constexpr float RangedParasiteTargetDistance = RangedStackDistance
        + RangedStackLateralOffset +
        MagmawParasitePolicy::SafeClearance;
    static constexpr float RangedParasiteSupportTargetDistance =
        RangedStackDistance;
    AdaptiveMagmawPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role,
        BotMovementArbitration::Lease const* movementLease = nullptr,
        bool activePathValid = false, bool moving = false,
        MagmawLaneTransitionState* laneTransition = nullptr,
        MagmawParasiteHazardState* hazardState = nullptr,
        MagmawEventMovementTransitionState* eventMovement = nullptr,
        std::optional<MagmawDirectionalMobilityInput> const& mobility =
            std::nullopt,
        MovementProducerOrder const& producerOrder =
            DefaultMovementProducerOrder,
        MagmawFacts const* facts = nullptr,
        MagmawPersonalParasiteEscapeTask* personalEscapeTask = nullptr,
        MagmawParasiteWaveTask* parasiteWaveTask = nullptr,
        MagmawRetainedFormationPath const* retainedPath = nullptr,
        MagmawSupportTargetOpportunities const* supportOpportunities =
            nullptr) const
    {
        AdaptiveMagmawPlan plan;
        if (board.Route.NodeId != "bwd.magmaw.encounter")
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (personalEscapeTask && bot)
            personalEscapeTask->ObserveActorLife(board, botGuid, bot->Alive);
        if (!bot || !bot->Alive)
            return plan;
        if (eventMovement)
        {
            eventMovement->ObserveScope(board, botGuid);
            eventMovement->ObserveArrival(bot->Position);
        }
        if (hazardState)
        {
            hazardState->ObserveScope(board, botGuid);
            hazardState->ObserveNativeProgress(board, bot->Position,
                MagmawParasitePolicy::DestinationTolerance,
                MagmawParasitePolicy::SafeClearance);
        }
        if (laneTransition)
        {
            laneTransition->ObserveScope(board);
            std::pair<ObjectGuid, ObjectGuid> const baiters =
                MagmawParasitePolicy::ResolveFixedBaiters(board);
            laneTransition->AssignBaiters(baiters.first, baiters.second);
            laneTransition->ObserveArrival(botGuid, bot->Position,
                MagmawParasitePolicy::DestinationTolerance, board.Revision);
            if (!HasLivingParasite(board) && !HasActivePillar(board))
                // Event A may despawn between the native arrival and this
                // observation. Seal that boundary explicitly as (0, 0), so
                // the first later event is retired instead of being captured
                // as if it were the arrival generation.
                laneTransition->SealNoMechanicArrival(board.Revision);
        }
        MagmawActorObservation const observed = ObserveMagmawActors(board, *bot,
            supportOpportunities);
        if (!observed.Boss)
            return plan;
        plan.OwnsNode = true;
        ActorSnapshot const* mangleOwner = FindMangleOwner(board);
        if (mangleOwner)
            plan.PriorityHealTarget = mangleOwner->Guid;
        plan.ParasiteCombat.Active = true;
        plan.ParasiteCombat.ActorGuid = botGuid;
        std::pair<ObjectGuid, ObjectGuid> const baiters =
            MagmawParasitePolicy::ResolveFixedBaiters(board);
        plan.ParasiteCombat.FireMageGuid = baiters.first;
        plan.ParasiteCombat.MarksmanshipHunterGuid = baiters.second;
        BindParasiteDamageTargets(*bot, role, observed, plan.ParasiteCombat);
        PrepullDecision prepull = EvaluatePrepull(board, *observed.Boss);
        if (IsPrepull(board, *observed.Boss))
        {
            std::optional<MagmawRangedAnchors> const anchors =
                ResolveRangedAnchors(board, *observed.Boss);
            if (anchors && !RangedGroupStaged(board, *anchors))
            {
                plan.SuppressOffense = true;
                plan.SuppressReason = "prepull_formation_staging";
                if (role != "tank")
                    plan.Movement.Propose(
                        MagmawMovementProposalOrigin::PrepullFormation,
                        BuildPointMovement(board,
                            FormationAnchor(board, *anchors, botGuid),
                            "prepull_ranged_stage",
                            BotActionArbitration::Priority::Mechanic,
                            325.0f));
                return plan;
            }
            if (prepull.Disposition == PrepullDisposition::HoldOffense)
            {
                plan.SuppressOffense = true;
                plan.SuppressReason = "prepull_health_recovery";
                return plan;
            }
            if (!IsDesignatedPullTank(board, botGuid, role))
            {
                plan.SuppressOffense = true;
                plan.SuppressReason = "prepull_pull_owner_wait";
                return plan;
            }
        }
        plan.DamageTarget = SelectDamageTarget(observed, botGuid, role,
            bot->ClassSpec,
            plan.ParasiteCombat);
        plan.ClearOptionalDamageTarget = plan.DamageTarget.IsEmpty()
            && observed.SupportOpportunitiesObserved;
        MagmawHookAssignment const hookAssignment = ResolveHookAssignment(
            board, *bot, botGuid);
        bool const pincerWarning = PincerWarningObserved(board);
        bool const pincerWindow = PincerCommitmentActive(hookAssignment,
            *observed.Boss, pincerWarning);
        plan.Interaction = ProposeHookInteraction(board, *bot, *observed.Boss,
            botGuid);
        bool crashSideHold = false;
        std::optional<BotNativeAction::Candidate> hazard =
            ProposeHazardMovement(board, *bot, *observed.Boss,
            pincerWindow, pincerWarning, movementLease, laneTransition,
            hazardState, eventMovement, mobility, &plan.DirectionalMobility,
            &crashSideHold);
        std::optional<BotNativeAction::Candidate> hookPreposition;
        std::optional<BotNativeAction::Candidate> hookApproach;
        if (!crashSideHold)
        {
            hookPreposition = ProposeHookPreposition(board, *bot,
                *observed.Boss, botGuid);
            hookApproach = ProposeHookApproach(board, *bot, *observed.Boss,
                botGuid);
        }
        bool const holdHeadPosition = observed.Head
            && plan.DamageTarget == observed.Head->Guid && !hazard && !hookPreposition && !hookApproach
            && !plan.Interaction && !plan.DirectionalMobility
            && !crashSideHold && !pincerWindow && !pincerWarning
            && !HasActivePillar(board)
            && (!HasLivingParasite(board) || !IsPillarBaiter(board, botGuid))
            && !HasActiveHazardPath(board, movementLease, activePathValid, moving)
            && InConfiguredHeadRange(board, *bot, observed.Head, role);
        plan.ReleaseRetainedRangedFormation = holdHeadPosition
            && activePathValid && retainedPath && retainedPath->PurposeValid
            && retainedPath->Purpose == "ranged_formation_restore"
            && retainedPath->NodeId == board.CurrentScope.NodeId
            && retainedPath->AttemptId == board.CurrentScope.AttemptId
            && retainedPath->WipeGeneration == board.CurrentScope.WipeGeneration
            && retainedPath->RouteGeneration == board.CurrentScope.RouteGeneration
            && movementLease
            && movementLease->MovementOwner == BotMovementArbitration::Owner::Mechanic
            && BotMovementArbitration::SameScope(movementLease->MovementScope,
                { board.CurrentScope.AttemptId, board.CurrentScope.WipeGeneration,
                    board.CurrentScope.RouteGeneration, board.CurrentScope.MapId,
                    board.CurrentScope.InstanceId });
        std::optional<BotNativeAction::Candidate> formationRestore;
        if (!holdHeadPosition && !crashSideHold && !pincerWindow && !pincerWarning
            && !(IsPillarBaiter(board, botGuid) && HasActivePillar(board))
            && (!HasLivingParasite(board) || !IsPillarBaiter(board, botGuid))
            && !HasActiveHazardPath(board, movementLease, activePathValid,
                moving))
            formationRestore = ProposeRangedFormationRestore(board, *bot,
                *observed.Boss, role);
        for (MagmawMovementProposalOrigin origin : producerOrder)
        {
            std::optional<BotNativeAction::Candidate>* proposal = nullptr;
            switch (origin)
            {
                case MagmawMovementProposalOrigin::Hazard:
                    proposal = &hazard;
                    break;
                case MagmawMovementProposalOrigin::HookPreposition:
                    proposal = &hookPreposition;
                    break;
                case MagmawMovementProposalOrigin::HookApproach:
                    proposal = &hookApproach;
                    break;
                case MagmawMovementProposalOrigin::FormationRestore:
                    proposal = &formationRestore;
                    break;
                case MagmawMovementProposalOrigin::PrepullFormation:
                case MagmawMovementProposalOrigin::TransferLaneTask:
                    break;
            }
            if (proposal && *proposal)
                plan.Movement.Propose(origin, std::move(**proposal));
        }
        EmitPersonalParasiteEscape(board, *bot, observed, facts,
            personalEscapeTask, parasiteWaveTask, hazardState, plan.Movement);
        if (!plan.Movement.Empty())
            plan.ReleaseRetainedRangedFormation = false;
        return plan;
    }
private:
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategySupport.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategyHazard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategyHook.h"

};
}

#endif
