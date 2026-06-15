#ifndef TRINITY_BOT_TELEMETRY_BUFFER_H
#define TRINITY_BOT_TELEMETRY_BUFFER_H

#include "Define.h"
#include "ObjectGuid.h"
#include <deque>
#include <map>
#include <string>
#include <vector>

class Player;

struct BotTelemetryFrame
{
    uint64 timestamp_ms = 0;
    ObjectGuid bot_guid;
    uint32 map_id = 0;
    uint32 zone_id = 0;
    uint32 area_id = 0;
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
    float o = 0.0f;
    uint8 level = 0;
    float hp_pct = 1.0f;
    float power_pct = 1.0f;
    bool in_combat = false;
    ObjectGuid target_guid;
    uint32 target_entry = 0;
    uint32 quest_id = 0;
    std::string situation_type;
    std::string action;
    std::string raw_json;
    std::string semantic_json;
};

struct BotTelemetryClip
{
    uint64 clip_id = 0;
    ObjectGuid bot_guid;
    std::string trigger_type;
    std::string reason;
    float importance_score = 0.0f;
    uint64 trigger_time_ms = 0;
    uint64 start_time_ms = 0;
    uint64 end_time_ms = 0;
    std::vector<BotTelemetryFrame> pre_frames;
    std::vector<BotTelemetryFrame> post_frames;
    std::string summary_json;
    uint32 persisted_pre_frames = 0;
    uint32 persisted_post_frames = 0;
};

struct BotTelemetryBufferConfig
{
    bool Enabled = true;
    uint32 FrameIntervalMs = 1000;
    uint32 PreEventWindowSec = 20;
    uint32 PostEventWindowSec = 10;
    uint32 MaxFramesPerBot = 120;
    uint32 MaxOpenClipsPerBot = 4;
};

class BotTelemetryBuffer
{
public:
    void Configure(BotTelemetryBufferConfig const& config);
    void Clear();
    void FlushOpenClips(uint64 experimentId, uint64 runId, std::string const& brainVersion);
    void FlushClosedClips(uint64 experimentId, uint64 runId, std::string const& brainVersion, ObjectGuid botGuid);

    bool IsEnabled() const { return _config.Enabled; }
    BotTelemetryBufferConfig const& GetConfig() const { return _config; }
    bool Observe(Player* bot, char const* situation = nullptr, char const* action = nullptr, char const* rawJson = nullptr, char const* semanticJson = nullptr, uint32 questId = 0);
    uint64 CaptureEvent(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotTelemetryFrame const& triggerFrame, char const* triggerType, float importanceScore, char const* reason, std::string const& summaryJson);
    uint64 GetActiveClipId(ObjectGuid botGuid) const;

private:
    struct BotBuffer
    {
        std::deque<BotTelemetryFrame> Frames;
        std::vector<BotTelemetryClip> OpenClips;
        uint64 LastFrameMs = 0;
    };

    BotTelemetryFrame BuildFrame(Player* bot, char const* situation, char const* action, char const* rawJson, char const* semanticJson, uint32 questId) const;
    void AppendPostFrame(BotBuffer& buffer, BotTelemetryFrame const& frame);
    void FinalizeClosedClips(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotBuffer& buffer, uint64 nowMs);
    void PersistClosedClip(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotTelemetryClip& clip);
    static uint64 InsertClipRow(uint64 experimentId, uint64 runId, std::string const& brainVersion, BotTelemetryClip const& clip);
    static void InsertFrameRows(uint64 experimentId, uint64 runId, std::string const& brainVersion, uint64 clipId, uint64 triggerTimeMs, std::vector<BotTelemetryFrame> const& frames, uint32 startIndex);
    static std::string Escape(std::string value);

    BotTelemetryBufferConfig _config;
    std::map<ObjectGuid, BotBuffer> _buffers;
};

#endif
