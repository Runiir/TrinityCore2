#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_LIQUID_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_LIQUID_H

// Pure rules of the swimmer's transport stages (Float, Swim, Hop, Emerge;
// BotWorldPopulationMgrNativePathTransportLiquid.cpp), testable without the
// world. The jump is the client's: vertical launch speed JumpVelocity, the
// core's gravity (Movement::gravity), a constant horizontal speed no faster
// than the run speed, landing on the way down.

#include "Define.h"
#include <cmath>
#include <string>

namespace BotValidationRouteNativeLiquid
{
constexpr float JumpVelocity = 7.95577f;
constexpr float JumpGravity = 19.2911f;
constexpr float MaxSwimYards = 12.0f;
constexpr float SwimSampleStepYards = 1.0f;
constexpr float FloatDepthSlackYards = 0.05f;
constexpr float JumpClearanceYards = 0.05f;
constexpr uint32 JumpSamples = 24;
constexpr uint32 BoardLatencyMs = 500;

// The outcome the executor gives a stage while its submitted hop is still in
// the air: progress (a committed outcome), so the arbitration keeps the hop's
// movement, GCD and cast lanes for that tick.
constexpr char const* HopInFlightReason = "native_liquid_hop_in_flight";

// ZLiquidStatus: LIQUID_MAP_IN_WATER | LIQUID_MAP_UNDER_WATER.
constexpr uint32 SwimmingLiquidStatus = 0x04 | 0x08;

inline bool InLiquid(uint32 liquidStatus)
{
    return (liquidStatus & SwimmingLiquidStatus) != 0;
}

// The feet are at least `depth` under the liquid surface `level`.
inline bool FloatDepthReached(float level, float feetZ, float depth)
{
    return level - feetZ >= depth - FloatDepthSlackYards;
}

inline float JumpApexYards()
{
    return JumpVelocity * JumpVelocity / (2.0f * JumpGravity);
}

struct JumpPlan
{
    bool Ok = false;
    std::string Reason;
    float AirTimeSeconds = 0.0f;
    float SpeedXY = 0.0f;
};

// The client's jump that lands `rise` yards higher (negative: lower) and
// `horizontal` yards away, on its way down.
inline JumpPlan PlanJump(float horizontal, float rise, float maxSpeedXY)
{
    JumpPlan plan;
    float const discriminant = JumpVelocity * JumpVelocity - 2.0f * JumpGravity * rise;
    if (discriminant < 0.0f)
    {
        plan.Reason = "liquid_hop_rise_beyond_jump_apex";
        return plan;
    }
    plan.AirTimeSeconds = (JumpVelocity + std::sqrt(discriminant)) / JumpGravity;
    plan.SpeedXY = horizontal / plan.AirTimeSeconds;
    if (!(horizontal > 0.05f) || plan.SpeedXY > maxSpeedXY)
    {
        plan.Reason = "liquid_hop_distance_beyond_run_speed";
        return plan;
    }
    plan.Ok = true;
    plan.Reason = "liquid_hop_lawful";
    return plan;
}

// Height of the feet `t` seconds into the ballistic jump.
inline float JumpFeetZ(float fromZ, float t)
{
    return fromZ + JumpVelocity * t - 0.5f * JumpGravity * t * t;
}

// The spline MotionMaster::MoveJumpWithGravity launches, as
// Movement::MoveSpline runs it: one straight segment of 3D length L at
// `velocity`, duration 1 + trunc(L * (1000 / velocity)) ms
// (MoveSpline::init_spline: CommonInitializer, minimal_duration 1), x and y
// linear in time, z the linear chord plus 0.5 * gravity * t * (T - t)
// (MoveSpline::computeParabolicElevation with the vertical acceleration
// SetParabolicVerticalAcceleration set). Its launch vertical speed is
// rise / T + gravity * T / 2.
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

struct SplineJump
{
    bool Ok = false;
    std::string Reason;
    int32 DurationMs = 0;
    float DurationSeconds = 0.0f;
    float Velocity = 0.0f;            // the spline speed along its 3D segment
    float LaunchVerticalSpeed = 0.0f;
    float SpeedXY = 0.0f;
};

// The client's jump as that spline: its duration is the ballistic air time
// rounded down to a whole millisecond (the launch vertical speed then never
// exceeds JumpVelocity), its speed the 3D length over that duration, checked
// against the duration MoveSpline will actually compute.
inline SplineJump PlanSplineJump(float horizontal, float rise, float maxSpeedXY)
{
    SplineJump jump;
    JumpPlan const ballistic = PlanJump(horizontal, rise, 1000.0f);
    if (!ballistic.Ok)
    {
        jump.Reason = ballistic.Reason;
        return jump;
    }
    int32 const wanted = int32(std::floor(ballistic.AirTimeSeconds * 1000.0f));
    if (wanted < 2)
    {
        jump.Reason = "liquid_hop_duration_invalid";
        return jump;
    }
    float const length = std::sqrt(horizontal * horizontal + rise * rise);
    jump.Velocity = length * 1000.0f / (float(wanted) - 0.5f);
    jump.DurationMs = SplineDurationMs(length, jump.Velocity);
    jump.DurationSeconds = float(jump.DurationMs) / 1000.0f;
    jump.LaunchVerticalSpeed = rise / jump.DurationSeconds
        + 0.5f * JumpGravity * jump.DurationSeconds;
    jump.SpeedXY = horizontal / jump.DurationSeconds;
    if (jump.DurationMs != wanted || jump.LaunchVerticalSpeed > JumpVelocity + 1e-3f)
    {
        jump.Reason = "liquid_hop_spline_timing_mismatch";
        return jump;
    }
    if (jump.SpeedXY > maxSpeedXY)
    {
        jump.Reason = "liquid_hop_distance_beyond_run_speed";
        return jump;
    }
    jump.Ok = true;
    jump.Reason = "liquid_hop_lawful";
    return jump;
}
}

#endif
