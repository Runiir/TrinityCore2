#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_CONFIG_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_CONFIG_H

#include "Define.h"
#include "Bots/BotLongTermProgressionBrain.h"

#include <cstddef>
#include <map>
#include <string>
#include <vector>

enum class BotWorldRuntimeMode
{
    ManualExperiment,
    AlwaysOnAutonomy,
    CalibrationFixture,
    ReplayFixture
};

// Boss recovery authority is part of the checked-in validation contract.  A
// native encounter owns raid reset/respawn; the bot route may not manufacture
// a boss object or state.  Phase 1 Magmaw additionally requires an exact
// native full wipe before non-combat recovery is allowed.
enum class ValidationRouteBossRecoveryPolicy : uint8
{
    NativeEncounter = 0,
    NativeFullWipeOnly = 1
};

// Validation admission is a monotonic server-owned transaction. Provisioning
// may end only by opening the player-action gate or by failing the attempt;
// an active or terminal cohort can never return to population/refill code.
enum class ValidationAdmissionPhase : uint8
{
    Provisioning = 0,
    Active = 1,
    Terminal = 2
};

struct ValidationRouteMemberAnchor
{
    uint32 RosterSlot = 0;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
};

struct BotWorldExperimentConfig
{
    std::string Name = "autonomous_zone_10";
    uint32 TargetPopulation = 10;
    uint32 MapId = 0;
    uint32 ZoneId = 12;
    uint8 MinLevel = 1;
    uint8 MaxLevel = 85;
    float CenterX = -9449.0f;
    float CenterY = 64.0f;
    float CenterZ = 56.0f;
    float Radius = 80.0f;
    bool AllowCombat = true;
    bool AllowGrinding = true;
    bool QuestFirst = false;
    bool GrindOnlyWhenNoQuestAvailable = false;
    bool AllowQuesting = true;
    bool AllowDungeons = false;
    bool AllowRaids = false;
    uint8 DungeonDifficulty = 0;
    uint8 RaidSize = 10;
    uint8 RaidDifficulty = 0;
    bool TrackHeroicRaidProgression = true;
    bool EnableProgression = true;
    bool RecordDecisions = true;
    bool RecordPerception = true;
    bool SmartSampling = true;
    bool AlwaysRecordFailures = true;
    bool AlwaysRecordInterventions = true;
    bool AlwaysRecordRareStates = true;
    uint32 NormalEventSampleRate = 20;
    uint32 NormalDecisionSampleRate = 10;
    float MinClipImportance = 0.75f;
    float MinReplayImportance = 0.90f;
    bool UpdateSemanticOutcomeStats = true;
    std::string BrainVersion = "utility_v1";
    std::string SpawnMode = "resume_or_race_start";
    std::string PoolTagFilter;
    std::vector<std::string> PoolClassSpecFilter;
    bool CombatCalibrationReferenceConditions = false;
    bool CombatCalibrationSelfProvidedBaseline = false;
    bool ValidationRouteEnable = false;
    std::string ValidationRouteManifestPath;
    std::string ValidationRouteAdvanceMode = "disabled";
    std::string ValidationRouteScenarioId;
    std::string ValidationRouteNodeId;
    uint32 ValidationRouteGeneration = 0;
    std::string ValidationRouteLabel;
    std::string ValidationRouteKind;
    std::string ValidationRouteNodeKind;
    std::string ValidationRouteDescentAction;
    std::string ValidationRouteMechanicProfile;
    ValidationRouteBossRecoveryPolicy ValidationRouteBossRecovery = ValidationRouteBossRecoveryPolicy::NativeEncounter;
    uint32 ValidationRouteMapId = 0;
    uint32 ValidationRecoveryEntranceAreaTriggerId = 0;
    uint32 ValidationRecoveryEntranceSourceMapId = 0;
    uint32 ValidationRecoveryEntranceTargetMapId = 0;
    float ValidationRouteX = 0.0f;
    float ValidationRouteY = 0.0f;
    float ValidationRouteZ = 0.0f;
    float ValidationRouteO = 0.0f;
    uint32 ValidationRouteTargetEntry = 0;
    uint32 ValidationRouteOpenerTargetEntry = 0;
    std::vector<uint32> ValidationRouteAlternateTargetEntries;
    std::vector<uint32> ValidationRouteAddTargetEntries;
    std::vector<uint32> ValidationRoutePackTargetEntries;
    std::vector<uint32> ValidationRouteScriptedEventEntries;
    std::vector<uint32> ValidationRouteScriptedEventTransitionAuraIds;
    bool ValidationRouteScriptedEventRequirePassive = false;
    uint32 ValidationRouteHazardSourceEntry = 0;
    uint32 ValidationRouteHazardDetectionSpellId = 0;
    uint32 ValidationRouteHazardDamageSpellId = 0;
    std::string ValidationRouteHazardShape;
    float ValidationRouteHazardRadiusYards = 0.0f;
    float ValidationRouteHazardSafetyMarginYards = 0.0f;
    uint32 ValidationRouteMinimumDistanceSourceEntry = 0;
    float ValidationRouteMinimumDistanceYards = 0.0f;
    std::vector<uint32> ValidationRouteSplitSourceGuids;
    std::vector<uint32> ValidationRouteSplitLaneARosterSlots;
    std::vector<uint32> ValidationRouteSplitLaneBRosterSlots;
    std::vector<uint32> ValidationRouteSplitLaneTankSlots;
    std::vector<uint32> ValidationRouteSplitHealerRosterSlots;
    std::vector<ValidationRouteMemberAnchor> ValidationRouteSplitMemberAnchors;
    std::vector<ValidationRouteMemberAnchor> ValidationRouteSplitTankCombatAnchors;
    std::vector<ValidationRouteMemberAnchor> ValidationRouteSplitTankNavigationAnchors;
    std::vector<ValidationRouteMemberAnchor> ValidationRouteSplitTankRecoveryAnchors;
    float ValidationRouteSplitMinimumSeparationYards = 0.0f;
    float ValidationRouteSplitNavigationMarginYards = 0.0f;
    float ValidationRouteSplitArrivalToleranceYards = 0.0f;
    float ValidationRouteSplitTankArrivalToleranceYards = 0.0f;
    float ValidationRouteSplitNativeMeleeStopYards = 0.0f;
    std::vector<uint32> ValidationRouteSplitSeedRosterSlots;
    float ValidationRouteSplitSeedMaxRangeYards = 0.0f;
    float ValidationRouteSplitTankThreatHeadroomMultiplier = 0.0f;
    uint32 ValidationRouteThunderclapSpellId = 0;
    uint32 ValidationRouteChargeSpellId = 0;
    float ValidationRouteChargeRangeYards = 0.0f;
    uint32 ValidationRouteChargeNativeIntervalMs = 0;
    uint32 ValidationRouteVengefulRageSpellId = 0;
    float ValidationRouteClusterRadiusYards = 0.0f;
    std::string ValidationRoutePatrolPullPolicy;
    float ValidationRoutePatrolWaitX = 0.0f;
    float ValidationRoutePatrolWaitY = 0.0f;
    float ValidationRoutePatrolWaitZ = 0.0f;
    float ValidationRoutePatrolWaitToleranceYards = 0.0f;
    float ValidationRoutePatrolAnchorToleranceYards = 0.0f;
    float ValidationRoutePatrolEngageRadiusYards = 0.0f;
    float ValidationRoutePatrolFutureGuardMarginYards = 0.0f;
    uint32 ValidationRoutePatrolPullOwnerRosterSlot = 0;
    uint32 ValidationRouteExpectedAliveCount = 0;
    uint32 ValidationRouteActivationAreaTriggerId = 0;
    uint32 ValidationRouteActivationDataId = 0;
    uint32 ValidationRouteActivationDataValue = 0;
    uint32 ValidationRouteActivationSpawnGroupId = 0;
    uint32 ValidationRouteActivationActionEntry = 0;
    int32 ValidationRouteActivationActionId = 0;
    uint32 ValidationRouteActivationSummonEntry = 0;
    float ValidationRouteActivationSummonX = 0.0f;
    float ValidationRouteActivationSummonY = 0.0f;
    float ValidationRouteActivationSummonZ = 0.0f;
    float ValidationRouteActivationSummonO = 0.0f;
    uint32 ValidationRouteOpenerSummonEntry = 0;
    float ValidationRouteOpenerSummonX = 0.0f;
    float ValidationRouteOpenerSummonY = 0.0f;
    float ValidationRouteOpenerSummonZ = 0.0f;
    float ValidationRouteOpenerSummonO = 0.0f;
    bool AllowConfiguredCenterFallback = false;
    bool UseSavedPosition = true;
    float NearPlayerRadius = 20.0f;
    std::string TrainingDummyEntries;
    std::string DeathRecoveryMode = "native_corpse_run";
    bool TeleportToCenterOnDeath = false;
    uint32 MaxDeathsBeforeFallback = 3;
    uint32 SafePositionMemorySec = 120;
    bool AutoStartRecording = false;
    uint32 AutoRecordingWindowMinutes = 30;
    std::string AutoRecordingNamePrefix = "autonomy_window";
    BotExperienceLearningConfig Learning;
};

struct BotPolicyModelConfig
{
    struct TreeNode
    {
        bool Leaf = false;
        std::string Feature;
        float Threshold = 0.0f;
        int Yes = 0;
        int No = 0;
        int Missing = 0;
        float Value = 0.0f;
    };

    struct Tree
    {
        std::vector<TreeNode> Nodes;
        std::map<int, size_t> NodeIndex;
    };

    struct Ensemble
    {
        std::string Objective;
        float BaseScore = 0.0f;
        std::vector<Tree> Trees;
    };

    bool Enabled = false;
    std::string Mode = "shadow";
    std::string Version;
    float ScoreWeight = 1.0f;
    bool FailClosed = true;
    uint32 MaxDecisionLatencyMs = 10;
    uint32 MinEvalRows = 100;
    float MaxDeathRate = 0.0f;
    float MaxStuckRate = 0.0f;
    float MaxFailureRate = 0.0f;
    bool AssistAllowed = false;
    std::string DeploymentReason = "disabled";
    std::string ArtifactPath;
    std::string ModelType;
    std::string FeatureSchemaVersion = "bot_policy_features_v1";
    bool ArtifactLoaded = false;
    std::map<std::string, float> ModelMeans;
    std::map<std::string, std::map<std::string, float>> ModelWeights;
    std::map<std::string, Ensemble> ModelTreeEnsembles;
};

struct BotWorldStatus
{
    bool Active = false;
    BotWorldRuntimeMode Mode = BotWorldRuntimeMode::ManualExperiment;
    uint64 ExperimentId = 0;
    uint64 RunId = 0;
    std::string Name;
    uint32 ActiveBots = 0;
    uint32 TargetBots = 0;
    uint32 Kills = 0;
    uint32 Deaths = 0;
    uint32 GearUpgrades = 0;
    uint32 StuckEvents = 0;
    uint32 QuestsAccepted = 0;
    uint32 QuestsCompleted = 0;
    uint32 QuestObjectiveProgress = 0;
    uint32 RaidBossKills = 0;
    uint32 HeroicRaidBossKills = 0;
    uint32 RaidTelemetryEvents = 0;
    uint32 RoleAssignments = 0;
    uint32 GroupFormations = 0;
    uint32 RaidFormations = 0;
    uint32 TargetPriorityDecisions = 0;
    uint32 InterruptSuccess = 0;
    uint32 AssignedInterruptSuccess = 0;
    uint32 HealerAssignments = 0;
    uint32 TankPositioning = 0;
    uint32 Regroups = 0;
    uint32 RecoveryEvents = 0;
    uint32 InstanceResets = 0;
    uint32 Decisions = 0;
    uint32 Failures = 0;
    uint32 DurationSeconds = 0;
};


#endif
