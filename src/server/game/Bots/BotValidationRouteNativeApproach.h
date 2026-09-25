#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_APPROACH_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_APPROACH_H

// Pure predicates for the lawful final approach onto a transport surface
// that the static navmesh does not reach:
// - surface walk: one straight walk at native speed from the navmesh edge
//   across the platform's own collision model, launched only when every
//   sample of the segment has a floor within tolerance of the segment's own
//   height and static and dynamic line of sight is clear;
// - ledge drop: a short proven walk off a ledge lip, then the core's own
//   MotionMaster::MoveFall (native gravity onto the floor Map::GetHeight
//   finds, exactly where the fall will land), then the client's landing
//   report so Player::HandleFall applies native fall damage.
// The server adapter samples the real map; these functions only decide.
// Included by the contract parser, the route logic, the executor and tests.

#include "Bots/BotValidationRouteNativeTypes.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

namespace BotValidationRouteNative
{
// Spacing of the floor samples along a straight segment.
constexpr float SurfaceSampleStepYards = 0.25f;
// Longest straight walk across a transport surface.
constexpr float MaxSurfaceWalkYards = 12.0f;
// Longest walk from a ledge edge to the point where the fall starts.
constexpr float MaxStepOffYards = 4.0f;
// A shallower drop is a walkable step-down owned by native pathing (the
// native_walkable_descent executor admits steps of up to 4 yd).
constexpr float MinLedgeDropYards = 4.0f;
// DEFAULT_PLAYER_BOUNDING_RADIUS (ObjectDefines.h). A floor seam no wider
// than the player's collision radius cannot swallow the player.
constexpr float PlayerBoundingRadiusYards = 0.389f;
constexpr float MaxUnsupportedSpanYards = PlayerBoundingRadiusYards;
// A member within this distance of its approach start may begin.
constexpr float ApproachStartToleranceYards = 1.0f;
// A settled member with no verified floor is re-snapped by an ordinary
// native-path move only when some floor lies within the navmesh step
// height (walkableClimb 1.6 yd) of its feet, at most this many times.
constexpr float ResnapFloorBandYards = 1.6f;
constexpr std::uint32_t MaxResnapMoves = 3;
// While an approach is armed or in flight the next decision follows within
// this delay, like a player reacting to the platform or to landing.
constexpr std::uint32_t ApproachFollowUpMs = 100;
// Worst case from a walk's arrival to the boarding report: one follow-up
// decision plus world update jitter.
constexpr std::uint64_t ApproachBoardLatencyMs = 250;
// A platform is stationary while its origin stays within this of its height.
constexpr float StationaryLevelToleranceYards = 0.75f;

// Movement::gravity, Movement::terminalVelocity (MovementUtil.cpp).
constexpr float NativeGravity = 19.29110527038574f;
constexpr float NativeTerminalVelocity = 60.148003f;
// Player::HandleFall ignores falls shorter than this.
constexpr float NativeFallDamageMinHeight = 14.57f;

// Movement::computeFallTime(height, false), in milliseconds.
inline std::uint64_t NativeFallTimeMs(float height)
{
    if (!(height > 0.0f))
        return 0;
    float const terminalLength = NativeTerminalVelocity * NativeTerminalVelocity
        / (2.0f * NativeGravity);
    float const seconds = height >= terminalLength
        ? (height - terminalLength) / NativeTerminalVelocity
            + NativeTerminalVelocity / NativeGravity
        : std::sqrt(2.0f * height / NativeGravity);
    return std::uint64_t(seconds * 1000.0f);
}

// Player::HandleFall: damage as a fraction of maximum health before absorbs;
// zero when a native aura (hover, feather fall, flight) or immunity negates
// it. `safeFallYards` is SPELL_AURA_SAFE_FALL, `damageRate` Rate.Damage.Fall.
inline float NativeFallDamageFraction(float fallHeight, float safeFallYards,
    float damageRate, bool negated)
{
    if (negated || !(fallHeight >= NativeFallDamageMinHeight))
        return 0.0f;
    float const fraction = (0.018f * (fallHeight - safeFallYards) - 0.2426f) * damageRate;
    return std::clamp(fraction, 0.0f, 1.0f);
}

inline std::uint64_t WalkTimeMs(float yards, float speed)
{
    if (!(yards > 0.0f))
        return 0;
    return std::uint64_t(yards / std::max(speed, 0.1f) * 1000.0f);
}

// One floor sample along a straight segment: a floor lies within the floor
// tolerance of the segment's own height at this point.
struct SurfaceSample
{
    // Horizontal yards from the segment start; samples are evenly spaced.
    float Along = 0.0f;
    bool StaticFloor = false;
    // This transport's own collision model, not merely its bounding box.
    bool TransportFloor = false;

    bool Supported() const { return StaticFloor || TransportFloor; }
};

struct ApproachVerdict
{
    bool Ok = false;
    std::string Reason;
};

// A straight walk is lawful only where a client could walk it: every sample
// is floor-supported except a seam no wider than the player's collision
// radius, and nothing blocks the way. A boarding walk ends on the
// transport's own surface, not over a closer static floor.
inline ApproachVerdict ValidateSurfaceWalk(std::vector<SurfaceSample> const& samples,
    float lengthYards, bool collisionFree, bool endOnTransport)
{
    if (!(lengthYards > 0.0f) || lengthYards > MaxSurfaceWalkYards)
        return { false, "surface_walk_length_invalid" };
    if (samples.size() < 2)
        return { false, "surface_walk_unsampled" };
    if (!collisionFree)
        return { false, "surface_walk_blocked" };
    if (!samples.front().Supported())
        return { false, "surface_walk_start_unsupported" };
    if (!samples.back().Supported())
        return { false, "surface_walk_end_unsupported" };
    if (endOnTransport && (!samples.back().TransportFloor || samples.back().StaticFloor))
        return { false, "surface_walk_end_not_on_transport" };
    float const spacing = samples[1].Along - samples[0].Along;
    float lastSupported = samples.front().Along;
    for (SurfaceSample const& sample : samples)
    {
        if (!sample.Supported())
            continue;
        if (sample.Along - lastSupported - spacing > MaxUnsupportedSpanYards + 1e-4f)
            return { false, "surface_walk_unsupported_span" };
        lastSupported = sample.Along;
    }
    return { true, "surface_walk_verified" };
}

// Everything the server adapter observed about one candidate step-off.
struct LedgeDropProbe
{
    // Level step from the member's feet to the step-off point.
    std::vector<SurfaceSample> Step;
    float StepLengthYards = 0.0f;
    float StepZ = 0.0f;
    bool StepCollisionFree = false;
    // Footprint points (centre and the collision radius around it) that
    // still find a floor less than MinLedgeDropYards below the step.
    std::uint32_t FootprintSupported = 0;
    // The floor MotionMaster::MoveFall will land on from the step-off point.
    bool LandingFound = false;
    float LandingZ = 0.0f;
    // That floor is this transport's own model with no static floor as high.
    bool LandingOnTransport = false;
    bool LandingInLiquid = false;
    float HealthPct = 0.0f;
    float PredictedDamagePct = 0.0f;
};

inline ApproachVerdict ValidateLedgeDrop(ApproachContract const& contract,
    LedgeDropProbe const& probe)
{
    if (!(probe.StepLengthYards > 0.0f) || probe.StepLengthYards > MaxStepOffYards)
        return { false, "ledge_drop_step_length_invalid" };
    if (probe.Step.size() < 2 || !probe.Step.front().Supported())
        return { false, "ledge_drop_edge_unsupported" };
    // A ledge: floor under the first part of the step, then none at all.
    bool leftFloor = false;
    for (SurfaceSample const& sample : probe.Step)
    {
        if (!sample.Supported())
            leftFloor = true;
        else if (leftFloor)
            return { false, "ledge_drop_step_profile_not_a_ledge" };
    }
    if (!leftFloor)
        return { false, "ledge_drop_step_off_over_floor" };
    if (!probe.StepCollisionFree)
        return { false, "ledge_drop_step_blocked" };
    if (probe.FootprintSupported)
        return { false, "ledge_drop_step_off_footprint_supported" };
    if (!probe.LandingFound)
        return { false, "ledge_drop_landing_missing" };
    if (probe.StepZ - probe.LandingZ < MinLedgeDropYards)
        return { false, "ledge_drop_too_shallow" };
    if (std::fabs(probe.LandingZ - contract.LandingZ) > contract.LandingToleranceYards)
        return { false, "ledge_drop_landing_height_mismatch" };
    if (probe.LandingInLiquid)
        return { false, "ledge_drop_lands_in_liquid" };
    if (probe.LandingOnTransport != contract.LandOnTransport)
        return { false, "ledge_drop_landing_surface_mismatch" };
    if (probe.HealthPct - probe.PredictedDamagePct < contract.MinHealthAfterFallPct)
        return { false, "ledge_drop_health_margin_low" };
    return { true, "ledge_drop_verified" };
}

// Candidates walk out from the member along the declared heading; the fall
// starts at the first one whose whole footprint has left the lip. Only these
// rejections (still on or over the lip) move to the next candidate, within
// MaxStepOffYards of the member; every other rejection is final.
inline bool StepOffCandidateAdvances(std::string const& reason)
{
    return reason == "ledge_drop_step_off_over_floor"
        || reason == "ledge_drop_step_off_footprint_supported";
}
}

#endif
