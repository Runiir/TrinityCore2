#ifndef TRINITY_BOT_LIQUID_BODY_CLEARANCE_H
#define TRINITY_BOT_LIQUID_BODY_CLEARANCE_H

// The swimmer's whole body along its swim and its hop, and where it boards
// (BotWorldPopulationMgrNativePathTransportLiquid.cpp).
//
// Before round 3 the swim and the hop were swept on their centre line only
// (line of sight at 0.15, half and 0.9 of the height, no lateral radius, the
// end point unproven): a swim beside the pillar skirt or a hop whose arc
// passed the wall edge could end with the side of the body inside the model.
// Here each is proven with the body cylinder of
// Movement/Spline/PassengerBodyTrajectory.h (knee to head, full collision
// radius), against the same ray query as the step-off's fall (static and
// dynamic line of sight, and the transport's own model):
// - Swim: the straight segment MoveSplineInit::MoveTo runs, and the body at
//   its end point.
// - Hop: the jump MoveJumpWithGravity runs, sampled every SampleStepMs as the
//   spline computes it (BotValidationRouteNativeLiquid::SplineJumpFeetZ),
//   reduced to chords with the body grown (radius, knee down, head up: a
//   parabola's apex rises straight above its chord) by the chords' deviation
//   and the arc's bulge between samples, and the body at the landing; at
//   least half of the inner landing footprint on the platform's surface.
//   With the requested landing obstructed, ChooseClearHop tries nearby
//   landings on the same rim (farther along the jump, then to either side)
//   before it refuses, as the step-off chooser moves out along its heading.
// - Emerge: the body standing where the swimmer reports it, knee to head,
//   is empty: a rising surface that already passed the knee is refused, not
//   boarded inside.
// Pure: the executor supplies the ray query and the floor probes.

#include "Bots/BotValidationRouteNativeLiquid.h"
#include "Movement/Spline/PassengerBodyTrajectory.h"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace BotLiquidBodyClearance
{
namespace Body = Movement::BodyTrajectory;
namespace Liquid = BotValidationRouteNativeLiquid;

constexpr char const* SwimBodyObstructedReason = "native_liquid_swim_body_obstructed";
constexpr char const* HopBodyObstructedReason = "native_liquid_hop_body_obstructed";
constexpr char const* HopFootprintUnsupportedReason = "native_liquid_hop_landing_footprint_unsupported";
constexpr char const* EmergeBodyObstructedReason = "native_liquid_emerge_body_obstructed";

// Nearby landings tried after the requested one: along the jump's own
// horizontal direction (farther onto the rim) and across it, in yards.
struct LandingOffset
{
    float Along;
    float Across;
};

inline constexpr LandingOffset HopLandingOffsets[] = {
    { 0.0f, 0.0f },
    { 0.25f, 0.0f }, { 0.5f, 0.0f },
    { 0.0f, 0.25f }, { 0.0f, -0.25f },
    { 0.25f, 0.25f }, { 0.25f, -0.25f },
    { 0.0f, 0.5f }, { 0.0f, -0.5f },
};
constexpr std::size_t HopLandingCandidates = sizeof(HopLandingOffsets) / sizeof(HopLandingOffsets[0]);
// The farthest a chosen landing lies from the requested one, its height on
// the 25-degree rim included (the executor accepts a jump in flight toward
// any of them as the requested hop; the strategy recognizes its hop in
// flight within 0.6 yards of its landing).
constexpr float MaxLandingShiftYards = 0.6f;

struct TrajectoryProof
{
    Body::Proof Proof;
    std::size_t Samples = 0;
    std::size_t Chords = 0;
    float InflationYards = 0.0f;
    bool Clear() const { return Proof.Clear(); }
};

// The straight swim, and the body at its end.
template <class Vec, class Blocked>
TrajectoryProof ProveSwim(Vec const& from, Vec const& to, float radius, float height,
    Blocked&& blocked)
{
    TrajectoryProof result;
    result.Samples = 2;
    result.Chords = 1;
    result.Proof = Body::ProveTrajectory(std::vector<Vec>{ from, to },
        Body::MakeBody(radius, height), blocked);
    return result;
}

// The feet along the jump spline MoveJumpWithGravity launches: x and y
// linear in time, z the chord plus the parabola, every SampleStepMs and at
// its end.
template <class Vec>
std::vector<Vec> HopSamples(Vec const& from, Vec const& to, Liquid::SplineJump const& jump)
{
    std::vector<Vec> samples;
    if (jump.DurationMs <= 0)
        return samples;
    auto at = [&](std::int32_t ms)
    {
        float const along = float(ms) / float(jump.DurationMs);
        return Vec{ from.x + (to.x - from.x) * along, from.y + (to.y - from.y) * along,
            Liquid::SplineJumpFeetZ(from.z, to.z - from.z, jump.DurationSeconds,
                float(ms) / 1000.0f) };
    };
    for (std::int32_t ms = 0; ms < jump.DurationMs; ms += Body::SampleStepMs)
        samples.push_back(at(ms));
    samples.push_back(at(jump.DurationMs));
    return samples;
}

// The jump's chords with the inflated body, and the body at the landing.
template <class Vec, class Blocked>
TrajectoryProof ProveHop(Vec const& from, Vec const& to, Liquid::SplineJump const& jump,
    float radius, float height, Blocked&& blocked)
{
    TrajectoryProof result;
    std::vector<Vec> const samples = HopSamples(from, to, jump);
    result.Samples = samples.size();
    if (samples.size() < 2)
    {
        result.Proof.Kind = Body::Obstruction::Path;
        return result;
    }
    Body::Chords const chords = Body::ReduceToChords(samples);
    std::vector<Vec> trajectory;
    trajectory.reserve(chords.Kept.size());
    for (std::size_t index : chords.Kept)
        trajectory.push_back(samples[index]);
    result.Chords = trajectory.size() - 1;
    result.InflationYards = chords.InflationYards;
    result.Proof = Body::ProveTrajectory(trajectory,
        Body::MakeBody(radius, height, chords.InflationYards), blocked);
    return result;
}

// The body standing with its feet at `feet`, knee to head, is empty.
template <class Vec, class Blocked>
bool BodyClearAt(Vec const& feet, float radius, float height, Blocked&& blocked,
    std::uint32_t& rays)
{
    return Body::CylinderClear(feet, Body::MakeBody(radius, height), blocked, rays);
}

// A landing `offset` from the requested one, in the jump's horizontal frame
// (its z is the executor's own floor query there).
template <class Vec>
Vec OffsetLanding(Vec const& from, Vec const& requested, LandingOffset offset)
{
    float const dx = requested.x - from.x;
    float const dy = requested.y - from.y;
    float const length = std::sqrt(dx * dx + dy * dy);
    if (!(length > Body::DegenerateYards))
        return requested;
    float const ux = dx / length, uy = dy / length;
    return Vec{ requested.x + ux * offset.Along - uy * offset.Across,
        requested.y + uy * offset.Along + ux * offset.Across, requested.z };
}

// What the executor proved for one landing.
struct HopCandidate
{
    // The landing itself is admissible (on the platform's surface, not a
    // static floor, a lawful jump): otherwise Reason names why.
    bool Admissible = false;
    std::string Reason;
    bool BodyClear = false;
    std::uint32_t InnerSupported = 0;
    std::uint32_t InnerPoints = 0;
    std::uint32_t Rays = 0;
};

inline bool FootprintSupported(HopCandidate const& candidate)
{
    return candidate.InnerPoints > 0 && 2 * candidate.InnerSupported >= candidate.InnerPoints;
}

struct HopChoice
{
    bool Ok = false;
    std::string Reason;
    std::size_t Index = 0;       // into HopLandingOffsets
    std::uint32_t Proofs = 0;
    std::uint32_t Rays = 0;
};

// The requested landing when its whole jump is clear; otherwise the first
// nearby landing that is. `probeAt(index)` probes HopLandingOffsets[index].
// Refused: the requested landing's own reason when it is not admissible
// (nothing nearby is tried for a landing that is not a hop at all), else the
// body's reason (obstructed, or the footprint not on the surface).
template <class ProbeAt>
HopChoice ChooseClearHop(ProbeAt&& probeAt)
{
    HopChoice choice;
    for (std::size_t index = 0; index < HopLandingCandidates; ++index)
    {
        HopCandidate const candidate = probeAt(index);
        choice.Rays += candidate.Rays;
        if (!candidate.Admissible)
        {
            if (index == 0)
            {
                choice.Reason = candidate.Reason;
                return choice;
            }
            continue;
        }
        ++choice.Proofs;
        bool const supported = FootprintSupported(candidate);
        if (candidate.BodyClear && supported)
        {
            choice.Ok = true;
            choice.Index = index;
            choice.Reason = "liquid_hop_body_clear";
            return choice;
        }
        if (choice.Reason.empty())
            choice.Reason = candidate.BodyClear ? HopFootprintUnsupportedReason
                : HopBodyObstructedReason;
    }
    if (choice.Reason.empty())
        choice.Reason = HopBodyObstructedReason;
    return choice;
}
}

#endif
