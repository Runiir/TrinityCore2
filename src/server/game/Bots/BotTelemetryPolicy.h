#ifndef TRINITY_BOT_TELEMETRY_POLICY_H
#define TRINITY_BOT_TELEMETRY_POLICY_H

#include "Define.h"
#include <string>

enum class BotTelemetryImportance
{
    Drop,
    Sample,
    Keep,
    Clip,
    Replay
};

struct BotTelemetryPolicyInput
{
    std::string eventType;
    std::string result;
    std::string situation;
    uint32 spellId = 0;
    uint32 questId = 0;
    uint32 itemId = 0;
    uint32 targetEntry = 0;
    float valueFloat = 0.0f;
    uint32 valueInt = 0;
    bool failure = false;
    bool rare = false;
    bool intervention = false;
};

struct BotTelemetryPolicyDecision
{
    BotTelemetryImportance importance = BotTelemetryImportance::Drop;
    float score = 0.0f;
    std::string reason;
    bool writeEvent = false;
    bool writeDecision = false;
    bool openClip = false;
    bool writeReplay = false;
};

struct BotTelemetryPolicyConfig
{
    bool smartSampling = true;
    bool alwaysRecordFailures = true;
    bool alwaysRecordInterventions = true;
    bool alwaysRecordRareStates = true;
    uint32 normalEventSampleRate = 20;
    uint32 normalDecisionSampleRate = 10;
    float minClipImportance = 0.75f;
    float minReplayImportance = 0.90f;
};

class BotTelemetryPolicy
{
public:
    static BotTelemetryPolicyDecision DecideEvent(BotTelemetryPolicyInput const& input, BotTelemetryPolicyConfig const& config, uint32 sequence);
    static BotTelemetryPolicyDecision DecideDecision(BotTelemetryPolicyInput const& input, BotTelemetryPolicyConfig const& config, uint32 sequence);
};

#endif
