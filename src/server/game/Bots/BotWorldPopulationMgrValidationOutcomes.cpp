#include "Bots/BotWorldPopulationMgr.h"

#include "GameTime.h"
#include "Player.h"
#include "Unit.h"

#include <chrono>
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

