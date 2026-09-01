#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneAuthority.h"

namespace BotEncounter
{
namespace
{
MagmawTransferLaneTask const* UniqueRunningTask(
    std::vector<MagmawTransferLaneTask> const& tasks, ObjectGuid actor)
{
    MagmawTransferLaneTask const* match = nullptr;
    for (MagmawTransferLaneTask const& task : tasks)
        if (task.Id.ActorGuid == actor
            && task.State == BotDecision::PersistentTaskState::Running)
        {
            if (match)
                return nullptr;
            match = &task;
        }
    return match;
}

std::optional<BotNativeAction::Candidate> UniqueTaskMovement(
    MagmawTransferLaneTask const& task)
{
    BotDecision::BotIntentSink sink;
    EmitMagmawTransferLaneTaskIntent(task, sink);
    if (sink.Proposals().size() != 1)
        return std::nullopt;
    BotNativeAction::Candidate const& candidate = sink.Proposals().front();
    if (!std::get_if<BotNativeAction::Move>(&candidate.Action))
        return std::nullopt;
    return candidate;
}

MagmawTransferLaneExecutionBinding BuildBinding(
    MagmawTransferLaneTask const& task,
    BotNativeAction::Candidate const& selected,
    uint64 legacyTransitionGeneration,
    MagmawTransferLaneAuthoritySource source)
{
    return { task.Id.Episode.Lifecycle.Key(), task.Id.ActorGuid,
        task.Id.Episode.EpisodeGeneration, task.Id.TaskGeneration,
        legacyTransitionGeneration, source, selected.Id.Key(),
        task.Destination };
}
}

MagmawTransferLaneAuthoritySelection SelectMagmawTransferLaneAuthority(
    bool taskAuthorityEnabled,
    std::vector<MagmawTransferLaneTask> const& tasks, ObjectGuid actor,
    MagmawMovementIntentCollection const& legacyMovements,
    uint64 legacyTransitionGeneration)
{
    size_t matchingIndex = 0;
    BotNativeAction::Candidate const* matchingLegacy = nullptr;
    uint32 matchingCount = 0;
    for (size_t index = 0; index < legacyMovements.Size(); ++index)
    {
        BotNativeAction::Candidate const& candidate =
            legacyMovements.Proposals()[index];
        if (candidate.Id.Actor != actor
            || LegacyMagmawMovementDiagnosticCandidateKey(candidate).empty())
            continue;
        ++matchingCount;
        matchingIndex = index;
        matchingLegacy = &candidate;
    }

    std::optional<BotNativeAction::Candidate> legacy;
    if (matchingCount == 1)
        legacy = *matchingLegacy;
    MagmawTransferLaneAuthoritySelection result =
        SelectMagmawTransferLaneAuthority(taskAuthorityEnabled, tasks, actor,
            legacy, legacyTransitionGeneration);
    result.Movements = legacyMovements;
    if (result.TaskAuthoritySelected && result.Movement)
        result.Movements.Replace(matchingIndex,
            MagmawMovementProposalOrigin::TransferLaneTask,
            *result.Movement);
    return result;
}

MagmawTransferLaneAuthoritySelection SelectMagmawTransferLaneAuthority(
    bool taskAuthorityEnabled,
    std::vector<MagmawTransferLaneTask> const& tasks, ObjectGuid actor,
    std::optional<BotNativeAction::Candidate> const& legacy,
    uint64 legacyTransitionGeneration)
{
    MagmawTransferLaneAuthoritySelection result;
    result.TaskAuthorityRequested = taskAuthorityEnabled;
    // This assignment is the default-off compatibility contract: no field in
    // the legacy candidate is reconstructed or normalized.
    result.Movement = legacy;
    result.Comparison = ObserveMagmawTransferLaneIntents(tasks, actor, legacy,
        legacyTransitionGeneration);

    MagmawTransferLaneTask const* task = UniqueRunningTask(tasks, actor);
    if (!task || !legacy
        || result.Comparison.Outcome
            != MagmawTransferLaneIntentComparisonOutcome::Equivalent)
        return result;

    std::optional<BotNativeAction::Candidate> taskMovement =
        UniqueTaskMovement(*task);
    if (!taskMovement)
        return result;

    BotNativeAction::Candidate const& selected = taskAuthorityEnabled
        ? *taskMovement : *legacy;
    MagmawTransferLaneAuthoritySource const source = taskAuthorityEnabled
        ? MagmawTransferLaneAuthoritySource::Task
        : MagmawTransferLaneAuthoritySource::Legacy;
    result.Binding = BuildBinding(*task, selected,
        legacyTransitionGeneration, source);
    if (taskAuthorityEnabled)
    {
        result.Movement = std::move(taskMovement);
        result.TaskAuthoritySelected = true;
    }
    return result;
}

MagmawTransferLaneNativeOutcome BindMagmawTransferLaneNativeOutcome(
    MagmawTransferLaneExecutionBinding const& binding,
    BotWorldMovement::ExecutionObservation const& movement,
    uint64 observedAtMs)
{
    return { binding, movement, observedAtMs };
}
}
