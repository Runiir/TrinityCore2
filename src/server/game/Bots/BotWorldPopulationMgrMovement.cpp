#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotExperienceLearningPolicy.h"
#include "ChaseMovementGenerator.h"
#include "GameTime.h"
#include "Map.h"
#include "MotionMaster.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Unit.h"
#include "Util.h"

#include <array>
#include <chrono>
#include <cmath>
#include <string>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

bool BotWorldPopulationMgr::MoveBotToPoint(WorldBotState& state, Player* bot, float x, float y, float z,
    bool terminalOnFailure, BotMovementArbitration::Owner movementOwner,
    BotMovementArbitration::Priority movementPriority, Unit* dynamicTarget,
    float dynamicTargetRange)
{
    if (!bot)
        return false;

    auto rejectPath = [&](char const* reason) -> bool
    {
        state.ActivePathValid = false;
        state.ActivePathSegmentValid = false;
        state.ActivePathTraversalMode.clear();
        state.ActivePathTargetGuid.Clear();
        state.LastPathRejectReason = reason ? reason : "route_destination_unreachable";
        state.LastNoProgressReason = state.LastPathRejectReason;
        state.LastRecoveryResult = state.LastPathRejectReason;
        state.LastPathChangeMs = NowMs();

        if (Cohort().Config.ValidationRouteEnable)
        {
            if (terminalOnFailure)
            {
                state.ValidationRouteTerminalState = true;
                state.ValidationRouteTerminalAtMs = NowMs();
                state.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
                state.ValidationRouteTerminalReason = state.LastPathRejectReason;
                state.LoopRecoveryCooldownUntilMs = NowMs() + 60000;
            }
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_manifest");
            RecordEvent(state, bot, "validation_route_recovery", nullptr, state.LastPathRejectReason.c_str(), raw.c_str(), semantic.c_str(), bot->GetExactDist(x, y, z), Cohort().Config.ValidationRouteTargetEntry);
        }

        return false;
    };

    if (!bot->IsInWorld() || !bot->GetMap())
        return rejectPath("route_destination_unreachable");

    using namespace BotMovementArbitration;
    uint64 const nowMs = NowMs();
    if (movementOwner == Owner::None)
    {
        if (bot->IsInCombat())
        {
            movementOwner = Owner::CombatRange;
            movementPriority = Priority::Combat;
        }
        else if (Cohort().Config.ValidationRouteEnable)
        {
            movementOwner = Owner::Route;
            movementPriority = Priority::Route;
        }
        else
        {
            movementOwner = Owner::Formation;
            movementPriority = Priority::Formation;
        }
    }

    Request movementRequest;
    movementRequest.MovementOwner = movementOwner;
    movementRequest.MovementPriority = movementPriority;
    movementRequest.ExpiresAtMs = nowMs + 1500;
    movementRequest.MovementScope = Scope{
        Cohort().Config.ValidationRouteEnable ? Cohort().AttemptId : 0,
        Cohort().Config.ValidationRouteEnable ? uint32(Cohort().Raid.WipeGeneration) : 0,
        Cohort().Config.ValidationRouteEnable ? Party().ValidationRouteGeneration : 0,
        bot->GetMapId(), bot->GetInstanceId()
    };
    movementRequest.X = x;
    movementRequest.Y = y;
    movementRequest.Z = z;
    bool const targetAwareChase = dynamicTarget && dynamicTarget->IsAlive()
        && dynamicTarget->IsInWorld() && dynamicTarget->GetMap() == bot->GetMap();
    movementRequest.DynamicTargetGuid = targetAwareChase
        ? dynamicTarget->GetGUID().GetRawValue() : 0;
    Decision const movementDecision = Evaluate(state.MovementLease, movementRequest, nowMs);
    if (movementDecision == Decision::RejectInvalid)
        return rejectPath("movement_lease_invalid_scope");
    if (movementDecision == Decision::PreserveExisting)
    {
        state.LastRecoveryMode = "movement_lease_preserved";
        state.LastRecoveryResult = "higher_priority_movement_active";
        return false;
    }

    constexpr float activeDestinationEpsilon = 0.1f;
    bool const activePathScopeMatches = !Cohort().Config.ValidationRouteEnable
        || (state.ActivePathAttemptId == Cohort().AttemptId
            && state.ActivePathWipeGeneration == Cohort().Raid.WipeGeneration
            && state.ActivePathRouteGeneration == Party().ValidationRouteGeneration
            && state.ActivePathRouteNodeId == Cohort().Config.ValidationRouteNodeId);
    // The top generator can temporarily be controlled movement while the
    // adaptive path still owns MOTION_SLOT_ACTIVE. Inspect the slot directly.
    // For live melee targets also verify the native chase object's target, so
    // target motion refreshes evidence/leases without clearing its repath loop.
    MotionMaster* motion = bot->GetMotionMaster();
    MovementGeneratorType const nativeActiveMotionType = motion
        ? motion->GetMotionSlotType(MOTION_SLOT_ACTIVE) : MAX_MOTION_TYPE;
    bool const nativePointPathActive = nativeActiveMotionType == POINT_MOTION_TYPE;
    bool nativeTargetChaseActive = false;
    if (targetAwareChase && nativeActiveMotionType == CHASE_MOTION_TYPE)
        if (MovementGenerator* active = motion->GetMotionSlot(MOTION_SLOT_ACTIVE))
            nativeTargetChaseActive =
                static_cast<ChaseMovementGenerator*>(active)->GetTarget()
                    == dynamicTarget;
    bool const matchingActiveDestination = targetAwareChase
        ? (nativeTargetChaseActive
            && state.ActivePathTargetGuid == dynamicTarget->GetGUID())
        : (state.ActivePathTargetGuid.IsEmpty()
            && std::fabs(x - state.ActivePathToX) <= activeDestinationEpsilon
            && std::fabs(y - state.ActivePathToY) <= activeDestinationEpsilon
            && std::fabs(z - state.ActivePathToZ) <= activeDestinationEpsilon);
    if (state.ActivePathValid
        && (state.IsMoving || nativePointPathActive || nativeTargetChaseActive)
        && activePathScopeMatches && matchingActiveDestination)
    {
        if (nativePointPathActive || nativeTargetChaseActive)
            state.IsMoving = true;
        state.ActivePathToX = x;
        state.ActivePathToY = y;
        state.ActivePathToZ = z;
        Apply(state.MovementLease, movementRequest);
        return true;
    }

    if (targetAwareChase)
    {
        // A dynamic hostile is not a fixed route coordinate. Commit the
        // arbitration lease, then let Trinity's native chase generator own
        // mmap repathing and the requested stop distance as the target and
        // caster move. Static route points continue through the strict
        // complete-path validation below.
        state.ActivePathFromX = bot->GetPositionX();
        state.ActivePathFromY = bot->GetPositionY();
        state.ActivePathFromZ = bot->GetPositionZ();
        state.ActivePathToX = x;
        state.ActivePathToY = y;
        state.ActivePathToZ = z;
        state.ActivePathSegmentValid = false;
        state.ActivePathTraversalMode = "native_target_chase";
        state.ActivePathValid = true;
        state.ActivePathTargetGuid = dynamicTarget->GetGUID();
        state.ActivePathAttemptId = Cohort().Config.ValidationRouteEnable
            ? Cohort().AttemptId : 0;
        state.ActivePathWipeGeneration = Cohort().Config.ValidationRouteEnable
            ? Cohort().Raid.WipeGeneration : 0;
        state.ActivePathRouteGeneration = Cohort().Config.ValidationRouteEnable
            ? Party().ValidationRouteGeneration : 0;
        state.ActivePathRouteNodeId = Cohort().Config.ValidationRouteEnable
            ? Cohort().Config.ValidationRouteNodeId : std::string();
        state.LastPathRejectReason.clear();
        state.LastNoProgressReason.clear();
        state.LastRecoveryMode = "native_target_chase";
        state.LastRecoveryResult = "native_movement_submitted";
        state.LastPathChangeMs = nowMs;
        state.IsMoving = true;
        Apply(state.MovementLease, movementRequest);

        bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        if (dynamicTargetRange > 0.0f)
            bot->GetMotionMaster()->MoveChase(dynamicTarget, dynamicTargetRange);
        else
            bot->GetMotionMaster()->MoveChase(dynamicTarget);
        return true;
    }

    float floorZ = bot->GetMap()->GetHeight(bot->GetPhaseShift(), x, y, z + 2.0f, true, 8.0f);
    if (floorZ <= INVALID_HEIGHT)
        return rejectPath("route_destination_invalid_floor");
    if (std::fabs(floorZ - z) > 4.0f)
        return rejectPath("route_destination_invalid_z_transition");

    float segmentX = x;
    float segmentY = y;
    float segmentZ = z;
    char const* traversalMode = "native_complete_path";
    bool segmentSelected = false;
    bool const progressiveStaticRoute = !targetAwareChase
        && movementOwner == Owner::Route;
    bool const strictNativeDescent = progressiveStaticRoute
        && Cohort().Config.ValidationRouteKind == "descent"
        && Cohort().Config.ValidationRouteDescentAction
            == "native_walkable_descent";
    float const currentGoalDistance = bot->GetExactDist(x, y, z);
    auto distanceToGoal = [x, y, z](float candidateX, float candidateY, float candidateZ)
    {
        float const dx = candidateX - x;
        float const dy = candidateY - y;
        float const dz = candidateZ - z;
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    };
    auto selectProgressEndpoint = [&](PathGenerator const& candidatePath,
        char const* candidateMode, float minimumProgress) -> bool
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
        float const endpointTravel = bot->GetExactDist(endpoint.x, endpoint.y, endpoint.z);
        float const endpointGoalDistance = distanceToGoal(endpoint.x, endpoint.y, endpoint.z);
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
    bool const pathOk = path.CalculatePath(x, y, z, false);
    PathType const pathType = path.GetPathType();
    if (pathOk && (pathType & PATHFIND_NORMAL)
        && !(pathType & PATHFIND_NOPATH)
        && !(pathType & PATHFIND_NOT_USING_PATH)
        && !(pathType & PATHFIND_SHORTCUT)
        && !(pathType & PATHFIND_FARFROMPOLY)
        && !(pathType & PATHFIND_INCOMPLETE))
        segmentSelected = true;
    else if (!strictNativeDescent && progressiveStaticRoute
        && pathOk && (pathType & PATHFIND_INCOMPLETE))
        selectProgressEndpoint(path, "native_partial_path", 3.0f);

    // A route goal is a logical destination, not an instruction to repeatedly
    // replace native motion with a straight-line shortcut. When mmap cannot
    // solve the whole route, try deterministic, nearby walkable segments and
    // reconcile again after the committed spline finishes. This is the same
    // feedback loop a player uses while walking around incomplete geometry.
    if (!segmentSelected && progressiveStaticRoute && !strictNativeDescent)
    {
        float const baseAngle = bot->GetAngle(x, y);
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
                float const candidateX = bot->GetPositionX() + std::cos(angle) * stepDistance;
                float const candidateY = bot->GetPositionY() + std::sin(angle) * stepDistance;
                float const candidateZ = bot->GetMap()->GetHeight(bot->GetPhaseShift(),
                    candidateX, candidateY, bot->GetPositionZ() + 2.0f, true, 8.0f);
                if (candidateZ <= INVALID_HEIGHT
                    || std::fabs(candidateZ - bot->GetPositionZ()) > 4.0f)
                    continue;

                PathGenerator stepPath(bot);
                if (!stepPath.CalculatePath(candidateX, candidateY, candidateZ, false))
                    continue;
                PathType const stepType = stepPath.GetPathType();
                if ((stepType & PATHFIND_NOPATH)
                    || (stepType & PATHFIND_NOT_USING_PATH)
                    || (stepType & PATHFIND_SHORTCUT)
                    || (stepType & PATHFIND_FARFROMPOLY_START)
                    || !(stepType & (PATHFIND_NORMAL | PATHFIND_INCOMPLETE)))
                    continue;

                G3D::Vector3 const& endpoint = stepPath.GetActualEndPosition();
                float const endpointTravel = bot->GetExactDist(endpoint.x, endpoint.y, endpoint.z);
                float const endpointGoalDistance = distanceToGoal(endpoint.x, endpoint.y, endpoint.z);
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

    char const* descentRejectReason = nullptr;
    if (!segmentSelected && strictNativeDescent && !bot->IsInCombat())
        descentRejectReason = "native_descent_complete_path_required";

    if (!segmentSelected)
    {
        if (descentRejectReason)
            return rejectPath(descentRejectReason);
        if (!pathOk || (pathType & PATHFIND_NOPATH))
            return rejectPath("route_destination_unreachable");
        if (pathType & PATHFIND_NOT_USING_PATH)
            return rejectPath("route_destination_missing_mmap");
        if (pathType & PATHFIND_INCOMPLETE)
            return rejectPath("route_destination_partial_path");
        if (pathType & PATHFIND_SHORTCUT)
            return rejectPath("route_destination_shortcut_path");
        if (pathType & PATHFIND_FARFROMPOLY)
            return rejectPath("route_destination_off_mesh");
        return rejectPath("route_destination_unreachable");
    }

    BotLearnedScore pathScore = BotExperienceLearningPolicy::ScorePath(bot, bot->GetPositionX(), bot->GetPositionY(), x, y, Cohort().LearningConfig);
    bool recentFailureMemory = IsFailedPathRecently(bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), x, y)
        || pathScore.Penalty >= Cohort().LearningConfig.RecentFailurePenaltyWeight;
    if (recentFailureMemory && !Cohort().Config.ValidationRouteEnable)
    {
        return rejectPath("route_destination_recently_failed");
    }
    if (recentFailureMemory)
        state.LastNoProgressReason = "route_destination_recently_failed_memory";

    state.ActivePathFromX = bot->GetPositionX();
    state.ActivePathFromY = bot->GetPositionY();
    state.ActivePathFromZ = bot->GetPositionZ();
    state.ActivePathToX = x;
    state.ActivePathToY = y;
    state.ActivePathToZ = z;
    state.ActivePathSegmentToX = segmentX;
    state.ActivePathSegmentToY = segmentY;
    state.ActivePathSegmentToZ = segmentZ;
    state.ActivePathSegmentValid = true;
    state.ActivePathTraversalMode = traversalMode;
    state.ActivePathValid = true;
    state.ActivePathTargetGuid = targetAwareChase
        ? dynamicTarget->GetGUID() : ObjectGuid::Empty;
    state.ActivePathAttemptId = Cohort().Config.ValidationRouteEnable ? Cohort().AttemptId : 0;
    state.ActivePathWipeGeneration = Cohort().Config.ValidationRouteEnable
        ? Cohort().Raid.WipeGeneration : 0;
    state.ActivePathRouteGeneration = Cohort().Config.ValidationRouteEnable
        ? Party().ValidationRouteGeneration : 0;
    state.ActivePathRouteNodeId = Cohort().Config.ValidationRouteEnable
        ? Cohort().Config.ValidationRouteNodeId : std::string();
    state.LastPathRejectReason.clear();
    state.LastNoProgressReason.clear();
    state.LastRecoveryMode = traversalMode;
    state.LastRecoveryResult = "native_movement_submitted";
    state.LastPathChangeMs = NowMs();
    Apply(state.MovementLease, movementRequest);

    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    if (targetAwareChase)
    {
        if (dynamicTargetRange > 0.0f)
            bot->GetMotionMaster()->MoveChase(dynamicTarget, dynamicTargetRange);
        else
            bot->GetMotionMaster()->MoveChase(dynamicTarget);
    }
    else if (std::fabs(segmentX - x) > activeDestinationEpsilon
        || std::fabs(segmentY - y) > activeDestinationEpsilon
        || std::fabs(segmentZ - z) > activeDestinationEpsilon)
        bot->GetMotionMaster()->MovePoint(0, segmentX, segmentY, segmentZ, true);
    else
        bot->GetMotionMaster()->MovePoint(0, x, y, z, true);
    return true;
}

char const* BotWorldPopulationMgr::ValidationDescentPhaseName(
    WorldBotState::ValidationDescentPhase phase)
{
    switch (phase)
    {
        case WorldBotState::ValidationDescentPhase::Unobserved: return "unobserved";
        case WorldBotState::ValidationDescentPhase::Approaching: return "approaching";
        case WorldBotState::ValidationDescentPhase::Departed: return "departed";
        case WorldBotState::ValidationDescentPhase::Falling: return "falling";
        case WorldBotState::ValidationDescentPhase::Landed: return "landed";
        case WorldBotState::ValidationDescentPhase::Ready: return "ready";
        case WorldBotState::ValidationDescentPhase::Blocked: return "blocked";
    }
    return "unknown";
}

BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeDescentIntent(
    WorldBotState& state, Player* bot,
    BotNativeAction::NativeDescent const& intent)
{
    using Phase = WorldBotState::ValidationDescentPhase;
    constexpr float ArrivalRadius = 18.0f;
    constexpr float ArrivalVerticalTolerance = 4.0f;
    constexpr float MinimumLandingHealthPct = 0.15f;
    constexpr float MinimumPreDescentHealthPct = 0.50f;
    constexpr float MaximumNativeWalkStepDown = 4.0f;
    constexpr uint64 GroundedStableMs = 500;
    constexpr uint64 NoProgressTerminalMs = 30000;
    uint64 const nowMs = NowMs();

    auto reject = [&](char const* reason) -> BotActionArbitration::Outcome
    {
        state.ValidationRouteDescentPhase = Phase::Blocked;
        state.ValidationRouteDescentRejectReason = reason;
        state.LastPathRejectReason = reason;
        state.LastNoProgressReason = reason;
        state.LastRecoveryMode = "native_walkable_descent";
        state.LastRecoveryResult = reason;
        return BotActionArbitration::Outcome::Retryable(reason);
    };

    if (!bot || !bot->IsInWorld() || !bot->GetMap())
        return reject("native_descent_bot_unavailable");
    if (Cohort().Config.ValidationRouteKind != "descent"
        || Cohort().Config.ValidationRouteDescentAction
            != "native_walkable_descent")
        return reject("native_descent_action_contract_mismatch");
    if (!intent.RouteGeneration
        || intent.RouteGeneration != Party().ValidationRouteGeneration)
        return reject("native_descent_generation_mismatch");
    if (!intent.HasNextGoal)
        return reject("native_descent_next_goal_missing");

    float const goalDistance = bot->GetExactDist(intent.LandingX,
        intent.LandingY, intent.LandingZ);
    if (state.ValidationRouteDescentGeneration != intent.RouteGeneration)
    {
        state.ValidationRouteDescentPhase = Phase::Approaching;
        state.ValidationRouteDescentGeneration = intent.RouteGeneration;
        state.ValidationRouteDescentStartX = bot->GetPositionX();
        state.ValidationRouteDescentStartY = bot->GetPositionY();
        state.ValidationRouteDescentStartZ = bot->GetPositionZ();
        state.ValidationRouteDescentInitialGoalDistance = goalDistance;
        state.ValidationRouteDescentBestGoalDistance = goalDistance;
        state.ValidationRouteDescentLandingHealthPct = 0.0f;
        state.ValidationRouteDescentLastProgressMs = nowMs;
        state.ValidationRouteDescentGroundedSinceMs = 0;
        state.ValidationRouteDescentDepartureObserved = false;
        state.ValidationRouteDescentFallingObserved = false;
        state.ValidationRouteDescentLandingObserved = false;
        state.ValidationRouteDescentHealthMarginSatisfied = false;
        state.ValidationRouteDescentLandingPathProven = false;
        state.ValidationRouteDescentMonotonicProgressObserved = false;
        state.ValidationRouteDescentRejectReason.clear();
    }

    if (!bot->IsAlive())
        return reject("native_descent_member_not_alive");

    if (state.ValidationRouteDescentLastProgressMs
        && nowMs - state.ValidationRouteDescentLastProgressMs
            >= NoProgressTerminalMs)
    {
        char const* const stalledPhase = ValidationDescentPhaseName(
            state.ValidationRouteDescentPhase);
        state.ValidationRouteDescentPhase = Phase::Blocked;
        state.ValidationRouteDescentRejectReason =
            std::string("native_descent_no_progress_")
            + stalledPhase;
        state.LastPathRejectReason =
            state.ValidationRouteDescentRejectReason;
        state.LastNoProgressReason =
            state.ValidationRouteDescentRejectReason;
        state.LastRecoveryMode = "native_walkable_descent";
        state.LastRecoveryResult = "native_descent_no_progress_terminal";
        state.LoopRecoveryCooldownUntilMs = nowMs + 60000;
        std::string const failureReason =
            std::string("native_descent_no_progress_terminal:")
            + state.ValidationRouteDescentRejectReason;
        FailValidationAttemptOnce(state, bot, failureReason,
            intent.RouteGeneration);
        return BotActionArbitration::Outcome::Terminal(
            failureReason);
    }

    if (goalDistance + 0.25f
        < state.ValidationRouteDescentBestGoalDistance)
    {
        state.ValidationRouteDescentBestGoalDistance = goalDistance;
        state.ValidationRouteDescentLastProgressMs = nowMs;
        state.ValidationRouteDescentMonotonicProgressObserved = true;
    }

    float const departureX = bot->GetPositionX()
        - state.ValidationRouteDescentStartX;
    float const departureY = bot->GetPositionY()
        - state.ValidationRouteDescentStartY;
    float const departure2d = std::sqrt(departureX * departureX
        + departureY * departureY);
    float const verticalDeparture = std::fabs(bot->GetPositionZ()
        - state.ValidationRouteDescentStartZ);
    if (!state.ValidationRouteDescentDepartureObserved
        && (departure2d >= 1.0f || verticalDeparture >= 0.75f
            || goalDistance + 0.5f
                < state.ValidationRouteDescentInitialGoalDistance))
    {
        state.ValidationRouteDescentDepartureObserved = true;
        state.ValidationRouteDescentPhase = Phase::Departed;
        state.ValidationRouteDescentLastProgressMs = nowMs;
    }

    // Falling is observation-only. Never replace the native transition with a
    // movement spline or repeatedly submit another path while gravity owns the
    // player. The ordinary route candidate reconciles again after landing.
    if (bot->IsFalling())
    {
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Route,
            BotActionArbitration::Priority::Mechanic,
            "native_descent_falling");
        state.ValidationRouteDescentFallingObserved = true;
        state.ValidationRouteDescentDepartureObserved = true;
        if (state.ValidationRouteDescentPhase != Phase::Falling)
            state.ValidationRouteDescentLastProgressMs = nowMs;
        state.ValidationRouteDescentPhase = Phase::Falling;
        state.ValidationRouteDescentGroundedSinceMs = 0;
        state.ValidationRouteDescentRejectReason.clear();
        state.LastNoProgressReason = "native_descent_falling_observed";
        return BotActionArbitration::Outcome::Progressed(
            "native_descent_falling_observed");
    }

    float const floorZ = bot->GetMap()->GetHeight(bot->GetPhaseShift(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ() + 2.0f,
        true, 8.0f);
    bool const grounded = floorZ > INVALID_HEIGHT
        && std::fabs(floorZ - bot->GetPositionZ()) <= 1.5f;
    bool const insideLanding = goalDistance <= ArrivalRadius
        && std::fabs(bot->GetPositionZ() - intent.LandingZ)
            <= ArrivalVerticalTolerance;
    if (insideLanding && grounded)
    {
        if (!state.ValidationRouteDescentDepartureObserved
            || !state.ValidationRouteDescentMonotonicProgressObserved)
            return reject("native_descent_departure_not_observed");

        if (!state.ValidationRouteDescentGroundedSinceMs)
        {
            state.ValidationRouteDescentGroundedSinceMs = nowMs;
            state.ValidationRouteDescentPhase = Phase::Landed;
            state.ValidationRouteDescentLastProgressMs = nowMs;
            state.LastNoProgressReason = "native_descent_grounded_stability_pending";
            return BotActionArbitration::Outcome::Progressed(
                "native_descent_grounded_observed");
        }
        if (nowMs - state.ValidationRouteDescentGroundedSinceMs
            < GroundedStableMs)
            return BotActionArbitration::Outcome::Retryable(
                "native_descent_grounded_stability_pending");

        state.ValidationRouteDescentLandingObserved = true;
        state.ValidationRouteDescentLandingX = bot->GetPositionX();
        state.ValidationRouteDescentLandingY = bot->GetPositionY();
        state.ValidationRouteDescentLandingZ = bot->GetPositionZ();
        state.ValidationRouteDescentLandingHealthPct = bot->GetMaxHealth()
            ? float(bot->GetHealth()) / float(bot->GetMaxHealth()) : 0.0f;
        state.ValidationRouteDescentHealthMarginSatisfied =
            state.ValidationRouteDescentLandingHealthPct
                >= MinimumLandingHealthPct;
        state.ValidationRouteDescentPhase = Phase::Landed;
        if (!state.ValidationRouteDescentHealthMarginSatisfied)
        {
            state.ValidationRouteDescentRejectReason =
                "native_descent_landing_health_margin_low";
            state.LastNoProgressReason =
                state.ValidationRouteDescentRejectReason;
            return BotActionArbitration::Outcome::Retryable(
                state.ValidationRouteDescentRejectReason);
        }

        PathGenerator onwardPath(bot);
        bool const onwardCalculated = onwardPath.CalculatePath(
            intent.NextGoalX, intent.NextGoalY, intent.NextGoalZ, false);
        PathType const onwardType = onwardPath.GetPathType();
        bool onwardExact = onwardCalculated
            && (onwardType & PATHFIND_NORMAL)
            && !(onwardType & PATHFIND_NOPATH)
            && !(onwardType & PATHFIND_NOT_USING_PATH)
            && !(onwardType & PATHFIND_INCOMPLETE)
            && !(onwardType & PATHFIND_SHORTCUT)
            && !(onwardType & PATHFIND_FARFROMPOLY);
        if (onwardExact)
        {
            G3D::Vector3 const& actualEnd =
                onwardPath.GetActualEndPosition();
            float const dx = actualEnd.x - intent.NextGoalX;
            float const dy = actualEnd.y - intent.NextGoalY;
            float const dz = actualEnd.z - intent.NextGoalZ;
            onwardExact = std::sqrt(dx * dx + dy * dy + dz * dz) <= 3.0f;
        }
        if (!onwardExact)
            return reject("native_descent_landing_next_goal_path_unavailable");

        state.ValidationRouteDescentLandingPathProven = true;
        state.ValidationRouteDescentPhase = Phase::Ready;
        state.ValidationRouteDescentLastProgressMs = nowMs;
        state.ValidationRouteDescentRejectReason.clear();
        state.LastPathRejectReason.clear();
        state.LastNoProgressReason.clear();
        state.LastRecoveryMode = "native_walkable_descent";
        state.LastRecoveryResult = "grounded_landing_and_onward_path_proven";
        return BotActionArbitration::Outcome::Committed(
            "native_descent_ready");
    }

    state.ValidationRouteDescentGroundedSinceMs = 0;
    float const currentHealthPct = bot->GetMaxHealth()
        ? float(bot->GetHealth()) / float(bot->GetMaxHealth()) : 0.0f;
    if (currentHealthPct < MinimumPreDescentHealthPct)
        return reject("native_descent_pre_step_health_margin_low");

    // The typed descent requires one complete ordinary Detour corridor to the
    // declared landing. An incomplete corridor or locally improving endpoint
    // is not authority to step onto a one-way edge. Its height samples must
    // also describe walk-sized transitions rather than a large implicit drop.
    PathGenerator descentPreflight(bot);
    bool const descentPathCalculated = descentPreflight.CalculatePath(
        intent.LandingX, intent.LandingY, intent.LandingZ, false);
    PathType const descentPathType = descentPreflight.GetPathType();
    bool completeNativePath = descentPathCalculated
        && (descentPathType & PATHFIND_NORMAL)
        && !(descentPathType & PATHFIND_NOPATH)
        && !(descentPathType & PATHFIND_NOT_USING_PATH)
        && !(descentPathType & PATHFIND_INCOMPLETE)
        && !(descentPathType & PATHFIND_SHORTCUT)
        && !(descentPathType & PATHFIND_FARFROMPOLY);
    if (completeNativePath)
    {
        G3D::Vector3 const& actualEnd =
            descentPreflight.GetActualEndPosition();
        float const dx = actualEnd.x - intent.LandingX;
        float const dy = actualEnd.y - intent.LandingY;
        float const dz = actualEnd.z - intent.LandingZ;
        completeNativePath = std::sqrt(dx * dx + dy * dy + dz * dz)
            <= 3.0f;
    }
    if (!completeNativePath)
        return reject("native_descent_complete_path_required");

    {
        Movement::PointsArray const& points = descentPreflight.GetPath();
        for (size_t index = 1; index < points.size(); ++index)
            if (points[index - 1].z - points[index].z
                > MaximumNativeWalkStepDown)
                return reject("native_descent_drop_policy_rejected");
    }

    SubmitMeleeAutoAttackIntent(state,
        BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
        BotMeleeAutoAttack::Owner::Route,
        BotActionArbitration::Priority::Mechanic,
        "native_descent_movement");
    bool const moved = MoveBotToPoint(state, bot, intent.LandingX,
        intent.LandingY, intent.LandingZ, false,
        BotMovementArbitration::Owner::Route,
        BotMovementArbitration::Priority::Route);
    if (!moved)
    {
        state.ValidationRouteDescentPhase = Phase::Blocked;
        state.ValidationRouteDescentRejectReason =
            state.LastPathRejectReason.empty()
                ? "native_descent_safe_segment_unavailable"
                : state.LastPathRejectReason;
        state.LastNoProgressReason =
            state.ValidationRouteDescentRejectReason;
        return BotActionArbitration::Outcome::Retryable(
            state.ValidationRouteDescentRejectReason);
    }

    state.ValidationRouteDescentPhase =
        state.ValidationRouteDescentDepartureObserved
            ? Phase::Departed : Phase::Approaching;
    state.ValidationRouteDescentRejectReason.clear();
    return BotActionArbitration::Outcome::Submitted(
        "native_descent_walk_segment_submitted");
}

