#include "Bots/BotWorldPopulationMgrValidationRouteNativeFacts.h"
#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"

#include "Creature.h"
#include "GameObject.h"
#include "GameObjectData.h"
#include "InstanceScript.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Transport.h"

#include <algorithm>

namespace
{
using namespace BotValidationRouteNative;
using BotWorldPopulationMgrValidationRouteNative::MemberInput;

// Entry-only targets are searched around the observing bot; spawn IDs are
// resolved in the map's spawn-id store.
constexpr float TargetSearchRadius = 250.0f;

ActorFact FromCreature(Creature const* creature)
{
    ActorFact fact;
    fact.Entry = creature->GetEntry();
    fact.SpawnId = creature->GetSpawnId();
    fact.Alive = creature->IsAlive();
    fact.Spawned = creature->IsInWorld();
    fact.Selectable = !creature->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
    fact.Interactable = creature->GetUInt32Value(UNIT_NPC_FLAGS) != 0;
    fact.ReactAggressive = creature->GetReactState() == REACT_AGGRESSIVE;
    fact.InCombat = creature->IsInCombat();
    fact.Flying = creature->IsFlying();
    fact.HasVictim = creature->GetVictim() != nullptr;
    for (auto const& applied : creature->GetAppliedAuras())
        fact.AuraIds.push_back(applied.first);
    return fact;
}

ActorFact FromGameObject(GameObject const* object)
{
    ActorFact fact;
    fact.Entry = object->GetEntry();
    fact.SpawnId = object->GetSpawnId();
    fact.Spawned = object->isSpawned();
    fact.Alive = fact.Spawned;
    fact.Selectable = fact.Spawned
        && !object->HasFlag(GAMEOBJECT_FLAGS, GO_FLAG_NOT_SELECTABLE);
    fact.Interactable = fact.Selectable;
    return fact;
}

std::vector<GameObject*> FindGameObjects(Player* observer, uint32 entry, uint64 spawnId)
{
    std::vector<GameObject*> found;
    Map* map = observer ? observer->GetMap() : nullptr;
    if (!map)
        return found;
    if (spawnId)
    {
        auto bounds = map->GetGameObjectBySpawnIdStore().equal_range(
            ObjectGuid::LowType(spawnId));
        for (auto itr = bounds.first; itr != bounds.second; ++itr)
            if (GameObject* object = itr->second; object && object->IsInWorld()
                && (!entry || object->GetEntry() == entry))
                found.push_back(object);
        return found;
    }
    std::vector<GameObject*> objects;
    observer->GetGameObjectListWithEntryInGrid(objects, entry, TargetSearchRadius);
    for (GameObject* object : objects)
        if (object && object->IsInWorld())
            found.push_back(object);
    return found;
}

std::vector<Creature*> FindCreatures(Player* observer, uint32 entry, uint64 spawnId)
{
    std::vector<Creature*> found;
    Map* map = observer ? observer->GetMap() : nullptr;
    if (!map)
        return found;
    if (spawnId)
    {
        auto bounds = map->GetCreatureBySpawnIdStore().equal_range(
            ObjectGuid::LowType(spawnId));
        for (auto itr = bounds.first; itr != bounds.second; ++itr)
            if (Creature* creature = itr->second; creature && creature->IsInWorld()
                && (!entry || creature->GetEntry() == entry))
                found.push_back(creature);
        return found;
    }
    std::vector<Creature*> creatures;
    observer->GetCreatureListWithEntryInGrid(creatures, entry, TargetSearchRadius);
    for (Creature* creature : creatures)
        if (creature && creature->IsInWorld())
            found.push_back(creature);
    return found;
}

// "Not in the spawn-id store" proves "not in the world" only for a spawn of
// this map whose grid is loaded in this instance.
bool GameObjectAbsenceAuthoritative(Map const* map, uint64 spawnId)
{
    if (!map || !spawnId)
        return false;
    GameObjectData const* data = sObjectMgr->GetGameObjectData(ObjectGuid::LowType(spawnId));
    return data && data->mapId == map->GetId() && map->IsGridLoaded(data->spawnPoint);
}

class ServerFacts final : public FactSource
{
public:
    ServerFacts(Player* evaluator, std::vector<MemberInput> const& members, uint64 owner)
        : _evaluator(evaluator), _members(members), _owner(owner) { }

    std::vector<ActorFact> Creatures(uint32 entry, uint64 spawnId) const override
    {
        std::vector<ActorFact> facts;
        for (Creature* creature : FindCreatures(_evaluator, entry, spawnId))
            facts.push_back(FromCreature(creature));
        return facts;
    }

    ObjectQuery GameObjects(uint32 entry, uint64 spawnId) const override
    {
        ObjectQuery query;
        for (GameObject* object : FindGameObjects(_evaluator, entry, spawnId))
            query.Facts.push_back(FromGameObject(object));
        query.AbsenceAuthoritative = spawnId
            && GameObjectAbsenceAuthoritative(_evaluator ? _evaluator->GetMap() : nullptr, spawnId);
        return query;
    }

    bool BossState(uint32 index, uint32& state) const override
    {
        InstanceScript const* instance = _evaluator ? _evaluator->GetInstanceScript() : nullptr;
        if (!instance || index >= instance->GetEncounterCount())
            return false;
        state = uint32(instance->GetBossState(index));
        return true;
    }

    std::vector<MemberFact> Members() const override
    {
        std::vector<MemberFact> facts;
        Map* map = _evaluator ? _evaluator->GetMap() : nullptr;
        for (MemberInput const& input : _members)
        {
            Player* member = input.Bot;
            if (!member)
                continue;
            MemberFact fact;
            fact.Guid = member->GetGUID().GetRawValue();
            fact.Alive = member->IsAlive();
            // A loaded member mid-teleport (not in the world) is off the route.
            fact.OnRouteInstance = input.OnRouteInstance && member->IsInWorld()
                && map && member->GetMap() == map;
            fact.Owner = fact.Guid == _owner;
            if (!fact.OnRouteInstance)
            {
                facts.push_back(fact);
                continue;
            }
            if (TransportBase const* transport = member->GetTransport())
            {
                fact.OnTransport = true;
                if (GameObject const* object = map->GetGameObject(transport->GetTransportGUID()))
                {
                    fact.TransportEntry = object->GetEntry();
                    fact.TransportSpawnId = object->GetSpawnId();
                }
            }
            if (Unit const* vehicle = member->GetVehicleBase())
            {
                fact.VehicleEntry = vehicle->GetEntry();
                fact.Seat = member->GetTransSeat();
            }
            facts.push_back(fact);
        }
        return facts;
    }

    TransportFact Transport(uint32 entry, uint64 spawnId) const override
    {
        return BotWorldPopulationMgrValidationRouteNative::Facts::ResolveTransport(
            _evaluator, entry, spawnId).Fact;
    }

private:
    Player* _evaluator;
    std::vector<MemberInput> const& _members;
    uint64 _owner;
};
}

namespace BotWorldPopulationMgrValidationRouteNative::Facts
{
Player* SelectEvaluator(std::vector<MemberInput> const& members)
{
    Player* living = nullptr;
    Player* any = nullptr;
    for (MemberInput const& member : members)
    {
        if (!member.Bot || !member.OnRouteInstance || !member.Bot->IsInWorld())
            continue;
        auto lower = [&member](Player* current)
        {
            return !current || member.Bot->GetGUID() < current->GetGUID();
        };
        if (member.Bot->IsAlive() && lower(living))
            living = member.Bot;
        if (lower(any))
            any = member.Bot;
    }
    return living ? living : any;
}

Verdict EvaluateCompletion(CompletionContract const& contract, Player* evaluator,
    std::vector<MemberInput> const& members, uint64 ownerGuid, CompletionMemory& memory)
{
    if (!evaluator)
        return { false, "no_evaluator_in_route_instance" };
    ServerFacts const facts(evaluator, members, ownerGuid);
    return BotValidationRouteNative::EvaluateCompletion(contract, facts, memory);
}

ResolvedTarget ResolveInteractionTarget(Player* bot, InteractionContract const& contract)
{
    ResolvedTarget resolved;
    std::vector<WorldObject*> candidates;
    if (contract.Target == TargetType::GameObject || contract.Target == TargetType::Any)
        for (GameObject* object : FindGameObjects(bot, contract.Entry, contract.SpawnId))
            if (object->isSpawned())
                candidates.push_back(object);
    if (contract.Target == TargetType::Creature || contract.Target == TargetType::Any)
        for (Creature* creature : FindCreatures(bot, contract.Entry, contract.SpawnId))
            if (creature->IsAlive())
                candidates.push_back(creature);
    resolved.Ambiguous = candidates.size() > 1;
    if (candidates.size() == 1)
        resolved.Object = candidates.front();
    return resolved;
}

TransportTarget ResolveTransport(Player* observer, uint32 entry, uint64 spawnId)
{
    TransportTarget target;
    std::vector<GameObject*> transports;
    for (GameObject* object : FindGameObjects(observer, entry, spawnId))
        if (object->GetGoType() == GAMEOBJECT_TYPE_TRANSPORT && object->ToTransportBase())
            transports.push_back(object);
    if (transports.size() > 1)
    {
        target.Fact.Present = true;
        target.Fact.Ambiguous = true;
        return target;
    }
    if (transports.empty())
        return target;
    target.Object = transports.front();
    target.Fact = BotValidationRouteBoardingAction::ObserveTransport(target.Object);
    return target;
}

bool OnTransport(Player const* member, GameObject const* transport)
{
    TransportBase const* current = member ? member->GetTransport() : nullptr;
    return current && transport && current->GetTransportGUID() == transport->GetGUID();
}
}
