#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/BotMgr.h"
#include "CellImpl.h"
#include "Config.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "GameObject.h"
#include "GridNotifiersImpl.h"
#include "Log.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "Random.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Creature.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>

namespace
{
uint64 ReadLastInsertId()
{
    if (QueryResult result = CharacterDatabase.Query("SELECT LAST_INSERT_ID()"))
        return result->Fetch()[0].GetUInt64();

    return 0;
}

float Distance2d(float ax, float ay, float bx, float by)
{
    float dx = ax - bx;
    float dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}
}

BotWorldPopulationMgr* BotWorldPopulationMgr::instance()
{
    static BotWorldPopulationMgr instance;
    return &instance;
}

bool BotWorldPopulationMgr::Start(std::string const& experimentName, BotWorldExperimentConfig const* overrideConfig)
{
    if (_active)
        Stop();

    if (!sConfigMgr->GetBoolDefault("BotWorld.Enable", false) || !sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return false;

    _config = overrideConfig ? *overrideConfig : BotWorldExperimentConfig();
    if (!experimentName.empty())
        _config.Name = experimentName;

    _config.TargetPopulation = sConfigMgr->GetIntDefault("BotWorld.TargetPopulation", _config.TargetPopulation);
    _config.MapId = sConfigMgr->GetIntDefault("BotWorld.Map", _config.MapId);
    _config.ZoneId = sConfigMgr->GetIntDefault("BotWorld.Zone", _config.ZoneId);
    _config.CenterX = sConfigMgr->GetFloatDefault("BotWorld.CenterX", _config.CenterX);
    _config.CenterY = sConfigMgr->GetFloatDefault("BotWorld.CenterY", _config.CenterY);
    _config.CenterZ = sConfigMgr->GetFloatDefault("BotWorld.CenterZ", _config.CenterZ);
    _config.Radius = sConfigMgr->GetFloatDefault("BotWorld.Radius", _config.Radius);
    _config.MinLevel = uint8(sConfigMgr->GetIntDefault("BotWorld.MinLevel", _config.MinLevel));
    _config.MaxLevel = uint8(sConfigMgr->GetIntDefault("BotWorld.MaxLevel", _config.MaxLevel));
    _config.AllowCombat = sConfigMgr->GetBoolDefault("BotWorld.AllowCombat", _config.AllowCombat);
    _config.EnableProgression = sConfigMgr->GetBoolDefault("BotProgression.Enable", _config.EnableProgression);
    _config.AllowQuesting = sConfigMgr->GetBoolDefault("BotProgression.AllowQuesting", sConfigMgr->GetBoolDefault("BotWorld.AllowQuesting", _config.AllowQuesting));
    _config.RecordDecisions = sConfigMgr->GetBoolDefault("BotExperiment.RecordDecisions", _config.RecordDecisions);
    _config.RecordPerception = sConfigMgr->GetBoolDefault("BotExperiment.RecordPerception", _config.RecordPerception);
    _config.SmartSampling = sConfigMgr->GetBoolDefault("BotExperiment.SmartSampling", _config.SmartSampling);
    _config.NormalDecisionSampleRate = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotExperiment.NormalDecisionSampleRate", _config.NormalDecisionSampleRate));
    _config.BrainVersion = sConfigMgr->GetStringDefault("BotExperiment.BrainVersion", _config.BrainVersion);

    _bots.clear();
    _failedSpawnGuids.clear();
    _metrics = BotWorldStatus();
    _metrics.Active = true;
    _metrics.Name = _config.Name;
    _metrics.TargetBots = _config.TargetPopulation;
    _elapsedMs = 0;
    _active = true;

    RecordRunStart();
    EnsurePopulation();
    return _active;
}

void BotWorldPopulationMgr::Stop()
{
    if (!_active)
        return;

    for (WorldBotState const& state : _bots)
    {
        RecordActivityStop(state, GetBot(state));
        sBotMgr->RemoveWorldBot(state.Guid);
    }

    RecordRunStop();
    _bots.clear();
    _active = false;
}

void BotWorldPopulationMgr::Update(uint32 diff)
{
    if (!_active)
        return;

    _elapsedMs += diff;
    EnsurePopulation();

    for (auto itr = _bots.begin(); itr != _bots.end();)
    {
        if (!GetBot(*itr))
        {
            itr = _bots.erase(itr);
            continue;
        }

        UpdateBot(*itr, diff);
        ++itr;
    }
}

void BotWorldPopulationMgr::EnsurePopulation()
{
    uint32 attempts = 0;
    uint32 maxAttempts = std::max<uint32>(1, _config.TargetPopulation * 2);
    while (_active && _bots.size() < _config.TargetPopulation && attempts < maxAttempts)
    {
        ++attempts;
        uint32 candidateGuid = SelectPoolCandidateGuid();
        if (!candidateGuid)
            break;

        float angle = frand(0.0f, 2.0f * float(M_PI));
        float dist = frand(0.0f, _config.Radius * 0.35f);
        float x = _config.CenterX + std::cos(angle) * dist;
        float y = _config.CenterY + std::sin(angle) * dist;
        Player* bot = sBotMgr->SpawnWorldBot("any", std::to_string(candidateGuid), _config.MapId, x, y, _config.CenterZ, angle);
        if (!bot)
        {
            _failedSpawnGuids.insert(candidateGuid);
            continue;
        }

        WorldBotState state;
        state.Guid = bot->GetGUID();
        state.DecisionTimer = urand(0, sConfigMgr->GetIntDefault("BotWorld.DecisionTickMs", 3000));
        state.LastX = bot->GetPositionX();
        state.LastY = bot->GetPositionY();
        state.LastZ = bot->GetPositionZ();
        _bots.push_back(state);
        _metrics.ActiveBots = uint32(_bots.size());

        RecordActivityStart(_bots.back(), bot);
        BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
        BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "idle", &power, stage);
        RecordEvent(_bots.back(), bot, "bot_spawned", nullptr, "ok", raw.c_str(), semantic.c_str());
    }
}

void BotWorldPopulationMgr::UpdateBot(WorldBotState& state, uint32 diff)
{
    Player* bot = GetBot(state);
    if (!bot)
        return;

    if (!bot->IsAlive())
    {
        state.DeadTimer += diff;
        if (state.DeadTimer == diff)
        {
            ++_metrics.Deaths;
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "corpse_recovery");
            RecordEvent(state, bot, "death", nullptr, "dead", raw.c_str(), semantic.c_str(), 0.0f, _metrics.Deaths);
        }

        if (state.DeadTimer >= 5000)
        {
            bot->ResurrectPlayer(0.7f, false);
            bot->TeleportTo(_config.MapId, _config.CenterX, _config.CenterY, _config.CenterZ, bot->GetOrientation());
            state.DeadTimer = 0;
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "corpse_recovery");
            RecordEvent(state, bot, "resurrected", nullptr, "ok", raw.c_str(), semantic.c_str());
        }
        return;
    }
    state.DeadTimer = 0;

    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
    std::vector<BotActivityScore> activityScores = _config.EnableProgression
        ? BotLongTermProgressionBrain::ScoreActivities(bot, power, stage, _config.AllowQuesting, _config.AllowCombat)
        : std::vector<BotActivityScore>(1, BotActivityScore());
    BotActivityScore chosenActivity = BotLongTermProgressionBrain::ChooseActivity(activityScores);
    state.ActivityType = BotLongTermProgressionBrain::ToString(chosenActivity.Activity);
    state.ProgressionStage = BotLongTermProgressionBrain::ToString(stage);

    float moved = Distance2d(bot->GetPositionX(), bot->GetPositionY(), state.LastX, state.LastY);
    bool moving = bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
    if (moving && moved < 0.2f)
        state.StuckTimer += diff;
    else
        state.StuckTimer = 0;
    state.LastX = bot->GetPositionX();
    state.LastY = bot->GetPositionY();
    state.LastZ = bot->GetPositionZ();

    if (state.StuckTimer >= 6000)
    {
        ++_metrics.StuckEvents;
        Position pos = bot->GetFirstCollisionPosition(4.0f, frand(0.0f, 2.0f * float(M_PI)));
        bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        bot->GetMotionMaster()->MovePoint(0, pos, true);
        state.StuckTimer = 0;
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "stuck_recovery", &power, stage, chosenActivity.Activity);
        RecordEvent(state, bot, "stuck_detected", nullptr, "repath", raw.c_str(), semantic.c_str(), 1.0f, _metrics.StuckEvents);
        RecordDecision(state, bot, "stuck_recovery", "unstuck", nullptr, raw.c_str(), semantic.c_str(), activityScores, chosenActivity, power, true, true);
        return;
    }

    if (state.DecisionTimer > diff)
    {
        state.DecisionTimer -= diff;
        return;
    }
    state.DecisionTimer = std::max<uint32>(500, sConfigMgr->GetIntDefault("BotWorld.DecisionTickMs", 3000));

    Unit* target = state.TargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, state.TargetGuid);
    if (!target)
        target = bot->GetVictim();

    uint32 maxHealth = bot->GetMaxHealth();
    float hpPct = maxHealth ? float(bot->GetHealth()) / float(maxHealth) : 1.0f;
    std::string situation = bot->IsInCombat() ? "open_world_combat" : "travel";
    std::string action = "wander";
    QuestActionResult questAction;

    if (hpPct < 0.35f && !bot->IsInCombat())
    {
        bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        bot->GetMotionMaster()->MoveIdle();
        state.RestTimer += state.DecisionTimer;
        if (state.RestTimer >= 3000)
        {
            bot->SetFullHealth();
            bot->SetFullPower(bot->GetPowerType());
            state.RestTimer = 0;
        }
        situation = "idle";
        action = "rest";
    }
    else if (chosenActivity.Activity == BotProgressionActivity::VendorRepairTrain)
    {
        bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        bot->GetMotionMaster()->MoveIdle();
        situation = "vendor_repair_train";
        action = "vendor_repair_train";
    }
    else if (_config.AllowQuesting
        && (chosenActivity.Activity == BotProgressionActivity::Questing || [&]() { QuestObjectivePlan activePlan; return FindActiveQuestObjective(bot, activePlan); }())
        && [&]() { questAction = TryQuesting(state, bot, power, stage, chosenActivity.Activity); return questAction.Handled; }())
    {
        situation = questAction.Situation;
        action = questAction.Action;
        target = questAction.Target;
    }
    else if (target && target->IsAlive())
    {
        state.TargetGuid = target->GetGUID();
        BotActionExecutor executor;
        executor.Pull(bot, target);
        uint32 spellId = SelectCombatSpell(bot, target);
        situation = "open_world_combat";
        action = spellId ? "cast_combat_spell" : "attack";
        if (spellId && TryCastCombatSpell(bot, target, spellId))
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, chosenActivity.Activity);
            RecordEvent(state, bot, "spell_cast", target, "ok", raw.c_str(), semantic.c_str(), 0.0f, 0, spellId);
        }
        if (!state.WasInCombat)
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, chosenActivity.Activity);
            RecordEvent(state, bot, "combat_started", target, "ok", raw.c_str(), semantic.c_str());
        }
        state.WasInCombat = true;
    }
    else if (target && !target->IsAlive())
    {
        BotActionExecutor executor;
        BotActionResult result = executor.Loot(bot, target);
        ++_metrics.Kills;
        situation = "open_world_combat";
        action = "loot";
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, chosenActivity.Activity);
        RecordEvent(state, bot, "mob_killed", target, "ok", raw.c_str(), semantic.c_str(), 0.0f, _metrics.Kills);
        RecordEvent(state, bot, "loot_received", target, ToString(result), raw.c_str(), semantic.c_str());
        RecordQuestObjectiveProgressForTarget(state, bot, target, raw.c_str(), semantic.c_str());
        BotGearUpgradeEvaluation gear = BotLongTermProgressionBrain::EvaluateGearUpgrade(bot);
        RecordGearEvaluation(state, bot, gear, raw.c_str(), semantic.c_str());
        state.TargetGuid.Clear();
        state.WasInCombat = false;
    }
    else if (_config.AllowCombat && (target = SelectSafeTarget(bot)))
    {
        BotActionExecutor executor;
        BotActionResult result = executor.Pull(bot, target);
        state.TargetGuid = target->GetGUID();
        uint32 spellId = SelectCombatSpell(bot, target);
        situation = "open_world_combat";
        action = spellId ? "pull_and_cast" : "pull_safe_mob";
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, chosenActivity.Activity);
        RecordEvent(state, bot, "combat_started", target, ToString(result), raw.c_str(), semantic.c_str());
        if (spellId && TryCastCombatSpell(bot, target, spellId))
            RecordEvent(state, bot, "spell_cast", target, "ok", raw.c_str(), semantic.c_str(), 0.0f, 0, spellId);
        state.WasInCombat = true;
    }
    else
    {
        MoveToWanderPoint(bot, state);
        state.WasInCombat = false;
    }

    power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    std::string raw = BuildRawJson(bot, target);
    std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, chosenActivity.Activity);
    RecordDecision(state, bot, situation.c_str(), action.c_str(), target, raw.c_str(), semantic.c_str(), activityScores, chosenActivity, power, questAction.Failure, questAction.Rare);
}

Player* BotWorldPopulationMgr::GetBot(WorldBotState const& state) const
{
    Player* bot = sBotMgr->GetLoadedPlayer(state.Guid);
    if (!bot || !bot->IsInWorld())
        return nullptr;

    return bot;
}

uint32 BotWorldPopulationMgr::SelectPoolCandidateGuid() const
{
    std::ostringstream query;
    query << "SELECT cbp.guid FROM character_bot_pool cbp INNER JOIN characters c ON c.guid = cbp.guid "
          << "WHERE cbp.enabled = 1 AND cbp.in_use = 0 "
          << "AND c.level BETWEEN " << uint32(_config.MinLevel) << " AND " << uint32(_config.MaxLevel);

    if (!_failedSpawnGuids.empty())
    {
        query << " AND cbp.guid NOT IN (";
        bool first = true;
        for (uint32 guid : _failedSpawnGuids)
        {
            if (!first)
                query << ',';
            query << guid;
            first = false;
        }
        query << ")";
    }

    query << " ORDER BY cbp.guid LIMIT 1";

    if (QueryResult result = CharacterDatabase.Query(query.str().c_str()))
        return result->Fetch()[0].GetUInt32();

    return 0;
}

Unit* BotWorldPopulationMgr::SelectSafeTarget(Player* bot) const
{
    if (!bot)
        return nullptr;

    Unit* target = bot->SelectNearbyTarget(nullptr, 30.0f);
    if (!target || !target->IsAlive() || !bot->IsValidAttackTarget(target) || !bot->IsWithinLOSInMap(target))
        return nullptr;

    if (Creature* creature = target->ToCreature())
        if (creature->isElite())
            return nullptr;

    int32 levelDelta = int32(target->getLevel()) - int32(bot->getLevel());
    if (levelDelta > 1)
        return nullptr;

    if (target->GetExactDist(bot) > 25.0f)
        return nullptr;

    return target;
}

Unit* BotWorldPopulationMgr::SelectQuestObjectiveTarget(Player* bot, QuestObjectivePlan const& plan) const
{
    if (!bot || plan.IsGameObject)
        return nullptr;

    if (plan.IsItemObjective && plan.ItemId)
    {
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 70.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 70.0f);

        Creature* best = nullptr;
        float bestDist = 0.0f;
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!creature || !creature->IsAlive() || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
                continue;

            std::vector<uint32> const* questItems = sObjectMgr->GetCreatureQuestItemList(creature->GetEntry());
            if (!questItems || std::find(questItems->begin(), questItems->end(), plan.ItemId) == questItems->end())
                continue;

            if (creature->isElite())
                continue;
            if (int32(creature->getLevel()) - int32(bot->getLevel()) > 1)
                continue;

            float dist = bot->GetExactDist(creature);
            if (!best || dist < bestDist)
            {
                best = creature;
                bestDist = dist;
            }
        }

        if (best)
            return best;
    }

    if (!plan.RequiredEntry)
        return SelectSafeTarget(bot);

    std::vector<Creature*> creatures;
    bot->GetCreatureListWithEntryInGrid(creatures, uint32(plan.RequiredEntry), 60.0f);
    Creature* best = nullptr;
    float bestDist = 0.0f;
    for (Creature* creature : creatures)
    {
        if (!creature || !creature->IsAlive() || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
            continue;
        if (creature->isElite())
            continue;
        if (int32(creature->getLevel()) - int32(bot->getLevel()) > 1)
            continue;

        float dist = bot->GetExactDist(creature);
        if (!best || dist < bestDist)
        {
            best = creature;
            bestDist = dist;
        }
    }

    return best;
}

WorldObject* BotWorldPopulationMgr::SelectQuestGiver(Player* bot, bool completeOnly, uint32* questId) const
{
    if (questId)
        *questId = 0;
    if (!bot)
        return nullptr;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 80.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 80.0f);

    WorldObject* best = nullptr;
    uint32 bestQuestId = 0;
    float bestScore = 0.0f;
    for (WorldObject* object : objects)
    {
        if (!object || (object->GetTypeId() != TYPEID_UNIT && object->GetTypeId() != TYPEID_GAMEOBJECT))
            continue;

        QuestRelationResult relations;
        if (Creature* creature = object->ToCreature())
        {
            if (!creature->IsAlive())
                continue;
            relations = completeOnly ? sObjectMgr->GetCreatureQuestInvolvedRelations(creature->GetEntry()) : sObjectMgr->GetCreatureQuestRelations(creature->GetEntry());
        }
        else if (GameObject* go = object->ToGameObject())
            relations = completeOnly ? sObjectMgr->GetGOQuestInvolvedRelations(go->GetEntry()) : sObjectMgr->GetGOQuestRelations(go->GetEntry());
        else
            continue;

        for (uint32 candidateQuestId : relations)
        {
            Quest const* quest = sObjectMgr->GetQuestTemplate(candidateQuestId);
            if (!quest)
                continue;

            if (completeOnly)
            {
                if (bot->GetQuestStatus(candidateQuestId) != QUEST_STATUS_COMPLETE || !bot->CanRewardQuest(quest, false))
                    continue;
            }
            else
            {
                if (!bot->CanTakeQuest(quest, false) || !bot->CanAddQuest(quest, false) || !HasSimpleSupportedObjective(quest))
                    continue;
            }

            float dist = bot->GetExactDist(object);
            float score = (completeOnly ? 1000.0f : 100.0f) - dist;
            if (!best || score > bestScore)
            {
                best = object;
                bestQuestId = candidateQuestId;
                bestScore = score;
            }
        }
    }

    if (questId)
        *questId = bestQuestId;
    return best;
}

WorldObject* BotWorldPopulationMgr::SelectQuestGameObject(Player* bot, QuestObjectivePlan const& plan) const
{
    if (!bot || (!plan.IsGameObject && !plan.IsItemObjective))
        return nullptr;

    if (plan.IsItemObjective && plan.ItemId)
    {
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 70.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 70.0f);

        GameObject* best = nullptr;
        float bestDist = 0.0f;
        for (WorldObject* object : objects)
        {
            GameObject* go = object ? object->ToGameObject() : nullptr;
            if (!go || !bot->IsInPhase(go))
                continue;

            std::vector<uint32> const* questItems = sObjectMgr->GetGameObjectQuestItemList(go->GetEntry());
            if (!questItems || std::find(questItems->begin(), questItems->end(), plan.ItemId) == questItems->end())
                continue;

            float dist = bot->GetExactDist(go);
            if (!best || dist < bestDist)
            {
                best = go;
                bestDist = dist;
            }
        }

        if (best)
            return best;
    }

    if (!plan.IsGameObject || plan.RequiredEntry >= 0)
        return nullptr;

    std::vector<GameObject*> gameObjects;
    bot->GetGameObjectListWithEntryInGrid(gameObjects, uint32(-plan.RequiredEntry), 70.0f);
    GameObject* best = nullptr;
    float bestDist = 0.0f;
    for (GameObject* go : gameObjects)
    {
        if (!go || !bot->IsInPhase(go))
            continue;

        float dist = bot->GetExactDist(go);
        if (!best || dist < bestDist)
        {
            best = go;
            bestDist = dist;
        }
    }

    return best;
}

bool BotWorldPopulationMgr::FindActiveQuestObjective(Player* bot, QuestObjectivePlan& plan) const
{
    if (!bot)
        return false;

    for (auto const& questStatus : bot->getQuestStatusMap())
    {
        if (questStatus.second.Status != QUEST_STATUS_INCOMPLETE)
            continue;

        Quest const* quest = sObjectMgr->GetQuestTemplate(questStatus.first);
        if (!quest || !HasSimpleSupportedObjective(quest))
            continue;

        for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
        {
            int32 required = quest->RequiredNpcOrGo[i];
            uint32 requiredCount = quest->RequiredNpcOrGoCount[i];
            if (!required || !requiredCount || questStatus.second.CreatureOrGOCount[i] >= requiredCount)
                continue;

            plan.QuestId = quest->GetQuestId();
            plan.RequiredEntry = required;
            plan.RequiredCount = requiredCount;
            plan.CurrentCount = questStatus.second.CreatureOrGOCount[i];
            plan.IsGameObject = required < 0;
            return true;
        }

        for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
        {
            uint32 requiredItem = quest->RequiredItemId[i];
            uint32 requiredCount = quest->RequiredItemCount[i];
            if (!requiredItem || !requiredCount || questStatus.second.ItemCount[i] >= requiredCount)
                continue;

            plan.QuestId = quest->GetQuestId();
            plan.RequiredCount = requiredCount;
            plan.CurrentCount = questStatus.second.ItemCount[i];
            plan.IsItemObjective = true;
            plan.ItemId = requiredItem;
            return true;
        }
    }

    return false;
}

bool BotWorldPopulationMgr::HasSimpleSupportedObjective(Quest const* quest) const
{
    if (!quest)
        return false;

    if (quest->IsTurnIn())
        return true;

    for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
        if (quest->RequiredNpcOrGo[i] && quest->RequiredNpcOrGoCount[i])
            return true;

    for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
        if (quest->RequiredItemId[i] && quest->RequiredItemCount[i])
            return true;

    return false;
}

uint32 BotWorldPopulationMgr::ChooseQuestReward(Player* bot, Quest const* quest, uint32* rewardItemId) const
{
    if (rewardItemId)
        *rewardItemId = 0;
    if (!bot || !quest || !quest->GetRewChoiceItemsCount())
        return 0;

    uint32 bestReward = 0;
    float bestScore = -1.0f;
    for (uint32 i = 0; i < quest->GetRewChoiceItemsCount(); ++i)
    {
        uint32 itemId = quest->RewardChoiceItemId[i];
        ItemTemplate const* proto = itemId ? sObjectMgr->GetItemTemplate(itemId) : nullptr;
        float score = BotLongTermProgressionBrain::ScoreItemForRole(bot, proto);
        if (score > bestScore)
        {
            bestReward = i;
            bestScore = score;
            if (rewardItemId)
                *rewardItemId = itemId;
        }
    }

    return bestReward;
}

BotWorldPopulationMgr::QuestActionResult BotWorldPopulationMgr::TryQuesting(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity)
{
    QuestActionResult result;
    if (!bot || bot->IsInCombat())
        return result;

    uint32 questId = 0;
    if (WorldObject* turnIn = SelectQuestGiver(bot, true, &questId))
    {
        Quest const* quest = sObjectMgr->GetQuestTemplate(questId);
        if (!quest)
            return result;

        result.Handled = true;
        result.Situation = "quest_turn_in";
        result.Action = "move_to_quest_complete";
        result.QuestId = questId;

        if (!bot->IsWithinDistInMap(turnIn, INTERACTION_DISTANCE))
        {
            bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            bot->GetMotionMaster()->MovePoint(0, turnIn->GetPositionX(), turnIn->GetPositionY(), turnIn->GetPositionZ(), true);
            return result;
        }

        uint32 rewardItemId = 0;
        uint32 rewardChoice = ChooseQuestReward(bot, quest, &rewardItemId);
        result.RewardChoice = rewardChoice;
        result.RewardItemId = rewardItemId;
        if (!bot->CanRewardQuest(quest, rewardChoice, false))
        {
            result.Failure = true;
            result.Rare = true;
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "quest_turn_in_failed", &power, stage, activity);
            RecordQuestEvent(state, bot, "objective_failed", questId, nullptr, "reward_blocked", raw.c_str(), semantic.c_str(), 0, rewardItemId);
            RecordQuestReplay(state, bot, "quest_failure", questId, raw.c_str(), semantic.c_str(), "{\"action\":\"reward_quest\"}", "{\"reason\":\"reward_blocked\"}");
            return result;
        }

        float powerBefore = power.Total;
        uint8 levelBefore = bot->getLevel();
        uint64 moneyBefore = bot->GetMoney();
        bot->RewardQuest(quest, rewardChoice, turnIn, true);
        ++_metrics.QuestsCompleted;
        state.LastQuestCompletedCount = _metrics.QuestsCompleted;
        uint32 elapsed = state.QuestStartTime ? (_elapsedMs / 1000) - state.QuestStartTime : 0;
        uint32 deaths = _metrics.Deaths >= state.QuestStartDeaths ? _metrics.Deaths - state.QuestStartDeaths : 0;
        BotRolePowerBreakdown powerAfter = BotLongTermProgressionBrain::CalculateRolePower(bot);
        std::ostringstream context;
        context << "{\"reward_choice\":" << rewardChoice
                << ",\"reward_item_id\":" << rewardItemId
                << ",\"time_to_complete_sec\":" << elapsed
                << ",\"death_count\":" << deaths
                << ",\"level_delta\":" << int32(bot->getLevel()) - int32(levelBefore)
                << ",\"gold_delta\":" << int64(bot->GetMoney()) - int64(moneyBefore)
                << ",\"power_gain\":" << (powerAfter.Total - powerBefore) << "}";

        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "quest_completed", &powerAfter, stage, activity);
        RecordQuestEvent(state, bot, "reward_chosen", questId, nullptr, "ok", raw.c_str(), semantic.c_str(), rewardChoice, rewardItemId, context.str().c_str());
        RecordQuestEvent(state, bot, "quest_completed", questId, nullptr, "ok", raw.c_str(), semantic.c_str(), elapsed, rewardItemId, context.str().c_str());
        result.Action = "complete_quest";
        return result;
    }

    QuestObjectivePlan plan;
    if (FindActiveQuestObjective(bot, plan))
    {
        result.Handled = true;
        result.Situation = "quest_objective";
        result.QuestId = plan.QuestId;

        WorldObject* questObject = SelectQuestGameObject(bot, plan);
        if (plan.IsGameObject || questObject)
        {
            result.Action = plan.IsItemObjective ? "loot_quest_object" : "use_quest_object";
            if (!questObject)
            {
                result.Failure = true;
                std::string raw = BuildRawJson(bot, nullptr);
                std::string semantic = BuildSemanticJson(bot, nullptr, "quest_objective_failed", &power, stage, activity);
                RecordQuestEvent(state, bot, "objective_failed", plan.QuestId, nullptr, "object_not_found", raw.c_str(), semantic.c_str(), plan.CurrentCount);
                RecordQuestReplay(state, bot, "quest_failure", plan.QuestId, raw.c_str(), semantic.c_str(), "{\"action\":\"use_quest_object\"}", "{\"reason\":\"object_not_found\"}");
                return result;
            }

            if (!bot->IsWithinDistInMap(questObject, INTERACTION_DISTANCE))
            {
                bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                bot->GetMotionMaster()->MovePoint(0, questObject->GetPositionX(), questObject->GetPositionY(), questObject->GetPositionZ(), true);
                return result;
            }

            if (GameObject* go = questObject->ToGameObject())
            {
                go->Use(bot);
                if (plan.IsItemObjective)
                    bot->SendLoot(go->GetGUID(), LOOT_CORPSE);
            }
            if (bot->CanCompleteQuest(plan.QuestId))
                bot->CompleteQuest(plan.QuestId);
            ++_metrics.QuestObjectiveProgress;
            state.LastQuestObjectiveProgress = _metrics.QuestObjectiveProgress;
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "quest_objective", &power, stage, activity);
            RecordQuestEvent(state, bot, "objective_progress", plan.QuestId, nullptr, plan.IsItemObjective ? "loot_object" : "use_object", raw.c_str(), semantic.c_str(), plan.CurrentCount + 1, plan.ItemId);
            return result;
        }

        Unit* objectiveTarget = SelectQuestObjectiveTarget(bot, plan);
        result.Target = objectiveTarget;
        result.Action = plan.IsItemObjective ? "collect_quest_item" : "kill_quest_mob";
        if (!objectiveTarget)
        {
            MoveToWanderPoint(bot, state);
            result.Action = plan.IsItemObjective ? "search_collect_mob" : "search_quest_mob";
            return result;
        }

        BotActionExecutor executor;
        BotActionResult pull = executor.Pull(bot, objectiveTarget);
        uint32 spellId = SelectCombatSpell(bot, objectiveTarget);
        if (spellId)
            TryCastCombatSpell(bot, objectiveTarget, spellId);
        if (pull != BotActionResult::Ok)
        {
            result.Failure = true;
            std::string raw = BuildRawJson(bot, objectiveTarget);
            std::string semantic = BuildSemanticJson(bot, objectiveTarget, "quest_objective_failed", &power, stage, activity);
            RecordQuestEvent(state, bot, "objective_failed", plan.QuestId, objectiveTarget, ToString(pull), raw.c_str(), semantic.c_str(), plan.CurrentCount);
            RecordQuestReplay(state, bot, "quest_failure", plan.QuestId, raw.c_str(), semantic.c_str(), "{\"action\":\"pull_quest_target\"}", "{\"reason\":\"pull_failed\"}");
        }
        return result;
    }

    if (WorldObject* giver = SelectQuestGiver(bot, false, &questId))
    {
        Quest const* quest = sObjectMgr->GetQuestTemplate(questId);
        if (!quest)
            return result;

        result.Handled = true;
        result.Situation = "quest_pickup";
        result.Action = "move_to_quest_giver";
        result.QuestId = questId;
        if (!bot->IsWithinDistInMap(giver, INTERACTION_DISTANCE))
        {
            bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            bot->GetMotionMaster()->MovePoint(0, giver->GetPositionX(), giver->GetPositionY(), giver->GetPositionZ(), true);
            return result;
        }

        bot->AddQuestAndCheckCompletion(quest, giver);
        ++_metrics.QuestsAccepted;
        state.LastQuestId = questId;
        state.QuestStartTime = _elapsedMs / 1000;
        state.QuestStartDeaths = _metrics.Deaths;
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "quest_accepted", &power, stage, activity);
        RecordQuestEvent(state, bot, "quest_seen", questId, nullptr, "ok", raw.c_str(), semantic.c_str());
        RecordQuestEvent(state, bot, "quest_accepted", questId, nullptr, "ok", raw.c_str(), semantic.c_str(), _metrics.QuestsAccepted);
        result.Action = "accept_quest";
        return result;
    }

    return result;
}

uint32 BotWorldPopulationMgr::SelectCombatSpell(Player* bot, Unit* target) const
{
    if (!bot || !target || !target->IsAlive())
        return 0;

    uint8 playerClass = bot->getClass();
    uint32 candidates[4] = { 0, 0, 0, 0 };
    switch (playerClass)
    {
        case CLASS_MAGE:
            candidates[0] = 133;      // Fireball
            candidates[1] = 44614;    // Frostfire Bolt
            break;
        case CLASS_PRIEST:
            candidates[0] = 585;      // Smite
            break;
        case CLASS_WARLOCK:
            candidates[0] = 686;      // Shadow Bolt
            break;
        case CLASS_DRUID:
            candidates[0] = 5176;     // Wrath
            break;
        case CLASS_SHAMAN:
            candidates[0] = 403;      // Lightning Bolt
            break;
        case CLASS_PALADIN:
            candidates[0] = 20271;    // Judgement
            break;
        case CLASS_HUNTER:
            candidates[0] = 75;       // Auto Shot
            break;
        case CLASS_DEATH_KNIGHT:
            candidates[0] = 45477;    // Icy Touch
            candidates[1] = 45462;    // Plague Strike
            break;
        case CLASS_WARRIOR:
            candidates[0] = 78;       // Heroic Strike
            break;
        case CLASS_ROGUE:
            candidates[0] = 1752;     // Sinister Strike
            break;
        default:
            break;
    }

    for (uint32 spellId : candidates)
        if (spellId && bot->HasSpell(spellId))
            return spellId;

    return 0;
}

bool BotWorldPopulationMgr::TryCastCombatSpell(Player* bot, Unit* target, uint32 spellId) const
{
    if (!bot || !target || !spellId || !target->IsAlive() || !bot->IsValidAttackTarget(target))
        return false;

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo || !bot->IsWithinLOSInMap(target))
        return false;

    float maxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    if (!bot->IsWithinDistInMap(target, maxRange))
        return false;

    if (bot->HasUnitState(UNIT_STATE_CASTING) || bot->GetSpellHistory()->HasGlobalCooldown(spellInfo) || !bot->GetSpellHistory()->IsReady(spellInfo))
        return false;

    int32 powerCost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (powerCost > 0 && bot->GetPower(bot->GetPowerType()) < uint32(powerCost))
        return false;

    return bot->CastSpell(target, spellId, false) == SPELL_CAST_OK;
}

void BotWorldPopulationMgr::MoveToWanderPoint(Player* bot, WorldBotState& /*state*/)
{
    if (!bot)
        return;

    float fromCenter = Distance2d(bot->GetPositionX(), bot->GetPositionY(), _config.CenterX, _config.CenterY);
    float angle = fromCenter > _config.Radius ? bot->GetAngle(_config.CenterX, _config.CenterY) : frand(0.0f, 2.0f * float(M_PI));
    float distance = frand(8.0f, 25.0f);
    Position pos = bot->GetFirstCollisionPosition(distance, angle);
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MovePoint(0, pos, true);
}

void BotWorldPopulationMgr::RecordRunStart()
{
    std::string escapedName = _config.Name;
    std::string escapedConfig = BuildConfigJson();
    std::string escapedBrain = _config.BrainVersion;
    CharacterDatabase.EscapeString(escapedName);
    CharacterDatabase.EscapeString(escapedConfig);
    CharacterDatabase.EscapeString(escapedBrain);
    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_runs (experiment_name, config_json, brain_version, status, started_at) VALUES ('%s', '%s', '%s', 'running', NOW())",
        escapedName.c_str(), escapedConfig.c_str(), escapedBrain.c_str());
    _runId = ReadLastInsertId();
    _experimentId = _runId;
    _metrics.ExperimentId = _experimentId;
    _metrics.RunId = _runId;
}

void BotWorldPopulationMgr::RecordRunStop()
{
    std::string summary = GetSummaryJson();
    CharacterDatabase.EscapeString(summary);
    CharacterDatabase.DirectPExecute("UPDATE experiment_bot_runs SET status = 'stopped', ended_at = NOW(), summary_json = '%s' WHERE id = " UI64FMTD, summary.c_str(), _runId);
}

void BotWorldPopulationMgr::RecordActivityStart(WorldBotState& state, Player* bot)
{
    if (!_runId || !bot)
        return;

    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
    std::vector<BotActivityScore> activityScores = _config.EnableProgression
        ? BotLongTermProgressionBrain::ScoreActivities(bot, power, stage, _config.AllowQuesting, _config.AllowCombat)
        : std::vector<BotActivityScore>(1, BotActivityScore());
    BotActivityScore chosenActivity = BotLongTermProgressionBrain::ChooseActivity(activityScores);
    state.ActivityStartPower = power.Total;
    state.ActivityStartGold = bot->GetMoney();
    state.ActivityStartDeaths = _metrics.Deaths;
    state.ActivityType = BotLongTermProgressionBrain::ToString(chosenActivity.Activity);
    state.ProgressionStage = BotLongTermProgressionBrain::ToString(stage);

    std::string config = BuildConfigJson();
    std::string brain = _config.BrainVersion;
    std::string activity = state.ActivityType;
    CharacterDatabase.EscapeString(config);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(activity);
    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_activities (experiment_id, run_id, bot_guid, brain_version, activity_type, start_power_score, config_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', '%s', %f, '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), activity.c_str(), state.ActivityStartPower, config.c_str());
    state.ActivityId = ReadLastInsertId();
}

void BotWorldPopulationMgr::RecordActivityStop(WorldBotState const& state, Player* bot)
{
    if (!_runId || !state.ActivityId)
        return;

    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    float endPower = bot ? power.Total : state.ActivityStartPower;
    float powerDelta = endPower - state.ActivityStartPower;
    int64 goldDelta = bot ? int64(bot->GetMoney()) - int64(state.ActivityStartGold) : 0;
    uint32 deaths = _metrics.Deaths >= state.ActivityStartDeaths ? _metrics.Deaths - state.ActivityStartDeaths : 0;
    std::string summary = GetSummaryJson();
    CharacterDatabase.EscapeString(summary);
    CharacterDatabase.DirectPExecute("UPDATE experiment_bot_activities SET ended_at = NOW(), end_power_score = %f, power_delta = %f, gold_delta = " SI64FMTD ", completed = 1, deaths = %u, summary_json = '%s' WHERE id = " UI64FMTD,
        endPower, powerDelta, goldDelta, deaths, summary.c_str(), state.ActivityId);
}

void BotWorldPopulationMgr::RecordGearEvaluation(WorldBotState const& state, Player* bot, BotGearUpgradeEvaluation const& evaluation, char const* rawJson, char const* semanticJson)
{
    if (!_runId || !bot || !evaluation.Upgrade)
        return;

    ++_metrics.GearUpgrades;

    std::ostringstream context;
    context << "{\"item_id\":" << evaluation.ItemId
            << ",\"bag\":" << uint32(evaluation.Bag)
            << ",\"slot\":" << uint32(evaluation.Slot)
            << ",\"inventory_type\":" << uint32(evaluation.InventoryType)
            << ",\"quality\":" << uint32(evaluation.Quality)
            << ",\"candidate_score\":" << evaluation.CandidateScore
            << ",\"equipped_score\":" << evaluation.EquippedScore
            << ",\"role_power_delta\":" << evaluation.PowerDelta
            << ",\"decision\":\"keep_upgrade_candidate\"}";

    RecordEvent(state, bot, "gear_upgrade", nullptr, "evaluated", rawJson, semanticJson, evaluation.PowerDelta, evaluation.ItemId);

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string event = "gear_evaluated";
    std::string result = "upgrade_candidate";
    std::string brain = _config.BrainVersion;
    std::string contextJson = context.str();
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(result);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(contextJson);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, map_id, zone_id, area_id, x, y, z, level, event_type, item_id, result, value_float, value_int, raw_json, semantic_json, context_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %u, %f, %f, %f, %u, '%s', %u, '%s', %f, %u, '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), evaluation.ItemId,
        result.c_str(), evaluation.PowerDelta, evaluation.ItemId, raw.c_str(), semantic.c_str(), contextJson.c_str());
}

void BotWorldPopulationMgr::RecordQuestObjectiveProgressForTarget(WorldBotState& state, Player* bot, Unit const* target, char const* rawJson, char const* semanticJson)
{
    if (!_runId || !bot || !target)
        return;

    Creature const* creature = target->ToCreature();
    if (!creature)
        return;

    uint32 entry = creature->GetEntry();
    for (auto const& questStatus : bot->getQuestStatusMap())
    {
        if (questStatus.second.Status != QUEST_STATUS_INCOMPLETE && questStatus.second.Status != QUEST_STATUS_COMPLETE)
            continue;

        Quest const* quest = sObjectMgr->GetQuestTemplate(questStatus.first);
        if (!quest)
            continue;

        for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
        {
            if (quest->RequiredNpcOrGo[i] != int32(entry) || !quest->RequiredNpcOrGoCount[i])
                continue;

            ++_metrics.QuestObjectiveProgress;
            state.LastQuestObjectiveProgress = _metrics.QuestObjectiveProgress;
            uint32 current = questStatus.second.CreatureOrGOCount[i];
            std::ostringstream context;
            context << "{\"required_entry\":" << entry
                    << ",\"required_count\":" << quest->RequiredNpcOrGoCount[i]
                    << ",\"current_count\":" << current
                    << ",\"objective_index\":" << uint32(i) << "}";
            RecordQuestEvent(state, bot, "objective_progress", quest->GetQuestId(), target, "kill", rawJson, semanticJson, current, 0, context.str().c_str());

            if (bot->CanCompleteQuest(quest->GetQuestId()))
                bot->CompleteQuest(quest->GetQuestId());
        }
    }
}

void BotWorldPopulationMgr::RecordQuestEvent(WorldBotState const& state, Player* bot, char const* eventType, uint32 questId, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, uint32 valueInt, uint32 itemId, char const* contextJson)
{
    if (!_runId || !bot)
        return;

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string event = eventType ? eventType : "quest_event";
    std::string res = result ? result : "";
    std::string brain = _config.BrainVersion;
    std::string context = contextJson ? contextJson : "{}";
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(res);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(context);

    uint32 targetEntry = 0;
    uint64 targetGuid = 0;
    if (target)
    {
        targetGuid = target->GetGUID().GetCounter();
        if (Creature const* creature = target->ToCreature())
            targetEntry = creature->GetEntry();
    }

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, map_id, zone_id, area_id, x, y, z, level, event_type, target_guid, target_entry, quest_id, item_id, result, value_int, raw_json, semantic_json, context_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %u, %f, %f, %f, %u, '%s', " UI64FMTD ", %u, %u, %u, '%s', %u, '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), targetGuid, targetEntry,
        questId, itemId, res.c_str(), valueInt, raw.c_str(), semantic.c_str(), context.c_str());
}

void BotWorldPopulationMgr::RecordQuestReplay(WorldBotState const& state, Player* bot, char const* replayType, uint32 questId, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson)
{
    if (!_runId || !bot)
        return;

    std::ostringstream botSnapshot;
    botSnapshot << "{\"guid\":" << bot->GetGUID().GetCounter()
                << ",\"level\":" << uint32(bot->getLevel())
                << ",\"class_id\":" << uint32(bot->getClass())
                << ",\"hp\":" << bot->GetHealth()
                << ",\"max_hp\":" << bot->GetMaxHealth()
                << ",\"quest_id\":" << questId
                << ",\"activity\":\"" << JsonEscape(state.ActivityType) << "\"}";

    std::ostringstream worldSnapshot;
    worldSnapshot << "{\"map_id\":" << bot->GetMapId()
                  << ",\"zone_id\":" << bot->GetZoneId()
                  << ",\"area_id\":" << bot->GetAreaId()
                  << ",\"x\":" << bot->GetPositionX()
                  << ",\"y\":" << bot->GetPositionY()
                  << ",\"z\":" << bot->GetPositionZ()
                  << ",\"o\":" << bot->GetOrientation()
                  << ",\"quest_id\":" << questId << "}";

    std::string type = replayType ? replayType : "quest_failure";
    std::string botJson = botSnapshot.str();
    std::string worldJson = worldSnapshot.str();
    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string action = actionJson ? actionJson : "{}";
    std::string failure = failureJson ? failureJson : "{}";
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(botJson);
    CharacterDatabase.EscapeString(worldJson);
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(action);
    CharacterDatabase.EscapeString(failure);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_replay_records (experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, bot_snapshot_json, world_snapshot_json, raw_state_json, semantic_state_json, chosen_action_json, failure_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %f, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), type.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), bot->GetOrientation(), botJson.c_str(), worldJson.c_str(), raw.c_str(), semantic.c_str(), action.c_str(), failure.c_str());
}

void BotWorldPopulationMgr::RecordEvent(WorldBotState const& state, Player* bot, char const* eventType, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, float valueFloat, uint32 valueInt, uint32 spellId)
{
    if (!_runId || !bot)
        return;

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string event = eventType ? eventType : "unknown";
    std::string res = result ? result : "";
    std::string brain = _config.BrainVersion;
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(res);
    CharacterDatabase.EscapeString(brain);
    uint32 targetEntry = 0;
    uint64 targetGuid = 0;
    if (target)
    {
        targetGuid = target->GetGUID().GetCounter();
        if (Creature const* creature = target->ToCreature())
            targetEntry = creature->GetEntry();
    }

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, map_id, zone_id, area_id, x, y, z, level, event_type, target_guid, target_entry, spell_id, result, value_float, value_int, raw_json, semantic_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %u, %f, %f, %f, %u, '%s', " UI64FMTD ", %u, %u, '%s', %f, %u, '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), targetGuid, targetEntry, spellId, res.c_str(), valueFloat, valueInt, raw.c_str(), semantic.c_str());
}

void BotWorldPopulationMgr::RecordDecision(WorldBotState& state, Player* bot, char const* situation, char const* action, Unit const* target, char const* rawJson, char const* semanticJson, std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, BotRolePowerBreakdown const& power, bool failure, bool rare)
{
    if (!_runId || !_config.RecordDecisions || !bot)
        return;

    ++state.Sequence;
    ++_metrics.Decisions;
    if (failure)
        ++_metrics.Failures;

    bool sampled = !_config.SmartSampling || failure || rare || (state.Sequence % _config.NormalDecisionSampleRate) == 0;
    if (!sampled)
        return;

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string candidateJson = BuildActivityCandidatesJson(activityScores);
    std::ostringstream chosen;
    chosen << "{\"action\":\"" << JsonEscape(action ? action : "wait") << "\"";
    if (target)
        chosen << ",\"target_guid\":" << target->GetGUID().GetCounter();
    chosen << ",\"activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(chosenActivity.Activity)) << "\""
           << ",\"activity_score\":" << chosenActivity.Score
           << ",\"expected_power_gain\":" << chosenActivity.ExpectedPowerGain;
    chosen << "}";
    std::ostringstream outcome;
    outcome << "{\"main_goal\":\"increase_character_power\""
            << ",\"current_stage\":\"" << JsonEscape(state.ProgressionStage) << "\""
            << ",\"chosen_activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(chosenActivity.Activity)) << "\""
            << ",\"expected_value\":" << chosenActivity.Score
            << ",\"role_power_score\":" << power.Total
            << ",\"power_delta\":" << (power.Total - state.ActivityStartPower)
            << "}";

    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    std::string chosenJson = chosen.str();
    std::string outcomeJson = outcome.str();
    std::string brain = _config.BrainVersion;
    CharacterDatabase.EscapeString(candidateJson);
    CharacterDatabase.EscapeString(chosenJson);
    CharacterDatabase.EscapeString(outcomeJson);
    CharacterDatabase.EscapeString(brain);
    std::string sit = situation ? situation : "idle";
    CharacterDatabase.EscapeString(sit);
    std::string currentActivity = BotLongTermProgressionBrain::ToString(chosenActivity.Activity);
    CharacterDatabase.EscapeString(currentActivity);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_decisions (experiment_id, run_id, bot_guid, brain_version, situation_type, current_activity, current_goal, map_id, zone_id, x, y, z, raw_state_json, semantic_state_json, candidate_actions_json, chosen_action_json, outcome_json, reward, is_failure, is_rare_state) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', '%s', '%s', 'increase_character_power', %u, %u, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', %f, %u, %u)",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), sit.c_str(), currentActivity.c_str(), bot->GetMapId(), bot->GetZoneId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), raw.c_str(), semantic.c_str(), candidateJson.c_str(), chosenJson.c_str(),
        outcomeJson.c_str(), failure ? -1.0f : chosenActivity.Score, failure ? 1 : 0, rare ? 1 : 0);
}

std::string BotWorldPopulationMgr::BuildRawJson(Player* bot, Unit const* target) const
{
    std::ostringstream json;
    json << "{\"bot_guid\":" << (bot ? bot->GetGUID().GetCounter() : 0)
         << ",\"map_id\":" << (bot ? bot->GetMapId() : 0)
         << ",\"zone_id\":" << (bot ? bot->GetZoneId() : 0)
         << ",\"area_id\":" << (bot ? bot->GetAreaId() : 0)
         << ",\"level\":" << (bot ? uint32(bot->getLevel()) : 0)
         << ",\"hp_pct\":";
    if (bot && bot->GetMaxHealth())
        json << (float(bot->GetHealth()) / float(bot->GetMaxHealth()));
    else
        json << 0.0f;
    json << ",\"in_combat\":" << (bot && bot->IsInCombat() ? "true" : "false")
         << ",\"moving\":" << (bot && (bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING)) ? "true" : "false")
         << ",\"x\":" << (bot ? bot->GetPositionX() : 0.0f)
         << ",\"y\":" << (bot ? bot->GetPositionY() : 0.0f)
         << ",\"z\":" << (bot ? bot->GetPositionZ() : 0.0f)
         << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
         << ",\"target_entry\":";
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        json << creature->GetEntry();
    else
        json << 0;
    json << ",\"target_level\":" << (target ? uint32(target->getLevel()) : 0)
         << ",\"target_alive\":" << (target && target->IsAlive() ? "true" : "false") << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildSemanticJson(Player* bot, Unit const* target, char const* situation, BotRolePowerBreakdown const* power, BotProgressionStage stage, BotProgressionActivity activity) const
{
    float hpPct = 1.0f;
    if (bot && bot->GetMaxHealth())
        hpPct = float(bot->GetHealth()) / float(bot->GetMaxHealth());

    bool elite = false;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        elite = creature->isElite();

    BotRolePowerBreakdown localPower;
    if (!power && bot)
    {
        localPower = BotLongTermProgressionBrain::CalculateRolePower(bot);
        power = &localPower;
        stage = BotLongTermProgressionBrain::ClassifyStage(bot, *power);
    }

    std::ostringstream json;
    json << "{\"situation_type\":\"" << JsonEscape(situation ? situation : "idle") << "\""
         << ",\"role\":\"solo\""
         << ",\"activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(activity)) << "\""
         << ",\"progression\":{\"main_goal\":\"increase_character_power\""
         << ",\"stage\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(stage)) << "\""
         << ",\"role_power_score\":" << (power ? power->Total : 0.0f)
         << ",\"item_level_score\":" << (power ? power->ItemLevelScore : 0.0f)
         << ",\"role_stat_weight_score\":" << (power ? power->RoleStatWeightScore : 0.0f)
         << ",\"weapon_score\":" << (power ? power->WeaponScore : 0.0f)
         << ",\"trinket_score\":" << (power ? power->TrinketScore : 0.0f)
         << ",\"gold_utility_score\":" << (power ? power->GoldUtilityScore : 0.0f) << "}"
         << ",\"self\":{\"hp_pct\":" << hpPct
         << ",\"low_health\":" << (hpPct < 0.35f ? "true" : "false")
         << ",\"level\":" << (bot ? uint32(bot->getLevel()) : 0)
         << ",\"avg_item_level\":" << (bot ? bot->GetAverageItemLevel() : 0.0f)
         << ",\"free_bag_slots\":" << (bot ? bot->GetFreeInventorySpace() : 0)
         << ",\"gold\":" << (bot ? bot->GetMoney() : 0)
         << ",\"dead\":" << (bot && !bot->IsAlive() ? "true" : "false") << "}"
         << ",\"enemy\":{\"present\":" << (target ? "true" : "false")
         << ",\"elite\":" << (elite ? "true" : "false")
         << ",\"safe_open_world_target\":" << (target && !elite && bot && int32(target->getLevel()) <= int32(bot->getLevel()) + 1 ? "true" : "false") << "}"
         << ",\"objective\":{\"main_goal\":\"increase_character_power\",\"questing_allowed\":" << (_config.AllowQuesting ? "true" : "false") << "}}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildConfigJson() const
{
    std::ostringstream json;
    json << "{\"name\":\"" << JsonEscape(_config.Name)
         << "\",\"type\":\"bot_world_autonomy\""
         << ",\"population\":" << _config.TargetPopulation
         << ",\"map\":" << _config.MapId
         << ",\"zone\":" << _config.ZoneId
         << ",\"min_level\":" << uint32(_config.MinLevel)
         << ",\"max_level\":" << uint32(_config.MaxLevel)
         << ",\"allow_combat\":" << (_config.AllowCombat ? "true" : "false")
         << ",\"progression_enabled\":" << (_config.EnableProgression ? "true" : "false")
         << ",\"allow_questing\":" << (_config.AllowQuesting ? "true" : "false")
         << ",\"record_decisions\":" << (_config.RecordDecisions ? "true" : "false")
         << ",\"record_perception\":" << (_config.RecordPerception ? "true" : "false")
         << ",\"smart_sampling\":" << (_config.SmartSampling ? "true" : "false")
         << ",\"brain_version\":\"" << JsonEscape(_config.BrainVersion) << "\"}";
    return json.str();
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
             << ",\"score\":" << score.Score << "}";
    }
    json << "]";
    return json.str();
}

BotWorldStatus BotWorldPopulationMgr::GetStatus() const
{
    BotWorldStatus status = _metrics;
    status.Active = _active;
    status.ActiveBots = uint32(_bots.size());
    status.DurationSeconds = _elapsedMs / 1000;
    return status;
}

std::string BotWorldPopulationMgr::GetStatusJson() const
{
    BotWorldStatus status = GetStatus();
    std::ostringstream json;
    json << "{\"ok\":true,\"experiment\":\"" << JsonEscape(status.Name)
         << "\",\"run\":" << status.RunId
         << ",\"brain\":\"" << JsonEscape(_config.BrainVersion)
         << "\",\"active\":" << (status.Active ? "true" : "false")
         << ",\"bots\":" << status.ActiveBots
         << ",\"target_bots\":" << status.TargetBots
         << ",\"duration_seconds\":" << status.DurationSeconds
         << ",\"kills\":" << status.Kills
         << ",\"deaths\":" << status.Deaths
         << ",\"gear_upgrades\":" << status.GearUpgrades
         << ",\"quests_accepted\":" << status.QuestsAccepted
         << ",\"quests_completed\":" << status.QuestsCompleted
         << ",\"quest_objective_progress\":" << status.QuestObjectiveProgress
         << ",\"stuck\":" << status.StuckEvents
         << ",\"decisions\":" << status.Decisions
         << ",\"failures\":" << status.Failures
         << ",\"failure_reason\":null}";
    return json.str();
}

std::string BotWorldPopulationMgr::GetSummaryJson() const
{
    BotWorldStatus status = GetStatus();
    float hours = status.DurationSeconds ? float(status.DurationSeconds) / 3600.0f : 0.0f;
    std::ostringstream json;
    json << "{\"bots\":" << status.ActiveBots
         << ",\"target_bots\":" << status.TargetBots
         << ",\"duration_minutes\":" << (float(status.DurationSeconds) / 60.0f)
         << ",\"total_kills\":" << status.Kills
         << ",\"total_deaths\":" << status.Deaths
         << ",\"kills_per_hour\":" << (hours > 0.0f ? float(status.Kills) / hours : 0.0f)
         << ",\"deaths_per_hour\":" << (hours > 0.0f ? float(status.Deaths) / hours : 0.0f)
         << ",\"stuck_events\":" << status.StuckEvents
         << ",\"quests_accepted\":" << status.QuestsAccepted
         << ",\"quests_completed\":" << status.QuestsCompleted
         << ",\"quest_objective_progress\":" << status.QuestObjectiveProgress
         << ",\"gear_upgrades\":" << status.GearUpgrades
         << ",\"decisions\":" << status.Decisions
         << ",\"failures_recorded\":" << status.Failures << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::JsonEscape(std::string const& value)
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
