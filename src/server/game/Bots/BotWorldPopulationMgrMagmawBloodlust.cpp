#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"

#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <array>
#include <algorithm>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

namespace
{
struct ExpectedMagmawRosterMember
{
    std::string_view Slot;
    std::string_view Role;
    std::string_view ClassSpec;
};

constexpr std::array<ExpectedMagmawRosterMember, 10> ExpectedMagmaw10NRoster = {{
    { "raid_tank_1", "tank", "protection_paladin" },
    { "raid_tank_2", "tank", "blood_death_knight" },
    { "raid_healer_1", "healer", "restoration_druid" },
    { "raid_healer_2", "healer", "holy_paladin" },
    { "raid_healer_3", "healer", "discipline_priest" },
    { "raid_dps_1", "dps", "fire_mage" },
    { "raid_dps_2", "dps", "fire_mage" },
    { "raid_dps_3", "dps", "affliction_warlock" },
    { "raid_dps_4", "dps", "marksmanship_hunter" },
    { "raid_dps_5", "dps", "elemental_shaman" },
}};

constexpr std::array<uint32, 8> RaidBloodlustLockouts = {
    BotEncounter::MagmawBloodlust::BloodlustSpell,
    BotEncounter::MagmawBloodlust::HeroismSpell,
    BotEncounter::MagmawBloodlust::TimeWarpSpell,
    BotEncounter::MagmawBloodlust::AncientHysteriaSpell,
    BotEncounter::MagmawBloodlust::ExhaustionSpell,
    BotEncounter::MagmawBloodlust::SatedSpell,
    BotEncounter::MagmawBloodlust::TemporalDisplacementSpell,
    BotEncounter::MagmawBloodlust::InsanitySpell,
};
}

void BotWorldPopulationMgr::SubmitMagmawBloodlustCandidate(
    BotUpdateContext& context)
{
    using namespace BotEncounter::MagmawBloodlust;

    if (!context.Bot || !context.AdaptiveMagmawOwnsNode)
        return;

    // Console diagnostics temporarily change the selected cohort. Bind this
    // deferred candidate to the active runtime instead of that mutable view.
    std::string const cohortId = _runningCohortId;
    CohortRuntime* const cohort = FindCohort(cohortId);
    if (!cohort || !cohort->EncounterSnapshot
        || cohort->Config.ValidationRouteNodeId != EncounterNode
        || cohort->Config.ValidationRouteKind != "boss"
        || cohort->Config.ValidationRouteScenarioId != DiagnosticScenario)
        return;

    RaidRuntime* const raid = &cohort->Raid;
    PartyRuntime* const party = &cohort->Party;
    if (!raid->Active || !raid->RaidInstance
        || !raid->ServerProvisioningComplete || !raid->BotActionsEnabled
        || !raid->RosterComplete || !raid->RosterCompositionValid
        || !raid->DifficultyReadbackComplete || !raid->DifficultyMatches
        || !raid->UniqueLeases || raid->ExpectedSize != ExpectedMagmaw10NRoster.size()
        || raid->ActiveSize != ExpectedMagmaw10NRoster.size()
        || raid->RosterByGuid.size() != ExpectedMagmaw10NRoster.size()
        || raid->AdmissionScenarioId != DiagnosticScenario)
        return;

    Player* const originalBot = context.Bot;
    auto const* originalState = &context.State;
    ObjectGuid const originalBotGuid = originalBot->GetGUID();
    auto const encounterSnapshot = cohort->EncounterSnapshot;
    uint64 const encounterSnapshotRevision = cohort->EncounterSnapshotRevision;

    auto exactRosterAndOwner = [raid]() -> std::optional<ObjectGuid>
    {
        ObjectGuid owner;
        for (ExpectedMagmawRosterMember const& expected : ExpectedMagmaw10NRoster)
        {
            auto const member = std::find_if(raid->RosterByGuid.begin(),
                raid->RosterByGuid.end(), [&expected](auto const& row)
                {
                    RaidRosterSlot const& slot = row.second;
                    return slot.RosterSlotId == expected.Slot
                        && slot.Role == expected.Role
                        && slot.ClassSpec == expected.ClassSpec
                        && slot.Active && slot.LeaseOwned
                        && slot.Guid.GetCounter() == row.first;
                });
            if (member == raid->RosterByGuid.end())
                return std::nullopt;
            if (member->second.ClassSpec == ElementalShamanSpec)
            {
                if (!owner.IsEmpty())
                    return std::nullopt;
                owner = member->second.Guid;
            }
        }
        return owner.IsEmpty() ? std::nullopt
            : std::optional<ObjectGuid>(owner);
    };

    std::optional<ObjectGuid> const owner = exactRosterAndOwner();
    if (!owner || *owner != context.Bot->GetGUID())
        return;

    uint64 const attemptId = cohort->AttemptId;
    uint64 const wipeGeneration = raid->WipeGeneration;
    uint64 const routeGeneration = party->ValidationRouteGeneration;
    if (raid->MagmawBloodlustAttemptId != attemptId
        || raid->MagmawBloodlustWipeGeneration != wipeGeneration
        || raid->MagmawBloodlustRouteGeneration != routeGeneration)
    {
        raid->MagmawBloodlustSubmitted = false;
        raid->MagmawBloodlustAuraObserved = false;
        raid->MagmawBloodlustSubmittedAtMs = 0;
        raid->MagmawBloodlustOwnerGuid.Clear();
        raid->MagmawBloodlustHeadGuid.Clear();
        raid->MagmawBloodlustAttemptId = attemptId;
        raid->MagmawBloodlustWipeGeneration = wipeGeneration;
        raid->MagmawBloodlustRouteGeneration = routeGeneration;
    }
    raid->MagmawBloodlustOwnerGuid = *owner;

    BotEncounter::Blackboard const& board = *encounterSnapshot;
    auto const window = ObserveFirstHeadWindow(board);

    auto currentMagmawBloodlustContextReason = [this, &context,
        originalState, originalBot, originalBotGuid, cohortId, cohort,
        encounterSnapshot, encounterSnapshotRevision, party, raid,
        routeGeneration, attemptId, wipeGeneration, ownerGuid = *owner]()
        -> char const*
    {
        if (FindCohort(cohortId) != cohort)
            return "magmaw_bloodlust_stale_context_cohort";
        if (&context.State != originalState || context.Bot != originalBot
            || !context.Bot || context.Bot->GetGUID() != originalBotGuid
            || context.State.Guid != originalBotGuid)
            return "magmaw_bloodlust_stale_context_bot";
        if (cohort->EncounterSnapshot != encounterSnapshot
            || cohort->EncounterSnapshotRevision != encounterSnapshotRevision)
            return "magmaw_bloodlust_stale_context_snapshot";
        if (cohort->AttemptId != attemptId)
            return "magmaw_bloodlust_stale_context_attempt";
        if (raid->WipeGeneration != wipeGeneration)
            return "magmaw_bloodlust_stale_context_wipe";
        if (party->ValidationRouteGeneration != routeGeneration)
            return "magmaw_bloodlust_stale_context_route";
        if (raid->MagmawBloodlustOwnerGuid != ownerGuid)
            return "magmaw_bloodlust_stale_context_owner";

        auto const ownerRow = raid->RosterByGuid.find(ownerGuid.GetCounter());
        if (ownerRow == raid->RosterByGuid.end()
            || ownerRow->second.Guid != ownerGuid
            || ownerRow->second.ClassSpec != ElementalShamanSpec
            || !ownerRow->second.Active || !ownerRow->second.LeaseOwned)
            return "magmaw_bloodlust_stale_context_owner";
        return nullptr;
    };

    auto recordBloodlustEvent = [this, &context, originalBot,
        currentMagmawBloodlustContextReason](char const* result, Unit* target,
        uint32 valueInt)
    {
        if (currentMagmawBloodlustContextReason())
            return;
        std::string const raw = BuildRawJson(originalBot, target);
        std::string const semantic = BuildSemanticJson(originalBot, target,
            "magmaw_bloodlust", &context.Power, context.Stage,
            context.ChosenActivity.Activity);
        RecordEvent(context.State, originalBot, "magmaw_bloodlust", target,
            result, raw.c_str(), semantic.c_str(), 0.0f, valueInt,
            BloodlustSpell);
    };

    // A submitted cast is latched until its native aura is observed.  Do not
    // submit a second cast merely because the next blackboard sample has not
    // caught up yet, and keep observation useful even after the head despawns.
    if (raid->MagmawBloodlustSubmitted)
    {
        bool observedAura = originalBot->HasAura(BloodlustSpell)
            || ObservedBloodlustAura(board, *owner);
        if (observedAura && !raid->MagmawBloodlustAuraObserved)
        {
            Unit* target = originalBot;
            if (window)
                target = ObjectAccessor::GetUnit(*originalBot, window->HeadGuid);
            recordBloodlustEvent("observed_aura_2825", target, BloodlustSpell);
            raid->MagmawBloodlustAuraObserved = true;
        }
        return;
    }

    if (!window)
        return;

    if (!raid->MagmawBloodlustHeadGuid.IsEmpty()
        && raid->MagmawBloodlustHeadGuid != window->HeadGuid)
        return;
    raid->MagmawBloodlustHeadGuid = window->HeadGuid;
    ObjectGuid const headGuid = window->HeadGuid;

    auto findNativeRaidLockout = [this, party]() -> std::pair<uint32, std::string>
    {
        for (uint32 spellId : RaidBloodlustLockouts)
            for (WorldBotState const& memberState : party->Bots)
            {
                Player* member = GetLoadedBot(memberState);
                if (!member)
                    return { 0, "raid_member_unobserved" };
                if (member->HasAura(spellId))
                    return { spellId, RaidLockoutReason(spellId) };
            }
        return { 0, {} };
    };

    BotActionArbitration::Candidate bloodlust;
    bloodlust.Key = "adaptive_magmaw:bloodlust:"
        + std::to_string(routeGeneration);
    bloodlust.Source = "adaptive_magmaw_bloodlust";
    bloodlust.ActionPriority = BotActionArbitration::Priority::Mechanic;
    bloodlust.UtilityScore = 350.0f;
    bloodlust.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::GlobalCooldown,
        BotActionArbitration::Resource::Cast,
        BotActionArbitration::Resource::Target);
    bloodlust.ExpiresAtMs = context.DecisionNowMs + 1000;
    bloodlust.RetryBaseMs = 250;
    bloodlust.RetryMaxMs = 2000;
    bloodlust.EscalateAfter = 4;
    bloodlust.Attempt = [&context, originalBot, raid, encounterSnapshot,
        headGuid, ownerGuid = *owner, currentMagmawBloodlustContextReason,
        recordBloodlustEvent, findNativeRaidLockout]()
    {
        if (char const* staleReason = currentMagmawBloodlustContextReason())
            return BotActionArbitration::Outcome::NotApplicable(staleReason);

        auto block = [originalBot, headGuid,
            currentMagmawBloodlustContextReason, recordBloodlustEvent](
            std::string const& reason)
        {
            if (char const* staleReason = currentMagmawBloodlustContextReason())
                return BotActionArbitration::Outcome::NotApplicable(staleReason);
            Unit* target = ObjectAccessor::GetUnit(*originalBot, headGuid);
            std::string const result = "blocked_" + reason;
            recordBloodlustEvent(result.c_str(), target, BloodlustSpell);
            return BotActionArbitration::Outcome::NotApplicable(result);
        };

        if (raid->MagmawBloodlustSubmitted
            || raid->MagmawBloodlustOwnerGuid != ownerGuid)
            return BotActionArbitration::Outcome::NotApplicable(
                "magmaw_bloodlust_already_latched");

        Unit* head = ObjectAccessor::GetUnit(*originalBot, headGuid);
        if (!head || !head->IsAlive() || head->GetEntry() != ExposedHeadEntry
            || head->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE)
            || !originalBot->IsValidAttackTarget(head))
            return block("head_not_selectable_or_attackable");

        if (auto const observedLockout = FindRaidLockout(*encounterSnapshot))
            return block(RaidLockoutReason(*observedLockout));

        auto const nativeLockout = findNativeRaidLockout();
        if (nativeLockout.first)
            return block(nativeLockout.second);
        if (!nativeLockout.second.empty())
            return block(nativeLockout.second);

        if (!originalBot->HasSpell(BloodlustSpell))
            return block("spell_not_in_shaman_spellbook");

        std::string failureReason;
        if (!TryCastFriendlySpell(originalBot, originalBot, BloodlustSpell,
                &failureReason))
            return block(failureReason.empty()
                ? "native_spell_submission_rejected" : failureReason);

        raid->MagmawBloodlustSubmitted = true;
        raid->MagmawBloodlustSubmittedAtMs = context.DecisionNowMs;
        context.Situation = "adaptive_magmaw";
        context.Action = "magmaw_bloodlust_submitted";
        context.State.LastDecisionHandler = "adaptive_magmaw_bloodlust";
        recordBloodlustEvent("submitted_native_spell_2825", head,
            BloodlustSpell);
        return BotActionArbitration::Outcome::Submitted(
            "magmaw_bloodlust_submitted_native");
    };
    context.State.DecisionKernel.Submit(std::move(bloodlust));
}
