#include "Bots/BotActionArbiter.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeHealthSync.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Creature.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

namespace BotWorldPopulationMgrValidationRoute
{
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunEntranceCombat()
{
    Creature* combatTarget = LaneSource->IsAlive() ? LaneSource : OtherSource;
    if (!combatTarget || !combatTarget->IsAlive())
        return PhaseResult::Abort;

    SourceSeparation = Sources[0]->GetExactDist2d(Sources[1]);
    if (Role == "healer" && Callbacks.TryGroupHeal
        && Callbacks.TryGroupHeal(Bot, combatTarget, false, true))
    {
        Record(combatTarget, "drudge_entrance_combat_heal", SourceSeparation);
        Target = combatTarget;
        State.TargetGuid = combatTarget->GetGUID();
        return PhaseResult::Handled;
    }

    bool const bothAlive = LaneSource->IsAlive() && OtherSource->IsAlive();
    float const laneHealth = bothAlive ? UnitHealthPct(LaneSource) : 0.0f;
    float const peerHealth = bothAlive ? UnitHealthPct(OtherSource) : 0.0f;
    bool const hold = bothAlive && BotRaidDrudgeHealthSync::ShouldHoldLowerLane(
        laneHealth, peerHealth);
    if (bothAlive && AssignedTank)
    {
        auto& party = Manager.Party();
        if (party.ValidationRouteDrudgeHealthSyncEvidenceAttemptId
                != Manager.Cohort().AttemptId
            || party.ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration
                != Manager.Cohort().Raid.WipeGeneration
            || party.ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration
                != party.ValidationRouteGeneration)
        {
            party.ValidationRouteDrudgeHealthSyncRosterGuids.clear();
            party.ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids.clear();
            party.ValidationRouteDrudgeHealthSyncEvidenceAttemptId =
                Manager.Cohort().AttemptId;
            party.ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration =
                Manager.Cohort().Raid.WipeGeneration;
            party.ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration =
                party.ValidationRouteGeneration;
        }
        party.ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids.insert(
            Bot->GetGUID().GetCounter());
        if (hold)
        {
            party.ValidationRouteDrudgeHealthSyncRosterGuids.insert(
                Bot->GetGUID().GetCounter());
            party.ValidationRouteDrudgeHealthSyncHoldSourceSpawnId =
                LaneSource == Sources[0] ? 250140 : 250141;
            party.ValidationRouteDrudgeHealthSyncHoldTankGuid = LaneTank
                ? LaneTank->GetGUID().GetCounter() : 0;
            party.ValidationRouteDrudgeHealthSyncHoldLowerPct = laneHealth;
            party.ValidationRouteDrudgeHealthSyncHoldPeerPct = peerHealth;
            party.ValidationRouteDrudgeHealthSyncHoldLowerAlive = true;
            party.ValidationRouteDrudgeHealthSyncHoldPeerAlive = true;
        }
    }
    if (hold)
    {
        HoldOffense();
        Record(LaneSource, AssignedTank
            ? "drudge_tank_health_sync_hold"
            : "drudge_kill_sync_hold_lower_health_lane",
            SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        // Tanks still need the ordinary role kernel for mitigation and
        // survival actions. The area authority keeps hostile offense held.
        return AssignedTank ? PhaseResult::Continue : PhaseResult::Handled;
    }

    if (Bot->GetVictim() && Bot->GetVictim() != combatTarget)
        Manager.SubmitMeleeAutoAttackIntent(State,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "split_lane_target_switch");
    if (Pet* pet = Bot->GetPet();
        pet && pet->GetVictim() && pet->GetVictim() != combatTarget)
        pet->AttackStop();
    for (Unit* controlled : Bot->m_Controlled)
        if (controlled && controlled->GetVictim()
            && controlled->GetVictim() != combatTarget)
            controlled->AttackStop();
    BotRaidAreaAuthority::SetAllOffenseSuppressed(
        Bot->GetGUID().GetRawValue(), false);
    BotRaidAreaAuthority::Set(Bot->GetGUID().GetRawValue(), true);
    Target = combatTarget;
    State.TargetGuid = combatTarget->GetGUID();
    State.WasInCombat = combatTarget->IsInCombat();
    return PhaseResult::Continue;
}
}
