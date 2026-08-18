#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotTelemetryBuffer.h"

#include "Config.h"

#include <algorithm>
#include <cstdlib>
#include <regex>
#include <string>
#include <vector>

namespace
{
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
}

void BotWorldPopulationMgr::ApplyRuntimeConfigOverride(BotWorldExperimentConfig const& overrideConfig)
{
    Cohort().Config = overrideConfig;
}

void BotWorldPopulationMgr::ApplyRuntimeProfile(BotWorldExperimentProfile const& profile)
{
    Cohort().Config.Name = profile.Name.empty() ? Cohort().Config.Name : profile.Name;
    if (profile.HasTargetPopulation) Cohort().Config.TargetPopulation = profile.Config.TargetPopulation;
    if (profile.HasMapId) Cohort().Config.MapId = profile.Config.MapId;
    if (profile.HasZoneId) Cohort().Config.ZoneId = profile.Config.ZoneId;
    if (profile.HasCenter)
    {
        Cohort().Config.CenterX = profile.Config.CenterX;
        Cohort().Config.CenterY = profile.Config.CenterY;
        Cohort().Config.CenterZ = profile.Config.CenterZ;
    }
    if (profile.HasRadius) Cohort().Config.Radius = profile.Config.Radius;
    if (profile.HasAllowCombat) Cohort().Config.AllowCombat = profile.Config.AllowCombat;
    if (profile.HasAllowGrinding) Cohort().Config.AllowGrinding = profile.Config.AllowGrinding;
    if (profile.HasAllowQuesting) Cohort().Config.AllowQuesting = profile.Config.AllowQuesting;
    if (profile.HasAllowDungeons) Cohort().Config.AllowDungeons = profile.Config.AllowDungeons;
    if (profile.HasAllowRaids) Cohort().Config.AllowRaids = profile.Config.AllowRaids;
    if (profile.HasDungeonDifficulty) Cohort().Config.DungeonDifficulty = profile.Config.DungeonDifficulty;
    if (profile.HasRaidSize) Cohort().Config.RaidSize = profile.Config.RaidSize;
    if (profile.HasRaidDifficulty) Cohort().Config.RaidDifficulty = profile.Config.RaidDifficulty;
    if (profile.HasTrackHeroicRaidProgression) Cohort().Config.TrackHeroicRaidProgression = profile.Config.TrackHeroicRaidProgression;
    if (profile.HasEnableProgression) Cohort().Config.EnableProgression = profile.Config.EnableProgression;
    if (profile.HasRecordDecisions) Cohort().Config.RecordDecisions = profile.Config.RecordDecisions;
    if (profile.HasRecordPerception) Cohort().Config.RecordPerception = profile.Config.RecordPerception;
    if (profile.HasSmartSampling) Cohort().Config.SmartSampling = profile.Config.SmartSampling;
    if (profile.HasPoolTagFilter) Cohort().Config.PoolTagFilter = profile.Config.PoolTagFilter;
    if (profile.HasSpawnMode) Cohort().Config.SpawnMode = profile.Config.SpawnMode;
    if (profile.HasAllowConfiguredCenterFallback) Cohort().Config.AllowConfiguredCenterFallback = profile.Config.AllowConfiguredCenterFallback;
    if (profile.HasUseSavedPosition) Cohort().Config.UseSavedPosition = profile.Config.UseSavedPosition;
    if (profile.HasNearPlayerRadius) Cohort().Config.NearPlayerRadius = profile.Config.NearPlayerRadius;
    if (profile.HasDeathRecoveryMode) Cohort().Config.DeathRecoveryMode = profile.Config.DeathRecoveryMode;
    if (profile.HasAutoStartRecording) Cohort().Config.AutoStartRecording = profile.Config.AutoStartRecording;
    if (profile.HasAutoRecordingWindowMinutes) Cohort().Config.AutoRecordingWindowMinutes = profile.Config.AutoRecordingWindowMinutes;
    if (profile.HasAutoRecordingNamePrefix) Cohort().Config.AutoRecordingNamePrefix = profile.Config.AutoRecordingNamePrefix;
    if (profile.HasValidationRouteEnable) Cohort().Config.ValidationRouteEnable = profile.Config.ValidationRouteEnable;
    if (profile.HasValidationRouteManifestPath) Cohort().Config.ValidationRouteManifestPath = profile.Config.ValidationRouteManifestPath;
    if (profile.HasValidationRouteAdvanceMode) Cohort().Config.ValidationRouteAdvanceMode = profile.Config.ValidationRouteAdvanceMode;
    if (profile.HasValidationRouteScenarioId) Cohort().Config.ValidationRouteScenarioId = profile.Config.ValidationRouteScenarioId;
    if (profile.HasValidationRouteNodeId) Cohort().Config.ValidationRouteNodeId = profile.Config.ValidationRouteNodeId;
    if (profile.HasValidationRouteLabel) Cohort().Config.ValidationRouteLabel = profile.Config.ValidationRouteLabel;
    if (profile.HasValidationRouteKind) Cohort().Config.ValidationRouteKind = profile.Config.ValidationRouteKind;
    if (profile.HasValidationRouteMechanicProfile) Cohort().Config.ValidationRouteMechanicProfile = profile.Config.ValidationRouteMechanicProfile;

    if (profile.HasValidationRouteEnable && !profile.Config.ValidationRouteEnable)
    {
        Cohort().Config.ValidationRouteManifestPath.clear();
        Cohort().Config.ValidationRouteAdvanceMode = "disabled";
        Cohort().Config.ValidationRouteScenarioId.clear();
        Cohort().Config.ValidationRouteNodeId.clear();
        Cohort().Config.ValidationRouteLabel.clear();
        Cohort().Config.ValidationRouteKind.clear();
        Cohort().Config.ValidationRouteMechanicProfile.clear();
    }
    else if (profile.HasValidationRouteManifestPath && !profile.Config.ValidationRouteManifestPath.empty())
        Cohort().Config.ValidationRouteEnable = true;
}

void BotWorldPopulationMgr::LoadConfig(std::string const& name, BotWorldExperimentConfig const* overrideConfig)
{
    Cohort().Config = BotWorldExperimentConfig();
    Cohort().Config.Name = name.empty() ? Cohort().Config.Name : name;
    Cohort().ProfileManifestPath = sConfigMgr->GetStringDefault("BotWorld.ProfileManifest", Cohort().ProfileManifestPath.empty() ? "dataset/bot_runtime_profiles/profiles.json" : Cohort().ProfileManifestPath);
    Cohort().Config.TargetPopulation = sConfigMgr->GetIntDefault("BotWorld.TargetPopulation", Cohort().Config.TargetPopulation);
    Cohort().Config.MapId = sConfigMgr->GetIntDefault("BotWorld.Map", Cohort().Config.MapId);
    Cohort().Config.ZoneId = sConfigMgr->GetIntDefault("BotWorld.Zone", Cohort().Config.ZoneId);
    Cohort().Config.CenterX = sConfigMgr->GetFloatDefault("BotWorld.CenterX", Cohort().Config.CenterX);
    Cohort().Config.CenterY = sConfigMgr->GetFloatDefault("BotWorld.CenterY", Cohort().Config.CenterY);
    Cohort().Config.CenterZ = sConfigMgr->GetFloatDefault("BotWorld.CenterZ", Cohort().Config.CenterZ);
    Cohort().Config.Radius = sConfigMgr->GetFloatDefault("BotWorld.Radius", Cohort().Config.Radius);
    Cohort().Config.MinLevel = uint8(sConfigMgr->GetIntDefault("BotWorld.MinLevel", Cohort().Config.MinLevel));
    Cohort().Config.MaxLevel = uint8(sConfigMgr->GetIntDefault("BotWorld.MaxLevel", Cohort().Config.MaxLevel));
    Cohort().Config.AllowCombat = sConfigMgr->GetBoolDefault("BotWorld.AllowCombat", Cohort().Config.AllowCombat);
    Cohort().Config.AllowGrinding = sConfigMgr->GetBoolDefault("BotWorld.AllowGrinding", Cohort().Config.AllowGrinding);
    Cohort().Config.QuestFirst = sConfigMgr->GetBoolDefault("BotWorld.QuestFirst", Cohort().Config.QuestFirst);
    Cohort().Config.GrindOnlyWhenNoQuestAvailable = sConfigMgr->GetBoolDefault("BotWorld.GrindOnlyWhenNoQuestAvailable", Cohort().Config.GrindOnlyWhenNoQuestAvailable);
    Cohort().Config.EnableProgression = sConfigMgr->GetBoolDefault("BotProgression.Enable", Cohort().Config.EnableProgression);
    Cohort().Config.AllowQuesting = sConfigMgr->GetBoolDefault("BotProgression.AllowQuesting", sConfigMgr->GetBoolDefault("BotWorld.AllowQuesting", Cohort().Config.AllowQuesting));
    Cohort().Config.AllowDungeons = sConfigMgr->GetBoolDefault("BotProgression.AllowDungeons", Cohort().Config.AllowDungeons);
    Cohort().Config.AllowRaids = sConfigMgr->GetBoolDefault("BotProgression.AllowRaids", Cohort().Config.AllowRaids);
    int32 const configuredDungeonDifficulty = sConfigMgr->GetIntDefault("BotProgression.DungeonDifficulty", Cohort().Config.DungeonDifficulty);
    int32 const configuredRaidSize = sConfigMgr->GetIntDefault("BotProgression.RaidSize", Cohort().Config.RaidSize);
    int32 const configuredRaidDifficulty = sConfigMgr->GetIntDefault("BotProgression.RaidDifficulty", Cohort().Config.RaidDifficulty);
    if (configuredDungeonDifficulty < DUNGEON_DIFFICULTY_NORMAL || configuredDungeonDifficulty >= MAX_DUNGEON_DIFFICULTY)
    {
        Cohort().Config.AllowDungeons = false;
        Cohort().LastPopulationFailureReason = "invalid_dungeon_difficulty";
    }
    else
        Cohort().Config.DungeonDifficulty = uint8(configuredDungeonDifficulty);
    if (configuredRaidSize != 10 && configuredRaidSize != 25)
    {
        Cohort().Config.AllowRaids = false;
        Cohort().LastPopulationFailureReason = "invalid_raid_size";
    }
    else
        Cohort().Config.RaidSize = uint8(configuredRaidSize);
    if (configuredRaidDifficulty < RAID_DIFFICULTY_10MAN_NORMAL || configuredRaidDifficulty >= MAX_RAID_DIFFICULTY)
    {
        Cohort().Config.AllowRaids = false;
        Cohort().LastPopulationFailureReason = "invalid_raid_difficulty";
    }
    else
        Cohort().Config.RaidDifficulty = uint8(configuredRaidDifficulty);
    Cohort().Config.TrackHeroicRaidProgression = sConfigMgr->GetBoolDefault("BotProgression.TrackHeroicRaidProgression", Cohort().Config.TrackHeroicRaidProgression);
    Cohort().Config.RecordDecisions = sConfigMgr->GetBoolDefault("BotExperiment.RecordDecisions", Cohort().Config.RecordDecisions);
    Cohort().Config.RecordPerception = sConfigMgr->GetBoolDefault("BotExperiment.RecordPerception", Cohort().Config.RecordPerception);
    Cohort().Config.SmartSampling = sConfigMgr->GetBoolDefault("BotExperiment.SmartSampling", Cohort().Config.SmartSampling);
    Cohort().Config.AlwaysRecordFailures = sConfigMgr->GetBoolDefault("BotExperiment.AlwaysRecordFailures", Cohort().Config.AlwaysRecordFailures);
    Cohort().Config.AlwaysRecordInterventions = sConfigMgr->GetBoolDefault("BotExperiment.AlwaysRecordInterventions", Cohort().Config.AlwaysRecordInterventions);
    Cohort().Config.AlwaysRecordRareStates = sConfigMgr->GetBoolDefault("BotExperiment.AlwaysRecordRareStates", Cohort().Config.AlwaysRecordRareStates);
    Cohort().Config.NormalEventSampleRate = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotExperiment.NormalEventSampleRate", Cohort().Config.NormalEventSampleRate));
    Cohort().Config.NormalDecisionSampleRate = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotExperiment.NormalDecisionSampleRate", Cohort().Config.NormalDecisionSampleRate));
    Cohort().Config.MinClipImportance = std::max(0.0f, sConfigMgr->GetFloatDefault("BotExperiment.MinClipImportance", Cohort().Config.MinClipImportance));
    Cohort().Config.MinReplayImportance = std::max(0.0f, sConfigMgr->GetFloatDefault("BotExperiment.MinReplayImportance", Cohort().Config.MinReplayImportance));
    Cohort().Config.UpdateSemanticOutcomeStats = sConfigMgr->GetBoolDefault("BotSemantic.UpdateOutcomeStats", Cohort().Config.UpdateSemanticOutcomeStats);
    Cohort().Config.BrainVersion = sConfigMgr->GetStringDefault("BotExperiment.BrainVersion", Cohort().Config.BrainVersion);
    Cohort().Config.SpawnMode = sConfigMgr->GetStringDefault("BotWorld.SpawnMode", Cohort().Config.SpawnMode);
    Cohort().Config.PoolTagFilter = sConfigMgr->GetStringDefault("BotWorld.PoolTagFilter", Cohort().Config.PoolTagFilter);
    Cohort().Config.CombatCalibrationReferenceConditions = sConfigMgr->GetBoolDefault(
        "BotWorld.CombatCalibration.ReferenceConditions", Cohort().Config.CombatCalibrationReferenceConditions);
    Cohort().Config.ValidationRouteEnable = sConfigMgr->GetBoolDefault("BotWorld.ValidationRoute.Enable", Cohort().Config.ValidationRouteEnable);
    Cohort().Config.ValidationRouteManifestPath = sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.ManifestPath", Cohort().Config.ValidationRouteManifestPath);
    Cohort().Config.ValidationRouteAdvanceMode = sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.AdvanceMode", Cohort().Config.ValidationRouteAdvanceMode);
    Cohort().Config.ValidationRouteScenarioId = sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.ScenarioId", Cohort().Config.ValidationRouteScenarioId);
    Cohort().Config.ValidationRouteNodeId = sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.NodeId", Cohort().Config.ValidationRouteNodeId);
    Cohort().Config.ValidationRouteGeneration = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.Generation", Cohort().Config.ValidationRouteGeneration);
    Cohort().Config.ValidationRouteLabel = sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.Label", Cohort().Config.ValidationRouteLabel);
    Cohort().Config.ValidationRouteKind = sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.Kind", Cohort().Config.ValidationRouteKind);
    Cohort().Config.ValidationRouteMechanicProfile = sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.MechanicProfile", Cohort().Config.ValidationRouteMechanicProfile);
    Cohort().Config.ValidationRouteMapId = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.Map", Cohort().Config.ValidationRouteMapId);
    Cohort().Config.ValidationRouteX = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.X", Cohort().Config.ValidationRouteX);
    Cohort().Config.ValidationRouteY = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.Y", Cohort().Config.ValidationRouteY);
    Cohort().Config.ValidationRouteZ = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.Z", Cohort().Config.ValidationRouteZ);
    Cohort().Config.ValidationRouteO = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.O", Cohort().Config.ValidationRouteO);
    Cohort().Config.ValidationRouteTargetEntry = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.TargetEntry", Cohort().Config.ValidationRouteTargetEntry);
    Cohort().Config.ValidationRouteAlternateTargetEntries = ParseUIntList(sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.AlternateTargetEntries", ""));
    Cohort().Config.ValidationRouteAddTargetEntries = ParseUIntList(sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.AddTargetEntries", ""));
    Cohort().Config.ValidationRoutePackTargetEntries = ParseUIntList(sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.PackTargetEntries", ""));
    Cohort().Config.ValidationRouteHazardSourceEntry = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.HazardSourceEntry", Cohort().Config.ValidationRouteHazardSourceEntry);
    Cohort().Config.ValidationRouteHazardDetectionSpellId = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.HazardDetectionSpellId", Cohort().Config.ValidationRouteHazardDetectionSpellId);
    Cohort().Config.ValidationRouteHazardDamageSpellId = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.HazardDamageSpellId", Cohort().Config.ValidationRouteHazardDamageSpellId);
    Cohort().Config.ValidationRouteHazardShape = sConfigMgr->GetStringDefault("BotWorld.ValidationRoute.HazardShape", Cohort().Config.ValidationRouteHazardShape);
    Cohort().Config.ValidationRouteHazardRadiusYards = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.HazardRadiusYards", Cohort().Config.ValidationRouteHazardRadiusYards);
    Cohort().Config.ValidationRouteHazardSafetyMarginYards = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.HazardSafetyMarginYards", Cohort().Config.ValidationRouteHazardSafetyMarginYards);
    Cohort().Config.ValidationRouteMinimumDistanceSourceEntry = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.MinimumDistanceSourceEntry", Cohort().Config.ValidationRouteMinimumDistanceSourceEntry);
    Cohort().Config.ValidationRouteMinimumDistanceYards = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.MinimumDistanceYards", Cohort().Config.ValidationRouteMinimumDistanceYards);
    Cohort().Config.ValidationRouteClusterRadiusYards = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.ClusterRadiusYards", Cohort().Config.ValidationRouteClusterRadiusYards);
    Cohort().Config.ValidationRouteActivationAreaTriggerId = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.ActivationAreaTriggerId", Cohort().Config.ValidationRouteActivationAreaTriggerId);
    Cohort().Config.ValidationRouteActivationDataId = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.ActivationDataId", Cohort().Config.ValidationRouteActivationDataId);
    Cohort().Config.ValidationRouteActivationDataValue = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.ActivationDataValue", Cohort().Config.ValidationRouteActivationDataValue);
    Cohort().Config.ValidationRouteActivationSummonEntry = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.ActivationSummonEntry", Cohort().Config.ValidationRouteActivationSummonEntry);
    Cohort().Config.ValidationRouteActivationSummonX = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.ActivationSummonX", Cohort().Config.ValidationRouteActivationSummonX);
    Cohort().Config.ValidationRouteActivationSummonY = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.ActivationSummonY", Cohort().Config.ValidationRouteActivationSummonY);
    Cohort().Config.ValidationRouteActivationSummonZ = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.ActivationSummonZ", Cohort().Config.ValidationRouteActivationSummonZ);
    Cohort().Config.ValidationRouteActivationSummonO = sConfigMgr->GetFloatDefault("BotWorld.ValidationRoute.ActivationSummonO", Cohort().Config.ValidationRouteActivationSummonO);
    Cohort().Config.ValidationRouteOpenerTargetEntry = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.OpenerTargetEntry", Cohort().Config.ValidationRouteOpenerTargetEntry);
    Cohort().Config.ValidationRouteOpenerSummonEntry = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.OpenerSummonEntry", Cohort().Config.ValidationRouteOpenerSummonEntry);
    Cohort().Config.ValidationRouteActivationSpawnGroupId = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.ActivationSpawnGroupId", Cohort().Config.ValidationRouteActivationSpawnGroupId);
    Cohort().Config.ValidationRouteActivationActionEntry = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.ActivationActionEntry", Cohort().Config.ValidationRouteActivationActionEntry);
    Cohort().Config.ValidationRouteActivationActionId = sConfigMgr->GetIntDefault("BotWorld.ValidationRoute.ActivationActionId", Cohort().Config.ValidationRouteActivationActionId);
    Cohort().Config.AllowConfiguredCenterFallback = sConfigMgr->GetBoolDefault("BotWorld.AllowConfiguredCenterFallback", Cohort().Config.AllowConfiguredCenterFallback);
    Cohort().Config.UseSavedPosition = sConfigMgr->GetBoolDefault("BotWorld.UseSavedPosition", Cohort().Config.UseSavedPosition);
    Cohort().Config.NearPlayerRadius = sConfigMgr->GetFloatDefault("BotWorld.NearPlayerRadius", Cohort().Config.NearPlayerRadius);
    Cohort().Config.TrainingDummyEntries = sConfigMgr->GetStringDefault("BotWorld.TrainingDummyEntries", Cohort().Config.TrainingDummyEntries);
    Cohort().Config.DeathRecoveryMode = sConfigMgr->GetStringDefault("BotWorld.DeathRecoveryMode", sConfigMgr->GetStringDefault("BotWorld.RespawnMode", Cohort().Config.DeathRecoveryMode));
    Cohort().Config.TeleportToCenterOnDeath = sConfigMgr->GetBoolDefault("BotWorld.TeleportToCenterOnDeath", Cohort().Config.TeleportToCenterOnDeath);
    Cohort().Config.MaxDeathsBeforeFallback = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotWorld.MaxDeathsBeforeFallback", Cohort().Config.MaxDeathsBeforeFallback));
    Cohort().Config.SafePositionMemorySec = std::max<uint32>(10, sConfigMgr->GetIntDefault("BotWorld.SafePositionMemorySec", Cohort().Config.SafePositionMemorySec));
    Cohort().Config.AutoStartRecording = sConfigMgr->GetBoolDefault("BotWorld.AutoStartRecording", Cohort().Config.AutoStartRecording);
    Cohort().Config.AutoRecordingWindowMinutes = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotWorld.AutoRecordingWindowMinutes", Cohort().Config.AutoRecordingWindowMinutes));
    Cohort().Config.AutoRecordingNamePrefix = sConfigMgr->GetStringDefault("BotWorld.AutoRecordingNamePrefix", Cohort().Config.AutoRecordingNamePrefix);
    Cohort().Config.Learning.Enabled = sConfigMgr->GetBoolDefault("BotLearning.Enable", Cohort().Config.Learning.Enabled);
    Cohort().Config.Learning.MinSamplesForStrongBias = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotLearning.MinSamplesForStrongBias", Cohort().Config.Learning.MinSamplesForStrongBias));
    Cohort().Config.Learning.DangerPenaltyWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotLearning.DangerPenaltyWeight", Cohort().Config.Learning.DangerPenaltyWeight));
    Cohort().Config.Learning.ProgressionRewardWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotLearning.ProgressionRewardWeight", Cohort().Config.Learning.ProgressionRewardWeight));
    Cohort().Config.Learning.RecentFailurePenaltyWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotLearning.RecentFailurePenaltyWeight", Cohort().Config.Learning.RecentFailurePenaltyWeight));
    Cohort().Config.Learning.ExplorationNoveltyWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotLearning.ExplorationNoveltyWeight", Cohort().Config.Learning.ExplorationNoveltyWeight));
    Cohort().Config.Learning.AllowGlobalMemoryFallback = sConfigMgr->GetBoolDefault("BotLearning.AllowGlobalMemoryFallback", Cohort().Config.Learning.AllowGlobalMemoryFallback);

    Cohort().PolicyModelConfig.Enabled = sConfigMgr->GetBoolDefault("BotPolicyModel.Enable", Cohort().PolicyModelConfig.Enabled);
    Cohort().PolicyModelConfig.Mode = sConfigMgr->GetStringDefault("BotPolicyModel.Mode", Cohort().PolicyModelConfig.Mode);
    Cohort().PolicyModelConfig.Version = sConfigMgr->GetStringDefault("BotPolicyModel.Version", Cohort().PolicyModelConfig.Version);
    Cohort().PolicyModelConfig.ScoreWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotPolicyModel.ScoreWeight", Cohort().PolicyModelConfig.ScoreWeight));
    Cohort().PolicyModelConfig.FailClosed = sConfigMgr->GetBoolDefault("BotPolicyModel.FailClosed", Cohort().PolicyModelConfig.FailClosed);
    Cohort().PolicyModelConfig.MaxDecisionLatencyMs = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotPolicyModel.MaxDecisionLatencyMs", Cohort().PolicyModelConfig.MaxDecisionLatencyMs));
    Cohort().PolicyModelConfig.MinEvalRows = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotPolicyModel.MinEvalRows", Cohort().PolicyModelConfig.MinEvalRows));
    Cohort().PolicyModelConfig.MaxDeathRate = std::max(0.0f, sConfigMgr->GetFloatDefault("BotPolicyModel.MaxDeathRate", Cohort().PolicyModelConfig.MaxDeathRate));
    Cohort().PolicyModelConfig.MaxStuckRate = std::max(0.0f, sConfigMgr->GetFloatDefault("BotPolicyModel.MaxStuckRate", Cohort().PolicyModelConfig.MaxStuckRate));
    Cohort().PolicyModelConfig.MaxFailureRate = std::max(0.0f, sConfigMgr->GetFloatDefault("BotPolicyModel.MaxFailureRate", Cohort().PolicyModelConfig.MaxFailureRate));
    if (Cohort().PolicyModelConfig.Mode != "shadow" && Cohort().PolicyModelConfig.Mode != "assist" && Cohort().PolicyModelConfig.Mode != "control")
        Cohort().PolicyModelConfig.Mode = "shadow";
    ValidatePolicyModelDeployment();

    // A native `.botauto profile` selection is a one-start operator choice.
    // RuntimeProfileDirty also covers reloads and manifest invalidation, so it
    // cannot identify that intent.  Only the dedicated pending bit may bypass
    // BotWorld.RuntimeProfile resolution, and it is consumed below.
    bool const explicitProfilePending = !overrideConfig && Cohort().RuntimeProfileSelectionPending;
    if (!overrideConfig && !explicitProfilePending && !SelectConfiguredRuntimeProfile())
    {
        Cohort().Config.TargetPopulation = 0;
        return;
    }

    if (overrideConfig)
    {
        Cohort().RuntimeProfileSelectionPending = false;
        ApplyRuntimeConfigOverride(*overrideConfig);
    }
    else if (!Cohort().SelectedProfileName.empty())
    {
        EnsureRuntimeProfilesLoaded();
        auto profileItr = Cohort().RuntimeProfiles.find(Cohort().SelectedProfileName);
        if (profileItr != Cohort().RuntimeProfiles.end())
            ApplyRuntimeProfile(profileItr->second);
        else
            Cohort().SelectedProfileName.clear();
        Cohort().RuntimeProfileSelectionPending = false;
    }
    else
        Cohort().RuntimeProfileSelectionPending = false;

    if (Cohort().Config.AllowRaids)
    {
        bool const validSize = Cohort().Config.RaidSize == 10 || Cohort().Config.RaidSize == 25;
        bool const validDifficulty = Cohort().Config.RaidDifficulty < MAX_RAID_DIFFICULTY;
        bool const difficultyIs25 = (Cohort().Config.RaidDifficulty & RAID_DIFFICULTY_MASK_25MAN) != 0;
        if (!validSize || !validDifficulty || ((Cohort().Config.RaidSize == 25) != difficultyIs25))
        {
            Cohort().Config.AllowRaids = false;
            Cohort().LastPopulationFailureReason = !validSize ? "invalid_raid_size"
                : (!validDifficulty ? "invalid_raid_difficulty" : "raid_size_difficulty_mismatch");
        }
    }

    if (!Cohort().PreparedClassSpecs.empty())
    {
        Cohort().Config.PoolTagFilter = Cohort().PreparedPoolTagFilter;
        Cohort().Config.PoolClassSpecFilter = Cohort().PreparedClassSpecs;
        Cohort().Config.TargetPopulation = uint32(Cohort().PreparedClassSpecs.size());
    }

    Cohort().LearningConfig = Cohort().Config.Learning;
    Party().ValidationRouteActivationApplied = false;
    Party().ValidationRouteActivationAttempts = 0;
    Party().ValidationRouteCanonicalBossRecoveryAttempts = 0;
    Party().ValidationRouteCanonicalBossRecoveryLastMs = 0;
    Party().ValidationRouteManifest.clear();
    Party().ValidationRouteTerminalEvidence.clear();
    Party().ValidationRouteBossDeathEvidence.clear();
    Party().ValidationRouteManifestIndex = 0;
    Party().ValidationRouteGeneration = Cohort().Config.ValidationRouteGeneration;
    Party().ValidationRouteManifestAdvancePending = false;
    Party().ValidationRouteManifestAdvanceGeneration = 0;
    Party().ValidationRouteManifestComplete = false;
    Party().ValidationRouteManifestAdvanceReason.clear();
    Party().ValidationRouteManifestLoadError.clear();
    Party().ValidationRouteProgressBaselineKills = Cohort().Metrics.Kills;
    Party().ValidationRouteObservedEngagement = false;
    Party().ValidationRouteObservedDeadScriptTarget = false;
    ResetValidationRouteBossAddDensityState();
    LoadValidationRouteManifest();

    BotTelemetryBufferConfig telemetry;
    telemetry.Enabled = sConfigMgr->GetBoolDefault("BotTelemetry.Enable", telemetry.Enabled);
    telemetry.FrameIntervalMs = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotTelemetry.FrameIntervalMs", telemetry.FrameIntervalMs));
    telemetry.PreEventWindowSec = sConfigMgr->GetIntDefault("BotTelemetry.PreEventWindowSec", telemetry.PreEventWindowSec);
    telemetry.PostEventWindowSec = sConfigMgr->GetIntDefault("BotTelemetry.PostEventWindowSec", telemetry.PostEventWindowSec);
    telemetry.MaxFramesPerBot = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotTelemetry.MaxFramesPerBot", telemetry.MaxFramesPerBot));
    telemetry.MaxOpenClipsPerBot = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotTelemetry.MaxOpenClipsPerBot", telemetry.MaxOpenClipsPerBot));
    Cohort().TelemetryBuffer.Configure(telemetry);
}

