#ifndef TRINITY_BOT_ADAPTIVE_NEFARIAN_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_NEFARIAN_STRATEGY_H

// Adaptive strategy for Nefarian's End (Blackwing Descent). It composes the
// observation (BotNefarianFacts.h), the capability duty plan
// (BotNefarianDutyPlan.h), the arena layout (BotNefarianLayout.h), per-bot
// tactics (BotNefarianTactics.h) and movement goals (BotNefarian*Movement.h)
// into one plan per bot and decision slice. It submits typed native requests
// only: no teleport, aura, damage or forced target is ever produced.
//
// The dispatch (KernelPreparation, BotWorldPopulationMgrNefarianCandidates.cpp)
// reads OwnsNode, DamageTarget, InterruptTarget, Movement (a Walk leg of at
// most 9.5 yards on the platform, BotNefarianPath.h, or a descent stage),
// Actions, SuppressOffense, Blocked and MovementHold. Ascent (Float, Swim,
// Hop, Board; BotNefarianAscent.h) is turned into native requests by patch
// .git/round6_patches/nefarian/N2 once package T's stages (N1) exist.

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianPhaseMovement.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianTankSelfCare.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianSurfaceIntent.h"
#include <cmath>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace BotEncounter
{
struct AdaptiveNefarianPlan
{
    bool OwnsNode = false;
    Nefarian::Phase Phase = Nefarian::Phase::Inactive;
    std::string_view Duty;
    ObjectGuid DamageTarget;
    ObjectGuid InterruptTarget;
    bool SuppressOffense = false;
    std::string_view SuppressReason;
    std::optional<BotNativeAction::Candidate> Movement;
    // The standing spot the legs lead to, and the leg submitted now.
    std::optional<Nefarian::SurfaceGoal> MovementSurface;
    std::optional<Nefarian::PathLeg> MovementLeg;
    // Why no leg was submitted although a goal exists (typed, for the trace).
    std::string_view MovementHold;
    // A capability the encounter needs and the runtime lacks, for example
    // pillar_ascent_unsupported in phase 2 (see the dossier, section 7).
    std::string_view Blocked;
    std::vector<BotNativeAction::Candidate> Actions;
    // The phase 2 swim-and-hop step of this decision (Movement stays empty).
    std::optional<Nefarian::AscentStep> Ascent;
};

class AdaptiveNefarianStrategy
{
public:
    static constexpr uint32 NefarianEntry = Nefarian::NefarianEntry;
    static constexpr uint32 OnyxiaEntry = Nefarian::OnyxiaEntry;
    static constexpr uint32 PrototypeEntry = Nefarian::PrototypeEntry;
    static constexpr uint32 BoneEntry = Nefarian::BoneWarriorEntry;
    static constexpr uint32 FlashpointEntry = Nefarian::FlashpointEntry;
    static constexpr uint32 FireEntry = Nefarian::ShadowblazeEntry;

    AdaptiveNefarianPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role, Nefarian::NativeFacts const* facts = nullptr) const
    {
        using namespace Nefarian;
        AdaptiveNefarianPlan plan;
        EncounterView const view = ObserveEncounter(board);
        if (!view.Owns())
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive || bot->Kind != ActorKind::Player)
            return plan;
        plan.OwnsNode = true;
        plan.Phase = view.CurrentPhase;
        plan.Blocked = CapabilityBlocker(view.CurrentPhase, facts);

        DutyPlan const duty = BuildNefarianDutyPlan(board);
        ArenaLayout const layout = BuildArenaLayout(duty);
        plan.Duty = DutyLabel(duty, *bot);
        ChooseDamageTarget(plan, board, view, duty, *bot, role, facts);
        ChooseActions(plan, board, view, duty, *bot, facts);
        ChooseMovement(plan, MovementContext{ board, view, duty, layout, *bot,
            facts });
        return plan;
    }

private:
    static std::string_view DutyLabel(Nefarian::DutyPlan const& duty,
        ActorSnapshot const& bot)
    {
        if (bot.Guid == duty.NefarianTank)
            return "nefarian_tank";
        if (bot.Guid == duty.OnyxiaTank)
            return "onyxia_tank";
        int const pillar = duty.PillarOf(bot.Guid);
        if (pillar >= 0)
        {
            Nefarian::PillarTeam const& team = duty.Pillars[pillar];
            if (bot.Guid == team.PrimaryInterrupter)
                return "pillar_interrupt";
            if (bot.Guid == team.Healer)
                return "pillar_healer";
        }
        if (bot.Guid == duty.Shackler)
            return "bone_shackler";
        if (bot.Guid == duty.WarriorHandler)
            return "bone_warrior_handler";
        return "raid";
    }

    static bool IsHealer(ActorSnapshot const& bot, std::string_view role)
    {
        return Nefarian::IsHealerSpec(bot.ClassSpec, role);
    }

    static void Suppress(AdaptiveNefarianPlan& plan, std::string_view reason)
    {
        plan.SuppressOffense = true;
        plan.SuppressReason = reason;
    }

    static void ChooseDamageTarget(AdaptiveNefarianPlan& plan,
        Blackboard const& board, Nefarian::EncounterView const& view,
        Nefarian::DutyPlan const& duty, ActorSnapshot const& bot,
        std::string_view role, Nefarian::NativeFacts const* facts)
    {
        using namespace Nefarian;
        // The Onyxia tank now: hers, or the Blood DK when hers is dead or
        // missing (round 7: nobody pulled with the Feral dead).
        ObjectGuid const onyxiaPuller = OnyxiaTankNow(board, duty);
        bool const onyxiaTank = ActsAsOnyxiaTank(board, view, duty, bot.Guid);
        bool const nefarianTank = bot.Guid == duty.NefarianTank && !onyxiaTank;
        bool const healer = IsHealer(bot, role) && bot.Guid != duty.OnyxiaTank
            && bot.Guid != duty.NefarianTank;
        switch (view.CurrentPhase)
        {
            case Phase::PreEngage:
                if (onyxiaTank && view.OnyxiaAlive() && view.Onyxia->Attackable
                    && !HasAura(*view.Onyxia, SpellOnyxiaFeignDeath))
                    plan.DamageTarget = view.Onyxia->Guid;
                else if (!healer && onyxiaPuller.IsEmpty() && view.OnyxiaAlive()
                    && view.Onyxia->Attackable
                    && !HasAura(*view.Onyxia, SpellOnyxiaFeignDeath))
                    // No tank left to pull: nobody to wait for.
                    plan.DamageTarget = view.Onyxia->Guid;
                else if (!healer)
                    Suppress(plan, HoldFirePreEngage);
                return;
            case Phase::OnyxiaOnly:
            case Phase::BothDragons:
                if (onyxiaTank)
                    plan.DamageTarget = view.Onyxia->Guid;
                else if (nefarianTank)
                {
                    if (view.NefarianLanded())
                        plan.DamageTarget = view.Nefarian->Guid;
                    else
                        Suppress(plan, "nefarian_airborne_tank_hold");
                }
                else if (!healer)
                {
                    if (OnyxiaHeldByTank(board, view, duty, facts))
                        plan.DamageTarget = PhaseOneDamageTarget(view,
                            PhaseOnePacingFor(facts));
                    else
                        Suppress(plan, HoldFireForOnyxiaTank);
                }
                return;
            case Phase::PlatformAscent:
            case Phase::PlatformHold:
            case Phase::PlatformReturn:
                if (healer)
                    return;
                if (ActorSnapshot const* prototype = PillarPrototype(view,
                        duty.PillarOf(bot.Guid)))
                    plan.DamageTarget = prototype->Guid;
                else if (ActorSnapshot const* nearest = NearestPrototype(view,
                        bot))
                    plan.DamageTarget = nearest->Guid;
                else
                    // Nefarian's Electrocute fires at every 10% he loses.
                    Suppress(plan, "nefarian_platform_no_prototype");
                return;
            case Phase::NefarianLanding:
                if (!healer)
                    Suppress(plan, "nefarian_landing");
                return;
            case Phase::NefarianGround:
                if (healer)
                    return;
                if (bot.Guid == duty.WarriorHandler)
                {
                    if (ActorSnapshot const* warrior = LooseWarrior(board, view,
                            duty, bot, facts))
                    {
                        plan.DamageTarget = warrior->Guid;
                        return;
                    }
                    // Only held warriors left: leave them held and stay with
                    // them rather than walking to Nefarian.
                    if (AnyActiveWarrior(view))
                    {
                        Suppress(plan, "bone_warrior_handler_holds_rooted");
                        return;
                    }
                }
                if (view.Nefarian && view.Nefarian->Alive)
                    plan.DamageTarget = view.Nefarian->Guid;
                return;
            default:
                return;
        }
    }

    static ActorSnapshot const* NearestPrototype(
        Nefarian::EncounterView const& view, ActorSnapshot const& bot)
    {
        ActorSnapshot const* best = nullptr;
        for (ActorSnapshot const* prototype : view.Prototypes)
            if (!best || Nefarian::Distance3(prototype->Position, bot.Position)
                    < Nefarian::Distance3(best->Position, bot.Position))
                best = prototype;
        return best;
    }

    // The warrior the handler (warden) should hold now: the nearest active
    // warrior that is not held (a stun, root or shackle breaks on damage), is
    // not the shackler's candidate and is not already on the warden - first
    // any in or near Nefarian's front (on his tank, say), then any other. When
    // only warriors already on the warden remain, the nearest unheld one of
    // those.
    static ActorSnapshot const* LooseWarrior(Blackboard const& board,
        Nefarian::EncounterView const& view, Nefarian::DutyPlan const& duty,
        ActorSnapshot const& warden, Nefarian::NativeFacts const* facts)
    {
        using namespace Nefarian;
        std::vector<ActorSnapshot const*> active;
        for (ActorSnapshot const* warrior : view.BoneWarriors)
            if (IsActiveBoneWarrior(*warrior))
                active.push_back(warrior);
        ActorSnapshot const* shackle = ShackleCandidate(board, active, duty, facts);
        auto rank = [&](ActorSnapshot const* warrior)
        {
            bool const inFront = !WarriorPointSafe(view, WorldToLocal(warrior->Position));
            bool const onWarden = warrior->VictimGuid == warden.Guid;
            return (onWarden ? 2 : 0) + (inFront ? 0 : 1);
        };
        ActorSnapshot const* best = nullptr;
        for (ActorSnapshot const* warrior : active)
        {
            if (warrior == shackle || IsBoneWarriorHeld(*warrior))
                continue;
            if (!best || rank(warrior) < rank(best)
                || (rank(warrior) == rank(best)
                    && Distance3(warrior->Position, warden.Position)
                        < Distance3(best->Position, warden.Position)))
                best = warrior;
        }
        return best;
    }

    static bool AnyActiveWarrior(Nefarian::EncounterView const& view)
    {
        return std::any_of(view.BoneWarriors.begin(), view.BoneWarriors.end(),
            [](ActorSnapshot const* warrior) { return Nefarian::IsActiveBoneWarrior(*warrior); });
    }

    static BotNativeAction::Candidate Cast(Blackboard const& board,
        std::string_view mechanic, ObjectGuid target, uint32 spellId,
        BotActionArbitration::Priority priority, float utility)
    {
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_nefarian";
        candidate.Id.Mechanic = std::string(mechanic);
        candidate.Id.Actor = target;
        candidate.Id.EventGeneration = spellId;
        candidate.ActionPriority = priority;
        candidate.Utility = utility;
        candidate.ExpiresAtMs = board.ObservedAtMs + 600;
        candidate.Action = BotNativeAction::CastSpell{ target, spellId };
        return candidate;
    }

    static void ChooseActions(AdaptiveNefarianPlan& plan, Blackboard const& board,
        Nefarian::EncounterView const& view, Nefarian::DutyPlan const& duty,
        ActorSnapshot const& bot, Nefarian::NativeFacts const* facts)
    {
        using namespace Nefarian;
        using BotActionArbitration::Priority;
        Phase const phase = view.CurrentPhase;

        if (PhaseWantsPillar(phase))
        {
            InterruptDecision const interrupt = DecideBlastNovaInterrupt(board,
                view, duty, bot, facts);
            if (!interrupt.Target.IsEmpty())
            {
                plan.InterruptTarget = interrupt.Target;
                plan.Actions.push_back(Cast(board, interrupt.Reason,
                    interrupt.Target, interrupt.SpellId, Priority::Interrupt,
                    100.0f));
                return;
            }
            // A crossing helper's magma defensive (round 8), once in the lava.
            {
                ArenaLayout const layout = BuildArenaLayout(duty);
                MovementContext const context{ board, view, duty, layout, bot, facts };
                if (CrossingDefensiveDue(context, CrossingFor(context)))
                    plan.Actions.push_back(Cast(board, "pillar_crossing_defensive", bot.Guid,
                        CrossingDefensiveFor(bot.ClassSpec), Priority::Survival, 96.0f));
            }
            // The tanks' self-care on the healerless pillar (round 8).
            for (HealDecision const& self : DecideTankSelfCare(view, duty, bot, facts))
            {
                bool const enrage = self.SpellId == SpellEnrage;
                plan.Actions.push_back(Cast(board, self.Reason, self.Target, self.SpellId,
                    self.SpellId == SpellDeathStrike ? Priority::Mechanic
                        : enrage ? Priority::Support : Priority::Survival,
                    enrage ? 82.0f : 95.0f));
            }
            HealDecision const care = DecidePreAscentCare(board, view, duty, bot, facts);
            if (!care.Target.IsEmpty())
                plan.Actions.push_back(Cast(board, care.Reason, care.Target,
                    care.SpellId, Priority::Support, 85.0f));
            HealDecision const heal = DecideOffHeal(board, view, duty, bot, facts);
            if (!heal.Target.IsEmpty())
                plan.Actions.push_back(Cast(board, heal.Reason, heal.Target,
                    heal.SpellId, Priority::Support, 80.0f));
            return;
        }

        TauntCapability const taunt = TauntFor(bot.ClassSpec);
        auto tauntIfLoose = [&](ActorSnapshot const* subject,
            std::string_view mechanic)
        {
            if (taunt.Known() && (!facts || facts->SpellUsable(bot.Guid, taunt.SpellId))
                && subject && subject->Alive && subject->InCombat
                && !subject->VictimGuid.IsEmpty()
                && subject->VictimGuid != bot.Guid)
                plan.Actions.push_back(Cast(board, mechanic, subject->Guid,
                    taunt.SpellId, Priority::ThreatControl, 90.0f));
        };
        bool const holdsOnyxia = ActsAsOnyxiaTank(board, view, duty, bot.Guid);
        if (holdsOnyxia)
            tauntIfLoose(view.Onyxia, "onyxia_taunt");
        // A Blood DK standing in for the dead Feral keeps Onyxia until she
        // dies and only then taunts Nefarian.
        if (bot.Guid == duty.NefarianTank && view.NefarianLanded() && !holdsOnyxia)
            tauntIfLoose(view.Nefarian, "nefarian_taunt");
        if (bot.Guid == duty.WarriorHandler && phase == Phase::NefarianGround)
            if (!plan.DamageTarget.IsEmpty() && plan.DamageTarget
                != (view.Nefarian ? view.Nefarian->Guid : ObjectGuid()))
                for (ActorSnapshot const* warrior : view.BoneWarriors)
                    if (warrior->Guid == plan.DamageTarget)
                        tauntIfLoose(warrior, "bone_warrior_taunt");

        if (phase == Phase::NefarianGround && DecideNaturesGrasp(view, duty, bot, facts))
            plan.Actions.push_back(Cast(board, "bone_warrior_natures_grasp", bot.Guid,
                WarriorRootFor(bot.ClassSpec), Priority::Support, 75.0f));
        if (phase == Phase::PreEngage)
            return;
        ControlDecision const shackle = DecideShackle(board, view, duty, bot, facts);
        if (!shackle.Target.IsEmpty())
            plan.Actions.push_back(Cast(board, shackle.Reason, shackle.Target,
                shackle.SpellId, Priority::Support, 70.0f));
    }

    static uint64 LegGeneration(Nefarian::SurfaceGoal const& goal,
        Nefarian::PathLeg const& leg)
    {
        uint64 const x = uint64(uint16(int16(std::lround(leg.To.X * 2.0f))));
        uint64 const y = uint64(uint16(int16(std::lround(leg.To.Y * 2.0f))));
        return (uint64(goal.Purpose) << 40) | (uint64(goal.Target) << 32)
            | (x << 16) | y;
    }

    static bool Stunned(ActorSnapshot const& bot)
    {
        return Nefarian::HasAnyAura(bot, { 77827, 94128, 94129, 94130 });
    }

    // Phase 3 descent (BotNefarianAscent.h): rim walk, step-off, fall, land.
    static void ChooseDescent(AdaptiveNefarianPlan& plan,
        Nefarian::MovementContext const& context)
    {
        using namespace Nefarian;
        DescentDecision const descent = PlanPillarDescent(context,
            context.Plan.SlotOf(context.Bot.Guid));
        if (!descent.Hold.empty())
            plan.MovementHold = descent.Hold;
        if (!descent.Move)
            return;
        if (Stunned(context.Bot)
            && descent.Move->Kind != BotNativeAction::TransportSurfaceMove::Stage::Land
            && descent.Move->Kind != BotNativeAction::TransportSurfaceMove::Stage::Fall)
        {
            plan.MovementHold = "nefarian_movement_stunned";
            return;
        }
        SurfaceGoal goal = MakeGoal(context, MovePurpose::PillarDescent,
            Surface::Floor, BotLocal(context), 3.0f, true);
        plan.MovementSurface = goal;
        BotNativeAction::Candidate movement;
        movement.Id.ScopeKey = context.Board.CurrentScope.Key();
        movement.Id.Strategy = "adaptive_nefarian";
        movement.Id.Mechanic = std::string(descent.Mechanic);
        movement.Id.Actor = context.Bot.Guid;
        movement.Id.EventGeneration = uint64(descent.Move->Kind) + 1;
        movement.ActionPriority = BotActionArbitration::Priority::Survival;
        movement.Utility = 470.0f;
        movement.ExpiresAtMs = context.Board.ObservedAtMs + 1000;
        movement.Action = *descent.Move;
        plan.Movement = std::move(movement);
    }

    // A walk already running that would now lead a following warrior deeper
    // into Nefarian's front (he turned, or the warrior did) is validated
    // before any other rule: unless this decision replaces it with a lawful
    // leg, the plan holds the bot (WarriorStopHold: the submission clears the
    // native chase or path, stops the spline and renews a Hazard movement
    // lease, so combat range movement cannot restart it).
    // The crossing helper's departure (BotNefarianCrossing.h): rim, step off
    // and fall, each a survival-lane surface request like the descent's.
    static void ChooseCrossingDeparture(AdaptiveNefarianPlan& plan,
        Nefarian::MovementContext const& context, Nefarian::CrossingAssignment const& crossing)
    {
        using namespace Nefarian;
        DescentDecision const departure = PlanCrossingDeparture(context,
            context.Plan.PillarOf(context.Bot.Guid), crossing.Pillar);
        if (!departure.Hold.empty())
            plan.MovementHold = departure.Hold;
        if (!departure.Move)
            return;
        if (Stunned(context.Bot))
        {
            plan.MovementHold = "nefarian_movement_stunned";
            return;
        }
        plan.MovementSurface = MakeGoal(context, MovePurpose::PillarAscent,
            Surface::Floor, BotLocal(context), 3.0f, true, crossing.Pillar);
        BotNativeAction::Candidate movement;
        movement.Id.ScopeKey = context.Board.CurrentScope.Key();
        movement.Id.Strategy = "adaptive_nefarian";
        movement.Id.Mechanic = std::string(departure.Mechanic);
        movement.Id.Actor = context.Bot.Guid;
        movement.Id.EventGeneration = uint64(departure.Move->Kind) + 101;
        movement.ActionPriority = BotActionArbitration::Priority::Mechanic;
        movement.Utility = 300.0f;
        movement.ExpiresAtMs = context.Board.ObservedAtMs + 1000;
        movement.Action = *departure.Move;
        plan.Movement = std::move(movement);
    }

    static void ChooseMovement(AdaptiveNefarianPlan& plan,
        Nefarian::MovementContext const& context)
    {
        using namespace Nefarian;
        bool const runningUnsafe = RunningWalkUnsafe(context);
        ChooseMovementLeg(plan, context);
        // Held (and the hold renewed every decision) for as long as no lawful
        // leg exists: a running walk that turned unsafe, a leg the warrior
        // rule refused, or the handler cornered where it stands (moving or
        // not). A lawful escape or leg releases it; a safe running leg kept
        // as nefarian_leg_in_flight is never held.
        bool const cornered = plan.MovementHold.empty() && plan.MovementSurface
            && plan.MovementSurface->WarriorHold;
        if (!plan.Movement && !plan.Ascent
            && (runningUnsafe || cornered
                || plan.MovementHold == "nefarian_warrior_path_unsafe"))
            plan.MovementHold = WarriorStopHold;
        // Round 7 (first live attempt): on the raised platform every step is
        // this plan's. No native combat range, chase or route walk (static
        // navmesh paths, which do not know the platform) may walk a bot off
        // the transport into the magma bowl under it:
        // - a leg of this plan in flight keeps its lease (LegInFlightHold);
        // - otherwise the platform hold is always proposed: alone when there
        //   is no leg (or only a diagnostic hold), and beside a proposed leg
        //   as the fallback that claims the movement lane when native
        //   admission rejects the leg. The warrior stop keeps precedence.
        // The pickup's budget spent: typed, for the trace and the status.
        if (!plan.Movement && plan.MovementHold.empty() && PickupExhausted(context))
            plan.MovementHold = PickupExhaustedHold;
        if (!plan.Ascent && PlatformHoldApplies(context)
            && plan.MovementHold != WarriorStopHold
            && plan.MovementHold != LegInFlightHold)
            plan.MovementHold = PlatformHoldWith(plan.MovementHold);
    }

    // The pickup's budget spent for the dragon this tank picks up (Onyxia,
    // or Nefarian once he has landed).
    static bool PickupExhausted(Nefarian::MovementContext const& context)
    {
        using namespace Nefarian;
        if (!context.Facts)
            return false;
        EncounterView const& view = context.View;
        if (ActsAsOnyxiaTank(context.Board, view, context.Plan, context.Bot.Guid))
            return view.Onyxia->VictimGuid != context.Bot.Guid
                && context.Facts->PickupExhausted(context.Bot.Guid, view.Onyxia->Guid);
        return context.Bot.Guid == context.Plan.NefarianTank && view.NefarianLanded()
            && view.Nefarian->VictimGuid != context.Bot.Guid
            && context.Facts->PickupExhausted(context.Bot.Guid, view.Nefarian->Guid);
    }

    static bool PlatformHoldApplies(Nefarian::MovementContext const& context)
    {
        using namespace Nefarian;
        // From the pull (the pull itself and the route's walks onto the
        // platform stay native), through phase 3 on the floor.
        switch (context.View.CurrentPhase)
        {
            case Phase::OnyxiaOnly:
            case Phase::BothDragons:
            case Phase::NefarianLanding:
            case Phase::NefarianGround:
                break;
            default:
                return false;
        }
        if (OnPillarStructure(context) || !OnPlatformFloor(context))
            return false;
        if (context.Facts)
            if (FallState const* fall = context.Facts->FindFall(context.Bot.Guid);
                fall && (fall->Falling || fall->LandingPending))
                return false;
        return true;
    }

    static bool RunningWalkUnsafe(Nefarian::MovementContext const& context)
    {
        using namespace Nefarian;
        if (!context.Facts || !LeadsWarriors(context) || OnPillarStructure(context))
            return false;
        if (FallState const* fall = context.Facts->FindFall(context.Bot.Guid);
            fall && (fall->Falling || fall->LandingPending))
            return false;
        MovementState const* motion = context.Facts->FindMotion(context.Bot.Guid);
        return motion && motion->Moving
            && !WarriorPathNoDeeper(context.View, BotLocal(context),
                WorldToLocal(motion->Destination));
    }

    static void ChooseMovementLeg(AdaptiveNefarianPlan& plan,
        Nefarian::MovementContext const& context)
    {
        using namespace Nefarian;
        using BotActionArbitration::Priority;
        Phase const phase = context.View.CurrentPhase;
        bool const fightOnFloor = !PhaseWantsPillar(phase);

        // Off the pillar before Nefarian lands (Shadow of Cowardice), and a
        // fall already under way is always carried through to its landing.
        if (fightOnFloor || context.Facts)
        {
            FallState const* fall = context.Facts
                ? context.Facts->FindFall(context.Bot.Guid) : nullptr;
            bool const falling = fall && (fall->Falling || fall->LandingPending);
            if (falling || (fightOnFloor && OnPillarStructure(context)))
            {
                ChooseDescent(plan, context);
                return;
            }
        }

        // Cross-pillar help (round 8): a helper leaves its pillar top.
        CrossingAssignment const crossing = fightOnFloor ? CrossingAssignment{}
            : CrossingFor(context);
        if (crossing.Departing && OnPillarStructure(context))
        {
            ChooseCrossingDeparture(plan, context, crossing);
            return;
        }

        std::optional<SurfaceGoal> goal;
        Priority priority = Priority::CombatMovement;
        float utility = 120.0f;
        auto take = [&](std::optional<SurfaceGoal> candidate, Priority urgent,
            float urgentUtility, Priority normal, float normalUtility)
        {
            if (goal || !candidate)
                return;
            goal = candidate;
            priority = candidate->Urgent ? urgent : normal;
            utility = candidate->Urgent ? urgentUtility : normalUtility;
        };

        if (fightOnFloor)
            take(FireEscape(context), Priority::Survival, 500.0f,
                Priority::Survival, 500.0f);
        take(PillarGoal(context), Priority::Survival, 450.0f, Priority::Mechanic,
            280.0f);
        if (fightOnFloor)
        {
            take(WarriorEscape(context), Priority::Survival, 490.0f,
                Priority::Survival, 490.0f);
            take(BreathEscape(context), Priority::Survival, 480.0f,
                Priority::Survival, 480.0f);
            take(KiteGoal(context), Priority::Survival, 420.0f,
                Priority::Survival, 420.0f);
            take(TankGoal(context), Priority::Mechanic, 350.0f,
                Priority::Mechanic, 300.0f);
            take(FormationGoal(context, plan.DamageTarget), Priority::Mechanic,
                320.0f, Priority::CombatMovement, 120.0f);
        }
        if (!goal)
            return;
        plan.MovementSurface = goal;

        LocalPoint const self = BotLocal(context);
        bool const onPillar = OnPillarStructure(context);
        if (context.View.Elevator.Guid.IsEmpty())
        {
            plan.MovementHold = "nefarian_elevator_unobserved";
            return;
        }
        // Phase 2: the swim-and-hop ascent owns every step off the floor.
        if (!fightOnFloor && goal->Pillar >= 0 && !onPillar
            && AscentSupported(context.Facts))
        {
            AscentDecision const ascent = PlanPillarAscent(context, goal->Pillar,
                crossing.Pillar == goal->Pillar ? crossing.Slot
                    : context.Plan.SlotOf(context.Bot.Guid));
            if (ascent.Step)
            {
                plan.Ascent = ascent.Step;
                return;
            }
            if (!ascent.Hold.empty())
            {
                plan.MovementHold = ascent.Hold;
                return;
            }
        }
        // Arrived - unless a caster or healer would stand where a pillar
        // hides a target or a target is out of range, or a non-tank would
        // stand in a dragon's core: then it finishes the leg.
        bool const selfServes = goal->Sight.empty() || SpotServes(self, goal->Sight);
        bool const selfClear = !InDragonCore(context, self);
        if (goal->Target == Surface::Floor
            && Distance(self, goal->Local) <= goal->ArrivalToleranceYards
            && selfServes && selfClear)
            return;
        if (!onPillar && !OnPlatformFloor(context))
        {
            plan.MovementHold = "nefarian_not_on_platform";
            return;
        }
        if (Stunned(context.Bot))
        {
            plan.MovementHold = "nefarian_movement_stunned";
            return;
        }

        std::optional<PathLeg> leg;
        if (goal->Target == Surface::PillarTop)
        {
            // On the pillar (after the hop): a short walk up to the slot.
            if (!onPillar || Distance(self, goal->Local) <= 0.75f)
                return;
            PathLeg top;
            top.To = goal->Local;
            top.LocalZ = goal->LocalZ;
            top.Kind = "pillar_top";
            leg = top;
        }
        else
            leg = NextLeg(self, goal->Local);
        // A correction under NextLeg's 1-yard arrival: a checked short leg
        // when the spot the bot stands on does not serve (sight, range or a
        // dragon's core).
        if (!leg && goal->Target == Surface::Floor && (!selfServes || !selfClear)
            && Distance(self, goal->Local) > 0.05f && SegmentWalkable(self, goal->Local))
        {
            PathLeg correction;
            correction.To = goal->Local;
            correction.LocalZ = FloorLocalZAt(goal->Local);
            correction.Kind = "short_correction";
            leg = correction;
        }
        if (!leg)
        {
            plan.MovementHold = "nefarian_no_surface_path";
            return;
        }
        // The leg itself (it may turn at a waypoint) never walks a following
        // warrior past Nefarian's front.
        if (!onPillar && LeadsWarriors(context)
            && !WarriorPathNoDeeper(context.View, self, leg->To))
        {
            plan.MovementHold = "nefarian_warrior_path_unsafe";
            return;
        }
        plan.MovementLeg = leg;
        Vector3 const legWorld = LocalToWorld(leg->To, leg->LocalZ,
            context.View.Elevator.OriginZ);

        // A walk already running the same way is kept until it ends: the
        // planned leg's end slides forward as the bot walks, so compare the
        // direction (and that the running segment is still lawful), not the
        // end point. A relaunch would claim movement, GCD and cast again and
        // re-run the executor's collision probe every decision.
        if (context.Facts)
            if (MovementState const* motion =
                    context.Facts->FindMotion(context.Bot.Guid);
                motion && motion->Moving)
            {
                LocalPoint const running = WorldToLocal(motion->Destination);
                float const runningLength = Distance(self, running);
                float const plannedLength = Distance(self, leg->To);
                // A running walk that would lead a following warrior into
                // Nefarian's front is never kept: the planned leg replaces it.
                if (runningLength >= 0.5f && plannedLength >= 0.5f
                    && runningLength <= MaxLegYards + 0.5f
                    && SegmentWalkable(self, running)
                    && (!LeadsWarriors(context)
                        || WarriorPathNoDeeper(context.View, self, running))
                    && Distance(running, leg->To) <= std::max(1.0f, plannedLength)
                    && AngularGap(AngleOf({ running.X - self.X, running.Y - self.Y }),
                        AngleOf({ leg->To.X - self.X, leg->To.Y - self.Y }))
                        <= DegToRad(10.0f))
                {
                    plan.MovementHold = "nefarian_leg_in_flight";
                    return;
                }
            }

        // Walks claim movement, GCD and cast: a formation spot far away is
        // mechanic work, a small correction yields to the rotation.
        if (goal->Purpose == MovePurpose::Formation
            && Distance(self, goal->Local) > 5.0f)
        {
            priority = Priority::Mechanic;
            utility = 200.0f;
        }

        BotNativeAction::Candidate movement;
        movement.Id.ScopeKey = context.Board.CurrentScope.Key();
        movement.Id.Strategy = "adaptive_nefarian";
        movement.Id.Mechanic = std::string(MovePurposeName(goal->Purpose));
        movement.Id.Actor = context.Bot.Guid;
        movement.Id.EventGeneration = LegGeneration(*goal, *leg);
        movement.ActionPriority = priority;
        movement.Utility = utility;
        movement.ExpiresAtMs = context.Board.ObservedAtMs + 1000;
        movement.Action = ToTransportSurfaceMove(context.View.Elevator.Guid,
            legWorld, leg->FloorToleranceYards);
        plan.Movement = std::move(movement);
    }
};

// Status receipt: the duty plan, phase and capability blocker a snapshot
// resolves to, or {"applies":false} outside the encounter node. "blocked" is
// empty or a typed capability blocker (pillar_ascent_unsupported).
inline std::string BuildNefarianDutyPlanStatusJson(Blackboard const* board,
    Nefarian::NativeFacts const* facts = nullptr)
{
    if (!board)
        return "{\"applies\":false}";
    Nefarian::EncounterView const view = Nefarian::ObserveEncounter(*board);
    if (!view.Owns())
        return "{\"applies\":false}";
    std::string json = Nefarian::NefarianDutyPlanJson(
        Nefarian::BuildNefarianDutyPlan(*board));
    json.pop_back();
    std::string_view const blocked =
        Nefarian::CapabilityBlocker(view.CurrentPhase, facts);
    json += ",\"phase\":\"" + std::string(Nefarian::PhaseName(view.CurrentPhase))
        + "\",\"blocked\":\"" + std::string(blocked)
        + "\",\"elevator_origin_z\":"
        + std::to_string(view.Elevator.Observed ? view.Elevator.OriginZ : 0.0f)
        + "}";
    return json;
}
}

#endif
