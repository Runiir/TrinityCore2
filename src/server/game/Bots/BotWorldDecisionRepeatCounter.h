#ifndef BOT_WORLD_DECISION_REPEAT_COUNTER_H
#define BOT_WORLD_DECISION_REPEAT_COUNTER_H

#include <cstdint>
#include <string_view>

namespace BotWorldDecisionRepeatCounter
{
constexpr std::uint32_t Next(
    std::uint32_t previousCount,
    std::string_view previousSituation,
    std::string_view previousAction,
    std::string_view previousResult,
    std::string_view currentSituation,
    std::string_view currentAction,
    std::string_view currentResult)
{
    bool const sameDecision = previousSituation == currentSituation
        && previousAction == currentAction
        && previousResult == currentResult;
    return sameDecision ? previousCount + 1 : 1;
}
}

#endif
