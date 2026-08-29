#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotExperienceLearningPolicy.h"
#include "Bots/BotWorldPopulationMgrNativePathAdmission.h"
#include "Bots/BotWorldPopulationMgrNativePathValidation.h"
#include "Bots/BotWorldPopulationMgrMovementPathSelection.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Map.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>
#include <array>
#include <cmath>

namespace
{
uint64 PlannerBotGuid(Player* bot)
{
    return bot ? bot->GetGUID().GetCounter() : 0;
}

uint32 PlannerBotMapId(Player* bot)
{
    return bot ? bot->GetMapId() : 0;
}
}

bool BotWorldPopulationMgr::PlanMovementPath(
    Player* bot, BotWorldMovement::Intent const& intent,
    BotWorldMovement::PathPlan& plan) const
{
    plan = {};

    float sampledTargetFloorZ = 0.0f;
    bool targetFloorSampled = false;
    bool targetFloorValid = false;
    BotWorldMovement::NativePathProofObservation nativeProof;

    auto reject = [&](char const* reason, char const* gate)
    {
        plan.RejectReason = reason ? reason : "route_destination_unreachable";
        RecordMovementPlannerOutcome(PlannerBotGuid(bot), PlannerBotMapId(bot),
            intent, targetFloorSampled, sampledTargetFloorZ, targetFloorValid,
            gate, false, plan.RejectReason.c_str(), &nativeProof);
        return false;
    };

    if (!bot || !bot->IsInWorld() || !bot->GetMap())
        return reject("route_destination_unreachable", "actor_admission");

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
        RecordMovementPlannerOutcome(PlannerBotGuid(bot), PlannerBotMapId(bot),
            intent, targetFloorSampled, sampledTargetFloorZ, targetFloorValid,
            "dynamic_target_chase", true, nullptr);
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
        RecordMovementPlannerOutcome(PlannerBotGuid(bot), PlannerBotMapId(bot),
            intent, targetFloorSampled, sampledTargetFloorZ, targetFloorValid,
            "native_long_path", true, nullptr);
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
    targetFloorSampled = true;
    sampledTargetFloorZ = floorZ;
    targetFloorValid = floorZ > INVALID_HEIGHT;
    bool const sameLevelDeclaredFloorFallback = targetFloorValid
        && BotWorldMovement::AdmitSameLevelDeclaredFloorFallback(
            bot->GetPositionZ(), intent.Z, floorZ);
    std::optional<float> pathReferenceFloorZ = intent.ReferenceFloorZ;
    if (!pathReferenceFloorZ && sameLevelDeclaredFloorFallback)
        pathReferenceFloorZ = bot->GetPositionZ();
    // A progressive route can still make a validated local step when its
    // final native runback target has no floor sample in the current map
    // state.  Complete-path and strict-descent intents remain fail-closed at
    // the target-floor gate.
    if (!targetFloorValid && (!progressiveStaticRoute || strictNativeDescent))
        return reject("route_destination_invalid_floor", "target_floor");
    // GetHeight can resolve the neighboring floor at a multi-level static
    // route waypoint.  Let native mmap admission arbitrate that mismatch for
    // progressive routes, while strict and ordinary movement stay fail-closed.
    if (targetFloorValid && std::fabs(floorZ - intent.Z) > 4.0f
        && !sameLevelDeclaredFloorFallback
        && (!progressiveStaticRoute || strictNativeDescent))
        return reject("route_destination_invalid_z_transition",
            "target_z_transition");
    float const currentGoalDistance = bot->GetExactDist(intent.X, intent.Y,
        intent.Z);
    bool const sameLevelLocalMechanicProgress =
        BotWorldMovement::AllowsSameLevelLocalMechanicProgress(intent.Owner,
            sameLevelDeclaredFloorFallback, currentGoalDistance,
            strictNativeDescent, intent.AllowNativeLongPath,
            intent.BoundedHazardProgress);
    bool const progressivePathAdmission = progressiveStaticRoute
        || sameLevelLocalMechanicProgress;

    auto distanceToGoal = [intent](float candidateX, float candidateY,
        float candidateZ)
    {
        float const dx = candidateX - intent.X;
        float const dy = candidateY - intent.Y;
        float const dz = candidateZ - intent.Z;
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    };

    auto nativePointFloorValid = [bot, &pathReferenceFloorZ](
        G3D::Vector3 const& point)
    {
        if (pathReferenceFloorZ)
            return BotWorldMovement::NativePathPointFloorValid(bot, point,
                *pathReferenceFloorZ, true);
        return BotWorldMovement::NativePathPointFloorValid(bot, point);
    };

    auto nativeEndpointFloorValid = [bot, &pathReferenceFloorZ](
        PathGenerator const& candidatePath)
    {
        if (pathReferenceFloorZ)
            return BotWorldMovement::NativePathPointFloorValid(bot,
                candidatePath.GetActualEndPosition(), *pathReferenceFloorZ,
                true);
        return BotWorldMovement::NativePathEndpointFloorValid(bot,
            candidatePath);
    };

    auto diagnoseNativePathFloors = [bot, &pathReferenceFloorZ](
        PathGenerator const& candidatePath)
    {
        if (pathReferenceFloorZ)
            return BotWorldMovement::DiagnoseNativePathFloors(bot,
                candidatePath,
                *pathReferenceFloorZ, true);
        return BotWorldMovement::DiagnoseNativePathFloors(bot, candidatePath,
            0.0f, false);
    };

    auto diagnoseCompleteNativePath = [&](bool calculated,
        PathGenerator const& candidatePath, G3D::Vector3 const& requested)
    {
        return BotWorldMovement::DiagnoseCompleteNativePathProof(calculated,
            candidatePath, requested, nativeEndpointFloorValid,
            diagnoseNativePathFloors);
    };

    auto completeNativePathToPoint = [&](G3D::Vector3 const& point,
        G3D::Vector3& verifiedEndpoint,
        BotWorldMovement::NativePathProofObservation& observation)
    {
        PathGenerator proofPath(bot);
        bool const pathOk = proofPath.CalculatePath(point.x, point.y,
            point.z, false);
        observation = diagnoseCompleteNativePath(pathOk, proofPath, point);
        if (!observation.Accepted)
            return false;
        verifiedEndpoint = proofPath.GetActualEndPosition();
        return true;
    };

    auto selectProgressEndpoint = [&](PathGenerator const& candidatePath,
        char const* candidateMode, float minimumProgress)
    {
        PathType const candidateType = candidatePath.GetPathType();
        if (!BotWorldMovement::NativePathCanProvideProgress(candidateType))
            return false;

        auto acceptPoint = [&](G3D::Vector3 const& point)
        {
            float const pointTravel = bot->GetExactDist(point.x, point.y,
                point.z);
            float const pointGoalDistance = distanceToGoal(point.x, point.y,
                point.z);
            if (!nativePointFloorValid(point) || pointTravel < 1.5f
                || pointGoalDistance + minimumProgress >= currentGoalDistance)
                return false;

            segmentX = point.x;
            segmentY = point.y;
            segmentZ = point.z;
            traversalMode = candidateMode;
            segmentSelected = true;
            return true;
        };

        if (candidateType & PATHFIND_INCOMPLETE)
        {
            constexpr float IncompleteEndpointClearance = 3.0f;
            return BotWorldMovement::SelectIncompletePathBackoffCandidate(
                candidatePath.GetPath(), candidatePath.GetActualEndPosition(),
                IncompleteEndpointClearance,
                [&](G3D::Vector3 const& point, float, float)
                {
                    G3D::Vector3 verifiedEndpoint;
                    BotWorldMovement::NativePathProofObservation proof;
                    if (!completeNativePathToPoint(point, verifiedEndpoint,
                            proof)
                        || !acceptPoint(verifiedEndpoint))
                        return false;
                    nativeProof = proof;
                    return true;
                });
        }

        G3D::Vector3 verifiedEndpoint;
        BotWorldMovement::NativePathProofObservation proof;
        proof = diagnoseCompleteNativePath(true, candidatePath,
            G3D::Vector3(intent.X, intent.Y, intent.Z));
        if (!proof.Accepted)
            return false;
        verifiedEndpoint = candidatePath.GetActualEndPosition();
        if (!acceptPoint(verifiedEndpoint))
            return false;
        nativeProof = proof;
        return true;
    };

    PathGenerator path(bot);
    bool const pathOk = path.CalculatePath(intent.X, intent.Y, intent.Z,
        false);
    PathType const pathType = path.GetPathType();
    nativeProof = diagnoseCompleteNativePath(pathOk, path,
        G3D::Vector3(intent.X, intent.Y, intent.Z));
    bool boundedLocalMechanicEndpoint = false;
    if (targetFloorValid && nativeProof.Calculated
        && nativeProof.Complete)
    {
        G3D::Vector3 const& verifiedMainEndpoint = path.GetActualEndPosition();
        boundedLocalMechanicEndpoint =
            BotWorldMovement::NativePathAllowsBoundedSameLevelMechanicProgress(
                intent.Owner, sameLevelDeclaredFloorFallback,
                sameLevelLocalMechanicProgress, nativeProof.Complete,
                BotWorldMovement::NativePathHasForbiddenAdmissionFlag(pathType),
                nativeProof, bot->GetExactDist(verifiedMainEndpoint.x,
                    verifiedMainEndpoint.y, verifiedMainEndpoint.z),
                currentGoalDistance,
                distanceToGoal(verifiedMainEndpoint.x, verifiedMainEndpoint.y,
                    verifiedMainEndpoint.z));
        if (nativeProof.Accepted || boundedLocalMechanicEndpoint)
        {
            segmentX = verifiedMainEndpoint.x;
            segmentY = verifiedMainEndpoint.y;
            segmentZ = verifiedMainEndpoint.z;
            if (boundedLocalMechanicEndpoint)
                traversalMode = "native_bounded_same_level_mechanic_endpoint";
            segmentSelected = true;
        }
    }
    else if (!strictNativeDescent && progressivePathAdmission
        && pathOk && (pathType & PATHFIND_INCOMPLETE))
        selectProgressEndpoint(path, "native_partial_path_backoff", 3.0f);

    // An incomplete route may still make deterministic local progress.  The
    // chosen endpoint is always mmap-validated and must reduce goal distance;
    // a straight-line shortcut is never submitted.
    if (!segmentSelected && progressivePathAdmission && !strictNativeDescent)
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
        bool bestBackedOff = false;
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
                float const resolvedCandidateZ = bot->GetMap()->GetHeight(
                    bot->GetPhaseShift(), candidateX, candidateY,
                    bot->GetPositionZ() + 2.0f, true, 8.0f);
                if (resolvedCandidateZ <= INVALID_HEIGHT)
                    continue;
                BotWorldMovement::NativeFloorResult const candidateFloor =
                    BotWorldMovement::AdmitSameLevelLocalStepFloor(
                        bot->GetPositionZ(), intent.Z, resolvedCandidateZ);
                if (!candidateFloor.Accepted())
                    continue;
                float const candidateZ = candidateFloor.Z;

                PathGenerator stepPath(bot);
                if (!stepPath.CalculatePath(candidateX, candidateY,
                    candidateZ, false))
                    continue;
                PathType const stepType = stepPath.GetPathType();
                if (!BotWorldMovement::NativePathCanProvideProgress(stepType))
                    continue;
                auto considerStepPoint = [&](G3D::Vector3 const& point,
                    bool backedOff)
                {
                    float const pointTravel = bot->GetExactDist(point.x,
                        point.y, point.z);
                    float const pointGoalDistance = distanceToGoal(point.x,
                        point.y, point.z);
                    if (!nativePointFloorValid(point) || pointTravel < 1.5f
                        || pointGoalDistance + 2.0f >= currentGoalDistance
                        || pointGoalDistance >= bestGoalDistance)
                        return false;

                    foundWalkableStep = true;
                    bestGoalDistance = pointGoalDistance;
                    bestX = point.x;
                    bestY = point.y;
                    bestZ = point.z;
                    bestBackedOff = backedOff;
                    return true;
                };

                if (stepType & PATHFIND_INCOMPLETE)
                {
                    constexpr float IncompleteEndpointClearance = 3.0f;
                    BotWorldMovement::SelectIncompletePathBackoffCandidate(
                        stepPath.GetPath(), stepPath.GetActualEndPosition(),
                        IncompleteEndpointClearance,
                        [&](G3D::Vector3 const& point, float, float)
                        {
                            G3D::Vector3 verifiedEndpoint;
                            BotWorldMovement::NativePathProofObservation proof;
                            if (!completeNativePathToPoint(point,
                                    verifiedEndpoint, proof)
                                || !considerStepPoint(verifiedEndpoint, true))
                                return false;
                            nativeProof = proof;
                            return true;
                        });
                }
                else
                {
                    G3D::Vector3 verifiedEndpoint;
                    BotWorldMovement::NativePathProofObservation proof;
                    proof = diagnoseCompleteNativePath(true, stepPath,
                        G3D::Vector3(candidateX, candidateY, candidateZ));
                    if (proof.Accepted)
                        verifiedEndpoint = stepPath.GetActualEndPosition();
                    if (proof.Accepted
                        && considerStepPoint(verifiedEndpoint, false))
                        nativeProof = proof;
                }
            }
        }
        if (foundWalkableStep)
        {
            segmentX = bestX;
            segmentY = bestY;
            segmentZ = bestZ;
            traversalMode = bestBackedOff
                ? "native_walkable_step_backoff"
                : "native_walkable_step";
            segmentSelected = true;
        }
    }

    if (!segmentSelected)
    {
        if (strictNativeDescent && !bot->IsInCombat())
            return reject("native_descent_complete_path_required",
                "complete_path_required");
        if (!targetFloorValid)
            return reject("route_destination_invalid_floor", "target_floor");
        if (!pathOk || (pathType & PATHFIND_NOPATH))
            return reject("route_destination_unreachable", "path_admission");
        if (pathType & PATHFIND_NOT_USING_PATH)
            return reject("route_destination_missing_mmap", "path_admission");
        if (pathType & PATHFIND_INCOMPLETE)
            return reject("route_destination_partial_path", "path_admission");
        if (pathType & PATHFIND_SHORTCUT)
            return reject("route_destination_shortcut_path", "path_admission");
        if (pathType & PATHFIND_FARFROMPOLY)
            return reject("route_destination_off_mesh", "path_admission");
        if ((pathType & PATHFIND_NORMAL) && !nativeProof.EndpointMatched)
            return reject("route_destination_endpoint_mismatch",
                "endpoint_match");
        if ((pathType & PATHFIND_NORMAL)
            && !nativeProof.EndpointFloorValid)
            return reject("route_destination_endpoint_floor_invalid",
                "endpoint_floor");
        if ((pathType & PATHFIND_NORMAL)
            && BotWorldMovement::NativePathFloorObservationBlocksCompleteProof(
                nativeProof.FloorObservation))
            return reject("route_destination_path_floor_gap", "path_floor");
        return reject("route_destination_unreachable", "path_admission");
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
        return reject("route_destination_recently_failed", "recent_failure");

    plan.SegmentX = segmentX;
    plan.SegmentY = segmentY;
    plan.SegmentZ = segmentZ;
    plan.TraversalMode = traversalMode;
    plan.Selected = true;
    RecordMovementPlannerOutcome(PlannerBotGuid(bot), PlannerBotMapId(bot),
        intent, targetFloorSampled, sampledTargetFloorZ, targetFloorValid,
        "path_admission", true, nullptr, &nativeProof);
    return true;
}
