#include "Bots/BotWorldPopulationMgr.h"

#include "Player.h"
#include "SpellAuras.h"
#include "Unit.h"

#include <cstddef>
#include <utility>

namespace
{
constexpr size_t MaximumWillOfUnbindingTransitions = 256;
}

void BotWorldPopulationMgr::ObserveWillOfUnbinding(
    CalibrationMetrics& metrics, Player* bot, uint64 observedAtMs)
{
    if (!bot)
        return;

    CalibrationMetrics::WillOfUnbindingObservation& observation =
        metrics.WillOfUnbinding;
    Aura const* stackAura = bot->GetAura(observation.StackAuraSpellId);
    uint8 const currentStacks = stackAura ? stackAura->GetStackAmount() : 0;
    ++observation.ObservationSampleCount;
    if (!observation.Initialized)
    {
        observation.Initialized = true;
        observation.InitialStacks = currentStacks;
        observation.LastObservedStacks = currentStacks;
        observation.LastObservedAtMs = observedAtMs;
        return;
    }

    if (currentStacks == observation.LastObservedStacks)
    {
        observation.LastObservedAtMs = observedAtMs;
        return;
    }

    ++observation.StackTransitionCount;
    if (currentStacks > observation.LastObservedStacks)
        ++observation.StackIncreaseCount;
    else
        ++observation.StackDecreaseCount;

    if (observation.StackTransitions.size() < MaximumWillOfUnbindingTransitions)
    {
        CalibrationMetrics::EffectiveStatVector currentStats;
        ObserveCalibrationEffectiveStats(bot, observedAtMs, currentStats);
        CalibrationMetrics::WillOfUnbindingStackTransition transition;
        transition.ElapsedMs = metrics.WindowStartedMs && observedAtMs >= metrics.WindowStartedMs
            ? observedAtMs - metrics.WindowStartedMs : 0;
        transition.PreviousStacks = observation.LastObservedStacks;
        transition.CurrentStacks = currentStacks;
        transition.EffectiveIntellect = currentStats.Intellect;
        transition.EffectiveSpellPower = currentStats.SpellPower;
        observation.StackTransitions.push_back(std::move(transition));
    }

    observation.LastObservedStacks = currentStacks;
    observation.LastObservedAtMs = observedAtMs;
}
