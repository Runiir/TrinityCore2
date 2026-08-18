#include "Bots/BotWorldPopulationMgr.h"

#include "GameTime.h"
#include "Player.h"

#include <chrono>
#include <string>

namespace
{
uint64 MovementEvidenceNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

bool BotWorldPopulationMgr::RejectMovementPath(
    WorldBotState& state, Player* bot,
    BotWorldMovement::Intent const& intent, char const* reason)
{
    state.ActivePathValid = false;
    state.ActivePathSegmentValid = false;
    state.ActivePathTraversalMode.clear();
    state.ActivePathTargetGuid.Clear();
    state.LastPathRejectReason = reason
        ? reason : "route_destination_unreachable";
    state.LastNoProgressReason = state.LastPathRejectReason;
    state.LastRecoveryResult = state.LastPathRejectReason;
    uint64 const nowMs = MovementEvidenceNowMs();
    state.LastPathChangeMs = nowMs;

    if (Cohort().Config.ValidationRouteEnable && bot)
    {
        if (intent.TerminalOnFailure)
        {
            state.ValidationRouteTerminalState = true;
            state.ValidationRouteTerminalAtMs = nowMs;
            state.ValidationRouteTerminalGeneration =
                Party().ValidationRouteGeneration;
            state.ValidationRouteTerminalReason = state.LastPathRejectReason;
            state.LoopRecoveryCooldownUntilMs = nowMs + 60000;
        }
        std::string const raw = BuildRawJson(bot, nullptr);
        std::string const semantic = BuildSemanticJson(
            bot, nullptr, "validation_route_manifest");
        RecordEvent(state, bot, "validation_route_recovery", nullptr,
            state.LastPathRejectReason.c_str(), raw.c_str(), semantic.c_str(),
            bot->GetExactDist(intent.X, intent.Y, intent.Z),
            Cohort().Config.ValidationRouteTargetEntry);
    }

    return false;
}

void BotWorldPopulationMgr::CommitMovementEvidence(
    WorldBotState& state, Player* bot,
    BotWorldMovement::Intent const& intent,
    BotWorldMovement::PathPlan const& plan,
    BotMovementArbitration::Request const& request, uint64 nowMs)
{
    state.ActivePathFromX = bot->GetPositionX();
    state.ActivePathFromY = bot->GetPositionY();
    state.ActivePathFromZ = bot->GetPositionZ();
    state.ActivePathToX = intent.X;
    state.ActivePathToY = intent.Y;
    state.ActivePathToZ = intent.Z;
    state.ActivePathSegmentValid = !plan.DynamicTarget;
    if (!plan.DynamicTarget)
    {
        state.ActivePathSegmentToX = plan.SegmentX;
        state.ActivePathSegmentToY = plan.SegmentY;
        state.ActivePathSegmentToZ = plan.SegmentZ;
    }
    state.ActivePathTraversalMode = plan.TraversalMode;
    state.ActivePathValid = true;
    state.ActivePathTargetGuid = plan.DynamicTarget
        ? intent.DynamicTarget->GetGUID() : ObjectGuid::Empty;
    state.ActivePathAttemptId = request.MovementScope.AttemptId;
    state.ActivePathWipeGeneration = request.MovementScope.WipeGeneration;
    state.ActivePathRouteGeneration = request.MovementScope.RouteGeneration;
    state.ActivePathRouteNodeId = Cohort().Config.ValidationRouteEnable
        ? Cohort().Config.ValidationRouteNodeId : std::string();
    state.LastPathRejectReason.clear();
    state.LastNoProgressReason.clear();
    state.LastRecoveryMode = plan.TraversalMode;
    state.LastRecoveryResult = "native_movement_submitted";
    state.LastPathChangeMs = nowMs;
    BotMovementArbitration::Apply(state.MovementLease, request);
}
