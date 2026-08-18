#include "Bots/BotWorldPopulationMgr.h"

#include "DatabaseEnv.h"

#include <algorithm>
#include <cmath>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace
{
std::string ReadSmallTextFile(std::string const& path, size_t maxBytes = 4 * 1024 * 1024)
{
    if (path.empty())
        return "";

    std::ifstream input(path.c_str(), std::ios::in | std::ios::binary);
    if (!input)
        return "";

    std::ostringstream data;
    data << input.rdbuf();
    std::string value = data.str();
    if (value.size() > maxBytes)
        return "";
    return value;
}


std::string ExtractJsonStringField(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
    std::smatch match;
    if (std::regex_search(json, match, pattern) && match.size() > 1)
        return match[1].str();
    return "";
}

std::string ExtractJsonObjectField(std::string const& json, std::string const& key)
{
    std::string needle = "\"" + key + "\"";
    size_t keyPos = json.find(needle);
    if (keyPos == std::string::npos)
        return "";
    size_t colon = json.find(':', keyPos + needle.size());
    if (colon == std::string::npos)
        return "";
    size_t start = json.find('{', colon);
    if (start == std::string::npos)
        return "";

    uint32 depth = 0;
    bool inString = false;
    bool escaped = false;
    for (size_t i = start; i < json.size(); ++i)
    {
        char c = json[i];
        if (inString)
        {
            if (escaped)
                escaped = false;
            else if (c == '\\')
                escaped = true;
            else if (c == '"')
                inString = false;
            continue;
        }

        if (c == '"')
            inString = true;
        else if (c == '{')
            ++depth;
        else if (c == '}')
        {
            if (!depth)
                return "";
            --depth;
            if (!depth)
                return json.substr(start, i - start + 1);
        }
    }
    return "";
}

std::string ExtractJsonArrayField(std::string const& json, std::string const& key)
{
    std::string needle = "\"" + key + "\"";
    size_t keyPos = json.find(needle);
    if (keyPos == std::string::npos)
        return "";
    size_t colon = json.find(':', keyPos + needle.size());
    if (colon == std::string::npos)
        return "";
    size_t start = json.find('[', colon);
    if (start == std::string::npos)
        return "";

    uint32 depth = 0;
    bool inString = false;
    bool escaped = false;
    for (size_t i = start; i < json.size(); ++i)
    {
        char c = json[i];
        if (inString)
        {
            if (escaped)
                escaped = false;
            else if (c == '\\')
                escaped = true;
            else if (c == '"')
                inString = false;
            continue;
        }

        if (c == '"')
            inString = true;
        else if (c == '[')
            ++depth;
        else if (c == ']')
        {
            if (!depth)
                return "";
            --depth;
            if (!depth)
                return json.substr(start, i - start + 1);
        }
    }
    return "";
}

std::vector<std::string> ExtractJsonObjectArrayItems(std::string const& arrayJson)
{
    std::vector<std::string> items;
    uint32 depth = 0;
    bool inString = false;
    bool escaped = false;
    size_t start = std::string::npos;
    for (size_t i = 0; i < arrayJson.size(); ++i)
    {
        char c = arrayJson[i];
        if (inString)
        {
            if (escaped)
                escaped = false;
            else if (c == '\\')
                escaped = true;
            else if (c == '"')
                inString = false;
            continue;
        }

        if (c == '"')
            inString = true;
        else if (c == '{')
        {
            if (!depth)
                start = i;
            ++depth;
        }
        else if (c == '}')
        {
            if (depth)
            {
                --depth;
                if (!depth && start != std::string::npos)
                    items.push_back(arrayJson.substr(start, i - start + 1));
            }
        }
    }
    return items;
}

std::set<std::string> ExtractJsonTopLevelKeys(std::string const& objectJson)
{
    std::set<std::string> keys;
    uint32 depth = 0;
    bool inString = false;
    bool escaped = false;
    size_t stringStart = std::string::npos;
    for (size_t i = 0; i < objectJson.size(); ++i)
    {
        char const c = objectJson[i];
        if (inString)
        {
            if (escaped)
                escaped = false;
            else if (c == '\\')
                escaped = true;
            else if (c == '"')
            {
                inString = false;
                if (depth == 1 && stringStart != std::string::npos)
                {
                    size_t next = i + 1;
                    while (next < objectJson.size() && std::isspace(static_cast<unsigned char>(objectJson[next])))
                        ++next;
                    if (next < objectJson.size() && objectJson[next] == ':')
                        keys.insert(objectJson.substr(stringStart, i - stringStart));
                }
            }
            continue;
        }
        if (c == '"')
        {
            inString = true;
            stringStart = i + 1;
        }
        else if (c == '{' || c == '[')
            ++depth;
        else if ((c == '}' || c == ']') && depth)
            --depth;
    }
    return keys;
}

bool ExtractJsonNumberField(std::string const& json, std::string const& key, float& value)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)");
    std::smatch match;
    if (std::regex_search(json, match, pattern) && match.size() > 1)
    {
        value = float(std::atof(match[1].str().c_str()));
        return true;
    }
    return false;
}

bool ExtractJsonIntField(std::string const& json, std::string const& key, int& value)
{
    float number = 0.0f;
    if (!ExtractJsonNumberField(json, key, number))
        return false;
    value = int(number);
    return true;
}

std::vector<uint32> ParseUIntList(std::string const& text)
{
    std::vector<uint32> values;
    std::regex pattern("([0-9]+)");
    for (std::sregex_iterator itr(text.begin(), text.end(), pattern), end; itr != end; ++itr)
    {
        uint32 value = uint32(std::strtoul((*itr)[1].str().c_str(), nullptr, 10));
        if (value && std::find(values.begin(), values.end(), value) == values.end())
            values.push_back(value);
    }
    return values;
}

std::vector<uint32> ExtractJsonUIntArrayField(std::string const& json, std::string const& key)
{
    return ParseUIntList(ExtractJsonArrayField(json, key));
}

bool ExtractJsonStrictUIntArrayField(std::string const& json, std::string const& key,
    std::vector<uint32>& values)
{
    values.clear();
    std::string const array = ExtractJsonArrayField(json, key);
    if (array.size() < 2 || array.front() != '[')
        return false;

    size_t index = 1;
    auto skipWhitespace = [&]()
    {
        while (index < array.size()
            && std::isspace(static_cast<unsigned char>(array[index])))
            ++index;
    };
    skipWhitespace();
    if (index < array.size() && array[index] == ']')
    {
        ++index;
        skipWhitespace();
        return index == array.size();
    }

    while (index < array.size())
    {
        if (!std::isdigit(static_cast<unsigned char>(array[index])))
            return false;
        uint64 value = 0;
        while (index < array.size()
            && std::isdigit(static_cast<unsigned char>(array[index])))
        {
            uint64 const digit = uint64(array[index] - '0');
            if (value > (std::numeric_limits<uint32>::max() - digit) / 10)
                return false;
            value = value * 10 + digit;
            ++index;
        }
        values.push_back(uint32(value));
        skipWhitespace();
        if (index >= array.size())
            return false;
        if (array[index] == ']')
        {
            ++index;
            skipWhitespace();
            return index == array.size();
        }
        if (array[index] != ',')
            return false;
        ++index;
        skipWhitespace();
    }
    return false;
}

bool JsonHasField(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:");
    return std::regex_search(json, pattern);
}

bool ExtractJsonBoolField(std::string const& json, std::string const& key, bool& value)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*(true|false)");
    std::smatch match;
    if (std::regex_search(json, match, pattern) && match.size() > 1)
    {
        value = match[1].str() == "true";
        return true;
    }
    return false;
}

bool JsonFieldIsString(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*\"");
    return std::regex_search(json, pattern);
}

bool JsonFieldIsNumber(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?");
    return std::regex_search(json, pattern);
}

bool JsonFieldIsBool(std::string const& json, std::string const& key)
{
    std::regex pattern("\"" + key + "\"\\s*:\\s*(true|false)");
    return std::regex_search(json, pattern);
}

std::vector<std::string> ExtractJsonLineObjects(std::string const& text)
{
    std::vector<std::string> items;
    std::istringstream input(text);
    std::string line;
    while (std::getline(input, line))
    {
        size_t first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos || line[first] != '{')
            continue;
        items.push_back(line.substr(first));
    }
    return items;
}

std::map<std::string, float> ExtractJsonNumberMap(std::string const& objectJson)
{
    std::map<std::string, float> values;
    std::regex pattern("\"([^\"]+)\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)");
    for (std::sregex_iterator itr(objectJson.begin(), objectJson.end(), pattern), end; itr != end; ++itr)
        values[(*itr)[1].str()] = float(std::atof((*itr)[2].str().c_str()));
    return values;
}

bool ParsePortableTree(std::string const& treeJson, BotPolicyModelConfig::Tree& tree)
{
    std::string nodesArray = ExtractJsonArrayField(treeJson, "nodes");
    if (nodesArray.empty())
        return false;

    for (std::string const& nodeJson : ExtractJsonObjectArrayItems(nodesArray))
    {
        BotPolicyModelConfig::TreeNode node;
        int id = 0;
        if (!ExtractJsonIntField(nodeJson, "id", id))
            return false;

        float leaf = 0.0f;
        if (ExtractJsonNumberField(nodeJson, "leaf", leaf))
        {
            node.Leaf = true;
            node.Value = leaf;
        }
        else
        {
            node.Feature = ExtractJsonStringField(nodeJson, "feature");
            if (node.Feature.empty())
                return false;
            ExtractJsonNumberField(nodeJson, "threshold", node.Threshold);
            ExtractJsonIntField(nodeJson, "yes", node.Yes);
            ExtractJsonIntField(nodeJson, "no", node.No);
            ExtractJsonIntField(nodeJson, "missing", node.Missing);
        }

        tree.NodeIndex[id] = tree.Nodes.size();
        tree.Nodes.push_back(std::move(node));
    }

    return !tree.Nodes.empty();
}

std::map<std::string, BotPolicyModelConfig::Ensemble> ParsePortableTreeEnsembles(std::string const& json)
{
    std::map<std::string, BotPolicyModelConfig::Ensemble> ensembles;
    std::string all = ExtractJsonObjectField(json, "tree_ensembles");
    if (all.empty())
        return ensembles;

    for (char const* label : { "action_success", "expected_reward", "death_risk", "stuck_risk", "quest_completion_likelihood" })
    {
        std::string labelObject = ExtractJsonObjectField(all, label);
        if (labelObject.empty())
            continue;

        BotPolicyModelConfig::Ensemble ensemble;
        ensemble.Objective = ExtractJsonStringField(labelObject, "objective");
        ExtractJsonNumberField(labelObject, "base_score", ensemble.BaseScore);
        std::string treesArray = ExtractJsonArrayField(labelObject, "trees");
        for (std::string const& treeJson : ExtractJsonObjectArrayItems(treesArray))
        {
            BotPolicyModelConfig::Tree tree;
            if (ParsePortableTree(treeJson, tree))
                ensemble.Trees.push_back(std::move(tree));
        }

        if (!ensemble.Trees.empty())
            ensembles[label] = std::move(ensemble);
    }

    return ensembles;
}

}

void BotWorldPopulationMgr::ValidatePolicyModelDeployment()
{
    Cohort().PolicyModelConfig.AssistAllowed = false;
    Cohort().PolicyModelConfig.DeploymentReason = "disabled";
    Cohort().PolicyModelConfig.ArtifactLoaded = false;
    Cohort().PolicyModelConfig.ArtifactPath.clear();
    Cohort().PolicyModelConfig.ModelType.clear();
    Cohort().PolicyModelConfig.ModelMeans.clear();
    Cohort().PolicyModelConfig.ModelWeights.clear();
    Cohort().PolicyModelConfig.ModelTreeEnsembles.clear();
    if (!Cohort().PolicyModelConfig.Enabled)
        return;

    if (Cohort().PolicyModelConfig.Version.empty())
    {
        Cohort().PolicyModelConfig.DeploymentReason = "missing_model_version";
        if (Cohort().PolicyModelConfig.FailClosed)
            Cohort().PolicyModelConfig.Mode = "shadow";
        return;
    }

    std::string version = Cohort().PolicyModelConfig.Version;
    CharacterDatabase.EscapeString(version);
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT accepted, artifact_path, model_type, "
        "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(metrics_json, '$.eval_rows')) AS UNSIGNED), 0), "
        "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(metrics_json, '$.death_rate')) AS DECIMAL(10,6)), 1), "
        "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(metrics_json, '$.stuck_rate')) AS DECIMAL(10,6)), 1), "
        "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(metrics_json, '$.failure_rate')) AS DECIMAL(10,6)), 1) "
        "FROM bot_policy_models WHERE model_version = '%s' ORDER BY created_at DESC LIMIT 1",
        version.c_str());

    if (!result)
    {
        Cohort().PolicyModelConfig.DeploymentReason = "model_not_registered";
        if (Cohort().PolicyModelConfig.FailClosed)
            Cohort().PolicyModelConfig.Mode = "shadow";
        return;
    }

    Field* fields = result->Fetch();
    bool accepted = fields[0].GetUInt8() != 0;
    Cohort().PolicyModelConfig.ArtifactPath = fields[1].GetString();
    Cohort().PolicyModelConfig.ModelType = fields[2].GetString();
    uint32 evalRows = fields[3].GetUInt32();
    float deathRate = fields[4].GetFloat();
    float stuckRate = fields[5].GetFloat();
    float failureRate = fields[6].GetFloat();

    if (!LoadPolicyModelArtifact(Cohort().PolicyModelConfig.ArtifactPath))
        Cohort().PolicyModelConfig.DeploymentReason = "artifact_load_failed";
    else if (Cohort().PolicyModelConfig.Mode == "shadow")
    {
        Cohort().PolicyModelConfig.DeploymentReason = "shadow_mode";
        return;
    }
    else if (Cohort().PolicyModelConfig.Mode == "control")
        Cohort().PolicyModelConfig.DeploymentReason = "control_mode_disabled";
    else if (!accepted)
        Cohort().PolicyModelConfig.DeploymentReason = "model_not_accepted";
    else if (evalRows < Cohort().PolicyModelConfig.MinEvalRows)
        Cohort().PolicyModelConfig.DeploymentReason = "insufficient_eval_rows";
    else if (deathRate > Cohort().PolicyModelConfig.MaxDeathRate)
        Cohort().PolicyModelConfig.DeploymentReason = "death_rate_regression";
    else if (stuckRate > Cohort().PolicyModelConfig.MaxStuckRate)
        Cohort().PolicyModelConfig.DeploymentReason = "stuck_rate_regression";
    else if (failureRate > Cohort().PolicyModelConfig.MaxFailureRate)
        Cohort().PolicyModelConfig.DeploymentReason = "failure_rate_regression";
    else
    {
        Cohort().PolicyModelConfig.AssistAllowed = true;
        Cohort().PolicyModelConfig.DeploymentReason = "assist_allowed";
        return;
    }

    if (Cohort().PolicyModelConfig.FailClosed)
        Cohort().PolicyModelConfig.Mode = "shadow";
}

bool BotWorldPopulationMgr::LoadPolicyModelArtifact(std::string const& artifactPath)
{
    std::string json = ReadSmallTextFile(artifactPath);
    if (json.empty())
        return false;

    std::string version = ExtractJsonStringField(json, "model_version");
    if (!version.empty() && version != Cohort().PolicyModelConfig.Version)
        return false;

    std::string schema = ExtractJsonStringField(json, "feature_schema_version");
    if (!schema.empty())
        Cohort().PolicyModelConfig.FeatureSchemaVersion = schema;

    std::string artifactFormat = ExtractJsonStringField(json, "artifact_format");
    std::map<std::string, BotPolicyModelConfig::Ensemble> treeEnsembles = ParsePortableTreeEnsembles(json);
    std::string fallbackObject = ExtractJsonObjectField(json, "fallback");
    std::string meansObject = ExtractJsonObjectField(json, "means");
    std::string weightsObject = ExtractJsonObjectField(json, "weights");
    if (!fallbackObject.empty())
    {
        if (meansObject.empty())
            meansObject = ExtractJsonObjectField(fallbackObject, "means");
        if (weightsObject.empty())
            weightsObject = ExtractJsonObjectField(fallbackObject, "weights");
    }
    if (treeEnsembles.empty() && (meansObject.empty() || weightsObject.empty()))
        return false;

    std::map<std::string, float> means = ExtractJsonNumberMap(meansObject);
    if (treeEnsembles.empty() && means.empty())
        return false;

    std::map<std::string, std::map<std::string, float>> weights;
    for (char const* label : { "action_success", "expected_reward", "death_risk", "stuck_risk", "quest_completion_likelihood" })
    {
        std::string labelObject = ExtractJsonObjectField(weightsObject, label);
        if (!labelObject.empty())
            weights[label] = ExtractJsonNumberMap(labelObject);
    }

    if (treeEnsembles.empty() && weights.empty())
        return false;

    Cohort().PolicyModelConfig.ModelMeans = std::move(means);
    Cohort().PolicyModelConfig.ModelWeights = std::move(weights);
    Cohort().PolicyModelConfig.ModelTreeEnsembles = std::move(treeEnsembles);
    if (!artifactFormat.empty())
        Cohort().PolicyModelConfig.ModelType = artifactFormat;
    Cohort().PolicyModelConfig.ArtifactLoaded = true;
    return true;
}
