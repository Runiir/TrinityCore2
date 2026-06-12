#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_H

#include "ObjectGuid.h"
#include "Bots/BotExperimentCoordinator.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include "Bots/BotTelemetryBuffer.h"
#include "Bots/BotTelemetryPolicy.h"
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
    std::string SpawnMode = "saved_or_near_player";
    bool AllowConfiguredCenterFallback = true;
    bool UseSavedPosition = true;
    float NearPlayerRadius = 20.0f;
    std::string RespawnMode = "corpse_or_safe_local";
    bool TeleportToCenterOnDeath = false;
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
    bool SpawnAutonomyBots(uint32 count);
    BotWorldStatus GetStatus() const;
    std::string GetStatusJson() const;
    std::string GetSummaryJson() const;
    bool IsActive() const { return _active; }
    std::string Replay(std::string const& replayType, std::string const& selector, std::string const& brainVersion = "");
    std::string CompareBrains(uint64 replayId, std::string const& firstBrainVersion, std::string const& secondBrainVersion);

private:
    struct WorldBotState
    {
        ObjectGuid Guid;
        uint32 DecisionTimer = 0;
        uint32 StuckTimer = 0;
        uint32 DeadTimer = 0;
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
        ObjectGuid TargetGuid;
        bool WasInCombat = false;
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
    };

    void LoadConfig(std::string const& name, BotWorldExperimentConfig const* overrideConfig);
    void EnsurePopulation();
    bool ResolveSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const;
    bool ResolveSavedSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const;
    bool ResolveNearPlayerSpawnPlacement(SpawnPlacement& placement) const;
    bool ResolveConfiguredCenterSpawnPlacement(SpawnPlacement& placement) const;
    void UpdateBot(WorldBotState& state, uint32 diff);
    Player* GetBot(WorldBotState const& state) const;
    uint32 SelectPoolCandidateGuid() const;
    Unit* SelectSafeTarget(Player* bot) const;
    Unit* SelectQuestObjectiveTarget(Player* bot, QuestObjectivePlan const& plan) const;
    WorldObject* SelectQuestGiver(Player* bot, bool completeOnly, uint32* questId) const;
    WorldObject* SelectQuestGameObject(Player* bot, QuestObjectivePlan const& plan) const;
    bool FindActiveQuestObjective(Player* bot, QuestObjectivePlan& plan) const;
    bool HasSimpleSupportedObjective(Quest const* quest) const;
    uint32 ChooseQuestReward(Player* bot, Quest const* quest, uint32* rewardItemId = nullptr) const;
    QuestActionResult TryQuesting(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity);
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
    ReplayRecord LoadReplayRecord(std::string const& replayType, std::string const& selector) const;
    ReplayRecord LoadReplayRecord(uint64 replayId) const;
    ReplayExecutionResult ExecuteReplayRecord(ReplayRecord const& record, std::string const& brainVersion);
    std::string BuildReplayResultJson(ReplayExecutionResult const& result) const;
    void RecordReplayEvent(WorldBotState const& state, Player* bot, char const* eventType, ReplayRecord const& record, char const* result, char const* contextJson = nullptr);
    void RecordActivityStart(WorldBotState& state, Player* bot);
    void RecordActivityStop(WorldBotState const& state, Player* bot = nullptr);
    void RecordGearEvaluation(WorldBotState& state, Player* bot, BotGearUpgradeEvaluation const& evaluation, char const* rawJson, char const* semanticJson);
    void RecordQuestObjectiveProgressForTarget(WorldBotState& state, Player* bot, Unit const* target, char const* rawJson, char const* semanticJson);
    void RecordQuestEvent(WorldBotState& state, Player* bot, char const* eventType, uint32 questId, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, uint32 valueInt = 0, uint32 itemId = 0, char const* contextJson = nullptr);
    void RecordExperimentSegmentEvent(Player* bot, char const* eventType, char const* result, uint32 questId, Unit const* target, uint64 clipId, char const* rawJson, char const* semanticJson);
    void RecordQuestReplay(WorldBotState const& state, Player* bot, char const* replayType, uint32 questId, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson);
    void RecordBossReplay(WorldBotState const& state, Player* bot, Unit const* boss, BossMechanicFeatures const& features, char const* replayType, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson);
    void RecordEvent(WorldBotState& state, Player* bot, char const* eventType, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, float valueFloat = 0.0f, uint32 valueInt = 0, uint32 spellId = 0);
    void RecordDecision(WorldBotState& state, Player* bot, char const* situation, char const* action, Unit const* target, char const* rawJson, char const* semanticJson, std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, BotRolePowerBreakdown const& power, bool failure, bool rare);
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
    std::string BuildConfigJson() const;
    std::string BuildActivityCandidatesJson(std::vector<BotActivityScore> const& activityScores) const;
    static std::string JsonEscape(std::string const& value);

    bool _active = false;
    BotWorldRuntimeMode _runtimeMode = BotWorldRuntimeMode::ManualExperiment;
    uint64 _experimentId = 0;
    uint64 _runId = 0;
    uint32 _elapsedMs = 0;
    BotWorldExperimentConfig _config;
    std::vector<WorldBotState> _bots;
    std::set<uint32> _failedSpawnGuids;
    BotWorldStatus _metrics;
    BotTelemetryBuffer _telemetryBuffer;
    BotExperimentCoordinator _experimentCoordinator;
};

#define sBotWorldPopulationMgr BotWorldPopulationMgr::instance()

#endif
