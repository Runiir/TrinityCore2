#include "Bots/BotBloodDecisionObservation.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMangleCooldownPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMangleDefensive.h"

#include "Creature.h"
#include "CreatureAI.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <limits>
#include <optional>
#include <string>
#include <utility>

namespace
{
using namespace BotEncounter::MagmawMangleDefensive;

using Readiness = std::array<DefensiveReadiness, DefensivePriority.size()>;

bool NativelyMangled(Player const* bot)
{
    for (uint32 spellId : MangleAuras)
        if (bot->HasAura(spellId))
            return true;
    return false;
}

bool NativelyKnownAndReady(Player const* bot, uint32 spellId)
{
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    return spellInfo && bot->HasSpell(spellId)
        && bot->GetSpellHistory()->IsReady(spellInfo);
}

bool NativeBoneShieldCovers(Player const* bot)
{
    Aura const* boneShield = bot->GetAura(BoneShieldSpell);
    return BoneShieldCovers(boneShield != nullptr,
        boneShield ? boneShield->GetCharges() : 0);
}

// Only natively known spells whose own cooldown is ready.  A running aura is
// never refreshed early, except a Bone Shield below 3 charges.
Readiness NativeReadiness(Player const* bot)
{
    Readiness states;
    for (size_t index = 0; index < DefensivePriority.size(); ++index)
    {
        uint32 const spellId = DefensivePriority[index];
        DefensiveReadiness& state = states[index];
        state.SpellId = spellId;
        state.Known = sSpellMgr->GetSpellInfo(spellId) && bot->HasSpell(spellId);
        state.Ready = state.Known && NativelyKnownAndReady(bot, spellId);
        state.Active = spellId == BoneShieldSpell
            ? NativeBoneShieldCovers(bot) : bot->HasAura(spellId);
    }
    return states;
}

uint32 NativeCooldownMs(uint32 spellId)
{
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    return spellInfo
        ? std::max(spellInfo->RecoveryTime, spellInfo->CategoryRecoveryTime) : 0;
}

// Remaining Blood Shield in ms; 0 when absent, unbounded when permanent.
uint32 NativeBloodShieldRemainingMs(Player const* bot)
{
    using BotEncounter::MagmawMangleCooldownPlan::BloodShieldAbsorbSpell;
    Aura const* bloodShield = bot->GetAura(BloodShieldAbsorbSpell);
    if (!bloodShield)
        return 0;
    int32 const durationMs = bloodShield->GetDuration();
    return durationMs < 0 ? std::numeric_limits<uint32>::max() : uint32(durationMs);
}

// Re-prove the blackboard window on the live boss: engaged Magmaw, its own
// Mangle timer inside the lead with this bot as the victim, or this bot
// already seized.
std::optional<DefensiveWindow> NativeWindow(Player* bot, ObjectGuid bossGuid)
{
    Creature* boss = ObjectAccessor::GetCreature(*bot, bossGuid);
    if (!boss || !boss->IsAlive() || boss->GetEntry() != BossEntry
        || !boss->IsInCombat() || !boss->IsAIEnabled())
        return std::nullopt;
    if (NativelyMangled(bot))
        return DefensiveWindow{ bossGuid, bot->GetGUID(),
            DefensiveTrigger::Mangled, 0 };

    uint32 const publishedMs =
        boss->AI()->GetTimeUntilEncounterMechanic(MassiveCrashSpell);
    if (publishedMs == std::numeric_limits<uint32>::max())
        return std::nullopt;
    uint32 const remainingMs = MangleDueInMs(publishedMs);
    if (remainingMs > PreMangleBoneShieldLeadMs || boss->GetVictim() != bot)
        return std::nullopt;
    return DefensiveWindow{ bossGuid, bot->GetGUID(),
        DefensiveTrigger::PreMangleLead, remainingMs };
}
}

void BotWorldPopulationMgr::SubmitMagmawMangleDefensiveCandidate(
    BotUpdateContext& context)
{
    if (!context.Bot || !context.AdaptiveMagmawOwnsNode)
        return;

    std::string const cohortId = Cohort().Id;
    CohortRuntime* const cohort = FindCohort(cohortId);
    if (!cohort || !cohort->EncounterSnapshot
        || cohort->Config.ValidationRouteNodeId != EncounterNode
        || cohort->Config.ValidationRouteKind != "boss")
        return;

    // Only the admitted raid tank.  The Balance druid in the raid_tank_1
    // slot is dps and is never Magmaw's intended Mangle target.
    Player* const bot = context.Bot;
    ObjectGuid const botGuid = bot->GetGUID();
    RaidRuntime const& raid = cohort->Raid;
    auto const row = raid.RosterByGuid.find(botGuid.GetCounter());
    if (!raid.Active || !raid.BotActionsEnabled
        || row == raid.RosterByGuid.end() || row->second.Guid != botGuid
        || row->second.Role != "tank" || !row->second.Active
        || !row->second.LeaseOwned)
        return;

    std::optional<DefensiveWindow> const window =
        ObserveMangleDefensiveWindow(*cohort->EncounterSnapshot, botGuid);
    if (!window)
        return;
    std::optional<uint32> const selected =
        SelectDefensive(*window, NativeReadiness(bot));
    if (!selected)
        return;

    uint32 const spellId = *selected;
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    bool const usesGlobalCooldown = spellInfo && spellInfo->StartRecoveryTime > 0;

    BotActionArbitration::Candidate defensive;
    defensive.Key = "adaptive_magmaw:mangle_defensive:" + std::to_string(spellId);
    defensive.Source = "adaptive_magmaw_mangle_defensive";
    defensive.ActionPriority = BotActionArbitration::Priority::Survival;
    defensive.UtilityScore = 400.0f;
    defensive.RequiredResources = usesGlobalCooldown
        ? BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast)
        : BotActionArbitration::Uses(BotActionArbitration::Resource::Cast);
    defensive.ExpiresAtMs = context.DecisionNowMs + 500;
    defensive.RetryBaseMs = 100;
    defensive.RetryMaxMs = 500;
    defensive.EscalateAfter = 4;

    uint64 const attemptId = cohort->AttemptId;
    uint64 const wipeGeneration = raid.WipeGeneration;
    defensive.Attempt = [this, &context, bot, botGuid, cohortId, cohort,
        attemptId, wipeGeneration, bossGuid = window->BossGuid, spellId]()
    {
        if (FindCohort(cohortId) != cohort || cohort->AttemptId != attemptId
            || cohort->Raid.WipeGeneration != wipeGeneration
            || context.Bot != bot || bot->GetGUID() != botGuid
            || !bot->IsAlive())
            return BotActionArbitration::Outcome::NotApplicable(
                "magmaw_mangle_defensive_stale_context");

        std::optional<DefensiveWindow> const native = NativeWindow(bot, bossGuid);
        if (!native)
            return BotActionArbitration::Outcome::NotApplicable(
                "magmaw_mangle_defensive_window_closed");
        if (SelectDefensive(*native, NativeReadiness(bot)) != spellId)
            return BotActionArbitration::Outcome::NotApplicable(
                "magmaw_mangle_defensive_not_selected");

        Unit* boss = ObjectAccessor::GetUnit(*bot, bossGuid);
        auto record = [this, &context, bot, boss, spellId,
            remainingMs = native->RemainingMs](std::string const& result)
        {
            std::string const raw = BuildRawJson(bot, boss);
            std::string const semantic = BuildSemanticJson(bot, boss,
                "magmaw_mangle_defensive", &context.Power, context.Stage,
                context.ChosenActivity.Activity);
            RecordEvent(context.State, bot, "magmaw_mangle_defensive", boss,
                result.c_str(), raw.c_str(), semantic.c_str(),
                float(remainingMs), spellId, spellId);
        };

        std::string failureReason;
        if (!TryCastFriendlySpell(bot, bot, spellId, &failureReason))
        {
            std::string const reason = failureReason.empty()
                ? "native_spell_submission_rejected" : failureReason;
            record("blocked_" + reason);
            return BotActionArbitration::Outcome::Retryable(
                "magmaw_mangle_defensive_" + reason);
        }

        context.Situation = "adaptive_magmaw";
        context.Action = "magmaw_mangle_defensive_submitted";
        context.State.LastDecisionHandler = "adaptive_magmaw_mangle_defensive";
        record("submitted_native_spell_" + std::to_string(spellId) + "_"
            + DefensiveTriggerName(native->Trigger));
        return BotActionArbitration::Outcome::Submitted(
            "magmaw_mangle_defensive_submitted_native");
    };
    context.State.DecisionKernel.Submit(std::move(defensive));
}

namespace BotEncounter::MagmawMangleCooldownPlan
{
namespace
{
// The profile candidate passed the native preflight and is not suppressed
// for this resolution.
bool CandidateCastable(std::vector<BotActionCandidate> const& candidates,
    uint32 spellId, uint32 excludedSpellId, uint32 policyExcludedSpellId)
{
    if (spellId == excludedSpellId || spellId == policyExcludedSpellId)
        return false;
    for (BotActionCandidate const& candidate : candidates)
        if (candidate.SpellId == spellId && candidate.RejectReason.empty())
            return true;
    return false;
}
}

Plan Observe(Player const* bot, std::string_view role, Blackboard const* board,
    std::vector<BotActionCandidate> const& candidates, uint32 excludedSpellId,
    uint32 policyExcludedSpellId)
{
    Plan plan;
    if (!bot || role != "tank")
        return plan;
    auto castable = [&candidates, excludedSpellId, policyExcludedSpellId](uint32 spellId)
    {
        return CandidateCastable(candidates, spellId, excludedSpellId,
            policyExcludedSpellId);
    };
    bool const seized = NativelyMangled(bot);
    plan.SeizedHeartStrikeHold = HoldSeizedHeartStrike(seized,
        castable(DeathStrikeSpell),
        BotBloodDecisionObservation::ObserveReadyRunes(bot).Blood,
        castable(RuneTapSpell));
    if (!board)
        return plan;
    ObjectGuid const botGuid = bot->GetGUID();
    std::optional<MangleTimer> const timer =
        MagmawMangleDefensive::ObserveMangleTimer(*board, botGuid);
    if (!timer)
        return plan;

    plan.Active = true;
    plan.Timer = *timer;
    plan.Timer.HitInProgress = plan.Timer.HitInProgress || seized;
    plan.HealthPct = BotWorldPopulationMgrNativeHelpers::UnitHealthPct(bot);
    plan.IceboundCooldownMs = NativeCooldownMs(IceboundFortitudeSpell);
    plan.VampiricBloodCooldownMs = NativeCooldownMs(VampiricBloodSpell);
    plan.BoneShieldCooldownMs = NativeCooldownMs(BoneShieldSpell);
    plan.ShorterSurvivalCastable = castable(VampiricBloodSpell)
        || castable(RuneTapSpell);

    if (seized)
        return plan;
    std::optional<DefensiveWindow> const window =
        MagmawMangleDefensive::ObserveMangleDefensiveWindow(*board, botGuid);
    bool const boneShieldPending = NativelyKnownAndReady(bot, BoneShieldSpell)
        && !NativeBoneShieldCovers(bot);
    plan.RuneHold = HoldRuneSpenders(window,
        NativeBloodShieldRemainingMs(bot), boneShieldPending);
    return plan;
}
}
