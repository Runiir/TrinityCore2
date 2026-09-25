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
// Body sweep of a straight walk: line-of-sight rays along the centre line,
// at half and at the full collision radius on both sides, at heights from
// the knee up to 0.9 of the collision height at most this far apart. It is a
// sampled sweep: an obstacle thinner than the ray spacing (0.35 yd upright,
// half the collision radius, about 0.19 yd, sideways) could pass between
// rays; walls, rails, bars and posts that stop a player cannot. Below the
// knee the floor samples (within the floor tolerance) own the clearance.
constexpr float BodySweepFirstLiftYards = 0.5f;
constexpr float BodySweepLiftStepYards = 0.35f;
constexpr float BodySweepSideFractions[] = { 0.0f, 0.5f, -0.5f, 1.0f, -1.0f };
// A member neither aboard nor in flight when a completion override holds
// gets this long to start before the node fails typed.
constexpr std::uint64_t ApproachHandoverGraceMs = 2000;
// A walk or step in flight stays inside this corridor around its declared
// line (the approach start tolerance plus one floor sample).
constexpr float ApproachCorridorYards = ApproachStartToleranceYards + SurfaceSampleStepYards;
// A rejected approach or boarding submission counts toward MaxSubmissions
// at most once per this window. Armed approaches observe every
// ApproachFollowUpMs, so without it five rejections of a passing condition
// (a stun, a cast, a settling spline) would exhaust a member in half a
// second; with it only seconds of persistent refusal do.
constexpr std::uint64_t SubmissionRejectionWindowMs = 1000;

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

// Heights above the segment at which the body sweep casts its rays.
inline std::vector<float> BodySweepLifts(float collisionHeight)
{
    float const top = 0.9f * std::max(collisionHeight, 1.0f);
    std::vector<float> lifts;
    for (float lift = BodySweepFirstLiftYards; lift < top; lift += BodySweepLiftStepYards)
        lifts.push_back(lift);
    lifts.push_back(top);
    return lifts;
}

// Whether (x, y) lies within `lateral` yards of the declared line from
// `from` toward `to`, between `lateral` before `from` and `reach` yards
// along it (reach defaults to the line's own length).
inline bool OnApproachCorridor(Point3 const& from, Point3 const& to, float x, float y,
    float lateral, float reach = -1.0f)
{
    float const dx = to.X - from.X;
    float const dy = to.Y - from.Y;
    float const length = std::hypot(dx, dy);
    if (!from.Valid || !to.Valid || !(length > 0.0f))
        return false;
    float const along = ((x - from.X) * dx + (y - from.Y) * dy) / length;
    float const across = std::fabs((y - from.Y) * dx - (x - from.X) * dy) / length;
    float const end = reach >= 0.0f ? reach : length;
    return across <= lateral && along >= -lateral && along <= end + lateral;
}

// 3D distance from (x, y, z) to the declared ledge-drop line, from the
// approach start to the step-off point. A member whose step off the lip was
// cut short (it stopped still over the ledge floor, on that line) is as much
// at the approach start as one standing on the start point, and steps off
// again from where it stands instead of walking back around to the start.
inline float DistanceToApproachLine(Point3 const& start, Point3 const& end,
    float x, float y, float z)
{
    float const dx = end.X - start.X;
    float const dy = end.Y - start.Y;
    float const dz = end.Z - start.Z;
    float const lengthSq = dx * dx + dy * dy + dz * dz;
    float t = 0.0f;
    if (end.Valid && lengthSq > 0.0f)
        t = std::clamp(((x - start.X) * dx + (y - start.Y) * dy + (z - start.Z) * dz)
            / lengthSq, 0.0f, 1.0f);
    float const px = start.X + dx * t - x;
    float const py = start.Y + dy * t - y;
    float const pz = start.Z + dz * t - z;
    return std::sqrt(px * px + py * py + pz * pz);
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
    // Ledge probes only: some floor lies below the segment within a
    // walkable step-down (MinLedgeDropYards) although not within tolerance.
    bool ShallowFloorBelow = false;

    bool Supported() const { return StaticFloor || TransportFloor; }
};

struct ApproachVerdict
{
    bool Ok = false;
    std::string Reason;
};

// A straight walk is lawful only where a client could walk it: every sample
// is floor-supported except a seam no wider than the player's collision
// radius, and nothing blocks the body's sweep. A boarding walk ends on the
// transport's own surface, not over a closer static floor; any other walk
// starts on it (a passenger, or on its floor), so the seam never makes a
// static-to-static walk off the navmesh.
inline ApproachVerdict ValidateSurfaceWalk(std::vector<SurfaceSample> const& samples,
    float lengthYards, bool collisionFree, bool endOnTransport, bool passenger = false)
{
    if (!(lengthYards > 0.0f) || lengthYards > MaxSurfaceWalkYards)
        return { false, "surface_walk_length_invalid" };
    if (samples.size() < 2)
        return { false, "surface_walk_unsampled" };
    if (!endOnTransport && !passenger && !samples.front().TransportFloor)
        return { false, "surface_walk_not_on_transport" };
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
    // That floor is this transport's own model with no static floor as high,
    // or static ground within the landing tolerance (not another gameobject).
    bool LandingOnTransport = false;
    bool LandingOnStatic = false;
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
    // A ledge: floor under the first part of the step, then none at all. A
    // sloped or stepped lip (floor within a walkable step-down past the edge)
    // is native pathing's, never a level walk through the air above it.
    bool leftFloor = false;
    for (SurfaceSample const& sample : probe.Step)
    {
        if (!sample.Supported())
        {
            if (sample.ShallowFloorBelow)
                return { false, "ledge_drop_lip_not_a_clean_drop" };
            leftFloor = true;
        }
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
    if (contract.LandOnTransport ? !probe.LandingOnTransport : !probe.LandingOnStatic)
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
