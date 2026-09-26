#ifndef TRINITY_BOT_MALORIAK_FORMATION_PLAN_H
#define TRINITY_BOT_MALORIAK_FORMATION_PLAN_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakDuties.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakGeometry.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakPlan.h"

#include <algorithm>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

// Formation movement for the adaptive Maloriak plan (split out of
// BotAdaptiveMaloriakStrategy.h): the Red cone stack, the Consuming Flames
// exit and the Blue, Dark and phase-two spread, with their hazard shifts.
namespace BotEncounter::Maloriak
{
constexpr float RangedSlotTolerance = 4.0f;
constexpr float MeleeSlotTolerance = 2.5f;

// While Aberrations are up in phase one the back fan of the ranged and the
// healers leans to the side of the Feral's kite: from 20 to 100 degrees off
// the rear toward that flank, 20 yards out, instead of 200 degrees across the
// back (six players stay 5.6 yards apart). Every fan slot then reaches every
// waypoint of that kite loop within 40 yards (healing the Feral, burning the
// pack), and the Frost Shock owner takes the flank end, within Frost Shock's
// 25 yards of the loop (review item 7).
constexpr float KiteFanNearDeg = 20.0f;
constexpr float KiteFanFarDeg = 100.0f;
constexpr float KiteFanRadius = 20.0f;

struct FanBias
{
    bool Active = false;
    float Side = 1.0f;       // +1: the kite is on the +V side of the frame
    ObjectGuid FlankOwner;   // takes the fan's flank end (the Frost Shock owner)
};

inline Vector3 BiasedBackRangedSlot(BossFrame const& frame, std::size_t position,
    std::size_t count, float side)
{
    float const t = count > 1 ? float(position) / float(count - 1) : 1.0f;
    float const offRear = (KiteFanNearDeg + (KiteFanFarDeg - KiteFanNearDeg) * t) * Pi / 180.0f;
    return FramePolar(frame, KiteFanRadius, Pi - side * offRear);
}

// The fan position of group member index: the flank owner moves to the end.
inline std::size_t FanPosition(std::vector<ActorSnapshot const*> const& group,
    std::size_t index, ObjectGuid flankOwner)
{
    std::size_t owner = group.size();
    for (std::size_t member = 0; member < group.size(); ++member)
        if (group[member]->Guid == flankOwner)
            owner = member;
    if (owner == group.size())
        return index;
    if (index == owner)
        return group.size() - 1;
    return index > owner ? index - 1 : index;
}

inline BotNativeAction::Candidate BuildMove(Blackboard const& board,
    Vector3 const& point, std::string_view mechanic, ObjectGuid actor,
    BotActionArbitration::Priority priority, float utility,
    bool preemptCasting)
{
    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = board.CurrentScope.Key();
    candidate.Id.Strategy = std::string(Maloriak::StrategyName);
    candidate.Id.Mechanic = std::string(mechanic);
    candidate.Id.Actor = actor;
    candidate.Id.EventGeneration = board.Revision;
    candidate.ActionPriority = priority;
    candidate.Utility = utility;
    candidate.ExpiresAtMs = board.ObservedAtMs + 750;
    candidate.Action = BotNativeAction::Move{ point.X, point.Y, point.Z,
        mechanic, preemptCasting };
    return candidate;
}

inline std::vector<ActorSnapshot const*> SortedGroup(Blackboard const& board,
    bool melee)
{
    std::vector<ActorSnapshot const*> group;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && player.Role != "tank"
            && (player.Role == "dps" && Maloriak::IsMeleeSpec(player.ClassSpec)) == melee)
            group.push_back(&player);
    std::sort(group.begin(), group.end(), [](ActorSnapshot const* left,
        ActorSnapshot const* right)
    {
        return left->Guid.GetRawValue() < right->Guid.GetRawValue();
    });
    return group;
}

inline std::size_t IndexIn(std::vector<ActorSnapshot const*> const& group,
    ObjectGuid guid)
{
    for (std::size_t index = 0; index < group.size(); ++index)
        if (group[index]->Guid == guid)
            return index;
    return group.size();
}

// Ranged slots are resolved in group order: each keeps the spread from
// the already resolved slots before it and from the unshifted ones after
// it, so two players never pick the same free point (every bot computes
// the same sequence). Passes: the nearest clear point within 40 degrees;
// then anywhere on the back arc (220 degrees either way, filtered by the
// arc), which a flank slot needs when the fan behind a boss at the
// cauldron rim is shadowed; then, as a last resort, a point in sight
// kept 2.5 yards only from the slots already resolved. Spread applies to
// the back-arc formations; the Red stack is meant to overlap.
template <typename SlotFor>
std::optional<Vector3> ResolveRangedSlot(Maloriak::BossFrame const& frame,
    std::vector<Maloriak::FormationHazard> const& hazards, Maloriak::SlotArc arc,
    std::size_t groupSize, std::size_t index, bool fanSlot,
    Vector3 const& destination, SlotFor const& slotFor)
{
    float const spread = arc == Maloriak::SlotArc::Back
        ? Maloriak::SpreadYards : 0.0f;
    auto spreadFrom = [spread](Vector3 const& point,
        std::vector<Vector3> const& others)
    {
        for (Vector3 const& other : others)
            if (Maloriak::Distance2d(point, other) < spread)
                return false;
        return true;
    };
    auto shift = [&](Vector3 const& slot, std::vector<Vector3> const& placed,
        std::vector<Vector3> const& others) -> std::optional<Vector3>
    {
        if (Maloriak::FormationPointClear(frame, slot, hazards)
            && spreadFrom(slot, placed))
            return slot;
        std::optional<Vector3> shifted = Maloriak::SafeFormationSlot(frame,
            slot, arc, 10.0f, 40.0f, hazards, others, spread, true);
        if (!shifted)
            shifted = Maloriak::SafeFormationSlot(frame, slot, arc, 10.0f,
                220.0f, hazards, others, spread, true);
        if (!shifted)
            shifted = Maloriak::SafeFormationSlot(frame, slot, arc, 10.0f,
                220.0f, hazards, placed, spread / 2.0f, true);
        return shifted;
    };
    auto othersFor = [&](std::size_t member, std::vector<Vector3> const& placed)
    {
        std::vector<Vector3> others = placed;
        for (std::size_t later = member + 1; later < groupSize; ++later)
            others.push_back(slotFor(later));
        return others;
    };
    std::vector<Vector3> placed;
    for (std::size_t member = 0; member < index; ++member)
        placed.push_back(fanSlot
            ? shift(slotFor(member), placed, othersFor(member, placed))
                .value_or(slotFor(member))
            : slotFor(member));
    return shift(destination, placed, othersFor(index, placed));
}

// Formation: Red stacks in the Scorching Blast cone except Consuming
// Flames targets; Blue, Dark and phase two spread behind. Green and the
// vial transitions leave ordinary combat movement alone. A bot whose
// target is not the boss (adds, ice blocks) keeps native combat movement.
// Slots inside a hazard clearance (Absolute Zero, jet fire, ice block)
// shift along their arc; melee with no clear ring point hold offense
// instead of chasing back into the hazard.
inline std::optional<BotNativeAction::Candidate> ProposeFormation(
    Blackboard const& board, Maloriak::Observation const& observation,
    ActorSnapshot const& bot, std::string_view botRole,
    Maloriak::BossFrame const& frame, AdaptiveMaloriakPlan& plan,
    FanBias const& bias = {})
{
    // A passive boss is walking to the cauldron or changing phase: its
    // facing points at the cauldron, not at the tank, so no formation.
    if (!observation.Boss->ReactAggressive)
        return std::nullopt;
    // A chilled player keeps the position its isolation gave it.
    if (Maloriak::HasAura(bot, Maloriak::BitingChillSpell))
        return std::nullopt;
    bool const melee = botRole == "dps" && Maloriak::IsMeleeSpec(bot.ClassSpec);
    // Boss-mechanic positioning does not depend on the offensive target:
    // ranged damage dealers and healers keep the Red cone stack (Scorching
    // Blast is split among everyone in it), the Consuming Flames exit and
    // the Blue spread while they burn Aberrations; the flank kite stays
    // within their spell reach. Melee damage dealers on an Aberration
    // fight it where the off-tank has it, so in Red the cone is shared by
    // the main tank, the healers and the ranged.
    if (melee && plan.DamageTarget != observation.Boss->Guid)
        return std::nullopt;
    std::vector<ActorSnapshot const*> const group = SortedGroup(board, melee);
    std::size_t const index = IndexIn(group, bot.Guid);
    if (index == group.size())
        return std::nullopt;
    auto slotFor = [&](std::size_t slotIndex) -> Vector3
    {
        switch (observation.CurrentPhase)
        {
            case Maloriak::Phase::Red:
                return melee ? Maloriak::FrontMeleeSlot(frame, slotIndex)
                    : Maloriak::FrontStackSlot(frame, slotIndex);
            default:
                if (melee)
                    return Maloriak::BackMeleeSlot(frame, slotIndex);
                if (bias.Active && observation.CurrentPhase != Maloriak::Phase::PhaseTwo)
                    return BiasedBackRangedSlot(frame,
                        FanPosition(group, slotIndex, bias.FlankOwner), group.size(),
                        bias.Side);
                return Maloriak::BackRangedSlot(frame, slotIndex, group.size());
        }
    };
    Vector3 destination;
    std::string_view mechanic;
    Maloriak::SlotArc arc = Maloriak::SlotArc::Back;
    switch (observation.CurrentPhase)
    {
        case Maloriak::Phase::Red:
            if (Maloriak::HasAnyAura(bot, Maloriak::ConsumingFlamesSpells))
            {
                destination = Maloriak::BehindSlot(frame, melee);
                mechanic = "consuming_flames_leave_cone";
            }
            else
            {
                destination = slotFor(index);
                mechanic = "red_cone_stack";
                arc = Maloriak::SlotArc::FrontCone;
            }
            break;
        case Maloriak::Phase::Blue:
        case Maloriak::Phase::Black:
        case Maloriak::Phase::PhaseTwo:
            destination = slotFor(index);
            mechanic = observation.CurrentPhase == Maloriak::Phase::Blue
                ? "blue_spread"
                : observation.CurrentPhase == Maloriak::Phase::Black
                    ? "dark_spread" : "phase_two_spread";
            break;
        default:
            return std::nullopt;
    }

    std::vector<Maloriak::FormationHazard> const hazards =
        Maloriak::CollectFormationHazards(observation);
    // Hazards and the cauldron (no line of sight across it) both shift
    // the slot along its arc.
    if (melee && !Maloriak::FormationPointClear(frame, destination, hazards))
    {
        // Only hazards hold melee offense; a slot the cauldron shadows
        // shifts around the ring, and with no ring point in sight the
        // melee player simply keeps fighting where it is.
        if (Maloriak::MeleeRingBlocked(frame, arc, hazards))
        {
            plan.SuppressOffense = true;
            plan.SuppressReason = "melee_ring_hazard_hold";
            plan.Duty = "melee_ring_hazard_hold";
            return std::nullopt;
        }
        std::optional<Vector3> const shifted = Maloriak::SafeFormationSlot(
            frame, destination, arc, 30.0f, 180.0f, hazards, {}, 0.0f, false);
        if (!shifted)
            return std::nullopt;
        destination = *shifted;
    }
    else if (!melee)
    {
        std::optional<Vector3> const shifted = ResolveRangedSlot(frame,
            hazards, arc, group.size(), index,
            mechanic != "consuming_flames_leave_cone", destination, slotFor);
        if (!shifted)
            return std::nullopt;
        destination = *shifted;
    }
    float const tolerance = melee ? MeleeSlotTolerance : RangedSlotTolerance;
    // A ranged player near its slot but itself behind the cauldron still
    // steps onto the slot.
    bool const inSight = melee || !Maloriak::CauldronConstrains(frame.Boss)
        || Maloriak::CauldronLineClear(bot.Position, frame.Boss);
    if (inSight && Maloriak::Distance2d(bot.Position, destination) <= tolerance)
        return std::nullopt;
    if (!melee)
    {
        std::vector<Vector3> neighbours;
        for (ActorSnapshot const& player : board.Players)
            if (player.Alive && player.Guid != bot.Guid)
                neighbours.push_back(player.Position);
        if (Maloriak::RangedPlaceAcceptable(frame, bot.Position, destination,
                arc, hazards, neighbours,
                arc == Maloriak::SlotArc::Back ? Maloriak::SpreadYards : 0.0f))
            return std::nullopt;
    }
    return BuildMove(board, destination, mechanic, observation.Boss->Guid,
        BotActionArbitration::Priority::Mechanic, 200.0f, false);
}
}

#endif
