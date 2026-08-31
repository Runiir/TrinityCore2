#ifndef TRINITY_BOT_MAGMAW_TRANSFER_LANE_TASK_H
#define TRINITY_BOT_MAGMAW_TRANSFER_LANE_TASK_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneMovementObservation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawRaidPlan.h"
#include "Bots/Decision/BotPersistentTask.h"

#include <memory>
#include <optional>
#include <vector>

namespace BotEncounter
{
enum class MagmawTransferLaneDirection : uint8
{
    None,
    Left,
    Right
};

enum class MagmawTransferLaneFailure : uint8
{
    None,
    NoSemanticProgress
};

enum class MagmawTransferLaneRetirement : uint8
{
    None,
    EncounterLifecycleChanged,
    RaidPlanChanged,
    AssignmentChanged,
    MechanicGenerationAdvanced,
    ActorLifeChanged,
    ActorDied
};

struct MagmawActorLifeIdentity
{
    uint64 WipeGeneration = 0;
    uint64 DeathSequence = 0;
    uint64 ResurrectionSequence = 0;
    bool Authoritative = false;

    friend bool operator==(MagmawActorLifeIdentity const& left,
        MagmawActorLifeIdentity const& right)
    {
        return left.WipeGeneration == right.WipeGeneration
            && left.DeathSequence == right.DeathSequence
            && left.ResurrectionSequence == right.ResurrectionSequence
            && left.Authoritative == right.Authoritative;
    }
};

struct MagmawTransferLaneEpisodeIdentity
{
    Scope Lifecycle;
    NativeEncounterLifecycle Encounter;
    uint64 RaidPlanGeneration = 0;
    uint64 RosterGeneration = 0;
    uint64 FireMageAssignmentGeneration = 0;
    uint64 HunterAssignmentGeneration = 0;
    uint64 MechanicGeneration = 0;
    uint64 EpisodeGeneration = 0;
};

struct MagmawTransferLaneEpisode
{
    MagmawTransferLaneEpisodeIdentity Id;
    ObjectGuid FireMageGuid;
    ObjectGuid HunterGuid;
    MagmawTransferLaneDirection Direction =
        MagmawTransferLaneDirection::None;
    Vector3 Destination;
    uint64 CreatedAtRevision = 0;
};

struct MagmawTransferLaneTaskIdentity
{
    MagmawTransferLaneEpisodeIdentity Episode;
    ObjectGuid ActorGuid;
    MagmawActorLifeIdentity ActorLife;
    uint64 TaskGeneration = 0;
};

struct MagmawTransferLaneTask
{
    MagmawTransferLaneTaskIdentity Id;
    Vector3 Destination;
    BotDecision::PersistentTaskState State =
        BotDecision::PersistentTaskState::Running;
    BotDecision::PersistentTaskSuspension Suspension =
        BotDecision::PersistentTaskSuspension::None;
    MagmawTransferLaneFailure Failure = MagmawTransferLaneFailure::None;
    float InitialDistance = 0.0f;
    float BestDistance = 0.0f;
    float LastDistance = 0.0f;
    uint64 StartedAtMs = 0;
    uint64 LastProgressAtMs = 0;
    uint64 LastObservedAtMs = 0;
    uint64 SuspendedAtMs = 0;
    uint64 ProgressRevision = 0;
    uint32 ObservationSamples = 0;
    uint32 ProgressSamples = 0;
    MagmawTransferLaneMovementDisposition MovementDisposition =
        MagmawTransferLaneMovementDisposition::NoLease;
};

struct MagmawRetiredTransferLaneTask
{
    MagmawTransferLaneTask Task;
    MagmawTransferLaneRetirement Reason =
        MagmawTransferLaneRetirement::None;
    uint64 RetiredAtRevision = 0;
};

struct MagmawTransferLaneActorObservation
{
    ObjectGuid Guid;
    MagmawActorLifeIdentity Life;
    Vector3 Position;
    bool PositionObserved = false;
    bool Alive = false;
    MagmawTransferLaneMovementObservation Movement;
};

class MagmawTransferLaneTaskShadow
{
public:
    static constexpr float ArrivalTolerance = 4.0f;
    static constexpr float ProgressEpsilon = 0.5f;
    static constexpr uint64 NoProgressFailureMs = 5000;

    static std::shared_ptr<MagmawTransferLaneTaskShadow const> Reconcile(
        std::shared_ptr<MagmawTransferLaneTaskShadow const> const& current,
        MagmawFacts const& facts, Blackboard const& board,
        MagmawRaidPlan const& plan,
        std::vector<MagmawTransferLaneActorObservation> const& actors);

    uint64 SourceRevision() const { return _sourceRevision; }
    std::optional<MagmawTransferLaneEpisode> const& Episode() const
    {
        return _episode;
    }
    std::vector<MagmawTransferLaneTask> const& Tasks() const
    {
        return _tasks;
    }
    std::vector<MagmawRetiredTransferLaneTask> const& Retired() const
    {
        return _retired;
    }

private:
    uint64 _sourceRevision = 0;
    uint64 _nextEpisodeGeneration = 0;
    uint64 _nextTaskGeneration = 0;
    std::optional<MagmawTransferLaneEpisode> _episode;
    std::vector<MagmawTransferLaneTask> _tasks;
    std::vector<MagmawRetiredTransferLaneTask> _retired;
};

char const* ToString(MagmawTransferLaneDirection value);
char const* ToString(MagmawTransferLaneFailure value);
char const* ToString(MagmawTransferLaneRetirement value);
char const* ToString(BotDecision::PersistentTaskState value);
char const* ToString(BotDecision::PersistentTaskSuspension value);
}

#endif
