#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotDatasetEvent.h"
#include "Bots/BotExperienceLearningPolicy.h"
#include "CellImpl.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "MapManager.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "Random.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <shared_mutex>
#include <sstream>
#include <string>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

float Distance2d(float ax, float ay, float bx, float by)
{
    float dx = ax - bx;
    float dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}
}

bool BotWorldPopulationMgr::ResolveSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const
{
    // Certifying route placement is resolved only by the inactive admission
    // transaction from the pinned route manifest; it never consults mutable
    // character positions or the free-roam placement fallbacks below.
    if (Cohort().Config.ValidationRouteEnable)
        return false;

    std::string mode = Cohort().Config.SpawnMode.empty() ? "resume_or_race_start" : Cohort().Config.SpawnMode;
    bool allowResume = Cohort().Config.UseSavedPosition && (mode == "resume_or_race_start" || mode == "resume_only" || mode == "saved_or_near_player");
    if (allowResume)
    {
        if (ResolveSavedSpawnPlacement(candidateGuid, placement))
            return true;

        if (mode == "resume_only")
            return false;
    }

    if (mode == "resume_or_race_start" || mode == "race_start_only")
    {
        if (ResolveRaceStartSpawnPlacement(candidateGuid, placement))
            return true;
        if (mode == "race_start_only")
            return false;
    }

    if (mode == "saved_or_near_player" || mode == "near_player")
        if (ResolveNearPlayerSpawnPlacement(placement))
            return true;

    if (mode == "configured_center" || Cohort().Config.AllowConfiguredCenterFallback)
        return ResolveConfiguredCenterSpawnPlacement(placement);

    return false;
}

bool BotWorldPopulationMgr::ResolveSavedSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const
{
    if (QueryResult result = CharacterDatabase.PQuery("SELECT map, position_x, position_y, position_z, orientation FROM characters WHERE guid = %u", candidateGuid))
    {
        Field* fields = result->Fetch();
        uint32 mapId = fields[0].GetUInt16();
        float x = fields[1].GetFloat();
        float y = fields[2].GetFloat();
        float z = fields[3].GetFloat();
        if (!IsValidBotResumePosition(candidateGuid, mapId, x, y, z))
        {
            if (Cohort().RunId)
            {
                std::string brain = Cohort().Config.BrainVersion;
                BotDatasetEvent dataset;
                dataset.run_id = Cohort().RunId;
                dataset.experiment_id = std::to_string(Cohort().ExperimentId);
                dataset.episode_id = Cohort().RunId;
                dataset.bot_guid = ObjectGuid(HighGuid::Player, candidateGuid);
                dataset.bot_role = "generic";
                dataset.policy_source = BotPolicySource::Heuristic;
                dataset.policy_version = Cohort().Config.BrainVersion;
                dataset.timestamp_ms = NowMs();
                dataset.domain = "spawn";
                dataset.situation = "spawn_resume_invalid";
                dataset.observation_json = "{\"map_id\":" + std::to_string(mapId) + ",\"x\":" + std::to_string(x) + ",\"y\":" + std::to_string(y) + ",\"z\":" + std::to_string(z) + "}";
                dataset.valid_action_mask_json = "{\"spawn\":true}";
                dataset.chosen_action_json = "{\"event_type\":\"spawn_resume_invalid\"}";
                dataset.action_result = "invalid_saved_position";
                dataset.outcome_json = "{\"source\":\"saved_position\"}";
                dataset.quality_flags_json = "{\"source\":\"experiment_bot_events\"}";
                std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
                CharacterDatabase.EscapeString(brain);
                CharacterDatabase.EscapeString(canonical);
                CharacterDatabase.DirectPExecute(
                    "INSERT INTO experiment_bot_events (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, brain_version, map_id, x, y, z, event_type, result, raw_json, semantic_json, context_json, canonical_event_json) "
                    "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %f, %f, %f, 'spawn_resume_invalid', 'invalid_saved_position', '{}', '{}', '{\"source\":\"saved_position\"}', '%s')",
                    BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
                    Cohort().ExperimentId, Cohort().RunId, candidateGuid, brain.c_str(), mapId, x, y, z, canonical.c_str());
            }
            return false;
        }

        placement.Valid = true;
        placement.MapId = mapId;
        placement.X = x;
        placement.Y = y;
        placement.Z = z;
        placement.O = fields[4].GetFloat();
        placement.Source = "saved_position";
        return true;
    }

    return false;
}

bool BotWorldPopulationMgr::ResolveRaceStartSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const
{
    QueryResult result = CharacterDatabase.PQuery("SELECT race, class FROM characters WHERE guid = %u", candidateGuid);
    if (!result)
        return false;

    Field* fields = result->Fetch();
    uint8 race = fields[0].GetUInt8();
    uint8 playerClass = fields[1].GetUInt8();
    PlayerInfo const* info = sObjectMgr->GetPlayerInfo(race, playerClass);
    if (!info || !MapManager::IsValidMapCoord(info->mapId, info->positionX, info->positionY, info->positionZ, 0.0f))
        return false;

    placement.Valid = true;
    placement.MapId = info->mapId;
    placement.X = info->positionX;
    placement.Y = info->positionY;
    placement.Z = info->positionZ;
    placement.O = 0.0f;
    placement.Source = "race_start";
    placement.RaceStartFallbackUsed = true;
    return true;
}

bool BotWorldPopulationMgr::ResolveNearPlayerSpawnPlacement(SpawnPlacement& placement) const
{
    std::shared_lock<std::shared_mutex> lock(*HashMapHolder<Player>::GetLock());
    HashMapHolder<Player>::MapType const& players = ObjectAccessor::GetPlayers();
    for (HashMapHolder<Player>::MapType::const_iterator itr = players.begin(); itr != players.end(); ++itr)
    {
        Player* player = itr->second;
        if (!player || !player->IsInWorld() || !player->GetMap())
            continue;

        if (CharacterDatabase.PQuery("SELECT 1 FROM character_bot_pool WHERE guid = %u LIMIT 1", player->GetGUID().GetCounter()))
            continue;

        Position pos = player->GetNearPosition(Cohort().Config.NearPlayerRadius, frand(0.0f, 2.0f * float(M_PI)));
        placement.Valid = true;
        placement.MapId = player->GetMapId();
        placement.X = pos.GetPositionX();
        placement.Y = pos.GetPositionY();
        placement.Z = pos.GetPositionZ();
        placement.O = pos.GetOrientation();
        placement.Source = "near_player";
        return true;
    }

    return false;
}

bool BotWorldPopulationMgr::ResolveConfiguredCenterSpawnPlacement(SpawnPlacement& placement) const
{
    float angle = frand(0.0f, 2.0f * float(M_PI));
    float dist = frand(0.0f, Cohort().Config.Radius * 0.35f);
    placement.Valid = true;
    placement.MapId = Cohort().Config.MapId;
    placement.X = Cohort().Config.CenterX + std::cos(angle) * dist;
    placement.Y = Cohort().Config.CenterY + std::sin(angle) * dist;
    placement.Z = Cohort().Config.CenterZ;
    placement.O = angle;
    placement.Source = "configured_center";
    return true;
}

bool BotWorldPopulationMgr::IsConfiguredCenterPosition(uint32 mapId, float x, float y, float z) const
{
    if (mapId != Cohort().Config.MapId)
        return false;
    return Distance2d(x, y, Cohort().Config.CenterX, Cohort().Config.CenterY) <= std::max(1.0f, Cohort().Config.Radius * 0.35f)
        && std::fabs(z - Cohort().Config.CenterZ) <= 10.0f;
}

bool BotWorldPopulationMgr::IsValidBotResumePosition(uint32 botGuid, uint32 mapId, float x, float y, float z) const
{
    if (!botGuid)
        return false;
    if (Cohort().Config.ValidationRouteEnable
        && Cohort().Config.ValidationRouteMapId
        && mapId != Cohort().Config.ValidationRouteMapId)
        return false;
    if (std::fabs(x) < 0.001f && std::fabs(y) < 0.001f && std::fabs(z) < 0.001f)
        return false;
    if (!MapManager::IsValidMapCoord(mapId, x, y, z, 0.0f))
        return false;
    if (IsConfiguredCenterPosition(mapId, x, y, z) && Cohort().Config.SpawnMode != "configured_center" && !Cohort().Config.AllowConfiguredCenterFallback)
        return false;
    return true;
}

void BotWorldPopulationMgr::PersistBotPosition(Player* bot) const
{
    if (!bot || !bot->IsInWorld() || !MapManager::IsValidMapCoord(bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), bot->GetOrientation()))
        return;

    CharacterDatabase.DirectPExecute(
        "UPDATE characters SET position_x = %f, position_y = %f, position_z = %f, orientation = %f, map = %u, zone = %u WHERE guid = %u",
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), bot->GetOrientation(), bot->GetMapId(), bot->GetZoneId(), bot->GetGUID().GetCounter());
}

void BotWorldPopulationMgr::RecordSpawnResolved(WorldBotState& state, Player* bot, SpawnPlacement const& placement, char const* result)
{
    if (!Cohort().RunId || !bot)
        return;

    std::ostringstream context;
    context << "{\"source\":\"" << JsonEscape(placement.Source) << "\""
            << ",\"map\":" << bot->GetMapId()
            << ",\"x\":" << bot->GetPositionX()
            << ",\"y\":" << bot->GetPositionY()
            << ",\"z\":" << bot->GetPositionZ()
            << ",\"o\":" << bot->GetOrientation()
            << ",\"race\":" << uint32(bot->getRace())
            << ",\"class\":" << uint32(bot->getClass())
            << ",\"level\":" << uint32(bot->getLevel())
            << ",\"race_start_fallback_used\":" << (placement.RaceStartFallbackUsed ? "true" : "false") << "}";
    std::string raw = BuildRawJson(bot, nullptr);
    std::string semantic = BuildSemanticJson(bot, nullptr, "spawn_resolved");
    std::string brain = Cohort().Config.BrainVersion;
    std::string eventResult = result ? result : placement.Source;
    std::string contextJson = context.str();
    BotDatasetEvent dataset;
    dataset.run_id = Cohort().RunId;
    dataset.experiment_id = std::to_string(Cohort().ExperimentId);
    dataset.episode_id = Cohort().RunId;
    dataset.bot_guid = bot->GetGUID();
    dataset.bot_role = GetDungeonRole(bot);
    dataset.bot_level = uint32(bot->getLevel());
    dataset.policy_source = BotPolicySource::Heuristic;
    dataset.policy_version = Cohort().Config.BrainVersion;
    dataset.timestamp_ms = NowMs();
    dataset.tick_id = state.EventSequence;
    dataset.domain = "spawn";
    dataset.situation = "spawn_resolved";
    dataset.observation_json = raw;
    dataset.semantic_json = semantic;
    dataset.valid_action_mask_json = "{\"spawn\":true}";
    dataset.chosen_action_json = "{\"event_type\":\"spawn_resolved\"}";
    dataset.action_result = eventResult;
    dataset.outcome_json = contextJson;
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_events\"}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(eventResult);
    CharacterDatabase.EscapeString(contextJson);
    CharacterDatabase.EscapeString(canonical);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO experiment_bot_events (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, brain_version, map_id, zone_id, area_id, x, y, z, level, event_type, result, value_int, raw_json, semantic_json, context_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %u, %f, %f, %f, %u, 'spawn_resolved', '%s', %u, '%s', '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), brain.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), eventResult.c_str(), uint32(bot->getLevel()), raw.c_str(), semantic.c_str(), contextJson.c_str(), canonical.c_str());
}

void BotWorldPopulationMgr::RememberSafePosition(WorldBotState& state, Player* bot, uint32 diff)
{
    if (!bot || !bot->IsAlive() || bot->IsInCombat() || state.StuckTimer)
        return;
    if (Cohort().Config.ValidationRouteEnable)
    {
        if (GetLocalDangerScore(state.Guid.GetCounter(), bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ()) >= 3.0f)
            return;
        if (state.RecentDeathCount >= 2
            && state.LastDeathMapId == bot->GetMapId()
            && Distance2d(state.LastDeathX, state.LastDeathY, bot->GetPositionX(), bot->GetPositionY()) <= 70.0f)
            return;
    }

    state.SafePositionTimer += diff;
    if (state.SafePositionTimer < 5000)
        return;
    state.SafePositionTimer = 0;

    uint64 nowMs = NowMs();
    PruneSafePositions(state, nowMs);

    float hpPct = bot->GetMaxHealth() ? float(bot->GetHealth()) / float(bot->GetMaxHealth()) : 1.0f;
    WorldBotState::SafePosition position;
    position.MapId = bot->GetMapId();
    position.ZoneId = bot->GetZoneId();
    position.AreaId = bot->GetAreaId();
    position.X = bot->GetPositionX();
    position.Y = bot->GetPositionY();
    position.Z = bot->GetPositionZ();
    position.O = bot->GetOrientation();
    position.HpPct = hpPct;
    position.SeenMs = nowMs;
    state.SafePositions.push_back(position);
    if (state.SafePositions.size() > 24)
        state.SafePositions.erase(state.SafePositions.begin(), state.SafePositions.begin() + (state.SafePositions.size() - 24));

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_safe_positions (bot_guid, map_id, zone_id, area_id, x, y, z, o, hp_pct, last_seen_at) "
        "VALUES (%u, %u, %u, %u, %f, %f, %f, %f, %f, NOW())",
        state.Guid.GetCounter(), position.MapId, position.ZoneId, position.AreaId, position.X, position.Y, position.Z, position.O, position.HpPct);
}

void BotWorldPopulationMgr::PruneSafePositions(WorldBotState& state, uint64 nowMs) const
{
    uint64 memoryMs = uint64(Cohort().Config.SafePositionMemorySec) * 1000;
    state.SafePositions.erase(std::remove_if(state.SafePositions.begin(), state.SafePositions.end(), [nowMs, memoryMs](WorldBotState::SafePosition const& position)
    {
        return position.SeenMs + memoryMs < nowMs;
    }), state.SafePositions.end());
}

void BotWorldPopulationMgr::RememberVisiblePois(WorldBotState& state, Player* bot, uint32 diff)
{
    if (!bot || !bot->IsAlive())
        return;

    state.PoiScanTimer += diff;
    if (state.PoiScanTimer < 5000)
        return;
    state.PoiScanTimer = 0;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 80.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 80.0f);

    for (WorldObject* object : objects)
    {
        if (!object || !bot->IsInPhase(object))
            continue;

        if (Creature* creature = object->ToCreature())
        {
            if (!creature->IsAlive() || !bot->IsWithinLOSInMap(creature))
                continue;

            uint32 questId = 0;
            if (creature->IsQuestGiver())
            {
                QuestRelationResult starters = sObjectMgr->GetCreatureQuestRelations(creature->GetEntry());
                QuestRelationResult enders = sObjectMgr->GetCreatureQuestInvolvedRelations(creature->GetEntry());
                if (starters.begin() != starters.end())
                    questId = *starters.begin();
                else if (enders.begin() != enders.end())
                    questId = *enders.begin();
                RememberPoi(state, bot, creature, "quest_giver", questId, 120.0f - bot->GetExactDist(creature));
            }
            if (creature->IsVendor())
                RememberPoi(state, bot, creature, "vendor", 0, 80.0f - bot->GetExactDist(creature));
            if (creature->IsTrainer())
                RememberPoi(state, bot, creature, "trainer", 0, 75.0f - bot->GetExactDist(creature));
            if (creature->IsInnkeeper())
                RememberPoi(state, bot, creature, "innkeeper", 0, 60.0f - bot->GetExactDist(creature));
            if (creature->IsTaxi())
                RememberPoi(state, bot, creature, "flight_master", 0, 70.0f - bot->GetExactDist(creature));
        }
        else if (GameObject* go = object->ToGameObject())
        {
            uint32 questId = 0;
            QuestRelationResult starters = sObjectMgr->GetGOQuestRelations(go->GetEntry());
            QuestRelationResult enders = sObjectMgr->GetGOQuestInvolvedRelations(go->GetEntry());
            if (starters.begin() != starters.end())
                questId = *starters.begin();
            else if (enders.begin() != enders.end())
                questId = *enders.begin();

            if (questId || sObjectMgr->GetGameObjectQuestItemList(go->GetEntry()))
                RememberPoi(state, bot, go, "objective_object", questId, 90.0f - bot->GetExactDist(go));
        }
    }
}

void BotWorldPopulationMgr::RememberPoi(WorldBotState& state, Player* bot, WorldObject* object, char const* poiType, uint32 questId, float score) const
{
    if (!bot || !object || !poiType)
        return;

    uint32 entry = 0;
    if (Creature* creature = object->ToCreature())
        entry = creature->GetEntry();
    else if (GameObject* go = object->ToGameObject())
        entry = go->GetEntry();

    std::ostringstream metadata;
    metadata << "{\"source\":\"visible_scan\",\"object_type\":\"" << (object->GetTypeId() == TYPEID_GAMEOBJECT ? "gameobject" : "creature") << "\"}";
    std::string metadataJson = metadata.str();
    CharacterDatabase.EscapeString(metadataJson);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_pois (bot_guid, map_id, zone_id, area_id, x, y, z, poi_type, entity_guid, entity_entry, quest_id, score, discovered_at, last_seen_at, metadata_json) "
        "VALUES (%u, %u, %u, %u, %f, %f, %f, '%s', %u, %u, %u, %f, NOW(), NOW(), '%s') "
        "ON DUPLICATE KEY UPDATE map_id = VALUES(map_id), zone_id = VALUES(zone_id), area_id = VALUES(area_id), x = VALUES(x), y = VALUES(y), z = VALUES(z), score = GREATEST(score, VALUES(score)), last_seen_at = NOW(), metadata_json = VALUES(metadata_json)",
        state.Guid.GetCounter(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(), object->GetPositionX(), object->GetPositionY(), object->GetPositionZ(),
        poiType, object->GetGUID().GetCounter(), entry, questId, score, metadataJson.c_str());

    RememberVisibleSourceMemory(state, bot, object, poiType, entry, questId, metadataJson.c_str());
}

void BotWorldPopulationMgr::RememberVisibleSourceMemory(WorldBotState const& state, Player* bot, WorldObject* object, char const* poiType, uint32 entry, uint32 questId, char const* metadataJson) const
{
    if (!bot || !object || !poiType || !entry)
        return;

    std::string sourceType = poiType;
    std::string metadata = metadataJson && *metadataJson ? metadataJson : "{}";
    CharacterDatabase.EscapeString(sourceType);
    CharacterDatabase.EscapeString(metadata);

    if (std::string(poiType) == "vendor" || std::string(poiType) == "trainer")
    {
        CharacterDatabase.DirectPExecute(
            "INSERT INTO bot_memory_recipe_sources "
            "(bot_guid, profession_skill_id, recipe_spell_id, source_type, source_entry, item_id, map_id, zone_id, area_id, x, y, z, reputation_required, discovered_at, last_seen_at, success_count, failure_count, metadata_json) "
            "VALUES (%u, 0, 0, '%s', %u, 0, %u, %u, %u, %f, %f, %f, 0, NOW(), NOW(), 0, 0, '%s') "
            "ON DUPLICATE KEY UPDATE map_id = VALUES(map_id), zone_id = VALUES(zone_id), area_id = VALUES(area_id), x = VALUES(x), y = VALUES(y), z = VALUES(z), last_seen_at = NOW(), metadata_json = VALUES(metadata_json)",
            state.Guid.GetCounter(), sourceType.c_str(), entry, bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
            object->GetPositionX(), object->GetPositionY(), object->GetPositionZ(), metadata.c_str());
        return;
    }

    if (std::string(poiType) == "objective_object")
    {
        CharacterDatabase.DirectPExecute(
            "INSERT INTO bot_memory_material_sources "
            "(bot_guid, item_id, source_type, source_entry, map_id, zone_id, area_id, x, y, z, drop_chance, observed_count, success_count, failure_count, last_seen_at, metadata_json) "
            "VALUES (%u, 0, '%s', %u, %u, %u, %u, %f, %f, %f, 0, 1, 0, 0, NOW(), '%s') "
            "ON DUPLICATE KEY UPDATE x = VALUES(x), y = VALUES(y), z = VALUES(z), observed_count = observed_count + 1, last_seen_at = NOW(), metadata_json = VALUES(metadata_json)",
            state.Guid.GetCounter(), sourceType.c_str(), entry, bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
            object->GetPositionX(), object->GetPositionY(), object->GetPositionZ(), metadata.c_str());
    }
}

void BotWorldPopulationMgr::MarkDeathDangerZone(WorldBotState& state, Player* bot, Unit const* target)
{
    if (!bot)
        return;

    uint32 sourceEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        sourceEntry = creature->GetEntry();

    if (state.LastDeathMapId == bot->GetMapId()
        && state.LastDeathAreaId == bot->GetAreaId()
        && Distance2d(state.LastDeathX, state.LastDeathY, bot->GetPositionX(), bot->GetPositionY()) <= 35.0f)
        ++state.RecentDeathCount;
    else
        state.RecentDeathCount = 1;

    state.LastDeathMapId = bot->GetMapId();
    state.LastDeathAreaId = bot->GetAreaId();
    state.LastDeathX = bot->GetPositionX();
    state.LastDeathY = bot->GetPositionY();

    std::ostringstream metadata;
    metadata << "{\"recent_death_count\":" << state.RecentDeathCount
             << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
             << ",\"source_entry\":" << sourceEntry << "}";
    std::string metadataJson = metadata.str();
    CharacterDatabase.EscapeString(metadataJson);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_danger_zones (bot_guid, map_id, zone_id, area_id, x, y, z, radius, danger_type, source_entry, death_count, failure_count, last_event_at, metadata_json) "
        "VALUES (%u, %u, %u, %u, %f, %f, %f, 35.0, '%s', %u, %u, %u, NOW(), '%s')",
        state.Guid.GetCounter(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(),
        state.RecentDeathCount >= Cohort().Config.MaxDeathsBeforeFallback ? "repeated_death" : "death", sourceEntry, state.RecentDeathCount, 0u, metadataJson.c_str());
}

void BotWorldPopulationMgr::MarkStuckFailure(WorldBotState& state, Player* bot)
{
    if (!bot)
        return;

    float fromX = state.ActivePathValid ? state.ActivePathFromX : state.LastX;
    float fromY = state.ActivePathValid ? state.ActivePathFromY : state.LastY;
    float fromZ = state.ActivePathValid ? state.ActivePathFromZ : state.LastZ;
    float toX = state.ActivePathValid ? state.ActivePathToX : bot->GetPositionX();
    float toY = state.ActivePathValid ? state.ActivePathToY : bot->GetPositionY();
    float toZ = state.ActivePathValid ? state.ActivePathToZ : bot->GetPositionZ();

    std::ostringstream metadata;
    metadata << "{\"stuck_timer_ms\":" << state.StuckTimer << "}";
    std::string metadataJson = metadata.str();
    CharacterDatabase.EscapeString(metadataJson);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_failed_paths (bot_guid, map_id, from_x, from_y, from_z, to_x, to_y, to_z, failure_type, failure_count, last_failed_at, metadata_json) "
        "VALUES (%u, %u, %f, %f, %f, %f, %f, %f, 'stuck', 1, NOW(), '%s')",
        state.Guid.GetCounter(), bot->GetMapId(), fromX, fromY, fromZ, toX, toY, toZ, metadataJson.c_str());

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_danger_zones (bot_guid, map_id, zone_id, area_id, x, y, z, radius, danger_type, stuck_count, failure_count, last_event_at, metadata_json) "
        "VALUES (%u, %u, %u, %u, %f, %f, %f, 20.0, 'stuck', 1, 1, NOW(), '%s')",
        state.Guid.GetCounter(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), metadataJson.c_str());
}

float BotWorldPopulationMgr::GetLocalDangerScore(uint32 botGuid, uint32 mapId, float x, float y, float z) const
{
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT COALESCE(SUM(death_count * 2 + stuck_count + failure_count), 0) "
        "FROM bot_memory_danger_zones "
        "WHERE bot_guid = %u AND map_id = %u "
        "AND POW(x - %f, 2) + POW(y - %f, 2) + POW(z - %f, 2) <= POW(radius, 2)",
        botGuid, mapId, x, y, z);
    return result ? result->Fetch()[0].GetFloat() : 0.0f;
}

bool BotWorldPopulationMgr::IsFailedPathRecently(uint32 botGuid, uint32 mapId, float fromX, float fromY, float toX, float toY) const
{
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT failure_count FROM bot_memory_failed_paths "
        "WHERE bot_guid = %u AND map_id = %u AND last_failed_at >= DATE_SUB(NOW(), INTERVAL 10 MINUTE) "
        "AND POW(from_x - %f, 2) + POW(from_y - %f, 2) <= POW(12.0, 2) "
        "AND POW(to_x - %f, 2) + POW(to_y - %f, 2) <= POW(12.0, 2) "
        "ORDER BY last_failed_at DESC LIMIT 1",
        botGuid, mapId, fromX, fromY, toX, toY);
    return bool(result);
}

bool BotWorldPopulationMgr::FindMemoryPoiTarget(Player* bot, float& x, float& y, float& z, uint64& poiId) const
{
    if (!bot)
        return false;

    QueryResult result = CharacterDatabase.PQuery(
        "SELECT id, x, y, z, score, visit_count, success_count, failure_count "
        "FROM bot_memory_pois "
        "WHERE bot_guid = %u AND map_id = %u AND zone_id = %u "
        "ORDER BY last_seen_at DESC LIMIT 16",
        bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetZoneId());
    if (!result)
        return false;

    bool found = false;
    float bestScore = -100000.0f;
    uint64 bestId = 0;
    float bestX = 0.0f;
    float bestY = 0.0f;
    float bestZ = 0.0f;
    do
    {
        Field* fields = result->Fetch();
        uint64 candidateId = fields[0].GetUInt64();
        float candidateX = fields[1].GetFloat();
        float candidateY = fields[2].GetFloat();
        float candidateZ = fields[3].GetFloat();
        float staticScore = fields[4].GetFloat();
        uint32 visitCount = fields[5].GetUInt32();
        uint32 successCount = fields[6].GetUInt32();
        uint32 failureCount = fields[7].GetUInt32();
        BotLearnedScore poiScore = BotExperienceLearningPolicy::ScorePoi(bot, candidateId, candidateX, candidateY, candidateZ, staticScore, visitCount, successCount, failureCount, Cohort().LearningConfig);
        BotLearnedScore pathScore = BotExperienceLearningPolicy::ScorePath(bot, bot->GetPositionX(), bot->GetPositionY(), candidateX, candidateY, Cohort().LearningConfig);
        if (poiScore.DangerScore >= 3.0f || pathScore.Penalty >= Cohort().LearningConfig.RecentFailurePenaltyWeight)
            continue;

        float adjustedScore = staticScore - float(visitCount) * 15.0f - float(failureCount) * 25.0f + poiScore.Score + pathScore.Score;
        if (!found || adjustedScore > bestScore)
        {
            found = true;
            bestScore = adjustedScore;
            bestId = candidateId;
            bestX = candidateX;
            bestY = candidateY;
            bestZ = candidateZ;
        }
    } while (result->NextRow());

    if (!found)
        return false;

    poiId = bestId;
    x = bestX;
    y = bestY;
    z = bestZ;
    return true;
}

void BotWorldPopulationMgr::MarkPoiVisited(uint64 poiId) const
{
    if (!poiId)
        return;

    CharacterDatabase.DirectPExecute("UPDATE bot_memory_pois SET visit_count = visit_count + 1, last_seen_at = NOW() WHERE id = " UI64FMTD, poiId);
}

