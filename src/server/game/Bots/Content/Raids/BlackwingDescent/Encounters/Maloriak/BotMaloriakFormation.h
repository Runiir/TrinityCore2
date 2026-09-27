#ifndef TRINITY_BOT_MALORIAK_FORMATION_H
#define TRINITY_BOT_MALORIAK_FORMATION_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakGeometry.h"

#include <cmath>
#include <optional>
#include <string_view>
#include <vector>

// Formation slots that stay out of the ground hazards. A slot inside a
// hazard's formation clearance is shifted along its arc around the boss
// (the melee ring or the ranged fan) to the nearest clear point; when none
// exists the bot gets no formation move. Clearance exceeds the hazard exit
// trigger by 2 yards, so a bot that just evaded is never sent back into the
// radius it evaded (no evade/return oscillation).
namespace BotEncounter::Maloriak
{
// Hazard radii from client rows: Absolute Zero trigger 3 yd and explosion
// 5 yd (the sphere also wanders), Magma Jets fire 3 yd, Shatter 5 yd.
constexpr float AbsoluteZeroDanger = 7.0f;
constexpr float MagmaFireDanger = 4.5f;
constexpr float ShatterDanger = 5.5f;
constexpr float ShatterExit = 8.0f;
constexpr float FormationHazardMargin = 2.0f;
// Blue and phase-two spread: 5 yards between ranged slots (Flash Freeze and
// Biting Chill radii).
constexpr float SpreadYards = 5.0f;
// Outer melee ring. Round 1 (r01, two kills): the rogue, the Retribution
// Paladin and the Blood DK landed melee swings on Maloriak from up to 6.5-6.9
// yards (centre to centre, not moving). A ring point at 5 yards is in reach
// with margin, so a sphere that blocks the 3.5-yard ring on one side no
// longer holds melee while the far side of the outer ring is clear.
constexpr float MeleeOuterRingRadius = 5.0f;

struct FormationHazard
{
    Vector3 Center;
    float Clearance = 0.0f;
};

inline std::vector<FormationHazard> CollectFormationHazards(
    Observation const& observation)
{
    std::vector<FormationHazard> hazards;
    for (ActorSnapshot const* sphere : observation.AbsoluteZeros)
        hazards.push_back({ sphere->Position, AbsoluteZeroDanger + FormationHazardMargin });
    for (ActorSnapshot const* fire : observation.MagmaJetFires)
        hazards.push_back({ fire->Position, MagmaFireDanger + FormationHazardMargin });
    for (ActorSnapshot const* block : observation.FlashFreezeBlocks)
        hazards.push_back({ block->Position, ShatterExit + 1.0f });
    return hazards;
}

inline bool ClearOfHazards(Vector3 const& point,
    std::vector<FormationHazard> const& hazards)
{
    for (FormationHazard const& hazard : hazards)
        if (Distance2d(point, hazard.Center) < hazard.Clearance)
            return false;
    return true;
}

// Polar coordinates of a point in the boss frame: radius and angle from the
// front (positive toward V).
struct FramePolarCoords
{
    float Radius = 0.0f;
    float Angle = 0.0f;
};

inline FramePolarCoords ToFramePolar(BossFrame const& frame, Vector3 const& point)
{
    float const dx = point.X - frame.Boss.X;
    float const dy = point.Y - frame.Boss.Y;
    float const forward = dx * frame.Ux + dy * frame.Uy;
    float const lateral = dx * frame.Vx() + dy * frame.Vy();
    return { std::sqrt(forward * forward + lateral * lateral),
        std::atan2(lateral, forward) };
}

inline float WrapAngle(float angle)
{
    while (angle > Pi)
        angle -= 2.0f * Pi;
    while (angle < -Pi)
        angle += 2.0f * Pi;
    return angle;
}

enum class SlotArc : uint8
{
    // Red: inside the Scorching Blast cone (30 of its 35 half-degrees).
    FrontCone,
    // Blue, Dark and phase two: anywhere outside a 70-degree half cone in
    // front (Magma Jets line and Engulfing Darkness cone).
    Back
};

inline bool ArcAdmits(SlotArc arc, float angleFromFront)
{
    float const degrees = std::fabs(WrapAngle(angleFromFront)) * 180.0f / Pi;
    return arc == SlotArc::FrontCone ? degrees <= 30.0f : degrees >= 70.0f;
}

// A formation point is usable when it is outside every hazard clearance and
// the cauldron does not stand between it and the boss (checked only while
// the boss himself is outside the cauldron's radius).
inline bool FormationPointClear(BossFrame const& frame, Vector3 const& point,
    std::vector<FormationHazard> const& hazards)
{
    return ClearOfHazards(point, hazards)
        && (!CauldronConstrains(frame.Boss) || CauldronLineClear(point, frame.Boss));
}

// The clear point nearest to the slot among its arc (alternating sides in
// stepDeg steps up to maxShiftDeg) and, for ranged slots, the same angles
// 5 or 10 yards farther out or 5 yards closer in (never closer than 8 yards
// or farther than 30). Every candidate also keeps spreadYards from the
// other players' slots when spreadYards > 0. nullopt when none clears.
inline std::optional<Vector3> SafeFormationSlot(BossFrame const& frame,
    Vector3 const& slot, SlotArc arc, float stepDeg, float maxShiftDeg,
    std::vector<FormationHazard> const& hazards,
    std::vector<Vector3> const& otherSlots, float spreadYards,
    bool radialShifts)
{
    auto spreadOk = [&](Vector3 const& point)
    {
        if (spreadYards > 0.0f)
            for (Vector3 const& other : otherSlots)
                if (Distance2d(point, other) < spreadYards)
                    return false;
        return true;
    };
    // The slot itself also keeps the spread: two slots clamped onto the
    // same point at a room wall must not both be accepted as they are.
    if (FormationPointClear(frame, slot, hazards) && spreadOk(slot))
        return slot;
    FramePolarCoords const polar = ToFramePolar(frame, slot);
    std::vector<float> radii{ polar.Radius };
    if (radialShifts)
        for (float offset : { 5.0f, 10.0f, -5.0f })
        {
            float const radius = polar.Radius + offset;
            if (radius >= 8.0f && radius <= 30.0f)
                radii.push_back(radius);
        }
    std::optional<Vector3> best;
    float bestDisplacement = 0.0f;
    for (float radius : radii)
        for (float shift = 0.0f; shift <= maxShiftDeg + 0.01f; shift += stepDeg)
            for (float sign : { 1.0f, -1.0f })
            {
                if (shift == 0.0f && sign < 0.0f)
                    continue;
                float const angle = polar.Angle + sign * shift * Pi / 180.0f;
                if (!ArcAdmits(arc, angle))
                    continue;
                Vector3 const point = FramePolar(frame, radius, angle);
                if (!FormationPointClear(frame, point, hazards) || !spreadOk(point))
                    continue;
                float const displacement = Distance2d(point, slot);
                if (!best || displacement < bestDisplacement)
                {
                    best = point;
                    bestDisplacement = displacement;
                }
            }
    return best;
}

// The first clear point of the melee ring (3.5 yards, then the 5-yard outer
// ring) in this arc, 15 degrees apart, nearest the preferred angle first.
// Hazards only by default (MeleeRingBlocked: the cauldron never holds melee
// offense); a formation destination passes inSight, so the point must also
// see the boss past the cauldron (FormationPointClear).
inline std::optional<Vector3> ClearMeleeRingPoint(BossFrame const& frame,
    SlotArc arc, std::vector<FormationHazard> const& hazards,
    float preferredAngle = Pi, bool inSight = false)
{
    for (float radius : { MeleeRingRadius, MeleeOuterRingRadius })
        for (int shift = 0; shift <= 12; ++shift)
            for (float sign : { 1.0f, -1.0f })
            {
                if (shift == 0 && sign < 0.0f)
                    continue;
                float const angle = WrapAngle(preferredAngle
                    + sign * float(shift) * Pi / 12.0f);
                if (!ArcAdmits(arc, angle))
                    continue;
                Vector3 const point = FramePolar(frame, radius, angle);
                if (inSight ? FormationPointClear(frame, point, hazards)
                        : ClearOfHazards(point, hazards))
                    return point;
            }
    return std::nullopt;
}

// True when every point of the melee rings the bot can fight from in this
// arc is inside a hazard clearance: melee then holds instead of chasing
// back into the hazard.
inline bool MeleeRingBlocked(BossFrame const& frame, SlotArc arc,
    std::vector<FormationHazard> const& hazards)
{
    // Hazards only: the cauldron shifts melee slots but never holds offense
    // (a melee player next to the boss keeps attacking when no ring point
    // has line of sight past the cauldron).
    if (hazards.empty())
        return false;
    return !ClearMeleeRingPoint(frame, arc, hazards);
}

// Ranged hysteresis. Slots follow the boss-tank frame, so every tank step
// or boss turn moved them; in the r03 attempt the healers re-pathed on
// almost every decision (49 phase-two spread moves in 20 s, 36 Blue moves)
// instead of casting. A ranged player that already stands within
// RangedHoldYards of its slot, 8 to 30 yards from the boss, inside the arc,
// clear of every hazard, with the cauldron not between it and the boss and
// (spreadYards > 0) apart from every other player keeps its place.
constexpr float RangedHoldYards = 9.0f;

inline bool RangedPlaceAcceptable(BossFrame const& frame, Vector3 const& place,
    Vector3 const& slot, SlotArc arc, std::vector<FormationHazard> const& hazards,
    std::vector<Vector3> const& otherPlayers, float spreadYards)
{
    if (Distance2d(place, slot) > RangedHoldYards)
        return false;
    FramePolarCoords const polar = ToFramePolar(frame, place);
    if (polar.Radius < 8.0f || polar.Radius > 30.0f || !ArcAdmits(arc, polar.Angle))
        return false;
    if (!FormationPointClear(frame, place, hazards))
        return false;
    if (spreadYards > 0.0f)
        for (Vector3 const& other : otherPlayers)
            if (Distance2d(place, other) < spreadYards)
                return false;
    return true;
}
}

#endif
