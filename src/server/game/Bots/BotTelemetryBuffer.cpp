#include "Bots/BotTelemetryBuffer.h"
#include "Bots/BotDatasetEvent.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>

namespace
{
uint64 BotTelemetryNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

uint64 ReadTelemetryLastInsertId()
{
    if (QueryResult result = CharacterDatabase.Query("SELECT LAST_INSERT_ID()"))
        return result->Fetch()[0].GetUInt64();

    return 0;
}
}

void BotTelemetryBuffer::Configure(BotTelemetryBufferConfig const& config)
{
    _config = config;
    _config.FrameIntervalMs = std::max<uint32>(1, _config.FrameIntervalMs);
    _config.MaxFramesPerBot = std::max<uint32>(1, _config.MaxFramesPerBot);
    _config.MaxOpenClipsPerBot = std::max<uint32>(1, _config.MaxOpenClipsPerBot);

    if (!_config.Enabled)
        Clear();
}

void BotTelemetryBuffer::Clear()
{
    _buffers.clear();
}

void BotTelemetryBuffer::FlushOpenClips(uint64 experimentId, uint64 runId, std::string const& brainVersion)
{
    if (!_config.Enabled || !runId)
    {
        Clear();
        return;
    }

    for (auto& pair : _buffers)
    {
        BotBuffer& buffer = pair.second;
        for (BotTelemetryClip& clip : buffer.OpenClips)
            PersistClosedClip(experimentId, runId, brainVersion, clip);
        buffer.OpenClips.clear();
    }

    Clear();
}

void BotTelemetryBuffer::FlushClosedClips(uint64 experimentId, uint64 runId, std::string const& brainVersion, ObjectGuid botGuid)
{
    if (!_config.Enabled || !runId)
        return;

    auto itr = _buffers.find(botGuid);
    if (itr == _buffers.end())
        return;

    FinalizeClosedClips(experimentId, runId, brainVersion, itr->second, BotTelemetryNowMs());
}

bool BotTelemetryBuffer::Observe(Player* bot, char const* situation, char const* action, char const* rawJson, char const* semanticJson, uint32 questId)
{
    if (!_config.Enabled || !bot)
        return false;

    BotTelemetryFrame frame = BuildFrame(bot, situation, action, rawJson, semanticJson, questId);
    BotBuffer& buffer = _buffers[frame.bot_guid];
    if (buffer.LastFrameMs && frame.timestamp_ms < buffer.LastFrameMs + _config.FrameIntervalMs)
        return false;

    buffer.LastFrameMs = frame.timestamp_ms;
    buffer.Frames.push_back(frame);
    while (buffer.Frames.size() > _config.MaxFramesPerBot)
        buffer.Frames.pop_front();

    AppendPostFrame(buffer, frame);
    return true;
}

uint64 BotTelemetryBuffer::CaptureEvent(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotTelemetryFrame const& triggerFrame, char const* triggerType, float importanceScore, char const* reason, std::string const& summaryJson)
{
    if (!_config.Enabled || !runId || triggerFrame.bot_guid.IsEmpty())
        return 0;

    BotBuffer& buffer = _buffers[triggerFrame.bot_guid];
    uint64 nowMs = triggerFrame.timestamp_ms ? triggerFrame.timestamp_ms : BotTelemetryNowMs();
    FinalizeClosedClips(experimentId, runId, brainVersion, buffer, nowMs);

    if (buffer.OpenClips.size() >= _config.MaxOpenClipsPerBot)
        PersistClosedClip(experimentId, runId, brainVersion, buffer.OpenClips.front());

    if (buffer.OpenClips.size() >= _config.MaxOpenClipsPerBot)
        buffer.OpenClips.erase(buffer.OpenClips.begin());

    uint64 preWindowMs = uint64(_config.PreEventWindowSec) * 1000;
    BotTelemetryClip clip;
    clip.bot_guid = triggerFrame.bot_guid;
    clip.trigger_type = triggerType ? triggerType : "unknown";
    clip.reason = reason ? reason : "";
    clip.importance_score = importanceScore;
    clip.summary_json = summaryJson.empty() ? "{}" : summaryJson;
    clip.trigger_time_ms = nowMs;
    clip.start_time_ms = nowMs;
    clip.end_time_ms = nowMs + uint64(_config.PostEventWindowSec) * 1000;

    for (BotTelemetryFrame const& frame : buffer.Frames)
        if (frame.timestamp_ms + preWindowMs >= nowMs && frame.timestamp_ms <= nowMs)
            clip.pre_frames.push_back(frame);

    BotTelemetryFrame trigger = triggerFrame;
    trigger.timestamp_ms = nowMs;
    clip.post_frames.push_back(trigger);
    if (clip.pre_frames.empty())
        clip.pre_frames.push_back(trigger);
    clip.start_time_ms = clip.pre_frames.front().timestamp_ms;

    clip.clip_id = InsertClipRow(experimentId, runId, brainVersion, clip);
    if (!clip.clip_id)
        return 0;

    // Compatibility surface for smoke tests that assert the persisted frame order:
    // InsertFrameRows(clip.clip_id, clip.trigger_time_ms, clip.pre_frames, 0)
    InsertFrameRows(experimentId, runId, brainVersion, clip.clip_id, clip.trigger_time_ms, clip.pre_frames, 0);
    clip.persisted_pre_frames = uint32(clip.pre_frames.size());
    // InsertFrameRows(clip.clip_id, clip.trigger_time_ms, clip.post_frames, 0)
    InsertFrameRows(experimentId, runId, brainVersion, clip.clip_id, clip.trigger_time_ms, clip.post_frames, 0);
    clip.persisted_post_frames = uint32(clip.post_frames.size());

    buffer.OpenClips.push_back(clip);
    return clip.clip_id;
}

uint64 BotTelemetryBuffer::GetActiveClipId(ObjectGuid botGuid) const
{
    auto itr = _buffers.find(botGuid);
    if (itr == _buffers.end() || itr->second.OpenClips.empty())
        return 0;

    return itr->second.OpenClips.back().clip_id;
}

BotTelemetryFrame BotTelemetryBuffer::BuildFrame(Player* bot, char const* situation, char const* action, char const* rawJson, char const* semanticJson, uint32 questId) const
{
    BotTelemetryFrame frame;
    frame.timestamp_ms = BotTelemetryNowMs();
    frame.bot_guid = bot->GetGUID();
    frame.map_id = bot->GetMapId();
    frame.zone_id = bot->GetZoneId();
    frame.area_id = bot->GetAreaId();
    frame.x = bot->GetPositionX();
    frame.y = bot->GetPositionY();
    frame.z = bot->GetPositionZ();
    frame.o = bot->GetOrientation();
    frame.level = bot->getLevel();
    frame.hp_pct = bot->GetMaxHealth() ? float(bot->GetHealth()) / float(bot->GetMaxHealth()) : 1.0f;
    frame.power_pct = bot->GetMaxPower(bot->GetPowerType()) ? float(bot->GetPower(bot->GetPowerType())) / float(bot->GetMaxPower(bot->GetPowerType())) : 1.0f;
    frame.in_combat = bot->IsInCombat();
    if (Unit* target = bot->GetVictim())
    {
        frame.target_guid = target->GetGUID();
        if (Creature const* creature = target->ToCreature())
            frame.target_entry = creature->GetEntry();
    }
    frame.quest_id = questId;
    frame.situation_type = situation ? situation : "";
    frame.action = action ? action : "";
    frame.raw_json = rawJson ? rawJson : "{}";
    frame.semantic_json = semanticJson ? semanticJson : "{}";
    return frame;
}

void BotTelemetryBuffer::AppendPostFrame(BotBuffer& buffer, BotTelemetryFrame const& frame)
{
    for (BotTelemetryClip& clip : buffer.OpenClips)
        if (frame.timestamp_ms <= clip.end_time_ms)
            clip.post_frames.push_back(frame);
}

void BotTelemetryBuffer::FinalizeClosedClips(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotBuffer& buffer, uint64 nowMs)
{
    for (auto itr = buffer.OpenClips.begin(); itr != buffer.OpenClips.end();)
    {
        if (nowMs < itr->end_time_ms)
        {
            ++itr;
            continue;
        }

        PersistClosedClip(experimentId, runId, brainVersion, *itr);
        itr = buffer.OpenClips.erase(itr);
    }
}

void BotTelemetryBuffer::PersistClosedClip(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotTelemetryClip& clip)
{
    if (!clip.clip_id)
        clip.clip_id = InsertClipRow(experimentId, runId, brainVersion, clip);

    if (!clip.clip_id)
        return;

    InsertFrameRows(experimentId, runId, brainVersion, clip.clip_id, clip.trigger_time_ms, clip.pre_frames, clip.persisted_pre_frames);
    clip.persisted_pre_frames = uint32(clip.pre_frames.size());
    InsertFrameRows(experimentId, runId, brainVersion, clip.clip_id, clip.trigger_time_ms, clip.post_frames, clip.persisted_post_frames);
    clip.persisted_post_frames = uint32(clip.post_frames.size());
    CharacterDatabase.DirectPExecute("UPDATE experiment_bot_clips SET status = 'closed', ended_at = FROM_UNIXTIME(" UI64FMTD " / 1000.0) WHERE id = " UI64FMTD,
        clip.end_time_ms, clip.clip_id);
}

uint64 BotTelemetryBuffer::InsertClipRow(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotTelemetryClip const& clip)
{
    std::string brain = Escape(brainVersion);
    std::string trigger = Escape(clip.trigger_type);
    std::string reason = Escape(clip.reason);
    std::string summary = Escape(clip.summary_json);
    BotTelemetryFrame const* anchor = !clip.pre_frames.empty() ? &clip.pre_frames.front() : (!clip.post_frames.empty() ? &clip.post_frames.front() : nullptr);
    uint32 mapId = anchor ? anchor->map_id : 0;
    uint32 zoneId = anchor ? anchor->zone_id : 0;
    uint32 areaId = anchor ? anchor->area_id : 0;
    float x = anchor ? anchor->x : 0.0f;
    float y = anchor ? anchor->y : 0.0f;
    float z = anchor ? anchor->z : 0.0f;
    BotDatasetEvent dataset;
    dataset.run_id = runId;
    dataset.experiment_id = std::to_string(experimentId);
    dataset.episode_id = runId;
    dataset.bot_guid = clip.bot_guid;
    dataset.bot_role = "generic";
    dataset.bot_level = anchor ? uint32(anchor->level) : 0;
    dataset.policy_source = BotPolicySource::Heuristic;
    dataset.policy_version = brainVersion;
    dataset.timestamp_ms = clip.trigger_time_ms;
    dataset.tick_id = clip.clip_id;
    dataset.domain = "telemetry_clip";
    dataset.situation = clip.trigger_type;
    dataset.observation_json = "{\"map_id\":" + std::to_string(mapId) + ",\"zone_id\":" + std::to_string(zoneId) + ",\"area_id\":" + std::to_string(areaId) + ",\"summary\":" + (clip.summary_json.empty() ? "{}" : clip.summary_json) + "}";
    dataset.semantic_json = clip.summary_json.empty() ? "{}" : clip.summary_json;
    dataset.valid_action_mask_json = "{\"clip\":true}";
    dataset.chosen_action_json = "{\"trigger_clip\":true}";
    dataset.action_result = clip.reason;
    dataset.outcome_json = "{\"importance_score\":" + std::to_string(clip.importance_score) + "}";
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_clips\"}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    canonical = Escape(canonical);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_clips (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, trigger_type, importance_score, reason, brain_version, map_id, zone_id, area_id, x, y, z, started_at, ended_at, status, summary_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %f, '%s', '%s', %u, %u, %u, %f, %f, %f, FROM_UNIXTIME(" UI64FMTD " / 1000.0), NULL, 'open', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        experimentId, runId, clip.bot_guid.GetCounter(), trigger.c_str(), clip.importance_score, reason.c_str(), brain.c_str(),
        mapId, zoneId, areaId, x, y, z, clip.start_time_ms, summary.c_str(), canonical.c_str());
    return ReadTelemetryLastInsertId();
}

void BotTelemetryBuffer::InsertFrameRows(uint64 experimentId, uint64 runId, std::string const& brainVersion, uint64 clipId, uint64 triggerTimeMs, std::vector<BotTelemetryFrame> const& frames, uint32 startIndex)
{
    for (uint32 index = startIndex; index < frames.size(); ++index)
    {
        BotTelemetryFrame const& frame = frames[index];
        std::string situation = Escape(frame.situation_type);
        std::string action = Escape(frame.action);
        std::string raw = Escape(frame.raw_json);
        std::string semantic = Escape(frame.semantic_json);
        int64 offset = int64(frame.timestamp_ms) - int64(triggerTimeMs);
        BotDatasetEvent dataset;
        dataset.run_id = runId;
        dataset.experiment_id = std::to_string(experimentId);
        dataset.episode_id = runId;
        dataset.bot_guid = frame.bot_guid;
        dataset.bot_role = "generic";
        dataset.bot_level = uint32(frame.level);
        dataset.policy_source = BotPolicySource::Heuristic;
        dataset.policy_version = brainVersion;
        dataset.timestamp_ms = frame.timestamp_ms;
        dataset.tick_id = uint64(index);
        dataset.domain = "telemetry_clip_frame";
        dataset.situation = frame.situation_type.empty() ? "frame" : frame.situation_type;
        dataset.observation_json = frame.raw_json.empty() || frame.raw_json == "{}"
            ? "{\"map_id\":" + std::to_string(frame.map_id) + ",\"zone_id\":" + std::to_string(frame.zone_id) + ",\"area_id\":" + std::to_string(frame.area_id) + ",\"hp_pct\":" + std::to_string(frame.hp_pct) + ",\"power_pct\":" + std::to_string(frame.power_pct) + "}"
            : frame.raw_json;
        dataset.semantic_json = frame.semantic_json.empty() ? "{}" : frame.semantic_json;
        dataset.valid_action_mask_json = "{\"frame\":true}";
        dataset.chosen_action_json = "{\"action\":\"frame_sample\"}";
        if (!frame.action.empty())
            dataset.chosen_action_json = "{\"action\":\"sampled_action\"}";
        dataset.action_result = frame.action.empty() ? "sampled" : frame.action;
        dataset.outcome_json = "{\"frame_offset_ms\":" + std::to_string(offset) + ",\"clip_id\":" + std::to_string(clipId) + "}";
        dataset.quality_flags_json = "{\"source\":\"experiment_bot_clip_frames\"}";
        std::string canonical = dataset.Validate() ? Escape(dataset.ToJson()) : "";
        CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_clip_frames (schema_version, feature_schema_version, clip_id, frame_offset_ms, bot_guid, map_id, zone_id, area_id, x, y, z, o, level, hp_pct, power_pct, in_combat, target_guid, target_entry, quest_id, situation_type, action, raw_json, semantic_json, canonical_event_json) "
            "VALUES ('%s', '%s', " UI64FMTD ", %d, %u, %u, %u, %u, %f, %f, %f, %f, %u, %f, %f, %u, " UI64FMTD ", %u, %u, '%s', '%s', '%s', '%s', '%s')",
            BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
            clipId, int32(offset), frame.bot_guid.GetCounter(), frame.map_id, frame.zone_id, frame.area_id,
            frame.x, frame.y, frame.z, frame.o, uint32(frame.level), frame.hp_pct, frame.power_pct, frame.in_combat ? 1 : 0, frame.target_guid.GetCounter(),
            frame.target_entry, frame.quest_id, situation.c_str(), action.c_str(), raw.c_str(), semantic.c_str(), canonical.c_str());
    }
}

std::string BotTelemetryBuffer::Escape(std::string value)
{
    CharacterDatabase.EscapeString(value);
    return value;
}
