#ifndef TRINITY_BOT_DATASET_EVENT_H
#define TRINITY_BOT_DATASET_EVENT_H

#include "Define.h"
#include "ObjectGuid.h"
#include <string>

enum class BotPolicySource
{
    Rule,
    Heuristic,
    Exploration,
    ShadowModel,
    AssistModel,
    ControlModel
};

struct BotDatasetEvent
{
    static char const* SchemaVersion;
    static char const* DefaultFeatureSchemaVersion;

    std::string schema_version = SchemaVersion;
    std::string feature_schema_version = DefaultFeatureSchemaVersion;
    uint64 run_id = 0;
    std::string experiment_id;
    uint64 episode_id = 0;
    ObjectGuid bot_guid;
    std::string bot_role;
    uint32 bot_level = 0;
    BotPolicySource policy_source = BotPolicySource::Rule;
    std::string policy_version;
    uint64 timestamp_ms = 0;
    uint64 tick_id = 0;
    std::string domain;
    std::string situation;
    std::string observation_json = "{}";
    std::string semantic_json = "{}";
    std::string valid_action_mask_json = "{}";
    std::string chosen_action_json = "{}";
    std::string action_result;
    std::string outcome_json = "{}";
    std::string quality_flags_json = "{}";

    bool Validate(std::string* error = nullptr) const;
    std::string ToJson() const;
};

char const* ToString(BotPolicySource source);
BotPolicySource BotPolicySourceFromString(std::string const& source);

#endif
