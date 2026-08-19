#include "Bots/BotWorldPopulationMgr.h"

#include "GameTime.h"
#include "Map.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Unit.h"

#include <chrono>
#include <cmath>
#include <string>

namespace
{
uint64 NativeMovementNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
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
    uint64 const nowMs = NativeMovementNowMs();

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
            std::string("native_descent_no_progress_") + stalledPhase;
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
        return BotActionArbitration::Outcome::Terminal(failureReason);
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

    // Falling is observation-only.  MotionMaster owns the native transition;
    // this executor never replaces gravity with another movement spline.
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
            state.LastNoProgressReason =
                "native_descent_grounded_stability_pending";
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
    // declared landing.  Height samples also enforce walk-sized transitions.
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
