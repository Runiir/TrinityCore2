#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_COHORT_SCOPE_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_COHORT_SCOPE_H

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace BotWorldCohortScope
{
template <class T>
class ScopedOverride final
{
public:
    ScopedOverride(T*& slot, T* next)
        : _slot(&slot), _previous(slot), _active(next != nullptr)
    {
        slot = next;
    }

    ScopedOverride(ScopedOverride const&) = delete;
    ScopedOverride& operator=(ScopedOverride const&) = delete;

    ScopedOverride(ScopedOverride&& other) noexcept
        : _slot(other._slot), _previous(other._previous),
          _active(other._active)
    {
        other._slot = nullptr;
        other._active = false;
    }

    ~ScopedOverride()
    {
        if (_slot)
            *_slot = _previous;
    }

    explicit operator bool() const { return _active; }

private:
    T** _slot;
    T* _previous;
    bool _active;
};

template <class T, class IsActive>
std::vector<T*> FreezeActive(std::vector<T*> const& runtimes,
    IsActive isActive)
{
    std::vector<T*> active;
    active.reserve(runtimes.size());
    for (T* runtime : runtimes)
        if (runtime && isActive(*runtime))
            active.push_back(runtime);
    return active;
}

struct RuntimeIdentity
{
    std::string CohortId;
    std::uint64_t ServerEpoch = 0;
    std::uint64_t AttemptId = 0;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    bool Active = false;
    bool ScopeKnown = false;
};

struct LeaseIdentity
{
    bool Observed = false;
    std::uint64_t ServerEpoch = 0;
    std::string CohortId;
    std::uint64_t AttemptId = 0;
};

struct ActorIdentity
{
    bool Present = false;
    bool RequiresLease = false;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    LeaseIdentity Lease;
};

enum class ResolutionStatus
{
    Resolved,
    MissingActor,
    MissingOwner,
    StaleLease,
    ConflictingOwners,
    MissingRuntime,
    InactiveRuntime,
    AttemptMismatch,
    MapInstanceMismatch,
    AmbiguousMapInstance
};

struct Resolution
{
    ResolutionStatus Status = ResolutionStatus::MissingActor;
    std::string CohortId;

    explicit operator bool() const
    {
        return Status == ResolutionStatus::Resolved;
    }
};

Resolution Resolve(std::uint64_t serverEpoch,
    std::vector<RuntimeIdentity> const& runtimes,
    std::vector<ActorIdentity> const& actors);

bool RequiresPlayerLease(bool actorIsPlayer, bool controlledByPlayer,
    bool controllerGuidIsPlayer, bool livePlayerOwner);

bool AllowsDiagnosticCleanup(std::uint64_t serverEpoch,
    std::string_view cohortId, std::uint64_t attemptId,
    LeaseIdentity const& observedLease);

bool AllowsConcurrentAdmission(std::uint32_t activeCohorts,
    std::uint32_t maximumActiveCohorts, std::uint32_t mapWorkerThreads);

bool MatchesPendingOwnership(std::string_view pendingCohortId,
    std::uint64_t pendingAttemptId, std::string_view currentCohortId,
    std::uint64_t currentAttemptId);
}

#endif
