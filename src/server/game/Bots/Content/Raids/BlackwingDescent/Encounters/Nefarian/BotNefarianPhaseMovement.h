#ifndef TRINITY_BOT_NEFARIAN_PHASE_MOVEMENT_H
#define TRINITY_BOT_NEFARIAN_PHASE_MOVEMENT_H

// Phase goals for Nefarian's End: pillar foot/top, dragon tanking, the bone
// warrior handler and raid formation. Hazard goals (fire, breath, kite) live
// in BotNefarianMovement.h and outrank everything here; the swim-and-hop
// ascent and the descent steps are in BotNefarianAscent.h.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianAscent.h"

namespace BotEncounter::Nefarian
{
inline bool AscentSupported(NativeFacts const* facts)
{
    return facts ? facts->PillarAscentSupported : RuntimePillarAscentSupported();
}

// Capability blocker of the current phase: phase 2 needs the swim-and-hop
// ascent (package T's Float, Swim and Hop stages, patch
// .git/round6_patches/nefarian/N1). Without it the plan and the duty-plan
// status carry pillar_ascent_unsupported so the watchdog can classify the
// run; the bots still hold the pillar feet meanwhile.
inline std::string_view CapabilityBlocker(Phase phase, NativeFacts const* facts)
{
    if (PhaseWantsPillar(phase) && !AscentSupported(facts))
        return "pillar_ascent_unsupported";
    return {};
}

inline std::optional<SurfaceGoal> PillarGoal(MovementContext const& context)
{
    Phase const phase = context.View.CurrentPhase;
    if (!PhaseWantsPillar(phase))
        return std::nullopt;
    int const pillar = context.Plan.PillarOf(context.Bot.Guid);
    if (pillar < 0)
        return std::nullopt;
    uint8 const slot = context.Plan.SlotOf(context.Bot.Guid);
    if (OnPillarStructure(context))
        return MakeGoal(context, phase == Phase::PlatformAscent
                ? MovePurpose::PillarAscent : MovePurpose::PillarHold,
            Surface::PillarTop, PillarSlot(uint8(pillar), slot), 1.0f, false,
            pillar);
    // The foot of the pillar on the member's slot heading, reached while the
    // floor keeps still. Without an ascent the team holds it; ranged members
    // reach the prototype (about 10 yd) from there.
    return MakeGoal(context, AscentSupported(context.Facts)
            ? MovePurpose::PillarAscent : MovePurpose::PillarFoot,
        Surface::Floor, PillarBase(uint8(pillar), slot), 1.5f,
        context.View.Elevator.State == ElevatorState::Raised, pillar);
}

inline LocalPoint NefarianGroundPosition(EncounterView const& view)
{
    if (view.Nefarian && view.NefarianLanded())
        return WorldToLocal(view.Nefarian->Position);
    return { 0.0f, 0.0f };
}

// Nefarian's facing on the ground: observed once he has landed, otherwise
// the layout's (he lands facing his tank).
inline float GroundFacing(EncounterView const& view, ArenaLayout const& layout)
{
    if (view.Nefarian && view.NefarianLanded())
        return PoseOf(*view.Nefarian).Facing;
    return layout.NefarianGroundFacing;
}

// Phase 3 wing: the side of Nefarian with more room from Shadowblaze fires
// and bone warriors (sparks land on warriors, collapsed or not).
inline float PhaseThreeWingSign(EncounterView const& view,
    ArenaLayout const& layout)
{
    LocalPoint const centre = NefarianGroundPosition(view);
    float bestScore = -1.0f;
    float bestSign = 1.0f;
    for (float sign : { 1.0f, -1.0f })
    {
        LocalPoint const wing = Offset(centre,
            GroundFacing(view, layout) + sign * Pi / 2.0f, 16.0f);
        float score = 60.0f;
        for (auto const* list : { &view.Fires, &view.BoneWarriors })
            for (ActorSnapshot const* actor : *list)
                score = std::min(score,
                    Distance(WorldToLocal(actor->Position), wing));
        if (score > bestScore + 2.0f)
        {
            bestScore = score;
            bestSign = sign;
        }
    }
    return bestSign;
}

inline std::optional<SurfaceGoal> TankGoal(MovementContext const& context)
{
    bool const onyxiaTank = context.Bot.Guid == context.Plan.OnyxiaTank;
    bool const nefarianTank = context.Bot.Guid == context.Plan.NefarianTank;
    if (!onyxiaTank && !nefarianTank)
        return std::nullopt;
    EncounterView const& view = context.View;
    ArenaLayout const& layout = context.Layout;
    Phase const phase = view.CurrentPhase;

    auto fromSpot = [&context](TankSpot const& spot)
    {
        MovePurpose const purpose = spot.Step == TankStep::Hold
            ? MovePurpose::TankHold : spot.Step == TankStep::Discharge
            ? MovePurpose::DischargeTurn : MovePurpose::TankLead;
        return MakeGoal(context, purpose, Surface::Floor, spot.Point, 2.5f,
            spot.Step == TankStep::Discharge);
    };

    if (phase == Phase::PreEngage || phase == Phase::OnyxiaOnly
        || phase == Phase::BothDragons)
    {
        if (onyxiaTank && view.OnyxiaAlive())
        {
            if (phase == Phase::PreEngage)
                return MakeGoal(context, MovePurpose::Stage, Surface::Floor,
                    Offset(WorldToLocal(view.Onyxia->Position),
                        layout.OnyxiaEndAngle, 10.0f), 3.0f, false);
            return fromSpot(PlanTankSpot(WorldToLocal(view.Onyxia->Position),
                layout.OnyxiaEndAngle, OnyxiaMeleeReach,
                view.OnyxiaDischarging()));
        }
        if (nefarianTank)
        {
            if (phase != Phase::BothDragons)
                return MakeGoal(context, MovePurpose::Stage, Surface::Floor,
                    Polar(layout.NefarianEndAngle, 12.0f), 3.0f, false);
            return fromSpot(PlanTankSpot(WorldToLocal(view.Nefarian->Position),
                layout.NefarianEndAngle, NefarianMeleeReach, false));
        }
        return std::nullopt;
    }

    if (phase != Phase::NefarianLanding && phase != Phase::NefarianGround)
        return std::nullopt;
    LocalPoint const centre = NefarianGroundPosition(view);
    if (nefarianTank)
        return MakeGoal(context, MovePurpose::TankHold, Surface::Floor,
            Offset(centre, layout.NefarianGroundFacing, 14.0f), 2.5f, false);
    if (context.Bot.Guid != context.Plan.WarriorHandler)
        return std::nullopt;
    // The warrior handler keeps reanimated warriors in a pen on the far wing,
    // away from the raid and never in front of Nefarian (his breath wakes and
    // empowers them), and kites them around the pen while one reaches it.
    // Kiting starts when an unheld chaser comes within HandlerKiteTriggerYards
    // and ends only past HandlerKiteReleaseYards; a running kite keeps its
    // destination to the end; and while a chaser is within the release, no
    // destination (kite or pen) is ever back toward it.
    float const raidSign = PhaseThreeWingSign(view, layout);
    float const penBearing = GroundFacing(view, layout) - raidSign * Pi / 2.0f;
    LocalPoint const self = BotLocal(context);
    ActorSnapshot const* chaser = ChasingBoneWarrior(view, context.Bot,
        HandlerKiteReleaseYards);
    LocalPoint const from = chaser ? WorldToLocal(chaser->Position) : self;
    // Never back toward the chaser: the walk heads at least 60 degrees off
    // the direction to it (along the pen arc with the warrior coming from
    // the centre side is fine; turning back past it is not).
    auto away = [&](LocalPoint point)
    {
        if (!chaser)
            return true;
        LocalPoint const walk{ point.X - self.X, point.Y - self.Y };
        LocalPoint const toward{ from.X - self.X, from.Y - self.Y };
        return walk.X * toward.X + walk.Y * toward.Y
            <= 0.5f * Length(walk) * Length(toward);
    };
    auto onPenArc = [&](LocalPoint point)
    {
        return std::fabs(Distance(point, centre) - HandlerPenRadius) <= 1.5f;
    };
    if (chaser && context.Facts)
        if (MovementState const* motion = context.Facts->FindMotion(context.Bot.Guid);
            motion && motion->Moving)
        {
            LocalPoint const running = WorldToLocal(motion->Destination);
            if (Distance(self, running) >= 0.5f && onPenArc(running) && away(running)
                && FloorPointSafe(context, running, true))
                return MakeGoal(context, MovePurpose::Kite, Surface::Floor, running,
                    2.0f, false);
        }
    if (chaser && Distance3(chaser->Position, context.Bot.Position) < HandlerKiteTriggerYards)
    {
        std::optional<LocalPoint> best;
        float bestDistance = 0.0f;
        for (float step : { -30.0f, -15.0f, 0.0f, 15.0f, 30.0f })
        {
            LocalPoint const point = Offset(centre, penBearing
                - raidSign * DegToRad(step), HandlerPenRadius);
            if (Distance(point, self) < 1.0f || !away(point)
                || !FloorPointSafe(context, point, true))
                continue;
            float const distance = Distance(point, from);
            if (!best || distance > bestDistance)
            {
                best = point;
                bestDistance = distance;
            }
        }
        // Cornered at the end of the arc: hold and tank it there (Nature's
        // Grasp roots it) rather than walk back past it.
        SurfaceGoal goal = MakeGoal(context, MovePurpose::Kite, Surface::Floor,
            best ? *best : self, 2.0f, false);
        goal.WarriorHold = !best;
        return goal;
    }
    // The pen itself, or the nearest pen-arc point the handler can reach
    // without leading a warrior past Nefarian's front (or back toward a
    // chaser still within the release distance: then it holds).
    for (float step : { 0.0f, -15.0f, 15.0f, -30.0f, 30.0f })
    {
        LocalPoint const point = Offset(centre, penBearing - raidSign * DegToRad(step),
            HandlerPenRadius);
        if (away(point) && FloorPointSafe(context, point, true))
            return MakeGoal(context, MovePurpose::WarriorPen, Surface::Floor, point,
                3.0f, false);
    }
    if (chaser)
    {
        SurfaceGoal goal = MakeGoal(context, MovePurpose::WarriorPen, Surface::Floor,
            self, 3.0f, false);
        goal.WarriorHold = true;
        return goal;
    }
    return std::nullopt;
}

inline uint8 FormationSlot(Blackboard const& board, ObjectGuid guid)
{
    uint8 slot = 0;
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid.GetCounter() < guid.GetCounter())
            ++slot;
    return slot;
}

inline std::optional<SurfaceGoal> FormationGoal(MovementContext const& context,
    ObjectGuid damageTarget)
{
    EncounterView const& view = context.View;
    Phase const phase = view.CurrentPhase;
    ActorSnapshot const& bot = context.Bot;
    bool const melee = IsMeleeDamageSpec(bot.ClassSpec);
    uint8 const slot = FormationSlot(context.Board, bot.Guid);
    float const slotAngle = float(slot) * (TwoPi / 10.0f);

    if (phase == Phase::PreEngage || phase == Phase::OnyxiaOnly
        || phase == Phase::BothDragons)
    {
        if (!view.OnyxiaAlive())
            return std::nullopt;
        LocalPoint const onyxia = WorldToLocal(view.Onyxia->Position);
        LocalPoint const nefarian = view.Nefarian
            ? WorldToLocal(view.Nefarian->Position) : LocalPoint{};
        LocalPoint anchor = RaidAnchor(context.Layout, onyxia, nefarian,
            view.NefarianLanded());
        // Until her tank has led Onyxia out of the centre, the raid waits
        // beside her lead-out path, outside her melee reach.
        bool const onyxiaCentred = Length(onyxia) < 15.0f;
        if (phase == Phase::PreEngage || (onyxiaCentred && !view.NefarianLanded()))
            anchor = Offset(onyxia, context.Layout.OnyxiaEndAngle + Pi / 2.0f,
                24.0f);
        LocalPoint wanted = Offset(anchor, slotAngle, 5.0f);
        if (melee && phase != Phase::PreEngage)
        {
            ActorSnapshot const* target = damageTarget == view.Onyxia->Guid
                || !view.Nefarian ? view.Onyxia : view.Nefarian;
            LocalPoint const body = WorldToLocal(target->Position);
            LocalPoint const toward{ anchor.X - body.X, anchor.Y - body.Y };
            float const reach = target == view.Onyxia ? OnyxiaMeleeReach
                : NefarianMeleeReach;
            wanted = Offset(body, AngleOf(toward) + DegToRad(8.0f * (slot % 3)),
                reach - 8.0f);
        }
        std::optional<LocalPoint> const safe = SafeNear(context, wanted,
            AngleOf({ wanted.X - anchor.X, wanted.Y - anchor.Y }), 0.0f,
            false);
        std::optional<LocalPoint> const moved = safe ? safe
            : SafeNear(context, anchor, slotAngle, 7.0f, false);
        if (!moved)
            return std::nullopt;
        return MakeGoal(context, phase == Phase::PreEngage ? MovePurpose::Stage
            : MovePurpose::Formation, Surface::Floor, *moved, 3.0f, false);
    }

    if (phase != Phase::NefarianLanding && phase != Phase::NefarianGround)
        return std::nullopt;
    LocalPoint const centre = NefarianGroundPosition(view);
    float const wing = GroundFacing(view, context.Layout)
        + PhaseThreeWingSign(view, context.Layout) * Pi / 2.0f;
    float const depth = melee ? NefarianMeleeReach - 9.0f
        : 18.0f + float(slot / 5) * 4.0f;
    LocalPoint const wanted = Offset(Offset(centre, wing, depth),
        wing + Pi / 2.0f, (float(slot % 5) - 2.0f) * 3.0f);
    std::optional<LocalPoint> const safe = SafeNear(context, wanted, wing, 0.0f,
        false);
    std::optional<LocalPoint> const moved = safe ? safe
        : SafeNear(context, centre, wing, depth, false);
    if (!moved)
        return std::nullopt;
    MovePurpose const purpose = OnPillarStructure(context)
        ? MovePurpose::PillarDescent : MovePurpose::Formation;
    return MakeGoal(context, purpose, Surface::Floor, *moved, 3.0f,
        purpose == MovePurpose::PillarDescent);
}
}

#endif
