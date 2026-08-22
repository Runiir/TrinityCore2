#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotExperienceLearningPolicy.h"
#include "Map.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Unit.h"
#include "Util.h"

#include <array>
#include <cmath>

bool BotWorldPopulationMgr::PlanMovementPath(
    Player* bot, BotWorldMovement::Intent const& intent,
    BotWorldMovement::PathPlan& plan) const
{
    plan = {};

    auto reject = [&](char const* reason)
    {
        plan.RejectReason = reason ? reason : "route_destination_unreachable";
        return false;
    };

    if (!bot || !bot->IsInWorld() || !bot->GetMap())
        return reject("route_destination_unreachable");

    bool const targetAwareChase = intent.DynamicTarget
        && intent.DynamicTarget->IsAlive()
        && intent.DynamicTarget->IsInWorld()
        && intent.DynamicTarget->GetMap() == bot->GetMap();
    plan.DynamicTarget = targetAwareChase;
    if (targetAwareChase)
    {
        // Dynamic targets are deliberately handed to Trinity's native chase
        // generator.  No fixed-point path is invented for a moving unit.
        plan.SegmentX = intent.X;
        plan.SegmentY = intent.Y;
        plan.SegmentZ = intent.Z;
        plan.TraversalMode = "native_target_chase";
        plan.Selected = true;
        return true;
    }

    bool const nativeLongPathRecovery = intent.AllowNativeLongPath
        && intent.Owner == BotMovementArbitration::Owner::Recovery;
    if (nativeLongPathRecovery)
    {
        // This is deliberately an intent-only admission.  The recovery brain
        // submits the same typed Move used for an ordinary player request;
        // only the movement executor below owns MotionMaster and submits the
        // final destination with native path generation.  Native pathing is
        // allowed to take a winding route here, so a segment need not reduce
        // straight-line distance to the entrance trigger.
        plan.SegmentX = intent.X;
        plan.SegmentY = intent.Y;
        plan.SegmentZ = intent.Z;
        plan.TraversalMode = "native_long_path";
        plan.NativeLongPath = true;
        plan.Selected = true;
        return true;
    }

    float segmentX = intent.X;
    float segmentY = intent.Y;
    float segmentZ = intent.Z;
    char const* traversalMode = "native_complete_path";
    bool segmentSelected = false;
    bool const progressiveStaticRoute = intent.AllowProgressiveSegments;
    bool const strictNativeDescent = intent.RequireCompletePath;
    float const floorZ = bot->GetMap()->GetHeight(bot->GetPhaseShift(),
        intent.X, intent.Y, intent.Z + 2.0f, true, 8.0f);
    bool const targetFloorValid = floorZ > INVALID_HEIGHT;
    // A progressive route can still make a validated local step when its
    // final native runback target has no floor sample in the current map
    // state.  Complete-path and strict-descent intents remain fail-closed at
    // the target-floor gate.
    if (!targetFloorValid && (!progressiveStaticRoute || strictNativeDescent))
        return reject("route_destination_invalid_floor");
    if (targetFloorValid && std::fabs(floorZ - intent.Z) > 4.0f)
        return reject("route_destination_invalid_z_transition");
    float const currentGoalDistance = bot->GetExactDist(intent.X, intent.Y,
        intent.Z);

    auto distanceToGoal = [intent](float candidateX, float candidateY,
        float candidateZ)
    {
        float const dx = candidateX - intent.X;
        float const dy = candidateY - intent.Y;
        float const dz = candidateZ - intent.Z;
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    };

    auto selectProgressEndpoint = [&](PathGenerator const& candidatePath,
        char const* candidateMode, float minimumProgress)
    {
        PathType const candidateType = candidatePath.GetPathType();
        if ((candidateType & PATHFIND_NOPATH)
            || (candidateType & PATHFIND_NOT_USING_PATH)
            || (candidateType & PATHFIND_SHORTCUT)
            || (candidateType & PATHFIND_FARFROMPOLY_START))
            return false;
        if (!(candidateType & (PATHFIND_NORMAL | PATHFIND_INCOMPLETE)))
            return false;

        G3D::Vector3 const& endpoint = candidatePath.GetActualEndPosition();
        float const endpointFloorZ = bot->GetMap()->GetHeight(
            bot->GetPhaseShift(), endpoint.x, endpoint.y, endpoint.z + 2.0f,
            true, 8.0f);
        if (endpointFloorZ <= INVALID_HEIGHT
            || std::fabs(endpointFloorZ - endpoint.z) > 1.5f)
            return false;
        float const endpointTravel = bot->GetExactDist(endpoint.x, endpoint.y,
            endpoint.z);
        float const endpointGoalDistance = distanceToGoal(endpoint.x,
            endpoint.y, endpoint.z);
        if (endpointTravel < 1.5f
            || endpointGoalDistance + minimumProgress >= currentGoalDistance)
            return false;

        segmentX = endpoint.x;
        segmentY = endpoint.y;
        segmentZ = endpoint.z;
        traversalMode = candidateMode;
        segmentSelected = true;
        return true;
    };

    PathGenerator path(bot);
    bool const pathOk = path.CalculatePath(intent.X, intent.Y, intent.Z,
        false);
    PathType const pathType = path.GetPathType();
    if (targetFloorValid && pathOk && (pathType & PATHFIND_NORMAL)
        && !(pathType & PATHFIND_NOPATH)
        && !(pathType & PATHFIND_NOT_USING_PATH)
        && !(pathType & PATHFIND_SHORTCUT)
        && !(pathType & PATHFIND_FARFROMPOLY)
        && !(pathType & PATHFIND_INCOMPLETE))
        segmentSelected = true;
    else if (!strictNativeDescent && progressiveStaticRoute
        && pathOk && (pathType & PATHFIND_INCOMPLETE))
        selectProgressEndpoint(path, "native_partial_path", 3.0f);

    // An incomplete route may still make deterministic local progress.  The
    // chosen endpoint is always mmap-validated and must reduce goal distance;
    // a straight-line shortcut is never submitted.
    if (!segmentSelected && progressiveStaticRoute && !strictNativeDescent)
    {
        float const baseAngle = bot->GetAngle(intent.X, intent.Y);
        std::array<float, 7> const angleOffsets{
            0.0f, float(M_PI) / 6.0f, -float(M_PI) / 6.0f,
            float(M_PI) / 3.0f, -float(M_PI) / 3.0f,
            float(M_PI) / 2.0f, -float(M_PI) / 2.0f
        };
        std::array<float, 2> const stepDistances{ 12.0f, 7.0f };
        float bestGoalDistance = currentGoalDistance;
        float bestX = 0.0f;
        float bestY = 0.0f;
        float bestZ = 0.0f;
        bool foundWalkableStep = false;
        for (float stepDistance : stepDistances)
        {
            for (float angleOffset : angleOffsets)
            {
                float const angle = baseAngle + angleOffset;
                float const candidateX = bot->GetPositionX()
                    + std::cos(angle) * stepDistance;
                float const candidateY = bot->GetPositionY()
                    + std::sin(angle) * stepDistance;
                float const candidateZ = bot->GetMap()->GetHeight(
                    bot->GetPhaseShift(), candidateX, candidateY,
                    bot->GetPositionZ() + 2.0f, true, 8.0f);
                if (candidateZ <= INVALID_HEIGHT
                    || std::fabs(candidateZ - bot->GetPositionZ()) > 4.0f)
                    continue;

                PathGenerator stepPath(bot);
                if (!stepPath.CalculatePath(candidateX, candidateY,
                    candidateZ, false))
                    continue;
                PathType const stepType = stepPath.GetPathType();
                if ((stepType & PATHFIND_NOPATH)
                    || (stepType & PATHFIND_NOT_USING_PATH)
                    || (stepType & PATHFIND_SHORTCUT)
                    || (stepType & PATHFIND_FARFROMPOLY_START)
                    || !(stepType & (PATHFIND_NORMAL | PATHFIND_INCOMPLETE)))
                    continue;

                G3D::Vector3 const& endpoint = stepPath.GetActualEndPosition();
                float const endpointTravel = bot->GetExactDist(endpoint.x,
                    endpoint.y, endpoint.z);
                float const endpointGoalDistance = distanceToGoal(endpoint.x,
                    endpoint.y, endpoint.z);
                if (endpointTravel < 1.5f
                    || endpointGoalDistance + 2.0f >= currentGoalDistance
                    || endpointGoalDistance >= bestGoalDistance)
                    continue;

                foundWalkableStep = true;
                bestGoalDistance = endpointGoalDistance;
                bestX = endpoint.x;
                bestY = endpoint.y;
                bestZ = endpoint.z;
            }
        }
        if (foundWalkableStep)
        {
            segmentX = bestX;
            segmentY = bestY;
            segmentZ = bestZ;
            traversalMode = "native_walkable_step";
            segmentSelected = true;
        }
    }

    if (!segmentSelected)
    {
        if (strictNativeDescent && !bot->IsInCombat())
            return reject("native_descent_complete_path_required");
        if (!targetFloorValid)
            return reject("route_destination_invalid_floor");
        if (!pathOk || (pathType & PATHFIND_NOPATH))
            return reject("route_destination_unreachable");
        if (pathType & PATHFIND_NOT_USING_PATH)
            return reject("route_destination_missing_mmap");
        if (pathType & PATHFIND_INCOMPLETE)
            return reject("route_destination_partial_path");
        if (pathType & PATHFIND_SHORTCUT)
            return reject("route_destination_shortcut_path");
        if (pathType & PATHFIND_FARFROMPOLY)
            return reject("route_destination_off_mesh");
        return reject("route_destination_unreachable");
    }

    BotLearnedScore const pathScore = BotExperienceLearningPolicy::ScorePath(
        bot, bot->GetPositionX(), bot->GetPositionY(), intent.X, intent.Y,
        Cohort().LearningConfig);
    bool const recentFailureMemory = IsFailedPathRecently(
        bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetPositionX(),
        bot->GetPositionY(), intent.X, intent.Y)
        || pathScore.Penalty >= Cohort().LearningConfig.RecentFailurePenaltyWeight;
    plan.RecentFailure = recentFailureMemory;
    if (recentFailureMemory && !intent.AllowRecentFailureRetry)
        return reject("route_destination_recently_failed");

    plan.SegmentX = segmentX;
    plan.SegmentY = segmentY;
    plan.SegmentZ = segmentZ;
    plan.TraversalMode = traversalMode;
    plan.Selected = true;
    return true;
}
