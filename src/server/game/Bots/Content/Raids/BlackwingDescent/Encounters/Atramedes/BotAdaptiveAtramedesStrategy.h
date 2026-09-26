#ifndef TRINITY_BOT_ADAPTIVE_ATRAMEDES_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_ATRAMEDES_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesAirActions.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesSpirits.h"
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
//   4. gong-owner standby at its shield, tank anchor drag, melee at maximum
//      melee range and the ranged arc on the ground, the relay stations
//      (owner, backup and the most mobile third gonger) and the spread ring
//      in the air.
// In the air the chased player first spends its mobility (a speed buff,
// Blink, Disengage) or, as a mage, its Ice Block; a mage with Ice Block
// ready takes the rescue strike, baits the flame and blocks it
// (BotAtramedesAirActions.h, user raid experience 2026-09-25).
// Damage: everyone hits Atramedes; in the air melee and the tank cannot reach
// him and ask the runtime to suppress offense instead of chasing.
// The two spirit packs before the bell get a kill order and a ranged
// standoff (BotAtramedesSpirits.h) without owning those route nodes.
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
        if (Spirits::IsSpiritNode(board.Route.NodeId))
            return ProposeSpirits(board, botGuid, role);
        AdaptiveAtramedesPlan plan;
        if (board.Route.NodeId != EncounterNode)
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return plan;
        Facts const facts = BuildFacts(board);
        // Only an engaged Atramedes. Before the pull (the respawn 30 s after
        // a wipe stands idle at AtramedesRespawnPosition) the route walks the
        // raid back and pulls him; an owned node with nothing to do would
        // hold everyone where they stand.
        if (!facts.Boss || facts.CurrentPhase == Phase::PrePull)
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
        // Air abilities: the Ice Block rescuer's bait and block, the chased
        // player's own extension or Ice Block.
        std::optional<AirAbility> ability;
        if (facts.CurrentPhase == Phase::Air)
        {
            ability = IceRescuerAbility(board, facts, *bot);
            if (!ability)
                ability = KiterAbility(facts, *bot, gong.Withheld);
        }
        if (ability)
        {
            if (ability->Cast)
                plan.Interaction = MakeCandidate(board, ability->Mechanic,
                    facts.Boss->Guid, BotActionArbitration::Priority::Survival, 560.0f,
                    *ability->Cast);
            if (ability->SuppressOffense)
            {
                plan.SuppressOffense = true;
                plan.SuppressReason = ability->SuppressReason;
                plan.DamageTarget = ObjectGuid();
            }
            if (ability->Hold)
                return plan;
        }

        if (!ability && gong.Required && gong.Clicker == botGuid && gong.Shield)
        {
            if (Geometry::Distance3d(bot->Position, gong.Shield->Position)
                <= ShieldClickDistance)
                plan.Interaction = MakeCandidate(board, gong.Reason,
                    gong.Shield->Guid, BotActionArbitration::Priority::Mechanic,
                    650.0f, BotNativeAction::SpellClick{ gong.Shield->Guid });
            else
            {
                // Ground: the stand point toward the tank anchor. Air: the
                // nearest point inside reach on the runner's side.
                Vector3 const approach = facts.CurrentPhase == Phase::Air
                    ? Geometry::PointAt(gong.Shield->Position,
                        Geometry::Bearing(gong.Shield->Position, bot->Position),
                        ShieldStandInset, ArenaCenter.Z)
                    : ShieldStandPoint(*gong.Shield);
                move = Survival(approach, "gong_approach", 530.0f);
            }
        }

        if (!move)
            move = SelectMovement(board, facts, duties, *bot, tank, melee);
        // Beside an instant self-buff the kite step leaves the cast lanes free.
        if (move && ability && ability->KeepKiting)
            move->PreemptCasting = false;
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
        if (std::optional<MoveProposal> run = AirRedirectRun(board, facts, self))
            return run;
        if (std::optional<MoveProposal> exit = SonicBreathBeamExit(board, facts, duties, self))
            return exit;
        if (std::optional<MoveProposal> exit = FlameExit(facts, self))
            return exit;
        if (std::optional<MoveProposal> exit = BombMarkerExit(facts, self))
            return exit;
        if (std::optional<MoveProposal> exit = FirePatchExit(facts, self))
            return exit;
        if (std::optional<MoveProposal> exit = SonarPulseExit(facts, self, melee))
            return exit;
        if (facts.CurrentPhase != Phase::Air)
            if (std::optional<MoveProposal> standby = GongStandby(facts, duties, self))
                return standby;
        return FormationMove(board, facts, duties, self, tank, melee);
    }

    // Spirit packs: once the pack is engaged everyone, the tank included,
    // hits the kill-order target (the route's shared focus and the tank's
    // area-threat target defer to it through the spirit patches). Melee leave
    // a whirlwinding spirit; ranged and healers hold the standoff half circle.
    static AdaptiveAtramedesPlan ProposeSpirits(Blackboard const& board,
        ObjectGuid botGuid, std::string_view role)
    {
        using namespace Atramedes;
        AdaptiveAtramedesPlan plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return plan;
        Spirits::Pack const pack = Spirits::BuildPack(board);
        if (pack.Engaged.empty())
            return plan;
        DutyPlan const duties = BuildDutyPlan(board);
        bool const tank = botGuid == duties.Tank || IsTank(*bot) || role == "tank";
        bool const melee = !tank && IsMelee(*bot);
        plan.Duty = tank ? "spirit_tank" : melee ? "spirit_melee" : "spirit_ranged";
        ActorSnapshot const* target = Spirits::KillTarget(pack, board.Route.NodeId);
        if (target)
            plan.DamageTarget = target->Guid;
        if (tank)
            return plan;
        std::optional<MoveProposal> move = melee ? Spirits::WhirlwindExit(pack, *bot, target)
            : Spirits::StandoffMove(board, pack, duties.Tank, *bot);
        if (move)
            plan.Movement = MakeCandidate(board, move->Mechanic,
                target ? target->Guid : pack.Engaged.front()->Guid,
                move->ActionPriority, move->Utility,
                BotNativeAction::Move(move->Destination.X, move->Destination.Y,
                    move->Destination.Z, move->Mechanic, move->PreemptCasting));
        return plan;
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
