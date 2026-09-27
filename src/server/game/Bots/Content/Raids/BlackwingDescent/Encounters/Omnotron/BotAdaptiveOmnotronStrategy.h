#ifndef TRINITY_BOT_ADAPTIVE_OMNOTRON_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_OMNOTRON_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronMovement.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronPositioning.h"
#include <algorithm>
#include <optional>
#include <string_view>
#include <vector>

// Omnotron Defense System (BWD) adaptive strategy for any two-tank
// composition. It owns the node only while a construct is engaged; before the
// pull the validation route approaches and pulls the patrolling construct.
//
// Per bot and snapshot it proposes:
// - DamageTarget: an active construct whose shield is spent this activation,
//   else the newest active unshielded one (so DoTs age out before a shield),
//   a Poison Bomb that is safe to kill for ranged damage dealers, or the
//   construct a tank owns;
// - SuppressOffense: when every active construct is shielded, and for a tank
//   whose own construct is shielded (it keeps holding it);
// - TankTarget: the construct a tank must hold (taunt if it is on anyone else);
// - InterruptTarget: Arcanotron for the rotation's current interrupter;
// - DispelTarget: a Soaked In Poison carrier for a poison dispeller;
// - OffenseAllowed: the constructs that may be damaged at all;
// - Movement: Lightning Conductor, Poison Bomb, Flamethrower, hazards, tank
//   positioning (generator exit, shield separation, centre slot), healer
//   coverage of every tank and Power Generator stacking, in that order.
namespace BotEncounter
{
struct AdaptiveOmnotronPlan
{
    bool OwnsNode = false;
    bool SuppressOffense = false;
    std::string_view SuppressReason;
    ObjectGuid DamageTarget;
    ObjectGuid InterruptTarget;
    // Arcane Annihilator cast count for this attempt: one interrupt candidate
    // identity per cast, so retries of one cast never delay the next.
    uint64 InterruptCastOrdinal = 0;
    ObjectGuid TankTarget;
    ObjectGuid DispelTarget;
    // Constructs this bot may damage (active, no shield or shield cast). The
    // runtime restricts every other construct entry for this bot, which also
    // keeps area spells away from a shielded construct. Never widened for an
    // interrupt or taunt: those get a single-cast allowance at submission.
    std::vector<ObjectGuid> OffenseAllowed;
    std::optional<BotNativeAction::Candidate> Movement;
};

class AdaptiveOmnotronStrategy
{
public:
    static constexpr uint32 Arcanotron = Omnotron::ArcanotronEntry;
    static constexpr uint32 Magmatron = Omnotron::MagmatronEntry;
    static constexpr uint32 Electron = Omnotron::ElectronEntry;
    static constexpr uint32 Toxitron = Omnotron::ToxitronEntry;
    static constexpr uint32 PoisonBomb = Omnotron::PoisonBombEntry;
    static constexpr uint32 PoisonPuddle = Omnotron::PoisonPuddleEntry;
    static constexpr uint32 ChemicalCloud = Omnotron::ChemicalCloudEntry;

    AdaptiveOmnotronPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
    {
        // Qualified names only: other encounter headers declare helpers with
        // the same names at BotEncounter scope.
        namespace O = Omnotron;
        AdaptiveOmnotronPlan plan;
        if (board.Route.NodeId != O::EncounterNodeId)
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return plan;
        O::EncounterFacts const facts = O::Observe(board);
        if (!facts.Engaged)
            return plan;
        plan.OwnsNode = true;
        for (O::ConstructFact const& construct : facts.Constructs)
            if (construct.Active && !construct.Shielded())
                plan.OffenseAllowed.push_back(construct.Actor->Guid);
        std::string_view const effectiveRole = role.empty()
            ? std::string_view(bot->Role) : role;
        O::DutyPlan const duty = O::BuildDutyPlan(board, facts,
            O::LedgerMode::Observe);

        ChooseTargets(board, facts, duty, *bot, effectiveRole, plan);

        if (duty.Interrupt.Primary == botGuid
            || (duty.Interrupt.Backup == botGuid
                && duty.Interrupt.CastAgeMs >= O::InterruptBackupDelayMs))
            plan.InterruptTarget = duty.Interrupt.Caster;
        plan.InterruptCastOrdinal = duty.Interrupt.Ordinal;
        // OffenseAllowed stays exactly the active unshielded constructs. An
        // interrupt or taunt on a shielded construct is widened for that one
        // native cast by the runtime (SingleCastAllowance); an allowed GUID
        // here would open every offense path of this bot, area spells beside
        // the shielded construct included.
        plan.DispelTarget = duty.DispelTargetFor(botGuid);
        plan.Movement = ProposeMovement(board, facts, duty, *bot, effectiveRole);
        return plan;
    }

private:
    static void ChooseTargets(Blackboard const& board,
        Omnotron::EncounterFacts const& facts, Omnotron::DutyPlan const& duty,
        ActorSnapshot const& bot, std::string_view role, AdaptiveOmnotronPlan& plan)
    {
        namespace O = Omnotron;
        if (role == "tank")
        {
            O::TankDuty const* tank = duty.TankDutyFor(bot.Guid);
            O::ConstructFact const* own = tank ? facts.Find(tank->Construct) : nullptr;
            if (own)
            {
                plan.TankTarget = own->Actor->Guid;
                if (own->Shielded())
                {
                    plan.SuppressOffense = true;
                    plan.SuppressReason = "tank_holds_shielded_construct";
                }
                else
                    plan.DamageTarget = own->Actor->Guid;
                return;
            }
            // Waiting next to the construct about to activate: no damage
            // target, or combat range movement would pull it back.
            if (tank && facts.Find(tank->Standby))
            {
                plan.SuppressOffense = true;
                plan.SuppressReason = "tank_standby_next_construct";
                return;
            }
        }
        else if (role == "dps" && O::StandsAtRange(bot.ClassSpec, role)
            && !duty.BombTarget.IsEmpty())
        {
            ActorSnapshot const* bomb = board.FindActor(duty.BombTarget);
            if (bomb && O::PlanarDistance(bomb->Position, bot.Position) <= 40.0f)
            {
                plan.DamageTarget = bomb->Guid;
                return;
            }
        }

        if (!duty.DamageFocus.IsEmpty())
            plan.DamageTarget = duty.DamageFocus;
        else if (!duty.DamageFallback.IsEmpty())
            plan.DamageTarget = duty.DamageFallback;
        else
        {
            plan.SuppressOffense = true;
            plan.SuppressReason = "all_constructs_shielded";
        }
    }

    static std::optional<BotNativeAction::Candidate> ProposeMovement(
        Blackboard const& board, Omnotron::EncounterFacts const& facts,
        Omnotron::DutyPlan const& duty, ActorSnapshot const& bot,
        std::string_view role)
    {
        namespace O = Omnotron;
        // Heroic Encasing Shadows roots the player; no path can be taken.
        if (O::HasAura(bot, O::EncasingShadowsAura))
            return std::nullopt;
        if (auto move = O::ProposeConductorIsolation(board, facts, bot))
            return move;
        if (auto move = O::ProposeBombKite(board, facts, bot))
            return move;
        if (auto move = O::ProposeAcquiredTargetLine(board, facts, bot))
            return move;
        if (auto move = O::ProposeFlamethrowerDodge(board, facts, bot))
            return move;
        if (auto move = O::ProposeHazardExit(board, facts, bot))
            return move;
        if (auto move = O::ProposeConductorClearance(board, bot))
            return move;
        if (role == "tank")
        {
            if (auto move = O::ProposeTankPosition(board, facts, duty, bot))
                return move;
            return O::ProposeTankSlot(board, facts, duty, bot);
        }
        if (auto move = O::ProposeHealerCoverage(board, facts, duty, bot, role))
            return move;
        return O::ProposeGeneratorStack(board, facts, duty, bot, role);
    }
};
}

#endif
