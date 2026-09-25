#ifndef TRINITY_BOT_EXPERIENCE_LEARNING_POLICY_H
#define TRINITY_BOT_EXPERIENCE_LEARNING_POLICY_H

#include "Define.h"
#include <string>

class Player;
class Unit;
class WorldObject;

enum class BotProgressionActivity : uint8;

struct BotExperienceLearningConfig
{
    bool Enabled = true;
    uint32 MinSamplesForStrongBias = 5;
    float DangerPenaltyWeight = 18.0f;
    float ProgressionRewardWeight = 12.0f;
    float RecentFailurePenaltyWeight = 10.0f;
    float ExplorationNoveltyWeight = 4.0f;
    bool AllowGlobalMemoryFallback = true;
};

struct BotLearnedScore
{
    float Score = 0.0f;
    float Penalty = 0.0f;
    float Confidence = 0.0f;
    uint32 SampleCount = 0;
    float DangerScore = 0.0f;
    float ProgressionValue = 0.0f;
    std::string Reason = "disabled";
};

class BotExperienceLearningPolicy
{
public:
    static BotLearnedScore ScoreActivity(Player const* bot, BotProgressionActivity activity, BotExperienceLearningConfig const& config);
    static BotLearnedScore ScoreArea(Player const* bot, uint32 areaId, BotExperienceLearningConfig const& config);
    static BotLearnedScore ScorePoi(Player const* bot, uint64 poiId, float x, float y, float z, float staticScore, uint32 visitCount, uint32 successCount, uint32 failureCount, BotExperienceLearningConfig const& config);
    static BotLearnedScore ScoreQuest(Player const* bot, uint32 questId, BotExperienceLearningConfig const& config);
    static BotLearnedScore ScoreMob(Player const* bot, Unit const* target, BotExperienceLearningConfig const& config);
    static BotLearnedScore ScorePath(Player const* bot, float fromX, float fromY, float toX, float toY, BotExperienceLearningConfig const& config);
    static BotLearnedScore ScoreRecoveryMode(Player const* bot, char const* mode, float x, float y, float z, uint32 recentDeathCount, BotExperienceLearningConfig const& config);

    static std::string ToJson(BotLearnedScore const& score);
    static uint32 StableKey(std::string const& value);

    // BotWorld.ShardIsolation (default off): parallel boss shards share one
    // worldserver and one character database. While on, learned scores are
    // disabled, the bot_guid = 0 global-memory fallback is never read, and
    // unkeyed semantic outcome statistics are not written, so no shard's
    // decisions depend on another shard's run.
    static bool ShardIsolationEnabled();
    static bool LearningEnabled(BotExperienceLearningConfig const& config);
    static bool GlobalMemoryFallbackAllowed(BotExperienceLearningConfig const& config);

private:
    static BotLearnedScore Disabled();
};

#endif
