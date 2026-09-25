#ifndef TRINITY_BOT_RAID_LOCKOUT_SEEDER_H
#define TRINITY_BOT_RAID_LOCKOUT_SEEDER_H

// In-server seeding, readback and teardown of raid lockouts whose exact boss
// set is already dead (docs/bot_raids/full_raid_parallel_shards.md, package A).
//
// Seeding writes the instance row, the never-respawn rows of the dead boss
// spawns and nothing else, synchronously; then it loads the map through
// MapManager::LoadInstanceForSave, so the native InstanceScript::Load runs
// exactly as for a saved lockout after a restart (boss states, spawn groups,
// doors, script extra values). The readback comes from that live script. The
// seeding map is unloaded again; the cohort's leader later re-creates it with
// its own team through CreateMap. World thread only.

#include "Bots/BotRaidLockoutRegistry.h"

#include <string>
#include <vector>

namespace BotRaidLockout
{
struct DoorObservation
{
    uint32 Entry = 0;
    bool ExpectedOpen = false;
    std::string Observed; // "open", "closed" or "not_loaded"
};

struct Readback
{
    std::string Source = "none"; // "live_instance_script", "database" or "none"
    bool MapLoaded = false;
    bool SaveLoaded = false;
    uint32 SavePlayerBinds = 0;
    uint32 SaveGroupBinds = 0;
    bool DbRowPresent = false;
    bool DbIdentityMatches = false;
    std::string DbSaveDataHex;
    uint32 DbCompletedEncounterMask = 0;
    std::string ScriptName;
    uint32 EncounterCount = 0;
    std::vector<uint8> BossStates;
    uint32 CompletedEncounterMask = 0;
    std::string SaveDataHex;
    bool SaveDataMatches = false;
    // The seeded DONE set holds exactly: nothing lost, nothing extra.
    bool LockoutIntact = false;
    // States, mask and save bytes equal the seed exactly (seed-time check).
    bool ExactMatch = false;
    std::vector<std::string> ExtraDone;
    std::vector<std::string> MissingDone;
    uint32 RespawnRowsLoaded = 0;
    uint32 MapPlayers = 0;
    std::vector<DoorObservation> Doors;
    std::string Failure;
};

// Loads and validates experiments/configs/raid_prerequisites/<raid>.json
// (BotWorld.RaidPrerequisitesDir). Returns "" or a failure reason.
std::string LoadDefinition(std::string const& raid, RaidDefinition& def);

// Allocates, writes, loads, reads back and registers one lockout for
// `cohortId`. On failure everything written is rolled back.
std::string SeedLockout(std::string const& cohortId, std::string const& raid,
    std::string const& difficultyToken, std::string const& bossList,
    LockoutRecord& record, Readback& readback);

// Live readback when the map is loaded, else from the database row.
Readback ReadbackLockout(LockoutRecord const& record);

// Removes the lockout: unbinds the recorded group and any online player,
// unloads the map and the save, deletes its rows and frees the instance id.
// Refuses while anyone is inside or still bound.
std::string ClearLockout(LockoutRecord const& record);

// Makes sure the instance save of an idle lockout is in memory (the core
// unloads it when its last bind goes away) before a group binds to it.
bool EnsureSaveLoaded(LockoutRecord const& record);

std::string ReadbackJson(Readback const& readback);
std::string RecordFieldsJson(LockoutRecord const& record);
}

#endif
