#ifndef TRINITY_BOT_MAGMAW_MOVEMENT_KERNEL_ADAPTER_H
#define TRINITY_BOT_MAGMAW_MOVEMENT_KERNEL_ADAPTER_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementKernelCandidate.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneKernelBridge.h"

#include <functional>
#include <optional>
#include <string>
#include <string_view>

namespace BotEncounter
{
struct MagmawParasiteHazardState;
struct MagmawPersonalParasiteEscapeTask;

struct MagmawMovementNativeLease
{
    BotMovementArbitration::Owner Owner =
        BotMovementArbitration::Owner::Mechanic;
    BotMovementArbitration::Priority Priority =
        BotMovementArbitration::Priority::Mechanic;
};

using MagmawMovementNativeExecutor = std::function<
    BotActionArbitration::Outcome(BotNativeAction::Intent const&,
        MagmawMovementNativeLease,
        BotWorldMovement::ExecutionObservation*)>;
using MagmawMovementCandidateObserver = std::function<void(
    BotActionArbitration::Kernel&, BotActionArbitration::Candidate const&,
    BotNativeAction::Candidate const&)>;
using MagmawMovementQueuedPredicate = std::function<bool(
    BotNativeAction::Candidate const&)>;

struct MagmawMovementNativeOutcome
{
    std::string CandidateKey;
    std::string Mechanic;
    ObjectGuid Actor;
    uint64 EventGeneration = 0;
    Vector3 Destination;
    BotActionArbitration::Outcome Result;
};

using MagmawMovementNativeOutcomeObserver = std::function<void(
    MagmawMovementNativeOutcome const&)>;

struct MagmawMovementKernelAdapterContext
{
    uint64 ObservedAtMs = 0;
    std::optional<MagmawTransferLaneExecutionBinding> TransferBinding;
    MagmawMovementNativeExecutor Execute;
    MagmawTransferLaneOutcomeObserver ObserveTransferOutcome;
    MagmawMovementNativeOutcomeObserver ObserveNativeOutcome;
    MagmawMovementCandidateObserver BeforeSubmit;
    MagmawMovementQueuedPredicate AlreadyQueued;
};

std::optional<MagmawMovementNativeLease> MagmawMovementNativeLeaseFor(
    std::string_view mechanic);

bool HasRetainedMagmawHazardOwnership(
    MagmawMovementIntentCollection const& movements,
    MagmawParasiteHazardState const& hazardState, ObjectGuid actor);

bool HasRetainedMagmawHazardOwnership(
    MagmawMovementIntentCollection const& movements,
    MagmawPersonalParasiteEscapeTask const& task, ObjectGuid actor);

// Shared final adapter used by the live manager and compiled fixtures. It
// submits every visible movement proposal to the real kernel, preserves typed
// transfer bindings, and hard-masks rejected or unmapped proposals.
size_t SubmitMagmawMovementKernelCandidates(
    BotActionArbitration::Kernel& kernel,
    MagmawMovementIntentCollection const& movements,
    MagmawMovementKernelAdapterContext context);
}

#endif
