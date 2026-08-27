#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"

#include "GameTime.h"
#include "MotionMaster.h"
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
}

bool BotWorldPopulationMgr::ExecuteMovementIntent(
    WorldBotState& state, Player* bot,
    BotWorldMovement::Intent const& intent)
{
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
        RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
            MovementExecutorMapId(bot), intent, "active_path", "retained",
            "native_movement_retained");
        return true;
    }

    BotWorldMovement::PathPlan plan;
    if (!PlanMovementPath(bot, intent, plan))
    {
        char const* reason = plan.RejectReason.empty()
            ? "route_destination_unreachable" : plan.RejectReason.c_str();
        RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
            MovementExecutorMapId(bot), intent, "planner_admission", "rejected",
            reason);
        return RejectMovementPath(state, bot, intent,
            reason);
    }

    CommitMovementEvidence(state, bot, intent, plan, request, nowMs);
    state.IsMoving = plan.DynamicTarget;

    // MotionMaster is the independent, set-and-forget movement executor.
    // The caller may continue submitting combat or support intents while this
    // generator advances between decision ticks.
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    if (plan.DynamicTarget)
    {
        if (intent.DynamicTargetRange > 0.0f)
            bot->GetMotionMaster()->MoveChase(intent.DynamicTarget,
                intent.DynamicTargetRange);
        else
            bot->GetMotionMaster()->MoveChase(intent.DynamicTarget);
    }
    else if (plan.NativeLongPath)
        bot->GetMotionMaster()->MovePoint(0, intent.X, intent.Y, intent.Z,
            true);
    else if (std::fabs(plan.SegmentX - intent.X) > 0.1f
        || std::fabs(plan.SegmentY - intent.Y) > 0.1f
        || std::fabs(plan.SegmentZ - intent.Z) > 0.1f)
        bot->GetMotionMaster()->MovePoint(0, plan.SegmentX, plan.SegmentY,
            plan.SegmentZ, true);
    else
        bot->GetMotionMaster()->MovePoint(0, intent.X, intent.Y, intent.Z,
            true);
    RecordMovementPlannerExecutorOutcome(MovementExecutorBotGuid(bot),
        MovementExecutorMapId(bot), intent, "native_path_submission", "submitted",
        "native_movement_submitted");
    return true;
}
