#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotDatasetEvent.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include "Bots/BotMgr.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Config.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Player.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <set>
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

uint64 ReadLastInsertId()
{
    if (QueryResult result = CharacterDatabase.Query("SELECT LAST_INSERT_ID()"))
        return result->Fetch()[0].GetUInt64();

    return 0;
}


std::string BoundedResultLabel(char const* result)
{
    std::string label = result && *result ? result : "ok";
    if (label.size() <= 63)
        return label;
    return label.substr(0, 63);
}

std::string BoundedResultLabel(std::string const& result)
{
    return BoundedResultLabel(result.c_str());
}

BotPolicySource WorldPolicySource(BotPolicyModelConfig const& config, bool decision)
{
    if (config.Enabled && !config.Version.empty())
    {
        if (config.Mode == "assist")
            return BotPolicySource::AssistModel;
        if (config.Mode == "control")
            return BotPolicySource::ControlModel;
        return BotPolicySource::ShadowModel;
    }

    return decision ? BotPolicySource::Exploration : BotPolicySource::Heuristic;
}

std::string WorldPolicyVersion(BotPolicyModelConfig const& config, std::string const& brainVersion)
{
    return config.Enabled && !config.Version.empty() ? config.Version : brainVersion;
}
}

void BotWorldPopulationMgr::RecordRunStart()
{
    std::string escapedName = Cohort().Config.Name;
    std::string escapedConfig = BuildConfigJson();
    std::string escapedBrain = Cohort().Config.BrainVersion;
    CharacterDatabase.EscapeString(escapedName);
    CharacterDatabase.EscapeString(escapedConfig);
    CharacterDatabase.EscapeString(escapedBrain);
    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_runs (experiment_name, config_json, brain_version, status, started_at) VALUES ('%s', '%s', '%s', 'running', NOW())",
        escapedName.c_str(), escapedConfig.c_str(), escapedBrain.c_str());
    Cohort().RunId = ReadLastInsertId();
    Cohort().ExperimentId = Cohort().RunId;
    Cohort().Metrics.ExperimentId = Cohort().ExperimentId;
    Cohort().Metrics.RunId = Cohort().RunId;
    Cohort().ExperimentCoordinator.Configure(Cohort().RunId, Cohort().Config.BrainVersion);
}

void BotWorldPopulationMgr::RecordRunStop()
{
    if (!Cohort().RunId)
        return;

    FlushPendingDecisionFingerprintMemory();
    std::string summary = GetSummaryJson();
    CharacterDatabase.EscapeString(summary);
    CharacterDatabase.DirectPExecute("UPDATE experiment_bot_runs SET status = 'stopped', ended_at = NOW(), summary_json = '%s' WHERE id = " UI64FMTD, summary.c_str(), Cohort().RunId);
}

BotWorldPopulationMgr::ReplayRecord BotWorldPopulationMgr::LoadReplayRecord(uint64 replayId) const
{
    ReplayRecord record;
    if (!replayId)
        return record;

    QueryResult result = CharacterDatabase.PQuery(
        "SELECT id, experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, "
        "bot_snapshot_json, world_snapshot_json, COALESCE(party_snapshot_json, ''), raw_state_json, semantic_state_json, "
        "COALESCE(chosen_action_json, ''), failure_json "
        "FROM experiment_bot_replay_records WHERE id = " UI64FMTD,
        replayId);
    if (!result)
        return record;

    Field* fields = result->Fetch();
    record.Loaded = true;
    record.Id = fields[0].GetUInt64();
    record.ExperimentId = fields[1].GetUInt64();
    record.RunId = fields[2].GetUInt64();
    record.BotGuid = fields[3].GetUInt32();
    record.ReplayType = fields[4].GetString();
    record.MapId = fields[5].GetUInt32();
    record.ZoneId = fields[6].GetUInt32();
    record.X = fields[7].GetFloat();
    record.Y = fields[8].GetFloat();
    record.Z = fields[9].GetFloat();
    record.O = fields[10].GetFloat();
    record.BotSnapshotJson = fields[11].GetString();
    record.WorldSnapshotJson = fields[12].GetString();
    record.PartySnapshotJson = fields[13].GetString();
    record.RawStateJson = fields[14].GetString();
    record.SemanticStateJson = fields[15].GetString();
    record.ChosenActionJson = fields[16].GetString();
    record.FailureJson = fields[17].GetString();
    return record;
}

BotWorldPopulationMgr::ReplayRecord BotWorldPopulationMgr::LoadReplayRecord(std::string const& replayType, std::string const& selector) const
{
    if (!selector.empty() && selector != "latest" && selector.find_first_not_of("0123456789") == std::string::npos)
        return LoadReplayRecord(uint64(strtoull(selector.c_str(), nullptr, 10)));

    std::string type = replayType.empty() ? "failure" : replayType;
    std::string where;
    if (type == "failure")
        where = "replay_type LIKE '%failure%'";
    else
    {
        CharacterDatabase.EscapeString(type);
        where = "replay_type = '" + type + "'";
    }

    std::string query =
        "SELECT id FROM experiment_bot_replay_records WHERE " + where +
        " ORDER BY id DESC LIMIT 1";
    if (QueryResult result = CharacterDatabase.Query(query.c_str()))
        return LoadReplayRecord(result->Fetch()[0].GetUInt64());

    return ReplayRecord();
}

void BotWorldPopulationMgr::RecordReplayEvent(WorldBotState const& state, Player* bot, char const* eventType, ReplayRecord const& record, char const* result, char const* contextJson)
{
    if (!Cohort().RunId || !bot)
        return;

    uint64 clipId = Cohort().TelemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";

    std::string raw = record.RawStateJson.empty() ? "{}" : record.RawStateJson;
    std::string semantic = record.SemanticStateJson.empty() ? "{}" : record.SemanticStateJson;
    std::string event = eventType ? eventType : "replay_event";
    std::string res = BoundedResultLabel(result);
    std::string brain = Cohort().Config.BrainVersion;
    std::string context = contextJson ? contextJson : "{}";
    BotDatasetEvent dataset;
    dataset.run_id = Cohort().RunId;
    dataset.experiment_id = std::to_string(Cohort().ExperimentId);
    dataset.episode_id = Cohort().RunId;
    dataset.bot_guid = bot->GetGUID();
    dataset.bot_role = GetDungeonRole(bot);
    dataset.bot_level = uint32(bot->getLevel());
    dataset.policy_source = WorldPolicySource(Cohort().PolicyModelConfig, false);
    dataset.policy_version = WorldPolicyVersion(Cohort().PolicyModelConfig, Cohort().Config.BrainVersion);
    dataset.timestamp_ms = NowMs();
    dataset.tick_id = state.EventSequence;
    dataset.domain = "replay_event";
    dataset.situation = event;
    dataset.observation_json = raw;
    dataset.semantic_json = semantic;
    dataset.valid_action_mask_json = "{\"event\":true}";
    dataset.chosen_action_json = "{\"event_type\":\"" + JsonEscape(event) + "\",\"replay_id\":" + std::to_string(record.Id) + "}";
    dataset.action_result = res.empty() ? "ok" : res;
    dataset.outcome_json = "{\"result\":\"" + JsonEscape(dataset.action_result) + "\",\"replay_id\":" + std::to_string(record.Id) + "}";
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_events\",\"replay_event\":true}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(res);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(context);
    CharacterDatabase.EscapeString(canonical);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, result, value_int, raw_json, semantic_json, context_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', '%s', %u, '%s', '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), res.c_str(),
        uint32(record.Id), raw.c_str(), semantic.c_str(), context.c_str(), canonical.c_str());
}

BotWorldPopulationMgr::ReplayExecutionResult BotWorldPopulationMgr::ExecuteReplayRecord(ReplayRecord const& record, std::string const& brainVersion)
{
    ReplayExecutionResult result;
    result.ReplayId = record.Id;
    result.ReplayType = record.ReplayType;
    result.BrainVersion = brainVersion.empty() ? Cohort().Config.BrainVersion : brainVersion;

    if (!record.Loaded)
    {
        result.FailureReason = "replay_record_not_found";
        return result;
    }

    if (Cohort().Active)
    {
        result.FailureReason = "botexp_population_active";
        return result;
    }

    if (!sConfigMgr->GetBoolDefault("BotWorld.Enable", false) || !sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
    {
        result.FailureReason = "botworld_or_playerbot_disabled";
        return result;
    }

    uint64 oldExperimentId = Cohort().ExperimentId;
    uint64 oldRunId = Cohort().RunId;
    uint32 oldElapsedMs = Cohort().ElapsedMs;
    BotWorldRuntimeMode oldRuntimeMode = Cohort().RuntimeMode;
    bool oldNonCertifyingAssistance = Cohort().NonCertifyingAssistance;
    BotWorldExperimentConfig oldConfig = Cohort().Config;
    BotWorldStatus oldMetrics = Cohort().Metrics;
    std::vector<WorldBotState> oldBots = Party().Bots;
    std::set<uint32> oldFailedSpawnGuids = Cohort().FailedSpawnGuids;

    Cohort().RuntimeMode = BotWorldRuntimeMode::ReplayFixture;
    Cohort().NonCertifyingAssistance = true;

    Cohort().Config = BotWorldExperimentConfig();
    Cohort().Config.Name = "replay_" + std::to_string(record.Id);
    Cohort().Config.TargetPopulation = 1;
    Cohort().Config.MapId = record.MapId;
    Cohort().Config.ZoneId = record.ZoneId;
    Cohort().Config.CenterX = record.X;
    Cohort().Config.CenterY = record.Y;
    Cohort().Config.CenterZ = record.Z;
    Cohort().Config.Radius = 25.0f;
    Cohort().Config.AllowCombat = true;
    Cohort().Config.AllowQuesting = true;
    Cohort().Config.AllowDungeons = record.ReplayType.find("boss") != std::string::npos || record.ReplayType.find("trash") != std::string::npos;
    Cohort().Config.AllowRaids = record.ReplayType.find("raid") != std::string::npos || record.ReplayType.find("boss") != std::string::npos;
    Cohort().Config.BrainVersion = result.BrainVersion;
    Party().Bots.clear();
    Cohort().FailedSpawnGuids.clear();
    Cohort().Metrics = BotWorldStatus();
    Cohort().Metrics.Active = false;
    Cohort().Metrics.Name = Cohort().Config.Name;
    Cohort().Metrics.TargetBots = 1;
    Cohort().ElapsedMs = 0;

    RecordRunStart();
    result.RunId = Cohort().RunId;

    Player* bot = nullptr;
    if (record.BotGuid)
        bot = sBotMgr->SpawnWorldBot("any", std::to_string(record.BotGuid), record.MapId, record.X, record.Y, record.Z, record.O);

    if (!bot)
    {
        uint32 fallbackGuid = SelectPoolCandidateGuid();
        if (fallbackGuid)
            bot = sBotMgr->SpawnWorldBot("any", std::to_string(fallbackGuid), record.MapId, record.X, record.Y, record.Z, record.O);
    }

    if (!bot)
    {
        result.FailureReason = "no_available_replay_bot";
        RecordRunStop();
        Cohort().ExperimentId = oldExperimentId;
        Cohort().RunId = oldRunId;
        Cohort().ElapsedMs = oldElapsedMs;
        Cohort().RuntimeMode = oldRuntimeMode;
        Cohort().NonCertifyingAssistance = oldNonCertifyingAssistance;
        Cohort().Config = oldConfig;
        Cohort().Metrics = oldMetrics;
        Party().Bots = oldBots;
        Cohort().FailedSpawnGuids = oldFailedSpawnGuids;
        return result;
    }

    bot->CombatStop(true);
    bot->CastStop();
    if (!bot->IsAlive())
        bot->ResurrectPlayer(1.0f, false);
    bot->TeleportTo(record.MapId, record.X, record.Y, record.Z, record.O);
    bot->SetFullHealth();
    bot->SetFullPower(bot->GetPowerType());

    WorldBotState state;
    state.Guid = bot->GetGUID();
    state.ValidationRouteGeneration = Party().ValidationRouteGeneration;
    state.DecisionTimer = 0;
    state.LastX = record.X;
    state.LastY = record.Y;
    state.LastZ = record.Z;
    state.ActivityType = "replay";
    Party().Bots.push_back(state);
    Cohort().Metrics.ActiveBots = 1;

    RecordActivityStart(Party().Bots.back(), bot);
    std::ostringstream startContext;
    startContext << "{\"replay_id\":" << record.Id
                 << ",\"source_experiment_id\":" << record.ExperimentId
                 << ",\"source_run_id\":" << record.RunId
                 << ",\"source_bot_guid\":" << record.BotGuid
                 << ",\"replay_type\":\"" << JsonEscape(record.ReplayType) << "\""
                 << ",\"source_failure\":" << (record.FailureJson.empty() ? "{}" : record.FailureJson)
                 << ",\"source_action\":" << (record.ChosenActionJson.empty() ? "{}" : record.ChosenActionJson) << "}";
    RecordReplayEvent(Party().Bots.back(), bot, "replay_started", record, "ok", startContext.str().c_str());

    UpdateBot(Party().Bots.back(), std::max<uint32>(500, sConfigMgr->GetIntDefault("BotWorld.DecisionTickMs", 3000)));

    BotRolePowerBreakdown finalPower = BotLongTermProgressionBrain::CalculateRolePower(bot);
    result.FinalPower = finalPower.Total;
    result.Decisions = Cohort().Metrics.Decisions;
    result.Failures = Cohort().Metrics.Failures;
    result.Deaths = Cohort().Metrics.Deaths;
    result.Kills = Cohort().Metrics.Kills;
    result.StuckEvents = Cohort().Metrics.StuckEvents;
    result.Success = bot->IsAlive() && !Cohort().Metrics.Failures && !Cohort().Metrics.Deaths;
    result.Ok = true;
    result.FirstAction = record.ChosenActionJson.empty() ? "{}" : record.ChosenActionJson;

    std::ostringstream finishContext;
    finishContext << "{\"replay_id\":" << record.Id
                  << ",\"success\":" << (result.Success ? "true" : "false")
                  << ",\"decisions\":" << result.Decisions
                  << ",\"failures\":" << result.Failures
                  << ",\"deaths\":" << result.Deaths
                  << ",\"kills\":" << result.Kills
                  << ",\"stuck_events\":" << result.StuckEvents
                  << ",\"final_power\":" << result.FinalPower << "}";
    RecordReplayEvent(Party().Bots.back(), bot, "replay_finished", record, result.Success ? "success" : "failure", finishContext.str().c_str());

    RecordActivityStop(Party().Bots.back(), bot);
    BotRaidAreaAuthority::Clear(bot->GetGUID().GetRawValue());
    FlushDecisionFingerprintMemory(Party().Bots.back());
    sBotMgr->RemoveWorldBot(bot->GetGUID());
    Party().Bots.clear();
    RecordRunStop();

    Cohort().ExperimentId = oldExperimentId;
    Cohort().RunId = oldRunId;
    Cohort().ElapsedMs = oldElapsedMs;
    Cohort().RuntimeMode = oldRuntimeMode;
    Cohort().NonCertifyingAssistance = oldNonCertifyingAssistance;
    Cohort().Config = oldConfig;
    Cohort().Metrics = oldMetrics;
    Party().Bots = oldBots;
    Cohort().FailedSpawnGuids = oldFailedSpawnGuids;
    return result;
}

std::string BotWorldPopulationMgr::BuildReplayResultJson(ReplayExecutionResult const& result) const
{
    std::ostringstream json;
    json << "{\"ok\":" << (result.Ok ? "true" : "false")
         << ",\"action\":\"botexp_replay\""
         << ",\"replay_id\":" << result.ReplayId
         << ",\"run_id\":" << result.RunId
         << ",\"replay_type\":\"" << JsonEscape(result.ReplayType) << "\""
         << ",\"brain_version\":\"" << JsonEscape(result.BrainVersion) << "\""
         << ",\"success\":" << (result.Success ? "true" : "false")
         << ",\"metrics\":{\"decisions\":" << result.Decisions
         << ",\"failures\":" << result.Failures
         << ",\"deaths\":" << result.Deaths
         << ",\"kills\":" << result.Kills
         << ",\"stuck_events\":" << result.StuckEvents
         << ",\"final_power\":" << result.FinalPower << "}"
         << ",\"failure_reason\":" << (result.FailureReason.empty() ? "null" : ("\"" + JsonEscape(result.FailureReason) + "\""))
         << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::Replay(std::string const& replayType, std::string const& selector, std::string const& brainVersion)
{
    ReplayRecord record = LoadReplayRecord(replayType, selector.empty() ? "latest" : selector);
    std::string version = brainVersion.empty() ? sConfigMgr->GetStringDefault("BotExperiment.BrainVersion", Cohort().Config.BrainVersion) : brainVersion;
    return BuildReplayResultJson(ExecuteReplayRecord(record, version));
}

std::string BotWorldPopulationMgr::CompareBrains(uint64 replayId, std::string const& firstBrainVersion, std::string const& secondBrainVersion)
{
    ReplayRecord record = LoadReplayRecord(replayId);
    ReplayExecutionResult first = ExecuteReplayRecord(record, firstBrainVersion);
    ReplayExecutionResult second = ExecuteReplayRecord(record, secondBrainVersion);
    std::ostringstream json;
    json << "{\"ok\":" << ((first.Ok && second.Ok) ? "true" : "false")
         << ",\"action\":\"botexp_comparebrain\""
         << ",\"replay_id\":" << replayId
         << ",\"first\":" << BuildReplayResultJson(first)
         << ",\"second\":" << BuildReplayResultJson(second)
         << ",\"winner\":";
    if (!first.Ok || !second.Ok || first.Success == second.Success)
        json << "null";
    else
        json << "\"" << JsonEscape(first.Success ? firstBrainVersion : secondBrainVersion) << "\"";
    json << ",\"failure_reason\":";
    if (first.Ok && second.Ok)
        json << "null";
    else if (!first.FailureReason.empty())
        json << "\"" << JsonEscape(first.FailureReason) << "\"";
    else
        json << "\"" << JsonEscape(second.FailureReason) << "\"";
    json << "}";
    return json.str();
}
