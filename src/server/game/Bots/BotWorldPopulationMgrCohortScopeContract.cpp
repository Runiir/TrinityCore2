#include "Bots/BotWorldPopulationMgrCohortScope.h"

#include <algorithm>
#include <set>
#include <utility>

namespace BotWorldCohortScope
{
namespace
{
bool MatchesScope(RuntimeIdentity const& runtime,
    std::vector<ActorIdentity> const& actors)
{
    if (!runtime.ScopeKnown)
        return false;
    return std::all_of(actors.begin(), actors.end(),
        [&runtime](ActorIdentity const& actor)
        {
            return !actor.Present
                || (actor.MapId == runtime.MapId
                    && actor.InstanceId == runtime.InstanceId);
        });
}
}

Resolution Resolve(std::uint64_t serverEpoch,
    std::vector<RuntimeIdentity> const& runtimes,
    std::vector<ActorIdentity> const& actors)
{
    if (std::none_of(actors.begin(), actors.end(),
            [](ActorIdentity const& actor) { return actor.Present; }))
        return { ResolutionStatus::MissingActor, {} };

    ActorIdentity const* scope = nullptr;
    for (ActorIdentity const& actor : actors)
    {
        if (!actor.Present)
            continue;
        if (scope && (scope->MapId != actor.MapId
                || scope->InstanceId != actor.InstanceId))
            return { ResolutionStatus::MapInstanceMismatch, {} };
        scope = &actor;
    }

    std::set<std::pair<std::string, std::uint64_t>> owners;
    for (ActorIdentity const& actor : actors)
    {
        if (!actor.Present || !actor.Lease.Observed)
            continue;
        if (actor.Lease.ServerEpoch != serverEpoch
            || actor.Lease.CohortId.empty() || !actor.Lease.AttemptId)
            return { ResolutionStatus::StaleLease, {} };
        owners.emplace(actor.Lease.CohortId, actor.Lease.AttemptId);
    }
    if (owners.size() > 1)
        return { ResolutionStatus::ConflictingOwners, {} };

    if (owners.empty()
        && std::any_of(actors.begin(), actors.end(),
            [](ActorIdentity const& actor)
            {
                return actor.Present && actor.RequiresLease;
            }))
        return { ResolutionStatus::MissingOwner, {} };

    if (!owners.empty())
    {
        auto const& [cohortId, attemptId] = *owners.begin();
        auto runtime = std::find_if(runtimes.begin(), runtimes.end(),
            [&cohortId](RuntimeIdentity const& value)
            {
                return value.CohortId == cohortId;
            });
        if (runtime == runtimes.end())
            return { ResolutionStatus::MissingRuntime, {} };
        if (!runtime->Active)
            return { ResolutionStatus::InactiveRuntime, {} };
        if (runtime->ServerEpoch != serverEpoch
            || runtime->AttemptId != attemptId)
            return { ResolutionStatus::AttemptMismatch, {} };
        if (runtime->ScopeKnown && !MatchesScope(*runtime, actors))
            return { ResolutionStatus::MapInstanceMismatch, {} };

        std::size_t const activeCount = std::count_if(runtimes.begin(),
            runtimes.end(), [](RuntimeIdentity const& value)
            {
                return value.Active;
            });
        if (!runtime->ScopeKnown && activeCount > 1)
            return { ResolutionStatus::MapInstanceMismatch, {} };
        return { ResolutionStatus::Resolved, cohortId };
    }

    std::vector<RuntimeIdentity const*> matches;
    for (RuntimeIdentity const& runtime : runtimes)
        if (runtime.Active && runtime.ServerEpoch == serverEpoch
            && runtime.AttemptId && MatchesScope(runtime, actors))
            matches.push_back(&runtime);
    if (matches.empty())
        return { ResolutionStatus::MissingOwner, {} };
    if (matches.size() > 1)
        return { ResolutionStatus::AmbiguousMapInstance, {} };
    return { ResolutionStatus::Resolved, matches.front()->CohortId };
}

bool RequiresPlayerLease(bool actorIsPlayer, bool controlledByPlayer,
    bool controllerGuidIsPlayer, bool livePlayerOwner)
{
    return actorIsPlayer || controlledByPlayer || controllerGuidIsPlayer
        || livePlayerOwner;
}

bool AllowsDiagnosticCleanup(std::uint64_t serverEpoch,
    std::string_view cohortId, std::uint64_t attemptId,
    LeaseIdentity const& observedLease)
{
    return !observedLease.Observed
        || (observedLease.ServerEpoch == serverEpoch
            && observedLease.CohortId == cohortId
            && observedLease.AttemptId == attemptId);
}

bool AllowsConcurrentAdmission(std::uint32_t activeCohorts,
    std::uint32_t maximumActiveCohorts, std::uint32_t mapWorkerThreads)
{
    if (activeCohorts >= maximumActiveCohorts)
        return false;
    return activeCohorts == 0 || mapWorkerThreads <= 1;
}

bool MatchesPendingOwnership(std::string_view pendingCohortId,
    std::uint64_t pendingAttemptId, std::string_view currentCohortId,
    std::uint64_t currentAttemptId)
{
    return !pendingCohortId.empty() && pendingAttemptId
        && pendingCohortId == currentCohortId
        && pendingAttemptId == currentAttemptId;
}
}
