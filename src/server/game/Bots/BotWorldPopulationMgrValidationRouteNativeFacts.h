#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_NATIVE_FACTS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_NATIVE_FACTS_H

#include "Bots/BotValidationRouteNativeLogic.h"
#include "Bots/BotWorldPopulationMgrValidationRouteNativeRuntime.h"

#include <cstdint>
#include <vector>

class GameObject;
class Player;
class WorldObject;

// World observations for native route contracts. Completion is evaluated
// from one evaluator on the route map in the route's original instance; an
// object that is merely not found is unknown unless the route instance's
// spawn-id store proves it absent.
namespace BotWorldPopulationMgrValidationRouteNative::Facts
{
// Lowest-GUID living member in the route instance (or any member in it).
Player* SelectEvaluator(std::vector<MemberInput> const& members);

BotValidationRouteNative::Verdict EvaluateCompletion(
    BotValidationRouteNative::CompletionContract const& contract, Player* evaluator,
    std::vector<MemberInput> const& members, std::uint64_t ownerGuid,
    BotValidationRouteNative::CompletionMemory& memory);

struct ResolvedTarget
{
    WorldObject* Object = nullptr;
    bool Ambiguous = false;
};

// A declared target must name exactly one live object; never guess.
ResolvedTarget ResolveInteractionTarget(Player* bot,
    BotValidationRouteNative::InteractionContract const& contract);

struct TransportTarget
{
    GameObject* Object = nullptr;
    BotValidationRouteNative::TransportFact Fact;
};

TransportTarget ResolveTransport(Player* observer, std::uint32_t entry, std::uint64_t spawnId);

bool OnTransport(Player const* member, GameObject const* transport);
}

#endif
