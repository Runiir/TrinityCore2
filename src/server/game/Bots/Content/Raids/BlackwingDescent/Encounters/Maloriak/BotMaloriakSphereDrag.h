#ifndef TRINITY_BOT_MALORIAK_SPHERE_DRAG_H
#define TRINITY_BOT_MALORIAK_SPHERE_DRAG_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakDuties.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakGeometry.h"

#include <algorithm>
#include <cmath>
#include <optional>
#include <vector>

// Phase two: the main tank walks Maloriak off an Absolute Zero sphere that
// blocks the melee ring. A sphere (41961) wanders within 10 yards of where
// it spawned and despawns only after a player triggers it
// (spell_maloriak_absolute_zero). In r01 kill 6bf522 the rogue stepped away
// from the boss at the second phase-two sphere (about 146 s) and, like the
// Retribution Paladin, landed nothing on him for the last 38 and 25 s, while
// no Absolute Zero ever exploded; a sphere blocking the melee ring
// (melee_ring_hazard_hold) fits, though the log records no sphere position.
// The guides' answer is ordinary tank positioning: the tank steps away and
// the boss follows it.
namespace BotEncounter::Maloriak
{
// How far the tank walks from the boss, and how far short of the tank the
// boss stops (r01 Blood DK swings landed at a median 6.4-6.8 yards).
constexpr float SphereDragYards = 12.0f;
constexpr float SphereDragBossLag = 6.5f;
// Spheres farther than this from the boss cannot touch the outer ring's
// clearance.
constexpr float SphereDragInfluenceYards =
    AbsoluteZeroDanger + FormationHazardMargin + MeleeOuterRingRadius;

inline bool HasLivingMeleeDamageDealer(Blackboard const& board)
{
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && player.Role == "dps" && IsMeleeSpec(player.ClassSpec))
            return true;
    return false;
}

// The tank's destination, or nullopt when no drag is needed or none helps.
// Direction: away from the spheres near the boss (weighted by nearness),
// rotated up to 90 degrees; the destination must be clear of every hazard
// clearance and inside the room, its midpoint outside every sphere's danger
// radius, the predicted boss position outside the cauldron's radius, and
// the melee ring around the predicted boss must have a clear point.
inline std::optional<Vector3> SphereDragPoint(Observation const& observation,
    BossFrame const& frame, Vector3 const& tank)
{
    if (observation.CurrentPhase != Phase::PhaseTwo
        || observation.AbsoluteZeros.empty() || observation.MagmaJetsCasting)
        return std::nullopt;
    std::vector<FormationHazard> const hazards = CollectFormationHazards(observation);
    if (!MeleeRingBlocked(frame, SlotArc::Back, hazards))
        return std::nullopt;

    Vector3 const boss = frame.Boss;
    float ax = 0.0f;
    float ay = 0.0f;
    bool sphereNear = false;
    for (ActorSnapshot const* sphere : observation.AbsoluteZeros)
    {
        float const dx = boss.X - sphere->Position.X;
        float const dy = boss.Y - sphere->Position.Y;
        float const distance = std::sqrt(dx * dx + dy * dy);
        if (distance >= SphereDragInfluenceYards)
            continue;
        sphereNear = true;
        float const weight = 1.0f / std::max(distance, 0.5f);
        if (distance > 0.01f)
        {
            ax += dx / distance * weight;
            ay += dy / distance * weight;
        }
    }
    // Jet fire alone never moves him: the fire lines lie along his front.
    if (!sphereNear)
        return std::nullopt;
    if (ax * ax + ay * ay < 1e-6f)
    {
        // A sphere on the boss itself: keep the tank's side.
        ax = tank.X - boss.X;
        ay = tank.Y - boss.Y;
        if (ax * ax + ay * ay < 1e-6f)
        {
            ax = frame.Ux;
            ay = frame.Uy;
        }
    }
    float const base = std::atan2(ay, ax);
    static constexpr float Rotations[] = { 0.0f, 30.0f, -30.0f, 60.0f, -60.0f,
        90.0f, -90.0f };
    for (float degrees : Rotations)
    {
        float const angle = base + degrees * Pi / 180.0f;
        float const ux = std::cos(angle);
        float const uy = std::sin(angle);
        Vector3 const point{ boss.X + ux * SphereDragYards,
            boss.Y + uy * SphereDragYards, tank.Z };
        if (!InRoom(point) || !ClearOfHazards(point, hazards))
            continue;
        Vector3 const midpoint{ (tank.X + point.X) / 2.0f,
            (tank.Y + point.Y) / 2.0f, tank.Z };
        bool pathClear = true;
        for (ActorSnapshot const* sphere : observation.AbsoluteZeros)
            if (Distance2d(midpoint, sphere->Position) < AbsoluteZeroDanger)
                pathClear = false;
        if (!pathClear)
            continue;
        BossFrame predicted;
        predicted.Boss = { boss.X + ux * (SphereDragYards - SphereDragBossLag),
            boss.Y + uy * (SphereDragYards - SphereDragBossLag), boss.Z };
        predicted.Ux = ux;
        predicted.Uy = uy;
        if (!CauldronConstrains(predicted.Boss)
            || MeleeRingBlocked(predicted, SlotArc::Back, hazards))
            continue;
        return point;
    }
    return std::nullopt;
}
}

#endif
