#ifndef TRINITY_BOT_MAGMAW_TRANSFER_LANE_INTENT_H
#define TRINITY_BOT_MAGMAW_TRANSFER_LANE_INTENT_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneTask.h"
#include "Bots/Decision/BotIntentSink.h"

#include <cstddef>
#include <optional>
#include <string>

namespace BotEncounter
{
constexpr float MagmawTransferLaneIntentDestinationTolerance2d = 0.25f;
constexpr float MagmawTransferLaneIntentDestinationToleranceZ = 0.50f;
constexpr uint64 MagmawTransferLaneIntentFreshnessMs = 750;
constexpr float MagmawTransferLaneIntentUtility = 500.0f;

enum class MagmawTransferLaneIntentComparisonOutcome : uint8
{
    NeitherPresent,
    ShadowOnly,
    LegacyOnly,
    Equivalent,
    Divergent
};

enum class MagmawTransferLaneIntentDivergence : uint32
{
    None = 0,
    AmbiguousShadowMovement = 1u << 0,
    MissingExecutionContract = 1u << 1,
    StrategyIdentity = 1u << 2,
    MechanicIdentity = 1u << 3,
    LifecycleScope = 1u << 4,
    ActionKind = 1u << 5,
    Actor = 1u << 6,
    GenerationCorrelation = 1u << 7,
    MovementResource = 1u << 8,
    DestinationNonFinite = 1u << 9,
    Destination2d = 1u << 10,
    DestinationZ = 1u << 11,
    PreemptCasting = 1u << 12,
    ActionPriority = 1u << 13,
    Utility = 1u << 14,
    Expiry = 1u << 15
};

constexpr uint32 DivergenceMask(
    MagmawTransferLaneIntentDivergence reason)
{
    return uint32(reason);
}

struct MagmawTransferLaneExecutionContract
{
    std::string ScopeKey;
    ObjectGuid Actor;
    uint64 EpisodeGeneration = 0;
    uint64 TaskGeneration = 0;
    uint64 LegacyTransitionGeneration = 0;
    uint64 ObservedAtMs = 0;
    Vector3 Destination;
};

struct MagmawTransferLaneIntentComparison
{
    MagmawTransferLaneIntentComparisonOutcome Outcome =
        MagmawTransferLaneIntentComparisonOutcome::NeitherPresent;
    uint32 ProposalCount = 0;
    uint32 MovementProposalCount = 0;
    uint32 Divergences = 0;
    std::string ScopeKey;
    std::string ShadowCandidateKey;
    std::string LegacyCandidateKey;
    ObjectGuid ShadowActor;
    ObjectGuid LegacyActor;
    uint64 ShadowEpisodeGeneration = 0;
    uint64 ShadowTaskGeneration = 0;
    uint64 LegacyEventGeneration = 0;
    uint64 ExpectedLegacyTransitionGeneration = 0;
    Vector3 ShadowDestination;
    Vector3 LegacyDestination;
    bool ShadowDestinationAvailable = false;
    bool LegacyDestinationAvailable = false;
    uint64 ObservedAtMs = 0;
    bool Observed = false;

    bool Ambiguous() const { return MovementProposalCount > 1; }
    bool Has(MagmawTransferLaneIntentDivergence reason) const
    {
        return (Divergences & DivergenceMask(reason)) != 0;
    }
};

struct MagmawTransferLaneIntentEpisodeIdentity
{
    std::string ScopeKey;
    ObjectGuid Actor;
    uint64 EpisodeGeneration = 0;
    uint64 TaskGeneration = 0;

    friend bool operator==(MagmawTransferLaneIntentEpisodeIdentity const& left,
        MagmawTransferLaneIntentEpisodeIdentity const& right)
    {
        return left.ScopeKey == right.ScopeKey && left.Actor == right.Actor
            && left.EpisodeGeneration == right.EpisodeGeneration
            && left.TaskGeneration == right.TaskGeneration;
    }
};

struct MagmawTransferLaneIntentEpisodeSummary
{
    MagmawTransferLaneIntentEpisodeIdentity Id;
    uint32 ObservedCount = 0;
    uint32 EquivalentCount = 0;
    uint32 DivergentCount = 0;
    uint32 AmbiguousCount = 0;
    uint32 ShadowOnlyCount = 0;
    uint32 LegacyOnlyCount = 0;
    uint64 FirstObservedAtMs = 0;
    uint64 LastObservedAtMs = 0;
    std::string StableShadowCandidateKey;
    std::string StableLegacyCandidateKey;
    std::string LastShadowCandidateKey;
    std::string LastLegacyCandidateKey;
    Vector3 StableShadowDestination;
    Vector3 StableLegacyDestination;
    Vector3 LastShadowDestination;
    Vector3 LastLegacyDestination;
    bool StableShadowDestinationAvailable = false;
    bool StableLegacyDestinationAvailable = false;
    bool LastShadowDestinationAvailable = false;
    bool LastLegacyDestinationAvailable = false;
    uint32 ShadowKeyChangeCount = 0;
    uint32 LegacyKeyChangeCount = 0;
    uint32 ShadowDestinationChangeCount = 0;
    uint32 LegacyDestinationChangeCount = 0;
    std::optional<MagmawTransferLaneIntentComparison> FirstFailingComparison;
};

struct MagmawTransferLaneIntentEpisodeAccumulator
{
    static constexpr size_t MaxRetiredSummaries = 16;
    std::optional<MagmawTransferLaneIntentEpisodeSummary> Active;
    std::vector<MagmawTransferLaneIntentEpisodeSummary> Retired;
};

void ResetMagmawTransferLaneIntentComparison(
    MagmawTransferLaneIntentComparison& comparison);

MagmawTransferLaneExecutionContract MagmawTransferLaneContract(
    MagmawTransferLaneTask const& task, uint64 legacyTransitionGeneration);

void EmitMagmawTransferLaneTaskIntent(
    MagmawTransferLaneTask const& task, BotDecision::BotIntentSink& sink);

MagmawTransferLaneIntentComparison CompareMagmawTransferLaneIntents(
    std::vector<BotNativeAction::Candidate> const& shadowProposals,
    std::optional<BotNativeAction::Candidate> const& legacy,
    std::optional<MagmawTransferLaneExecutionContract> const& contract);

MagmawTransferLaneIntentComparison ObserveMagmawTransferLaneIntents(
    std::vector<MagmawTransferLaneTask> const& tasks, ObjectGuid actor,
    std::optional<BotNativeAction::Candidate> const& legacy,
    uint64 legacyTransitionGeneration);

std::string LegacyMagmawMovementDiagnosticCandidateKey(
    BotNativeAction::Candidate const& candidate);

void ObserveMagmawTransferLaneIntentEpisode(
    MagmawTransferLaneIntentEpisodeAccumulator& accumulator,
    MagmawTransferLaneIntentComparison const& comparison);
void ResetMagmawTransferLaneIntentEpisodeAccumulator(
    MagmawTransferLaneIntentEpisodeAccumulator& accumulator);

char const* ToString(MagmawTransferLaneIntentComparisonOutcome value);
}

#endif
