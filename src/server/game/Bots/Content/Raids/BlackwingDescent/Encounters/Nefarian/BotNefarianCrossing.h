#ifndef TRINITY_BOT_NEFARIAN_CROSSING_H
#define TRINITY_BOT_NEFARIAN_CROSSING_H

// Cross-pillar help (round 8, user raid experience 2026-09-26, followed
// literally). When a healer pillar has killed its prototype, one healer and one
// damage dealer from it swim across the lava to the tank pillar and help finish.
// - Only the first finishing pillar sends help: the observer's kill order
//   (NativeFacts::PillarKillMs) persists it, a pillar whose healer died releases
//   it, and only while the platform rests at the lowered stop and the tank
//   pillar's prototype keeps CrossingMinTargetHealthPct.
// - The damage dealer is one whose magma defensive the bot actually has ready
//   (Divine Shield, Pain Suppression) if any, otherwise the first by slot: the
//   healer heals the pair during the swim.
// - A helper leaves only with CrossingMinHealthPct of its health; at the rim a
//   ready defensive is cast first (no movement that decision, so it owns the
//   cast lanes), and the step waits until it is up with
//   CrossingProtectionWindowMs left.
// - Lawful native stages only: walk to the rim on the slot heading closest to
//   the tank pillar, step off into the lava under the ledge-drop contract's
//   liquid variant (LandInLiquid, patch R8_ledge_drop_into_liquid.patch; the
//   dry-ground contract keeps refusing liquid), fall onto the sunken ring
//   (Land), float, swim to a spare swim station and hop onto the tank pillar.
// - Cancelled with the phase: no departure once the platform rises; a helper
//   already under way boards the rising floor (PlanPillarAscent) or, once its
//   target died, swims to the nearer of its own pillar and the tank pillar.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianAscent.h"
#include <optional>
#include <type_traits>
#include <utility>

namespace BotEncounter::Nefarian
{
constexpr float CrossingMinHealthPct = 80.0f;
constexpr float CrossingMinTargetHealthPct = 25.0f;
// A defensive must still cover this long when the helper steps off (the
// step, the fall and the first magma ticks).
constexpr uint64 CrossingProtectionWindowMs = 6000;

struct CrossingAssignment
{
    int Pillar = -1;      // the pillar to go to (-1: no crossing)
    uint8 Slot = 0;       // its spare slot there
    bool Departing = false;
};

// A member's magma defensive, as the native facts see it: it must be a spell
// the bot actually has (SpellKnown), not a spec mapping.
enum class DefensiveState : uint8
{
    None,        // no such spell known
    Ready,       // known, off cooldown, no Forbearance: cast it at the rim
    Active,      // up, with at least CrossingProtectionWindowMs left
    Unavailable  // known but on cooldown, blocked by Forbearance, or short
};

inline DefensiveState CrossingDefensiveState(ActorSnapshot const& actor,
    NativeFacts const* facts, uint64 nowMs)
{
    uint32 const spell = CrossingDefensiveFor(actor.ClassSpec);
    if (!spell || (facts && !facts->SpellKnown(actor.Guid, spell)))
        return DefensiveState::None;
    for (AuraSnapshot const& aura : actor.Auras)
        if (aura.SpellId == spell)
            return aura.ExpiresAtMs == 0 || aura.ExpiresAtMs >= nowMs + CrossingProtectionWindowMs
                ? DefensiveState::Active : DefensiveState::Unavailable;
    if (spell == SpellDivineShield && HasAura(actor, SpellForbearance))
        return DefensiveState::Unavailable;
    if (facts && !facts->SpellReady(actor.Guid, spell))
        return DefensiveState::Unavailable;
    return DefensiveState::Ready;
}

// A pillar's helpers (user raid experience 2026-09-26): its living healer and
// one living damage dealer - one whose defensive is ready or up if any,
// otherwise the first by slot (the healer heals the pair during the swim).
inline ObjectGuid PillarDamageHelper(Blackboard const& board, DutyPlan const& plan, int pillar,
    NativeFacts const* facts)
{
    ObjectGuid first;
    for (ObjectGuid member : plan.Pillars[pillar].Members)
        if (ActorSnapshot const* actor = board.FindActor(member);
            actor && actor->Alive && actor->Role == "dps")
        {
            DefensiveState const state = CrossingDefensiveState(*actor, facts, board.ObservedAtMs);
            if (state == DefensiveState::Ready || state == DefensiveState::Active)
                return member;
            if (first.IsEmpty())
                first = member;
        }
    return first;
}

// A pillar that can send help: a healer pillar with its healer alive.
inline bool PillarCanSendHelp(Blackboard const& board, DutyPlan const& plan, int pillar)
{
    if (pillar < 0 || pillar == plan.TankPillar || plan.Pillars[pillar].Healer.IsEmpty())
        return false;
    ActorSnapshot const* healer = board.FindActor(plan.Pillars[pillar].Healer);
    return healer && healer->Alive;
}

inline bool IsPillarHelper(Blackboard const& board, DutyPlan const& plan, int pillar,
    ObjectGuid guid, NativeFacts const* facts = nullptr)
{
    if (!PillarCanSendHelp(board, plan, pillar))
        return false;
    return guid == plan.Pillars[pillar].Healer
        || guid == PillarDamageHelper(board, plan, pillar, facts);
}

// The step-off into the lava needs the ledge-drop contract's liquid variant
// (TransportSurfaceMove::LandInLiquid, round 8 patch
// R8_ledge_drop_into_liquid.patch): the dry-ground contract rejects a
// landing under liquid (ledge_drop_lands_in_liquid) and must keep doing so.
// Until the executor carries it the crossing is not proposed at all.
template <typename Move, typename = void>
struct HasLandInLiquid : std::false_type { };
template <typename Move>
struct HasLandInLiquid<Move, std::void_t<decltype(std::declval<Move&>().LandInLiquid)>>
    : std::true_type { };
inline constexpr bool CrossingSupported =
    HasLandInLiquid<BotNativeAction::TransportSurfaceMove>::value;

template <typename Move>
inline void RequestLandInLiquid(Move& move)
{
    if constexpr (HasLandInLiquid<Move>::value)
        move.LandInLiquid = true;
}

template <typename Move>
inline bool LandsInLiquid(Move const& move)
{
    if constexpr (HasLandInLiquid<Move>::value)
        return move.LandInLiquid;
    else
        return false;
}

// The defensive cast due now: a departing helper at its rim with a ready
// defensive (PlanCrossingDeparture holds it there for the cast).
inline bool CrossingDefensiveDue(MovementContext const& context, CrossingAssignment const& crossing)
{
    return crossing.Departing && CrossingSupported
        && CrossingDefensiveState(context.Bot, context.Facts, context.Board.ObservedAtMs)
            == DefensiveState::Ready;
}

// Whether a member stands on (or above) its own pillar.
inline bool OnHomePillar(ActorSnapshot const& actor, int pillar, float originZ)
{
    LocalPoint const local = WorldToLocal(actor.Position);
    return Distance(local, PillarCenters[pillar % 3]) <= PillarSkirtRadius
        && actor.Position.Z >= originZ + PillarSkirtLocalZ + 1.5f;
}

// The pillar that sends help now, or -1: the first healer pillar to have
// killed its prototype (the observer's kill order, PillarKillMs, persists the
// choice: a later finisher never takes it over) among those whose healer
// lives. Without observed kill times (the replays): a pillar already under
// way keeps it, then the lower pillar.
inline int SendingPillar(Blackboard const& board, EncounterView const& view,
    DutyPlan const& plan, NativeFacts const* facts = nullptr)
{
    if (plan.TankPillar < 0 || view.CurrentPhase != Phase::PlatformHold)
        return -1;
    ActorSnapshot const* target = PillarPrototype(view, plan.TankPillar);
    if (!target || !target->Alive)
        return -1;
    int best = -1;
    uint64 bestKill = 0;
    for (int pillar = 0; pillar < int(plan.Pillars.size()); ++pillar)
    {
        if (!PillarCanSendHelp(board, plan, pillar) || PillarPrototype(view, pillar))
            continue;
        uint64 const kill = facts ? facts->PillarKillMs[pillar] : 0;
        if (kill && (best < 0 || !bestKill || kill < bestKill))
        {
            best = pillar;
            bestKill = kill;
            continue;
        }
        if (bestKill)
            continue;
        for (ObjectGuid member : plan.Pillars[pillar].Members)
            if (ActorSnapshot const* actor = board.FindActor(member);
                actor && actor->Alive && IsPillarHelper(board, plan, pillar, member, facts)
                && !OnHomePillar(*actor, pillar, view.Elevator.OriginZ))
                return pillar;
        if (best < 0)
            best = pillar;
    }
    return best;
}

inline CrossingAssignment CrossingFor(MovementContext const& context)
{
    CrossingAssignment crossing;
    if (!CrossingSupported)
        return crossing;
    DutyPlan const& plan = context.Plan;
    int const home = plan.PillarOf(context.Bot.Guid);
    if (home < 0 || !IsPillarHelper(context.Board, plan, home, context.Bot.Guid, context.Facts))
        return crossing;
    bool const onHome = OnHomePillar(context.Bot, home, context.View.Elevator.OriginZ);
    if (SendingPillar(context.Board, context.View, plan, context.Facts) == home)
    {
        ActorSnapshot const* target = PillarPrototype(context.View, plan.TankPillar);
        if (onHome && (context.Bot.HealthPct < CrossingMinHealthPct
                || !target || target->HealthPct < CrossingMinTargetHealthPct))
            return crossing;
        crossing.Pillar = plan.TankPillar;
        crossing.Slot = uint8(std::min<std::size_t>(5,
            plan.Pillars[plan.TankPillar].Members.size()
                + (context.Bot.Guid == plan.Pillars[home].Healer ? 0 : 1)));
        crossing.Departing = onHome;
        return crossing;
    }
    // Under way when the help ended (the target died, the phase moved on):
    // a helper swimming makes for the nearer pillar; one standing on the
    // tank pillar stays there. Only after its pillar's kill in phase 2 (the
    // lowered or rising platform), never before the prototypes appear.
    Phase const phase = context.View.CurrentPhase;
    bool const lateInPhaseTwo = phase == Phase::PlatformHold || phase == Phase::PlatformReturn;
    bool const swimming = context.Bot.Position.Z < MagmaSurfaceZ - 0.3f
        && !IsElevatorPassenger(context);
    float onPillarDistance = 0.0f;
    bool const onTankPillar = plan.TankPillar >= 0 && OnPillarStructure(context)
        && NearestPillar(BotLocal(context), onPillarDistance) == plan.TankPillar;
    if (lateInPhaseTwo && !onHome && (swimming || onTankPillar)
        && !PillarPrototype(context.View, home))
    {
        LocalPoint const local = BotLocal(context);
        float const toHome = Distance(local, PillarCenters[home % 3]);
        float const toTank = plan.TankPillar < 0 ? 1e9f
            : Distance(local, PillarCenters[plan.TankPillar % 3]);
        if (toTank < toHome)
        {
            crossing.Pillar = plan.TankPillar;
            crossing.Slot = uint8(std::min<std::size_t>(5,
                plan.Pillars[plan.TankPillar].Members.size()
                    + (context.Bot.Guid == plan.Pillars[home].Healer ? 0 : 1)));
        }
    }
    return crossing;
}

// The departure from the home pillar top: out to the rim on the slot heading
// closest to the tank pillar, step off, fall onto the sunken ring. The land,
// float, swim and hop follow (PlanPillarDescent's Land stage, then
// PlanPillarAscent toward the tank pillar).
inline DescentDecision PlanCrossingDeparture(MovementContext const& context, int home,
    int target)
{
    DescentDecision decision;
    ElevatorView const& elevator = context.View.Elevator;
    if (!context.Facts || elevator.State != ElevatorState::Lowered)
    {
        decision.Hold = "nefarian_crossing_wait_for_lowered_floor";
        return decision;
    }
    uint8 const pillar = uint8(home % 3);
    float const toward = AngleOf({ PillarCenters[target % 3].X - PillarCenters[pillar].X,
        PillarCenters[target % 3].Y - PillarCenters[pillar].Y });
    uint8 slot = 0;
    for (uint8 candidate = 1; candidate < 6; ++candidate)
        if (AngularGap(PillarSlotHeading(pillar, candidate), toward)
            < AngularGap(PillarSlotHeading(pillar, slot), toward))
            slot = candidate;
    float const heading = PillarSlotHeading(pillar, slot);
    LocalPoint const local = BotLocal(context);
    float const distance = Distance(local, PillarCenters[pillar]);

    BotNativeAction::TransportSurfaceMove move;
    move.Transport = elevator.Guid;
    move.LandingZ = elevator.OriginZ + RingLocalZ;
    move.LandingToleranceYards = 1.0f;
    move.LandOnTransport = true;
    move.MinHealthAfterFallPct = 0.2f;
    move.FloorToleranceYards = 0.6f;
    if (distance < DescentRimRadius - 0.3f || AngularGap(AngleOf({ local.X - PillarCenters[pillar].X,
            local.Y - PillarCenters[pillar].Y }), heading) > DegToRad(10.0f))
    {
        float const rimZ = PlatformFrame::PillarTopLocalZ - PillarRimSlope
            * (DescentRimRadius - SlotProfile(pillar, slot).FlatRadius);
        Vector3 const rim = LocalToWorld(Offset(PillarCenters[pillar], heading,
            DescentRimRadius), rimZ, elevator.OriginZ);
        move.Kind = BotNativeAction::TransportSurfaceMove::Stage::Walk;
        move.X = rim.X;
        move.Y = rim.Y;
        move.Z = rim.Z;
        move.EndOnTransport = true;
        decision.Move = move;
        decision.Mechanic = "pillar_crossing_rim";
        return decision;
    }
    // At the rim, before the irreversible step: the magma defensive first.
    // A ready one is cast now (the plan proposes no movement this decision,
    // so the instant cast owns the lanes); the step waits until it is up
    // with CrossingProtectionWindowMs left. Without one (none known, on
    // cooldown, Forbearance) the helper goes and its healer heals it.
    if (CrossingDefensiveState(context.Bot, context.Facts, context.Board.ObservedAtMs)
        == DefensiveState::Ready)
    {
        decision.Hold = "nefarian_crossing_defensive_first";
        return decision;
    }
    RequestLandInLiquid(move);
    if (distance < DescentOverVoidRadius(pillar, slot) - 0.15f)
    {
        Vector3 const off = LocalToWorld(Offset(PillarCenters[pillar], heading,
            DescentStepOffRadius), 0.0f, 0.0f);
        move.Kind = BotNativeAction::TransportSurfaceMove::Stage::StepOff;
        move.X = off.X;
        move.Y = off.Y;
        move.Z = context.Bot.Position.Z;
        decision.Move = move;
        decision.Mechanic = "pillar_crossing_step_off";
        return decision;
    }
    move.Kind = BotNativeAction::TransportSurfaceMove::Stage::Fall;
    decision.Move = move;
    decision.Mechanic = "pillar_crossing_fall";
    return decision;
}
}

#endif
