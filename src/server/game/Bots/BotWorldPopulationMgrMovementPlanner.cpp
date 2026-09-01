#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotExperienceLearningPolicy.h"
#include "Bots/BotWorldPopulationMgrConnectedSurfacePath.h"
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
    std::uint64_t const launchReceiptId = plan.LaunchReceiptId;
    plan = {};
    plan.LaunchReceiptId = launchReceiptId;
    plan.Execution = BotWorldMovement::BeginExecutionObservation(intent.X,
        intent.Y, intent.Z, launchReceiptId);

    float sampledTargetFloorZ = 0.0f;
    bool targetFloorSampled = false;
    bool targetFloorValid = false;
    BotWorldMovement::NativePathProofObservation nativeProof;
    BotWorldMovement::NativePathProofObservation primaryNativeProof;
    BotWorldMovement::NativePathControlSequence plannerControls;
    BotWorldMovement::PrimaryDisposition primaryDisposition =
        BotWorldMovement::PrimaryDisposition::Forbidden;
    bool localFallbackAttempted = false;

    auto reject = [&](char const* reason, char const* gate)
    {
        BotWorldMovement::ObserveExecutionProof(plan.Execution, nativeProof);
        plan.RejectReason = reason ? reason : "route_destination_unreachable";
        RecordMovementPlannerOutcome(plan.LaunchReceiptId,
            PlannerBotGuid(bot), PlannerBotMapId(bot),
            intent, targetFloorSampled, sampledTargetFloorZ, targetFloorValid,
            gate, false, plan.RejectReason.c_str(), plan, &nativeProof,
            plannerControls.Available ? &plannerControls : nullptr,
            primaryDisposition, &primaryNativeProof,
            localFallbackAttempted);
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
        plan.Execution.PlannerAccepted = true;
        RecordMovementPlannerOutcome(plan.LaunchReceiptId,
            PlannerBotGuid(bot), PlannerBotMapId(bot),
            intent, targetFloorSampled, sampledTargetFloorZ, targetFloorValid,
            "dynamic_target_chase", true, nullptr, plan);
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
        plan.Execution.PlannerAccepted = true;
        RecordMovementPlannerOutcome(plan.LaunchReceiptId,
            PlannerBotGuid(bot), PlannerBotMapId(bot),
            intent, targetFloorSampled, sampledTargetFloorZ, targetFloorValid,
            "native_long_path", true, nullptr, plan);
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
    // A request-level height sample is not a topology proof. Multi-level maps
    // can resolve unrelated geometry below an otherwise connected native
    // route, so retain these predicates for the terminal reason but let the
    // PathGenerator establish or refute native connectivity first.
    bool const targetFloorRequiresNativeProof = !targetFloorValid
        && (!progressiveStaticRoute || strictNativeDescent);
    bool const targetZTransitionRequiresNativeProof = targetFloorValid
        && std::fabs(floorZ - intent.Z) > 4.0f
        && !sameLevelDeclaredFloorFallback
        && (!progressiveStaticRoute || strictNativeDescent);
    float const currentGoalDistance = bot->GetExactDist(intent.X, intent.Y,
        intent.Z);
    bool const sameLevelDeclaredMechanicRequest = std::isfinite(
        bot->GetPositionZ()) && std::isfinite(intent.Z)
        && std::fabs(bot->GetPositionZ() - intent.Z)
            <= BotWorldMovement::NativeFloorTolerance;
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
        BotWorldMovement::NativePathProofObservation& observation,
        BotWorldMovement::NativePathControlSequence& controls)
    {
        PathGenerator proofPath(bot);
        bool const pathOk = proofPath.CalculatePath(point.x, point.y,
            point.z, false);
        controls = BotWorldMovement::ObserveNativePathControls(
            proofPath.GetPath(), "world");
        observation = diagnoseCompleteNativePath(pathOk, proofPath, point);
        if (!observation.Calculated || !observation.Complete)
            return false;
        verifiedEndpoint = proofPath.GetActualEndPosition();
        bool const boundedEndpoint =
            BotWorldMovement::NativePathAllowsBoundedSameLevelMechanicProgress(
                intent.Owner, sameLevelDeclaredFloorFallback,
                sameLevelLocalMechanicProgress, observation.Complete,
                BotWorldMovement::NativePathHasForbiddenAdmissionFlag(
                    proofPath.GetPathType()), observation,
                bot->GetExactDist(verifiedEndpoint.x, verifiedEndpoint.y,
                    verifiedEndpoint.z),
                currentGoalDistance,
                distanceToGoal(verifiedEndpoint.x, verifiedEndpoint.y,
                    verifiedEndpoint.z),
                sameLevelDeclaredMechanicRequest);
        return observation.Accepted || boundedEndpoint;
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
                    BotWorldMovement::NativePathControlSequence controls;
                    if (!completeNativePathToPoint(point, verifiedEndpoint,
                            proof, controls)
                        || !acceptPoint(verifiedEndpoint))
                        return false;
                    nativeProof = proof;
                    plannerControls = controls;
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
        plannerControls = BotWorldMovement::ObserveNativePathControls(
            candidatePath.GetPath(), "world");
        return true;
    };

    PathGenerator path(bot);
    bool const pathOk = path.CalculatePath(intent.X, intent.Y, intent.Z,
        false);
    PathType const pathType = path.GetPathType();
    plannerControls = BotWorldMovement::ObserveNativePathControls(
        path.GetPath(), "world");
    nativeProof = diagnoseCompleteNativePath(pathOk, path,
        G3D::Vector3(intent.X, intent.Y, intent.Z));
    primaryNativeProof = nativeProof;
    if (intent.HazardEscape)
    {
        G3D::Vector3 const& endpoint = path.GetActualEndPosition();
        plan.HazardEscapeProgress =
            BotWorldMovement::ObserveHazardEscapeProgress(
                *intent.HazardEscape, bot->GetPositionX(),
                bot->GetPositionY(), bot->GetPositionZ(), endpoint.x,
                endpoint.y, endpoint.z);
        plan.HazardEscapeProgress.ProofQualified =
            BotWorldMovement::NativePathProvesSameSurfaceHazardEscape(
                intent.Owner, sameLevelDeclaredMechanicRequest,
                nativeProof.Complete,
                BotWorldMovement::NativePathHasForbiddenAdmissionFlag(
                    path.GetPathType()),
                nativeProof, *intent.HazardEscape,
                plan.HazardEscapeProgress);
    }
    bool const connectedPolyCorridor = path.HasConnectedPolyCorridor();
    bool const primaryFallbackEligible = progressivePathAdmission
        && !strictNativeDescent && pathOk
        && (pathType & PATHFIND_INCOMPLETE)
        && BotWorldMovement::NativePathCanProvideProgress(pathType);
    primaryDisposition = BotWorldMovement::ClassifyPrimaryDisposition(
        primaryNativeProof, primaryFallbackEligible,
        BotWorldMovement::NativePathHasForbiddenAdmissionFlag(pathType));
    bool boundedLocalMechanicEndpoint = false;
    if (targetFloorValid && nativeProof.Calculated && nativeProof.Complete)
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
                    verifiedMainEndpoint.z),
                sameLevelDeclaredMechanicRequest);
        BotWorldMovement::NativePrimaryEndpointAdmission const admission =
            BotWorldMovement::ClassifyNativePrimaryEndpointAdmission(
                nativeProof,
                targetFloorRequiresNativeProof
                    || targetZTransitionRequiresNativeProof,
                BotWorldMovement::NativePathHasForbiddenAdmissionFlag(
                    pathType),
                connectedPolyCorridor, boundedLocalMechanicEndpoint);
        if (admission
            != BotWorldMovement::NativePrimaryEndpointAdmission::Rejected)
        {
            segmentX = verifiedMainEndpoint.x;
            segmentY = verifiedMainEndpoint.y;
            segmentZ = verifiedMainEndpoint.z;
            if (admission == BotWorldMovement::
                    NativePrimaryEndpointAdmission::ConnectedSurface)
                traversalMode = "native_connected_surface_path";
            else if (admission == BotWorldMovement::
                    NativePrimaryEndpointAdmission::BoundedLocalMechanic)
                traversalMode = "native_bounded_same_level_mechanic_endpoint";
            segmentSelected = true;
        }
    }
    else if (!strictNativeDescent && progressivePathAdmission
        && pathOk && (pathType & PATHFIND_INCOMPLETE))
    {
        localFallbackAttempted = true;
        selectProgressEndpoint(path, "native_partial_path_backoff", 3.0f);
    }

    auto selectProgressiveLocalMechanicEndpoint = [&]()
    {
        if (!sameLevelLocalMechanicProgress)
            return false;

        G3D::Vector3 const actorPoint(bot->GetPositionX(),
            bot->GetPositionY(), bot->GetPositionZ());
        G3D::Vector3 const declaredDestination(intent.X, intent.Y,
            bot->GetPositionZ());
        return BotWorldMovement::SelectProgressiveLocalMechanicCandidate(
            actorPoint, declaredDestination,
            [&](G3D::Vector3 const& candidate, float)
            {
                float const resolvedCandidateZ = bot->GetMap()->GetHeight(
                    bot->GetPhaseShift(), candidate.x, candidate.y,
                    bot->GetPositionZ() + 2.0f, true, 8.0f);
                if (resolvedCandidateZ <= INVALID_HEIGHT)
                    return false;
                BotWorldMovement::NativeFloorResult const candidateFloor =
                    BotWorldMovement::AdmitSameLevelLocalStepFloor(
                        bot->GetPositionZ(), intent.Z, resolvedCandidateZ);
                if (!candidateFloor.Accepted())
                    return false;

                G3D::Vector3 const candidatePoint(candidate.x, candidate.y,
                    candidateFloor.Z);
                G3D::Vector3 verifiedEndpoint;
                BotWorldMovement::NativePathProofObservation proof;
                BotWorldMovement::NativePathControlSequence controls;
                if (!completeNativePathToPoint(candidatePoint,
                        verifiedEndpoint, proof, controls))
                    return false;
                float const endpointTravel = bot->GetExactDist(
                    verifiedEndpoint.x, verifiedEndpoint.y,
                    verifiedEndpoint.z);
                float const endpointGoalDistance = distanceToGoal(
                    verifiedEndpoint.x, verifiedEndpoint.y,
                    verifiedEndpoint.z);
                if (!nativePointFloorValid(verifiedEndpoint)
                    || endpointTravel
                        < BotWorldMovement::NativeLocalMechanicEndpointMinimumTravel
                    || endpointGoalDistance
                        + BotWorldMovement::NativeLocalMechanicEndpointMinimumProgress
                        >= currentGoalDistance)
                    return false;

                segmentX = verifiedEndpoint.x;
                segmentY = verifiedEndpoint.y;
                segmentZ = verifiedEndpoint.z;
                traversalMode = "native_bounded_same_level_local_step";
                nativeProof = proof;
                plannerControls = controls;
                segmentSelected = true;
                return true;
            });
    };

    bool const primaryPathAllowsProgressiveLocalFallback =
        BotWorldMovement::NativePrimaryPathAllowsProgressiveLocalFallback(
            nativeProof);

    if (!segmentSelected && progressivePathAdmission && !strictNativeDescent
        && primaryPathAllowsProgressiveLocalFallback)
    {
        localFallbackAttempted = true;
        selectProgressiveLocalMechanicEndpoint();
    }

    // An incomplete route may still make deterministic local progress.  The
    // chosen endpoint is always mmap-validated and must reduce goal distance;
    // a straight-line shortcut is never submitted.
    if (!segmentSelected && progressivePathAdmission && !strictNativeDescent
        && primaryPathAllowsProgressiveLocalFallback)
    {
        localFallbackAttempted = true;
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
                            BotWorldMovement::NativePathControlSequence controls;
                            if (!completeNativePathToPoint(point,
                                    verifiedEndpoint, proof, controls)
                                || !considerStepPoint(verifiedEndpoint, true))
                                return false;
                            nativeProof = proof;
                            plannerControls = controls;
                            return true;
                        });
                }
                else
                {
                    G3D::Vector3 verifiedEndpoint;
                    BotWorldMovement::NativePathProofObservation proof;
                    BotWorldMovement::NativePathControlSequence controls;
                    if (completeNativePathToPoint(
                            G3D::Vector3(candidateX, candidateY, candidateZ),
                            verifiedEndpoint, proof, controls)
                        && considerStepPoint(verifiedEndpoint, false))
                    {
                        nativeProof = proof;
                        plannerControls = controls;
                    }
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
        if (targetFloorRequiresNativeProof)
            return reject("route_destination_invalid_floor", "target_floor");
        if (targetZTransitionRequiresNativeProof)
            return reject("route_destination_invalid_z_transition",
                "target_z_transition");
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
    plan.Execution.PlannerAccepted = true;
    BotWorldMovement::ObserveExecutionProof(plan.Execution, nativeProof);
    RecordMovementPlannerOutcome(plan.LaunchReceiptId, PlannerBotGuid(bot),
        PlannerBotMapId(bot),
        intent, targetFloorSampled, sampledTargetFloorZ, targetFloorValid,
        "path_admission", true, nullptr, plan, &nativeProof,
        plannerControls.Available ? &plannerControls : nullptr,
        primaryDisposition, &primaryNativeProof,
        localFallbackAttempted);
    return true;
}
