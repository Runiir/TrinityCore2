#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotActionArbiter.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Creature.h"
#include "Pet.h"
#include "Player.h"

namespace BotWorldPopulationMgrValidationRoute
{
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunThreatAndEvidenceActions()
{
    if (!OtherSource->IsAlive())
    {
        auto& party = Manager.Party();
        if (party.ValidationRouteDrudgeDeathEvidenceSequence
            && !party.ValidationRouteDrudgeRageWaitEvidenceSequence
            && LaneSource->GetGUID().GetCounter()
                == party.ValidationRouteDrudgeSurvivorSourceGuid)
            party.ValidationRouteDrudgeRageWaitEvidenceSequence =
                ++Manager.Cohort().Raid.EvidenceSequence;
        if (!LaneSource->HasAura(Manager.Cohort().Config.ValidationRouteVengefulRageSpellId))
        {
            HoldOffense();
            Record(LaneSource, "drudge_wait_native_vengeful_rage", SourceSeparation);
            Target = LaneSource;
            State.TargetGuid = LaneSource->GetGUID();
            return PhaseResult::Handled;
        }
        if (party.ValidationRouteDrudgeDeathEvidenceSequence
            && party.ValidationRouteDrudgeRageWaitEvidenceSequence
            && !party.ValidationRouteDrudgeRageAuraEvidenceSequence
            && LaneSource->GetGUID().GetCounter()
                == party.ValidationRouteDrudgeSurvivorSourceGuid)
        {
            party.ValidationRouteDrudgeRageAuraEvidenceSequence =
                ++Manager.Cohort().Raid.EvidenceSequence;
            Record(LaneSource, "drudge_native_vengeful_rage_observed", SourceSeparation);
        }
    }
    if (RunDrudgeSeedCoordinator() == PhaseResult::Handled)
        return PhaseResult::Handled;
    bool const laneOwnershipSafe = LaneSource->IsAlive()
        && LaneSource->GetVictim() == LaneTank
        && (!OtherSource->IsAlive() || OtherSource->GetVictim() == OtherTank);
    if (!laneOwnershipSafe)
    {
        HoldOffense();
        Record(LaneSource, "drudge_lane_wait_lane_ownership", SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource ? LaneSource->GetGUID() : ObjectGuid::Empty;
        return PhaseResult::Handled;
    }

    if (Sources[0]->IsAlive() && Sources[1]->IsAlive()
        && !ExactRosterReSeparated())
    {
        HoldOffense();
        Record(LaneSource, "drudge_lane_profile_hold_contract_unsafe", SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    if (Sources[0]->IsAlive() && Sources[1]->IsAlive() && AssignedTank)
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
            party.ValidationRouteDrudgeHealthSyncEvidenceAttemptId = Manager.Cohort().AttemptId;
            party.ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration = Manager.Cohort().Raid.WipeGeneration;
            party.ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration = party.ValidationRouteGeneration;
        }
        party.ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids.insert(
            Bot->GetGUID().GetCounter());
        if (UnitHealthPct(LaneSource) < UnitHealthPct(OtherSource))
        {
            party.ValidationRouteDrudgeHealthSyncRosterGuids.insert(
                Bot->GetGUID().GetCounter());
            party.ValidationRouteDrudgeHealthSyncHoldSourceSpawnId =
                LaneSource == Sources[0] ? 250140 : 250141;
            party.ValidationRouteDrudgeHealthSyncHoldTankGuid = LaneTank
                ? LaneTank->GetGUID().GetCounter() : 0;
            party.ValidationRouteDrudgeHealthSyncHoldLowerPct = UnitHealthPct(LaneSource);
            party.ValidationRouteDrudgeHealthSyncHoldPeerPct = UnitHealthPct(OtherSource);
            party.ValidationRouteDrudgeHealthSyncHoldLowerAlive = LaneSource->IsAlive();
            party.ValidationRouteDrudgeHealthSyncHoldPeerAlive = OtherSource->IsAlive();
        }
    }
    if (Sources[0]->IsAlive() && Sources[1]->IsAlive()
        && UnitHealthPct(LaneSource) < UnitHealthPct(OtherSource))
    {
        HoldOffense();
        Record(LaneSource, AssignedTank ? "drudge_tank_health_sync_hold"
            : "drudge_kill_sync_hold_lower_health_lane", SourceSeparation);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    if (Sources[0]->IsAlive() && Sources[1]->IsAlive() && Role != "tank")
    {
        Player* intendedSeed = OtherTank;
        float const intendedDistance = intendedSeed
            ? LaneSource->GetExactDist(intendedSeed) : 0.0f;
        if (!intendedSeed || intendedSeed->GetMap() != LaneSource->GetMap()
            || intendedDistance < Bot->GetExactDist(LaneSource)
                + 2.0f * Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards)
        {
            HoldOffense();
            Record(LaneSource, "drudge_native_farthest_profile_hold",
                intendedDistance, Bot->GetGUID().GetCounter());
            Target = LaneSource;
            State.TargetGuid = LaneSource->GetGUID();
            return PhaseResult::Handled;
        }
    }
    if (Bot->GetVictim() && Bot->GetVictim() != LaneSource)
        Manager.SubmitMeleeAutoAttackIntent(State, BotMeleeAutoAttack::Kind::Suppress,
            ObjectGuid::Empty, BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl, "split_lane_target_switch");
    if (Pet* pet = Bot->GetPet(); pet && pet->GetVictim() && pet->GetVictim() != LaneSource)
        pet->AttackStop();
    for (Unit* controlled : Bot->m_Controlled)
        if (controlled && controlled->GetVictim() && controlled->GetVictim() != LaneSource)
            controlled->AttackStop();
    BotRaidAreaAuthority::SetAllOffenseSuppressed(Bot->GetGUID().GetRawValue(), false);
    BotRaidAreaAuthority::Set(Bot->GetGUID().GetRawValue(), true);
    ResolvedCombatAction profileAction = Manager.ResolveProfileCombatAction(
        Bot, LaneSource, 1, false, 0, false, false, true, false, true);
    BotActionResult const result = Manager.ExecuteProfileCombatAction(&State, Bot,
        LaneSource, &profileAction, 1, false, 0, false, false, true, false, true);
    bool const valid = profileAction.Valid && profileAction.Type == "cast"
        && profileAction.SpellId && profileAction.TargetGuid == LaneSource->GetGUID();
    bool const succeeded = valid && result == BotActionResult::Ok;
    if (succeeded)
        Manager.Party().ValidationRouteDrudgeProfileActionRosterGuids.insert(
            Bot->GetGUID().GetCounter());
    Record(LaneSource, succeeded ? "drudge_lane_single_target_action"
        : "drudge_lane_single_target_hold", SourceSeparation, profileAction.SpellId);
    Target = LaneSource;
    State.TargetGuid = LaneSource->GetGUID();
    State.WasInCombat = LaneSource->IsInCombat();
    return PhaseResult::Handled;
}
}
