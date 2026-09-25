#ifndef TRINITY_BOT_ADAPTIVE_NEFARIAN_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_NEFARIAN_STRATEGY_H

// Adaptive strategy for Nefarian's End (Blackwing Descent). It composes the
// observation (BotNefarianFacts.h), the capability duty plan
// (BotNefarianDutyPlan.h), the arena layout (BotNefarianLayout.h), per-bot
// tactics (BotNefarianTactics.h) and movement goals (BotNefarian*Movement.h)
// into one plan per bot and decision slice. It submits typed native requests
// only: no teleport, aura, damage or forced target is ever produced.
//
// The existing dispatch reads OwnsNode, DamageTarget, InterruptTarget and
// Movement: one TransportSurfaceMove Walk leg of at most 9.5 yards on the
// platform (BotNefarianPath.h). Actions, SuppressOffense, Blocked and
// MovementHold need the dispatch patches in .git/round2_patches/nefarian/.

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianPhaseMovement.h"
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
        ChooseDamageTarget(plan, board, view, duty, *bot, role);
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
        std::string_view role)
    {
        using namespace Nefarian;
        bool const onyxiaTank = bot.Guid == duty.OnyxiaTank;
        bool const nefarianTank = bot.Guid == duty.NefarianTank;
        bool const healer = IsHealer(bot, role) && !onyxiaTank && !nefarianTank;
        switch (view.CurrentPhase)
        {
            case Phase::PreEngage:
                if (onyxiaTank && view.OnyxiaAlive() && view.Onyxia->Attackable
                    && !HasAura(*view.Onyxia, SpellOnyxiaFeignDeath))
                    plan.DamageTarget = view.Onyxia->Guid;
                else if (!healer)
                    Suppress(plan, "nefarian_pre_engage_hold");
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
                    plan.DamageTarget = PhaseOneDamageTarget(view);
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
                if (onyxiaTank)
                    if (ActorSnapshot const* warrior = LooseWarrior(board, view,
                            duty, bot))
                    {
                        plan.DamageTarget = warrior->Guid;
                        return;
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

    // The nearest active, unheld warrior attacking a non-tank (or the warden).
    // The shackler's candidate is left alone: any damage breaks the shackle.
    static ActorSnapshot const* LooseWarrior(Blackboard const& board,
        Nefarian::EncounterView const& view, Nefarian::DutyPlan const& duty,
        ActorSnapshot const& warden)
    {
        using namespace Nefarian;
        std::vector<ActorSnapshot const*> active;
        for (ActorSnapshot const* warrior : view.BoneWarriors)
            if (IsActiveBoneWarrior(*warrior))
                active.push_back(warrior);
        ActorSnapshot const* shackle = ShackleCandidate(board, active, duty);
        ActorSnapshot const* best = nullptr;
        float bestDistance = 0.0f;
        for (ActorSnapshot const* warrior : active)
        {
            if (warrior == shackle || IsBoneWarriorHeld(*warrior))
                continue;
            if (duty.IsTank(warrior->VictimGuid)
                && warrior->VictimGuid != warden.Guid)
                continue;
            float const distance = Distance3(warrior->Position, warden.Position);
            if (!best || distance < bestDistance)
            {
                best = warrior;
                bestDistance = distance;
            }
        }
        return best;
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
            }
            return;
        }

        TauntCapability const taunt = TauntFor(bot.ClassSpec);
        auto tauntIfLoose = [&](ActorSnapshot const* subject,
            std::string_view mechanic)
        {
            if (taunt.Known() && subject && subject->Alive && subject->InCombat
                && !subject->VictimGuid.IsEmpty()
                && subject->VictimGuid != bot.Guid)
                plan.Actions.push_back(Cast(board, mechanic, subject->Guid,
                    taunt.SpellId, Priority::ThreatControl, 90.0f));
        };
        if (bot.Guid == duty.OnyxiaTank && view.OnyxiaAlive())
            tauntIfLoose(view.Onyxia, "onyxia_taunt");
        if (bot.Guid == duty.NefarianTank && view.NefarianLanded())
            tauntIfLoose(view.Nefarian, "nefarian_taunt");
        if (bot.Guid == duty.OnyxiaTank && phase == Phase::NefarianGround)
            if (!plan.DamageTarget.IsEmpty() && plan.DamageTarget
                != (view.Nefarian ? view.Nefarian->Guid : ObjectGuid()))
                for (ActorSnapshot const* warrior : view.BoneWarriors)
                    if (warrior->Guid == plan.DamageTarget)
                        tauntIfLoose(warrior, "bone_warrior_taunt");

        if (phase == Phase::PreEngage || duty.IsTank(bot.Guid))
            return;
        ControlDecision const control = DecideBoneWarriorControl(board, view, duty,
            bot, facts);
        if (!control.Target.IsEmpty())
            plan.Actions.push_back(Cast(board, control.Reason, control.Target,
                control.SpellId, Priority::Support,
                control.SpellId == SpellShackleUndead ? 70.0f : 60.0f));
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

    static void ChooseMovement(AdaptiveNefarianPlan& plan,
        Nefarian::MovementContext const& context)
    {
        using namespace Nefarian;
        using BotActionArbitration::Priority;
        Phase const phase = context.View.CurrentPhase;
        bool const fightOnFloor = !PhaseWantsPillar(phase);

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
        bool const onTop = OnPillarTop(context);
        if (onTop && goal->Target == Surface::Floor)
        {
            // Leaving a pillar top is a 10-yard drop off a near-vertical side:
            // StepOff/Fall/Land, not a walk. Not wired yet.
            goal->Purpose = MovePurpose::PillarDescent;
            plan.MovementSurface = goal;
            plan.Blocked = "pillar_descent_unsupported";
            plan.MovementHold = "pillar_descent_unsupported";
            return;
        }
        if (goal->Target == Surface::Floor
            && Distance(self, goal->Local) <= goal->ArrivalToleranceYards)
            return;
        if (context.View.Elevator.Guid.IsEmpty())
        {
            plan.MovementHold = "nefarian_elevator_unobserved";
            return;
        }
        if (!onTop && !OnPlatformFloor(context))
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
            // Only reached when the runtime declares a pillar ascent.
            PathLeg ascent;
            ascent.To = goal->Local;
            ascent.LocalZ = goal->LocalZ;
            ascent.FloorToleranceYards = RiseLegFloorTolerance;
            ascent.Kind = "pillar_ascent";
            if (onTop || Distance(self, goal->Local) <= MaxLegYards)
                leg = ascent;
            else
                leg = NextLeg(self, BotLocalZ(context),
                    PillarBase(uint8(std::max(goal->Pillar, 0)), 0));
        }
        else
            leg = NextLeg(self, BotLocalZ(context), goal->Local);
        if (!leg)
        {
            plan.MovementHold = "nefarian_no_surface_path";
            return;
        }
        plan.MovementLeg = leg;
        Vector3 const legWorld = LocalToWorld(leg->To, leg->LocalZ,
            context.View.Elevator.OriginZ);

        // The same leg is already running: do not relaunch it every decision.
        if (context.Facts)
            if (MovementState const* motion =
                    context.Facts->FindMotion(context.Bot.Guid))
                if (motion->Moving && Distance3(motion->Destination, legWorld)
                        <= 1.0f)
                {
                    plan.MovementHold = "nefarian_leg_in_flight";
                    return;
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
