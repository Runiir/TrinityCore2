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
}

void BotWorldPopulationMgr::MarkValidationRouteTerminalAfterProgress(
    char const* reason, WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action, Unit*& target, float routeDistance)
{
    Party().ValidationRouteFocusGuid.Clear();
    Party().ValidationRouteFocusEntry = 0;
    Party().ValidationRouteFocusMapId = 0;
    Party().ValidationRouteFocusX = 0.0f;
    Party().ValidationRouteFocusY = 0.0f;
    Party().ValidationRouteFocusZ = 0.0f;
    Party().ValidationRouteFocusSeenMs = 0;
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
        cohortState.ValidationRouteAnchorOverrideValid = false;
        cohortState.ValidationRouteAnchorOverrideUntilMs = 0;
        cohortState.ValidationRouteAnchorOverrideReason.clear();
        cohortState.ValidationRouteTerminalState = true;
        cohortState.ValidationRouteTerminalAtMs = NowMs();
        cohortState.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
        cohortState.ValidationRouteTerminalReason = reason
            ? reason : "route_exhausted_after_progress";
        cohortState.LoopRecoveryCooldownUntilMs = NowMs() + 60000;
    }

    target = nullptr;
    state.LastNoProgressReason = reason
        ? reason : "route_exhausted_after_progress";
    situation = "normal_dungeon_trash";
    action = "validation_route_failed";
    std::string raw = BuildRawJson(bot, nullptr);
    std::string semantic = BuildSemanticJson(
        bot, nullptr, situation.c_str(), &power, stage, activity);
    RecordEvent(state, bot, "validation_route_recovery", nullptr,
        state.LastNoProgressReason.c_str(), raw.c_str(), semantic.c_str(),
        routeDistance, Cohort().Config.ValidationRouteTargetEntry);
}
