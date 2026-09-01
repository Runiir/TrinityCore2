#ifndef TRINITY_BOT_MAGMAW_PERSONAL_PARASITE_ESCAPE_TASK_H
#define TRINITY_BOT_MAGMAW_PERSONAL_PARASITE_ESCAPE_TASK_H

#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMoveAwayGeometry.h"
#include "Bots/Decision/BotPersistentTask.h"

#include <optional>
#include <string>
#include <string_view>

namespace BotEncounter
{
enum class MagmawPersonalParasiteEscapeFailure : uint8
{
    None,
    InfectedBeforeClearance,
    NoDistinctAlternate,
    NoSemanticProgress,
    AlternateNativeRouteRejected
};

enum class MagmawPersonalParasiteEscapeLifecycle : uint8
{
    Inactive,
    TaskCreated,
    AwaitingAuthoritativeFacts,
    CandidateBuilt,
    Submitted,
    NativeProgress,
    SafeClearance,
    Infected,
    Failed
};

enum class MagmawPersonalParasiteAuthorityGap : uint32
{
    None = 0,
    ObservationRevision = 1 << 0,
    LifecycleScope = 1 << 1,
    LifecycleAuthority = 1 << 2,
    ProjectionAuthority = 1 << 3,
    ParasiteAuthority = 1 << 4,
    ParasiteSource = 1 << 5
};

struct MagmawParasiteWaveTask
{
    std::string ScopeKey;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
    uint64 Generation = 0;
    bool GenerationAuthoritative = false;
    bool Active = false;
    bool AwaitingAuthoritativeFacts = false;
    uint64 NextGeneration = 0;
    uint64 CreatedAtMs = 0;
    uint64 LastObservedAtMs = 0;

    void ObserveScope(Blackboard const& board);
    void Reconcile(Blackboard const& board, MagmawFacts const& facts,
        bool personalThreatObserved);
};

struct MagmawPersonalParasiteEscapeDiagnostics
{
    uint64 TaskGeneration = 0;
    MagmawPersonalParasiteEscapeLifecycle Lifecycle =
        MagmawPersonalParasiteEscapeLifecycle::Inactive;
    uint32 ObservedLifecycleMask = 0;
    uint32 AuthorityGapMask = 0;
    uint64 CreatedAtMs = 0;
    uint64 AwaitingFactsAtMs = 0;
    uint64 CandidateBuiltAtMs = 0;
    uint64 SubmittedAtMs = 0;
    uint64 NativeProgressAtMs = 0;
    uint64 TerminalAtMs = 0;
    std::string CandidateKey;
    std::string LastNativeReason;
    uint64 NativeOutcomeCount = 0;
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
    MagmawParasiteWaveTask LocalWave;
    uint64 NextTaskGeneration = 0;
    uint64 TaskGeneration = 0;
    uint64 NextCandidateGeneration = 0;
    uint64 CandidateGeneration = 0;
    uint64 CandidateExpiresAtMs = 0;
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
    bool ActorLifeObserved = false;
    bool ActorAlive = false;
    uint64 ActorLifeGeneration = 0;
    bool AlternateUsed = false;
    bool AlternatePending = false;
    float BestClearance = 0.0f;
    float BestDistance = 0.0f;
    uint64 StartedAtMs = 0;
    uint64 LastProgressAtMs = 0;
    uint64 LastProgressRevision = 0;
    MagmawPersonalParasiteEscapeDiagnostics Diagnostics;

    void ObserveScope(Blackboard const& board, ObjectGuid actor);
    void ObserveActorLife(Blackboard const& board, ObjectGuid actor,
        bool alive);

    std::optional<BotNativeAction::Candidate> Tick(
        Blackboard const& board, MagmawFacts const& facts,
        ActorSnapshot const& bot, ActorSnapshot const* personalThreat,
        float safeClearance, float arrivalTolerance, bool preemptCasting,
        MagmawParasiteWaveTask* sharedWave = nullptr);

    bool ObserveNativeOutcome(ObjectGuid actor, uint64 candidateGeneration,
        Vector3 const& destination, std::string_view candidateKey,
        BotActionArbitration::Phase phase, std::string_view reason,
        uint64 observedAtMs);

    bool OwnsMovement() const
    {
        return Started && State == BotDecision::PersistentTaskState::Running
            && !AlternatePending;
    }

    static bool IsPermanentNativeRejection(std::string_view reason);
    static bool SamePoint(Vector3 const& left, Vector3 const& right);
    static bool HasParasiticInfection(ActorSnapshot const& actor);

    void MarkLifecycle(MagmawPersonalParasiteEscapeLifecycle lifecycle,
        uint64 observedAtMs);
};

char const* ToString(MagmawPersonalParasiteEscapeLifecycle value);
char const* ToString(MagmawPersonalParasiteEscapeFailure value);
}

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPersonalParasiteEscapeTask.inl"

#endif
