#ifndef TRINITY_BOT_NEFARIAN_MAGMA_H
#define TRINITY_BOT_NEFARIAN_MAGMA_H

// Phase 2 magma and the pillar ascent. The user's tactic (user raid
// experience 2026-09-26): as the floor sinks, swim up in the rising magma
// beside your pillar, then hop onto the pillar top once it is level with the
// surface. Every number is native data, recorded with its derivation in
// experiments/configs/cata_raid_encounters/blackwing_descent/
// nefarian_magma_v1.json and re-derived by tests/test_nefarian_magma.py:
// - The magma is WMO liquid group 0 of Blackwingv2.wmo (vmap spawn 857346),
//   flat at world z 2.7713 across the whole arena. LiquidType 19 (WMO Magma)
//   becomes 404 "Blackwing Descent - Magma" through area 5094's override;
//   its liquid spell 81114 deals 5000 fire every second and adds a stack of
//   Magma 81118 (+250 fire damage taken per stack, 99 stacks, 10 s) each
//   second. The core applies it while the unit's feet are below the surface
//   (Unit::ProcessTerrainStatusUpdate, IsInWater).
// - The platform lowers by GoState 24: TransportAnimation.dbc takes the
//   origin from +13.90172 (13133 ms) linearly to 0 (200 ms) over the 13333 ms
//   the stop change lasts, so it sinks 1.0749 yd/s, from 7.03378 to -6.86794.
// - The pillar tops (local 9.925) stop at world 3.0571, 0.286 above the
//   surface; they never go under (0.249 above at the animation's 36 mm dip).
//   The ring (local 1.439) goes under 5.50 s after the platform starts down,
//   the flat centre (local -0.546) after 3.66 s.
// - A pillar is a flat top (radius 3.5-3.9 on the slot headings), a
//   25-degree rim falling 0.465 per yard to a vertical wall at radius 5.3-5.7
//   (rim edge local 9.14-9.16, 0.49 under the surface at the lowered stop),
//   a skirt to local 2.2 out to 6.0, then the ring.
// A swimmer floats with its feet FloatDepthYards (1.2, about 0.6 of the
// player collision height 2.03) under the surface, where the core counts it
// in the liquid. The hop is the client's own jump (vertical speed 7.95577
// yd/s, gravity 19.2911, apex 1.64 yd) at no more than the run speed, from
// the swim station beside the wall onto the rim just above the waterline;
// the member then boards the platform and walks up to its slot. A single jump
// onto the flat top would have to cross the wall edge (0.71 above the feet
// 0.3 yards away) at speed and is not planned.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianGeometry.h"
#include <algorithm>
#include <cmath>
#include <string_view>

namespace BotEncounter::Nefarian
{
constexpr float MagmaSurfaceZ = 2.7713f;
constexpr float FloatDepthYards = 1.2f;
constexpr float SwimSpeedYardsPerSecond = 4.72222f; // MOVE_SWIM base
constexpr float RunSpeedYardsPerSecond = 7.0f;       // MOVE_RUN base
constexpr float JumpVelocity = 7.95577f;
constexpr float JumpGravity = 19.2911f;              // Movement::gravity
constexpr float BodyRadiusYards = 0.389f;

// The lowering stop change (GoState 24) and its animation keys.
constexpr float StopChangeMs = 13333.0f;
constexpr float LinearFromMs = 200.0f;
constexpr float LinearToMs = 13133.0f;
constexpr float RaisedOffset = 13.90172f;

// Elevator origin z `ms` after the lowering starts (the dip keys at the ends
// are within 0.04 of the stops and are left out).
inline float LoweringOriginZ(float ms)
{
    float const progress = std::clamp(StopChangeMs - ms, LinearFromMs, LinearToMs);
    float const offset = RaisedOffset * (progress - LinearFromMs)
        / (LinearToMs - LinearFromMs);
    return PlatformFrame::LoweredOriginZ + offset;
}

// When a local height reaches world z `worldZ` while the platform lowers (0
// if already below, StopChangeMs if never).
inline float LoweringReachesMs(float localZ, float worldZ)
{
    float const offset = worldZ - localZ - PlatformFrame::LoweredOriginZ;
    if (offset >= RaisedOffset)
        return 0.0f;
    if (offset <= 0.0f)
        return StopChangeMs;
    float const progress = LinearFromMs + offset / RaisedOffset
        * (LinearToMs - LinearFromMs);
    return StopChangeMs - progress;
}

// Magma damage of `ticks` seconds in the liquid (10N, before resistance):
// tick k (from 0) deals 5000 + 250 k.
inline float MagmaDamage(uint32 ticks)
{
    uint32 const stacked = std::min<uint32>(ticks, 99);
    float damage = 0.0f;
    for (uint32 tick = 0; tick < ticks; ++tick)
        damage += 5000.0f + 250.0f * float(std::min(tick, stacked));
    return damage;
}

// Each pillar's profile on each slot heading (nefarian_magma_v1.json
// pillar.slots): the flat top's radius on the heading itself, and over the
// heading +-8 degrees (the body's width) the flat top's and the wall's radius.
struct PillarSlotProfile
{
    float FlatRadius;
    float FlatEnvelopeRadius;
    float WallRadius;
};

inline constexpr PillarSlotProfile PillarSlotProfiles[3][6] = {
    { { 3.8f, 3.8f, 5.6f }, { 3.7f, 3.8f, 5.6f }, { 3.7f, 3.8f, 5.6f },
      { 3.7f, 3.7f, 5.5f }, { 3.7f, 3.7f, 5.5f }, { 3.6f, 3.6f, 5.4f } },
    { { 3.7f, 3.8f, 5.6f }, { 3.7f, 3.7f, 5.5f }, { 3.7f, 3.7f, 5.6f },
      { 3.7f, 3.7f, 5.4f }, { 3.6f, 3.7f, 5.5f }, { 3.5f, 3.6f, 5.3f } },
    { { 3.9f, 3.9f, 5.7f }, { 3.8f, 3.9f, 5.7f }, { 3.8f, 3.8f, 5.6f },
      { 3.7f, 3.8f, 5.6f }, { 3.7f, 3.7f, 5.5f }, { 3.6f, 3.6f, 5.4f } },
};

inline PillarSlotProfile const& SlotProfile(uint8 pillar, uint8 slot)
{
    return PillarSlotProfiles[pillar % 3][slot % 6];
}

constexpr float PillarRimSlope = 0.465f;
constexpr float PillarSkirtRadius = 6.05f;
constexpr float PillarSkirtLocalZ = 2.25f;

// Upper envelope of the pillar's surface (local z) on a slot heading at
// `radius` yards from its centre: flat top, rim, wall, skirt, ring.
inline float PillarSurfaceEnvelope(uint8 pillar, uint8 slot, float radius)
{
    PillarSlotProfile const& profile = SlotProfile(pillar, slot);
    if (radius <= profile.FlatEnvelopeRadius)
        return PlatformFrame::PillarTopLocalZ;
    if (radius < profile.WallRadius)
        return PlatformFrame::PillarTopLocalZ
            - PillarRimSlope * (radius - profile.FlatEnvelopeRadius);
    if (radius <= PillarSkirtRadius)
        return PillarSkirtLocalZ;
    return RingLocalZ;
}

// The magma surface in the platform frame at the lowered stop (9.639).
constexpr float LoweredMagmaLocalZ = MagmaSurfaceZ - PlatformFrame::LoweredOriginZ;
// The hop lands on the rim just above the waterline at the lowered stop.
constexpr float HopLandingLocalZ = LoweredMagmaLocalZ + 0.05f;

inline float HopLandingRadius(uint8 pillar, uint8 slot)
{
    return SlotProfile(pillar, slot).FlatRadius
        + (PlatformFrame::PillarTopLocalZ - HopLandingLocalZ) / PillarRimSlope;
}

// The swim station: floating beside the wall on the slot's heading, the
// whole body outside the skirt.
constexpr float SwimStationRadius = 6.7f;

// Descent from the top: walk out to the rim, step off where the body has
// left the wall; the fall lands on the skirt or the ring.
constexpr float DescentRimRadius = 5.0f;
constexpr float DescentStepOffRadius = 7.0f;

inline float DescentOverVoidRadius(uint8 pillar, uint8 slot)
{
    return SlotProfile(pillar, slot).WallRadius + BodyRadiusYards;
}

// The spline MotionMaster::MoveJumpWithGravity launches, as Movement::MoveSpline
// runs it: one straight segment of 3D length L at `velocity`, duration
// 1 + trunc(L * (1000 / velocity)) ms (MoveSpline::init_spline,
// CommonInitializer with minimal_duration 1), x and y linear in time, and
// z = the linear chord + 0.5 * gravity * t * (T - t)
// (MoveSpline::computeParabolicElevation with vertical_acceleration =
// gravity). Its launch vertical speed is rise / T + gravity * T / 2.
inline int32 SplineDurationMs(float length, float velocity)
{
    int32 time = 1;
    time += length * (1000.0f / velocity);
    return time;
}

inline float SplineJumpFeetZ(float fromZ, float rise, float durationSeconds, float t)
{
    return fromZ + rise * t / durationSeconds
        + 0.5f * JumpGravity * t * (durationSeconds - t);
}

struct HopPlan
{
    bool Ok = false;
    std::string_view Reason;
    float LandingRadius = 0.0f;
    float LandingLocalZ = 0.0f;
    float RiseYards = 0.0f;
    float AirTimeSeconds = 0.0f;      // the executed spline's duration
    int32 DurationMs = 0;
    float SplineVelocity = 0.0f;      // MoveJumpWithGravity's speed (3D)
    float LaunchVerticalSpeed = 0.0f; // at most the client's jump speed
    float SpeedXY = 0.0f;
    float MinClearanceYards = 0.0f;
};

// A radial jump on a slot heading, from a swimmer at `fromRadius` yards from
// the pillar centre with its feet at world `fromZ`, onto the rim just above
// the waterline, with the platform origin at `originZ`. The executed spline
// lasts the client's jump air time, rounded down to a whole millisecond (so
// its launch vertical speed never exceeds JumpVelocity), its horizontal
// speed is at most the run speed, and every sample of that spline keeps the
// whole body (radius BodyRadiusYards) above the surface envelope, except the
// descent onto its own landing point.
inline HopPlan PlanHop(uint8 pillar, uint8 slot, float fromRadius, float fromZ,
    float originZ)
{
    HopPlan hop;
    hop.LandingRadius = HopLandingRadius(pillar, slot);
    hop.LandingLocalZ = HopLandingLocalZ;
    float const toZ = originZ + hop.LandingLocalZ;
    hop.RiseYards = toZ - fromZ;
    float const discriminant = JumpVelocity * JumpVelocity
        - 2.0f * JumpGravity * hop.RiseYards;
    if (discriminant < 0.0f)
    {
        hop.Reason = "hop_rise_beyond_jump_apex";
        return hop;
    }
    float const ballistic = (JumpVelocity + std::sqrt(discriminant)) / JumpGravity;
    float const distance = fromRadius - hop.LandingRadius;
    int32 const durationMs = int32(std::floor(ballistic * 1000.0f));
    if (!(distance > 0.0f) || durationMs < 2)
    {
        hop.Reason = "hop_distance_beyond_run_speed";
        return hop;
    }
    float const length = std::sqrt(distance * distance + hop.RiseYards * hop.RiseYards);
    hop.SplineVelocity = length * 1000.0f / (float(durationMs) - 0.5f);
    hop.DurationMs = SplineDurationMs(length, hop.SplineVelocity);
    hop.AirTimeSeconds = float(hop.DurationMs) / 1000.0f;
    hop.LaunchVerticalSpeed = hop.RiseYards / hop.AirTimeSeconds
        + 0.5f * JumpGravity * hop.AirTimeSeconds;
    hop.SpeedXY = distance / hop.AirTimeSeconds;
    if (hop.DurationMs != durationMs || hop.LaunchVerticalSpeed > JumpVelocity + 1e-3f)
    {
        hop.Reason = "hop_spline_timing_mismatch";
        return hop;
    }
    if (hop.SpeedXY > RunSpeedYardsPerSecond)
    {
        hop.Reason = "hop_distance_beyond_run_speed";
        return hop;
    }
    hop.MinClearanceYards = 100.0f;
    constexpr int Samples = 96;
    for (int i = 0; i <= Samples; ++i)
    {
        float const t = hop.AirTimeSeconds * float(i) / float(Samples);
        float const radius = fromRadius - hop.SpeedXY * t;
        if (t > 0.5f * hop.AirTimeSeconds
            && radius - hop.LandingRadius < BodyRadiusYards + 0.05f)
            continue; // settling onto its own landing point
        float const feet = SplineJumpFeetZ(fromZ, hop.RiseYards, hop.AirTimeSeconds, t);
        float surface = -1000.0f;
        for (float side : { -1.0f, -0.5f, 0.0f, 0.5f, 1.0f })
            surface = std::max(surface, originZ + PillarSurfaceEnvelope(pillar, slot,
                radius + side * BodyRadiusYards));
        hop.MinClearanceYards = std::min(hop.MinClearanceYards, feet - surface);
    }
    if (hop.MinClearanceYards < 0.05f)
    {
        hop.Reason = "hop_arc_hits_pillar";
        return hop;
    }
    hop.Ok = true;
    hop.Reason = "hop_lawful";
    return hop;
}
}

#endif
