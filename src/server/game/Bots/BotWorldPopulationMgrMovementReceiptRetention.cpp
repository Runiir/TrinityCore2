#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"

#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"

namespace BotWorldMovement
{
void MovementPlannerDiagnosticSidecar::RetainRejectedHazard(
    MovementPlannerObservation const& observation)
{
    if (!observation.LaunchReceipt.Id
        || observation.MovementOwner
            != BotMovementArbitration::Owner::Hazard
        || observation.PlannerResult != "rejected")
        return;

    auto& pending = _rejectedHazardsByGuid[observation.BotGuid];
    for (MovementPlannerObservation& retained : pending)
        if (retained.LaunchReceipt.Id == observation.LaunchReceipt.Id)
        {
            retained = observation;
            return;
        }
    pending.push_back(observation);
    while (pending.size() > MaxTraceHistory)
        pending.pop_front();
}

void MovementPlannerDiagnosticSidecar::RetainCompleteHazardRetry(
    MovementPlannerObservation const& observation,
    NativePathProofObservation const* nativeProof, bool accepted)
{
    if (!observation.LaunchReceipt.ProgressCaptureEnabled
        || observation.MovementOwner != BotMovementArbitration::Owner::Hazard
        || !nativeProof || !nativeProof->Available || !nativeProof->Calculated)
        return;

    std::uint64_t const botGuid = observation.BotGuid;
    std::uint64_t const fingerprint =
        observation.LaunchReceipt.IntentFingerprint;
    if (!nativeProof->Complete)
    {
        _incompleteHazardFingerprintByGuid[botGuid] = fingerprint;
        return;
    }

    auto incomplete = _incompleteHazardFingerprintByGuid.find(botGuid);
    if (!accepted || incomplete == _incompleteHazardFingerprintByGuid.end()
        || incomplete->second != fingerprint)
        return;

    MovementProgressDiagnostics().RequestRetention(
        observation.LaunchReceipt.Id, botGuid);
    _incompleteHazardFingerprintByGuid.erase(incomplete);
}
}
