#ifndef TRINITY_BOT_ADAPTIVE_ATRAMEDES_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_ATRAMEDES_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesFormation.h"
#include <optional>
#include <string>
#include <string_view>

// Atramedes (BWD 10N) adaptive strategy for the canonical composition.
//
// One pure decision per bot per snapshot, in fixed urgency order:
//   1. strike a shield (native spellclick) when the gong decision names this
//      bot and a shield is in reach, otherwise walk to it;
//   2. kite the breath that tracks this bot (Sonic Breath around the boss on
//      the ground, Roaring Flame Breath along the shield ring in the air);
//   3. leave the Sonic Breath beam, Reverberating Flame, Sonar Bomb markers,
//      fire patches and Sonar Pulse disk lanes (all of them add Sound);
//   4. gong-owner standby at its shield, tank anchor drag, ranged arc on the
//      ground and the spread ring in the air.
// Damage: everyone hits Atramedes; in the air melee and the tank cannot reach
// him and ask the runtime to suppress offense instead of chasing.
namespace BotEncounter
{
struct AdaptiveAtramedesPlan
{
    bool OwnsNode = false;
    // Consumed only when the runtime wires it (see the Atramedes handoff);
    // otherwise the air slot movement alone keeps melee spread.
    bool SuppressOffense = false;
    std::string_view SuppressReason;
    ObjectGuid DamageTarget;
    std::optional<BotNativeAction::Candidate> Movement;
    std::optional<BotNativeAction::Candidate> Interaction;
    // Diagnostics: the duty and the gong reason (or why the shield budget
    // withheld one) behind this plan.
    std::string_view Duty;
    std::string_view GongReason;
};

class AdaptiveAtramedesStrategy
{
public:
    static constexpr uint32 BossEntry = Atramedes::BossEntry;
    static constexpr uint64 CandidateLifetimeMs = 750;

    AdaptiveAtramedesPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
    {
        using namespace Atramedes;
        AdaptiveAtramedesPlan plan;
        if (board.Route.NodeId != EncounterNode)
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return plan;
        Facts const facts = BuildFacts(board);
        if (!facts.Boss)
            return plan;
        plan.OwnsNode = true;

        DutyPlan const duties = BuildDutyPlan(board);
        bool const tank = botGuid == duties.Tank
            || (duties.Tank.IsEmpty() && (IsTank(*bot) || role == "tank"));
        bool const melee = !tank && IsMelee(*bot);
        plan.Duty = DutyName(facts, duties, botGuid, tank, melee);

        if (facts.CurrentPhase == Phase::Air && (melee || tank))
        {
            plan.SuppressOffense = true;
            plan.SuppressReason = "atramedes_air_phase_out_of_reach";
        }
        else
            plan.DamageTarget = facts.Boss->Guid;

        std::optional<MoveProposal> move;
        GongDecision const gong = DecideGong(board, facts, duties);
        if (gong.Required)
            plan.GongReason = gong.Reason;
        else if (!gong.Withheld.empty())
            plan.GongReason = gong.Withheld;
        if (gong.Required && gong.Clicker == botGuid && gong.Shield)
        {
            if (Geometry::Distance3d(bot->Position, gong.Shield->Position)
                <= ShieldClickDistance)
                plan.Interaction = MakeCandidate(board, gong.Reason,
                    gong.Shield->Guid, BotActionArbitration::Priority::Mechanic,
                    650.0f, BotNativeAction::SpellClick{ gong.Shield->Guid });
            else
                move = Survival(ShieldStandPoint(*gong.Shield), "gong_approach", 530.0f);
        }

        if (!move)
            move = SelectMovement(board, facts, duties, *bot, tank, melee);
        if (move)
            plan.Movement = MakeCandidate(board, move->Mechanic, facts.Boss->Guid,
                move->ActionPriority, move->Utility,
                BotNativeAction::Move(move->Destination.X, move->Destination.Y,
                    move->Destination.Z, move->Mechanic, move->PreemptCasting));
        return plan;
    }

    static std::optional<Atramedes::MoveProposal> SelectMovement(
        Blackboard const& board, Atramedes::Facts const& facts,
        Atramedes::DutyPlan const& duties, ActorSnapshot const& self,
        bool tank, bool melee)
    {
        using namespace Atramedes;
        if (std::optional<MoveProposal> kite = GroundKiteMove(board, facts, duties, self))
            return kite;
        if (std::optional<MoveProposal> kite = AirKiteMove(facts, self))
            return kite;
        if (std::optional<MoveProposal> exit = SonicBreathBeamExit(board, facts, duties, self))
            return exit;
        if (std::optional<MoveProposal> exit = FlameExit(facts, self))
            return exit;
        if (std::optional<MoveProposal> exit = BombMarkerExit(facts, self))
            return exit;
        if (std::optional<MoveProposal> exit = FirePatchExit(facts, self))
            return exit;
        if (std::optional<MoveProposal> exit = SonarPulseExit(facts, self))
            return exit;
        if (facts.CurrentPhase != Phase::Air)
            if (std::optional<MoveProposal> standby = GongStandby(facts, duties, self))
                return standby;
        return FormationMove(facts, duties, self, tank, melee);
    }

private:
    static std::string_view DutyName(Atramedes::Facts const& facts,
        Atramedes::DutyPlan const& duties, ObjectGuid guid, bool tank, bool melee)
    {
        if (guid == facts.GroundKiter)
            return "sonic_breath_kiter";
        if (guid == facts.AirKiter)
            return "roaring_flame_breath_kiter";
        if (tank)
            return "tank";
        if (guid == duties.GongOwner)
            return "gong_owner";
        if (guid == duties.GongBackup)
            return "gong_backup";
        return melee ? "melee" : "ranged";
    }

    static BotNativeAction::Candidate MakeCandidate(Blackboard const& board,
        std::string_view mechanic, ObjectGuid actor,
        BotActionArbitration::Priority priority, float utility,
        BotNativeAction::Intent action)
    {
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_atramedes";
        candidate.Id.Mechanic = std::string(mechanic);
        candidate.Id.Actor = actor;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = priority;
        candidate.Utility = utility;
        candidate.ExpiresAtMs = board.ObservedAtMs + CandidateLifetimeMs;
        candidate.Action = std::move(action);
        return candidate;
    }
};
}

#endif
