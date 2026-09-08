#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
#include "Bots/BotServerVehicleExitLanding.h"

#include "GameTime.h"
#include "MotionMaster.h"
#include "Movement/Spline/MoveSpline.h"
#include "Player.h"
#include "Unit.h"

#include <chrono>
#include <cmath>

namespace
{
uint64 MovementExecutorNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

uint64 MovementExecutorBotGuid(Player* bot)
{
    return bot ? bot->GetGUID().GetCounter() : 0;
}

uint32 MovementExecutorMapId(Player* bot)
{
    return bot ? bot->GetMapId() : 0;
}

void BindVehicleExitGroundReceipt(
    BotServerVehicleExitLanding::Episode& episode, Player* bot,
    std::uint64_t receiptId)
{
    if (!bot || !episode.ExitPending || !receiptId)
        return;

    BotWorldMovement::NativeMovementProgressObservation const progress =
        BotWorldMovement::MovementProgressDiagnostics().ForReceipt(receiptId);
    BotServerVehicleExitLanding::BindSubmittedGroundReceipt(episode, progress);
}
}

bool BotWorldPopulationMgr::ExecuteMovementIntent(
    WorldBotState& state, Player* bot,
    BotWorldMovement::Intent const& intent)
{
    using namespace BotWorldPopulationMgrBotState::MovementRejectionIsolation;

    state.LastMovementExecution = BotWorldMovement::BeginExecutionObservation(
        intent.X, intent.Y, intent.Z);

    if (!bot)
        return false;
    if (!bot->IsInWorld() || !bot->GetMap())
    {
        RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
            MovementExecutorMapId(bot), intent, "actor_admission", "rejected",
            "route_destination_unreachable");
        return RejectMovementPath(state, bot, intent,
            "route_destination_unreachable");
    }

    if (BotWorldMovement::BlocksNonRecoveryCrossMapMovement(
            intent.Owner, intent.NativeRecoveryCrossMapPending))
    {
        // The recovery brain remains the sole owner of a cross-map entrance
        // transition.  Route/combat callbacks may still be evaluated while a
        // native worldport is pending, but must not submit their instance
        // destination to the source-map floor/Z planner.
        state.LastRecoveryMode = "native_corpse_run";
        state.LastRecoveryResult = "native_recovery_worldport_pending";
        state.LastNoProgressReason = "native_recovery_worldport_pending";
        RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
            MovementExecutorMapId(bot), intent, "cross_map_pending", "rejected",
            "native_recovery_worldport_pending");
        return false;
    }

    uint64 const nowMs = MovementExecutorNowMs();

    // Every ordinary movement producer converges here before lease retention,
    // path planning, or MotionMaster submission.  Keep the future-pack mask
    // out of caller-specific route/formation/combat/hazard branches. Native
    // corpse recovery and an authority-bound current-pack hazard point exit
    // are the only typed exceptions.
    bool const appliesFutureDestinationGuard =
        BotWorldMovement::AppliesValidationRoutePatrolFutureDestinationGuard(
            intent.Owner, intent.DestinationAuthority,
            intent.DynamicTarget != nullptr);
    bool const validationRouteDestinationSafe =
        !appliesFutureDestinationGuard
        || IsValidationRoutePatrolCombatPointSafe(bot, intent.X, intent.Y,
            intent.Z);
    if (BotWorldMovement::EvaluateFutureDestinationGate(intent.Owner,
            intent.DestinationAuthority, intent.DynamicTarget != nullptr,
            validationRouteDestinationSafe)
        == BotWorldMovement::FutureDestinationGateDecision::RejectFuturePack)
    {
        RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
            MovementExecutorMapId(bot), intent, "future_pack_destination",
            "rejected", "route_destination_future_pack_unsafe");

        // This rejection has no planner receipt and never acquired movement
        // ownership. Keep it observable in the planner sidecar above, but do
        // not let it destroy a different owner's admitted native path or the
        // route hazard owner's bounded retry token. With neither state, the
        // ordinary fail-closed rejection below remains authoritative.
        bool const routeHazardRetryArmed = HasArmedRouteHazardRetry(
            true,
            !state.ValidationRouteDodgeCasterGuid.IsEmpty()
                && state.ValidationRouteDodgeSpellId != 0,
            state.ValidationRouteDodgeUntilMs, nowMs, state.ActivePathValid,
            state.LastPathRejectReason);
        if (BotWorldPopulationMgrBotState::
                ApplyPreAdmissionMovementPathRejection(
                    state, intent.Owner,
                    "route_destination_future_pack_unsafe", nowMs,
                    routeHazardRetryArmed)
            == Disposition::ObserveOnlyPreserveExistingOwner)
            return false;

        return RejectMovementPath(state, bot, intent,
            "route_destination_future_pack_unsafe");
    }

    BotMovementArbitration::Request const request = BuildMovementRequest(
        bot, intent, nowMs);
    BotMovementArbitration::Decision const decision =
        BotMovementArbitration::Evaluate(state.MovementLease, request, nowMs);
    if (decision == BotMovementArbitration::Decision::RejectInvalid)
    {
        RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
            MovementExecutorMapId(bot), intent, "movement_lease", "rejected",
            "movement_lease_invalid_scope");
        return RejectMovementPath(state, bot, intent,
            "movement_lease_invalid_scope");
    }
    if (decision == BotMovementArbitration::Decision::PreserveExisting)
    {
        state.LastRecoveryMode = "movement_lease_preserved";
        state.LastRecoveryResult = "higher_priority_movement_active";
        RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
            MovementExecutorMapId(bot), intent, "movement_lease", "preserved",
            "higher_priority_movement_active");
        return false;
    }

    // A player immediately cancels a hard cast when reacting to a lethal
    // ground mechanic. The encounter brain expresses that decision through
    // the Hazard owner/priority pair; the movement service performs only the
    // native interruption required to make the admitted path start now.
    if (BotWorldMovement::InterruptsActiveCast(intent.Owner, intent.Priority)
        && bot->HasUnitState(UNIT_STATE_CASTING))
        bot->InterruptNonMeleeSpells(false);

    BotWorldMovement::ActivePathObservation const active =
        ObserveActiveMovement(state, bot, intent, request);
    if (state.ActivePathValid
        && (state.IsMoving || active.NativePointPathActive
            || active.NativeTargetChaseActive)
        && active.ScopeMatches && active.MatchingDestination)
    {
        if (active.NativePointPathActive || active.NativeTargetChaseActive)
            state.IsMoving = true;
        state.ActivePathToX = intent.X;
        state.ActivePathToY = intent.Y;
        state.ActivePathToZ = intent.Z;
        state.LastRecoveryMode = "native_active_path";
        state.LastRecoveryResult = "native_movement_retained";
        BotMovementArbitration::Apply(state.MovementLease, request);
        state.LastMovementExecution.Disposition =
            BotWorldMovement::ExecutionDisposition::Retained;
        RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
            MovementExecutorMapId(bot), intent, "active_path", "retained",
            "native_movement_retained");
        return true;
    }

    BotWorldMovement::PathPlan plan;
    plan.LaunchReceiptId = BeginMovementPlannerReceipt(
        MovementExecutorBotGuid(bot), MovementExecutorMapId(bot), intent,
        request.MovementScope, request.DynamicTargetGuid,
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(),
        Cohort().Config.ValidationRouteEnable);
    bool const planned = PlanMovementPath(bot, intent, plan);
    state.LastMovementExecution = plan.Execution;
    if (!planned)
    {
        char const* reason = plan.RejectReason.empty()
            ? "route_destination_unreachable" : plan.RejectReason.c_str();
        RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
            MovementExecutorMapId(bot), intent, "planner_admission", "rejected",
            reason, plan.LaunchReceiptId);
        return RejectMovementPath(state, bot, intent,
            reason);
    }

    CommitMovementEvidence(state, bot, intent, plan, request, nowMs);
    bool const aerialGhostRecovery = plan.NativeLongPath
        && BotWorldMovement::UsesNativeRecoveryGhostFlight(
            intent.Owner, intent.AllowNativeLongPath,
            state.NativeRecoveryGhostFlightEnabled);
    // A point spline is already the bot's native movement state as soon as it
    // is submitted.  Keep that same-tick observation visible to the combat
    // resolver so a cast-time spender cannot cancel a newly admitted hazard
    // escape before Trinity reports UNIT_STATE_MOVING on the next update.
    state.IsMoving = true;

    // MotionMaster is the independent, set-and-forget movement executor.
    // The caller may continue submitting combat or support intents while this
    // generator advances between decision ticks.
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    auto submitPoint = [&](float x, float y, float z, bool generatePath)
    {
        BotWorldMovement::RecordNativePathSubmission(plan.LaunchReceiptId,
            MovementExecutorBotGuid(bot), MovementExecutorMapId(bot),
            bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(),
            x, y, z, generatePath);
        Movement::NativePathLaunchContext const launchContext =
            BotWorldMovement::NativePathLaunchContextForReceipt(
                plan.LaunchReceiptId,
                MovementExecutorBotGuid(bot), MovementExecutorMapId(bot));
        bot->GetMotionMaster()->MovePoint(0, x, y, z, generatePath, 0.0f,
            launchContext);
        if (Cohort().Config.ValidationRouteEnable)
        {
            bool const splineInitialized = bot->movespline
                && bot->movespline->Initialized();
            G3D::Vector3 const splineFinal = splineInitialized
                ? bot->movespline->FinalDestination() : G3D::Vector3();
            BotWorldMovement::ArmMovementProgressReceipt(plan.LaunchReceiptId,
                MovementExecutorBotGuid(bot), MovementExecutorMapId(bot),
                splineInitialized,
                splineInitialized ? bot->movespline->GetId() : 0,
                splineFinal.x, splineFinal.y, splineFinal.z, nowMs);
            if (state.ServerProvisioned && generatePath && !aerialGhostRecovery)
            {
                BotServerVehicleExitLanding::RememberGroundPointSubmission(
                    state.ServerVehicleExitLanding, plan.LaunchReceiptId,
                    MovementExecutorBotGuid(bot), MovementExecutorMapId(bot),
                    bot->GetInstanceId(), nowMs, request.MovementScope);
                BindVehicleExitGroundReceipt(
                    state.ServerVehicleExitLanding, bot,
                    plan.LaunchReceiptId);
            }
        }
    };
    if (plan.DynamicTarget)
    {
        if (intent.DynamicTargetRange > 0.0f)
            bot->GetMotionMaster()->MoveChase(intent.DynamicTarget,
                intent.DynamicTargetRange);
        else
            bot->GetMotionMaster()->MoveChase(intent.DynamicTarget);
    }
    else if (aerialGhostRecovery)
    {
        if (!bot->CanFly())
            bot->SetCanFly(true);
        if (!bot->IsGravityDisabled())
        {
            bot->SetDisableGravity(true);
            state.NativeRecoveryGhostGravityDisabled = true;
        }
        // Use the same persistent point generator used by ordinary playerbot
        // movement.  The previous two-point GenericMovementGenerator could
        // finalize immediately while the recovery state continued to retain
        // it as an active path, leaving a ghost stationary at the graveyard.
        // Flight and gravity flags make this a direct native aerial spline;
        // generatePath=false avoids asking the ground navmesh to route it.
        submitPoint(intent.X, intent.Y, intent.Z, false);
        bool const pointGeneratorActive =
            bot->GetMotionMaster()->GetMotionSlotType(MOTION_SLOT_ACTIVE)
                == POINT_MOTION_TYPE
            && !bot->movespline->Finalized();
        if (!pointGeneratorActive)
        {
            state.LastMovementExecution.Disposition =
                BotWorldMovement::ExecutionDisposition::Rejected;
            RecordMovementPlannerExecutorOutcome(
                MovementExecutorBotGuid(bot), MovementExecutorMapId(bot), intent,
                "native_aerial_point_submission", "rejected",
                "native_aerial_point_generator_inactive",
                plan.LaunchReceiptId);
            return RejectMovementPath(state, bot, intent,
                "native_aerial_point_generator_inactive");
        }
        RecordMovementPlannerExecutorOutcome(
            MovementExecutorBotGuid(bot), MovementExecutorMapId(bot), intent,
            "native_aerial_point_submission", "submitted",
            "native_aerial_point_movement_submitted", plan.LaunchReceiptId);
        state.LastMovementExecution.Disposition =
            BotWorldMovement::ExecutionDisposition::Submitted;
        state.LastMovementExecution.NativeSubmitted = true;
        return true;
    }
    else if (plan.NativeLongPath)
        submitPoint(intent.X, intent.Y, intent.Z, true);
    else if (std::fabs(plan.SegmentX - intent.X) > 0.1f
        || std::fabs(plan.SegmentY - intent.Y) > 0.1f
        || std::fabs(plan.SegmentZ - intent.Z) > 0.1f)
        submitPoint(plan.SegmentX, plan.SegmentY, plan.SegmentZ, true);
    else
        submitPoint(intent.X, intent.Y, intent.Z, true);
    state.LastMovementExecution.Disposition =
        BotWorldMovement::ExecutionDisposition::Submitted;
    state.LastMovementExecution.NativeSubmitted = true;
    RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
        MovementExecutorMapId(bot), intent, "native_path_submission", "submitted",
        "native_movement_submitted", plan.LaunchReceiptId);
    return true;
}
