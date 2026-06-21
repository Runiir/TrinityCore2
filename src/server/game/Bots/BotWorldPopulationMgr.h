#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_H

#include "ObjectGuid.h"
#include "Bots/BotExperimentCoordinator.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotTelemetryBuffer.h"
#include "Bots/BotTelemetryPolicy.h"
#include <deque>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

class Player;
class Quest;
class Unit;
class WorldObject;

enum class BotWorldRuntimeMode
{
    ManualExperiment,
    AlwaysOnAutonomy
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
    bool ValidationRouteEnable = false;
    std::string ValidationRouteManifestPath;
    std::string ValidationRouteAdvanceMode = "disabled";
    std::string ValidationRouteScenarioId;
    std::string ValidationRouteNodeId;
    std::string ValidationRouteLabel;
    std::string ValidationRouteKind;
    std::string ValidationRouteMechanicProfile;
    uint32 ValidationRouteMapId = 0;
    float ValidationRouteX = 0.0f;
    float ValidationRouteY = 0.0f;
    float ValidationRouteZ = 0.0f;
    float ValidationRouteO = 0.0f;
    uint32 ValidationRouteTargetEntry = 0;
    uint32 ValidationRouteOpenerTargetEntry = 0;
    std::vector<uint32> ValidationRouteAlternateTargetEntries;
    std::vector<uint32> ValidationRoutePackTargetEntries;
    float ValidationRouteClusterRadiusYards = 0.0f;
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
    std::string DeathRecoveryMode = "safe_local";
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

class BotWorldPopulationMgr
{
public:
    static BotWorldPopulationMgr* instance();

    void Update(uint32 diff);
    bool Start(std::string const& experimentName, BotWorldExperimentConfig const* overrideConfig = nullptr);
    void Stop();
    bool StartAutonomy(BotWorldExperimentConfig const* overrideConfig = nullptr);
    void StopAutonomy();
    void Shutdown();
    bool SpawnAutonomyBots(uint32 count);
    std::string GetRuntimeProfilesJson();
    std::string SelectRuntimeProfile(std::string const& name);
    std::string ClearRuntimeProfile();
    std::string ReloadRuntimeProfiles();
    std::string PrepareValidationProfile(std::string const& name);
    BotWorldStatus GetStatus() const;
    std::string GetStatusJson() const;
    std::string GetSummaryJson() const;
    std::string GetBotDebugJson(std::string const& selector) const;
    std::string GetBotDiagnosisJson(std::string const& selector);
    std::string GetBotTraceJson(std::string const& selector, uint32 limit) const;
    bool IsActive() const { return _active; }
    std::string Replay(std::string const& replayType, std::string const& selector, std::string const& brainVersion = "");
    std::string CompareBrains(uint64 replayId, std::string const& firstBrainVersion, std::string const& secondBrainVersion);

    enum class QuestObjectiveType
    {
        Kill,
        CollectItem,
        InteractGameObject,
        CastSpellOnTarget,
        UseAbilityOnDummy,
        UseItemOnTarget
    };

    enum class QuestClassification
    {
        ObjectiveQuest,
        ChainQuest,
        UnsupportedQuest
    };

private:
    struct BotWorldExperimentProfile
    {
        std::string Name;
        std::string Description;
        BotWorldExperimentConfig Config;
        bool HasTargetPopulation = false;
        bool HasMapId = false;
        bool HasZoneId = false;
        bool HasCenter = false;
        bool HasRadius = false;
        bool HasAllowCombat = false;
        bool HasAllowGrinding = false;
        bool HasAllowQuesting = false;
        bool HasAllowDungeons = false;
        bool HasAllowRaids = false;
        bool HasTrackHeroicRaidProgression = false;
        bool HasEnableProgression = false;
        bool HasRecordDecisions = false;
        bool HasRecordPerception = false;
        bool HasSmartSampling = false;
        bool HasPoolTagFilter = false;
        bool HasSpawnMode = false;
        bool HasAllowConfiguredCenterFallback = false;
        bool HasUseSavedPosition = false;
        bool HasNearPlayerRadius = false;
        bool HasDeathRecoveryMode = false;
        bool HasAutoStartRecording = false;
        bool HasAutoRecordingWindowMinutes = false;
        bool HasAutoRecordingNamePrefix = false;
        bool HasValidationRouteEnable = false;
        bool HasValidationRouteManifestPath = false;
        bool HasValidationRouteAdvanceMode = false;
        bool HasValidationRouteScenarioId = false;
        bool HasValidationRouteNodeId = false;
        bool HasValidationRouteLabel = false;
        bool HasValidationRouteKind = false;
        bool HasValidationRouteMechanicProfile = false;
    };

    struct ValidationRouteManifestNode
    {
        std::string ScenarioId;
        std::string NodeId;
        std::string Label;
        std::string Kind;
        std::string MechanicProfile;
        uint32 MapId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float O = 0.0f;
        uint32 TargetEntry = 0;
        uint32 OpenerTargetEntry = 0;
        std::vector<uint32> AlternateTargetEntries;
        std::vector<uint32> PackTargetEntries;
        float ClusterRadiusYards = 0.0f;
        uint32 ActivationDataId = 0;
        uint32 ActivationDataValue = 0;
        uint32 ActivationSpawnGroupId = 0;
        uint32 ActivationActionEntry = 0;
        int32 ActivationActionId = 0;
        uint32 ActivationSummonEntry = 0;
        float ActivationSummonX = 0.0f;
        float ActivationSummonY = 0.0f;
        float ActivationSummonZ = 0.0f;
        float ActivationSummonO = 0.0f;
        uint32 OpenerSummonEntry = 0;
        float OpenerSummonX = 0.0f;
        float OpenerSummonY = 0.0f;
        float OpenerSummonZ = 0.0f;
        float OpenerSummonO = 0.0f;
        uint32 ExpectedBotCount = 0;
    };

    struct WorldBotState
    {
        struct SafePosition
        {
            uint32 MapId = 0;
            uint32 ZoneId = 0;
            uint32 AreaId = 0;
            float X = 0.0f;
            float Y = 0.0f;
            float Z = 0.0f;
            float O = 0.0f;
            float HpPct = 1.0f;
            uint64 SeenMs = 0;
        };

        ObjectGuid Guid;
        uint32 DecisionTimer = 0;
        uint32 StuckTimer = 0;
        uint32 DeadTimer = 0;
        uint32 SafePositionTimer = 0;
        uint32 PoiScanTimer = 0;
        uint32 RestTimer = 0;
        uint32 Sequence = 0;
        uint64 ActivityId = 0;
        float ActivityStartPower = 0.0f;
        uint64 ActivityStartGold = 0;
        uint32 ActivityStartDeaths = 0;
        uint32 QuestStartTime = 0;
        uint32 QuestStartDeaths = 0;
        uint32 LastQuestId = 0;
        uint32 LastQuestCompletedCount = 0;
        uint32 LastQuestObjectiveProgress = 0;
        uint64 SpawnedMs = 0;
        std::string SpawnSource = "unknown";
        bool RaceStartFallbackUsed = false;
        uint32 SpawnMapId = 0;
        float SpawnX = 0.0f;
        float SpawnY = 0.0f;
        float SpawnZ = 0.0f;
        float SpawnO = 0.0f;
        std::string CurrentQuestState = "idle";
        std::string CurrentObjectiveType = "none";
        bool CurrentTargetIsTrainingDummy = false;
        bool CurrentDummyAllowedByQuest = false;
        uint32 RequiredSpellId = 0;
        uint32 RequiredItemId = 0;
        uint32 RequiredTargetEntry = 0;
        uint32 LastQuestProgressBefore = 0;
        uint32 LastQuestProgressAfter = 0;
        std::string LastRejectedTargetReason;
        uint32 RaidBossKills = 0;
        uint32 HeroicRaidBossKills = 0;
        uint32 RaidAttempts = 0;
        uint32 RaidWipes = 0;
        uint32 EventSequence = 0;
        std::string ActivityType = "experiment_exploration";
        std::string ProgressionStage = "leveling";
        float LastX = 0.0f;
        float LastY = 0.0f;
        float LastZ = 0.0f;
        float ActivePathFromX = 0.0f;
        float ActivePathFromY = 0.0f;
        float ActivePathFromZ = 0.0f;
        float ActivePathToX = 0.0f;
        float ActivePathToY = 0.0f;
        float ActivePathToZ = 0.0f;
        bool ActivePathValid = false;
        std::string LastPathRejectReason;
        uint32 LastDeathMapId = 0;
        uint32 LastDeathAreaId = 0;
        float LastDeathX = 0.0f;
        float LastDeathY = 0.0f;
        uint32 RecentDeathCount = 0;
        ObjectGuid TargetGuid;
        bool WasInCombat = false;
        uint32 ValidationRouteUnresolvedFocusHoldCount = 0;
        ObjectGuid ValidationRouteCombatProgressTargetGuid;
        float ValidationRouteCombatBestHealthPct = 1.0f;
        uint32 ValidationRouteCombatNoProgressCount = 0;
        uint32 ValidationRouteBossSlowProgressCount = 0;
        ObjectGuid ValidationRoutePackProgressTargetGuid;
        float ValidationRoutePackBestHealthPct = 1.0f;
        uint32 ValidationRoutePackNoProgressCount = 0;
        bool ValidationRouteActivationApplied = false;
        uint32 ValidationRouteActivationAttempts = 0;
        uint32 ValidationRouteTargetSearchMissCount = 0;
        bool ValidationRouteTerminalState = false;
        uint64 ValidationRouteTerminalAtMs = 0;
        std::string ValidationRouteTerminalReason;
        bool ValidationCohortLocked = false;
        bool ValidationCohortViolation = false;
        std::string ValidationCohortViolationReason;
        ObjectGuid ValidationCohortLeaderGuid;
        ObjectGuid ValidationCohortGroupGuid;
        uint32 ValidationCohortMapId = 0;
        uint32 ValidationCohortInstanceId = 0;
        uint32 ValidationCohortPhaseMask = 0;
        bool ValidationGroupFormationRecorded = false;
        bool ValidationRaidFormationRecorded = false;
        bool ValidationRoleAssignmentRecorded = false;
        bool ValidationRouteAnchorOverrideValid = false;
        uint64 ValidationRouteAnchorOverrideUntilMs = 0;
        float ValidationRouteAnchorOverrideX = 0.0f;
        float ValidationRouteAnchorOverrideY = 0.0f;
        float ValidationRouteAnchorOverrideZ = 0.0f;
        std::string ValidationRouteAnchorOverrideReason;
        std::vector<SafePosition> SafePositions;
        std::map<uint64, uint64> DummyTargetCooldownUntilMs;
        std::map<std::string, uint64> AbilityObjectiveCooldownUntilMs;
        std::map<std::string, uint32> AbilityObjectiveNoProgressCasts;
        ObjectGuid LastKilledTargetGuid;
        ObjectGuid LastLootTargetGuid;
        uint64 LastDecisionTickMs = 0;
        uint64 LastMovementProgressMs = 0;
        uint64 LastPathChangeMs = 0;
        bool IsMoving = false;
        float DistanceMovedSinceLastDecision = 0.0f;
        float LastDecisionDistanceMoved = 0.0f;
        std::string LastDecisionSituation = "unknown";
        std::string LastDecisionAction = "wait";
        std::string LastDecisionActivity = "experiment_exploration";
        std::string LastDecisionResult = "ok";
        std::string LastDecisionReason;
        std::string LastDecisionHandler = "none";
        std::string LastActionCategory = "wait";
        std::string LastClassSpecProfile = "{}";
        std::string LastRoleGoal = "increase_character_power";
        std::string LastRoleSaturationStateJson = "{}";
        std::string LastRecommendedBalanceMode = "role_first";
        std::string LastSaturationReason = "role_first";
        std::string LastProgressionReason = "{}";
        std::string LastProfessionGoal = "{}";
        std::string LastMechanicFamily = "none";
        std::string LastEncounterRoleResponsibility = "maintain_role";
        std::string LastValidActionMaskJson = "{}";
        std::string LastChosenActionJson = "{}";
        std::string LastNextExpectedAction = "wait_for_next_decision_tick";
        std::string LastCombatRejectReason;
        uint32 LastDecisionQuestId = 0;
        ObjectGuid LastDecisionTargetGuid;
        uint32 LastDecisionFingerprintHash = 0;
        uint32 LastDecisionFingerprintRepeatCount = 0;
        uint32 LastDecisionFingerprintFailureCount = 0;
        uint32 ConsecutiveSameDecisionCount = 0;
        uint32 IdleDecisionRepeatCount = 0;
        uint32 TargetChurnCount = 0;
        uint64 TargetChurnWindowStartMs = 0;
        uint64 LoopRecoveryCooldownUntilMs = 0;
        uint32 LoopGuardrailCount = 0;
        uint64 LastLoopGuardrailMs = 0;
        std::string LastLoopGuardrailAction;
        std::string LastLoopGuardrailReason;
        std::string LastRecoveryMode;
        std::string LastRecoveryResult;
        uint64 LastRecoveryMs = 0;
        uint32 RecoveryAttemptCount = 0;

        struct DecisionTraceEntry
        {
            uint64 TimestampMs = 0;
            uint32 Sequence = 0;
            std::string Situation = "unknown";
            std::string Action = "wait";
            uint32 QuestId = 0;
            uint64 TargetGuid = 0;
            uint32 DestinationMapId = 0;
            float DestinationX = 0.0f;
            float DestinationY = 0.0f;
            float DestinationZ = 0.0f;
            std::string Result = "ok";
            std::string ReasonCode;
            uint32 FingerprintHash = 0;
            uint32 FingerprintRepeatCount = 0;
            uint32 FingerprintFailureCount = 0;
            uint32 ConsecutiveSameDecisionCount = 0;
            uint32 IdleDecisionRepeatCount = 0;
            uint32 TargetChurnCount = 0;
            std::string LoopGuardrailAction;
            std::string LoopGuardrailReason;
            std::string RecoveryMode;
            std::string RecoveryResult;
        };
        std::deque<DecisionTraceEntry> DecisionTrace;

        uint32 LootAttemptCount = 0;
        uint64 LootStartedMs = 0;
        uint64 LootCompletedMs = 0;
        std::string LastLootResult = "none";
        uint32 LastLootItemsCount = 0;
        uint64 LastLootMoney = 0;
        bool LastLootStateCleared = false;
        uint64 NextLootAttemptMs = 0;
        uint64 NextGearDecisionMs = 0;
        uint64 NextProfessionDecisionMs = 0;
        bool PreferMaterialMemoryAction = false;
        std::string LastNoProgressReason;
        std::map<std::string, uint64> NoProgressCooldownUntilMs;
        std::map<uint64, uint64> QuestGiverCooldownUntilMs;
        std::map<uint32, uint64> QuestCooldownUntilMs;
        std::map<std::string, uint32> QuestPickupAttemptCount;
        uint32 NewlyAcceptedQuestId = 0;
        uint64 RecentlyAcceptedQuestUntilMs = 0;
        uint64 ObjectiveSearchUntilMs = 0;
        float ObjectiveSearchX = 0.0f;
        float ObjectiveSearchY = 0.0f;
        float ObjectiveSearchZ = 0.0f;
        std::string LastObjectiveNotFoundReason;
        std::string LastGrindingAllowedReason;
        uint32 QuestSearchRadiusIndex = 0;
        uint32 ActiveQuestClusterId = 0;
        std::string LastNoQuestReason;
        std::string LastQuestBucketReason;
        std::string LastQuestClassification;

        struct RouteDestination
        {
            bool Valid = false;
            uint32 MapId = 0;
            float X = 0.0f;
            float Y = 0.0f;
            float Z = 0.0f;
            uint32 QuestId = 0;
            std::string Reason;
        } QuestSearchDestination, QuestRouteDestination;

        struct BotQuestWorkState
        {
            uint32 ActiveQuestId = 0;
            uint32 ObjectiveIndex = 0;
            std::string ObjectiveType = "none";
            int32 RequiredEntry = 0;
            uint32 RequiredItem = 0;
            uint32 RequiredSpell = 0;
            uint32 RequiredCount = 0;
            uint32 CurrentCount = 0;
            ObjectGuid SelectedTargetGuid;
            ObjectGuid SelectedObjectGuid;
            ObjectGuid SelectedGiverGuid;
            std::string Phase = "idle";
            uint64 PhaseStartedMs = 0;
            uint64 LastProgressMs = 0;
            uint32 RetryCount = 0;
            std::string FailedReason;
            uint64 CooldownUntilMs = 0;
            uint32 ProgressBefore = 0;
            uint32 ProgressAfter = 0;
            uint32 VerifiedCasts = 0;
            uint64 VerifyAfterMs = 0;
        } QuestWork;
    };

    struct QuestObjectivePlan
    {
        uint32 QuestId = 0;
        int32 RequiredEntry = 0;
        uint32 RequiredCount = 0;
        uint32 CurrentCount = 0;
        bool IsGameObject = false;
        bool IsItemObjective = false;
        uint32 ItemId = 0;
        QuestObjectiveType ObjectiveType = QuestObjectiveType::Kill;
        uint32 RequiredSpellId = 0;
        uint32 ObjectiveIndex = 0;
        bool RequiresTrainingDummy = false;
    };

    struct QuestActionResult
    {
        bool Handled = false;
        bool Failure = false;
        bool Rare = false;
        std::string Situation = "questing";
        std::string Action = "wait";
        Unit* Target = nullptr;
        uint32 QuestId = 0;
        uint32 RewardChoice = 0;
        uint32 RewardItemId = 0;
    };

    struct BotDiagnosis
    {
        std::string DiagnosisCode = "waiting_decision_tick";
        std::string Severity = "info";
        float Confidence = 0.5f;
        std::string Intent = "increase_character_power";
        std::string CurrentAction = "wait";
        std::string Blocker;
        std::string NextExpectedAction = "wait_for_next_decision_tick";
        std::string SuggestedInvestigation = "inspect_trace_for_repeated_state";
    };

    struct QuestRoutePoint
    {
        bool Valid = false;
        uint32 MapId = 0;
        uint32 ZoneId = 0;
        uint32 QuestId = 0;
        uint32 ObjectiveIndex = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float Score = 0.0f;
        std::string Source;
    };

    struct QuestObjectiveBucket
    {
        uint32 BucketId = 0;
        uint32 MapId = 0;
        float CenterX = 0.0f;
        float CenterY = 0.0f;
        float CenterZ = 0.0f;
        float Score = 0.0f;
        std::vector<QuestObjectivePlan> Objectives;
        std::string Reason;
    };

    struct QuestPortfolioPlan
    {
        uint32 ActiveQuestCount = 0;
        std::vector<QuestObjectiveBucket> Buckets;
        std::vector<QuestObjectivePlan> UnresolvedObjectives;
    };

    struct DungeonTrashPackFeatures
    {
        uint32 PackSize = 0;
        uint32 EliteCount = 0;
        uint32 CasterCount = 0;
        uint32 HealerCount = 0;
        uint32 ActiveCasts = 0;
        uint32 DangerousCasts = 0;
        float InterruptPriority = 0.0f;
        float AoeValue = 0.0f;
        float CcValue = 0.0f;
        float PullRisk = 0.0f;
        float TankThreat = 0.0f;
        float PartyAverageHpPct = 1.0f;
        float LowestAllyHpPct = 1.0f;
        float HealerManaPct = 1.0f;
        bool PatrolNearby = false;
        ObjectGuid PriorityTargetGuid;
        uint32 PriorityTargetEntry = 0;
        uint32 PrioritySpellId = 0;
    };

    struct DungeonTrashActionResult
    {
        bool Handled = false;
        bool Failure = false;
        bool Rare = false;
        std::string Situation = "dungeon_trash";
        std::string Action = "follow_tank";
        Unit* Target = nullptr;
        uint32 SpellId = 0;
        DungeonTrashPackFeatures Pack;
    };

    struct BossMechanicFeatures
    {
        bool RaidEncounter = false;
        bool BossPresent = false;
        bool BossCasting = false;
        uint32 BossEntry = 0;
        uint32 CastSpellId = 0;
        int32 CastRemainingMs = 0;
        bool DangerousCast = false;
        bool MustInterrupt = false;
        bool GroundDanger = false;
        bool MoveOut = false;
        bool TankSpike = false;
        bool RaidDamage = false;
        bool AddsActive = false;
        bool StackPlaceholder = false;
        bool SpreadPlaceholder = false;
        uint32 AddCount = 0;
        float TankHpPct = 1.0f;
        float PartyAverageHpPct = 1.0f;
        float LowestAllyHpPct = 1.0f;
        float HealerManaPct = 1.0f;
        float DangerScore = 0.0f;
        float InterruptPriority = 0.0f;
        ObjectGuid BossGuid;
        ObjectGuid PriorityAddGuid;
    };

    struct BossMechanicActionResult
    {
        bool Handled = false;
        bool Failure = false;
        bool Rare = false;
        std::string Situation = "dungeon_boss";
        std::string Action = "boss_wait";
        Unit* Target = nullptr;
        uint32 SpellId = 0;
        BossMechanicFeatures Features;
    };

    struct RaidRoleAssignment
    {
        std::string Role = "dps";
        uint8 SubGroup = 0;
        uint32 RaidSize = 0;
        uint32 TankCount = 0;
        uint32 HealerCount = 0;
        uint32 DpsCount = 0;
        uint32 RoleIndex = 0;
        ObjectGuid MainTankGuid;
        ObjectGuid OffTankGuid;
        ObjectGuid RaidLeaderGuid;
    };

    struct RaidPositioningAnchors
    {
        bool Active = false;
        std::string AnchorType = "leader";
        ObjectGuid AnchorGuid;
        float AnchorX = 0.0f;
        float AnchorY = 0.0f;
        float AnchorZ = 0.0f;
        float StackX = 0.0f;
        float StackY = 0.0f;
        float StackZ = 0.0f;
        float SpreadX = 0.0f;
        float SpreadY = 0.0f;
        float SpreadZ = 0.0f;
        float DistanceToAnchor = 0.0f;
    };

    struct RaidMechanicAdapter
    {
        std::string MechanicFamily = "boss_pressure";
        std::string AssignmentType = "maintain_role";
        std::string RecommendedAction = "boss_single_target";
        ObjectGuid AssignedTargetGuid;
        float Priority = 0.0f;
        bool HeroicOnly = false;
    };

    struct RaidGearTargetPlan
    {
        float CurrentItemLevel = 0.0f;
        float TargetItemLevel = 359.0f;
        float NeededItemLevel = 0.0f;
        std::string RecommendedActivity = "raid";
        bool ReadyForRaid = false;
        bool ReadyForHeroicRaid = false;
    };

    struct HeroicRaidProgression
    {
        bool TrackingEnabled = false;
        bool HeroicEligible = false;
        std::string Stage = "normal_raid";
        uint32 RaidAttempts = 0;
        uint32 RaidBossKills = 0;
        uint32 HeroicRaidBossKills = 0;
        uint32 Wipes = 0;
        float RolePowerScore = 0.0f;
        float TargetItemLevel = 372.0f;
    };

    struct SemanticOutcomeStats
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

    struct ReplayRecord
    {
        bool Loaded = false;
        uint64 Id = 0;
        uint64 ExperimentId = 0;
        uint64 RunId = 0;
        uint32 BotGuid = 0;
        std::string ReplayType;
        uint32 MapId = 0;
        uint32 ZoneId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float O = 0.0f;
        std::string BotSnapshotJson;
        std::string WorldSnapshotJson;
        std::string PartySnapshotJson;
        std::string RawStateJson;
        std::string SemanticStateJson;
        std::string ChosenActionJson;
        std::string FailureJson;
    };

    struct ReplayExecutionResult
    {
        bool Ok = false;
        bool Success = false;
        uint64 ReplayId = 0;
        uint64 RunId = 0;
        std::string BrainVersion;
        std::string FailureReason;
        uint32 Decisions = 0;
        uint32 Failures = 0;
        uint32 Deaths = 0;
        uint32 Kills = 0;
        uint32 StuckEvents = 0;
        float FinalPower = 0.0f;
        std::string FirstAction;
        std::string ReplayType;
    };

    struct SpawnPlacement
    {
        bool Valid = false;
        uint32 MapId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float O = 0.0f;
        std::string Source;
        bool RaceStartFallbackUsed = false;
    };

    struct BotDeathRecoveryPolicy
    {
        std::vector<std::string> Modes;
        bool CenterFallbackEnabled = false;
        uint32 MaxDeathsBeforeFallback = 3;
        uint32 SafePositionMemorySec = 120;
    };

    struct DeathRecoveryResult
    {
        bool Recovered = false;
        bool UsedFallback = false;
        bool RepeatedDeath = false;
        std::string Mode;
        std::string Result = "failed";
    };

    struct PolicyModelTrace
    {
        bool Enabled = false;
        float ModelScore = 0.0f;
        uint32 ModelRank = 0;
        uint32 FeaturesHash = 0;
        std::string Json = "{}";
    };

    void LoadConfig(std::string const& name, BotWorldExperimentConfig const* overrideConfig);
    void ApplyRuntimeConfigOverride(BotWorldExperimentConfig const& overrideConfig);
    void ApplyRuntimeProfile(BotWorldExperimentProfile const& profile);
    bool SelectConfiguredRuntimeProfile();
    bool EnsureRuntimeProfilesLoaded();
    bool LoadRuntimeProfiles(std::string* failureReason = nullptr);
    std::string RuntimeProfilesJson(char const* action) const;
    void MaybeStartAutoRecordingWindow();
    void RotateAutoRecordingWindowIfNeeded(uint32 diff);
    std::string BuildAutoRecordingWindowName() const;
    void ValidatePolicyModelDeployment();
    bool LoadPolicyModelArtifact(std::string const& artifactPath);
    void EnsurePopulation();
    bool ResolveSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const;
    bool ResolveSavedSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const;
    bool ResolveRaceStartSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const;
    bool ResolveNearPlayerSpawnPlacement(SpawnPlacement& placement) const;
    bool ResolveConfiguredCenterSpawnPlacement(SpawnPlacement& placement) const;
    bool IsValidBotResumePosition(uint32 botGuid, uint32 mapId, float x, float y, float z) const;
    bool IsConfiguredCenterPosition(uint32 mapId, float x, float y, float z) const;
    void PersistBotPosition(Player* bot) const;
    void RecordSpawnResolved(WorldBotState& state, Player* bot, SpawnPlacement const& placement, char const* result);
    void UpdateBot(WorldBotState& state, uint32 diff);
    bool TryReattachValidationBot(WorldBotState& state, Player* bot, char const* context);
    void RememberSafePosition(WorldBotState& state, Player* bot, uint32 diff);
    void PruneSafePositions(WorldBotState& state, uint64 nowMs) const;
    void RememberVisiblePois(WorldBotState& state, Player* bot, uint32 diff);
    void RememberPoi(WorldBotState& state, Player* bot, WorldObject* object, char const* poiType, uint32 questId, float score) const;
    void MarkDeathDangerZone(WorldBotState& state, Player* bot, Unit const* target);
    void MarkStuckFailure(WorldBotState& state, Player* bot);
    float GetLocalDangerScore(uint32 botGuid, uint32 mapId, float x, float y, float z) const;
    bool IsFailedPathRecently(uint32 botGuid, uint32 mapId, float fromX, float fromY, float toX, float toY) const;
    bool FindMemoryPoiTarget(Player* bot, float& x, float& y, float& z, uint64& poiId) const;
    void MarkPoiVisited(uint64 poiId) const;
    bool MoveBotToPoint(WorldBotState& state, Player* bot, float x, float y, float z);
    BotDeathRecoveryPolicy BuildDeathRecoveryPolicy() const;
    DeathRecoveryResult RecoverDeadBot(WorldBotState& state, Player* bot);
    bool TryCorpseRecovery(Player* bot, std::string& result) const;
    bool TrySafeLocalResurrect(Player* bot, std::string& result) const;
    bool TryNearestGraveyardResurrect(Player* bot, std::string& result) const;
    bool TryLastSafePositionResurrect(WorldBotState& state, Player* bot, std::string& result);
    bool TryConfiguredCenterDeathFallback(Player* bot, std::string& result) const;
    Player* GetLoadedBot(WorldBotState const& state) const;
    Player* GetBot(WorldBotState const& state) const;
    uint32 SelectPoolCandidateGuid() const;
    Unit* SelectSafeTarget(WorldBotState& state, Player* bot);
    Unit* SelectQuestObjectiveTarget(Player* bot, QuestObjectivePlan const& plan) const;
    Unit* SelectQuestAbilityObjectiveTarget(Player* bot, QuestObjectivePlan const& plan, WorldBotState const& state) const;
    WorldObject* SelectQuestGiver(Player* bot, bool completeOnly, uint32* questId, WorldBotState const* state = nullptr) const;
    WorldObject* SelectQuestGameObject(Player* bot, QuestObjectivePlan const& plan) const;
    bool FindActiveQuestObjective(Player* bot, QuestObjectivePlan& plan) const;
    bool FindQuestObjective(Player* bot, uint32 questId, QuestObjectivePlan& plan) const;
    bool GetQuestObjectivePlan(Player* bot, uint32 questId, uint32 objectiveIndex, QuestObjectiveType type, QuestObjectivePlan& plan) const;
    QuestClassification ClassifyQuestForBot(Player* bot, Quest const* quest) const;
    QuestPortfolioPlan BuildQuestPortfolioPlan(Player* bot, WorldBotState const& state) const;
    bool FindQuestPickupDestination(Player* bot, WorldBotState const& state, QuestRoutePoint& point) const;
    bool FindQuestTurnInDestination(Player* bot, uint32 questId, QuestRoutePoint& point) const;
    bool ResolveObjectiveRoutePoint(Player* bot, QuestObjectivePlan const& plan, QuestRoutePoint& point) const;
    bool SelectQuestObjectiveBucket(Player* bot, QuestPortfolioPlan const& plan, QuestObjectiveBucket& bucket) const;
    void SetQuestWorkPhase(WorldBotState& state, char const* phase);
    void SetQuestWorkFromPlan(WorldBotState& state, QuestObjectivePlan const& plan);
    void ResetQuestWork(WorldBotState& state);
    bool IsProgressionCombatTarget(Player* bot, Unit* target, char const** rejectReason = nullptr) const;
    bool IsQuestRelevantTarget(Player* bot, Unit* target) const;
    bool HasNearbySupportedQuestGiver(Player* bot, WorldBotState const& state) const;
    bool IsGenericGrindingAllowed(WorldBotState& state, Player* bot, BotProgressionActivity activity, bool hasActiveQuestObjective);
    void MoveToObjectiveSearchPoint(WorldBotState& state, Player* bot, QuestObjectivePlan const* plan, WorldObject const* avoidObject = nullptr);
    bool VerifyQuestObjectiveProgress(WorldBotState& state, Player* bot, QuestObjectivePlan const& plan, Unit const* target, uint32 before, char const* reason, char const* rawJson, char const* semanticJson);
    bool IsTrainingDummy(Unit const* unit) const;
    bool IsTrainingDummyAllowedForQuest(QuestObjectivePlan const& plan, Unit const* target) const;
    bool IsDummyEntryConfigured(uint32 entry, bool* explicitAllow = nullptr) const;
    bool QuestTextSuggestsAbilityObjective(Quest const* quest) const;
    uint32 SelectQuestAbilitySpell(Player* bot, Quest const* quest, QuestObjectivePlan const& plan) const;
    uint32 QuestObjectiveProgress(Player* bot, QuestObjectivePlan const& plan) const;
    bool StopDisallowedDummyCombat(WorldBotState& state, Player* bot, Unit* target);
    bool HasSimpleSupportedObjective(Quest const* quest) const;
    uint32 ChooseQuestReward(Player* bot, Quest const* quest, uint32* rewardItemId = nullptr) const;
    QuestActionResult TryQuesting(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity);
    bool TryValidationRouteObjective(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action, Unit*& target);
    bool IsBossContext(Player* bot, Unit const* target) const;
    Unit* FindBossTarget(Player* bot) const;
    BossMechanicFeatures BuildBossMechanicFeatures(Player* bot, Unit const* boss) const;
    BossMechanicActionResult TryBossMechanics(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity);
    RaidRoleAssignment BuildRaidRoleAssignment(Player* bot) const;
    RaidPositioningAnchors BuildRaidPositioningAnchors(Player* bot, Unit const* boss, RaidRoleAssignment const& assignment, BossMechanicFeatures const& features) const;
    RaidMechanicAdapter BuildRaidMechanicAdapter(Player* bot, Unit const* boss, RaidRoleAssignment const& assignment, BossMechanicFeatures const& features) const;
    RaidGearTargetPlan BuildRaidGearTargetPlan(Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    HeroicRaidProgression BuildHeroicRaidProgression(WorldBotState const& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    std::string BuildRaidRoleAssignmentJson(RaidRoleAssignment const& assignment) const;
    std::string BuildRaidPositioningAnchorsJson(RaidPositioningAnchors const& anchors) const;
    std::string BuildRaidMechanicAdapterJson(RaidMechanicAdapter const& adapter) const;
    std::string BuildRaidGearTargetPlanJson(RaidGearTargetPlan const& plan) const;
    std::string BuildHeroicRaidProgressionJson(HeroicRaidProgression const& progression) const;
    void RecordRaidTelemetry(WorldBotState& state, Player* bot, Unit const* boss, char const* eventType, char const* result, BossMechanicFeatures const& features, RaidRoleAssignment const& assignment, RaidPositioningAnchors const& anchors, RaidMechanicAdapter const& adapter, RaidGearTargetPlan const& gearPlan, HeroicRaidProgression const& progression, char const* rawJson, char const* semanticJson, float valueFloat = 0.0f, uint32 valueInt = 0, uint32 spellId = 0);
    bool IsDungeonTrashContext(Player* bot, Unit const* target) const;
    Player* FindDungeonAnchor(Player* bot) const;
    Unit* FindGroupCombatTarget(Player* bot, Player* anchor) const;
    DungeonTrashPackFeatures BuildDungeonTrashPackFeatures(Player* bot, Unit const* focus) const;
    DungeonTrashActionResult TryDungeonTrash(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity);
    char const* GetDungeonRole(Player* bot) const;
    uint32 SelectInterruptSpell(Player* bot) const;
    uint32 SelectHealSpell(Player* bot) const;
    bool TryCastFriendlySpell(Player* bot, Unit* target, uint32 spellId) const;
    std::string BuildDungeonTrashPackJson(DungeonTrashPackFeatures const& pack) const;
    std::string BuildBossMechanicsJson(BossMechanicFeatures const& features) const;
    uint32 SelectCombatSpell(Player* bot, Unit* target) const;
    bool TryCastCombatSpell(Player* bot, Unit* target, uint32 spellId) const;
    void MoveToWanderPoint(Player* bot, WorldBotState& state);
    void RecordRunStart();
    void RecordRunStop();
    void LoadValidationRouteManifest();
    bool ApplyValidationRouteManifestNode(size_t index, char const* reason);
    bool MaybeAdvanceValidationRouteManifest();
    void ResetValidationRouteRuntimeState(char const* reason);
    bool ValidationRouteHasProgressSinceApply() const;
    ReplayRecord LoadReplayRecord(std::string const& replayType, std::string const& selector) const;
    ReplayRecord LoadReplayRecord(uint64 replayId) const;
    ReplayExecutionResult ExecuteReplayRecord(ReplayRecord const& record, std::string const& brainVersion);
    std::string BuildReplayResultJson(ReplayExecutionResult const& result) const;
    void RecordReplayEvent(WorldBotState const& state, Player* bot, char const* eventType, ReplayRecord const& record, char const* result, char const* contextJson = nullptr);
    void RecordActivityStart(WorldBotState& state, Player* bot);
    void RecordActivityStop(WorldBotState const& state, Player* bot = nullptr);
    void EnsureValidationCohortGroup();
    bool IsValidationProfileName(std::string const& name) const;
    bool PrepareCurrentValidationProfile(char const* reason);
    bool ApplyValidationProvisioningSql(char const* reason);
    bool ResetValidationBotPool(char const* reason);
    bool IsValidationCohortMemberInOriginalInstance(WorldBotState const& state, Player const* bot) const;
    void MarkValidationCohortViolation(WorldBotState& state, Player const* bot, char const* reason);
    bool TrySmartGearDecision(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action);
    bool TryProfessionMemoryAction(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action);
    void RecordGearEvaluation(WorldBotState& state, Player* bot, BotGearUpgradeEvaluation const& evaluation, char const* rawJson, char const* semanticJson);
    void RecordQuestObjectiveProgressForTarget(WorldBotState& state, Player* bot, Unit const* target, char const* rawJson, char const* semanticJson);
    void RecordQuestEvent(WorldBotState& state, Player* bot, char const* eventType, uint32 questId, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, uint32 valueInt = 0, uint32 itemId = 0, char const* contextJson = nullptr);
    void RecordObjectiveClusterMemory(WorldBotState const& state, Player* bot, char const* eventType, uint32 questId, char const* result, uint32 valueInt, char const* contextJson) const;
    void RememberVisibleSourceMemory(WorldBotState const& state, Player* bot, WorldObject* object, char const* poiType, uint32 entry, uint32 questId, char const* metadataJson) const;
    void RecordExperimentSegmentEvent(Player* bot, char const* eventType, char const* result, uint32 questId, Unit const* target, uint64 clipId, char const* rawJson, char const* semanticJson);
    void RecordQuestReplay(WorldBotState const& state, Player* bot, char const* replayType, uint32 questId, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson);
    void RecordBossReplay(WorldBotState const& state, Player* bot, Unit const* boss, BossMechanicFeatures const& features, char const* replayType, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson);
    uint64 RecordDecisionReplay(WorldBotState const& state, Player* bot, Unit const* target, char const* situation, char const* action, char const* rawJson, char const* semanticJson, char const* candidateJson, BotActivityScore const& chosenActivity, bool failure);
    void RecordEvent(WorldBotState& state, Player* bot, char const* eventType, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, float valueFloat = 0.0f, uint32 valueInt = 0, uint32 spellId = 0);
    void RecordDecision(WorldBotState& state, Player* bot, char const* situation, char const* action, Unit const* target, char const* rawJson, char const* semanticJson, std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, BotRolePowerBreakdown const& power, bool failure, bool rare);
    void RecordDecisionFingerprintMemory(WorldBotState& state, Player* bot, char const* situation, char const* action, BotActivityScore const& chosenActivity, bool failure) const;
    void RecordDecisionTrace(WorldBotState& state, char const* situation, char const* action, Unit const* target, uint32 questId, char const* result, char const* reasonCode);
    BotDiagnosis BuildBotDiagnosis(WorldBotState const& state, Player const* bot) const;
    std::string BuildBotDiagnosisObjectJson(WorldBotState const& state, Player const* bot) const;
    std::string BuildBotDecisionSnapshotJson(WorldBotState const& state, Player const* bot) const;
    std::string BuildBotTraceEntriesJson(WorldBotState const& state, uint32 limit) const;
    BotTelemetryPolicyConfig GetTelemetryPolicyConfig() const;
    BotTelemetryPolicyInput BuildTelemetryPolicyInput(char const* eventType, char const* result, char const* situation, Unit const* target, uint32 spellId = 0, uint32 questId = 0, uint32 itemId = 0, float valueFloat = 0.0f, uint32 valueInt = 0, bool failure = false, bool rare = false, bool intervention = false) const;
    void RecordPolicyReplay(WorldBotState const& state, Player* bot, Unit const* target, BotTelemetryPolicyInput const& input, char const* rawJson, char const* semanticJson);
    BotTelemetryFrame BuildTelemetryFrame(Player* bot, Unit const* target, char const* situation, char const* action, char const* rawJson, char const* semanticJson, uint32 questId = 0) const;
    uint64 MaybeCaptureTelemetryClip(Player* bot, Unit const* target, BotTelemetryPolicyInput const& input, BotTelemetryPolicyDecision const& decision, char const* rawJson, char const* semanticJson);
    void UpdateSemanticOutcomeStats(Player* bot, char const* entityType, uint32 entityKey, char const* eventType, char const* result, float reward, float powerDelta, bool failure, char const* featuresJson);
    void UpdateSemanticStatsFromEvent(Player* bot, Unit const* target, char const* eventType, char const* result, float valueFloat, uint32 valueInt, uint32 spellId, char const* semanticJson);
    SemanticOutcomeStats GetSemanticOutcomeStats(char const* entityType, uint32 entityKey) const;
    std::string BuildOutcomeStatsJson(SemanticOutcomeStats const& stats) const;
    std::string BuildEmbeddingFeaturesJson(Player const* bot, Unit const* target, char const* entityType, uint32 entityKey, char const* semanticFamily) const;
    std::string BuildRawJson(Player* bot, Unit const* target) const;
    std::string BuildSemanticJson(Player* bot, Unit const* target, char const* situation, BotRolePowerBreakdown const* power = nullptr, BotProgressionStage stage = BotProgressionStage::Leveling, BotProgressionActivity activity = BotProgressionActivity::ExperimentExploration) const;
    RoleSaturationState BuildRoleSaturationState(Player const* bot, Unit const* target, char const* role, float encounterDanger = 0.0f, float interruptPressure = 0.0f, bool tankBuster = false, bool adds = false, bool noValidActions = false) const;
    std::string BuildConfigJson() const;
    std::string BuildActivityCandidatesJson(std::vector<BotActivityScore> const& activityScores) const;
    void ApplyPolicyModelScores(std::vector<BotActivityScore>& activityScores, Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    PolicyModelTrace BuildPolicyModelTrace(std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, Player const* bot, uint64 clipId, uint64 replayId) const;
    float ScorePolicyModelCandidate(BotActivityScore const& score, Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    std::map<std::string, float> BuildPolicyModelFeatureMap(BotActivityScore const& score, Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    float PredictPolicyModelLabel(char const* label, std::map<std::string, float> const& features) const;
    static uint32 FeatureSchemaHash(std::string const& value);
    static std::string JsonEscape(std::string const& value);

    bool _active = false;
    BotWorldRuntimeMode _runtimeMode = BotWorldRuntimeMode::ManualExperiment;
    uint64 _experimentId = 0;
    uint64 _runId = 0;
    uint32 _elapsedMs = 0;
    uint32 _recordingWindowElapsedMs = 0;
    uint32 _recordingWindowIndex = 0;
    BotWorldExperimentConfig _config;
    std::string _profileManifestPath;
    std::map<std::string, BotWorldExperimentProfile> _runtimeProfiles;
    std::vector<std::string> _runtimeProfileOrder;
    std::string _selectedProfileName;
    std::string _profileManifestLoadError;
    bool _runtimeProfilesLoaded = false;
    bool _runtimeProfileDirty = false;
    BotExperienceLearningConfig _learningConfig;
    BotPolicyModelConfig _policyModelConfig;
    std::vector<WorldBotState> _bots;
    std::set<uint32> _failedSpawnGuids;
    std::string _lastPopulationFailureReason;
    BotWorldStatus _metrics;
    BotTelemetryBuffer _telemetryBuffer;
    BotExperimentCoordinator _experimentCoordinator;
    ObjectGuid _validationRouteFocusGuid;
    uint32 _validationRouteFocusEntry = 0;
    uint32 _validationRouteFocusMapId = 0;
    float _validationRouteFocusX = 0.0f;
    float _validationRouteFocusY = 0.0f;
    float _validationRouteFocusZ = 0.0f;
    uint64 _validationRouteFocusSeenMs = 0;
    ObjectGuid _validationRouteBossProgressTargetGuid;
    uint32 _validationRouteBossSlowProgressCount = 0;
    bool _validationRouteActivationApplied = false;
    uint32 _validationRouteActivationAttempts = 0;
    std::vector<ValidationRouteManifestNode> _validationRouteManifest;
    size_t _validationRouteManifestIndex = 0;
    uint32 _validationRouteProgressBaselineKills = 0;
    bool _validationRouteManifestAdvancePending = false;
    bool _validationRouteManifestComplete = false;
    std::string _validationRouteManifestAdvanceReason;
    std::string _validationRouteManifestLoadError;
    mutable std::map<uint32, std::string> _lastCombatMaskByBot;
    mutable std::map<uint32, std::string> _lastChosenCombatByBot;
    mutable std::map<uint32, std::string> _lastActionCategoryByBot;
    mutable std::map<uint32, RoleSaturationState> _lastSaturationByBot;
};

#define sBotWorldPopulationMgr BotWorldPopulationMgr::instance()

#endif
