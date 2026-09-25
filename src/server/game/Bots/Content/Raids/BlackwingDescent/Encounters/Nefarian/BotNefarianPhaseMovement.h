#ifndef TRINITY_BOT_NEFARIAN_PHASE_MOVEMENT_H
#define TRINITY_BOT_NEFARIAN_PHASE_MOVEMENT_H

// Phase goals for Nefarian's End: pillar ascent/hold/descent, dragon tanking
// and raid formation. Hazard goals (fire, breath, kite) live in
// BotNefarianMovement.h and outrank everything here.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianMovement.h"

namespace BotEncounter::Nefarian
{
// Capability blocker of the current phase: phase 2 needs a lawful pillar
// ascent, which the movement layer does not provide (it can neither swim nor
// climb). Published on the plan and in the duty-plan status so the watchdog
// can classify the run; the bots still hold the pillar feet meanwhile.
inline std::string_view CapabilityBlocker(Phase phase, NativeFacts const* facts)
{
    if (PhaseWantsPillar(phase) && !(facts && facts->PillarAscentSupported))
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
    bool const onTop = OnPillarTop(context);
    // Without a pillar ascent the team holds the pillar's foot, where ranged
    // members reach the prototype (about 18 yd) through the magma.
    bool const ascent = context.Facts && context.Facts->PillarAscentSupported;
    if (!onTop && !ascent)
        return MakeGoal(context, MovePurpose::PillarFoot, Surface::Floor,
            PillarBase(uint8(pillar), slot), 3.0f, false, pillar);
    // While the floor is still up, wait at the pillar's foot; once it moves
    // the pillar top is the only refuge from the magma.
    if (phase == Phase::PlatformAscent && !onTop
        && context.View.Elevator.State == ElevatorState::Raised)
        return MakeGoal(context, MovePurpose::PillarAscent, Surface::Floor,
            PillarBase(uint8(pillar), slot), 3.0f, false, pillar);
    return MakeGoal(context, phase == Phase::PlatformAscent
            ? MovePurpose::PillarAscent : MovePurpose::PillarHold,
        Surface::PillarTop, PillarSlot(uint8(pillar), slot), 2.0f, !onTop,
        pillar);
}

inline LocalPoint NefarianGroundPosition(EncounterView const& view)
{
    if (view.Nefarian && view.NefarianLanded())
        return WorldToLocal(view.Nefarian->Position);
    return { 0.0f, 0.0f };
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
            layout.NefarianGroundFacing + sign * Pi / 2.0f, 16.0f);
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
    // The free Onyxia tank keeps reanimated warriors on the far wing, away
    // from Nefarian's breath and tail and from the raid.
    float const raidSign = PhaseThreeWingSign(view, layout);
    LocalPoint const pen = Offset(centre,
        layout.NefarianGroundFacing - raidSign * Pi / 2.0f, 24.0f);
    return MakeGoal(context, MovePurpose::WarriorPen, Surface::Floor, pen, 3.0f,
        false);
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
    float const wing = context.Layout.NefarianGroundFacing
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
    MovePurpose const purpose = OnPillarTop(context) ? MovePurpose::PillarDescent
        : MovePurpose::Formation;
    return MakeGoal(context, purpose, Surface::Floor, *moved, 3.0f,
        purpose == MovePurpose::PillarDescent);
}
}

#endif
