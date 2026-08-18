#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "GameTime.h"
#include "Player.h"
#include "Unit.h"

#include <chrono>
#include <functional>
#include <string>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;
    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
}
}

void BotWorldPopulationMgr::MarkTrashClusterCleared(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, char const* reason)
{
    uint64 nowMs = NowMs();
    Party().ValidationRouteManifestAdvancePending = true;
    Party().ValidationRouteManifestAdvanceGeneration = Party().ValidationRouteGeneration;
    Party().ValidationRouteManifestAdvanceReason = reason ? reason : "trash_cluster_cleared";
    for (WorldBotState& cohortState : Party().Bots)
    {
        cohortState.TargetGuid.Clear();
        cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
        cohortState.ValidationRoutePackProgressTargetGuid.Clear();
        cohortState.ValidationRouteCombatNoProgressCount = 0;
        cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
        cohortState.ValidationRoutePackNoProgressCount = 0;
        cohortState.ValidationRoutePackNoProgressSinceMs = 0;
        cohortState.ValidationRouteUnresolvedFocusHoldCount = 0;
        cohortState.ValidationRouteTerminalState = true;
        cohortState.ValidationRouteTerminalAtMs = nowMs;
        cohortState.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
        cohortState.ValidationRouteTerminalReason = reason ? reason : "trash_cluster_cleared";
        cohortState.LoopRecoveryCooldownUntilMs = nowMs + 60000;
    }
    std::string raw = BuildRawJson(bot, nullptr);
    std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_terminal", &power, stage, activity);
    RecordEvent(state, bot, "validation_route_terminal", nullptr, reason ? reason : "trash_cluster_cleared", raw.c_str(), semantic.c_str(), float(Cohort().Metrics.Kills), Cohort().Config.ValidationRouteTargetEntry);
}

void BotWorldPopulationMgr::MarkValidationRouteTrashFailed(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, Unit* failedTarget, char const* reason,
    char const* situationName, float metric, uint32 data,
    float bestHealthPct, uint32 noProgressCount, uint32 noProgressThreshold)
{
    uint64 nowMs = NowMs();
    std::string raw = BuildRawJson(bot, failedTarget);
    std::string semantic = BuildSemanticJson(bot, failedTarget, situationName ? situationName : "validation_route_trash_failed", &power, stage, activity);
    char const* terminalReason = reason ? reason : "validation_trash_no_progress";
    RecordEvent(state, bot, "validation_route_failed", failedTarget, terminalReason, raw.c_str(), semantic.c_str(), metric, data);
    float targetHealthPct = failedTarget ? UnitHealthPct(failedTarget) : metric;
    float observedBestHealthPct = bestHealthPct >= 0.0f ? bestHealthPct : targetHealthPct;
    for (WorldBotState& cohortState : Party().Bots)
    {
        RecordRouteProgress(cohortState, GetLoadedBot(cohortState), failedTarget, terminalReason, targetHealthPct, observedBestHealthPct, noProgressCount, noProgressThreshold);
        Player* cohortBot = GetLoadedBot(cohortState);
        std::string routeText = "Route reset: " + cohortState.LastRouteProgress.Summary;
        if (cohortBot && routeText != cohortState.LastBlockedDiagnosticText)
        {
            cohortBot->Say(routeText, LANG_UNIVERSAL);
            cohortState.LastBlockedDiagnosticText = routeText;
        }
        cohortState.TargetGuid.Clear();
        cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
        cohortState.ValidationRoutePackProgressTargetGuid.Clear();
        cohortState.ValidationRouteCombatNoProgressCount = 0;
        cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
        cohortState.ValidationRoutePackNoProgressCount = 0;
        cohortState.ValidationRoutePackNoProgressSinceMs = 0;
        cohortState.ValidationRouteUnresolvedFocusHoldCount = 0;
        cohortState.ValidationRouteTerminalState = true;
        cohortState.ValidationRouteTerminalAtMs = nowMs;
        cohortState.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
        cohortState.ValidationRouteTerminalReason = terminalReason;
        cohortState.LastNoProgressReason = terminalReason;
        cohortState.LoopRecoveryCooldownUntilMs = nowMs + 60000;
    }
}

void BotWorldPopulationMgr::ClearValidationRouteKilledFocus(
    WorldBotState& state, ObjectGuid killedGuid)
{
    if (killedGuid.IsEmpty())
        return;

    if (Party().ValidationRouteFocusGuid == killedGuid)
    {
        Party().ValidationRouteFocusGuid.Clear();
        Party().ValidationRouteFocusEntry = 0;
        Party().ValidationRouteFocusMapId = 0;
        Party().ValidationRouteFocusX = 0.0f;
        Party().ValidationRouteFocusY = 0.0f;
        Party().ValidationRouteFocusZ = 0.0f;
        Party().ValidationRouteFocusSeenMs = 0;
    }
    if (Party().ValidationRouteBossProgressTargetGuid == killedGuid)
    {
        Party().ValidationRouteBossProgressTargetGuid.Clear();
        Party().ValidationRouteBossSlowProgressCount = 0;
        ResetValidationRouteBossAddDensityState();
    }

    for (WorldBotState& cohortState : Party().Bots)
    {
        bool preservePartialWipeRendezvous =
            cohortState.ValidationRouteAnchorOverrideValid
            && cohortState.ValidationRouteAnchorOverrideReason
                == "validation_route_partial_wipe_retreat_rendezvous";
        if (cohortState.TargetGuid == killedGuid)
            cohortState.TargetGuid.Clear();
        if (cohortState.ValidationRouteCombatProgressTargetGuid == killedGuid)
            cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
        if (cohortState.ValidationRoutePackProgressTargetGuid == killedGuid)
            cohortState.ValidationRoutePackProgressTargetGuid.Clear();
        if (cohortState.LastDecisionTargetGuid == killedGuid)
            cohortState.LastDecisionTargetGuid.Clear();
        // A retreat rendezvous is recovery state, not killed-focus state.
        // Clearing it when the abandoned pack leashes or dies makes the
        // dead critical role resurrect at its old safe position instead
        // of beside the survivors.
        if (!preservePartialWipeRendezvous)
        {
            cohortState.ValidationRouteAnchorOverrideValid = false;
            cohortState.ValidationRouteAnchorOverrideUntilMs = 0;
            cohortState.ValidationRouteAnchorOverrideReason.clear();
        }
        if (cohortState.LastCombatAttempt.TargetGuid == killedGuid)
            cohortState.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();
        if (cohortState.LastRouteProgress.TargetGuid == killedGuid)
            cohortState.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();
        cohortState.ValidationRouteTerminalState = false;
        cohortState.ValidationRouteTerminalAtMs = 0;
        cohortState.ValidationRouteTerminalGeneration = 0;
        cohortState.ValidationRouteTerminalReason.clear();
        if (!preservePartialWipeRendezvous)
            cohortState.RecentDeathCount = 0;
    }

    state.ValidationRouteUnresolvedFocusHoldCount = 0;
}


bool BotWorldPopulationMgr::RecordValidationRouteBossKill(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, Unit* killedTarget,
    char const* assistResult)
{
    if (!killedTarget)
        return false;

    bool confirmedDeath = Party().ValidationRouteConfirmedBossDeathGuid == killedTarget->GetGUID()
        && Party().ValidationRouteConfirmedBossDeathGeneration == Party().ValidationRouteGeneration
        && Party().ValidationRouteConfirmedBossDeathMapId == killedTarget->GetMapId()
        && Party().ValidationRouteConfirmedBossDeathInstanceId == killedTarget->GetInstanceId();
    if (!confirmedDeath)
    {
        std::string raw = BuildRawJson(bot, killedTarget);
        std::string semantic = BuildSemanticJson(bot, killedTarget, "validation_route_boss_outcome", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_recovery", killedTarget, "boss_death_unconfirmed", raw.c_str(), semantic.c_str(), UnitHealthPct(killedTarget), Cohort().Config.ValidationRouteTargetEntry, killedTarget->GetHealth());
        return false;
    }
    if (Party().ValidationRouteRecordedKillGuids.find(killedTarget->GetGUID()) != Party().ValidationRouteRecordedKillGuids.end())
        return false;

    Party().ValidationRouteRecordedKillGuids.insert(killedTarget->GetGUID());
    std::string raw = BuildRawJson(bot, killedTarget);
    std::string semantic = BuildSemanticJson(bot, killedTarget, "validation_route_boss_outcome", &power, stage, activity);
    if (killedTarget->IsAlive() || killedTarget->GetHealth())
    {
        RecordEvent(state, bot, "validation_route_recovery", killedTarget, assistResult ? assistResult : "boss_route_target_unresolved", raw.c_str(), semantic.c_str(), UnitHealthPct(killedTarget), Cohort().Config.ValidationRouteTargetEntry, killedTarget->GetHealth());
        return false;
    }

    if (state.LastKilledTargetGuid != killedTarget->GetGUID())
    {
        ++Cohort().Metrics.Kills;
        state.LastKilledTargetGuid = killedTarget->GetGUID();
    }

    ClearValidationRouteKilledFocus(state, killedTarget->GetGUID());

    RecordEvent(state, bot, "boss_killed", killedTarget, "ok", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Metrics.Kills);
    if (Cohort().Config.ValidationRouteKind == "boss")
    {
        uint64 nowMs = NowMs();
        for (WorldBotState& cohortState : Party().Bots)
        {
            cohortState.TargetGuid.Clear();
            cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
            cohortState.ValidationRoutePackProgressTargetGuid.Clear();
            cohortState.ValidationRouteCombatNoProgressCount = 0;
            cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
            cohortState.ValidationRoutePackNoProgressCount = 0;
            cohortState.ValidationRoutePackNoProgressSinceMs = 0;
            cohortState.ValidationRouteUnresolvedFocusHoldCount = 0;
            cohortState.ValidationRouteTerminalState = true;
            cohortState.ValidationRouteTerminalAtMs = nowMs;
            cohortState.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
            cohortState.ValidationRouteTerminalReason = "boss_killed";
            cohortState.LoopRecoveryCooldownUntilMs = nowMs + 60000;
        }

        if (!Party().ValidationRouteManifest.empty() && Cohort().Config.ValidationRouteAdvanceMode == "terminal")
        {
            Party().ValidationRouteManifestAdvancePending = true;
            Party().ValidationRouteManifestAdvanceGeneration = Party().ValidationRouteGeneration;
            Party().ValidationRouteManifestAdvanceReason = "boss_killed";
        }

        RecordEvent(state, bot, "validation_route_terminal", killedTarget, "boss_killed", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Config.ValidationRouteTargetEntry);
    }
    if (bot->GetMap() && bot->GetMap()->IsRaid())
    {
        ++state.RaidBossKills;
        ++Cohort().Metrics.RaidBossKills;
        if (stage == BotProgressionStage::HeroicRaid)
        {
            ++state.HeroicRaidBossKills;
            ++Cohort().Metrics.HeroicRaidBossKills;
        }

        BossMechanicFeatures features = BuildBossMechanicFeatures(bot, killedTarget);
        RaidRoleAssignment assignment = BuildRaidRoleAssignment(bot);
        RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(bot, killedTarget, assignment, features);
        RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(bot, killedTarget, assignment, features);
        RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(bot, power, stage);
        HeroicRaidProgression progression = BuildHeroicRaidProgression(state, bot, power, stage);
        RecordRaidTelemetry(state, bot, killedTarget, "raid_boss_killed", "ok", features, assignment, anchors, adapter, gearPlan, progression, raw.c_str(), semantic.c_str(), power.Total, Cohort().Metrics.RaidBossKills);
    }

    MaybeAdvanceValidationRouteManifest();
    return true;
}

bool BotWorldPopulationMgr::RecordValidationRouteTrashKill(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, Unit* killedTarget, char const* reason,
    std::function<bool(Creature const*)> const& isValidationRouteScriptTarget,
    std::function<bool()> const& trashClusterHasLiveMobs)
{
    if (!killedTarget || killedTarget->IsAlive() || killedTarget->GetHealth())
        return false;

    Creature* creature = killedTarget->ToCreature();
    if (!creature)
        return false;

    if (Party().ValidationRouteRecordedKillGuids.find(killedTarget->GetGUID()) != Party().ValidationRouteRecordedKillGuids.end())
        return false;

    if (Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration
        || Party().ValidationRoutePackEngagedGuids.find(killedTarget->GetGUID()) == Party().ValidationRoutePackEngagedGuids.end())
        return false;

    Party().ValidationRouteRecordedKillGuids.insert(killedTarget->GetGUID());
    if (Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration)
    {
        Party().ValidationRoutePackMemberGuids.insert(killedTarget->GetGUID());
        Party().ValidationRoutePackDeathGuids.insert(killedTarget->GetGUID());
    }
    ++Cohort().Metrics.Kills;
    state.LastKilledTargetGuid = killedTarget->GetGUID();

    ClearValidationRouteKilledFocus(state, killedTarget->GetGUID());
    Party().ValidationRouteObservedEngagement = true;
    std::string raw = BuildRawJson(bot, killedTarget);
    std::string semantic = BuildSemanticJson(bot, killedTarget, "validation_route_trash_outcome", &power, stage, activity);
    RecordEvent(state, bot, "mob_killed", killedTarget, reason ? reason : "validation_route_recovery", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Metrics.Kills);
    if (isValidationRouteScriptTarget(creature)
        && !Party().ValidationRouteManifest.empty()
        && Cohort().Config.ValidationRouteAdvanceMode == "terminal"
        && Cohort().Config.ValidationRouteKind != "boss")
    {
        if (!trashClusterHasLiveMobs())
            RecordEvent(state, bot, "validation_route_target_search", nullptr, "trash_cluster_empty_pending_anchor_verification", raw.c_str(), semantic.c_str(), float(Cohort().Metrics.Kills), Cohort().Config.ValidationRouteTargetEntry);
        else
            RecordEvent(state, bot, "validation_route_target_search", nullptr, "trash_route_target_killed_cluster_still_alive", raw.c_str(), semantic.c_str(), float(Cohort().Metrics.Kills), Cohort().Config.ValidationRouteTargetEntry);
    }
    return true;
}


bool BotWorldPopulationMgr::RecordDefeatedValidationRouteTarget(
    Unit* defeatedTarget, char const* reason,
    std::function<bool(Creature const*)> const& isValidationRouteScriptTarget,
    std::function<bool(Unit*, char const*)> const& recordValidationRouteBossKill,
    std::function<bool(Unit*, char const*)> const& recordValidationRouteTrashKill)
{
    if (!defeatedTarget || defeatedTarget->IsAlive() || defeatedTarget->GetHealth())
        return false;

    if (Creature* creature = defeatedTarget->ToCreature())
    {
        bool persistedPackMember = Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
            && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID()) != Party().ValidationRoutePackMemberGuids.end();
        if (!isValidationRouteScriptTarget(creature) && !persistedPackMember)
            return false;

        return creature->IsDungeonBoss() || creature->isWorldBoss()
            ? recordValidationRouteBossKill(defeatedTarget, reason)
            : recordValidationRouteTrashKill(defeatedTarget, reason);
    }

    return false;
}

bool BotWorldPopulationMgr::RecordDefeatedValidationRoutePackMembers(
    Player* bot,
    std::function<bool(Unit*, char const*)> const& recordValidationRouteTrashKill)
{
    if (Cohort().Config.ValidationRouteKind == "boss" || !bot || !bot->GetMap()
        || Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration)
        return false;

    bool recorded = false;
    std::vector<ObjectGuid> memberGuids(Party().ValidationRoutePackMemberGuids.begin(), Party().ValidationRoutePackMemberGuids.end());
    for (ObjectGuid const& guid : memberGuids)
    {
        if (Party().ValidationRoutePackEngagedGuids.find(guid) == Party().ValidationRoutePackEngagedGuids.end()
            || Party().ValidationRoutePackDeathGuids.find(guid) != Party().ValidationRoutePackDeathGuids.end()
            || Party().ValidationRoutePackTransitionGuids.find(guid) != Party().ValidationRoutePackTransitionGuids.end())
            continue;
        if (Creature* creature = bot->GetMap()->GetCreature(guid); creature && !creature->IsAlive() && !creature->GetHealth())
            recorded = recordValidationRouteTrashKill(creature, "enrolled_member_seen_dead") || recorded;
    }
    return recorded;
}
