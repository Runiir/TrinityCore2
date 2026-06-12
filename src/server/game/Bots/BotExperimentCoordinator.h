#ifndef TRINITY_BOT_EXPERIMENT_COORDINATOR_H
#define TRINITY_BOT_EXPERIMENT_COORDINATOR_H

#include "Define.h"
#include "ObjectGuid.h"
#include <map>
#include <string>
#include <vector>

class Player;

enum class BotExperimentSegmentStatus
{
    Running,
    Success,
    Failure,
    Timeout
};

struct BotExperimentTrigger
{
    std::string EventType;
};

struct BotExperimentDefinition
{
    std::string Name;
    std::vector<BotExperimentTrigger> Triggers;
    std::vector<std::string> SuccessEvents;
    std::vector<std::string> FailureEvents;
};

struct BotExperimentSegment
{
    uint64 Id = 0;
    uint64 ParentRunId = 0;
    uint64 TriggerEventId = 0;
    uint64 ClipId = 0;
    ObjectGuid BotGuid;
    uint32 QuestId = 0;
    std::string ExperimentName;
    std::string BrainVersion;
    BotExperimentSegmentStatus Status = BotExperimentSegmentStatus::Running;
};

struct BotExperimentSegmentCounts
{
    uint32 Started = 0;
    uint32 Running = 0;
    uint32 Success = 0;
    uint32 Failure = 0;
    uint32 Timeout = 0;
};

class BotExperimentCoordinator
{
public:
    BotExperimentCoordinator();

    void Configure(uint64 parentRunId, std::string const& brainVersion);
    void Clear();
    void HandleTelemetryEvent(Player* bot, char const* eventType, char const* result, uint32 questId, uint64 triggerEventId, uint64 clipId, char const* triggerJson, char const* summaryJson);
    std::string GetCountsJson() const;
    BotExperimentSegmentCounts GetCounts() const { return _counts; }

private:
    std::string MakeKey(ObjectGuid botGuid, std::string const& experimentName, uint32 questId) const;
    BotExperimentDefinition const* GetDefinition(std::string const& experimentName) const;
    void StartSegment(Player* bot, BotExperimentDefinition const& definition, char const* eventType, uint32 questId, uint64 triggerEventId, uint64 clipId, char const* triggerJson);
    void FinishSegment(BotExperimentSegment& segment, BotExperimentSegmentStatus status, char const* result, char const* summaryJson);
    static bool Contains(std::vector<std::string> const& values, std::string const& value);
    static char const* ToString(BotExperimentSegmentStatus status);
    static std::string Escape(std::string value);

    uint64 _parentRunId = 0;
    std::string _brainVersion = "utility_v1";
    std::vector<BotExperimentDefinition> _definitions;
    std::map<std::string, BotExperimentSegment> _activeSegments;
    BotExperimentSegmentCounts _counts;
};

#endif
