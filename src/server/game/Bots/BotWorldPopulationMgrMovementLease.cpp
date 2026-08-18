#include "Bots/BotWorldPopulationMgr.h"

#include "ChaseMovementGenerator.h"
#include "MotionMaster.h"
#include "Player.h"
#include "Unit.h"

#include <cmath>
#include <limits>

BotMovementArbitration::Request BotWorldPopulationMgr::BuildMovementRequest(
    Player* bot, BotWorldMovement::Intent const& intent, uint64 nowMs) const
{
    using namespace BotMovementArbitration;

    Request request;
    request.MovementOwner = intent.Owner;
    request.MovementPriority = intent.Priority;
    request.ExpiresAtMs = nowMs + 1500;
    bool const scopedRoute = Cohort().Config.ValidationRouteEnable;
    request.MovementScope = Scope{
        scopedRoute ? Cohort().AttemptId : 0,
        scopedRoute ? uint32(Cohort().Raid.WipeGeneration) : 0,
        scopedRoute ? Party().ValidationRouteGeneration : 0,
        bot ? bot->GetMapId() : std::numeric_limits<uint32>::max(),
        bot ? bot->GetInstanceId() : 0
    };
    request.X = intent.X;
    request.Y = intent.Y;
    request.Z = intent.Z;

    bool const targetAwareChase = intent.DynamicTarget
        && bot
        && intent.DynamicTarget->IsAlive()
        && intent.DynamicTarget->IsInWorld()
        && bot->IsInWorld()
        && intent.DynamicTarget->GetMap() == bot->GetMap();
    request.DynamicTargetGuid = targetAwareChase
        ? intent.DynamicTarget->GetGUID().GetRawValue() : 0;
    return request;
}

BotWorldMovement::ActivePathObservation
BotWorldPopulationMgr::ObserveActiveMovement(
    WorldBotState const& state, Player* bot,
    BotWorldMovement::Intent const& intent,
    BotMovementArbitration::Request const& request) const
{
    BotWorldMovement::ActivePathObservation observation;
    if (!bot)
        return observation;

    bool const scopedRoute = Cohort().Config.ValidationRouteEnable;
    observation.ScopeMatches = !scopedRoute
        || (state.ActivePathAttemptId == request.MovementScope.AttemptId
            && state.ActivePathWipeGeneration
                == request.MovementScope.WipeGeneration
            && state.ActivePathRouteGeneration
                == request.MovementScope.RouteGeneration
            && state.ActivePathRouteNodeId
                == Cohort().Config.ValidationRouteNodeId);

    MotionMaster* motion = bot->GetMotionMaster();
    MovementGeneratorType const nativeActiveMotionType = motion
        ? motion->GetMotionSlotType(MOTION_SLOT_ACTIVE) : MAX_MOTION_TYPE;
    observation.NativePointPathActive = nativeActiveMotionType
        == POINT_MOTION_TYPE;

    bool const targetAwareChase = request.DynamicTargetGuid != 0;
    if (targetAwareChase && nativeActiveMotionType == CHASE_MOTION_TYPE)
        if (MovementGenerator* active = motion->GetMotionSlot(MOTION_SLOT_ACTIVE))
            observation.NativeTargetChaseActive =
                static_cast<ChaseMovementGenerator*>(active)->GetTarget()
                    == intent.DynamicTarget;

    constexpr float ActiveDestinationEpsilon = 0.1f;
    observation.MatchingDestination = targetAwareChase
        ? (observation.NativeTargetChaseActive
            && state.ActivePathTargetGuid
                == intent.DynamicTarget->GetGUID())
        : (state.ActivePathTargetGuid.IsEmpty()
            && std::fabs(intent.X - state.ActivePathToX)
                <= ActiveDestinationEpsilon
            && std::fabs(intent.Y - state.ActivePathToY)
                <= ActiveDestinationEpsilon
            && std::fabs(intent.Z - state.ActivePathToZ)
                <= ActiveDestinationEpsilon);
    return observation;
}
