#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_H

#include "ObjectGuid.h"
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

class Player;
class Unit;

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
    bool AllowQuesting = false;
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
    uint32 StuckEvents = 0;
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
        float LastX = 0.0f;
        float LastY = 0.0f;
        float LastZ = 0.0f;
        ObjectGuid TargetGuid;
        bool WasInCombat = false;
    };

    void EnsurePopulation();
    void UpdateBot(WorldBotState& state, uint32 diff);
    Player* GetBot(WorldBotState const& state) const;
    uint32 SelectPoolCandidateGuid() const;
    Unit* SelectSafeTarget(Player* bot) const;
    uint32 SelectCombatSpell(Player* bot, Unit* target) const;
    bool TryCastCombatSpell(Player* bot, Unit* target, uint32 spellId) const;
    void MoveToWanderPoint(Player* bot, WorldBotState& state);
    void RecordRunStart();
    void RecordRunStop();
    void RecordActivityStart(WorldBotState& state, Player* bot);
    void RecordActivityStop(WorldBotState const& state);
    void RecordEvent(WorldBotState const& state, Player* bot, char const* eventType, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, float valueFloat = 0.0f, uint32 valueInt = 0, uint32 spellId = 0);
    void RecordDecision(WorldBotState& state, Player* bot, char const* situation, char const* action, Unit const* target, char const* rawJson, char const* semanticJson, bool failure, bool rare);
    std::string BuildRawJson(Player* bot, Unit const* target) const;
    std::string BuildSemanticJson(Player* bot, Unit const* target, char const* situation) const;
    std::string BuildConfigJson() const;
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
