#include "Bots/BotExperienceLearningPolicy.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include "DatabaseEnv.h"
#include "Player.h"
#include "Unit.h"
#include "Creature.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>

namespace
{
struct OutcomeStats
{
    bool Known = false;
    uint32 Samples = 0;
    uint32 Successes = 0;
    uint32 Failures = 0;
    uint32 Deaths = 0;
    float AvgReward = 0.0f;
    float AvgPowerDelta = 0.0f;
    float DangerScore = 0.0f;
    float ProgressionValue = 0.0f;
};

std::string Escape(std::string value)
{
    CharacterDatabase.EscapeString(value);
    return value;
}

std::string PolicyJsonEscape(std::string const& value)
{
    std::ostringstream escaped;
    for (char c : value)
    {
        switch (c)
        {
            case '\\': escaped << "\\\\"; break;
            case '"': escaped << "\\\""; break;
            case '\b': escaped << "\\b"; break;
            case '\f': escaped << "\\f"; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20)
                    escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0') << uint32(static_cast<unsigned char>(c)) << std::dec;
                else
                    escaped << c;
                break;
        }
    }
    return escaped.str();
}

float Clamp(float value, float low, float high)
{
    return std::max(low, std::min(high, value));
}

OutcomeStats ReadOutcomeStats(char const* entityType, uint32 entityKey)
{
    OutcomeStats stats;
    if (!entityType || !entityKey)
        return stats;

    std::string type = Escape(entityType);
    if (QueryResult result = CharacterDatabase.PQuery(
        "SELECT samples, successes, failures, deaths, avg_reward, avg_power_delta, danger_score, progression_value "
        "FROM bot_semantic_outcome_stats WHERE entity_type = '%s' AND entity_key = %u",
        type.c_str(), entityKey))
    {
        Field* fields = result->Fetch();
        stats.Known = true;
        stats.Samples = fields[0].GetUInt32();
        stats.Successes = fields[1].GetUInt32();
        stats.Failures = fields[2].GetUInt32();
        stats.Deaths = fields[3].GetUInt32();
        stats.AvgReward = fields[4].GetFloat();
        stats.AvgPowerDelta = fields[5].GetFloat();
        stats.DangerScore = fields[6].GetFloat();
        stats.ProgressionValue = fields[7].GetFloat();
    }
    return stats;
}

float Confidence(uint32 samples, BotExperienceLearningConfig const& config)
{
    if (!samples)
        return 0.0f;

    return Clamp(float(samples) / float(std::max<uint32>(1, config.MinSamplesForStrongBias)), 0.15f, 1.0f);
}

void ApplyOutcome(BotLearnedScore& learned, OutcomeStats const& stats, BotExperienceLearningConfig const& config, char const* reason)
{
    if (!stats.Known)
        return;

    float confidence = Confidence(stats.Samples, config);
    float successRate = stats.Samples ? float(stats.Successes) / float(stats.Samples) : 0.0f;
    float failureRate = stats.Samples ? float(stats.Failures) / float(stats.Samples) : 0.0f;
    float deathRate = stats.Samples ? float(stats.Deaths) / float(stats.Samples) : 0.0f;
    float reward = stats.ProgressionValue * config.ProgressionRewardWeight
        + stats.AvgReward * 0.5f
        + stats.AvgPowerDelta * 0.5f
        + successRate * 6.0f;
    float penalty = stats.DangerScore * config.DangerPenaltyWeight
        + failureRate * config.RecentFailurePenaltyWeight
        + deathRate * config.DangerPenaltyWeight * 1.5f
        + float(stats.Deaths) * 0.75f;

    learned.Score += (reward - penalty) * confidence;
    learned.Penalty += penalty * confidence;
    learned.Confidence = std::max(learned.Confidence, confidence);
    learned.SampleCount += stats.Samples;
    learned.DangerScore = std::max(learned.DangerScore, stats.DangerScore);
    learned.ProgressionValue = std::max(learned.ProgressionValue, stats.ProgressionValue);
    learned.Reason = reason;
}

uint32 RecentDecisionFailures(Player const* bot, char const* activity, uint32 areaId)
{
    if (!bot)
        return 0;

    std::string activitySql = Escape(activity ? activity : "");
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT COUNT(*) FROM experiment_bot_decisions "
        "WHERE bot_guid = %u AND ts >= DATE_SUB(NOW(), INTERVAL 30 MINUTE) "
        "AND is_failure = 1 AND (current_activity = '%s' OR area_id = %u OR zone_id = %u)",
        bot->GetGUID().GetCounter(), activitySql.c_str(), areaId, bot->GetZoneId());
    return result ? result->Fetch()[0].GetUInt32() : 0;
}

uint32 RecentReplayFailures(Player const* bot, char const* replayType)
{
    if (!bot)
        return 0;

    std::string typeSql = Escape(replayType ? replayType : "");
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT COUNT(*) FROM experiment_bot_replay_records "
        "WHERE bot_guid = %u AND created_at >= DATE_SUB(NOW(), INTERVAL 60 MINUTE) "
        "AND (replay_type = '%s' OR zone_id = %u) "
        "AND (failure_json LIKE '%%failed%%' OR failure_json LIKE '%%death%%' OR failure_json LIKE '%%stuck%%' OR failure_json LIKE '%%blocked%%')",
        bot->GetGUID().GetCounter(), typeSql.c_str(), bot->GetZoneId());
    return result ? result->Fetch()[0].GetUInt32() : 0;
}

uint32 RecentClipFailures(Player const* bot, uint32 areaId)
{
    if (!bot)
        return 0;

    QueryResult result = CharacterDatabase.PQuery(
        "SELECT COUNT(*) FROM experiment_bot_clips "
        "WHERE bot_guid = %u AND started_at >= DATE_SUB(NOW(), INTERVAL 60 MINUTE) "
        "AND (area_id = %u OR zone_id = %u) "
        "AND (trigger_type IN ('death', 'repeated_death', 'stuck_detected', 'death_recovery_failed') OR status = 'failed')",
        bot->GetGUID().GetCounter(), areaId, bot->GetZoneId());
    return result ? result->Fetch()[0].GetUInt32() : 0;
}

uint32 RecentSegmentFailures(Player const* bot, char const* experimentName, uint32 areaId)
{
    if (!bot)
        return 0;

    std::string experimentSql = Escape(experimentName ? experimentName : "");
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT COUNT(*) FROM experiment_bot_segments "
        "WHERE bot_guid = %u AND started_at >= DATE_SUB(NOW(), INTERVAL 60 MINUTE) "
        "AND status IN ('failure', 'timeout') AND (experiment_name = '%s' OR area_id = %u OR zone_id = %u)",
        bot->GetGUID().GetCounter(), experimentSql.c_str(), areaId, bot->GetZoneId());
    return result ? result->Fetch()[0].GetUInt32() : 0;
}

void ApplyRecentFailures(BotLearnedScore& learned, uint32 count, BotExperienceLearningConfig const& config, char const* reason)
{
    if (!count)
        return;

    float penalty = std::min<float>(30.0f, float(count) * config.RecentFailurePenaltyWeight);
    learned.Score -= penalty;
    learned.Penalty += penalty;
    learned.SampleCount += count;
    learned.Confidence = std::max(learned.Confidence, Confidence(count, config));
    learned.Reason = reason;
}

float LocalDanger(Player const* bot, float x, float y, float z, BotExperienceLearningConfig const& config)
{
    if (!bot)
        return 0.0f;

    char const* botFilter = config.AllowGlobalMemoryFallback ? "(bot_guid = %u OR bot_guid = 0)" : "bot_guid = %u";
    std::ostringstream query;
    query << "SELECT COALESCE(SUM(death_count * 2 + stuck_count + failure_count), 0) FROM bot_memory_danger_zones "
          << "WHERE " << botFilter << " AND map_id = %u "
          << "AND POW(x - %f, 2) + POW(y - %f, 2) + POW(z - %f, 2) <= POW(radius, 2)";
    QueryResult result = CharacterDatabase.PQuery(query.str().c_str(), bot->GetGUID().GetCounter(), bot->GetMapId(), x, y, z);
    return result ? result->Fetch()[0].GetFloat() : 0.0f;
}
}

BotLearnedScore BotExperienceLearningPolicy::Disabled()
{
    BotLearnedScore score;
    score.Reason = "disabled";
    return score;
}

uint32 BotExperienceLearningPolicy::StableKey(std::string const& value)
{
    uint32 hash = 2166136261u;
    for (char c : value)
    {
        hash ^= uint8(c);
        hash *= 16777619u;
    }
    return hash ? hash : 1;
}

BotLearnedScore BotExperienceLearningPolicy::ScoreActivity(Player const* bot, BotProgressionActivity activity, BotExperienceLearningConfig const& config)
{
    if (!config.Enabled || !bot)
        return Disabled();

    char const* activityName = BotLongTermProgressionBrain::ToString(activity);
    BotLearnedScore learned;
    learned.Reason = "conservative_default";
    ApplyOutcome(learned, ReadOutcomeStats("activity", StableKey(activityName)), config, "activity_outcome_stats");
    ApplyOutcome(learned, ReadOutcomeStats("area", bot->GetAreaId()), config, "area_outcome_stats");
    ApplyRecentFailures(learned, RecentDecisionFailures(bot, activityName, bot->GetAreaId()), config, "recent_decision_failures");

    char const* segment = activity == BotProgressionActivity::Questing ? "quest_execution_v1"
        : activity == BotProgressionActivity::Grinding ? "combat_survival_v1"
        : activity == BotProgressionActivity::ExperimentExploration ? "autonomous_exploration_v1"
        : "death_recovery_v1";
    ApplyRecentFailures(learned, RecentSegmentFailures(bot, segment, bot->GetAreaId()), config, "recent_segment_failures");

    if (activity == BotProgressionActivity::ExperimentExploration)
        learned.Score += config.ExplorationNoveltyWeight * (1.0f - learned.Confidence);

    return learned;
}

BotLearnedScore BotExperienceLearningPolicy::ScoreArea(Player const* bot, uint32 areaId, BotExperienceLearningConfig const& config)
{
    if (!config.Enabled || !bot || !areaId)
        return Disabled();

    BotLearnedScore learned;
    learned.Reason = "conservative_default";
    ApplyOutcome(learned, ReadOutcomeStats("area", areaId), config, "area_outcome_stats");
    ApplyRecentFailures(learned, RecentDecisionFailures(bot, nullptr, areaId), config, "recent_area_decision_failures");
    ApplyRecentFailures(learned, RecentClipFailures(bot, areaId), config, "recent_area_clip_failures");
    ApplyRecentFailures(learned, RecentReplayFailures(bot, nullptr), config, "recent_area_replay_failures");
    return learned;
}

BotLearnedScore BotExperienceLearningPolicy::ScorePoi(Player const* bot, uint64 /*poiId*/, float x, float y, float z, float staticScore, uint32 visitCount, uint32 successCount, uint32 failureCount, BotExperienceLearningConfig const& config)
{
    if (!config.Enabled || !bot)
        return Disabled();

    BotLearnedScore learned;
    learned.Reason = "poi_memory";
    uint32 samples = successCount + failureCount + visitCount;
    float confidence = Confidence(samples, config);
    float danger = LocalDanger(bot, x, y, z, config);
    float successRate = samples ? float(successCount) / float(samples) : 0.0f;
    float failureRate = samples ? float(failureCount) / float(samples) : 0.0f;
    float novelty = 1.0f / float(1 + visitCount);
    float penalty = danger * config.DangerPenaltyWeight + failureRate * config.RecentFailurePenaltyWeight + float(visitCount) * 0.8f;
    float reward = staticScore * 0.15f + successRate * 8.0f + novelty * config.ExplorationNoveltyWeight;
    learned.Score = (reward - penalty) * std::max(0.15f, confidence);
    learned.Penalty = penalty;
    learned.Confidence = confidence;
    learned.SampleCount = samples;
    learned.DangerScore = danger;
    learned.ProgressionValue = staticScore;
    return learned;
}

BotLearnedScore BotExperienceLearningPolicy::ScoreQuest(Player const* bot, uint32 questId, BotExperienceLearningConfig const& config)
{
    if (!config.Enabled || !bot || !questId)
        return Disabled();

    BotLearnedScore learned;
    learned.Reason = "conservative_default";
    ApplyOutcome(learned, ReadOutcomeStats("quest", questId), config, "quest_outcome_stats");
    ApplyOutcome(learned, ReadOutcomeStats("area", bot->GetAreaId()), config, "quest_area_outcome_stats");
    ApplyRecentFailures(learned, RecentReplayFailures(bot, "quest_failure"), config, "recent_quest_replay_failures");
    return learned;
}

BotLearnedScore BotExperienceLearningPolicy::ScoreMob(Player const* bot, Unit const* target, BotExperienceLearningConfig const& config)
{
    if (!config.Enabled || !bot || !target)
        return Disabled();

    BotLearnedScore learned;
    learned.Reason = "conservative_default";
    if (Creature const* creature = target->ToCreature())
        ApplyOutcome(learned, ReadOutcomeStats("mob", creature->GetEntry()), config, "mob_outcome_stats");
    ApplyOutcome(learned, ReadOutcomeStats("area", bot->GetAreaId()), config, "mob_area_outcome_stats");
    float danger = LocalDanger(bot, target->GetPositionX(), target->GetPositionY(), target->GetPositionZ(), config);
    if (danger > 0.0f)
    {
        float penalty = danger * config.DangerPenaltyWeight;
        learned.Score -= penalty;
        learned.Penalty += penalty;
        learned.DangerScore = std::max(learned.DangerScore, danger);
        learned.Reason = "local_danger_zone";
    }
    return learned;
}

BotLearnedScore BotExperienceLearningPolicy::ScorePath(Player const* bot, float fromX, float fromY, float toX, float toY, BotExperienceLearningConfig const& config)
{
    if (!config.Enabled || !bot)
        return Disabled();

    BotLearnedScore learned;
    learned.Reason = "path_memory";
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT COALESCE(SUM(failure_count), 0) FROM bot_memory_failed_paths "
        "WHERE bot_guid = %u AND map_id = %u AND last_failed_at >= DATE_SUB(NOW(), INTERVAL 60 MINUTE) "
        "AND POW(from_x - %f, 2) + POW(from_y - %f, 2) <= POW(18.0, 2) "
        "AND POW(to_x - %f, 2) + POW(to_y - %f, 2) <= POW(18.0, 2)",
        bot->GetGUID().GetCounter(), bot->GetMapId(), fromX, fromY, toX, toY);
    uint32 failures = result ? result->Fetch()[0].GetUInt32() : 0;
    ApplyRecentFailures(learned, failures, config, "recent_failed_path");
    return learned;
}

BotLearnedScore BotExperienceLearningPolicy::ScoreRecoveryMode(Player const* bot, char const* mode, float x, float y, float z, uint32 recentDeathCount, BotExperienceLearningConfig const& config)
{
    if (!config.Enabled || !bot || !mode)
        return Disabled();

    BotLearnedScore learned;
    learned.Reason = "recovery_mode";
    ApplyOutcome(learned, ReadOutcomeStats("recovery", StableKey(mode)), config, "recovery_outcome_stats");
    float danger = LocalDanger(bot, x, y, z, config);
    float repeatedPenalty = float(recentDeathCount) * config.RecentFailurePenaltyWeight;
    float dangerPenalty = danger * config.DangerPenaltyWeight;
    learned.Score -= repeatedPenalty + dangerPenalty;
    learned.Penalty += repeatedPenalty + dangerPenalty;
    learned.DangerScore = std::max(learned.DangerScore, danger);
    learned.SampleCount += recentDeathCount;
    learned.Confidence = std::max(learned.Confidence, Confidence(recentDeathCount, config));
    return learned;
}

std::string BotExperienceLearningPolicy::ToJson(BotLearnedScore const& score)
{
    std::ostringstream json;
    json << "{\"learned_score\":" << score.Score
         << ",\"learned_penalty\":" << score.Penalty
         << ",\"learned_reason\":\"" << PolicyJsonEscape(score.Reason) << "\""
         << ",\"sample_count\":" << score.SampleCount
         << ",\"danger_score\":" << score.DangerScore
         << ",\"progression_value\":" << score.ProgressionValue
         << ",\"confidence\":" << score.Confidence << "}";
    return json.str();
}
