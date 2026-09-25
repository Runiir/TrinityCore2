#ifndef TRINITY_BOT_NEFARIAN_LAYOUT_H
#define TRINITY_BOT_NEFARIAN_LAYOUT_H

// Arena layout for Nefarian's End, derived from the duty plan: where each
// dragon should end up and where the tanks lead them. Guides (Wowhead, Icy
// Veins) put the dragons at opposite ends, angled along the walls, with the
// raid on their wings. Natively a dragon stops at its melee reach (20.8 /
// 22.8 yd) from its tank, so a radial drag cannot separate them by the
// 50-yard Children of Deathwing range; the tank instead leads its dragon
// around a run circle and holds tangentially ahead of it.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianGeometry.h"

namespace BotEncounter::Nefarian
{
// On the outer ring (r >= 32), clear of the rise and inside the pillar blocks.
constexpr float TankRunRadius = 34.0f;
constexpr float DragonGoalMinRadius = 22.0f;
constexpr float DragonGoalAngleToleranceDeg = 12.0f;
constexpr float DragonEndOffsetDeg = 30.0f;

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

// Angular lead on the run circle that keeps a chord just inside or just
// outside a dragon's melee reach.
inline float LeadAngle(float chord, float radius = TankRunRadius)
{
    float const half = std::min(0.99f, std::max(0.0f, chord * 0.5f / radius));
    return 2.0f * std::asin(half);
}

enum class TankStep : uint8
{
    LeadOut,   // dragon near the centre: pull it out toward its end
    Orbit,     // lead it around the run circle
    Hold,      // at its end: stand tangentially ahead (dragon only turns)
    Discharge  // Onyxia wind-up: stand outward so her tail faces the raid
};

inline std::string_view TankStepName(TankStep step)
{
    switch (step)
    {
        case TankStep::LeadOut: return "lead_out";
        case TankStep::Orbit: return "orbit";
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

inline LocalPoint RunPoint(float angle)
{
    return Polar(angle, TankRunRadius);
}

// Pick the orbit/hold side whose point is clear of the pillars; prefer the
// requested sign.
inline float ClearSide(float dragonAngle, float lead, float preferred)
{
    for (float sign : { preferred, -preferred })
        if (!NearPillar(RunPoint(dragonAngle + sign * lead)))
            return sign;
    return preferred;
}

inline TankSpot PlanTankSpot(LocalPoint dragon, float goalAngle, float reach,
    bool dischargeTurn)
{
    TankSpot spot;
    float const radius = Length(dragon);
    float const lead = LeadAngle(reach - 2.0f);
    if (radius < 8.0f)
    {
        float const sign = ClearSide(goalAngle, lead, 1.0f);
        spot.Step = TankStep::LeadOut;
        spot.Point = RunPoint(goalAngle + sign * lead);
        return spot;
    }

    float const dragonAngle = AngleOf(dragon);
    float const error = NormalizeSigned(goalAngle - dragonAngle);
    bool const atEnd = std::fabs(error)
            <= DegToRad(DragonGoalAngleToleranceDeg)
        && radius >= DragonGoalMinRadius;
    if (!atEnd)
    {
        float const sign = error >= 0.0f ? 1.0f : -1.0f;
        spot.Step = TankStep::Orbit;
        spot.Point = RunPoint(dragonAngle + sign * (lead + DegToRad(4.0f)));
        return spot;
    }

    if (dischargeTurn)
    {
        LocalPoint const outward = Offset(dragon, dragonAngle, 5.0f);
        if (Length(outward) <= MaxFloorRadius && !NearPillar(outward))
        {
            spot.Step = TankStep::Discharge;
            spot.Point = outward;
            return spot;
        }
    }

    float const holdLead = LeadAngle(reach - 7.0f);
    float const sign = ClearSide(dragonAngle, holdLead, 1.0f);
    spot.Step = TankStep::Hold;
    spot.Point = RunPoint(dragonAngle + sign * holdLead);
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
