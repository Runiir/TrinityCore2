#ifndef TRINITY_BOT_MAGMAW_TRANSFER_LANE_INTENT_H
#define TRINITY_BOT_MAGMAW_TRANSFER_LANE_INTENT_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneTask.h"
#include "Bots/Decision/BotIntentSink.h"

#include <cmath>
#include <optional>
#include <variant>

namespace BotEncounter
{
constexpr float MagmawTransferLaneIntentDestinationTolerance2d = 0.25f;

enum class MagmawTransferLaneIntentComparisonOutcome : uint8
{
    NeitherPresent,
    ShadowOnly,
    LegacyOnly,
    Equivalent,
    Divergent
};

enum class MagmawTransferLaneIntentDivergence : uint8
{
    None = 0,
    AmbiguousShadowMovement = 1 << 0,
    ActionKind = 1 << 1,
    Actor = 1 << 2,
    MovementResource = 1 << 3,
    Destination2d = 1 << 4,
    UnhandledDestination = 1 << 5
};

constexpr uint8 DivergenceMask(MagmawTransferLaneIntentDivergence reason)
{
    return uint8(reason);
}

struct MagmawTransferLaneIntentComparison
{
    MagmawTransferLaneIntentComparisonOutcome Outcome =
        MagmawTransferLaneIntentComparisonOutcome::NeitherPresent;
    uint32 ProposalCount = 0;
    uint32 MovementProposalCount = 0;
    uint8 Divergences = 0;
    ObjectGuid ShadowActor;
    ObjectGuid LegacyActor;
    uint64 ShadowTaskGeneration = 0;
    bool Observed = false;

    bool Ambiguous() const
    {
        return MovementProposalCount > 1;
    }

    bool Has(MagmawTransferLaneIntentDivergence reason) const
    {
        return (Divergences & DivergenceMask(reason)) != 0;
    }
};

inline void ResetMagmawTransferLaneIntentComparison(
    MagmawTransferLaneIntentComparison& comparison)
{
    comparison = {};
}

inline void EmitMagmawTransferLaneTaskIntent(
    MagmawTransferLaneTask const& task, BotDecision::BotIntentSink& sink)
{
    if (task.State != BotDecision::PersistentTaskState::Running)
        return;

    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = task.Id.Episode.Lifecycle.Key();
    candidate.Id.Strategy = "magmaw_transfer_lane_task_shadow";
    candidate.Id.Mechanic = "transfer_lane";
    candidate.Id.Actor = task.Id.ActorGuid;
    candidate.Id.EventGeneration = task.Id.TaskGeneration;
    candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
    candidate.Action = BotNativeAction::Move{ task.Destination.X,
        task.Destination.Y, task.Destination.Z,
        "magmaw_transfer_lane_task_shadow" };
    sink.Propose(std::move(candidate));
}

inline bool IsMovementProposal(BotNativeAction::Candidate const& candidate)
{
    return BotActionArbitration::Conflicts(candidate.Resources(),
        BotActionArbitration::Uses(BotActionArbitration::Resource::Movement));
}

inline std::optional<Vector3> IntentDestination(
    BotNativeAction::Intent const& intent)
{
    if (auto const* move = std::get_if<BotNativeAction::Move>(&intent))
        return Vector3{ move->X, move->Y, move->Z };
    if (auto const* mobility =
            std::get_if<BotNativeAction::DirectionalMobility>(&intent))
        return Vector3{ mobility->X, mobility->Y, mobility->Z };
    return std::nullopt;
}

inline uint8 CompareMagmawIntentDestinations(
    BotNativeAction::Candidate const& shadow,
    BotNativeAction::Candidate const& legacy)
{
    std::optional<Vector3> const shadowDestination =
        IntentDestination(shadow.Action);
    std::optional<Vector3> const legacyDestination =
        IntentDestination(legacy.Action);
    if (!shadowDestination || !legacyDestination)
        return DivergenceMask(
            MagmawTransferLaneIntentDivergence::UnhandledDestination);
    bool const diverges = std::hypot(
        shadowDestination->X - legacyDestination->X,
        shadowDestination->Y - legacyDestination->Y)
        > MagmawTransferLaneIntentDestinationTolerance2d;
    return diverges ? DivergenceMask(
        MagmawTransferLaneIntentDivergence::Destination2d) : 0;
}

inline uint8 ComparePresentMagmawTransferLaneIntents(
    BotNativeAction::Candidate const& shadow,
    BotNativeAction::Candidate const& legacy)
{
    uint8 divergences = 0;
    if (shadow.Action.index() != legacy.Action.index())
        divergences |= DivergenceMask(
            MagmawTransferLaneIntentDivergence::ActionKind);
    if (shadow.Id.Actor != legacy.Id.Actor)
        divergences |= DivergenceMask(
            MagmawTransferLaneIntentDivergence::Actor);
    BotActionArbitration::ResourceMask const movement =
        BotActionArbitration::Uses(BotActionArbitration::Resource::Movement);
    if (shadow.Resources() != movement || legacy.Resources() != movement)
        divergences |= DivergenceMask(
            MagmawTransferLaneIntentDivergence::MovementResource);
    divergences |= CompareMagmawIntentDestinations(shadow, legacy);
    return divergences;
}

inline MagmawTransferLaneIntentComparison CompareMagmawTransferLaneIntents(
    std::vector<BotNativeAction::Candidate> const& shadowProposals,
    std::optional<BotNativeAction::Candidate> const& legacy)
{
    MagmawTransferLaneIntentComparison result;
    result.Observed = true;
    result.ProposalCount = shadowProposals.size();
    BotNativeAction::Candidate const* shadowMovement = nullptr;
    for (BotNativeAction::Candidate const& proposal : shadowProposals)
        if (IsMovementProposal(proposal))
        {
            ++result.MovementProposalCount;
            shadowMovement = result.MovementProposalCount == 1
                ? &proposal : nullptr;
        }

    if (result.Ambiguous())
    {
        result.Outcome = MagmawTransferLaneIntentComparisonOutcome::Divergent;
        result.Divergences |= DivergenceMask(
            MagmawTransferLaneIntentDivergence::AmbiguousShadowMovement);
        return result;
    }
    if (!shadowMovement && !legacy)
        return result;
    if (shadowMovement && !legacy)
    {
        result.Outcome = MagmawTransferLaneIntentComparisonOutcome::ShadowOnly;
        result.ShadowActor = shadowMovement->Id.Actor;
        result.ShadowTaskGeneration = shadowMovement->Id.EventGeneration;
        return result;
    }
    if (!shadowMovement)
    {
        result.Outcome = MagmawTransferLaneIntentComparisonOutcome::LegacyOnly;
        result.LegacyActor = legacy->Id.Actor;
        return result;
    }

    result.ShadowActor = shadowMovement->Id.Actor;
    result.LegacyActor = legacy->Id.Actor;
    result.ShadowTaskGeneration = shadowMovement->Id.EventGeneration;
    result.Divergences = ComparePresentMagmawTransferLaneIntents(
        *shadowMovement, *legacy);
    result.Outcome = result.Divergences
        ? MagmawTransferLaneIntentComparisonOutcome::Divergent
        : MagmawTransferLaneIntentComparisonOutcome::Equivalent;
    return result;
}

inline MagmawTransferLaneIntentComparison ObserveMagmawTransferLaneIntents(
    std::vector<MagmawTransferLaneTask> const& tasks, ObjectGuid actor,
    std::optional<BotNativeAction::Candidate> const& legacy)
{
    BotDecision::BotIntentSink shadowSink;
    for (MagmawTransferLaneTask const& task : tasks)
        if (task.Id.ActorGuid == actor)
            EmitMagmawTransferLaneTaskIntent(task, shadowSink);
    return CompareMagmawTransferLaneIntents(shadowSink.Proposals(), legacy);
}

inline char const* ToString(MagmawTransferLaneIntentComparisonOutcome value)
{
    switch (value)
    {
        case MagmawTransferLaneIntentComparisonOutcome::ShadowOnly:
            return "shadow_only";
        case MagmawTransferLaneIntentComparisonOutcome::LegacyOnly:
            return "legacy_only";
        case MagmawTransferLaneIntentComparisonOutcome::Equivalent:
            return "equivalent";
        case MagmawTransferLaneIntentComparisonOutcome::Divergent:
            return "divergent";
        default: return "neither_present";
    }
}
}

#endif
