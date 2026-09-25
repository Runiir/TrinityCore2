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
    // BotRaidLockout::CompareReadback against the seed (BotRaidLockoutPlan.h).
    ReadbackComparison Comparison;
    uint32 RespawnRowsLoaded = 0;
    // Everyone inside the map, game masters included.
    uint32 MapPlayers = 0;
    std::vector<DoorObservation> Doors;
    std::string Failure;
};

// Loads and validates <dir>/<raid>.json. The directory is
// BotWorld.RaidPrerequisitesDir, default experiments/configs/raid_prerequisites;
// a relative one resolves against the source tree (SourceDirectory /
// BuiltInConfig), never the working directory. Returns "" or a failure reason.
std::string LoadDefinition(std::string const& raid, RaidDefinition& def);

// Allocates, writes, loads, reads back and registers one lockout for
// `cohortId`. On failure everything written is rolled back.
std::string SeedLockout(std::string const& cohortId, std::string const& raid,
    std::string const& difficultyToken, std::string const& bossList,
    LockoutRecord& record, Readback& readback);

// Live readback when the map is loaded, else from the database row.
Readback ReadbackLockout(LockoutRecord const& record);

// Removes the lockout: unloads the map, unbinds the recorded group, unloads
// the save and deletes its rows. Every refusal (anyone inside, a foreign group
// or an online player still bound) is checked before anything changes. The
// instance id is never freed: a reused id would load this lockout's leftover
// corpse and corpse_phases rows into a new instance.
std::string ClearLockout(LockoutRecord const& record);

// Makes sure the instance save of an idle lockout is in memory (the core
// unloads it when its last bind goes away) before a group binds to it.
bool EnsureSaveLoaded(LockoutRecord const& record);

std::string ReadbackJson(Readback const& readback);
std::string RecordFieldsJson(LockoutRecord const& record);
}

#endif
