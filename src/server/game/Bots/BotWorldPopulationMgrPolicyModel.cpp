#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotLongTermProgressionBrain.h"

#include "Player.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace
{
float Sigmoid(float value)
{
    if (value >= 0.0f)
    {
        float z = std::exp(-value);
        return 1.0f / (1.0f + z);
    }

    float z = std::exp(value);
    return z / (1.0f + z);
}

float EvalPortableTree(BotPolicyModelConfig::Tree const& tree, std::map<std::string, float> const& features)
{
    int nodeId = 0;
    for (uint32 depth = 0; depth < 1024; ++depth)
    {
        auto indexItr = tree.NodeIndex.find(nodeId);
        if (indexItr == tree.NodeIndex.end() || indexItr->second >= tree.Nodes.size())
            return 0.0f;

        BotPolicyModelConfig::TreeNode const& node = tree.Nodes[indexItr->second];
        if (node.Leaf)
            return node.Value;

        auto featureItr = features.find(node.Feature);
        if (featureItr == features.end())
            nodeId = node.Missing;
        else if (featureItr->second < node.Threshold)
            nodeId = node.Yes;
        else
            nodeId = node.No;
    }

    return 0.0f;
}
}

std::string BotWorldPopulationMgr::BuildActivityCandidatesJson(std::vector<BotActivityScore> const& activityScores) const
{
    std::ostringstream json;
    json << "[";
    bool first = true;
    for (BotActivityScore const& score : activityScores)
    {
        if (!first)
            json << ",";
        first = false;
        json << "{\"activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(score.Activity)) << "\""
             << ",\"expected_power_gain\":" << score.ExpectedPowerGain
             << ",\"expected_xp_gain\":" << score.ExpectedXpGain
             << ",\"expected_gold_gain\":" << score.ExpectedGoldGain
             << ",\"expected_unlock_value\":" << score.ExpectedUnlockValue
             << ",\"expected_dataset_value\":" << score.ExpectedDatasetValue
             << ",\"expected_death_risk\":" << score.ExpectedDeathRisk
             << ",\"expected_wipe_risk\":" << score.ExpectedWipeRisk
             << ",\"expected_time_cost\":" << score.ExpectedTimeCost
             << ",\"expected_stuck_risk\":" << score.ExpectedStuckRisk
             << ",\"learned_score\":" << score.LearnedScore
             << ",\"learned_penalty\":" << score.LearnedPenalty
             << ",\"learned_reason\":\"" << JsonEscape(score.LearnedReason) << "\""
             << ",\"sample_count\":" << score.LearnedSampleCount
             << ",\"danger_score\":" << score.LearnedDangerScore
             << ",\"progression_value\":" << score.LearnedProgressionValue
             << ",\"confidence\":" << score.LearnedConfidence
             << ",\"score\":" << score.Score << "}";
    }
    json << "]";
    return json.str();
}

void BotWorldPopulationMgr::ApplyPolicyModelScores(std::vector<BotActivityScore>& activityScores, Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const
{
    if (!Cohort().PolicyModelConfig.Enabled || Cohort().PolicyModelConfig.Version.empty())
        return;

    auto started = std::chrono::steady_clock::now();
    std::vector<float> modelScores;
    modelScores.reserve(activityScores.size());
    for (BotActivityScore const& score : activityScores)
        modelScores.push_back(ScorePolicyModelCandidate(score, bot, power, stage));

    uint32 latencyMs = uint32(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - started).count());
    bool assist = Cohort().PolicyModelConfig.Mode == "assist" && Cohort().PolicyModelConfig.AssistAllowed;
    if (!assist || latencyMs > Cohort().PolicyModelConfig.MaxDecisionLatencyMs)
        return;

    for (size_t i = 0; i < activityScores.size() && i < modelScores.size(); ++i)
        activityScores[i].Score += Cohort().PolicyModelConfig.ScoreWeight * modelScores[i];
}

std::map<std::string, float> BotWorldPopulationMgr::BuildPolicyModelFeatureMap(BotActivityScore const& score, Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const
{
    std::map<std::string, float> features;
    features["learned_score"] = score.LearnedScore;
    features["learned_penalty"] = score.LearnedPenalty;
    features["danger_score"] = score.LearnedDangerScore;
    features["progression_value"] = score.LearnedProgressionValue;
    features["confidence"] = score.LearnedConfidence;
    features["utility_score"] = score.Score;
    features["candidate_count"] = 1.0f;
    features["map_id"] = bot ? float(bot->GetMapId()) : 0.0f;
    features["zone_id"] = bot ? float(bot->GetZoneId()) : 0.0f;
    features["bot_guid"] = bot ? float(bot->GetGUID().GetCounter()) : 0.0f;
    features["bot_level_norm"] = bot ? std::min<float>(1.0f, float(bot->getLevel()) / 85.0f) : 0.0f;
    features["role_power_norm"] = std::min<float>(1.0f, power.Total / 500.0f);
    features["progression_stage"] = float(uint8(stage));
    features["expected_power_gain"] = score.ExpectedPowerGain;
    features["expected_xp_gain"] = score.ExpectedXpGain;
    features["expected_gold_gain"] = score.ExpectedGoldGain;
    features["expected_unlock_value"] = score.ExpectedUnlockValue;
    features["expected_dataset_value"] = score.ExpectedDatasetValue;
    features["expected_death_risk"] = score.ExpectedDeathRisk;
    features["expected_wipe_risk"] = score.ExpectedWipeRisk;
    features["expected_stuck_risk"] = score.ExpectedStuckRisk;
    features["expected_time_cost"] = score.ExpectedTimeCost;
    features["json_chosen_learned_score"] = score.LearnedScore;
    features["json_chosen_learned_penalty"] = score.LearnedPenalty;
    features["json_chosen_danger_score"] = score.LearnedDangerScore;
    features["json_chosen_progression_value"] = score.LearnedProgressionValue;
    features["json_chosen_confidence"] = score.LearnedConfidence;
    features["json_chosen_activity_score"] = score.Score;
    features["json_chosen_expected_power_gain"] = score.ExpectedPowerGain;
    features["json_outcome_expected_value"] = score.Score;
    return features;
}

float BotWorldPopulationMgr::PredictPolicyModelLabel(char const* label, std::map<std::string, float> const& features) const
{
    if (!label)
        return 0.0f;

    std::string key = label;
    auto ensembleItr = Cohort().PolicyModelConfig.ModelTreeEnsembles.find(key);
    if (ensembleItr != Cohort().PolicyModelConfig.ModelTreeEnsembles.end())
    {
        BotPolicyModelConfig::Ensemble const& ensemble = ensembleItr->second;
        float value = ensemble.BaseScore;
        for (BotPolicyModelConfig::Tree const& tree : ensemble.Trees)
            value += EvalPortableTree(tree, features);
        if (ensemble.Objective == "binary:logistic")
            value = Sigmoid(value);
        return value;
    }

    float value = 0.0f;
    auto meanItr = Cohort().PolicyModelConfig.ModelMeans.find(key);
    if (meanItr != Cohort().PolicyModelConfig.ModelMeans.end())
        value = meanItr->second;

    auto weightItr = Cohort().PolicyModelConfig.ModelWeights.find(key);
    if (weightItr != Cohort().PolicyModelConfig.ModelWeights.end())
    {
        for (auto const& weight : weightItr->second)
        {
            auto featureItr = features.find(weight.first);
            if (featureItr != features.end())
                value += featureItr->second * weight.second;
        }
    }

    if (key != "expected_reward")
        value = std::max<float>(0.0f, std::min<float>(1.0f, value));
    return value;
}

float BotWorldPopulationMgr::ScorePolicyModelCandidate(BotActivityScore const& score, Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const
{
    if (!Cohort().PolicyModelConfig.Enabled || Cohort().PolicyModelConfig.Version.empty())
        return 0.0f;
    if (!Cohort().PolicyModelConfig.ArtifactLoaded)
        return 0.0f;

    std::map<std::string, float> features = BuildPolicyModelFeatureMap(score, bot, power, stage);
    float actionSuccess = PredictPolicyModelLabel("action_success", features);
    float expectedReward = PredictPolicyModelLabel("expected_reward", features);
    float deathRisk = PredictPolicyModelLabel("death_risk", features);
    float stuckRisk = PredictPolicyModelLabel("stuck_risk", features);
    float questCompletion = PredictPolicyModelLabel("quest_completion_likelihood", features);
    return expectedReward + actionSuccess + questCompletion - deathRisk - stuckRisk;
}

BotWorldPopulationMgr::PolicyModelTrace BotWorldPopulationMgr::BuildPolicyModelTrace(std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, Player const* bot, uint64 clipId, uint64 replayId) const
{
    PolicyModelTrace result;
    if (!Cohort().PolicyModelConfig.Enabled || Cohort().PolicyModelConfig.Version.empty())
        return result;
    result.Enabled = true;

    struct CandidateTrace
    {
        std::string Activity;
        float ModelScore = 0.0f;
        float UtilityScore = 0.0f;
    };

    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
    std::vector<CandidateTrace> ranked;
    ranked.reserve(activityScores.size());
    uint32 chosenRank = 0;
    float chosenModelScore = 0.0f;
    std::string chosenName = BotLongTermProgressionBrain::ToString(chosenActivity.Activity);
    for (BotActivityScore const& score : activityScores)
    {
        CandidateTrace trace;
        trace.Activity = BotLongTermProgressionBrain::ToString(score.Activity);
        trace.ModelScore = ScorePolicyModelCandidate(score, bot, power, stage);
        trace.UtilityScore = score.Score;
        ranked.push_back(trace);
        if (trace.Activity == chosenName)
            chosenModelScore = trace.ModelScore;
    }

    std::sort(ranked.begin(), ranked.end(), [](CandidateTrace const& left, CandidateTrace const& right)
    {
        return left.ModelScore > right.ModelScore;
    });

    for (uint32 i = 0; i < ranked.size(); ++i)
    {
        if (ranked[i].Activity == chosenName)
        {
            chosenRank = i + 1;
            break;
        }
    }

    std::ostringstream features;
    features << "bot_guid=" << (bot ? bot->GetGUID().GetCounter() : 0)
             << "|run_id=" << Cohort().RunId
             << "|experiment_id=" << Cohort().ExperimentId
             << "|level=" << (bot ? uint32(bot->getLevel()) : 0)
             << "|activity=" << chosenName
             << "|clip_id=" << clipId
             << "|replay_id=" << replayId
             << "|model=" << Cohort().PolicyModelConfig.Version;
    uint32 featuresHash = FeatureSchemaHash(features.str());

    std::ostringstream json;
    json << "{\"enabled\":true"
         << ",\"mode\":\"" << JsonEscape(Cohort().PolicyModelConfig.Mode) << "\""
         << ",\"assist_allowed\":" << (Cohort().PolicyModelConfig.AssistAllowed ? "true" : "false")
         << ",\"deployment_reason\":\"" << JsonEscape(Cohort().PolicyModelConfig.DeploymentReason) << "\""
         << ",\"artifact_loaded\":" << (Cohort().PolicyModelConfig.ArtifactLoaded ? "true" : "false")
         << ",\"model_type\":\"" << JsonEscape(Cohort().PolicyModelConfig.ModelType) << "\""
         << ",\"model_version\":\"" << JsonEscape(Cohort().PolicyModelConfig.Version) << "\""
         << ",\"feature_schema_version\":\"" << JsonEscape(Cohort().PolicyModelConfig.FeatureSchemaVersion) << "\""
         << ",\"model_score\":" << chosenModelScore
         << ",\"model_rank\":" << chosenRank
         << ",\"model_reason\":\"" << JsonEscape(Cohort().PolicyModelConfig.Mode == "assist" && Cohort().PolicyModelConfig.AssistAllowed ? "assist_score_blend" : "shadow_score_only") << "\""
         << ",\"model_features_hash\":" << featuresHash
         << ",\"trace\":{\"run_id\":" << Cohort().RunId
         << ",\"experiment_id\":" << Cohort().ExperimentId
         << ",\"decision_id\":null"
         << ",\"clip_id\":" << clipId
         << ",\"replay_id\":" << replayId
         << ",\"bot_guid\":" << (bot ? bot->GetGUID().GetCounter() : 0)
         << ",\"brain_version\":\"" << JsonEscape(Cohort().Config.BrainVersion) << "\""
         << ",\"model_version\":\"" << JsonEscape(Cohort().PolicyModelConfig.Version) << "\""
         << ",\"feature_schema_version\":\"" << JsonEscape(Cohort().PolicyModelConfig.FeatureSchemaVersion) << "\"}"
         << ",\"top_alternatives\":[";
    for (uint32 i = 0; i < ranked.size() && i < 3; ++i)
    {
        if (i)
            json << ",";
        json << "{\"activity\":\"" << JsonEscape(ranked[i].Activity) << "\",\"model_score\":" << ranked[i].ModelScore << ",\"utility_score\":" << ranked[i].UtilityScore << "}";
    }
    json << "]}";
    result.ModelScore = chosenModelScore;
    result.ModelRank = chosenRank;
    result.FeaturesHash = featuresHash;
    result.Json = json.str();
    return result;
}

uint32 BotWorldPopulationMgr::FeatureSchemaHash(std::string const& value)
{
    uint32 hash = 2166136261u;
    for (char c : value)
    {
        hash ^= uint8(c);
        hash *= 16777619u;
    }
    return hash;
}
