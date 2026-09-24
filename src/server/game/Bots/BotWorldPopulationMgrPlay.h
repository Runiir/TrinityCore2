#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_PLAY_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_PLAY_H

#include "ObjectGuid.h"

#include <functional>
#include <set>
#include <string>

class BotWorldPopulationMgr;
class Group;
class Player;
class Unit;
namespace BotEncounter
{
struct ActorSnapshot;
struct Blackboard;
}

// Human play mode (docs/bot_raids/human_play_mode.md). A friend of
// BotWorldPopulationMgr: every play-only branch of the shared validation
// lifecycle lives here and is reached only for a CohortPurpose::Play cohort,
// so validation cohorts keep their code paths unchanged.
namespace BotWorldPopulationMgrPlay
{
inline constexpr char const* CohortId = "play";
inline constexpr char const* Scenario = "blackwing_descent_10n_magmaw_diagnostic";

struct Context
{
    // `.botauto play` commands. Each returns one JSON line.
    static std::string Fill(BotWorldPopulationMgr& mgr, Player* leader);
    static std::string Go(BotWorldPopulationMgr& mgr, Player* invoker);
    static std::string Stop(BotWorldPopulationMgr& mgr, Player* invoker);
    static std::string Status(BotWorldPopulationMgr& mgr);

    // Lifecycle hooks, called only while a Play cohort is selected.
    static bool IsExternalSlot(BotWorldPopulationMgr const& mgr, std::string const& slotId);
    static uint32 ExternalSlotCount(BotWorldPopulationMgr const& mgr);
    static uint32 ExpectedBotCount(BotWorldPopulationMgr const& mgr, uint32 declaredRosterSize);
    static bool ResetBotPool(BotWorldPopulationMgr& mgr, char const* reason);
    static Player* AdmissionAnchor(BotWorldPopulationMgr& mgr);
    // Every cohort bot is in the group, the group fits the raid, and every
    // other member is a registered (or newly registered) human.
    static bool NativeGroupAdmits(BotWorldPopulationMgr& mgr, Group* group,
        std::set<ObjectGuid> const& botGuids);
    static bool PermitRouteAdvance(BotWorldPopulationMgr& mgr, uint64 prospectiveGeneration);
    static void PublishExternalPlayers(BotWorldPopulationMgr& mgr,
        BotEncounter::Blackboard& board, Player* observer,
        std::function<BotEncounter::ActorSnapshot(Unit*)> const& build,
        std::set<ObjectGuid>& seenUnits);
    // Status-JSON fields of an active play session; "" for any other cohort,
    // so validation status bytes are unchanged.
    static std::string StatusFieldsJson(BotWorldPopulationMgr const& mgr);
};
}

#endif
