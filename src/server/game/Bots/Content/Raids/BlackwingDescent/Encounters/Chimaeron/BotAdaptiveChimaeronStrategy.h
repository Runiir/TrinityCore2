#ifndef TRINITY_BOT_ADAPTIVE_CHIMAERON_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_CHIMAERON_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotEncounterLatches.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronBurn.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronHealingPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronSupportActions.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronTankSwap.h"

#include <optional>
#include <string>
#include <string_view>

namespace BotEncounter
{
// One bot's proposal for one blackboard revision. The encounter script owns
// every native fact; this plan only ranks lawful player actions:
// - Movement: formation slot (prewake staging, mixture spread, outage stack);
// - Action: an ordinary native cast (taunt exchange, raid cooldown, absorb,
//   Bloodlust) of a spell the bot knows;
// - PriorityHealTarget: the floor/urgency assignment for this healer;
// - SuppressOffense: hold damage while the boss sleeps (unless another hostile
//   is fighting the raid) and through the burn sequence (BotChimaeronBurn.h).
// Latches come from the cohort's published EncounterLatchView for this
// revision (set once per publication by UpdateEncounterLatches); without a
// view (replays) only the current revision counts.
struct AdaptiveChimaeronPlan
{
    bool OwnsNode = false;
    bool HealingDisabled = false;
    bool SuppressOffense = false;
    std::string SuppressReason;
    ObjectGuid DamageTarget;
    ObjectGuid PriorityHealTarget;
    std::optional<BotNativeAction::Candidate> Movement;
    std::optional<BotNativeAction::Candidate> Action;
    Chimaeron::Phase EncounterPhase = Chimaeron::Phase::None;
    std::string Duty;
};

class AdaptiveChimaeronStrategy
{
public:
    static constexpr uint32 BossEntry = Chimaeron::BossEntry;

    AdaptiveChimaeronPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role, EncounterLatchView const* latches = nullptr) const
    {
        using namespace Chimaeron;
        AdaptiveChimaeronPlan plan;
        Observation const observation = Observe(board, botGuid);
        plan.EncounterPhase = observation.CurrentPhase;
        if (observation.CurrentPhase == Phase::None)
            return plan;
        ActorSnapshot const& boss = *observation.Boss;
        ActorSnapshot const& bot = *observation.Bot;
        Duties const duties = BuildDuties(board, botGuid, role);
        plan.Duty = DutyName(duties, botGuid);

        if (observation.CurrentPhase == Phase::Prewake)
        {
            // The route owns these nodes (arrival, Finkle's gossip, the wake
            // wait) and their completions. Nobody may pull the sleeping boss
            // before the Bile-O-Tron is active; once the wake wait starts the
            // raid stages so the Break tank is the nearest player. A patrol or
            // leftover pack fighting the raid lifts the suppression.
            // Back asleep at the encounter node (the native reset after a
            // wipe) the plan keeps the node, so the generic boss adapters do
            // not pull him without Finkle's Mixture, and stages only once the
            // Bile-O-Tron is active again (the Finkle owner must reach him
            // first).
            bool const resetAtEncounter = board.Route.NodeId == EncounterNode;
            plan.OwnsNode = resetAtEncounter;
            plan.SuppressOffense = !OtherHostileEngaged(board, boss);
            if (plan.SuppressOffense)
                plan.SuppressReason = resetAtEncounter
                    ? "encounter_reset_boss_asleep" : "prewake_boss_asleep";
            if (board.Route.NodeId == WakeWaitNode || (resetAtEncounter && observation.MixtureOn))
                if (std::optional<Point> slot = PrewakeSlot(duties, ToPoint(boss.Position), botGuid))
                    plan.Movement = ProposeMove(board, bot, *slot, SpreadTolerance,
                        "prewake_stage", boss.Guid, 300.0f);
            return plan;
        }

        plan.OwnsNode = true;
        plan.DamageTarget = boss.Guid;
        BurnState const burn = ReadBurnState(board, observation, duties, latches);
        plan.HealingDisabled = observation.CurrentPhase == Phase::Mortality
            || HasAura(bot, MortalityRaidSpell);

        if (role == "healer" && !plan.HealingDisabled)
            plan.PriorityHealTarget = SelectPriorityHealTarget(board, observation,
                duties, botGuid);

        // Non-tanks hold from 23% until the release and a settled handoff.
        // Tanks keep threat and self-healing above the handoff line, hold
        // below it, and the Break tank stands down once the handoff arms.
        if (role != "tank" && burn.HoldNonTanks())
        {
            plan.SuppressOffense = true;
            plan.SuppressReason = burn.Released && burn.HandoffPending()
                ? "burn_wait_for_mortality_handoff" : "burn_hold_before_mortality";
        }
        else if (role == "tank" && HoldTank(board, burn, observation, duties, botGuid))
        {
            plan.SuppressOffense = true;
            plan.SuppressReason = botGuid == duties.BreakTank && burn.Armed()
                    && !burn.HandoffFailed()
                ? "burn_break_tank_stand_down" : "burn_hold_tanks_below_handoff";
        }

        Point const centre = FormationCentre(board, boss);
        if (observation.CurrentPhase == Phase::Outage)
            plan.Movement = ProposeMove(board, bot, StackSlot(board, centre, botGuid),
                StackTolerance, "outage_slime_stack", boss.Guid, 320.0f);
        else if (observation.CurrentPhase == Phase::Mixture)
            if (std::optional<Point> slot = SpreadSlot(duties, centre, botGuid))
                plan.Movement = ProposeMove(board, bot, *slot, SpreadTolerance,
                    "mixture_slime_spread", boss.Guid, 250.0f);

        if (std::optional<TauntDecision> taunt = DecideTaunt(board, observation, duties,
                botGuid, burn))
            plan.Action = ProposeCast(board, boss.Guid, taunt->SpellId, taunt->Reason, 400.0f);
        else if (std::optional<CastDecision> cast = DecideSupportCast(board, observation,
                duties, botGuid, burn, latches))
            plan.Action = ProposeCast(board, cast->Target, cast->SpellId, cast->Reason, 350.0f);
        return plan;
    }

private:
    static BotNativeAction::CandidateIdentity Identity(Blackboard const& board,
        std::string_view mechanic, ObjectGuid actor)
    {
        BotNativeAction::CandidateIdentity id;
        id.ScopeKey = board.CurrentScope.Key();
        id.Strategy = "adaptive_chimaeron";
        id.Mechanic = std::string(mechanic);
        id.Actor = actor;
        id.EventGeneration = board.Revision;
        return id;
    }

    static std::optional<BotNativeAction::Candidate> ProposeMove(Blackboard const& board,
        ActorSnapshot const& bot, Chimaeron::Point slot, float tolerance,
        std::string_view mechanic, ObjectGuid actor, float utility)
    {
        if (Chimaeron::Distance(Chimaeron::ToPoint(bot.Position), slot) <= tolerance)
            return std::nullopt;
        BotNativeAction::Candidate candidate;
        candidate.Id = Identity(board, mechanic, actor);
        candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
        candidate.Utility = utility;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{ slot.X, slot.Y, bot.Position.Z };
        return candidate;
    }

    static BotNativeAction::Candidate ProposeCast(Blackboard const& board,
        ObjectGuid target, uint32 spellId, std::string_view mechanic, float utility)
    {
        BotNativeAction::Candidate candidate;
        candidate.Id = Identity(board, mechanic, target);
        candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
        candidate.Utility = utility;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::CastSpell{ target, spellId };
        return candidate;
    }
};
}

#endif
