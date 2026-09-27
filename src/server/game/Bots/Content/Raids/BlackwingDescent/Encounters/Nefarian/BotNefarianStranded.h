#ifndef TRINITY_BOT_NEFARIAN_STRANDED_H
#define TRINITY_BOT_NEFARIAN_STRANDED_H

// Round 2 (live evidence, label blackwing_descent_10n-r01-553da85c98, kill
// 6bf52232): two ways a member was stranded off the fight for the rest of it.
//
// 1. Phase 2 retarget. The Elemental shaman's pillar prototype died at 100 s;
//    the plan then chose the nearest other prototype, about 70 yards away on
//    another pillar. Native combat range recovery walked her from the pillar
//    top toward it at pillar-top height and stopped in the air over the lava
//    (the point spline ended on its selected endpoint; the floor under it was
//    168 yards down). An elevator passenger does not fall by itself, so she
//    rose with the floor and hovered at local Z 10.3 through phase 3, where
//    Shadow of Cowardice (offset Z above 9.5) hit her every 4-6 seconds.
//    Now (user tactic, authoritative) only the crossing pair leaves, by the
//    swim path, and its damage dealer targets the tank pillar's prototype
//    only once in reach there; everyone else holds on its pillar.
//
// 2. Stranded above the floor. The rogue ended phase 2 at local Z 3.1, 8
//    yards from a pillar centre (outside its 6.05-yard skirt) and 1.7 yards
//    above the ring; no floor leg could start there, so the platform hold
//    kept him 26 yards from Nefarian for 15 minutes. A stationary passenger
//    standing clearly above the collision-model floor, clear of every pillar
//    structure, falls where it stands (the ledge-drop contract's Fall stage:
//    MotionMaster::MoveFall, refused unless the native floor query finds the
//    declared floor), like a client whose feet have no floor under them.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianCrossing.h"

namespace BotEncounter::Nefarian
{
// A crossing helper damages the tank pillar's prototype only once it is in
// reach (melee reach, or this for ranged): never earlier, or native range
// recovery would walk it off its pillar top instead of the swim.
constexpr float PrototypeHelpRangeYards = 30.0f;
// Standing this far above the model floor counts as stranded in the air.
constexpr float StrandedHeightYards = 1.0f;

inline bool MeleePrototypeHelper(ActorSnapshot const& bot)
{
    return IsMeleeDamageSpec(bot.ClassSpec) || bot.Role == "tank";
}

struct PhaseTwoHelp
{
    ActorSnapshot const* Target = nullptr;
    std::string_view Hold; // why no target (typed, for the trace)
};

// The phase 2 damage target of a member whose own pillar has no prototype
// (user raid experience 2026-09-26, authoritative): only the crossing pair
// (one healer and one damage dealer of the first healer pillar to finish,
// BotNefarianCrossing.h) leaves, by the swim path, and the damage dealer
// takes the tank pillar's prototype once it is in reach there. Everyone else
// holds on its pillar and never targets another pillar's prototype.
inline PhaseTwoHelp PhaseTwoHelpTarget(MovementContext const& context)
{
    PhaseTwoHelp help;
    CrossingAssignment const crossing = CrossingFor(context);
    if (crossing.Pillar < 0)
    {
        help.Hold = "nefarian_platform_prototype_out_of_reach";
        return help;
    }
    ActorSnapshot const* target = PillarPrototype(context.View, crossing.Pillar);
    float const reach = MeleePrototypeHelper(context.Bot) ? PrototypeMeleeReach
        : PrototypeHelpRangeYards;
    if (target && target->Alive
        && Distance3(target->Position, context.Bot.Position) <= reach)
        help.Target = target;
    else
        help.Hold = "nefarian_crossing_under_way";
    return help;
}

// A stationary elevator passenger over the resting raised floor, clear of
// every pillar structure, standing more than StrandedHeightYards above the
// collision-model floor under it.
inline bool StrandedAbovePlatform(MovementContext const& context)
{
    if (!context.Facts || context.View.Elevator.State != ElevatorState::Raised)
        return false;
    TransportPlacement const* placement = context.Facts->FindPlacement(context.Bot.Guid);
    if (!placement || placement->TransportEntry != ElevatorEntry)
        return false;
    if (FallState const* fall = context.Facts->FindFall(context.Bot.Guid);
        fall && (fall->Falling || fall->LandingPending))
        return false;
    if (MovementState const* motion = context.Facts->FindMotion(context.Bot.Guid);
        motion && motion->Moving)
        return false;
    LocalPoint const local = BotLocal(context);
    float pillarDistance = 0.0f;
    NearestPillar(local, pillarDistance);
    if (pillarDistance <= PillarSkirtRadius + 0.5f || Length(local) > OuterFloorLimit)
        return false;
    return placement->Offset.Z > FloorLocalZAt(local) + StrandedHeightYards;
}

// The fall of a stranded member onto the floor under it.
inline BotNativeAction::TransportSurfaceMove StrandedFall(MovementContext const& context)
{
    BotNativeAction::TransportSurfaceMove move;
    move.Transport = context.View.Elevator.Guid;
    move.Kind = BotNativeAction::TransportSurfaceMove::Stage::Fall;
    move.LandingZ = context.View.Elevator.OriginZ + FloorLocalZAt(BotLocal(context));
    move.LandingToleranceYards = 1.0f;
    move.LandOnTransport = true;
    move.MinHealthAfterFallPct = 0.2f;
    move.FloorToleranceYards = 0.6f;
    return move;
}
}

#endif
