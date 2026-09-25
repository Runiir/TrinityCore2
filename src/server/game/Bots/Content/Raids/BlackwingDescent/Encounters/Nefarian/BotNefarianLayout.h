#ifndef TRINITY_BOT_NEFARIAN_LAYOUT_H
#define TRINITY_BOT_NEFARIAN_LAYOUT_H

// Arena layout for Nefarian's End, derived from the duty plan: where each
// dragon should end up and where the tanks lead them. Guides (Wowhead, Icy
// Veins) put the dragons at opposite ends, angled along the walls, with the
// raid on their wings. Natively a chasing dragon stops at its melee reach
// (Onyxia 20.8, Nefarian 22.8 yd) short of its tank, and only turns while
// the tank stays inside that reach. So a tank:
// - pulls: stands on the ring at r 52 beyond the dragon's end; the dragon
//   chases out from the centre and stops at about r 29-31;
// - holds: once the dragon is at r >= 27.5 within 15 degrees of its end,
//   stands 7 yards from it, tangentially and 25 degrees outward, so the
//   dragon faces along the wall with its tail away from the raid.
// Opposite ends at r >= 27.5 are at least 2 * 27.5 * cos(15) = 53 yards
// apart, beyond Children of Deathwing's 50 yards.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianPath.h"

namespace BotEncounter::Nefarian
{
constexpr float TankPullRadius = 52.0f;
constexpr float DragonHoldMinRadius = 27.5f;
constexpr float DragonGoalAngleToleranceDeg = 15.0f;
constexpr float DragonEndOffsetDeg = 30.0f;
constexpr float TankHoldDistance = 7.0f;
constexpr float TankHoldOutwardDeg = 25.0f;
constexpr float TankDischargeDistance = 7.0f;
constexpr float PullMirrorLimitDeg = 25.0f;

struct ArenaLayout
{
    float OnyxiaEndAngle = DegToRad(DragonEndOffsetDeg);
    float NefarianEndAngle = DegToRad(DragonEndOffsetDeg) - Pi;
    // Phase 3: Nefarian stays near the centre facing his tank.
    float NefarianGroundFacing = 0.0f;
};

inline float PillarAngle(int pillar)
{
    return AngleOf(PillarCenters[pillar < 0 ? 0 : pillar % 3]);
}

inline float AngularGap(float left, float right)
{
    return std::fabs(NormalizeSigned(left - right));
}

// Onyxia's end sits beside her tank's phase-2 pillar and Nefarian's end is
// opposite it, rotated toward his tank's pillar, so each tank reaches its
// platform quickly when the floor sinks.
inline ArenaLayout BuildArenaLayout(DutyPlan const& plan)
{
    ArenaLayout layout;
    int const onyxiaPillar = plan.PillarOf(plan.OnyxiaTank);
    int const nefarianPillar = plan.PillarOf(plan.NefarianTank);
    float const base = PillarAngle(onyxiaPillar);
    float const offset = DegToRad(DragonEndOffsetDeg);
    float bestGap = 10.0f;
    for (float sign : { 1.0f, -1.0f })
    {
        float const onyxia = NormalizeSigned(base + sign * offset);
        float const nefarian = NormalizeSigned(onyxia + Pi);
        float const gap = nefarianPillar < 0 ? 0.0f
            : AngularGap(nefarian, PillarAngle(nefarianPillar));
        if (gap < bestGap)
        {
            bestGap = gap;
            layout.OnyxiaEndAngle = onyxia;
            layout.NefarianEndAngle = nefarian;
        }
    }
    layout.NefarianGroundFacing = PillarAngle(nefarianPillar);
    return layout;
}

enum class TankStep : uint8
{
    LeadOut,   // dragon near the centre: pull it out toward its end
    Pull,      // dragon short of its end or off its heading: pull again
    Hold,      // at its end: stand tangentially ahead (dragon only turns)
    Discharge  // Onyxia wind-up: stand outward so her tail faces the raid
};

inline std::string_view TankStepName(TankStep step)
{
    switch (step)
    {
        case TankStep::LeadOut: return "lead_out";
        case TankStep::Pull: return "pull";
        case TankStep::Hold: return "hold";
        case TankStep::Discharge: return "discharge_turn";
    }
    return "unknown";
}

struct TankSpot
{
    TankStep Step = TankStep::Hold;
    LocalPoint Point;
};

inline bool DragonAtEnd(LocalPoint dragon, float goalAngle)
{
    return Length(dragon) >= DragonHoldMinRadius
        && AngularGap(AngleOf(dragon), goalAngle)
            <= DegToRad(DragonGoalAngleToleranceDeg);
}

inline TankSpot PlanTankSpot(LocalPoint dragon, float goalAngle, float reach,
    bool dischargeTurn)
{
    TankSpot spot;
    float const radius = Length(dragon);
    float const dragonAngle = radius < 1.0f ? goalAngle : AngleOf(dragon);
    if (!DragonAtEnd(dragon, goalAngle))
    {
        // A dragon off its heading is pulled past its end by the same angle,
        // on a heading whose radial line clears the pillars.
        float mirror = 0.0f;
        if (radius >= 8.0f)
            mirror = std::max(-DegToRad(PullMirrorLimitDeg),
                std::min(DegToRad(PullMirrorLimitDeg),
                    -NormalizeSigned(dragonAngle - goalAngle)));
        float const pull = NearestRadialCrossing(goalAngle + mirror, goalAngle);
        spot.Step = radius < 8.0f ? TankStep::LeadOut : TankStep::Pull;
        spot.Point = Polar(pull, TankPullRadius);
        return spot;
    }

    if (dischargeTurn)
    {
        LocalPoint const outward = Offset(dragon, dragonAngle,
            TankDischargeDistance);
        if (OnFloorArea(outward))
        {
            spot.Step = TankStep::Discharge;
            spot.Point = outward;
            return spot;
        }
    }

    spot.Step = TankStep::Hold;
    float const turn = Pi / 2.0f - DegToRad(TankHoldOutwardDeg);
    std::optional<LocalPoint> fallback;
    for (float sign : { 1.0f, -1.0f })
    {
        LocalPoint const raw = Offset(dragon, dragonAngle + sign * turn,
            TankHoldDistance);
        LocalPoint const point = SnapToStandingArea(raw);
        if (Distance(point, dragon) > reach - 3.0f)
            continue;
        if (OnFloorArea(point))
        {
            spot.Point = point;
            return spot;
        }
        if (!fallback)
            fallback = point;
    }
    spot.Point = fallback ? *fallback
        : Offset(dragon, dragonAngle, TankDischargeDistance);
    return spot;
}

// Raid anchor between the dragons: half of the dragons' midpoint, which lies
// on both inner wings once they face tangentially at opposite ends. Before
// Nefarian lands the raid waits on Onyxia's side of the centre, where he
// lands, so he is led away from the raid rather than through it.
inline LocalPoint RaidAnchor(ArenaLayout const& layout, LocalPoint onyxia,
    LocalPoint nefarian, bool nefarianLanded)
{
    if (!nefarianLanded)
        return Polar(layout.OnyxiaEndAngle, 8.0f);
    return { (onyxia.X + nefarian.X) * 0.25f, (onyxia.Y + nefarian.Y) * 0.25f };
}
}

#endif
