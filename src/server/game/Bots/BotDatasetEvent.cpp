#include "Bots/BotDatasetEvent.h"
#include <rapidjson/document.h>
#include <cctype>
#include <iomanip>
#include <sstream>

char const* BotDatasetEvent::SchemaVersion = "bot_dataset_event_v1";
char const* BotDatasetEvent::DefaultFeatureSchemaVersion = "bot_policy_features_v1";

namespace
{
std::string BotDatasetJsonEscape(std::string const& value)
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

std::string BotDatasetTrim(std::string value)
{
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front())))
        value.erase(value.begin());
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back())))
        value.pop_back();
    return value;
}

bool BotDatasetIsJsonValue(std::string const& value)
{
    std::string trimmed = BotDatasetTrim(value);
    if (trimmed.empty())
        return false;

    char first = trimmed.front();
    if (first != '{' && first != '[' && first != '"' && first != 't' && first != 'f' && first != 'n' && first != '-' && !std::isdigit(static_cast<unsigned char>(first)))
        return false;

    rapidjson::Document doc;
    doc.Parse(trimmed.c_str());
    return !doc.HasParseError();
}

std::string BotDatasetJsonOrEmptyObject(std::string const& value)
{
    return BotDatasetIsJsonValue(value) ? value : "{}";
}

bool BotDatasetFail(std::string* error, char const* message)
{
    if (error)
        *error = message;
    return false;
}
}

char const* ToString(BotPolicySource source)
{
    switch (source)
    {
        case BotPolicySource::Rule: return "rule";
        case BotPolicySource::Heuristic: return "heuristic";
        case BotPolicySource::Exploration: return "exploration";
        case BotPolicySource::ShadowModel: return "shadow_model";
        case BotPolicySource::AssistModel: return "assist_model";
        case BotPolicySource::ControlModel: return "control_model";
        default: return "rule";
    }
}

BotPolicySource BotPolicySourceFromString(std::string const& source)
{
    if (source == "heuristic")
        return BotPolicySource::Heuristic;
    if (source == "exploration")
        return BotPolicySource::Exploration;
    if (source == "shadow_model")
        return BotPolicySource::ShadowModel;
    if (source == "assist_model")
        return BotPolicySource::AssistModel;
    if (source == "control_model")
        return BotPolicySource::ControlModel;
    return BotPolicySource::Rule;
}

bool BotDatasetEvent::Validate(std::string* error) const
{
    if (schema_version.empty())
        return BotDatasetFail(error, "missing schema_version");
    if (!run_id)
        return BotDatasetFail(error, "invalid run_id");
    if (experiment_id.empty())
        return BotDatasetFail(error, "missing experiment_id");
    if (bot_guid.IsEmpty() || !bot_guid.GetCounter())
        return BotDatasetFail(error, "invalid bot_guid");
    if (observation_json.empty() || observation_json == "{}" || !BotDatasetIsJsonValue(observation_json))
        return BotDatasetFail(error, "missing_or_malformed_observation_json");
    if (chosen_action_json.empty() || chosen_action_json == "{}" || !BotDatasetIsJsonValue(chosen_action_json))
        return BotDatasetFail(error, "missing_or_malformed_chosen_action_json");
    if (!BotDatasetIsJsonValue(semantic_json))
        return BotDatasetFail(error, "malformed_semantic_json");
    if (!BotDatasetIsJsonValue(valid_action_mask_json))
        return BotDatasetFail(error, "malformed_valid_action_mask_json");
    if (!BotDatasetIsJsonValue(outcome_json))
        return BotDatasetFail(error, "malformed_outcome_json");
    if (!BotDatasetIsJsonValue(quality_flags_json))
        return BotDatasetFail(error, "malformed_quality_flags_json");
    return true;
}

std::string BotDatasetEvent::ToJson() const
{
    std::ostringstream out;
    out << "{\"schema_version\":\"" << BotDatasetJsonEscape(schema_version) << "\""
        << ",\"feature_schema_version\":\"" << BotDatasetJsonEscape(feature_schema_version) << "\""
        << ",\"run_id\":" << run_id
        << ",\"experiment_id\":\"" << BotDatasetJsonEscape(experiment_id) << "\""
        << ",\"episode_id\":" << episode_id
        << ",\"bot_guid\":" << bot_guid.GetCounter()
        << ",\"bot_role\":\"" << BotDatasetJsonEscape(bot_role) << "\""
        << ",\"bot_level\":" << bot_level
        << ",\"policy_source\":\"" << ToString(policy_source) << "\""
        << ",\"policy_version\":\"" << BotDatasetJsonEscape(policy_version) << "\""
        << ",\"timestamp_ms\":" << timestamp_ms
        << ",\"tick_id\":" << tick_id
        << ",\"domain\":\"" << BotDatasetJsonEscape(domain) << "\""
        << ",\"situation\":\"" << BotDatasetJsonEscape(situation) << "\""
        << ",\"observation_json\":" << BotDatasetJsonOrEmptyObject(observation_json)
        << ",\"semantic_json\":" << BotDatasetJsonOrEmptyObject(semantic_json)
        << ",\"valid_action_mask_json\":" << BotDatasetJsonOrEmptyObject(valid_action_mask_json)
        << ",\"chosen_action_json\":" << BotDatasetJsonOrEmptyObject(chosen_action_json)
        << ",\"action_result\":\"" << BotDatasetJsonEscape(action_result) << "\""
        << ",\"outcome_json\":" << BotDatasetJsonOrEmptyObject(outcome_json)
        << ",\"quality_flags_json\":" << BotDatasetJsonOrEmptyObject(quality_flags_json)
        << "}";
    return out.str();
}
