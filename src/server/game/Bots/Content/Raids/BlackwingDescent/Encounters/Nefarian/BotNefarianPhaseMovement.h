#ifndef TRINITY_BOT_NEFARIAN_PHASE_MOVEMENT_H
#define TRINITY_BOT_NEFARIAN_PHASE_MOVEMENT_H

// Phase goals for Nefarian's End: pillar foot/top, dragon tanking, the bone
// warrior handler and raid formation. Hazard goals (fire, breath, kite) live
// in BotNefarianMovement.h and outrank everything here; the swim-and-hop
// ascent and the descent steps are in BotNefarianAscent.h.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianAscent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianCrossing.h"
#include <algorithm>
#include <initializer_list>
#include <vector>

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
    int pillar = context.Plan.PillarOf(context.Bot.Guid);
    if (pillar < 0)
        return std::nullopt;
    uint8 slot = context.Plan.SlotOf(context.Bot.Guid);
    // A helper crossing to the tank pillar (round 8) takes a spare slot there.
    if (CrossingAssignment const crossing = CrossingFor(context);
        crossing.Pillar >= 0 && !crossing.Departing)
    {
        pillar = crossing.Pillar;
        slot = crossing.Slot;
    }
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

// Round 7: a caster or healer whose line to its target crosses a pillar
// (the pillars rise about 10 yards above the raised floor) gets a line of
// sight failure, and native combat range recovery then walked it off the
// platform. Formation spots for them keep every line clear of the pillars.
constexpr float PillarSightRadius = 6.1f; // the skirt at the pillar's base

inline bool PillarSightClear(LocalPoint from, LocalPoint to)
{
    LocalPoint const d{ to.X - from.X, to.Y - from.Y };
    float const length2 = d.X * d.X + d.Y * d.Y;
    for (LocalPoint const& pillar : PillarCenters)
    {
        float t = length2 > 1e-4f
            ? ((pillar.X - from.X) * d.X + (pillar.Y - from.Y) * d.Y) / length2 : 0.0f;
        t = std::clamp(t, 0.0f, 1.0f);
        if (Distance(pillar, { from.X + d.X * t, from.Y + d.Y * t }) < PillarSightRadius)
            return false;
    }
    return true;
}

// The Onyxia tank's pickup (round 7). Until she attacks it, the pickup owns
// its movement:
// - within reach of her (Growl's range, 30, less a margin; melee reach when
//   Growl is not usable now) with a clear line (the pillar model and, when
//   observed, the native line of sight): it stands still, so no movement
//   claims the cast lanes and the taunt (ThreatControl) runs;
// - otherwise it walks to a safe floor spot within OnyxiaPickupYards of her
//   with a pillar-clear line, on the side it comes from. A spot the native
//   line of sight rejected is left for another at least 4 yards away (the
//   bounded recovery: a finite list of spots).
// Only once she targets it does it lead her out (PlanTankSpot).
constexpr float OnyxiaPickupYards = 25.0f;
constexpr float OnyxiaTauntReachYards = 28.0f; // Growl 30, less a margin

// The same pickup for either dragon (round 8: in the r07 run's first attempt
// the hunter held Nefarian at the centre for the whole attempt while the
// Blood DK waited 48 yards away at its pull spot, out of taunt range).
inline SurfaceGoal DragonPickupGoal(MovementContext const& context,
    ActorSnapshot const& onyxiaActor, float meleeReach)
{
    LocalPoint const self = BotLocal(context);
    LocalPoint const onyxia = WorldToLocal(onyxiaActor.Position);
    uint32 const taunt = TauntFor(context.Bot.ClassSpec).SpellId;
    bool const tauntUsable = taunt
        && (!context.Facts || context.Facts->SpellUsable(context.Bot.Guid, taunt));
    float const reach = tauntUsable ? OnyxiaTauntReachYards : meleeReach - 2.0f;
    bool const nativeSight = !context.Facts || context.Facts->InSight(onyxiaActor.Guid);
    PickupState const* memory = context.Facts
        ? context.Facts->FindPickup(context.Bot.Guid, onyxiaActor.Guid) : nullptr;
    // The budget spent (PickupMemory): hold and keep trying from here.
    if (memory && memory->Exhausted)
        return MakeGoal(context, MovePurpose::TankLead, Surface::Floor, self, 3.0f, true);
    if (Distance(self, onyxia) <= reach && PillarSightClear(self, onyxia) && nativeSight)
        return MakeGoal(context, MovePurpose::TankLead, Surface::Floor, self, 3.0f, true);
    auto rejected = [memory](LocalPoint point)
    {
        if (!memory)
            return false;
        for (Vector3 const& spot : memory->RejectedSpots)
            if (Distance(WorldToLocal(spot), point) < 4.0f)
                return true;
        return false;
    };
    float const bearing = Distance(self, onyxia) < 0.5f ? 0.0f
        : AngleOf({ self.X - onyxia.X, self.Y - onyxia.Y });
    float const outer = std::min(OnyxiaPickupYards, reach - 3.0f);
    for (float radius : { outer, outer - 5.0f, outer - 10.0f })
        for (float step : { 0.0f, 20.0f, -20.0f, 40.0f, -40.0f, 60.0f, -60.0f, 90.0f, -90.0f })
        {
            LocalPoint const point = Offset(onyxia, bearing + DegToRad(step), radius);
            if ((!nativeSight && Distance(point, self) < 4.0f) || rejected(point))
                continue;
            if (FloorPointSafe(context, point, true) && PillarSightClear(point, onyxia))
                return MakeGoal(context, MovePurpose::TankLead, Surface::Floor, point, 3.0f,
                    true);
        }
    // No spot: hold, and let the taunt try from here.
    return MakeGoal(context, MovePurpose::TankLead, Surface::Floor, self, 3.0f, true);
}

inline SurfaceGoal OnyxiaPickupGoal(MovementContext const& context)
{
    return DragonPickupGoal(context, *context.View.Onyxia, OnyxiaMeleeReach);
}

inline std::optional<SurfaceGoal> TankGoal(MovementContext const& context)
{
    // The Onyxia tank now: her tank, or the Blood DK when hers is dead.
    bool const onyxiaTank = ActsAsOnyxiaTank(context.Board, context.View, context.Plan,
        context.Bot.Guid);
    bool const nefarianTank = context.Bot.Guid == context.Plan.NefarianTank && !onyxiaTank;
    if (!onyxiaTank && !nefarianTank && context.Bot.Guid != context.Plan.WarriorHandler)
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
            // Round 7: pick her up first. Until she attacks her tank, it
            // walks to where it sees her past the pillars within taunt range
            // (the first live attempt's Feral landed behind a pillar and its
            // Growl failed on line of sight for 24 s).
            if (view.Onyxia->VictimGuid != context.Bot.Guid)
                return OnyxiaPickupGoal(context);
            return fromSpot(PlanTankSpot(WorldToLocal(view.Onyxia->Position),
                layout.OnyxiaEndAngle, OnyxiaMeleeReach,
                view.OnyxiaDischarging()));
        }
        if (nefarianTank)
        {
            if (phase != Phase::BothDragons)
                return MakeGoal(context, MovePurpose::Stage, Surface::Floor,
                    Polar(layout.NefarianEndAngle, 12.0f), 3.0f, false);
            // Picked up first: until Nefarian attacks his tank it walks into
            // taunt range with a clear line (DragonPickupGoal).
            if (view.Nefarian->VictimGuid != context.Bot.Guid)
                return DragonPickupGoal(context, *view.Nefarian, NefarianMeleeReach);
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

// Heal and spell range is 40 yards; a spot keeps its targets within 36 so a
// tank's step or a dragon's turn does not put them out of reach.
constexpr float SightRangeYards = 36.0f;
// How far from its wanted spot a caster or healer that already serves its
// targets may stand before it walks (round 4).
constexpr float FormationKeepYards = 10.0f;

// Hunter shots and Auto Shot carry a 5 yd minimum range that the spell system
// extends by the melee range (Spell::GetMinMaxRange; the dragons' melee
// reaches above already hold the 1.5-yd player and the 4/3 allowance), as
// Chimaeron's round-2 fix does. Round 2 here: 577 min_range_required
// rejections from an 18-yd phase 3 formation slot (limit 27.83 on Nefarian).
constexpr float StandoffSpellMinRangeYards = 5.0f;
// A dragon's step inside its tank's arrival tolerance does not bring it
// inside the minimum range.
constexpr float StandoffMarginYards = 1.5f;

inline bool IsStandoffSpec(std::string_view spec)
{
    return spec == "beast_mastery_hunter" || spec == "marksmanship_hunter"
        || spec == "survival_hunter";
}

// The nearest a standoff member may stand to its dragon damage target
// (centre to centre), or 0 when neither applies.
inline float StandoffMinRange(MovementContext const& context, ObjectGuid damageTarget)
{
    if (!IsStandoffSpec(context.Bot.ClassSpec) || damageTarget.IsEmpty())
        return 0.0f;
    EncounterView const& view = context.View;
    if (view.Nefarian && view.Nefarian->Guid == damageTarget)
        return StandoffSpellMinRangeYards + NefarianMeleeReach + StandoffMarginYards;
    if (view.Onyxia && view.Onyxia->Guid == damageTarget)
        return StandoffSpellMinRangeYards + OnyxiaMeleeReach + StandoffMarginYards;
    return 0.0f;
}
static_assert(StandoffSpellMinRangeYards + NefarianMeleeReach + StandoffMarginYards + 3.0f
        < SightRangeYards, "a standoff band inside the sight range exists on Nefarian");

// Whom a ranged member or healer must see from its spot: its damage target,
// and for a healer the dragon tanks (`primaryOnly`: the tank of the dragon
// that fights now - Onyxia's before Nefarian lands, his after she dies).
inline std::vector<LocalPoint> SightTargets(MovementContext const& context,
    ObjectGuid damageTarget, bool healer, bool primaryOnly = false)
{
    std::vector<LocalPoint> targets;
    for (ActorSnapshot const* dragon : { context.View.Onyxia, context.View.Nefarian })
        if (dragon && dragon->Alive && dragon->Guid == damageTarget)
            targets.push_back(WorldToLocal(dragon->Position));
    if (!healer)
        return targets;
    ObjectGuid const primary = context.View.OnyxiaAlive() ? context.Plan.OnyxiaTank
        : context.Plan.NefarianTank;
    for (ObjectGuid tank : { context.Plan.OnyxiaTank, context.Plan.NefarianTank })
    {
        if (primaryOnly && tank != primary)
            continue;
        if (ActorSnapshot const* actor = context.Board.FindActor(tank);
            actor && actor->Alive && actor->Guid != context.Bot.Guid)
            targets.push_back(WorldToLocal(actor->Position));
    }
    return targets;
}

// A spot from which every target is in sight past the pillars and within
// SightRangeYards, and at least `minRangeYards` from the first (the damage
// target of a standoff member).
inline bool SpotServes(LocalPoint point, std::vector<LocalPoint> const& targets,
    float minRangeYards = 0.0f)
{
    if (minRangeYards > 0.0f && !targets.empty()
        && Distance(point, targets.front()) < minRangeYards)
        return false;
    return std::all_of(targets.begin(), targets.end(), [point](LocalPoint target)
        {
            return PillarSightClear(point, target)
                && Distance(point, target) <= SightRangeYards;
        });
}

// The first safe floor spot that serves its targets: rings of 0, 4, 8 and 12
// yards around `wanted`, then, stepping toward the targets (a tank leading
// Onyxia out to the ring), rings of 0 and 4 yards every 4 yards.
inline std::optional<LocalPoint> SightedSpot(MovementContext const& context,
    LocalPoint wanted, float bearing, std::vector<LocalPoint> const& targets,
    float minRangeYards = 0.0f)
{
    auto search = [&](LocalPoint centre, std::initializer_list<float> radii)
        -> std::optional<LocalPoint>
    {
        for (float radius : radii)
            for (float step : { 0.0f, 45.0f, -45.0f, 90.0f, -90.0f, 135.0f, -135.0f, 180.0f })
            {
                LocalPoint const point = Offset(centre, bearing + DegToRad(step), radius);
                if (FloorPointSafe(context, point, false)
                    && SpotServes(point, targets, minRangeYards))
                    return point;
                if (radius == 0.0f)
                    break;
            }
        return std::nullopt;
    };
    if (std::optional<LocalPoint> const near = search(wanted, { 0.0f, 4.0f, 8.0f, 12.0f }))
        return near;
    if (targets.empty())
        return std::nullopt;
    LocalPoint centroid{ 0.0f, 0.0f };
    for (LocalPoint target : targets)
        centroid = { centroid.X + target.X / float(targets.size()),
            centroid.Y + target.Y / float(targets.size()) };
    for (float along = 4.0f; along <= 48.0f; along += 4.0f)
        if (std::optional<LocalPoint> const point =
                search(StepToward(wanted, centroid, along), { 0.0f, 4.0f }))
            return point;
    return std::nullopt;
}

// The sighted formation goal of a caster or healer: every target first, the
// fighting dragon's tank alone when the two tanks are too far apart.
inline std::optional<SurfaceGoal> SightedFormationGoal(MovementContext const& context,
    LocalPoint wanted, float bearing, ObjectGuid damageTarget, MovePurpose purpose)
{
    ActorSnapshot const& bot = context.Bot;
    bool const healer = IsHealerSpec(bot.ClassSpec, bot.Role);
    for (bool primaryOnly : { false, true })
    {
        if (primaryOnly && !healer)
            break;
        std::vector<LocalPoint> const targets = SightTargets(context, damageTarget,
            healer, primaryOnly);
        // A standoff member's first sight target is its dragon (SightTargets
        // lists the damage target first): its spot keeps the minimum range,
        // and the search starts outside it.
        float const minRange = targets.empty() ? 0.0f
            : StandoffMinRange(context, damageTarget);
        LocalPoint start = wanted;
        if (minRange > 0.0f && Distance(start, targets.front()) < minRange + 1.5f)
        {
            LocalPoint const out{ start.X - targets.front().X, start.Y - targets.front().Y };
            float const heading = Length(out) < 0.1f ? bearing : AngleOf(out);
            start = Offset(targets.front(), heading, minRange + 1.5f);
        }
        // Round 4: a member standing on the platform floor near its spot,
        // where it is safe and serves every target, stays: the search's first
        // hit moves with every step of a tank or turn of a dragon, and each
        // walk takes the cast lanes (round 3: the healers cast almost only
        // instants while the Onyxia tank died).
        if (LocalPoint const self = BotLocal(context);
            Distance(self, start) <= FormationKeepYards && OnPlatformFloor(context)
            && FloorPointSafe(context, self, false) && SpotServes(self, targets, minRange))
        {
            SurfaceGoal goal = MakeGoal(context, purpose, Surface::Floor, self, 3.0f, false);
            goal.Sight = targets;
            goal.SightRangeYards = SightRangeYards;
            goal.SightMinRangeYards = minRange;
            return goal;
        }
        if (std::optional<LocalPoint> const point = SightedSpot(context, start, bearing,
                targets, minRange))
        {
            SurfaceGoal goal = MakeGoal(context, purpose, Surface::Floor, *point, 3.0f,
                false);
            goal.Sight = targets;
            goal.SightRangeYards = SightRangeYards;
            goal.SightMinRangeYards = minRange;
            return goal;
        }
    }
    return std::nullopt;
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
        if (!melee && phase != Phase::PreEngage)
            if (std::optional<SurfaceGoal> const sighted = SightedFormationGoal(context,
                    wanted, AngleOf({ wanted.X - anchor.X, wanted.Y - anchor.Y }),
                    damageTarget, MovePurpose::Formation))
                return sighted;
        std::optional<LocalPoint> moved;
        if (!moved)
            moved = SafeNear(context, wanted,
                AngleOf({ wanted.X - anchor.X, wanted.Y - anchor.Y }), 0.0f, false);
        if (!moved)
            moved = SafeNear(context, anchor, slotAngle, 7.0f, false);
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
    if (!melee && !OnPillarStructure(context))
        if (std::optional<SurfaceGoal> const sighted = SightedFormationGoal(context,
                wanted, wing, damageTarget, MovePurpose::Formation))
            return sighted;
    std::optional<LocalPoint> moved;
    if (!moved)
        moved = SafeNear(context, wanted, wing, 0.0f, false);
    if (!moved)
        moved = SafeNear(context, centre, wing, depth, false);
    if (!moved)
        return std::nullopt;
    MovePurpose const purpose = OnPillarStructure(context)
        ? MovePurpose::PillarDescent : MovePurpose::Formation;
    return MakeGoal(context, purpose, Surface::Floor, *moved, 3.0f,
        purpose == MovePurpose::PillarDescent);
}
}

#endif
