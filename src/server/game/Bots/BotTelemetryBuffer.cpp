#include "Bots/BotTelemetryBuffer.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>

namespace
{
uint64 NowMs()
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

    FinalizeClosedClips(experimentId, runId, brainVersion, itr->second, NowMs());
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

uint64 BotTelemetryBuffer::CaptureEvent(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotTelemetryFrame const& triggerFrame, char const* triggerType, float importanceScore, std::string const& summaryJson)
{
    if (!_config.Enabled || !runId || triggerFrame.bot_guid.IsEmpty())
        return 0;

    BotBuffer& buffer = _buffers[triggerFrame.bot_guid];
    uint64 nowMs = triggerFrame.timestamp_ms ? triggerFrame.timestamp_ms : NowMs();
    FinalizeClosedClips(experimentId, runId, brainVersion, buffer, nowMs);

    if (buffer.OpenClips.size() >= _config.MaxOpenClipsPerBot)
        PersistClosedClip(experimentId, runId, brainVersion, buffer.OpenClips.front());

    if (buffer.OpenClips.size() >= _config.MaxOpenClipsPerBot)
        buffer.OpenClips.erase(buffer.OpenClips.begin());

    uint64 preWindowMs = uint64(_config.PreEventWindowSec) * 1000;
    BotTelemetryClip clip;
    clip.bot_guid = triggerFrame.bot_guid;
    clip.trigger_type = triggerType ? triggerType : "unknown";
    clip.importance_score = importanceScore;
    clip.summary_json = summaryJson.empty() ? "{}" : summaryJson;
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

    clip.clip_id = InsertClipRow(experimentId, runId, brainVersion, clip);
    if (!clip.clip_id)
        return 0;

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
    frame.timestamp_ms = NowMs();
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

    InsertFrameRows(experimentId, runId, clip.clip_id, clip.pre_frames, "pre");
    InsertFrameRows(experimentId, runId, clip.clip_id, clip.post_frames, "post");
    CharacterDatabase.DirectPExecute("UPDATE experiment_bot_telemetry_clips SET status = 'closed', end_time_ms = " UI64FMTD ", pre_frame_count = %u, post_frame_count = %u WHERE id = " UI64FMTD,
        clip.end_time_ms, uint32(clip.pre_frames.size()), uint32(clip.post_frames.size()), clip.clip_id);
}

uint64 BotTelemetryBuffer::InsertClipRow(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotTelemetryClip const& clip)
{
    std::string brain = Escape(brainVersion);
    std::string trigger = Escape(clip.trigger_type);
    std::string summary = Escape(clip.summary_json);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_telemetry_clips (experiment_id, run_id, bot_guid, brain_version, trigger_type, importance_score, start_time_ms, end_time_ms, pre_frame_count, post_frame_count, summary_json, status) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', '%s', %f, " UI64FMTD ", " UI64FMTD ", %u, %u, '%s', 'open')",
        experimentId, runId, clip.bot_guid.GetCounter(), brain.c_str(), trigger.c_str(), clip.importance_score, clip.start_time_ms, clip.end_time_ms,
        uint32(clip.pre_frames.size()), uint32(clip.post_frames.size()), summary.c_str());
    return ReadTelemetryLastInsertId();
}

void BotTelemetryBuffer::InsertFrameRows(uint64 experimentId, uint64 runId, uint64 clipId, std::vector<BotTelemetryFrame> const& frames, char const* framePhase)
{
    uint32 index = 0;
    for (BotTelemetryFrame const& frame : frames)
    {
        std::string situation = Escape(frame.situation_type);
        std::string action = Escape(frame.action);
        std::string raw = Escape(frame.raw_json);
        std::string semantic = Escape(frame.semantic_json);
        std::string phase = Escape(framePhase ? framePhase : "");
        CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_telemetry_frames (experiment_id, run_id, clip_id, bot_guid, frame_phase, frame_index, timestamp_ms, map_id, zone_id, area_id, x, y, z, o, level, hp_pct, power_pct, in_combat, target_guid, target_entry, quest_id, situation_type, action, raw_json, semantic_json) "
            "VALUES (" UI64FMTD ", " UI64FMTD ", " UI64FMTD ", %u, '%s', %u, " UI64FMTD ", %u, %u, %u, %f, %f, %f, %f, %u, %f, %f, %u, " UI64FMTD ", %u, %u, '%s', '%s', '%s', '%s')",
            experimentId, runId, clipId, frame.bot_guid.GetCounter(), phase.c_str(), index++, frame.timestamp_ms, frame.map_id, frame.zone_id, frame.area_id,
            frame.x, frame.y, frame.z, frame.o, uint32(frame.level), frame.hp_pct, frame.power_pct, frame.in_combat ? 1 : 0, frame.target_guid.GetCounter(),
            frame.target_entry, frame.quest_id, situation.c_str(), action.c_str(), raw.c_str(), semantic.c_str());
    }
}

std::string BotTelemetryBuffer::Escape(std::string value)
{
    CharacterDatabase.EscapeString(value);
    return value;
}
