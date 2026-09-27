#ifndef TRINITY_BOT_OMNOTRON_POSITIONING_H
#define TRINITY_BOT_OMNOTRON_POSITIONING_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronMovement.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <string_view>
#include <vector>

// Raid geometry for Omnotron. Both tanked constructs are held on two slots
// beside the arena centre, so one healer position covers both tanks and a
// damage-focus switch costs a few yards instead of a run across the room.
// Round 1 (blackwing_descent_10n-r01): the Blood DK held the pulled Electron
// ~30 yd north of the centre, the Feral tank activated Magmatron at its spawn
// in the south, both healers stayed north, and the Feral tank died to
// Magmatron melee 50-57 yd from both healers (Holy Shock out_of_range).
namespace BotEncounter::Omnotron
{
// Tactic parameters (yards), not encounter values. The slots are 10 yd apart:
// close enough for cleave to reach both unshielded constructs, as in the
// matched WCL kill xAhkN2y9YP3KRmnJ fight 12 (one Heart Strike at 00:51.069
// and one Blood Boil at 00:57.088 each hit both Toxitron and Magmatron). A
// shielded construct is still dragged beyond ShieldSeparationDistance by
// ProposeTankPosition and walked back after its shield. A tank moves only
// when its construct is farther than the tolerance from its slot, and walks
// the trail distance past the slot so the following construct stops on it.
// Healers keep every living tank within HealerTankReach (BotOmnotronMovement.h).
inline constexpr float TankSlotOffset = 5.0f;
inline constexpr float TankSlotTolerance = 6.0f;
inline constexpr float ConstructTrail = 3.5f;
inline constexpr float SlotGeneratorClearance = PowerGeneratorRadius
    + ConstructBoundingRadius + 2.0f;

namespace Detail
{
inline std::array<Vector3, 2> BaseTankSlots(float z)
{
    return { Vector3{ ArenaCenterX - TankSlotOffset, ArenaCenterY, z },
        Vector3{ ArenaCenterX + TankSlotOffset, ArenaCenterY, z } };
}

// A slot inside a Power Generator's reach moves out of it along the line from
// the generator, so the slot never pulls a construct back into the +50%
// field the tank has just walked it out of.
inline Vector3 ClearOfGenerators(EncounterFacts const& facts, Vector3 slot)
{
    for (ActorSnapshot const* generator : facts.PowerGenerators)
        if (PlanarDistance(generator->Position, slot) < SlotGeneratorClearance)
        {
            Vector3 const away = Geometry::Direction(generator->Position, slot, 0.0f);
            Vector3 const center{ ArenaCenterX, ArenaCenterY, slot.Z };
            slot = Geometry::Offset(generator->Position, away, GeneratorExitDistance);
            float const distance = PlanarDistance(slot, center);
            if (distance > ArenaRadius)
            {
                slot.X = center.X + (slot.X - center.X) * ArenaRadius / distance;
                slot.Y = center.Y + (slot.Y - center.Y) * ArenaRadius / distance;
            }
        }
    return slot;
}
}

// The slot of the construct this tank holds. With two tanked constructs the
// pairing with the smaller total walk wins (ties by construct GUID), so both
// tanks compute the same assignment from one snapshot.
inline std::optional<Vector3> TankSlotFor(EncounterFacts const& facts,
    DutyPlan const& duty, ObjectGuid tankGuid)
{
    TankDuty const* mine = duty.TankDutyFor(tankGuid);
    ConstructFact const* own = mine ? facts.Find(mine->Construct) : nullptr;
    if (!own || !own->Fighting())
        return std::nullopt;
    ConstructFact const* other = nullptr;
    for (TankDuty const& tank : duty.Tanks)
        if (tank.Tank != tankGuid)
            if (ConstructFact const* fact = facts.Find(tank.Construct))
                if (fact->Fighting() && fact != own)
                    other = fact;
    std::array<Vector3, 2> const slots = Detail::BaseTankSlots(own->Actor->Position.Z);
    float const ownNear = PlanarDistance(own->Actor->Position, slots[0]);
    float const ownFar = PlanarDistance(own->Actor->Position, slots[1]);
    std::size_t index = ownNear <= ownFar ? 0 : 1;
    if (other)
    {
        float const straight = ownNear
            + PlanarDistance(other->Actor->Position, slots[1]);
        float const crossed = ownFar
            + PlanarDistance(other->Actor->Position, slots[0]);
        if (std::fabs(straight - crossed) > 0.01f)
            index = straight < crossed ? 0 : 1;
        else
            index = own->Actor->Guid < other->Actor->Guid ? 0 : 1;
    }
    return Detail::ClearOfGenerators(facts, slots[index]);
}

// A tank walks its unshielded construct to its slot. A shielded construct is
// left to the shield separation producer; a slot in a hazard is not taken.
inline std::optional<BotNativeAction::Candidate> ProposeTankSlot(
    Blackboard const& board, EncounterFacts const& facts, DutyPlan const& duty,
    ActorSnapshot const& bot)
{
    TankDuty const* tank = duty.TankDutyFor(bot.Guid);
    ConstructFact const* own = tank ? facts.Find(tank->Construct) : nullptr;
    if (!own || own->Shielded())
        return std::nullopt;
    std::optional<Vector3> const slot = TankSlotFor(facts, duty, bot.Guid);
    if (!slot || PlanarDistance(own->Actor->Position, *slot) <= TankSlotTolerance
        || HazardDepth(facts, *slot) > 0.0f)
        return std::nullopt;
    // The walked-to point is checked, not only the slot: the trail offset can
    // reach into a hazard beyond a clear slot. Then the slot itself (already
    // checked clear, clamped the same way) is the destination, else hold.
    Vector3 destination = Geometry::ClampToArena(bot.Position,
        Geometry::Offset(*slot, Geometry::Direction(own->Actor->Position, *slot,
            bot.Facing), ConstructTrail));
    if (HazardDepth(facts, destination) > 0.0f)
    {
        destination = Geometry::ClampToArena(bot.Position, *slot);
        if (HazardDepth(facts, destination) > 0.0f)
            return std::nullopt;
    }
    return MoveCandidate(board, bot, destination, "tank_center_slot",
        own->Actor->Guid, BotActionArbitration::Priority::Mechanic, 230.0f);
}

inline std::vector<ActorSnapshot const*> LivingTanks(Blackboard const& board)
{
    std::vector<ActorSnapshot const*> tanks;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && player.Role == "tank")
            tanks.push_back(&player);
    return tanks;
}

inline float FarthestTank(std::vector<ActorSnapshot const*> const& tanks,
    Vector3 const& point)
{
    float farthest = 0.0f;
    for (ActorSnapshot const* tank : tanks)
        farthest = std::max(farthest, PlanarDistance(tank->Position, point));
    return farthest;
}

// A healer with a living tank beyond HealerTankReach walks to the nearest
// clear point that reaches every tank: around the tanks' centroid, outside
// hazards and a Lightning Conductor carrier's reach.
inline std::optional<BotNativeAction::Candidate> ProposeHealerCoverage(
    Blackboard const& board, EncounterFacts const& facts, DutyPlan const& duty,
    ActorSnapshot const& bot, std::string_view role)
{
    if (role != "healer" || duty.HasMovementDuty(bot.Guid))
        return std::nullopt;
    std::vector<ActorSnapshot const*> const tanks = LivingTanks(board);
    if (tanks.empty() || FarthestTank(tanks, bot.Position) <= HealerTankReach)
        return std::nullopt;
    Vector3 centroid{ 0.0f, 0.0f, bot.Position.Z };
    for (ActorSnapshot const* tank : tanks)
    {
        centroid.X += tank->Position.X / float(tanks.size());
        centroid.Y += tank->Position.Y / float(tanks.size());
    }
    auto nearCarrier = [&](Vector3 const& point)
    {
        bool near = false;
        ForEachOtherPlayer(board, bot.Guid, [&](ActorSnapshot const& player)
        {
            near = near || (CarriesLightningConductor(player)
                && PlanarDistance(player.Position, point)
                    < LightningConductorRadius + ConductorClearance);
        });
        return near;
    };
    // Clear points that reach every tank: the shortest walk. Without one (tanks
    // far apart, or a hazard on the centroid), the clear point nearest to the
    // farthest tank, and only for a real gain. Never a point inside a hazard.
    std::optional<Vector3> reaching;
    float reachingTravel = 0.0f;
    std::optional<Vector3> closest;
    float closestFarthest = FarthestTank(tanks, bot.Position) - 3.0f;
    for (float radius : { 0.0f, 4.0f, 8.0f, 12.0f, 16.0f })
        for (int step = 0; step < (radius > 0.0f ? 16 : 1); ++step)
        {
            float const angle = float(step) * Geometry::Pi / 8.0f;
            Vector3 const point = Geometry::ClampToArena(bot.Position,
                Geometry::Offset(centroid, { std::cos(angle), std::sin(angle), 0.0f },
                    radius));
            if (HazardDepth(facts, point) > 0.0f || nearCarrier(point))
                continue;
            float const farthest = FarthestTank(tanks, point);
            float const travel = PlanarDistance(bot.Position, point);
            if (farthest <= HealerTankReach - 2.0f
                && (!reaching || travel < reachingTravel))
            {
                reaching = point;
                reachingTravel = travel;
            }
            if (farthest < closestFarthest)
            {
                closest = point;
                closestFarthest = farthest;
            }
        }
    std::optional<Vector3> const best = reaching ? reaching : closest;
    if (!best)
        return std::nullopt;
    return MoveCandidate(board, bot, *best, "healer_tank_coverage",
        tanks.front()->Guid, BotActionArbitration::Priority::Mechanic, 160.0f);
}
}

#endif
