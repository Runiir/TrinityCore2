#ifndef TRINITY_BOT_MAGMAW_FACTS_H
#define TRINITY_BOT_MAGMAW_FACTS_H

#include "Bots/BotEncounterBlackboard.h"

#include <memory>
#include <utility>
#include <vector>

namespace BotEncounter
{
enum class MagmawTruth : uint8
{
    Unknown,
    False,
    True
};

enum class MagmawPhase : uint8
{
    Unknown,
    Prepull,
    Combat,
    Recovery,
    Completed
};

enum class MagmawGenerationKind : uint8
{
    Unknown,
    ObservationEdge
};

struct MagmawTypedGeneration
{
    MagmawGenerationKind Kind = MagmawGenerationKind::Unknown;
    uint64 Value = 0;
    FactSource Source = FactSource::VisibleUnitState;

    bool Authoritative() const
    {
        return Kind != MagmawGenerationKind::Unknown;
    }
};

struct MagmawActorFact
{
    ObjectGuid Guid;
    uint32 Entry = 0;
    Vector3 Position;
    FactSource Source = FactSource::VisibleUnitState;

    friend bool operator==(MagmawActorFact const& left,
        MagmawActorFact const& right)
    {
        return left.Guid == right.Guid && left.Entry == right.Entry
            && left.Position.X == right.Position.X
            && left.Position.Y == right.Position.Y
            && left.Position.Z == right.Position.Z
            && left.Source == right.Source;
    }
};

struct MagmawSignal
{
    MagmawTruth Active = MagmawTruth::Unknown;
    bool ObservedPresent = false;
    bool Authoritative = false;
    MagmawTypedGeneration Generation;
    FactSource EvidenceSource = FactSource::VisibleUnitState;
    std::vector<MagmawActorFact> Sources;
};

// Value-only, cohort-shared observation. Actor-relative distance and nearest
// selection deliberately remain in the existing per-actor strategy.
struct MagmawFacts
{
    Scope Lifecycle;
    uint64 ObservationRevision = 0;
    bool CacheScopeComplete = false;
    bool LifecycleAuthoritative = false;
    bool EncounterIdentityAuthoritative = false;
    bool EncounterEpochAuthoritative = false;
    bool ProjectionAuthoritative = false;
    bool ArenaObservationAuthoritative = false;
    MagmawTruth OwnsNode = MagmawTruth::Unknown;
    FactSource OwnershipSource = FactSource::RouteManifest;
    MagmawPhase Phase = MagmawPhase::Unknown;
    bool PhaseAuthoritative = false;
    MagmawTruth Prepull = MagmawTruth::Unknown;
    std::vector<MagmawActorFact> Bosses;
    bool BossIdentityAuthoritative = false;
    std::vector<MagmawActorFact> Heads;
    bool HeadIdentityAuthoritative = false;
    MagmawTruth BossInteractable = MagmawTruth::Unknown;
    bool BossInteractableAuthoritative = false;
    MagmawTruth HeadExposed = MagmawTruth::Unknown;
    bool HeadExposureAuthoritative = false;
    ObjectGuid ExposedHeadGuid;
    bool ExposedHeadIdentityAuthoritative = false;
    MagmawSignal Pillar;
    MagmawSignal Crash;
    MagmawSignal PincerWarning;
    MagmawSignal PincerVehicles;
    MagmawSignal Parasites;
    ObjectGuid MangleOwnerGuid;
    bool MangleOwnerAuthoritative = false;
    MagmawTruth WipeLocked = MagmawTruth::Unknown;
};

class MagmawFactsReducer
{
public:
    static MagmawFacts Reduce(Blackboard const& board);
};

// BotWorldPopulationMgr stores only a shared_ptr to this forward-declared
// type. The full projection therefore does not fan out through its header.
class MagmawFactsCache
{
public:
    static std::shared_ptr<MagmawFactsCache const> ForSnapshot(
        std::shared_ptr<MagmawFactsCache const> const& current,
        Blackboard const& snapshot);

    bool Matches(Scope const& scope, uint64 revision) const;
    MagmawFacts const& Facts() const { return _facts; }

private:
    struct EdgeCounters
    {
        uint64 Pillar = 0;
        uint64 Crash = 0;
        uint64 PincerWarning = 0;
        uint64 PincerVehicles = 0;
        uint64 Parasites = 0;
    };

    MagmawFactsCache(MagmawFacts facts, EdgeCounters counters)
        : _facts(std::move(facts)), _counters(counters) { }

    MagmawFacts _facts;
    EdgeCounters _counters;
};
}

#endif
