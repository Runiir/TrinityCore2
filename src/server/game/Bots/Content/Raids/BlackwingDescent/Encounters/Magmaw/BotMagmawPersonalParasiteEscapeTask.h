#ifndef TRINITY_BOT_MAGMAW_PERSONAL_PARASITE_ESCAPE_TASK_H
#define TRINITY_BOT_MAGMAW_PERSONAL_PARASITE_ESCAPE_TASK_H

#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"
#include "Bots/Decision/BotPersistentTask.h"

#include <optional>
#include <string>
#include <string_view>

namespace BotEncounter
{
enum class MagmawPersonalParasiteEscapeFailure : uint8
{
    None,
    NoDistinctAlternate,
    NoSemanticProgress,
    AlternateNativeRouteRejected
};

// One actor owns one semantic escape for one authoritative parasite wave.
// Observed actor/hazard geometry is task input, never task identity.
struct MagmawPersonalParasiteEscapeTask
{
    std::string ScopeKey;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
    ObjectGuid ActorGuid;
    uint64 WaveGeneration = 0;
    bool WaveGenerationAuthoritative = false;
    uint64 NextLocalWaveToken = 0;
    uint64 NextCandidateGeneration = 0;
    uint64 CandidateGeneration = 0;
    ObjectGuid DangerGuid;
    Vector3 DangerPosition;
    Vector3 Destination;
    Vector3 PrimaryDestination;
    BotDecision::PersistentTaskState State =
        BotDecision::PersistentTaskState::Aborted;
    MagmawPersonalParasiteEscapeFailure Failure =
        MagmawPersonalParasiteEscapeFailure::None;
    bool Started = false;
    bool WaveEnded = true;
    bool AlternateUsed = false;
    bool AlternatePending = false;
    float BestClearance = 0.0f;
    float BestDistance = 0.0f;
    uint64 StartedAtMs = 0;
    uint64 LastProgressAtMs = 0;
    uint64 LastProgressRevision = 0;

    void ObserveScope(Blackboard const& board, ObjectGuid actor);

    std::optional<BotNativeAction::Candidate> Tick(
        Blackboard const& board, MagmawFacts const& facts,
        ActorSnapshot const& bot, ActorSnapshot const* personalThreat,
        float safeClearance, float arrivalTolerance, bool preemptCasting);

    bool ObserveNativeOutcome(ObjectGuid actor, uint64 candidateGeneration,
        Vector3 const& destination, std::string_view reason);

    bool OwnsMovement() const
    {
        return Started && State == BotDecision::PersistentTaskState::Running
            && !AlternatePending;
    }

    static bool IsPermanentNativeRejection(std::string_view reason);
    static bool SamePoint(Vector3 const& left, Vector3 const& right);
};
}

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPersonalParasiteEscapeTask.inl"

#endif
