#include "Bots/BotWorldPopulationMgr.h"

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
}

bool BotWorldPopulationMgr::ExecuteMovementIntent(
    WorldBotState& state, Player* bot,
    BotWorldMovement::Intent const& intent)
{
    if (!bot)
        return false;
    if (!bot->IsInWorld() || !bot->GetMap())
        return RejectMovementPath(state, bot, intent,
            "route_destination_unreachable");

    uint64 const nowMs = MovementExecutorNowMs();
    BotMovementArbitration::Request const request = BuildMovementRequest(
        bot, intent, nowMs);
    BotMovementArbitration::Decision const decision =
        BotMovementArbitration::Evaluate(state.MovementLease, request, nowMs);
    if (decision == BotMovementArbitration::Decision::RejectInvalid)
        return RejectMovementPath(state, bot, intent,
            "movement_lease_invalid_scope");
    if (decision == BotMovementArbitration::Decision::PreserveExisting)
    {
        state.LastRecoveryMode = "movement_lease_preserved";
        state.LastRecoveryResult = "higher_priority_movement_active";
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
        BotMovementArbitration::Apply(state.MovementLease, request);
        return true;
    }

    BotWorldMovement::PathPlan plan;
    if (!PlanMovementPath(bot, intent, plan))
        return RejectMovementPath(state, bot, intent,
            plan.RejectReason.empty() ? "route_destination_unreachable"
                                      : plan.RejectReason.c_str());

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
    return true;
}
