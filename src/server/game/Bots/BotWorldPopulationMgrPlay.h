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

// Core hook for WorldSession::HandleRaidReadyCheckOpcode; no-op unless a
// play session owns the group.
void OnRaidReadyCheckStarted(Group* group, Player* initiator);
// Core hook for addon messages (DBM/BigWigs pull timers from the leader).
void OnAddonMessage(Player* sender, uint32 chatType, std::string const& prefix,
    std::string const& message);
// Script hook for party/raid chat and raid warnings ("pull 10").
void OnGroupChat(Player* sender, uint32 chatType, std::string const& message, Group* group);

struct Context
{
    // `.botauto play` commands. Each returns one JSON line.
    static std::string Fill(BotWorldPopulationMgr& mgr, Player* leader);
    static std::string Go(BotWorldPopulationMgr& mgr, Player* invoker);
    static std::string Stop(BotWorldPopulationMgr& mgr, Player* invoker);
    static std::string Status(BotWorldPopulationMgr& mgr);
    // `.botauto play pull [seconds|cancel]`, DBM/BigWigs timers and raid chat.
    static std::string Pull(BotWorldPopulationMgr& mgr, Player* invoker, bool cancel,
        uint32 seconds, std::string const& source);

    // Lifecycle hooks, called only while the play cohort is the scoped cohort.
    static bool IsExternalSlot(BotWorldPopulationMgr const& mgr, std::string const& slotId);
    static uint32 ExternalSlotCount(BotWorldPopulationMgr const& mgr);
    static uint32 ExpectedBotCount(BotWorldPopulationMgr const& mgr, uint32 declaredRosterSize);
    static bool ResetBotPool(BotWorldPopulationMgr& mgr, char const* reason);
    static Player* AdmissionAnchor(BotWorldPopulationMgr& mgr);
    // Every cohort bot is in the group, the group fits the raid, and every
    // other member is a registered (or newly registered) human.
    static bool NativeGroupAdmits(BotWorldPopulationMgr& mgr, Group* group,
        std::set<ObjectGuid> const& botGuids);
    // Bots advance when a human moves toward (or fights at) the next node,
    // when a pull timer runs, or on a manual go.
    static bool PermitRouteAdvance(BotWorldPopulationMgr& mgr, uint64 prospectiveGeneration);
    // True once the leader's pull timer expired; bots stage but hold the
    // boss pull until then (or until anyone engages).
    static bool PullPermitted(BotWorldPopulationMgr& mgr);
    // The sender leads or assists the active play raid.
    static bool FromPlayLeadership(BotWorldPopulationMgr& mgr, Player* sender);
    // The frozen leader check of validation; any leader holds in play,
    // where a human leads and may pass the lead.
    static bool FrozenLeaderHolds(BotWorldPopulationMgr const& mgr, Group const* group,
        ObjectGuid frozenLeader);
    // A human raid leader started a native ready check: arm the play
    // cohort's bots to answer it (the validation cohort's bot leader arms it
    // through `.botauto readycheck` instead).
    static void OnRaidReadyCheckStarted(BotWorldPopulationMgr& mgr, Group* group, Player* initiator);
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
