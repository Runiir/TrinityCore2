#ifndef TRINITY_BOT_LEDGE_DROP_BODY_CLEARANCE_H
#define TRINITY_BOT_LEDGE_DROP_BODY_CLEARANCE_H

// The step-off a member takes is one whose whole native fall is proven, not
// only the floor under its centre. MotionMaster::MoveFall (and the
// executor's LaunchFallOnto) falls straight down from the step-off point; the
// landing proof of BotValidationRouteNativeApproach.h checks the floor under
// the centre alone, so a candidate beside a sloped pillar skirt landed the
// centre on the ring with the side of the body in the skirt (BWD 10N round 3,
// pillar 1 slot 2: step 1.0 yd, centre landing at local 1.439, skirt at
// 2.106 at 0.38 yd). Here the vertical fall of the body cylinder
// (Movement/Spline/PassengerBodyTrajectory.h) and the landing footprint must
// be clear as well; an obstructed candidate moves on to the next one farther
// out, like a landing that is not yet the declared floor, and with none
// clear within MaxStepOffYards the step is refused with
// ledge_drop_fall_body_obstructed.
// Pure: the executor supplies the probes.

#include "Bots/BotValidationRouteNativeApproach.h"

#include <cstdint>
#include <string>

namespace BotLedgeDropBodyClearance
{
namespace Route = BotValidationRouteNative;

constexpr char const* BodyObstructedReason = "ledge_drop_fall_body_obstructed";
constexpr char const* FootprintUnsupportedReason = "ledge_drop_landing_footprint_unsupported";

// What the executor observed about the body's fall from one candidate.
struct FallBodyProbe
{
    // The body cylinder, from the knee to the head, clear all the way down
    // and at the landing.
    bool PathClear = false;
    bool LandingClear = false;
    // Inner footprint points (half the collision radius around the centre)
    // with a floor within the floor tolerance of the landing.
    std::uint32_t InnerSupported = 0;
    std::uint32_t InnerPoints = 0;
    std::uint32_t Rays = 0;
};

// The body lands standing: at least half of its inner footprint is on the
// landing floor (the centre's floor is ValidateLedgeDrop's), not balanced on
// a seam over a deeper hole.
inline bool FootprintSupported(FallBodyProbe const& probe)
{
    return probe.InnerPoints > 0 && 2 * probe.InnerSupported >= probe.InnerPoints;
}

inline Route::ApproachVerdict ValidateFallBody(FallBodyProbe const& probe)
{
    if (!probe.LandingClear || !probe.PathClear)
        return { false, BodyObstructedReason };
    if (!FootprintSupported(probe))
        return { false, FootprintUnsupportedReason };
    return { true, "ledge_drop_verified" };
}

inline bool BodyReasonAdvances(std::string const& reason)
{
    return reason == BodyObstructedReason || reason == FootprintUnsupportedReason;
}

// Route::ChooseStepOff with the body's fall proven too: bodyAt(step, probe)
// runs only for a candidate ValidateLedgeDrop admits (the landing it proves
// is probe.LandingZ). A body rejection advances to the next candidate. With
// no candidate admitted, a body rejection seen on the way is the refusal
// (the first one); otherwise ChooseStepOff's own choice.
struct Choice
{
    Route::StepOffChoice Step;
    std::uint32_t BodyProofs = 0;
    std::uint32_t Rays = 0;
};

template <typename ProbeAt, typename BodyAt>
Choice ChooseClearStepOff(Route::ApproachContract const& contract, ProbeAt&& probeAt,
    BodyAt&& bodyAt)
{
    Choice result;
    Route::StepOffChoice pastLip;
    Route::StepOffChoice firstBody;
    bool leftLip = false;
    bool bodyRejected = false;
    Route::StepOffChoice& choice = result.Step;
    for (float step = Route::SurfaceSampleStepYards; step <= Route::MaxStepOffYards + 1e-3f;
        step += Route::SurfaceSampleStepYards)
    {
        Route::LedgeDropProbe const probe = probeAt(step);
        choice.Verdict = Route::ValidateLedgeDrop(contract, probe);
        choice.StepYards = step;
        if (choice.Verdict.Ok)
        {
            FallBodyProbe const body = bodyAt(step, probe);
            ++result.BodyProofs;
            result.Rays += body.Rays;
            choice.Verdict = ValidateFallBody(body);
            if (choice.Verdict.Ok)
                return result;
            if (!bodyRejected)
            {
                bodyRejected = true;
                firstBody = choice;
            }
        }
        else if (!Route::StepOffCandidateAdvances(choice.Verdict.Reason))
        {
            if (bodyRejected)
                choice = firstBody;
            return result;
        }
        if (!leftLip && !Route::StepOffStillOnLip(choice.Verdict.Reason))
        {
            leftLip = true;
            pastLip = choice;
        }
    }
    choice = bodyRejected ? firstBody : leftLip ? pastLip : choice;
    return result;
}
}

#endif
