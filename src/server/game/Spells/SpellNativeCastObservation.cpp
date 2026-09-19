#include "SpellNativeCastObservation.h"

#include <utility>

namespace SpellNativeCastObservationOps
{
void BeginNextTerminalIfComplete(SpellNativeCastObservation& observation)
{
    if (!observation.FinishingObserved)
        return;
    observation.FinishingObserved = false;
    observation.Finished = false;
    observation.Success = false;
    observation.NativeFailureResultAvailable = false;
    observation.MovementCheckAvailable = false;
    observation.TerminalSource = "unknown";
    observation.CancellationOwner = "unknown";
    observation.CancellationOwnerAvailable = false;
    observation.TerminalTargetGuid.Clear();
    observation.TerminalTargetPresenceAvailable = false;
    observation.TerminalTargetAliveAvailable = false;
    observation.TerminalTargetAttackabilityAvailable = false;
    observation.TerminalTargetPresent = false;
    observation.TerminalTargetAlive = false;
    observation.TerminalTargetAttackable = false;
    observation.PriorState = 0;
    observation.FinishedAtMs = 0;
    observation.TerminalScopeJson.clear();
}

void SetSubmittedTarget(SpellNativeCastObservation& observation,
    ObjectGuid submittedTargetGuid)
{
    observation.SubmittedTargetGuid = submittedTargetGuid;
}

void MarkPrepared(SpellNativeCastObservation& observation,
    std::string sourceScopeJson, std::uint64_t observedAtMs)
{
    if (observation.Prepared)
        return;
    observation.Prepared = true;
    observation.PreparedAtMs = observedAtMs;
    observation.SourceScopeJson = std::move(sourceScopeJson);
}

void RecordResult(SpellNativeCastObservation& observation,
    std::uint32_t result, std::uint32_t successResult)
{
    BeginNextTerminalIfComplete(observation);
    if (result == successResult)
        return;
    observation.NativeFailureResultAvailable = true;
    observation.LastNativeFailureResult = result;
}

void MarkUpdate(SpellNativeCastObservation& observation, char const* source,
    std::uint32_t movementResult)
{
    BeginNextTerminalIfComplete(observation);
    if (source && *source)
        observation.TerminalSource = source;
    if (movementResult)
    {
        observation.MovementCheckAvailable = true;
        observation.MovementCheckResult = movementResult;
    }
}

void MarkCancelled(SpellNativeCastObservation& observation)
{
    BeginNextTerminalIfComplete(observation);
    if (observation.TerminalSource == "unknown")
        observation.TerminalSource = "cancel";
    observation.CancellationOwner = "unknown";
    observation.CancellationOwnerAvailable = false;
}

void MarkFinishing(SpellNativeCastObservation& observation, bool success,
    ObjectGuid terminalTargetGuid, bool terminalTargetPresent,
    bool terminalTargetAliveAvailable, bool terminalTargetAlive,
    bool terminalTargetAttackabilityAvailable, bool terminalTargetAttackable,
    std::uint32_t priorState, std::string terminalScopeJson,
    std::uint64_t observedAtMs)
{
    BeginNextTerminalIfComplete(observation);
    observation.TerminalTargetGuid = terminalTargetGuid;
    observation.TerminalTargetPresenceAvailable = true;
    observation.TerminalTargetPresent = terminalTargetPresent;
    observation.TerminalTargetAliveAvailable = terminalTargetAliveAvailable;
    observation.TerminalTargetAlive = terminalTargetAlive;
    observation.TerminalTargetAttackabilityAvailable =
        terminalTargetAttackabilityAvailable;
    observation.TerminalTargetAttackable = terminalTargetAttackable;
    observation.PriorState = priorState;
    observation.FinishingObserved = true;
    observation.Finished = true;
    observation.Success = success;
    ++observation.TerminalOrdinal;
    observation.FinishedAtMs = observedAtMs;
    observation.TerminalScopeJson = std::move(terminalScopeJson);
    if (observation.TerminalSource == "unknown")
        observation.TerminalSource = "finish";
}
}
