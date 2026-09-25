#ifndef TRINITY_BOT_OMNOTRON_MOVEMENT_H
#define TRINITY_BOT_OMNOTRON_MOVEMENT_H

#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronDutyPlan.h"
#include <cmath>
#include <optional>
#include <string>
#include <string_view>

// Movement intents for Omnotron mechanics. Each producer returns a logical
// destination only; native pathing moves the bot. Producers are evaluated in
// the strategy's fixed order and the first proposal wins.
namespace BotEncounter::Omnotron
{
// Tactic margins (yards) added to the client radii in BotOmnotronFacts.h.
inline constexpr float HazardMargin = 1.5f;
inline constexpr float ConductorClearance = 3.0f;
inline constexpr float FlamethrowerMarginDeg = 8.0f;
inline constexpr float BombKiteDistance = 16.0f;
inline constexpr float GeneratorExitDistance = 15.0f;
inline constexpr float ShieldSeparationDistance = 12.0f;
inline constexpr float GeneratorApproachRange = 30.0f;
inline constexpr uint64 MovementIntentLifetimeMs = 750;

namespace Geometry
{
inline constexpr float Pi = 3.14159265358979323846f;

inline Vector3 Direction(Vector3 const& from, Vector3 const& to, float fallbackFacing)
{
    float dx = to.X - from.X;
    float dy = to.Y - from.Y;
    float const length = std::sqrt(dx * dx + dy * dy);
    if (length < 0.01f)
        return { std::cos(fallbackFacing), std::sin(fallbackFacing), 0.0f };
    return { dx / length, dy / length, 0.0f };
}

inline Vector3 Offset(Vector3 const& origin, Vector3 const& direction, float distance)
{
    return { origin.X + direction.X * distance, origin.Y + direction.Y * distance,
        origin.Z };
}

inline float AngleDiffDeg(float left, float right)
{
    float diff = std::fmod(std::fabs(left - right), 2.0f * Pi);
    if (diff > Pi)
        diff = 2.0f * Pi - diff;
    return diff * 180.0f / Pi;
}

inline float Bearing(Vector3 const& from, Vector3 const& to)
{
    return std::atan2(to.Y - from.Y, to.X - from.X);
}

// Keep destinations on the measured floor when the fight is in the room;
// a snapshot elsewhere (fixtures, a stray pull) is left unclamped.
inline Vector3 ClampToArena(Vector3 const& bot, Vector3 point)
{
    Vector3 const center{ ArenaCenterX, ArenaCenterY, point.Z };
    if (PlanarDistance(bot, center) > ArenaRadius + 15.0f)
        return point;
    float const distance = PlanarDistance(point, center);
    if (distance <= ArenaRadius)
        return point;
    point.X = center.X + (point.X - center.X) * ArenaRadius / distance;
    point.Y = center.Y + (point.Y - center.Y) * ArenaRadius / distance;
    return point;
}
}

inline BotNativeAction::Candidate MoveCandidate(Blackboard const& board,
    ActorSnapshot const& bot, Vector3 const& destination, std::string_view mechanic,
    ObjectGuid subject, BotActionArbitration::Priority priority, float utility)
{
    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = board.CurrentScope.Key();
    candidate.Id.Strategy = "adaptive_omnotron";
    candidate.Id.Mechanic = std::string(mechanic);
    candidate.Id.Actor = subject;
    candidate.Id.EventGeneration = board.Revision;
    candidate.ActionPriority = priority;
    candidate.Utility = utility;
    candidate.ExpiresAtMs = board.ObservedAtMs + MovementIntentLifetimeMs;
    candidate.Action = BotNativeAction::Move{ destination.X, destination.Y,
        bot.Position.Z };
    return candidate;
}

// Signed hazard depth at a point: yards inside the worst avoidable area
// (negative outside all of them; -1000 without any hazard).
inline float HazardDepth(EncounterFacts const& facts, Vector3 const& point,
    ObjectGuid fixatedBy = ObjectGuid{})
{
    float depth = -1000.0f;
    auto consider = [&depth, &point](ActorSnapshot const* source, float radius)
    {
        depth = std::max(depth, radius + HazardMargin
            - PlanarDistance(point, source->Position));
    };
    for (ActorSnapshot const* cloud : facts.ChemicalClouds)
        consider(cloud, ChemicalCloudPlayerRadius);
    for (ActorSnapshot const* puddle : facts.PoisonPuddles)
        consider(puddle, PoisonPuddleRadius);
    for (ActorSnapshot const* bomb : facts.PoisonBombs)
        if (bomb->Guid != fixatedBy)
            consider(bomb, PoisonBombBlastRadius);
    return depth;
}

template <typename Visitor>
inline void ForEachOtherPlayer(Blackboard const& board, ObjectGuid botGuid,
    Visitor&& visit)
{
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && player.Guid != botGuid)
            visit(player);
    for (ActorSnapshot const& player : board.ExternalPlayers)
        if (player.Alive && player.Guid != botGuid)
            visit(player);
}

inline float NearestOtherPlayer(Blackboard const& board, ObjectGuid botGuid,
    Vector3 const& point)
{
    float nearest = 1000.0f;
    ForEachOtherPlayer(board, botGuid, [&nearest, &point](ActorSnapshot const& player)
    {
        nearest = std::min(nearest, PlanarDistance(point, player.Position));
    });
    return nearest;
}

// Lightning Conductor: the carrier damages allies within 8 yd every 2 s.
inline std::optional<BotNativeAction::Candidate> ProposeConductorIsolation(
    Blackboard const& board, EncounterFacts const& facts, ActorSnapshot const& bot)
{
    if (!CarriesLightningConductor(bot)
        || NearestOtherPlayer(board, bot.Guid, bot.Position)
            >= LightningConductorRadius + ConductorClearance)
        return std::nullopt;
    Vector3 best = bot.Position;
    float bestScore = -1000.0f;
    for (float radius : { 8.0f, 12.0f, 16.0f })
        for (int step = 0; step < 16; ++step)
        {
            float const angle = float(step) * Geometry::Pi / 8.0f;
            Vector3 const point = Geometry::ClampToArena(bot.Position,
                Geometry::Offset(bot.Position,
                    { std::cos(angle), std::sin(angle), 0.0f }, radius));
            float const score = NearestOtherPlayer(board, bot.Guid, point)
                - 10.0f * std::max(0.0f, HazardDepth(facts, point))
                - 0.05f * radius;
            if (score > bestScore)
            {
                bestScore = score;
                best = point;
            }
        }
    return MoveCandidate(board, bot, best, "lightning_conductor_isolate",
        bot.Guid, BotActionArbitration::Priority::Survival, 320.0f);
}

// A fixated player keeps its Poison Bomb away and runs clear of others, so
// the blast (on contact) reaches nobody else.
inline std::optional<BotNativeAction::Candidate> ProposeBombKite(
    Blackboard const& board, EncounterFacts const& facts, ActorSnapshot const& bot)
{
    ActorSnapshot const* chaser = nullptr;
    for (ActorSnapshot const* bomb : facts.PoisonBombs)
        if (BombFixateTarget(board, *bomb) == bot.Guid
            && (!chaser || PlanarDistance(bomb->Position, bot.Position)
                < PlanarDistance(chaser->Position, bot.Position)))
            chaser = bomb;
    if (!chaser || PlanarDistance(chaser->Position, bot.Position) >= BombKiteDistance)
        return std::nullopt;
    Vector3 const away = Geometry::Direction(chaser->Position, bot.Position, bot.Facing);
    float const baseAngle = std::atan2(away.Y, away.X);
    Vector3 best = bot.Position;
    float bestScore = -1000.0f;
    for (float offsetDeg : { 0.0f, 30.0f, -30.0f, 60.0f, -60.0f, 90.0f, -90.0f })
    {
        float const angle = baseAngle + offsetDeg * Geometry::Pi / 180.0f;
        Vector3 const point = Geometry::ClampToArena(bot.Position,
            Geometry::Offset(bot.Position, { std::cos(angle), std::sin(angle), 0.0f },
                10.0f));
        float const score = PlanarDistance(point, chaser->Position)
            + 0.5f * std::min(NearestOtherPlayer(board, bot.Guid, point), 12.0f)
            - 10.0f * std::max(0.0f, HazardDepth(facts, point, chaser->Guid));
        if (score > bestScore)
        {
            bestScore = score;
            best = point;
        }
    }
    return MoveCandidate(board, bot, best, "poison_bomb_kite", chaser->Guid,
        BotActionArbitration::Priority::Survival, 330.0f);
}

// Flamethrower (79504) is a 25 deg cone from Magmatron toward the Acquiring
// Target player. Returns the cone axis origin and bearing when one is armed.
struct FlamethrowerCone
{
    Vector3 Origin;
    float Bearing = 0.0f;
    ObjectGuid Target;
    ObjectGuid Source;
};

inline std::optional<FlamethrowerCone> ObserveFlamethrower(Blackboard const& board,
    EncounterFacts const& facts)
{
    ConstructFact const* magmatron = facts.FindKind(ConstructKind::Magmatron);
    if (!magmatron || !magmatron->Active)
        return std::nullopt;
    ActorSnapshot const& source = *magmatron->Actor;
    FlamethrowerCone cone;
    cone.Origin = source.Position;
    cone.Source = source.Guid;
    if (source.Cast && InSet(FlamethrowerChannel, source.Cast->SpellId))
    {
        cone.Target = source.Cast->TargetGuid;
        ActorSnapshot const* target = cone.Target.IsEmpty() ? nullptr
            : board.FindActor(cone.Target);
        cone.Bearing = target ? Geometry::Bearing(source.Position, target->Position)
            : source.Facing;
        return cone;
    }
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && IsAcquiredTarget(player))
        {
            cone.Target = player.Guid;
            cone.Bearing = Geometry::Bearing(source.Position, player.Position);
            return cone;
        }
    return std::nullopt;
}

inline bool InsideCone(FlamethrowerCone const& cone, Vector3 const& point,
    float marginDeg)
{
    if (PlanarDistance(cone.Origin, point) < 1.0f)
        return true;
    return Geometry::AngleDiffDeg(Geometry::Bearing(cone.Origin, point), cone.Bearing)
        < FlamethrowerHalfAngleDeg + marginDeg;
}

// The Acquiring Target player turns the cone away from everyone else.
inline std::optional<BotNativeAction::Candidate> ProposeAcquiredTargetLine(
    Blackboard const& board, EncounterFacts const& facts, ActorSnapshot const& bot)
{
    std::optional<FlamethrowerCone> const cone = ObserveFlamethrower(board, facts);
    if (!cone || cone->Target != bot.Guid)
        return std::nullopt;
    bool exposed = false;
    ForEachOtherPlayer(board, bot.Guid, [&](ActorSnapshot const& player)
    {
        exposed = exposed || InsideCone(*cone, player.Position, FlamethrowerMarginDeg);
    });
    if (!exposed)
        return std::nullopt;
    float const radius = std::clamp(PlanarDistance(cone->Origin, bot.Position), 10.0f, 18.0f);
    Vector3 best = bot.Position;
    float bestScore = -1000.0f;
    for (int step = 0; step < 24; ++step)
    {
        float const angle = float(step) * Geometry::Pi / 12.0f;
        Vector3 const point = Geometry::ClampToArena(bot.Position,
            Geometry::Offset(cone->Origin, { std::cos(angle), std::sin(angle), 0.0f },
                radius));
        float const bearing = Geometry::Bearing(cone->Origin, point);
        float separation = 180.0f;
        ForEachOtherPlayer(board, bot.Guid, [&](ActorSnapshot const& player)
        {
            if (PlanarDistance(cone->Origin, player.Position) >= 1.0f)
                separation = std::min(separation, Geometry::AngleDiffDeg(bearing,
                    Geometry::Bearing(cone->Origin, player.Position)));
        });
        float const score = std::min(separation, 60.0f)
            - 10.0f * std::max(0.0f, HazardDepth(facts, point))
            - 0.3f * PlanarDistance(bot.Position, point);
        if (score > bestScore)
        {
            bestScore = score;
            best = point;
        }
    }
    return MoveCandidate(board, bot, best, "acquiring_target_line_clear",
        cone->Source, BotActionArbitration::Priority::Survival, 315.0f);
}

// Everyone else steps sideways out of the armed cone.
inline std::optional<BotNativeAction::Candidate> ProposeFlamethrowerDodge(
    Blackboard const& board, EncounterFacts const& facts, ActorSnapshot const& bot)
{
    std::optional<FlamethrowerCone> const cone = ObserveFlamethrower(board, facts);
    if (!cone || cone->Target == bot.Guid
        || !InsideCone(*cone, bot.Position, FlamethrowerMarginDeg))
        return std::nullopt;
    float const distance = PlanarDistance(cone->Origin, bot.Position);
    float const relative = Geometry::Bearing(cone->Origin, bot.Position) - cone->Bearing;
    float const side = std::sin(relative) >= 0.0f ? 1.0f : -1.0f;
    Vector3 const perpendicular{ -std::sin(cone->Bearing) * side,
        std::cos(cone->Bearing) * side, 0.0f };
    float const needed = std::tan((FlamethrowerHalfAngleDeg + FlamethrowerMarginDeg + 4.0f)
        * Geometry::Pi / 180.0f) * std::max(distance, 4.0f) + 2.0f;
    Vector3 const point = Geometry::ClampToArena(bot.Position,
        Geometry::Offset(bot.Position, perpendicular, std::max(needed, 4.0f)));
    return MoveCandidate(board, bot, point, "flamethrower_line_dodge", cone->Source,
        BotActionArbitration::Priority::Survival, 305.0f);
}

// Chemical Cloud (12 yd, +50% damage taken), Poison Puddle and another
// player's Poison Bomb blast radius. Sample reachable points and take the one
// outside every hazard (least depth), then the shortest move: pushing straight
// away from one hazard can end in the arena edge or in the next hazard.
inline std::optional<BotNativeAction::Candidate> ProposeHazardExit(
    Blackboard const& board, EncounterFacts const& facts, ActorSnapshot const& bot)
{
    ObjectGuid chaser;
    for (ActorSnapshot const* bomb : facts.PoisonBombs)
        if (BombFixateTarget(board, *bomb) == bot.Guid)
            chaser = bomb->Guid;
    if (HazardDepth(facts, bot.Position, chaser) <= 0.0f)
        return std::nullopt;
    ActorSnapshot const* worst = nullptr;
    float worstDepth = 0.0f;
    auto consider = [&](ActorSnapshot const* source, float radius)
    {
        float const depth = radius + HazardMargin
            - PlanarDistance(bot.Position, source->Position);
        if (depth > worstDepth)
        {
            worst = source;
            worstDepth = depth;
        }
    };
    for (ActorSnapshot const* cloud : facts.ChemicalClouds)
        consider(cloud, ChemicalCloudPlayerRadius);
    for (ActorSnapshot const* puddle : facts.PoisonPuddles)
        consider(puddle, PoisonPuddleRadius);
    for (ActorSnapshot const* bomb : facts.PoisonBombs)
        if (bomb->Guid != chaser)
            consider(bomb, PoisonBombBlastRadius);

    Vector3 best = bot.Position;
    float bestDepth = 1000.0f;
    float bestTravel = 0.0f;
    for (float radius : { 4.0f, 7.0f, 10.0f, 14.0f, 18.0f, 24.0f })
        for (int step = 0; step < 16; ++step)
        {
            float const angle = float(step) * Geometry::Pi / 8.0f;
            Vector3 const point = Geometry::ClampToArena(bot.Position,
                Geometry::Offset(bot.Position,
                    { std::cos(angle), std::sin(angle), 0.0f }, radius));
            // A point 1 yd beyond every edge counts as clear.
            float const depth = std::max(-1.0f, HazardDepth(facts, point, chaser));
            float const travel = PlanarDistance(bot.Position, point);
            if (depth < bestDepth - 0.01f
                || (std::fabs(depth - bestDepth) <= 0.01f && travel < bestTravel))
            {
                best = point;
                bestDepth = depth;
                bestTravel = travel;
            }
        }
    return MoveCandidate(board, bot, best, "omnotron_hazard_exit",
        worst ? worst->Guid : ObjectGuid{}, BotActionArbitration::Priority::Survival,
        300.0f);
}

// Everyone else keeps out of a Lightning Conductor carrier's 8 yd.
inline std::optional<BotNativeAction::Candidate> ProposeConductorClearance(
    Blackboard const& board, ActorSnapshot const& bot)
{
    if (CarriesLightningConductor(bot))
        return std::nullopt;
    ActorSnapshot const* carrier = nullptr;
    ForEachOtherPlayer(board, bot.Guid, [&](ActorSnapshot const& player)
    {
        if (CarriesLightningConductor(player)
            && PlanarDistance(player.Position, bot.Position)
                < LightningConductorRadius + 2.0f)
            carrier = &player;
    });
    if (!carrier)
        return std::nullopt;
    Vector3 const point = Geometry::ClampToArena(bot.Position, Geometry::Offset(
        carrier->Position, Geometry::Direction(carrier->Position, bot.Position, bot.Facing),
        LightningConductorRadius + ConductorClearance + 1.0f));
    return MoveCandidate(board, bot, point, "lightning_conductor_clear", carrier->Guid,
        BotActionArbitration::Priority::Survival, 290.0f);
}

// Tanks: pull the owned construct out of a Power Generator, drag a shielded
// construct away from the other one, or wait next to the recharging one.
inline std::optional<BotNativeAction::Candidate> ProposeTankPosition(
    Blackboard const& board, EncounterFacts const& facts, DutyPlan const& duty,
    ActorSnapshot const& bot)
{
    TankDuty const* tank = duty.TankDutyFor(bot.Guid);
    if (!tank)
        return std::nullopt;
    ConstructFact const* own = facts.Find(tank->Construct);
    if (own)
    {
        for (ActorSnapshot const* generator : facts.PowerGenerators)
            if (PlanarDistance(own->Actor->Position, generator->Position)
                < PowerGeneratorRadius + ConstructBoundingRadius + 1.0f)
                return MoveCandidate(board, bot, Geometry::ClampToArena(bot.Position,
                    Geometry::Offset(generator->Position, Geometry::Direction(
                        generator->Position, bot.Position, bot.Facing),
                        GeneratorExitDistance)), "tank_generator_exit", own->Actor->Guid,
                    BotActionArbitration::Priority::Mechanic, 250.0f);
        if (own->Shielded())
            for (ConstructFact const& other : facts.Constructs)
                if (&other != own && other.Fighting()
                    && PlanarDistance(other.Actor->Position, own->Actor->Position)
                        < ShieldSeparationDistance)
                    return MoveCandidate(board, bot, Geometry::ClampToArena(bot.Position,
                        Geometry::Offset(bot.Position, Geometry::Direction(
                            other.Actor->Position, own->Actor->Position, bot.Facing),
                            ShieldSeparationDistance)), "tank_shield_separation",
                        own->Actor->Guid, BotActionArbitration::Priority::Mechanic, 240.0f);
        return std::nullopt;
    }
    ConstructFact const* next = facts.Find(tank->Standby);
    if (!next || PlanarDistance(bot.Position, next->Actor->Position) <= 7.0f)
        return std::nullopt;
    return MoveCandidate(board, bot, Geometry::Offset(next->Actor->Position,
            Geometry::Direction(next->Actor->Position, bot.Position, bot.Facing), 5.0f),
        "tank_standby_next_construct", next->Actor->Guid,
        BotActionArbitration::Priority::Mechanic, 200.0f);
}

// Ranged damage dealers and healers stand in a Power Generator (+50% damage
// done, mana) when it is clear of hazards and in reach of the fight.
inline std::optional<BotNativeAction::Candidate> ProposeGeneratorStack(
    Blackboard const& board, EncounterFacts const& facts, DutyPlan const& duty,
    ActorSnapshot const& bot, std::string_view role)
{
    if (!StandsAtRange(bot.ClassSpec, role) || duty.HasMovementDuty(bot.Guid))
        return std::nullopt;
    ActorSnapshot const* generator = nullptr;
    for (ActorSnapshot const* candidate : facts.PowerGenerators)
        if (PlanarDistance(candidate->Position, bot.Position) <= GeneratorApproachRange
            && (!generator || PlanarDistance(candidate->Position, bot.Position)
                < PlanarDistance(generator->Position, bot.Position)))
            generator = candidate;
    if (!generator
        || PlanarDistance(generator->Position, bot.Position) <= PowerGeneratorRadius - 1.5f
        || HasAura(*generator, OverchargedPowerGeneratorAura)
        || HazardDepth(facts, generator->Position) > -3.0f)
        return std::nullopt;
    bool conductorNearby = false;
    ForEachOtherPlayer(board, bot.Guid, [&](ActorSnapshot const& player)
    {
        conductorNearby = conductorNearby || (CarriesLightningConductor(player)
            && PlanarDistance(player.Position, generator->Position)
                < LightningConductorRadius + ConductorClearance);
    });
    if (conductorNearby)
        return std::nullopt;
    if (role != "healer")
    {
        ConstructFact const* focus = facts.Find(duty.DamageFocus);
        if (!focus || PlanarDistance(focus->Actor->Position, generator->Position) > 35.0f)
            return std::nullopt;
    }
    float const angle = float(bot.Guid.GetCounter() % 8) * Geometry::Pi / 4.0f;
    Vector3 const point = Geometry::Offset(generator->Position,
        { std::cos(angle), std::sin(angle), 0.0f }, 2.0f);
    return MoveCandidate(board, bot, point, "power_generator_stack", generator->Guid,
        BotActionArbitration::Priority::Mechanic, 150.0f);
}
}

#endif
