#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/BotCanonicalRaidScope.h"
#include "Bots/BotRaidBossLust.h"

#include "Creature.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <optional>
#include <string>

// The canonical boss lust fallback (BotRaidBossLust.h): on a boss node whose
// strategy declares no lust timing, the lust owner casts its known lust spell
// once per attempt after the main tank has held the boss for TankHoldMs. The
// cast is the owner's own native spell (TryCastFriendlySpell); the latch is
// committed only after the submission succeeds.
void BotWorldPopulationMgr::SubmitRaidBossLustCandidate(BotUpdateContext& context)
{
    Player* const bot = context.Bot;
    CohortRuntime& cohort = Cohort();
    if (!bot || !bot->IsAlive() || !cohort.EncounterSnapshot
        || !BotCanonicalRaidScope::IsCanonicalRaid(cohort.Raid.RaidInstance,
            cohort.Config.ValidationRouteScenarioId)
        || cohort.Config.ValidationRouteKind != "boss"
        || !cohort.Raid.EncounterInProgress
        || BotRaidBossLust::StrategyOwnsLust(cohort.Config.ValidationRouteNodeId,
            cohort.Config.ValidationRouteScenarioId))
        return;

    BotEncounter::Blackboard const& board = *cohort.EncounterSnapshot;
    std::optional<BotRaidBossLust::Owner> const owner =
        BotRaidBossLust::SelectOwner(board);
    if (!owner || owner->Guid != bot->GetGUID())
        return;

    uint64 const attemptId = cohort.AttemptId;
    uint64 const wipeGeneration = cohort.Raid.WipeGeneration;
    uint64 const routeGeneration = Party().ValidationRouteGeneration;
    BotRaidBossLust::Latch& latch = cohort.Raid.BossLust;
    uint64 const resetGeneration = cohort.Raid.BossResetGeneration;
    BotRaidBossLust::Rebind(latch, attemptId, wipeGeneration, routeGeneration,
        resetGeneration);
    if (latch.Submitted)
        return;

    BotRaidBossLust::TankHold const hold = BotRaidBossLust::FindTankHold(board,
        [bot](ObjectGuid guid)
        {
            Creature const* creature = ObjectAccessor::GetCreature(*bot, guid);
            return creature && (creature->IsDungeonBoss() || creature->isWorldBoss());
        }, &latch);
    BotRaidBossLust::ObserveTankHold(latch, hold.Boss, hold.Tank,
        context.DecisionNowMs);
    if (BotRaidBossLust::BlockedReason(board, latch, context.DecisionNowMs))
        return;

    std::optional<uint32> const spellId = BotEncounter::Chimaeron::KnownLustSpell(
        owner->ProposedSpell,
        bot->HasSpell(BotEncounter::Chimaeron::TimeWarpSpell),
        bot->HasSpell(BotEncounter::Chimaeron::BloodlustSpell),
        bot->HasSpell(BotEncounter::Chimaeron::HeroismSpell));
    if (!spellId || bot->HasAura(*spellId))
        return;
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(*spellId);
    if (!spellInfo || !bot->GetSpellHistory()->IsReady(spellInfo))
    {
        // A resource-free typed reason (as Chimaeron's unknown lust): nothing
        // else is displaced and no refused cast is retried every tick.
        BotActionArbitration::Candidate cooldown;
        cooldown.Key = std::string("raid_boss_lust:")
            + BotRaidBossLust::OwnerLustCooldownReason + ":" + std::to_string(routeGeneration);
        cooldown.Source = "raid_boss_lust";
        cooldown.ActionPriority = BotActionArbitration::Priority::Mechanic;
        cooldown.UtilityScore = 300.0f;
        cooldown.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::None);
        cooldown.ExpiresAtMs = context.DecisionNowMs + 1000;
        cooldown.Attempt = []()
        {
            return BotActionArbitration::Outcome::NotApplicable(
                BotRaidBossLust::OwnerLustCooldownReason);
        };
        context.State.DecisionKernel.Submit(std::move(cooldown));
        return;
    }

    std::string const cohortId = cohort.Id;
    CohortRuntime* const cohortPtr = &cohort;
    ObjectGuid const bossGuid = hold.Boss;
    BotActionArbitration::Candidate lust;
    lust.Key = "raid_boss_lust:" + std::to_string(routeGeneration) + ":"
        + std::to_string(resetGeneration);
    lust.Source = "raid_boss_lust";
    lust.ActionPriority = BotActionArbitration::Priority::Mechanic;
    lust.UtilityScore = 300.0f;
    lust.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::GlobalCooldown,
        BotActionArbitration::Resource::Cast);
    lust.ExpiresAtMs = context.DecisionNowMs + 1000;
    lust.RetryBaseMs = 250;
    lust.RetryMaxMs = 2000;
    lust.EscalateAfter = 4;
    lust.Attempt = [this, &context, bot, cohortId, cohortPtr, attemptId,
        wipeGeneration, routeGeneration, resetGeneration, bossGuid, spell = *spellId]()
    {
        if (FindCohort(cohortId) != cohortPtr || context.Bot != bot)
            return BotActionArbitration::Outcome::NotApplicable(
                "raid_boss_lust_stale_context");
        BotRaidBossLust::Latch& current = cohortPtr->Raid.BossLust;
        if (current.Submitted || current.AttemptId != attemptId
            || current.WipeGeneration != wipeGeneration
            || current.RouteGeneration != routeGeneration
            || current.ResetGeneration != resetGeneration)
            return BotActionArbitration::Outcome::NotApplicable(
                "raid_boss_lust_latch_moved");
        std::string failureReason;
        if (!TryCastFriendlySpell(bot, bot, spell, &failureReason))
            return BotActionArbitration::Outcome::Retryable(failureReason.empty()
                ? "raid_boss_lust_native_submission_rejected" : failureReason);
        current.Submitted = true;
        current.SubmittedAtMs = context.DecisionNowMs;
        current.SubmittedSpellId = spell;
        context.Situation = "raid_boss_lust";
        context.Action = "raid_boss_lust_submitted";
        context.State.LastDecisionHandler = "raid_boss_lust";
        Unit* boss = ObjectAccessor::GetUnit(*bot, bossGuid);
        std::string const raw = BuildRawJson(bot, boss);
        std::string const semantic = BuildSemanticJson(bot, boss, "raid_boss_lust",
            &context.Power, context.Stage, context.ChosenActivity.Activity);
        std::string const result = "submitted_native_spell_" + std::to_string(spell);
        RecordEvent(context.State, bot, "raid_boss_lust", boss, result.c_str(),
            raw.c_str(), semantic.c_str(), 0.0f, spell, spell);
        return BotActionArbitration::Outcome::Submitted(
            "raid_boss_lust_submitted_native");
    };
    context.State.DecisionKernel.Submit(std::move(lust));
}
