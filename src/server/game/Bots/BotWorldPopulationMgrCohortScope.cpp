#include "Bots/BotWorldPopulationMgrCohortScope.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Player.h"
#include "Totem.h"
#include "Unit.h"
#include "World.h"

#include <utility>

namespace
{
struct CallbackOwnerEvidence
{
    Player* PlayerOwner = nullptr;
    bool RequiresLease = false;
};

CallbackOwnerEvidence CallbackOwner(Unit* unit)
{
    if (!unit)
        return {};

    CallbackOwnerEvidence evidence;
    bool controlledByPlayer = unit->IsControlledByPlayer();
    bool controllerGuidIsPlayer =
        unit->GetCharmerOrOwnerGUID().IsPlayer();
    if (Player* player = unit->GetCharmerOrOwnerPlayerOrPlayerItself())
        evidence.PlayerOwner = player;

    if (!evidence.PlayerOwner)
    {
        Unit* current = unit;
        for (std::uint8_t depth = 0; depth < 4 && current; ++depth)
        {
            controlledByPlayer = controlledByPlayer
                || current->IsControlledByPlayer();
            controllerGuidIsPlayer = controllerGuidIsPlayer
                || current->GetCharmerOrOwnerGUID().IsPlayer();
            current = current->IsTotem() ? current->ToTotem()->GetOwner()
                : current->GetCharmerOrOwner();
            if (!current)
                break;
            if (Player* player = current->ToPlayer())
            {
                evidence.PlayerOwner = player;
                break;
            }
        }
    }
    evidence.RequiresLease = BotWorldCohortScope::RequiresPlayerLease(
        unit->GetGUID().IsPlayer(), controlledByPlayer,
        controllerGuidIsPlayer, evidence.PlayerOwner != nullptr);
    return evidence;
}
}

thread_local BotWorldPopulationMgr::CohortRuntime*
    BotWorldPopulationMgr::_scopedCohort = nullptr;

BotWorldPopulationMgr::CohortScope::CohortScope(CohortRuntime* runtime)
    : _scope(_scopedCohort, runtime)
{
}

BotWorldPopulationMgr::CohortRuntime const*
BotWorldPopulationMgr::CohortScope::Get() const
{
    return _scope ? _scopedCohort : nullptr;
}

BotWorldPopulationMgr::CohortScope::operator bool() const
{
    return Get() != nullptr;
}

BotWorldPopulationMgr::CohortScope BotWorldPopulationMgr::ScopeCohort(
    CohortRuntime* runtime)
{
    return CohortScope(runtime);
}

BotWorldCohortScope::RuntimeIdentity
BotWorldPopulationMgr::RuntimeIdentityFor(CohortRuntime const& runtime) const
{
    BotWorldCohortScope::RuntimeIdentity identity;
    identity.CohortId = runtime.Id;
    identity.ServerEpoch = _serverEpoch;
    identity.AttemptId = runtime.AttemptId;
    identity.Active = runtime.Active;
    if (runtime.Party.MapId || runtime.Party.InstanceId)
    {
        identity.MapId = runtime.Party.MapId;
        identity.InstanceId = runtime.Party.InstanceId;
        identity.ScopeKnown = true;
    }
    else if (runtime.CalibrationActive
        && runtime.CalibrationFixtureTargetMapId)
    {
        identity.MapId = runtime.CalibrationFixtureTargetMapId;
        identity.InstanceId = 0;
        identity.ScopeKnown = true;
    }
    else if (runtime.CalibrationActive
        && !runtime.Party.CalibrationBots.empty())
    {
        identity.MapId = runtime.Party.CalibrationBots.front().SpawnMapId;
        identity.InstanceId = 0;
        identity.ScopeKnown = true;
    }
    return identity;
}

BotWorldPopulationMgr::CohortRuntime*
BotWorldPopulationMgr::ResolveCallbackCohort(Unit* first, Unit* second)
{
    std::vector<BotWorldCohortScope::RuntimeIdentity> runtimes;
    runtimes.reserve(_cohorts.size());
    for (auto const& [_, runtime] : _cohorts)
        if (runtime)
            runtimes.push_back(RuntimeIdentityFor(*runtime));

    std::vector<BotWorldCohortScope::ActorIdentity> actors;
    actors.reserve(2);
    auto appendActor = [this, &actors](Unit* unit)
    {
        if (!unit)
            return;
        BotWorldCohortScope::ActorIdentity actor;
        actor.Present = true;
        actor.MapId = unit->GetMapId();
        actor.InstanceId = unit->GetInstanceId();
        CallbackOwnerEvidence const owner = CallbackOwner(unit);
        actor.RequiresLease = owner.RequiresLease;
        std::lock_guard<std::mutex> guard(_leaseMutex);
        if (owner.PlayerOwner)
        {
            auto lease = _guidLeases.find(
                owner.PlayerOwner->GetGUID().GetCounter());
            if (lease != _guidLeases.end())
            {
                actor.Lease.Observed = true;
                actor.Lease.ServerEpoch = lease->second.ServerEpoch;
                actor.Lease.CohortId = lease->second.CohortId;
                actor.Lease.AttemptId = lease->second.AttemptId;
            }
        }
        actors.push_back(std::move(actor));
    };
    appendActor(first);
    appendActor(second);

    BotWorldCohortScope::Resolution resolution =
        BotWorldCohortScope::Resolve(_serverEpoch, runtimes, actors);
    if (!resolution)
        return nullptr;
    return FindCohort(resolution.CohortId);
}

BotWorldPopulationMgr::CohortScope
BotWorldPopulationMgr::ScopeCallbackCohort(Unit* first, Unit* second)
{
    return ScopeCohort(ResolveCallbackCohort(first, second));
}

uint32 BotWorldPopulationMgr::MapWorkerThreadCount() const
{
    return sWorld->getIntConfig(CONFIG_NUMTHREADS);
}
