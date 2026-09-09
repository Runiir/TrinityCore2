#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotWorldPopulationMgrBossMechanicsSupport.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"
#include "Creature.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellAuras.h"
#include "Unit.h"

#include <algorithm>
#include <string>
#include <utility>

using BotWorldBossMechanics::NowMs;

bool BotWorldPopulationMgr::TryBossTankSwap(WorldBotState& state, Player* bot,
    char const* role, BossMechanicActionResult& result,
    RaidRoleAssignment const& raidAssignment, RaidMechanicAdapter const& raidAdapter,
    std::function<void(uint32)> const& recordSwap, bool forceFacing)
{
    Unit* currentTank = result.Target->GetVictim();
    bool tankSwapConditionActive = false;
    bool tankSwapTimerTrigger = false;
    std::string tankSwapTriggerKey;
    if (result.Features.RaidEncounter && raidAdapter.ContractResolved && currentTank)
    {
        if (raidAdapter.TankSwapTrigger == "debuff_stacks")
            if (Aura const* aura = currentTank->GetAura(raidAdapter.TankSwapAuraId))
                if (aura->GetStackAmount() >= raidAdapter.TankSwapAuraStacks)
                {
                    tankSwapConditionActive = true;
                    tankSwapTriggerKey = "debuff:" + std::to_string(raidAdapter.TankSwapAuraId)
                        + ":" + std::to_string(currentTank->GetGUID().GetCounter());
                }
        if (raidAdapter.TankSwapTrigger == "timer")
            tankSwapTimerTrigger = state.LastRaidTankSwapMs
                && NowMs() >= state.LastRaidTankSwapMs + raidAdapter.TankSwapIntervalMs;
        if (raidAdapter.TankSwapTrigger == "boss_cast")
            if (result.Features.CastSpellId == raidAdapter.TankSwapTriggerSpellId)
            {
                tankSwapConditionActive = true;
                tankSwapTriggerKey = "cast:" + std::to_string(result.Features.CastSpellId);
            }
        if (raidAdapter.TankSwapTrigger == "add_spawn" && !result.Features.PriorityAddGuid.IsEmpty())
            if (Unit* add = ObjectAccessor::GetUnit(*bot, result.Features.PriorityAddGuid))
                if (add->GetEntry() == raidAdapter.TankSwapAddEntry)
                {
                    tankSwapConditionActive = true;
                    tankSwapTriggerKey = "add:" + std::to_string(add->GetGUID().GetCounter());
                }
        if (raidAdapter.TankSwapTrigger == "phase_transition")
            if (Cohort().Raid.EncounterPhase == raidAdapter.TankSwapPhase)
            {
                tankSwapConditionActive = true;
                tankSwapTriggerKey = "phase:" + raidAdapter.TankSwapPhase;
            }
    }
    if (!tankSwapConditionActive && raidAdapter.TankSwapTrigger != "timer")
        state.LastRaidTankSwapTriggerKey.clear();
    bool const tankSwapTriggered = tankSwapTimerTrigger
        || (tankSwapConditionActive && !tankSwapTriggerKey.empty()
            && state.LastRaidTankSwapTriggerKey != tankSwapTriggerKey);
    ObjectGuid nextTankGuid;
    if (currentTank)
    {
        if (currentTank->GetGUID() == raidAssignment.MainTankGuid)
            nextTankGuid = raidAssignment.OffTankGuid;
        else if (currentTank->GetGUID() == raidAssignment.OffTankGuid)
            nextTankGuid = raidAssignment.MainTankGuid;
    }
    if (tankSwapTriggered && std::string(role) == "tank"
        && !nextTankGuid.IsEmpty() && bot->GetGUID() == nextTankGuid && currentTank != bot)
    {
        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role);
        std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates(bot, result.Target, profile);
        for (BotActionCandidate const& candidate : candidates)
        {
            if (candidate.Category != BotCombatActionCategory::Taunt || !candidate.RejectReason.empty())
                continue;
            bool swapped = TryCastCombatSpell(bot, result.Target, candidate.SpellId, forceFacing);
            result.Action = swapped ? "raid_tank_swap_taunt" : "raid_tank_swap_taunt_failed";
            result.SpellId = swapped ? candidate.SpellId : 0;
            result.Failure = !swapped;
            result.Rare = true;
            if (swapped)
            {
                uint64 const swapAtMs = NowMs();
                for (WorldBotState& memberState : Party().Bots)
                    if (memberState.Guid == raidAssignment.MainTankGuid || memberState.Guid == raidAssignment.OffTankGuid)
                    {
                        memberState.LastRaidTankSwapTriggerSpellId = result.Features.CastSpellId;
                        memberState.LastRaidTankSwapTriggerKey = tankSwapTriggerKey;
                        memberState.LastRaidTankSwapWipeGeneration = Cohort().Raid.WipeGeneration;
                        memberState.LastRaidTankSwapMs = swapAtMs;
                    }
            }
            recordSwap(candidate.SpellId);
            return true;
        }
    }

    return false;
}

void BotWorldPopulationMgr::SubmitAdaptiveTankSwapCandidate(BotUpdateContext& context)
{
    // Magmaw is the bounded adaptive integration; other callers retain the
    // generic shared swap helper. The owner replaces generic boss actions, but not the contract's
    // tank handoff. Submit only that handoff, without borrowing Movement.
    if (!context.Bot || !context.AdaptiveMagmawOwnsNode
        || std::string(GetDungeonRole(context.Bot)) != "tank")
        return;
    auto* const cohort = &Cohort();
    auto const snapshot = cohort->EncounterSnapshot;
    auto& party = cohort->Party;
    if (!snapshot || cohort->Config.ValidationRouteNodeId != "bwd.magmaw.encounter"
        || cohort->Config.ValidationRouteKind != "boss"
        || snapshot->NativeBossState != "in_progress"
        || party.ValidationRouteManifestIndex >= party.ValidationRouteManifest.size())
        return;
    auto const contract = party.ValidationRouteManifest[party.ValidationRouteManifestIndex];
    if (!contract.MechanicContractResolved || contract.NodeId != "bwd.magmaw.encounter"
        || contract.TankSwapTrigger.empty() || contract.TankSwapTrigger == "none")
        return;
    auto const* observedBoss = BotEncounter::MagmawBloodlust::FindBoss(*snapshot);
    if (!observedBoss)
        return;
    ObjectGuid const bossGuid = observedBoss->Guid;
    ObjectGuid const actorGuid = context.Bot->GetGUID();
    uint64 const attempt = cohort->AttemptId;
    uint64 const wipe = cohort->Raid.WipeGeneration;
    uint64 const route = party.ValidationRouteGeneration;
    auto const revision = cohort->EncounterSnapshotRevision;
    auto const manifestIndex = party.ValidationRouteManifestIndex;

    BotActionArbitration::Candidate swap;
    swap.Key = "world.adaptive_tank_swap:" + std::to_string(attempt) + ":"
        + std::to_string(wipe) + ":" + std::to_string(route);
    swap.Source = "raid_tank_swap_contract";
    swap.ActionPriority = BotActionArbitration::Priority::Mechanic;
    swap.UtilityScore = 4.0f;
    // Native taunts still obey cast/GCD/target legality, but must not cancel
    // an already admitted native movement spline to turn towards the boss.
    swap.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::GlobalCooldown,
        BotActionArbitration::Resource::Cast,
        BotActionArbitration::Resource::Target);
    swap.ExpiresAtMs = context.DecisionNowMs + 1000;
    swap.Attempt = [this, &context, cohort, snapshot, bossGuid, actorGuid,
        attempt, wipe, route, revision, manifestIndex, contract]()
    {
        using BotActionArbitration::Outcome;
        if (&Cohort() != cohort || context.Bot == nullptr
            || context.Bot->GetGUID() != actorGuid || context.State.Guid != actorGuid
            || !context.AdaptiveMagmawOwnsNode
            || cohort->EncounterSnapshot != snapshot
            || cohort->EncounterSnapshotRevision != revision
            || cohort->AttemptId != attempt || cohort->Raid.WipeGeneration != wipe
            || cohort->Party.ValidationRouteGeneration != route
            || cohort->Config.ValidationRouteNodeId != contract.NodeId
            || cohort->Config.ValidationRouteKind != "boss"
            || cohort->Party.ValidationRouteManifestIndex != manifestIndex
            || manifestIndex >= cohort->Party.ValidationRouteManifest.size())
            return Outcome::NotApplicable("tank_swap_stale_scope");
        auto const& currentContract = cohort->Party.ValidationRouteManifest[manifestIndex];
        if (!currentContract.MechanicContractResolved
            || currentContract.NodeId != contract.NodeId
            || currentContract.MechanicContractId != contract.MechanicContractId
            || currentContract.TankSwapTrigger != contract.TankSwapTrigger
            || currentContract.TankSwapAuraId != contract.TankSwapAuraId
            || currentContract.TankSwapAuraStacks != contract.TankSwapAuraStacks
            || currentContract.TankSwapIntervalMs != contract.TankSwapIntervalMs
            || currentContract.TankSwapTriggerSpellId != contract.TankSwapTriggerSpellId
            || currentContract.TankSwapAddEntry != contract.TankSwapAddEntry
            || currentContract.TankSwapPhase != contract.TankSwapPhase
            || currentContract.MainTankRosterSlot != contract.MainTankRosterSlot
            || currentContract.OffTankRosterSlot != contract.OffTankRosterSlot
            || currentContract.TargetEntries != contract.TargetEntries)
            return Outcome::NotApplicable("tank_swap_stale_contract");
        Unit* boss = ObjectAccessor::GetUnit(*context.Bot, bossGuid);
        if (!context.Bot->IsAlive() || !context.Bot->IsInWorld()
            || !boss || !boss->IsAlive() || !boss->IsInCombat()
            || boss->GetMap() != context.Bot->GetMap()
            || boss->GetEntry() != BotEncounter::MagmawBloodlust::BossEntry
            || !context.Bot->IsValidAttackTarget(boss))
            return Outcome::NotApplicable("tank_swap_boss_unavailable");
        char const* role = GetDungeonRole(context.Bot);
        if (std::string(role) != "tank")
            return Outcome::NotApplicable("tank_swap_role_changed");
        RaidRoleAssignment const assignment = BuildRaidRoleAssignment(context.Bot);
        if (actorGuid != assignment.MainTankGuid && actorGuid != assignment.OffTankGuid)
            return Outcome::NotApplicable("tank_swap_not_assigned");
        BossMechanicActionResult result;
        result.Target = boss;
        result.Features = BuildBossMechanicFeatures(context.Bot, boss);
        if (!result.Features.RaidEncounter)
            return Outcome::NotApplicable("tank_swap_not_raid");
        RaidMechanicAdapter const adapter = BuildRaidMechanicAdapter(
            context.Bot, boss, assignment, result.Features);
        if (!adapter.ContractResolved)
            return Outcome::NotApplicable("tank_swap_contract_unresolved");
        // Preserve the generic dispatcher's wipe/first-native-combat latch.
        auto& state = context.State;
        if (state.LastRaidTankSwapWipeGeneration != wipe)
        {
            state.LastRaidTankSwapTriggerKey.clear();
            state.LastRaidTankSwapWipeGeneration = wipe;
        }
        if (!state.WasInCombat)
        {
            ++state.RaidAttempts;
            state.LastRaidTankSwapTriggerKey.clear();
            state.LastRaidTankSwapMs = NowMs();
            state.WasInCombat = true;
        }
        auto recordSwap = [this, &context, &state, boss, &assignment, &result, &adapter](uint32 spellId)
        {
            auto const anchors = BuildRaidPositioningAnchors(context.Bot, boss, assignment, result.Features);
            auto const gear = BuildRaidGearTargetPlan(context.Bot, context.Power, context.Stage);
            auto const progression = BuildHeroicRaidProgression(state, context.Bot, context.Power, context.Stage);
            std::string const raw = BuildRawJson(context.Bot, boss);
            std::string const semantic = BuildSemanticJson(context.Bot, boss, "raid_boss",
                &context.Power, context.Stage, context.ChosenActivity.Activity);
            RecordRaidTelemetry(state, context.Bot, boss, "raid_tank_swap",
                result.Failure ? "native_taunt_failed" : "native_taunt",
                result.Features, assignment, anchors, adapter, gear, progression,
                raw.c_str(), semantic.c_str(), result.Features.DangerScore,
                result.Features.CastSpellId, spellId);
        };
        if (!TryBossTankSwap(state, context.Bot, role, result, assignment,
            adapter, recordSwap, false))
            return Outcome::NotApplicable("tank_swap_not_eligible");
        context.Action = result.Action;
        context.Situation = "raid_boss";
        state.LastDecisionHandler = "raid_tank_swap_contract";
        return result.Failure ? Outcome::Retryable("native_taunt_failed")
            : Outcome::Submitted("native_taunt_submitted");
    };
    context.State.DecisionKernel.Submit(std::move(swap));
}
