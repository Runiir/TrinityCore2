#include "Bots/BotExperimentCoordinator.h"
#include "DatabaseEnv.h"
#include "Player.h"

#include <algorithm>
#include <sstream>

namespace
{
uint64 ReadSegmentLastInsertId()
{
    if (QueryResult result = CharacterDatabase.Query("SELECT LAST_INSERT_ID()"))
        return result->Fetch()[0].GetUInt64();

    return 0;
}
}

BotExperimentCoordinator::BotExperimentCoordinator()
{
    _definitions =
    {
        { "autonomous_exploration_v1", { { "bot_enters_new_area" }, { "bot_discovers_new_poi" } }, { "reaches_next_poi", "sees_quest_giver", "survives_duration" }, { "stuck_detected", "death" } },
        { "quest_discovery_v1", { { "quest_seen" } }, { "quest_accepted" }, { "quest_rejected", "quest_unusable", "timeout" } },
        { "quest_execution_v1", { { "quest_accepted" } }, { "quest_completed" }, { "objective_failed", "timeout" } },
        { "combat_survival_v1", { { "combat_started" } }, { "mob_killed", "boss_killed" }, { "death", "flee", "stuck" } },
        { "death_recovery_v1", { { "death" } }, { "resurrected", "safe_after_30s" }, { "repeated_death", "death_recovery_failed", "teleport_fallback_required", "teleport_fallback_used" } },
        { "stuck_recovery_v1", { { "stuck_detected" } }, { "movement_resumed" }, { "stuck_repeated", "teleport_fallback_required" } },
    };
}

void BotExperimentCoordinator::Configure(uint64 parentRunId, std::string const& brainVersion)
{
    _parentRunId = parentRunId;
    _brainVersion = brainVersion;
}

void BotExperimentCoordinator::Clear()
{
    _activeSegments.clear();
    _counts = BotExperimentSegmentCounts();
}

void BotExperimentCoordinator::HandleTelemetryEvent(Player* bot, char const* eventType, char const* result, uint32 questId, uint64 triggerEventId, uint64 clipId, char const* triggerJson, char const* summaryJson)
{
    if (!bot || !eventType || !*eventType)
        return;

    std::string event = eventType;
    for (auto itr = _activeSegments.begin(); itr != _activeSegments.end();)
    {
        BotExperimentDefinition const* definition = GetDefinition(itr->second.ExperimentName);
        if (!definition)
        {
            itr = _activeSegments.erase(itr);
            continue;
        }

        if (itr->second.BotGuid == bot->GetGUID()
            && (!itr->second.QuestId || !questId || itr->second.QuestId == questId)
            && Contains(definition->SuccessEvents, event))
        {
            FinishSegment(itr->second, BotExperimentSegmentStatus::Success, result ? result : eventType, summaryJson);
            itr = _activeSegments.erase(itr);
            continue;
        }

        if (itr->second.BotGuid == bot->GetGUID()
            && (!itr->second.QuestId || !questId || itr->second.QuestId == questId)
            && Contains(definition->FailureEvents, event))
        {
            FinishSegment(itr->second, event == "timeout" ? BotExperimentSegmentStatus::Timeout : BotExperimentSegmentStatus::Failure, result ? result : eventType, summaryJson);
            itr = _activeSegments.erase(itr);
            continue;
        }

        ++itr;
    }

    for (BotExperimentDefinition const& definition : _definitions)
        for (BotExperimentTrigger const& trigger : definition.Triggers)
            if (trigger.EventType == event)
                StartSegment(bot, definition, eventType, questId, triggerEventId, clipId, triggerJson);
}

std::string BotExperimentCoordinator::GetCountsJson() const
{
    std::ostringstream json;
    json << "{\"started\":" << _counts.Started
         << ",\"running\":" << uint32(_activeSegments.size())
         << ",\"success\":" << _counts.Success
         << ",\"failure\":" << _counts.Failure
         << ",\"timeout\":" << _counts.Timeout << "}";
    return json.str();
}

std::string BotExperimentCoordinator::MakeKey(ObjectGuid botGuid, std::string const& experimentName, uint32 questId) const
{
    std::ostringstream key;
    key << botGuid.GetCounter() << ":" << experimentName << ":" << questId;
    return key.str();
}

BotExperimentDefinition const* BotExperimentCoordinator::GetDefinition(std::string const& experimentName) const
{
    for (BotExperimentDefinition const& definition : _definitions)
        if (definition.Name == experimentName)
            return &definition;

    return nullptr;
}

void BotExperimentCoordinator::StartSegment(Player* bot, BotExperimentDefinition const& definition, char const* eventType, uint32 questId, uint64 triggerEventId, uint64 clipId, char const* triggerJson)
{
    if (!bot)
        return;

    std::string key = MakeKey(bot->GetGUID(), definition.Name, questId);
    if (_activeSegments.find(key) != _activeSegments.end())
        return;

    std::string parentRunSql = _parentRunId ? std::to_string(_parentRunId) : "NULL";
    std::string triggerEventSql = triggerEventId ? std::to_string(triggerEventId) : "NULL";
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";
    std::string name = Escape(definition.Name);
    std::string brain = Escape(_brainVersion);
    std::string initialResult = Escape(eventType ? eventType : "");
    std::string trigger = Escape(triggerJson && *triggerJson ? triggerJson : "{}");

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_segments (parent_run_id, experiment_name, trigger_event_id, clip_id, bot_guid, brain_version, status, result, started_at, map_id, zone_id, area_id, x, y, z, trigger_json, summary_json) "
        "VALUES (%s, '%s', %s, %s, %u, '%s', 'running', '%s', NOW(), %u, %u, %u, %f, %f, %f, '%s', '{}')",
        parentRunSql.c_str(), name.c_str(), triggerEventSql.c_str(), clipSql.c_str(), bot->GetGUID().GetCounter(), brain.c_str(), initialResult.c_str(),
        bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), trigger.c_str());

    BotExperimentSegment segment;
    segment.Id = ReadSegmentLastInsertId();
    segment.ParentRunId = _parentRunId;
    segment.TriggerEventId = triggerEventId;
    segment.ClipId = clipId;
    segment.BotGuid = bot->GetGUID();
    segment.QuestId = questId;
    segment.ExperimentName = definition.Name;
    segment.BrainVersion = _brainVersion;
    _activeSegments[key] = segment;
    ++_counts.Started;
}

void BotExperimentCoordinator::FinishSegment(BotExperimentSegment& segment, BotExperimentSegmentStatus status, char const* result, char const* summaryJson)
{
    segment.Status = status;
    if (status == BotExperimentSegmentStatus::Success)
        ++_counts.Success;
    else if (status == BotExperimentSegmentStatus::Failure)
        ++_counts.Failure;
    else if (status == BotExperimentSegmentStatus::Timeout)
        ++_counts.Timeout;

    if (!segment.Id)
        return;

    std::string resultText = Escape(result && *result ? result : ToString(status));
    std::string summary = Escape(summaryJson && *summaryJson ? summaryJson : "{}");
    CharacterDatabase.DirectPExecute("UPDATE experiment_bot_segments SET status = '%s', result = '%s', ended_at = NOW(), summary_json = '%s' WHERE id = " UI64FMTD,
        ToString(status), resultText.c_str(), summary.c_str(), segment.Id);
}

bool BotExperimentCoordinator::Contains(std::vector<std::string> const& values, std::string const& value)
{
    return std::find(values.begin(), values.end(), value) != values.end();
}

char const* BotExperimentCoordinator::ToString(BotExperimentSegmentStatus status)
{
    switch (status)
    {
        case BotExperimentSegmentStatus::Running: return "running";
        case BotExperimentSegmentStatus::Success: return "success";
        case BotExperimentSegmentStatus::Failure: return "failure";
        case BotExperimentSegmentStatus::Timeout: return "timeout";
    }

    return "unknown";
}

std::string BotExperimentCoordinator::Escape(std::string value)
{
    CharacterDatabase.EscapeString(value);
    return value;
}
