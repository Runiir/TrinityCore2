#ifndef TRINITY_BOT_RAID_LOCKOUT_REGISTRY_H
#define TRINITY_BOT_RAID_LOCKOUT_REGISTRY_H

// Seeded raid lockouts keyed by cohort id (package A of
// docs/bot_raids/full_raid_parallel_shards.md). A record exists only after
// `.botauto lockout seed`; a cohort without one never reaches any lockout
// branch, so the fresh-instance admission path is unchanged.

#include "Define.h"
#include "Bots/BotRaidLockoutPlan.h"

#include <map>
#include <string>
#include <utility>
#include <vector>

class Group;

namespace BotRaidLockout
{
struct LockoutRecord
{
    std::string CohortId;
    std::string Raid;
    std::string ScriptName;
    std::string ScriptHeader;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
    uint8 Difficulty = 0;
    uint32 EncounterCount = 0;
    std::vector<std::string> BossesDone;
    std::vector<uint32> BossIndicesDone;
    std::vector<uint8> ExpectedStates;
    std::map<std::string, uint32> BossIndexByKey; // every boss on this difficulty
    uint32 CompletedEncounterMask = 0;
    std::string SaveData;                       // canonical GetSaveData() bytes
    std::vector<std::pair<std::string, uint32>> ExtraValues;
    std::vector<RespawnRow> RespawnRows;        // never-respawn rows written by the seeder
    std::vector<DoorReadback> Doors;
    // Informational: bosses whose live instance_encounters credit differs
    // from the prerequisite file. The completed mask uses DBC bits only.
    std::vector<std::string> CreditEntryMismatches;
    uint64 SeededAtUnix = 0;
    // Admission: the planned raid leader whose seed group binds to the save,
    // and the group that did bind. Both 0 while the lockout is idle. The
    // seeder's own bind writes no group_instance row (load = true), but the
    // core may: see BindArmedSeedGroup. The players' permanent binds are
    // native character_instance rows.
    uint32 ArmedLeaderGuid = 0;
    uint32 BoundGroupGuid = 0;
};

namespace Registry
{
bool Find(std::string const& cohortId, LockoutRecord& record);
bool Insert(LockoutRecord const& record);
void Erase(std::string const& cohortId);
bool Arm(std::string const& cohortId, uint32 leaderGuid);
void Disarm(std::string const& cohortId);
void SetBoundGroup(std::string const& cohortId, uint32 groupGuid);
bool HasInstance(uint32 instanceId);
}

// BotMgr seed-raid hook (BotMgrLoading.cpp). When `leaderGuid` is the armed
// leader of a seeded lockout, binds `seed` permanently to that lockout's
// instance save before the leader's own map entry, so CreateMap routes the
// whole cohort into the seeded instance. A no-op for every other leader.
void BindArmedSeedGroup(uint32 leaderGuid, Group* seed, uint32 placementMapId);

// Undoes BindArmedSeedGroup when the armed leader's placement fails after the
// bind (BotMgrLoading.cpp failure branches). A no-op for every other leader.
void ReleaseArmedSeedGroup(uint32 leaderGuid);

// Unbinds the group recorded for `cohortId` from its lockout, deletes any
// group_instance row of that pair synchronously and forgets the group.
// Admission rollback calls it before the bots leave, so no half-bound group
// outlives a failed admission. A no-op without a bound group.
void ReleaseSeedGroupBind(std::string const& cohortId);
}

#endif
