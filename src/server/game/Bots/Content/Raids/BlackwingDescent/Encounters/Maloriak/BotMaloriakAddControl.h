#ifndef TRINITY_BOT_MALORIAK_ADD_CONTROL_H
#define TRINITY_BOT_MALORIAK_ADD_CONTROL_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakDuties.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakGeometry.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakKite.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <tuple>
#include <vector>

// Aberration control for the Feral off-tank (user tactic, user raid
// experience 2026-09-26): one burn target for every damage dealer, the
// off-tank's pickup, the hunter's Freeze Trap / Ice Trap, the shaman's Frost
// Shock, and the off-tank's paced kite. Every choice is a pure function of
// one blackboard, so all bots of the cohort agree on it.
namespace BotEncounter::Maloriak
{
// Freezing Trap Effect on an Aberration (damage breaks it).
constexpr uint32 FreezingTrapAuraSpell = 3355;
// Nature's Grasp: a baseline druid spell usable in bear form (the Nefarian
// capability note); an enemy striking the druid is rooted.
constexpr uint32 NaturesGraspSpell = 16689;
// Frost Shock 8056: 25-yard range (SpellRange 5), one yard of margin.
constexpr float FrostShockRangeYards = 24.0f;

inline bool IsFrozenAdd(ActorSnapshot const& add)
{
    return HasAura(add, FreezingTrapAuraSpell);
}

// Released, landed Aberrations the off-tank does not hold yet.
inline std::vector<ActorSnapshot const*> LooseAberrations(
    Observation const& observation, ObjectGuid offTank)
{
    std::vector<ActorSnapshot const*> loose;
    for (ActorSnapshot const* aberration : observation.ActiveAberrations)
        if (aberration->Attackable && aberration->VictimGuid != offTank)
            loose.push_back(aberration);
    return loose;
}

// The one Aberration every damage dealer burns (user refinement: one at a
// time): the weakest attackable one, a frozen one only when nothing else is
// left.
inline ActorSnapshot const* BurnFocus(Observation const& observation)
{
    ActorSnapshot const* best = nullptr;
    auto rank = [](ActorSnapshot const* add)
    {
        return std::make_tuple(IsFrozenAdd(*add), add->HealthPct, add->Guid.GetRawValue());
    };
    for (ActorSnapshot const* aberration : observation.ActiveAberrations)
        if (aberration->Attackable && (!best || rank(aberration) < rank(best)))
            best = aberration;
    return best;
}

// A player's aura on an add (a DoT, a debuff): someone is damaging it.
inline bool HasPlayerAura(Blackboard const& board, ActorSnapshot const& add)
{
    for (AuraSnapshot const& aura : add.Auras)
        if (!aura.CasterGuid.IsEmpty() && FindPlayer(board, aura.CasterGuid))
            return true;
    return false;
}

inline ObjectGuid FirstAlive(Blackboard const& board, bool (*capable)(std::string_view))
{
    ObjectGuid best;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && capable(player.ClassSpec)
            && (best.IsEmpty() || player.Guid.GetRawValue() < best.GetRawValue()))
            best = player.Guid;
    return best;
}

// Biting Chill isolation distance kept from a chilled player (the strategy's
// BitingChillExit).
constexpr float TrapPostChillYards = 8.0f;

// A trap post position keeps the Blue spread from every other living player
// and a Biting Chill target's isolation distance.
inline bool TrapPostPositionClear(Blackboard const& board, Vector3 const& position,
    ObjectGuid hunter)
{
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && player.Guid != hunter
            && Distance2d(player.Position, position)
                < (HasAura(player, BitingChillSpell) ? TrapPostChillYards : SpreadYards))
            return false;
    return true;
}

inline std::optional<Vector3> KiteTrapPost(Blackboard const& board,
    Observation const& observation, KiteGeometry const& kite, ObjectGuid hunter)
{
    std::vector<Vector3> corners = kite.Waypoints;
    Vector3 const boss = observation.Boss->Position;
    std::sort(corners.begin(), corners.end(), [&boss](Vector3 const& left, Vector3 const& right)
    {
        return Distance2d(left, boss) > Distance2d(right, boss);
    });
    for (Vector3 const& corner : corners)
        if (TrapPostPositionClear(board, corner, hunter))
            return corner;
    return std::nullopt;
}

// The raid-wide control assignment for one snapshot.
struct AddControl
{
    ActorSnapshot const* Focus = nullptr;       // every damage dealer's target
    std::vector<ActorSnapshot const*> Loose;     // attackable, not on the off-tank
    ActorSnapshot const* OffTankPickup = nullptr;
    ObjectGuid Hunter;
    ActorSnapshot const* FreezeTarget = nullptr; // unhit, running at the hunter
    ActorSnapshot const* IceTrapTarget = nullptr;
    std::optional<Vector3> TrapPoint;            // where the hunter lays it
    bool KiteTrap = false;                       // Ice Trap for the kited pack
    ActorSnapshot const* SlowTarget = nullptr;   // the shaman's Frost Shock
    std::vector<ActorSnapshot const*> Pack;      // Aberrations on the off-tank
    ObjectGuid OffTank;
    Vector3 OffTankPosition{};
    ObjectGuid SlowOwner;                        // the shaman
};

inline AddControl ResolveAddControl(Blackboard const& board,
    Observation const& observation, ObjectGuid offTank)
{
    AddControl control;
    control.Focus = BurnFocus(observation);
    control.Loose = LooseAberrations(observation, offTank);
    std::vector<ActorSnapshot const*> const& loose = control.Loose;
    for (ActorSnapshot const* aberration : observation.ActiveAberrations)
        if (aberration->Attackable && !offTank.IsEmpty()
            && aberration->VictimGuid == offTank)
            control.Pack.push_back(aberration);
    ActorSnapshot const* tank = FindPlayer(board, offTank);
    control.OffTank = tank ? offTank : ObjectGuid();
    if (tank)
        control.OffTankPosition = tank->Position;
    control.SlowOwner = FirstAlive(board, SlowsAberrations);
    ActorSnapshot const* shaman = FindPlayer(board, control.SlowOwner);

    // The off-tank's pickup: Prime Subjects first, then adds on healers and
    // damage dealers, then the nearest; never a frozen one (let it sleep).
    if (tank && tank->Alive)
    {
        auto squishyVictim = [&board](ActorSnapshot const& add)
        {
            ActorSnapshot const* victim = FindPlayer(board, add.VictimGuid);
            return victim && victim->Role != "tank";
        };
        std::vector<ActorSnapshot const*> candidates = loose;
        for (ActorSnapshot const* subject : observation.PrimeSubjects)
            if (subject->Attackable && subject->VictimGuid != offTank)
                candidates.push_back(subject);
        auto rank = [&](ActorSnapshot const& add)
        {
            return std::make_tuple(add.Entry == PrimeSubjectEntry ? 0 : 1,
                squishyVictim(add) ? 0 : 1, Distance2d(tank->Position, add.Position),
                add.Guid.GetRawValue());
        };
        for (ActorSnapshot const* add : candidates)
            if (!IsFrozenAdd(*add)
                && Distance2d(tank->Position, add->Position) <= 90.0f
                && (!control.OffTankPickup || rank(*add) < rank(*control.OffTankPickup)))
                control.OffTankPickup = add;
    }

    // The hunter's trap. Freeze Trap only for an Aberration running at the
    // hunter that nobody is damaging: not the burn focus, not the off-tank's
    // pickup, no player's aura (DoT) on it, not frozen already. Otherwise an
    // Ice Trap (a slow that damage does not break).
    control.Hunter = FirstAlive(board, LaysTraps);
    ActorSnapshot const* hunter = FindPlayer(board, control.Hunter);
    if (hunter)
        for (ActorSnapshot const* add : loose)
        {
            if (add->VictimGuid != hunter->Guid || IsFrozenAdd(*add)
                || Distance2d(add->Position, hunter->Position) > TrapTriggerYards)
                continue;
            bool const unhit = add != control.Focus && add != control.OffTankPickup
                && !HasPlayerAura(board, *add);
            if (unhit)
                control.FreezeTarget = add;
            else
                control.IceTrapTarget = add;
            control.TrapPoint = hunter->Position;
            break;
        }
    // The kited pack: an Ice Trap on a corner of the loop the off-tank
    // actually kites on (the corner farthest from Maloriak first). The post
    // keeps the Blue spread from every other player, the off-tank and its
    // pack standing there included, and a Biting Chill target's isolation
    // distance; with no such corner the post is suspended.
    if (hunter && !control.TrapPoint && !control.Pack.empty() && tank
        && observation.CurrentPhase != Phase::Red)
        if (std::optional<Vector3> const post = KiteTrapPost(board, observation,
                OccupiedKite(observation, tank->Position, control.Pack), hunter->Guid))
        {
            control.IceTrapTarget = control.Pack.front();
            control.TrapPoint = *post;
            control.KiteTrap = true;
        }

    // Frost Shock: a loose Aberration first (nearest Maloriak), then one on
    // the kited pack; never a frozen or freeze-reserved one, never one
    // already slowed.
    // Only an add within Frost Shock's range of the shaman (its fan slot is
    // the flank nearest the kite).
    auto slowable = [&](ActorSnapshot const* add)
    {
        return add != control.FreezeTarget && !IsFrozenAdd(*add)
            && !HasAura(*add, FrostShockSpell) && shaman
            && Distance2d(add->Position, shaman->Position) <= FrostShockRangeYards;
    };
    Vector3 const boss = observation.Boss->Position;
    for (std::vector<ActorSnapshot const*> const* group :
        std::array<std::vector<ActorSnapshot const*> const*, 2>{ &loose, &control.Pack })
    {
        for (ActorSnapshot const* add : *group)
            if (slowable(add) && (!control.SlowTarget
                || std::make_pair(Distance2d(add->Position, boss), add->Guid.GetRawValue())
                    < std::make_pair(Distance2d(control.SlowTarget->Position, boss),
                        control.SlowTarget->Guid.GetRawValue())))
                control.SlowTarget = add;
        if (control.SlowTarget)
            break;
    }
    return control;
}
}

#endif
