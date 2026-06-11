#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_H

#include "ObjectGuid.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

class Player;
class Quest;
class Unit;
class WorldObject;

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
    bool EnableProgression = true;
    bool RecordDecisions = true;
    bool RecordPerception = true;
    bool SmartSampling = true;
    uint32 NormalDecisionSampleRate = 10;
    std::string BrainVersion = "utility_v1";
};

struct BotWorldStatus
{
    bool Active = false;
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
    BotWorldStatus GetStatus() const;
    std::string GetStatusJson() const;
    std::string GetSummaryJson() const;
    bool IsActive() const { return _active; }

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

    void EnsurePopulation();
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
    uint32 SelectCombatSpell(Player* bot, Unit* target) const;
    bool TryCastCombatSpell(Player* bot, Unit* target, uint32 spellId) const;
    void MoveToWanderPoint(Player* bot, WorldBotState& state);
    void RecordRunStart();
    void RecordRunStop();
    void RecordActivityStart(WorldBotState& state, Player* bot);
    void RecordActivityStop(WorldBotState const& state, Player* bot = nullptr);
    void RecordGearEvaluation(WorldBotState const& state, Player* bot, BotGearUpgradeEvaluation const& evaluation, char const* rawJson, char const* semanticJson);
    void RecordQuestObjectiveProgressForTarget(WorldBotState& state, Player* bot, Unit const* target, char const* rawJson, char const* semanticJson);
    void RecordQuestEvent(WorldBotState const& state, Player* bot, char const* eventType, uint32 questId, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, uint32 valueInt = 0, uint32 itemId = 0, char const* contextJson = nullptr);
    void RecordQuestReplay(WorldBotState const& state, Player* bot, char const* replayType, uint32 questId, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson);
    void RecordEvent(WorldBotState const& state, Player* bot, char const* eventType, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, float valueFloat = 0.0f, uint32 valueInt = 0, uint32 spellId = 0);
    void RecordDecision(WorldBotState& state, Player* bot, char const* situation, char const* action, Unit const* target, char const* rawJson, char const* semanticJson, std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, BotRolePowerBreakdown const& power, bool failure, bool rare);
    std::string BuildRawJson(Player* bot, Unit const* target) const;
    std::string BuildSemanticJson(Player* bot, Unit const* target, char const* situation, BotRolePowerBreakdown const* power = nullptr, BotProgressionStage stage = BotProgressionStage::Leveling, BotProgressionActivity activity = BotProgressionActivity::ExperimentExploration) const;
    std::string BuildConfigJson() const;
    std::string BuildActivityCandidatesJson(std::vector<BotActivityScore> const& activityScores) const;
    static std::string JsonEscape(std::string const& value);

    bool _active = false;
    uint64 _experimentId = 0;
    uint64 _runId = 0;
    uint32 _elapsedMs = 0;
    BotWorldExperimentConfig _config;
    std::vector<WorldBotState> _bots;
    std::set<uint32> _failedSpawnGuids;
    BotWorldStatus _metrics;
};

#define sBotWorldPopulationMgr BotWorldPopulationMgr::instance()

#endif
