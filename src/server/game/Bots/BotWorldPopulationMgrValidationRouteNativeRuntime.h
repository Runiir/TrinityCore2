#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_NATIVE_RUNTIME_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_NATIVE_RUNTIME_H

#include "Bots/BotActionArbiter.h"
#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotValidationRouteNativeTypes.h"
#include "Bots/BotWorldPopulationMgrBotState.h"

#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>

class Player;
class WorldObject;

// Server adapter for native route contracts (interaction, observed completion
// and transport). Completion is evaluated once per cohort observation tick by
// one evaluator in the route's original instance; each bot then submits only
// player-opcode intents into its own decision kernel. Manager-owned effects
// (event recording, terminalization, attempt failure) are callbacks.
namespace BotWorldPopulationMgrValidationRouteNative
{
using WorldBotState = BotWorldPopulationMgrBotState::WorldBotState;

struct RosterMember
{
    std::uint32_t Slot = 0;
    std::string Role;
};

struct MemberInput
{
    Player* Bot = nullptr;
    // On the route map, in the cohort's original instance.
    bool OnRouteInstance = false;
};

struct Callbacks
{
    std::function<BotActionArbitration::Outcome(BotNativeAction::Intent const&,
        BotMovementArbitration::Owner, BotMovementArbitration::Priority)> Execute;
    // Diagnostic route event for the current bot.
    std::function<void(std::string const& result, WorldObject* target,
        float value, std::uint32_t entry)> Record;
    // Native postcondition observed: terminalize every cohort member once.
    std::function<void(std::string const& label, WorldObject* evidence)> Complete;
    // Bounded contract exhausted (timeout, attempts, stranded): fail once.
    std::function<void(std::string const& reason)> Fail;
};

struct Input
{
    Player* Bot = nullptr;
    WorldBotState* State = nullptr;
    std::string* Situation = nullptr;
    std::string* Action = nullptr;
    BotEncounter::Blackboard const* Board = nullptr;
    BotValidationRouteNative::NodeContract* Node = nullptr;
    float AnchorX = 0.0f;
    float AnchorY = 0.0f;
    float AnchorZ = 0.0f;
    // Every loaded cohort member, on any map.
    std::vector<MemberInput> Members;
    // Raw GUID -> frozen roster slot (1-based) and role.
    std::map<std::uint64_t, RosterMember> Roster;
    BotValidationRouteNative::RuntimeScope Scope;
    std::uint64_t NowMs = 0;
    // Cohort observation tick (encounter snapshot revision).
    std::uint64_t Tick = 0;
    bool CompletionAlreadyRecorded = false;
};

struct Result
{
    // Any declared native contract owns the node's movement and actions.
    bool OwnsNode = false;
    bool Satisfied = false;
};

Result Run(Input const& input, Callbacks const& callbacks);
}

#endif
