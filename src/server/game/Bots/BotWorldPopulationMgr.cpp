#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/BotMgr.h"
#include "CellImpl.h"
#include "Config.h"
#include "Corpse.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "GameObject.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "GroupReference.h"
#include "LFG.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "Random.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Creature.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <limits>
#include <regex>
#include <shared_mutex>
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

float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;

    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
}

std::string LowerCopy(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return char(std::tolower(c)); });
    return value;
}

bool ContainsInsensitive(std::string const& text, char const* needle)
{
    if (!needle || !*needle)
        return false;
    return LowerCopy(text).find(LowerCopy(needle)) != std::string::npos;
}

char const* ToString(BotWorldPopulationMgr::QuestObjectiveType type)
{
    switch (type)
    {
        case BotWorldPopulationMgr::QuestObjectiveType::Kill: return "kill";
        case BotWorldPopulationMgr::QuestObjectiveType::CollectItem: return "collect_item";
        case BotWorldPopulationMgr::QuestObjectiveType::InteractGameObject: return "interact_gameobject";
        case BotWorldPopulationMgr::QuestObjectiveType::CastSpellOnTarget: return "cast_spell_on_target";
        case BotWorldPopulationMgr::QuestObjectiveType::UseAbilityOnDummy: return "use_ability_on_dummy";
        case BotWorldPopulationMgr::QuestObjectiveType::UseItemOnTarget: return "use_item_on_target";
        default: return "unknown";
    }
}

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

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

std::vector<std::string> SplitRecoveryModes(std::string const& mode)
{
    if (mode == "corpse_recover")
        return { "corpse_recover", "safe_local_resurrect", "nearest_graveyard_or_spirit_healer", "last_safe_position", "configured_center_fallback" };
    if (mode == "safe_local" || mode == "safe_local_resurrect" || mode == "corpse_or_safe_local")
        return { "safe_local_resurrect", "last_safe_position", "nearest_graveyard_or_spirit_healer", "corpse_recover", "configured_center_fallback" };
    if (mode == "nearest_graveyard_or_spirit_healer" || mode == "graveyard")
        return { "nearest_graveyard_or_spirit_healer", "last_safe_position", "safe_local_resurrect", "configured_center_fallback" };
    if (mode == "last_safe_position")
        return { "last_safe_position", "safe_local_resurrect", "nearest_graveyard_or_spirit_healer", "configured_center_fallback" };
    if (mode == "configured_center_fallback")
        return { "configured_center_fallback" };
    return { "safe_local_resurrect", "last_safe_position", "nearest_graveyard_or_spirit_healer", "corpse_recover", "configured_center_fallback" };
}

bool SpellLooksLikeHeal(SpellInfo const* spellInfo)
{
    return spellInfo && (spellInfo->HasEffect(SPELL_EFFECT_HEAL)
        || spellInfo->HasEffect(SPELL_EFFECT_HEAL_PCT)
        || spellInfo->HasEffect(SPELL_EFFECT_HEAL_MECHANICAL));
}

bool SpellLooksDangerous(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    return spellInfo->HasEffect(SPELL_EFFECT_SCHOOL_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL)
        || spellInfo->HasEffect(SPELL_EFFECT_NORMALIZED_WEAPON_DMG)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_PERCENT_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_POWER_DRAIN)
        || spellInfo->HasEffect(SPELL_EFFECT_HEALTH_LEECH);
}

bool SpellLooksLikeSummonOrAdds(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    return spellInfo->HasEffect(SPELL_EFFECT_SUMMON)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_PET)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_OBJECT_SLOT1)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_OBJECT_SLOT2)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_OBJECT_SLOT3)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_OBJECT_SLOT4)
        || spellInfo->HasEffect(SPELL_EFFECT_SUMMON_CHANGE_ITEM);
}

bool SpellLooksLikeGroundDanger(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    if (spellInfo->HasEffect(SPELL_EFFECT_PERSISTENT_AREA_AURA))
        return true;

    for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[i];
        if (!effect.IsEffect())
            continue;

        if ((effect.IsTargetingArea() || effect.CalcRadius() >= 4.0f)
            && (SpellLooksDangerous(spellInfo) || effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE))
            return true;
    }

    return false;
}

bool SpellLooksRaidWide(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    if (spellInfo->MaxAffectedTargets >= 4)
        return true;

    for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[i];
        if (!effect.IsEffect())
            continue;

        if ((effect.IsTargetingArea() || effect.CalcRadius() >= 12.0f) && SpellLooksDangerous(spellInfo))
            return true;
    }

    return false;
}

bool SpellLooksTankSpike(SpellInfo const* spellInfo)
{
    if (!spellInfo)
        return false;

    if (spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL)
        || spellInfo->HasEffect(SPELL_EFFECT_NORMALIZED_WEAPON_DMG)
        || spellInfo->HasEffect(SPELL_EFFECT_WEAPON_PERCENT_DAMAGE))
        return true;

    return SpellLooksDangerous(spellInfo) && !SpellLooksRaidWide(spellInfo);
}

uint32 SemanticMechanicKey(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = result ? result : "";
    if (event == "interrupt_success" || event == "interrupt_failed")
        return 2;
    if (event == "boss_mechanic" || res == "move_out")
        return 1;
    if (event == "boss_adds")
        return 5;
    if (event == "boss_heal")
        return 4;
    if (event == "boss_action" || event == "boss_started")
        return 11;
    if (event == "trash_action" || event == "trash_heal")
        return 10;
    if (event == "death")
        return 99;
    return 0;
}

char const* SemanticMechanicFamily(uint32 key)
{
    switch (key)
    {
        case 1: return "ground_danger";
        case 2: return "must_interrupt";
        case 4: return "raid_damage";
        case 5: return "adds";
        case 10: return "trash_pack";
        case 11: return "boss_pressure";
        case 99: return "death_failure";
        default: return "unknown";
    }
}

bool EventLooksSuccessful(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = result ? result : "";
    return res == "ok"
        || event == "mob_killed"
        || event == "boss_killed"
        || event == "quest_completed"
        || event == "objective_progress"
        || event == "gear_upgrade"
        || event == "gear_evaluated"
        || event == "interrupt_success";
}

bool EventLooksFailure(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = result ? result : "";
    return event == "death"
        || event == "repeated_death"
        || event == "stuck_detected"
        || event == "objective_failed"
        || event == "death_recovery_failed"
        || event == "interrupt_failed"
        || event == "teleport_fallback_used"
        || res == "failed"
        || res.find("failed") != std::string::npos
        || res.find("blocked") != std::string::npos;
}

std::string BuildSpellTagJson(SpellInfo const* spellInfo, bool mustInterrupt, bool groundDanger, bool tankSpike, bool raidDamage, bool adds)
{
    std::ostringstream tags;
    tags << "[";
    bool first = true;
    auto addTag = [&tags, &first](char const* tag)
    {
        if (!first)
            tags << ",";
        tags << "\"" << tag << "\"";
        first = false;
    };

    if (SpellLooksDangerous(spellInfo))
        addTag("direct_damage");
    if (groundDanger)
    {
        addTag("ground_effect");
        addTag("move_out");
    }
    if (mustInterrupt)
        addTag("must_interrupt");
    if (tankSpike)
        addTag("tank_spike");
    if (raidDamage)
        addTag("raid_damage");
    if (adds)
        addTag("add_wave");
    if (SpellLooksLikeHeal(spellInfo))
        addTag("boss_heal");

    tags << "]";
    return tags.str();
}
}

BotWorldPopulationMgr* BotWorldPopulationMgr::instance()
{
    static BotWorldPopulationMgr instance;
    return &instance;
}

bool BotWorldPopulationMgr::Start(std::string const& experimentName, BotWorldExperimentConfig const* overrideConfig)
{
    if (_active && _runtimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy)
    {
        if (_runId)
        {
            _telemetryBuffer.FlushOpenClips(_experimentId, _runId, _config.BrainVersion);
            RecordRunStop();
        }
        else
            _telemetryBuffer.Clear();

        if (overrideConfig)
            LoadConfig(experimentName.empty() ? "autonomy_recording_window" : experimentName, overrideConfig);
        else if (!experimentName.empty())
            _config.Name = experimentName;
        else
            _config.Name = "autonomy_recording_window";

        _metrics = BotWorldStatus();
        _metrics.Active = true;
        _metrics.Mode = BotWorldRuntimeMode::AlwaysOnAutonomy;
        _metrics.Name = _config.Name;
        _metrics.TargetBots = _config.TargetPopulation;
        _elapsedMs = 0;
        _recordingWindowElapsedMs = 0;
        RecordRunStart();
        return true;
    }

    if (_active)
        Stop();

    if (!sConfigMgr->GetBoolDefault("BotWorld.Enable", false) || !sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return false;

    LoadConfig(experimentName.empty() ? "autonomous_zone_10" : experimentName, overrideConfig);
    _telemetryBuffer.Clear();
    _experimentCoordinator.Clear();
    _bots.clear();
    _failedSpawnGuids.clear();
    _metrics = BotWorldStatus();
    _metrics.Active = true;
    _metrics.Mode = BotWorldRuntimeMode::ManualExperiment;
    _metrics.Name = _config.Name;
    _metrics.TargetBots = _config.TargetPopulation;
    _elapsedMs = 0;
    _recordingWindowElapsedMs = 0;
    _active = true;
    _runtimeMode = BotWorldRuntimeMode::ManualExperiment;

    RecordRunStart();
    EnsurePopulation();
    return _active;
}

void BotWorldPopulationMgr::Stop()
{
    if (!_active)
        return;

    if (_runtimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy)
    {
        for (WorldBotState const& state : _bots)
            PersistBotPosition(GetBot(state));
        _telemetryBuffer.FlushOpenClips(_experimentId, _runId, _config.BrainVersion);
        RecordRunStop();
        _experimentCoordinator.Clear();
        _experimentCoordinator.Configure(0, _config.BrainVersion);
        _runId = 0;
        _experimentId = 0;
        _metrics.RunId = 0;
        _metrics.ExperimentId = 0;
        return;
    }

    for (WorldBotState const& state : _bots)
    {
        Player* bot = GetBot(state);
        PersistBotPosition(bot);
        RecordActivityStop(state, bot);
        sBotMgr->RemoveWorldBot(state.Guid);
    }

    _telemetryBuffer.FlushOpenClips(_experimentId, _runId, _config.BrainVersion);
    RecordRunStop();
    _experimentCoordinator.Clear();
    _runId = 0;
    _experimentId = 0;
    _bots.clear();
    _active = false;
}

bool BotWorldPopulationMgr::StartAutonomy(BotWorldExperimentConfig const* overrideConfig)
{
    if (_active)
    {
        if (_runtimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy)
            StopAutonomy();
        else
            Stop();
    }

    if (!sConfigMgr->GetBoolDefault("BotWorld.Enable", false) || !sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return false;

    LoadConfig("always_on_autonomy", overrideConfig);
    _telemetryBuffer.Clear();
    _experimentCoordinator.Clear();
    _experimentCoordinator.Configure(0, _config.BrainVersion);
    _bots.clear();
    _failedSpawnGuids.clear();
    _metrics = BotWorldStatus();
    _metrics.Active = true;
    _metrics.Mode = BotWorldRuntimeMode::AlwaysOnAutonomy;
    _metrics.Name = _config.Name;
    _metrics.TargetBots = _config.TargetPopulation;
    _elapsedMs = 0;
    _recordingWindowElapsedMs = 0;
    _recordingWindowIndex = 0;
    _runId = 0;
    _experimentId = 0;
    _active = true;
    _runtimeMode = BotWorldRuntimeMode::AlwaysOnAutonomy;

    MaybeStartAutoRecordingWindow();
    EnsurePopulation();
    return _active;
}

void BotWorldPopulationMgr::StopAutonomy()
{
    if (!_active || _runtimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy)
        return;

    for (WorldBotState const& state : _bots)
    {
        Player* bot = GetBot(state);
        PersistBotPosition(bot);
        RecordActivityStop(state, bot);
        sBotMgr->RemoveWorldBot(state.Guid);
    }

    _telemetryBuffer.FlushOpenClips(_experimentId, _runId, _config.BrainVersion);
    RecordRunStop();
    _experimentCoordinator.Clear();
    _bots.clear();
    _active = false;
    _runId = 0;
    _experimentId = 0;
}

bool BotWorldPopulationMgr::SpawnAutonomyBots(uint32 count)
{
    if (!_active || _runtimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy || !count)
        return false;

    _config.TargetPopulation += count;
    _metrics.TargetBots = _config.TargetPopulation;
    EnsurePopulation();
    return true;
}

void BotWorldPopulationMgr::Update(uint32 diff)
{
    if (!_active)
        return;

    _elapsedMs += diff;
    RotateAutoRecordingWindowIfNeeded(diff);
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

void BotWorldPopulationMgr::LoadConfig(std::string const& name, BotWorldExperimentConfig const* overrideConfig)
{
    _config = overrideConfig ? *overrideConfig : BotWorldExperimentConfig();
    _config.Name = name.empty() ? _config.Name : name;
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
    _config.AllowGrinding = sConfigMgr->GetBoolDefault("BotWorld.AllowGrinding", _config.AllowGrinding);
    _config.QuestFirst = sConfigMgr->GetBoolDefault("BotWorld.QuestFirst", _config.QuestFirst);
    _config.GrindOnlyWhenNoQuestAvailable = sConfigMgr->GetBoolDefault("BotWorld.GrindOnlyWhenNoQuestAvailable", _config.GrindOnlyWhenNoQuestAvailable);
    _config.EnableProgression = sConfigMgr->GetBoolDefault("BotProgression.Enable", _config.EnableProgression);
    _config.AllowQuesting = sConfigMgr->GetBoolDefault("BotProgression.AllowQuesting", sConfigMgr->GetBoolDefault("BotWorld.AllowQuesting", _config.AllowQuesting));
    _config.AllowDungeons = sConfigMgr->GetBoolDefault("BotProgression.AllowDungeons", _config.AllowDungeons);
    _config.AllowRaids = sConfigMgr->GetBoolDefault("BotProgression.AllowRaids", _config.AllowRaids);
    _config.TrackHeroicRaidProgression = sConfigMgr->GetBoolDefault("BotProgression.TrackHeroicRaidProgression", _config.TrackHeroicRaidProgression);
    _config.RecordDecisions = sConfigMgr->GetBoolDefault("BotExperiment.RecordDecisions", _config.RecordDecisions);
    _config.RecordPerception = sConfigMgr->GetBoolDefault("BotExperiment.RecordPerception", _config.RecordPerception);
    _config.SmartSampling = sConfigMgr->GetBoolDefault("BotExperiment.SmartSampling", _config.SmartSampling);
    _config.AlwaysRecordFailures = sConfigMgr->GetBoolDefault("BotExperiment.AlwaysRecordFailures", _config.AlwaysRecordFailures);
    _config.AlwaysRecordInterventions = sConfigMgr->GetBoolDefault("BotExperiment.AlwaysRecordInterventions", _config.AlwaysRecordInterventions);
    _config.AlwaysRecordRareStates = sConfigMgr->GetBoolDefault("BotExperiment.AlwaysRecordRareStates", _config.AlwaysRecordRareStates);
    _config.NormalEventSampleRate = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotExperiment.NormalEventSampleRate", _config.NormalEventSampleRate));
    _config.NormalDecisionSampleRate = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotExperiment.NormalDecisionSampleRate", _config.NormalDecisionSampleRate));
    _config.MinClipImportance = std::max(0.0f, sConfigMgr->GetFloatDefault("BotExperiment.MinClipImportance", _config.MinClipImportance));
    _config.MinReplayImportance = std::max(0.0f, sConfigMgr->GetFloatDefault("BotExperiment.MinReplayImportance", _config.MinReplayImportance));
    _config.UpdateSemanticOutcomeStats = sConfigMgr->GetBoolDefault("BotSemantic.UpdateOutcomeStats", _config.UpdateSemanticOutcomeStats);
    _config.BrainVersion = sConfigMgr->GetStringDefault("BotExperiment.BrainVersion", _config.BrainVersion);
    _config.SpawnMode = sConfigMgr->GetStringDefault("BotWorld.SpawnMode", _config.SpawnMode);
    _config.AllowConfiguredCenterFallback = sConfigMgr->GetBoolDefault("BotWorld.AllowConfiguredCenterFallback", _config.AllowConfiguredCenterFallback);
    _config.UseSavedPosition = sConfigMgr->GetBoolDefault("BotWorld.UseSavedPosition", _config.UseSavedPosition);
    _config.NearPlayerRadius = sConfigMgr->GetFloatDefault("BotWorld.NearPlayerRadius", _config.NearPlayerRadius);
    _config.TrainingDummyEntries = sConfigMgr->GetStringDefault("BotWorld.TrainingDummyEntries", _config.TrainingDummyEntries);
    _config.DeathRecoveryMode = sConfigMgr->GetStringDefault("BotWorld.DeathRecoveryMode", sConfigMgr->GetStringDefault("BotWorld.RespawnMode", _config.DeathRecoveryMode));
    _config.TeleportToCenterOnDeath = sConfigMgr->GetBoolDefault("BotWorld.TeleportToCenterOnDeath", _config.TeleportToCenterOnDeath);
    _config.MaxDeathsBeforeFallback = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotWorld.MaxDeathsBeforeFallback", _config.MaxDeathsBeforeFallback));
    _config.SafePositionMemorySec = std::max<uint32>(10, sConfigMgr->GetIntDefault("BotWorld.SafePositionMemorySec", _config.SafePositionMemorySec));
    _config.AutoStartRecording = sConfigMgr->GetBoolDefault("BotWorld.AutoStartRecording", _config.AutoStartRecording);
    _config.AutoRecordingWindowMinutes = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotWorld.AutoRecordingWindowMinutes", _config.AutoRecordingWindowMinutes));
    _config.AutoRecordingNamePrefix = sConfigMgr->GetStringDefault("BotWorld.AutoRecordingNamePrefix", _config.AutoRecordingNamePrefix);
    _config.Learning.Enabled = sConfigMgr->GetBoolDefault("BotLearning.Enable", _config.Learning.Enabled);
    _config.Learning.MinSamplesForStrongBias = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotLearning.MinSamplesForStrongBias", _config.Learning.MinSamplesForStrongBias));
    _config.Learning.DangerPenaltyWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotLearning.DangerPenaltyWeight", _config.Learning.DangerPenaltyWeight));
    _config.Learning.ProgressionRewardWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotLearning.ProgressionRewardWeight", _config.Learning.ProgressionRewardWeight));
    _config.Learning.RecentFailurePenaltyWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotLearning.RecentFailurePenaltyWeight", _config.Learning.RecentFailurePenaltyWeight));
    _config.Learning.ExplorationNoveltyWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotLearning.ExplorationNoveltyWeight", _config.Learning.ExplorationNoveltyWeight));
    _config.Learning.AllowGlobalMemoryFallback = sConfigMgr->GetBoolDefault("BotLearning.AllowGlobalMemoryFallback", _config.Learning.AllowGlobalMemoryFallback);
    _learningConfig = _config.Learning;

    _policyModelConfig.Enabled = sConfigMgr->GetBoolDefault("BotPolicyModel.Enable", _policyModelConfig.Enabled);
    _policyModelConfig.Mode = sConfigMgr->GetStringDefault("BotPolicyModel.Mode", _policyModelConfig.Mode);
    _policyModelConfig.Version = sConfigMgr->GetStringDefault("BotPolicyModel.Version", _policyModelConfig.Version);
    _policyModelConfig.ScoreWeight = std::max(0.0f, sConfigMgr->GetFloatDefault("BotPolicyModel.ScoreWeight", _policyModelConfig.ScoreWeight));
    _policyModelConfig.FailClosed = sConfigMgr->GetBoolDefault("BotPolicyModel.FailClosed", _policyModelConfig.FailClosed);
    _policyModelConfig.MaxDecisionLatencyMs = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotPolicyModel.MaxDecisionLatencyMs", _policyModelConfig.MaxDecisionLatencyMs));
    _policyModelConfig.MinEvalRows = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotPolicyModel.MinEvalRows", _policyModelConfig.MinEvalRows));
    _policyModelConfig.MaxDeathRate = std::max(0.0f, sConfigMgr->GetFloatDefault("BotPolicyModel.MaxDeathRate", _policyModelConfig.MaxDeathRate));
    _policyModelConfig.MaxStuckRate = std::max(0.0f, sConfigMgr->GetFloatDefault("BotPolicyModel.MaxStuckRate", _policyModelConfig.MaxStuckRate));
    _policyModelConfig.MaxFailureRate = std::max(0.0f, sConfigMgr->GetFloatDefault("BotPolicyModel.MaxFailureRate", _policyModelConfig.MaxFailureRate));
    if (_policyModelConfig.Mode != "shadow" && _policyModelConfig.Mode != "assist" && _policyModelConfig.Mode != "control")
        _policyModelConfig.Mode = "shadow";
    ValidatePolicyModelDeployment();

    BotTelemetryBufferConfig telemetry;
    telemetry.Enabled = sConfigMgr->GetBoolDefault("BotTelemetry.Enable", telemetry.Enabled);
    telemetry.FrameIntervalMs = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotTelemetry.FrameIntervalMs", telemetry.FrameIntervalMs));
    telemetry.PreEventWindowSec = sConfigMgr->GetIntDefault("BotTelemetry.PreEventWindowSec", telemetry.PreEventWindowSec);
    telemetry.PostEventWindowSec = sConfigMgr->GetIntDefault("BotTelemetry.PostEventWindowSec", telemetry.PostEventWindowSec);
    telemetry.MaxFramesPerBot = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotTelemetry.MaxFramesPerBot", telemetry.MaxFramesPerBot));
    telemetry.MaxOpenClipsPerBot = std::max<uint32>(1, sConfigMgr->GetIntDefault("BotTelemetry.MaxOpenClipsPerBot", telemetry.MaxOpenClipsPerBot));
    _telemetryBuffer.Configure(telemetry);
}

void BotWorldPopulationMgr::MaybeStartAutoRecordingWindow()
{
    if (!_active || _runtimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy || !_config.AutoStartRecording || _runId)
        return;

    _config.Name = BuildAutoRecordingWindowName();
    _metrics.Name = _config.Name;
    _metrics.TargetBots = _config.TargetPopulation;
    _recordingWindowElapsedMs = 0;
    RecordRunStart();
}

void BotWorldPopulationMgr::RotateAutoRecordingWindowIfNeeded(uint32 diff)
{
    if (!_active || _runtimeMode != BotWorldRuntimeMode::AlwaysOnAutonomy || !_config.AutoStartRecording)
        return;

    if (!_runId)
    {
        MaybeStartAutoRecordingWindow();
        return;
    }

    _recordingWindowElapsedMs += diff;
    uint32 windowMs = _config.AutoRecordingWindowMinutes * 60 * 1000;
    if (_recordingWindowElapsedMs < windowMs)
        return;

    _telemetryBuffer.FlushOpenClips(_experimentId, _runId, _config.BrainVersion);
    RecordRunStop();
    ++_recordingWindowIndex;
    _config.Name = BuildAutoRecordingWindowName();
    _metrics = BotWorldStatus();
    _metrics.Active = true;
    _metrics.Mode = BotWorldRuntimeMode::AlwaysOnAutonomy;
    _metrics.Name = _config.Name;
    _metrics.TargetBots = _config.TargetPopulation;
    _metrics.ActiveBots = uint32(_bots.size());
    _elapsedMs = 0;
    _recordingWindowElapsedMs = 0;
    RecordRunStart();
}

std::string BotWorldPopulationMgr::BuildAutoRecordingWindowName() const
{
    std::ostringstream name;
    name << (_config.AutoRecordingNamePrefix.empty() ? "autonomy_window" : _config.AutoRecordingNamePrefix)
         << "_" << _recordingWindowIndex;
    return name.str();
}

void BotWorldPopulationMgr::ValidatePolicyModelDeployment()
{
    _policyModelConfig.AssistAllowed = false;
    _policyModelConfig.DeploymentReason = "disabled";
    _policyModelConfig.ArtifactLoaded = false;
    _policyModelConfig.ArtifactPath.clear();
    _policyModelConfig.ModelType.clear();
    _policyModelConfig.ModelMeans.clear();
    _policyModelConfig.ModelWeights.clear();
    _policyModelConfig.ModelTreeEnsembles.clear();
    if (!_policyModelConfig.Enabled)
        return;

    if (_policyModelConfig.Version.empty())
    {
        _policyModelConfig.DeploymentReason = "missing_model_version";
        if (_policyModelConfig.FailClosed)
            _policyModelConfig.Mode = "shadow";
        return;
    }

    std::string version = _policyModelConfig.Version;
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
        _policyModelConfig.DeploymentReason = "model_not_registered";
        if (_policyModelConfig.FailClosed)
            _policyModelConfig.Mode = "shadow";
        return;
    }

    Field* fields = result->Fetch();
    bool accepted = fields[0].GetUInt8() != 0;
    _policyModelConfig.ArtifactPath = fields[1].GetString();
    _policyModelConfig.ModelType = fields[2].GetString();
    uint32 evalRows = fields[3].GetUInt32();
    float deathRate = fields[4].GetFloat();
    float stuckRate = fields[5].GetFloat();
    float failureRate = fields[6].GetFloat();

    if (!LoadPolicyModelArtifact(_policyModelConfig.ArtifactPath))
        _policyModelConfig.DeploymentReason = "artifact_load_failed";
    else if (_policyModelConfig.Mode == "shadow")
    {
        _policyModelConfig.DeploymentReason = "shadow_mode";
        return;
    }
    else if (_policyModelConfig.Mode == "control")
        _policyModelConfig.DeploymentReason = "control_mode_disabled";
    else if (!accepted)
        _policyModelConfig.DeploymentReason = "model_not_accepted";
    else if (evalRows < _policyModelConfig.MinEvalRows)
        _policyModelConfig.DeploymentReason = "insufficient_eval_rows";
    else if (deathRate > _policyModelConfig.MaxDeathRate)
        _policyModelConfig.DeploymentReason = "death_rate_regression";
    else if (stuckRate > _policyModelConfig.MaxStuckRate)
        _policyModelConfig.DeploymentReason = "stuck_rate_regression";
    else if (failureRate > _policyModelConfig.MaxFailureRate)
        _policyModelConfig.DeploymentReason = "failure_rate_regression";
    else
    {
        _policyModelConfig.AssistAllowed = true;
        _policyModelConfig.DeploymentReason = "assist_allowed";
        return;
    }

    if (_policyModelConfig.FailClosed)
        _policyModelConfig.Mode = "shadow";
}

bool BotWorldPopulationMgr::LoadPolicyModelArtifact(std::string const& artifactPath)
{
    std::string json = ReadSmallTextFile(artifactPath);
    if (json.empty())
        return false;

    std::string version = ExtractJsonStringField(json, "model_version");
    if (!version.empty() && version != _policyModelConfig.Version)
        return false;

    std::string schema = ExtractJsonStringField(json, "feature_schema_version");
    if (!schema.empty())
        _policyModelConfig.FeatureSchemaVersion = schema;

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

    _policyModelConfig.ModelMeans = std::move(means);
    _policyModelConfig.ModelWeights = std::move(weights);
    _policyModelConfig.ModelTreeEnsembles = std::move(treeEnsembles);
    if (!artifactFormat.empty())
        _policyModelConfig.ModelType = artifactFormat;
    _policyModelConfig.ArtifactLoaded = true;
    return true;
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

        SpawnPlacement placement;
        if (!ResolveSpawnPlacement(candidateGuid, placement))
        {
            TC_LOG_ERROR("server", "BotWorld spawn skipped bot_guid=%u spawn_mode=%s fallback=%u reason=no_saved_or_local_spawn",
                candidateGuid, _config.SpawnMode.c_str(), _config.AllowConfiguredCenterFallback ? 1 : 0);
            _failedSpawnGuids.insert(candidateGuid);
            continue;
        }

        Player* bot = placement.Source == "saved_position"
            ? sBotMgr->SpawnWorldBotAtSavedPosition("any", std::to_string(candidateGuid))
            : sBotMgr->SpawnWorldBot("any", std::to_string(candidateGuid), placement.MapId, placement.X, placement.Y, placement.Z, placement.O);
        if (!bot)
        {
            _failedSpawnGuids.insert(candidateGuid);
            continue;
        }
        TC_LOG_INFO("server", "BotWorld spawn selected bot=%s source=%s map=%u position=%f,%f,%f",
            bot->GetGUID().ToString().c_str(), placement.Source.c_str(), bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());

        WorldBotState state;
        state.Guid = bot->GetGUID();
        state.DecisionTimer = urand(0, sConfigMgr->GetIntDefault("BotWorld.DecisionTickMs", 3000));
        state.LastX = bot->GetPositionX();
        state.LastY = bot->GetPositionY();
        state.LastZ = bot->GetPositionZ();
        state.SpawnSource = placement.Source;
        state.RaceStartFallbackUsed = placement.RaceStartFallbackUsed;
        state.SpawnMapId = bot->GetMapId();
        state.SpawnX = bot->GetPositionX();
        state.SpawnY = bot->GetPositionY();
        state.SpawnZ = bot->GetPositionZ();
        state.SpawnO = bot->GetOrientation();
        _bots.push_back(state);
        _metrics.ActiveBots = uint32(_bots.size());

        RecordActivityStart(_bots.back(), bot);
        BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
        BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "idle", &power, stage);
        RecordSpawnResolved(_bots.back(), bot, placement, placement.Source.c_str());
        RecordEvent(_bots.back(), bot, "bot_spawned", nullptr, "ok", raw.c_str(), semantic.c_str());
        if (_config.AllowRaids && bot->GetMap() && bot->GetMap()->IsRaid())
        {
            RaidRoleAssignment assignment = BuildRaidRoleAssignment(bot);
            BossMechanicFeatures features = BuildBossMechanicFeatures(bot, nullptr);
            RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(bot, nullptr, assignment, features);
            RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(bot, nullptr, assignment, features);
            RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(bot, power, stage);
            HeroicRaidProgression progression = BuildHeroicRaidProgression(_bots.back(), bot, power, stage);
            RecordRaidTelemetry(_bots.back(), bot, nullptr, "raid_role_assignment", "assigned", features, assignment, anchors, adapter, gearPlan, progression, raw.c_str(), semantic.c_str());
        }
    }
}

bool BotWorldPopulationMgr::ResolveSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const
{
    std::string mode = _config.SpawnMode.empty() ? "resume_or_race_start" : _config.SpawnMode;
    bool allowResume = _config.UseSavedPosition && (mode == "resume_or_race_start" || mode == "resume_only" || mode == "saved_or_near_player");
    if (allowResume)
    {
        if (ResolveSavedSpawnPlacement(candidateGuid, placement))
            return true;

        if (mode == "resume_only")
            return false;
    }

    if (mode == "resume_or_race_start" || mode == "race_start_only")
    {
        if (ResolveRaceStartSpawnPlacement(candidateGuid, placement))
            return true;
        if (mode == "race_start_only")
            return false;
    }

    if (mode == "saved_or_near_player" || mode == "near_player")
        if (ResolveNearPlayerSpawnPlacement(placement))
            return true;

    if (mode == "configured_center" || _config.AllowConfiguredCenterFallback)
        return ResolveConfiguredCenterSpawnPlacement(placement);

    return false;
}

bool BotWorldPopulationMgr::ResolveSavedSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const
{
    if (QueryResult result = CharacterDatabase.PQuery("SELECT map, position_x, position_y, position_z, orientation FROM characters WHERE guid = %u", candidateGuid))
    {
        Field* fields = result->Fetch();
        uint32 mapId = fields[0].GetUInt16();
        float x = fields[1].GetFloat();
        float y = fields[2].GetFloat();
        float z = fields[3].GetFloat();
        if (!IsValidBotResumePosition(candidateGuid, mapId, x, y, z))
        {
            if (_runId)
            {
                std::string brain = _config.BrainVersion;
                CharacterDatabase.EscapeString(brain);
                CharacterDatabase.DirectPExecute(
                    "INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, map_id, x, y, z, event_type, result, raw_json, semantic_json, context_json) "
                    "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %f, %f, %f, 'spawn_resume_invalid', 'invalid_saved_position', '{}', '{}', '{\"source\":\"saved_position\"}')",
                    _experimentId, _runId, candidateGuid, brain.c_str(), mapId, x, y, z);
            }
            return false;
        }

        placement.Valid = true;
        placement.MapId = mapId;
        placement.X = x;
        placement.Y = y;
        placement.Z = z;
        placement.O = fields[4].GetFloat();
        placement.Source = "saved_position";
        return true;
    }

    return false;
}

bool BotWorldPopulationMgr::ResolveRaceStartSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const
{
    QueryResult result = CharacterDatabase.PQuery("SELECT race, class FROM characters WHERE guid = %u", candidateGuid);
    if (!result)
        return false;

    Field* fields = result->Fetch();
    uint8 race = fields[0].GetUInt8();
    uint8 playerClass = fields[1].GetUInt8();
    PlayerInfo const* info = sObjectMgr->GetPlayerInfo(race, playerClass);
    if (!info || !MapManager::IsValidMapCoord(info->mapId, info->positionX, info->positionY, info->positionZ, 0.0f))
        return false;

    placement.Valid = true;
    placement.MapId = info->mapId;
    placement.X = info->positionX;
    placement.Y = info->positionY;
    placement.Z = info->positionZ;
    placement.O = 0.0f;
    placement.Source = "race_start";
    placement.RaceStartFallbackUsed = true;
    return true;
}

bool BotWorldPopulationMgr::ResolveNearPlayerSpawnPlacement(SpawnPlacement& placement) const
{
    std::shared_lock<std::shared_mutex> lock(*HashMapHolder<Player>::GetLock());
    HashMapHolder<Player>::MapType const& players = ObjectAccessor::GetPlayers();
    for (HashMapHolder<Player>::MapType::const_iterator itr = players.begin(); itr != players.end(); ++itr)
    {
        Player* player = itr->second;
        if (!player || !player->IsInWorld() || !player->GetMap())
            continue;

        if (CharacterDatabase.PQuery("SELECT 1 FROM character_bot_pool WHERE guid = %u LIMIT 1", player->GetGUID().GetCounter()))
            continue;

        Position pos = player->GetNearPosition(_config.NearPlayerRadius, frand(0.0f, 2.0f * float(M_PI)));
        placement.Valid = true;
        placement.MapId = player->GetMapId();
        placement.X = pos.GetPositionX();
        placement.Y = pos.GetPositionY();
        placement.Z = pos.GetPositionZ();
        placement.O = pos.GetOrientation();
        placement.Source = "near_player";
        return true;
    }

    return false;
}

bool BotWorldPopulationMgr::ResolveConfiguredCenterSpawnPlacement(SpawnPlacement& placement) const
{
    float angle = frand(0.0f, 2.0f * float(M_PI));
    float dist = frand(0.0f, _config.Radius * 0.35f);
    placement.Valid = true;
    placement.MapId = _config.MapId;
    placement.X = _config.CenterX + std::cos(angle) * dist;
    placement.Y = _config.CenterY + std::sin(angle) * dist;
    placement.Z = _config.CenterZ;
    placement.O = angle;
    placement.Source = "configured_center";
    return true;
}

bool BotWorldPopulationMgr::IsConfiguredCenterPosition(uint32 mapId, float x, float y, float z) const
{
    if (mapId != _config.MapId)
        return false;
    return Distance2d(x, y, _config.CenterX, _config.CenterY) <= std::max(1.0f, _config.Radius * 0.35f)
        && std::fabs(z - _config.CenterZ) <= 10.0f;
}

bool BotWorldPopulationMgr::IsValidBotResumePosition(uint32 botGuid, uint32 mapId, float x, float y, float z) const
{
    if (!botGuid)
        return false;
    if (std::fabs(x) < 0.001f && std::fabs(y) < 0.001f && std::fabs(z) < 0.001f)
        return false;
    if (!MapManager::IsValidMapCoord(mapId, x, y, z, 0.0f))
        return false;
    if (IsConfiguredCenterPosition(mapId, x, y, z) && _config.SpawnMode != "configured_center" && !_config.AllowConfiguredCenterFallback)
        return false;
    return true;
}

void BotWorldPopulationMgr::PersistBotPosition(Player* bot) const
{
    if (!bot || !bot->IsInWorld() || !MapManager::IsValidMapCoord(bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), bot->GetOrientation()))
        return;

    CharacterDatabase.DirectPExecute(
        "UPDATE characters SET position_x = %f, position_y = %f, position_z = %f, orientation = %f, map = %u, zone = %u WHERE guid = %u",
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), bot->GetOrientation(), bot->GetMapId(), bot->GetZoneId(), bot->GetGUID().GetCounter());
}

void BotWorldPopulationMgr::RecordSpawnResolved(WorldBotState& state, Player* bot, SpawnPlacement const& placement, char const* result)
{
    if (!_runId || !bot)
        return;

    std::ostringstream context;
    context << "{\"source\":\"" << JsonEscape(placement.Source) << "\""
            << ",\"map\":" << bot->GetMapId()
            << ",\"x\":" << bot->GetPositionX()
            << ",\"y\":" << bot->GetPositionY()
            << ",\"z\":" << bot->GetPositionZ()
            << ",\"o\":" << bot->GetOrientation()
            << ",\"race\":" << uint32(bot->getRace())
            << ",\"class\":" << uint32(bot->getClass())
            << ",\"level\":" << uint32(bot->getLevel())
            << ",\"race_start_fallback_used\":" << (placement.RaceStartFallbackUsed ? "true" : "false") << "}";
    std::string raw = BuildRawJson(bot, nullptr);
    std::string semantic = BuildSemanticJson(bot, nullptr, "spawn_resolved");
    std::string brain = _config.BrainVersion;
    std::string eventResult = result ? result : placement.Source;
    std::string contextJson = context.str();
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(eventResult);
    CharacterDatabase.EscapeString(contextJson);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, map_id, zone_id, area_id, x, y, z, level, event_type, result, value_int, raw_json, semantic_json, context_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %u, %f, %f, %f, %u, 'spawn_resolved', '%s', %u, '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), eventResult.c_str(), uint32(bot->getLevel()), raw.c_str(), semantic.c_str(), contextJson.c_str());
}

void BotWorldPopulationMgr::RememberSafePosition(WorldBotState& state, Player* bot, uint32 diff)
{
    if (!bot || !bot->IsAlive() || bot->IsInCombat() || state.StuckTimer)
        return;

    state.SafePositionTimer += diff;
    if (state.SafePositionTimer < 5000)
        return;
    state.SafePositionTimer = 0;

    uint64 nowMs = NowMs();
    PruneSafePositions(state, nowMs);

    float hpPct = bot->GetMaxHealth() ? float(bot->GetHealth()) / float(bot->GetMaxHealth()) : 1.0f;
    WorldBotState::SafePosition position;
    position.MapId = bot->GetMapId();
    position.ZoneId = bot->GetZoneId();
    position.AreaId = bot->GetAreaId();
    position.X = bot->GetPositionX();
    position.Y = bot->GetPositionY();
    position.Z = bot->GetPositionZ();
    position.O = bot->GetOrientation();
    position.HpPct = hpPct;
    position.SeenMs = nowMs;
    state.SafePositions.push_back(position);
    if (state.SafePositions.size() > 24)
        state.SafePositions.erase(state.SafePositions.begin(), state.SafePositions.begin() + (state.SafePositions.size() - 24));

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_safe_positions (bot_guid, map_id, zone_id, area_id, x, y, z, o, hp_pct, last_seen_at) "
        "VALUES (%u, %u, %u, %u, %f, %f, %f, %f, %f, NOW())",
        state.Guid.GetCounter(), position.MapId, position.ZoneId, position.AreaId, position.X, position.Y, position.Z, position.O, position.HpPct);
}

void BotWorldPopulationMgr::PruneSafePositions(WorldBotState& state, uint64 nowMs) const
{
    uint64 memoryMs = uint64(_config.SafePositionMemorySec) * 1000;
    state.SafePositions.erase(std::remove_if(state.SafePositions.begin(), state.SafePositions.end(), [nowMs, memoryMs](WorldBotState::SafePosition const& position)
    {
        return position.SeenMs + memoryMs < nowMs;
    }), state.SafePositions.end());
}

void BotWorldPopulationMgr::RememberVisiblePois(WorldBotState& state, Player* bot, uint32 diff)
{
    if (!bot || !bot->IsAlive())
        return;

    state.PoiScanTimer += diff;
    if (state.PoiScanTimer < 5000)
        return;
    state.PoiScanTimer = 0;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 80.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 80.0f);

    for (WorldObject* object : objects)
    {
        if (!object || !bot->IsInPhase(object))
            continue;

        if (Creature* creature = object->ToCreature())
        {
            if (!creature->IsAlive() || !bot->IsWithinLOSInMap(creature))
                continue;

            uint32 questId = 0;
            if (creature->IsQuestGiver())
            {
                QuestRelationResult starters = sObjectMgr->GetCreatureQuestRelations(creature->GetEntry());
                QuestRelationResult enders = sObjectMgr->GetCreatureQuestInvolvedRelations(creature->GetEntry());
                if (starters.begin() != starters.end())
                    questId = *starters.begin();
                else if (enders.begin() != enders.end())
                    questId = *enders.begin();
                RememberPoi(state, bot, creature, "quest_giver", questId, 120.0f - bot->GetExactDist(creature));
            }
            if (creature->IsVendor())
                RememberPoi(state, bot, creature, "vendor", 0, 80.0f - bot->GetExactDist(creature));
            if (creature->IsTrainer())
                RememberPoi(state, bot, creature, "trainer", 0, 75.0f - bot->GetExactDist(creature));
            if (creature->IsInnkeeper())
                RememberPoi(state, bot, creature, "innkeeper", 0, 60.0f - bot->GetExactDist(creature));
            if (creature->IsTaxi())
                RememberPoi(state, bot, creature, "flight_master", 0, 70.0f - bot->GetExactDist(creature));
        }
        else if (GameObject* go = object->ToGameObject())
        {
            uint32 questId = 0;
            QuestRelationResult starters = sObjectMgr->GetGOQuestRelations(go->GetEntry());
            QuestRelationResult enders = sObjectMgr->GetGOQuestInvolvedRelations(go->GetEntry());
            if (starters.begin() != starters.end())
                questId = *starters.begin();
            else if (enders.begin() != enders.end())
                questId = *enders.begin();

            if (questId || sObjectMgr->GetGameObjectQuestItemList(go->GetEntry()))
                RememberPoi(state, bot, go, "objective_object", questId, 90.0f - bot->GetExactDist(go));
        }
    }
}

void BotWorldPopulationMgr::RememberPoi(WorldBotState& state, Player* bot, WorldObject* object, char const* poiType, uint32 questId, float score) const
{
    if (!bot || !object || !poiType)
        return;

    uint32 entry = 0;
    if (Creature* creature = object->ToCreature())
        entry = creature->GetEntry();
    else if (GameObject* go = object->ToGameObject())
        entry = go->GetEntry();

    std::ostringstream metadata;
    metadata << "{\"source\":\"visible_scan\",\"object_type\":\"" << (object->GetTypeId() == TYPEID_GAMEOBJECT ? "gameobject" : "creature") << "\"}";
    std::string metadataJson = metadata.str();
    CharacterDatabase.EscapeString(metadataJson);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_pois (bot_guid, map_id, zone_id, area_id, x, y, z, poi_type, entity_guid, entity_entry, quest_id, score, discovered_at, last_seen_at, metadata_json) "
        "VALUES (%u, %u, %u, %u, %f, %f, %f, '%s', %u, %u, %u, %f, NOW(), NOW(), '%s') "
        "ON DUPLICATE KEY UPDATE map_id = VALUES(map_id), zone_id = VALUES(zone_id), area_id = VALUES(area_id), x = VALUES(x), y = VALUES(y), z = VALUES(z), score = GREATEST(score, VALUES(score)), last_seen_at = NOW(), metadata_json = VALUES(metadata_json)",
        state.Guid.GetCounter(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(), object->GetPositionX(), object->GetPositionY(), object->GetPositionZ(),
        poiType, object->GetGUID().GetCounter(), entry, questId, score, metadataJson.c_str());
}

void BotWorldPopulationMgr::MarkDeathDangerZone(WorldBotState& state, Player* bot, Unit const* target)
{
    if (!bot)
        return;

    uint32 sourceEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        sourceEntry = creature->GetEntry();

    if (state.LastDeathMapId == bot->GetMapId()
        && state.LastDeathAreaId == bot->GetAreaId()
        && Distance2d(state.LastDeathX, state.LastDeathY, bot->GetPositionX(), bot->GetPositionY()) <= 35.0f)
        ++state.RecentDeathCount;
    else
        state.RecentDeathCount = 1;

    state.LastDeathMapId = bot->GetMapId();
    state.LastDeathAreaId = bot->GetAreaId();
    state.LastDeathX = bot->GetPositionX();
    state.LastDeathY = bot->GetPositionY();

    std::ostringstream metadata;
    metadata << "{\"recent_death_count\":" << state.RecentDeathCount
             << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
             << ",\"source_entry\":" << sourceEntry << "}";
    std::string metadataJson = metadata.str();
    CharacterDatabase.EscapeString(metadataJson);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_danger_zones (bot_guid, map_id, zone_id, area_id, x, y, z, radius, danger_type, source_entry, death_count, failure_count, last_event_at, metadata_json) "
        "VALUES (%u, %u, %u, %u, %f, %f, %f, 35.0, '%s', %u, %u, %u, NOW(), '%s')",
        state.Guid.GetCounter(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(),
        state.RecentDeathCount >= _config.MaxDeathsBeforeFallback ? "repeated_death" : "death", sourceEntry, state.RecentDeathCount, state.RecentDeathCount, metadataJson.c_str());
}

void BotWorldPopulationMgr::MarkStuckFailure(WorldBotState& state, Player* bot)
{
    if (!bot)
        return;

    float fromX = state.ActivePathValid ? state.ActivePathFromX : state.LastX;
    float fromY = state.ActivePathValid ? state.ActivePathFromY : state.LastY;
    float fromZ = state.ActivePathValid ? state.ActivePathFromZ : state.LastZ;
    float toX = state.ActivePathValid ? state.ActivePathToX : bot->GetPositionX();
    float toY = state.ActivePathValid ? state.ActivePathToY : bot->GetPositionY();
    float toZ = state.ActivePathValid ? state.ActivePathToZ : bot->GetPositionZ();

    std::ostringstream metadata;
    metadata << "{\"stuck_timer_ms\":" << state.StuckTimer << "}";
    std::string metadataJson = metadata.str();
    CharacterDatabase.EscapeString(metadataJson);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_failed_paths (bot_guid, map_id, from_x, from_y, from_z, to_x, to_y, to_z, failure_type, failure_count, last_failed_at, metadata_json) "
        "VALUES (%u, %u, %f, %f, %f, %f, %f, %f, 'stuck', 1, NOW(), '%s')",
        state.Guid.GetCounter(), bot->GetMapId(), fromX, fromY, fromZ, toX, toY, toZ, metadataJson.c_str());

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_danger_zones (bot_guid, map_id, zone_id, area_id, x, y, z, radius, danger_type, stuck_count, failure_count, last_event_at, metadata_json) "
        "VALUES (%u, %u, %u, %u, %f, %f, %f, 20.0, 'stuck', 1, 1, NOW(), '%s')",
        state.Guid.GetCounter(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), metadataJson.c_str());
}

float BotWorldPopulationMgr::GetLocalDangerScore(uint32 botGuid, uint32 mapId, float x, float y, float z) const
{
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT COALESCE(SUM(death_count * 2 + stuck_count + failure_count), 0) "
        "FROM bot_memory_danger_zones "
        "WHERE bot_guid = %u AND map_id = %u "
        "AND POW(x - %f, 2) + POW(y - %f, 2) + POW(z - %f, 2) <= POW(radius, 2)",
        botGuid, mapId, x, y, z);
    return result ? result->Fetch()[0].GetFloat() : 0.0f;
}

bool BotWorldPopulationMgr::IsFailedPathRecently(uint32 botGuid, uint32 mapId, float fromX, float fromY, float toX, float toY) const
{
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT failure_count FROM bot_memory_failed_paths "
        "WHERE bot_guid = %u AND map_id = %u AND last_failed_at >= DATE_SUB(NOW(), INTERVAL 10 MINUTE) "
        "AND POW(from_x - %f, 2) + POW(from_y - %f, 2) <= POW(12.0, 2) "
        "AND POW(to_x - %f, 2) + POW(to_y - %f, 2) <= POW(12.0, 2) "
        "ORDER BY last_failed_at DESC LIMIT 1",
        botGuid, mapId, fromX, fromY, toX, toY);
    return bool(result);
}

bool BotWorldPopulationMgr::FindMemoryPoiTarget(Player* bot, float& x, float& y, float& z, uint64& poiId) const
{
    if (!bot)
        return false;

    QueryResult result = CharacterDatabase.PQuery(
        "SELECT id, x, y, z, score, visit_count, success_count, failure_count "
        "FROM bot_memory_pois "
        "WHERE bot_guid = %u AND map_id = %u AND zone_id = %u "
        "ORDER BY last_seen_at DESC LIMIT 16",
        bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetZoneId());
    if (!result)
        return false;

    bool found = false;
    float bestScore = -100000.0f;
    uint64 bestId = 0;
    float bestX = 0.0f;
    float bestY = 0.0f;
    float bestZ = 0.0f;
    do
    {
        Field* fields = result->Fetch();
        uint64 candidateId = fields[0].GetUInt64();
        float candidateX = fields[1].GetFloat();
        float candidateY = fields[2].GetFloat();
        float candidateZ = fields[3].GetFloat();
        float staticScore = fields[4].GetFloat();
        uint32 visitCount = fields[5].GetUInt32();
        uint32 successCount = fields[6].GetUInt32();
        uint32 failureCount = fields[7].GetUInt32();
        BotLearnedScore poiScore = BotExperienceLearningPolicy::ScorePoi(bot, candidateId, candidateX, candidateY, candidateZ, staticScore, visitCount, successCount, failureCount, _learningConfig);
        BotLearnedScore pathScore = BotExperienceLearningPolicy::ScorePath(bot, bot->GetPositionX(), bot->GetPositionY(), candidateX, candidateY, _learningConfig);
        if (poiScore.DangerScore >= 3.0f || pathScore.Penalty >= _learningConfig.RecentFailurePenaltyWeight)
            continue;

        float adjustedScore = staticScore - float(visitCount) * 15.0f - float(failureCount) * 25.0f + poiScore.Score + pathScore.Score;
        if (!found || adjustedScore > bestScore)
        {
            found = true;
            bestScore = adjustedScore;
            bestId = candidateId;
            bestX = candidateX;
            bestY = candidateY;
            bestZ = candidateZ;
        }
    } while (result->NextRow());

    if (!found)
        return false;

    poiId = bestId;
    x = bestX;
    y = bestY;
    z = bestZ;
    return true;
}

void BotWorldPopulationMgr::MarkPoiVisited(uint64 poiId) const
{
    if (!poiId)
        return;

    CharacterDatabase.DirectPExecute("UPDATE bot_memory_pois SET visit_count = visit_count + 1, last_seen_at = NOW() WHERE id = " UI64FMTD, poiId);
}

void BotWorldPopulationMgr::MoveBotToPoint(WorldBotState& state, Player* bot, float x, float y, float z)
{
    if (!bot)
        return;

    BotLearnedScore pathScore = BotExperienceLearningPolicy::ScorePath(bot, bot->GetPositionX(), bot->GetPositionY(), x, y, _learningConfig);
    if (IsFailedPathRecently(bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), x, y)
        || pathScore.Penalty >= _learningConfig.RecentFailurePenaltyWeight)
    {
        float angle = bot->GetAngle(x, y) + frand(-0.75f, 0.75f);
        Position alternate = bot->GetFirstCollisionPosition(6.0f, angle);
        BotLearnedScore alternatePathScore = BotExperienceLearningPolicy::ScorePath(bot, bot->GetPositionX(), bot->GetPositionY(), alternate.GetPositionX(), alternate.GetPositionY(), _learningConfig);
        if (!IsFailedPathRecently(bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), alternate.GetPositionX(), alternate.GetPositionY())
            && alternatePathScore.Penalty < pathScore.Penalty)
        {
            x = alternate.GetPositionX();
            y = alternate.GetPositionY();
            z = alternate.GetPositionZ();
        }
    }

    state.ActivePathFromX = bot->GetPositionX();
    state.ActivePathFromY = bot->GetPositionY();
    state.ActivePathFromZ = bot->GetPositionZ();
    state.ActivePathToX = x;
    state.ActivePathToY = y;
    state.ActivePathToZ = z;
    state.ActivePathValid = true;

    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MovePoint(0, x, y, z, true);
}

BotWorldPopulationMgr::BotDeathRecoveryPolicy BotWorldPopulationMgr::BuildDeathRecoveryPolicy() const
{
    BotDeathRecoveryPolicy policy;
    policy.Modes = SplitRecoveryModes(_config.DeathRecoveryMode);
    policy.CenterFallbackEnabled = _config.TeleportToCenterOnDeath;
    policy.MaxDeathsBeforeFallback = _config.MaxDeathsBeforeFallback;
    policy.SafePositionMemorySec = _config.SafePositionMemorySec;
    return policy;
}

BotWorldPopulationMgr::DeathRecoveryResult BotWorldPopulationMgr::RecoverDeadBot(WorldBotState& state, Player* bot)
{
    DeathRecoveryResult recovery;
    if (!bot || bot->IsAlive())
        return recovery;

    BotDeathRecoveryPolicy policy = BuildDeathRecoveryPolicy();
    recovery.RepeatedDeath = state.RecentDeathCount >= policy.MaxDeathsBeforeFallback;
    struct ScoredMode
    {
        std::string Mode;
        float Score = 0.0f;
    };
    std::vector<ScoredMode> scoredModes;
    for (std::string const& mode : policy.Modes)
    {
        float x = bot->GetPositionX();
        float y = bot->GetPositionY();
        float z = bot->GetPositionZ();
        if (mode == "last_safe_position" && !state.SafePositions.empty())
        {
            WorldBotState::SafePosition const& safe = state.SafePositions.back();
            x = safe.X;
            y = safe.Y;
            z = safe.Z;
        }
        else if (mode == "configured_center_fallback")
        {
            x = _config.CenterX;
            y = _config.CenterY;
            z = _config.CenterZ;
        }

        BotLearnedScore learned = BotExperienceLearningPolicy::ScoreRecoveryMode(bot, mode.c_str(), x, y, z, state.RecentDeathCount, _learningConfig);
        float staticScore = mode == "last_safe_position" ? 20.0f
            : mode == "safe_local_resurrect" ? 10.0f
            : mode == "nearest_graveyard_or_spirit_healer" ? 8.0f
            : mode == "corpse_recover" ? 6.0f
            : 0.0f;
        scoredModes.push_back({ mode, staticScore + learned.Score });
    }
    std::sort(scoredModes.begin(), scoredModes.end(), [](ScoredMode const& left, ScoredMode const& right)
    {
        if (left.Score == right.Score)
            return left.Mode < right.Mode;
        return left.Score > right.Score;
    });

    for (ScoredMode const& scored : scoredModes)
    {
        std::string const& mode = scored.Mode;
        if (mode == "configured_center_fallback" && (!policy.CenterFallbackEnabled || !recovery.RepeatedDeath))
            continue;

        std::string result;
        bool ok = false;
        if (mode == "corpse_recover")
            ok = TryCorpseRecovery(bot, result);
        else if (mode == "safe_local_resurrect")
            ok = TrySafeLocalResurrect(bot, result);
        else if (mode == "nearest_graveyard_or_spirit_healer")
            ok = TryNearestGraveyardResurrect(bot, result);
        else if (mode == "last_safe_position")
            ok = TryLastSafePositionResurrect(state, bot, result);
        else if (mode == "configured_center_fallback")
            ok = TryConfiguredCenterDeathFallback(bot, result);

        if (!ok)
            continue;

        recovery.Recovered = true;
        recovery.UsedFallback = mode == "configured_center_fallback";
        recovery.Mode = mode;
        recovery.Result = result.empty() ? "ok" : result;
        return recovery;
    }

    recovery.Result = "no_recovery_mode_succeeded";
    return recovery;
}

bool BotWorldPopulationMgr::TryCorpseRecovery(Player* bot, std::string& result) const
{
    Corpse* corpse = bot ? bot->GetCorpse() : nullptr;
    if (!bot || !corpse || corpse->GetMapId() != bot->GetMapId())
    {
        result = "corpse_unavailable";
        return false;
    }

    Position pos = corpse->GetNearPosition(3.0f, frand(0.0f, 2.0f * float(M_PI)));
    bot->ResurrectPlayer(0.7f, false);
    bot->NearTeleportTo(pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ(), pos.GetOrientation());
    result = "corpse_recovered";
    return true;
}

bool BotWorldPopulationMgr::TrySafeLocalResurrect(Player* bot, std::string& result) const
{
    if (!bot)
    {
        result = "bot_unavailable";
        return false;
    }

    Position pos = bot->GetFirstCollisionPosition(4.0f, frand(0.0f, 2.0f * float(M_PI)));
    bot->ResurrectPlayer(0.7f, false);
    bot->NearTeleportTo(pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ(), pos.GetOrientation());
    result = "safe_local_resurrected";
    return true;
}

bool BotWorldPopulationMgr::TryNearestGraveyardResurrect(Player* bot, std::string& result) const
{
    if (!bot)
    {
        result = "bot_unavailable";
        return false;
    }

    WorldSafeLocsEntry const* graveyard = sObjectMgr->GetClosestGraveyard(*bot, bot->GetTeam(), bot);
    if (!graveyard)
    {
        result = "graveyard_unavailable";
        return false;
    }

    bot->ResurrectPlayer(0.7f, false);
    bot->TeleportTo(graveyard->Continent, graveyard->Loc.X, graveyard->Loc.Y, graveyard->Loc.Z, bot->GetOrientation());
    result = "nearest_graveyard_resurrected";
    return true;
}

bool BotWorldPopulationMgr::TryLastSafePositionResurrect(WorldBotState& state, Player* bot, std::string& result)
{
    if (!bot)
    {
        result = "bot_unavailable";
        return false;
    }

    PruneSafePositions(state, NowMs());
    if (state.SafePositions.empty())
    {
        QueryResult stored = CharacterDatabase.PQuery(
            "SELECT map_id, x, y, z, o FROM bot_memory_safe_positions "
            "WHERE bot_guid = %u AND last_seen_at >= DATE_SUB(NOW(), INTERVAL %u SECOND) "
            "ORDER BY last_seen_at DESC LIMIT 1",
            state.Guid.GetCounter(), _config.SafePositionMemorySec);
        if (!stored)
        {
            result = "safe_position_unavailable";
            return false;
        }

        Field* fields = stored->Fetch();
        uint32 mapId = fields[0].GetUInt32();
        float x = fields[1].GetFloat();
        float y = fields[2].GetFloat();
        float z = fields[3].GetFloat();
        float o = fields[4].GetFloat();
        bot->ResurrectPlayer(0.7f, false);
        if (mapId == bot->GetMapId())
            bot->NearTeleportTo(x, y, z, o);
        else
            bot->TeleportTo(mapId, x, y, z, o);
        result = "stored_safe_position_resurrected";
        return true;
    }

    WorldBotState::SafePosition const& position = state.SafePositions.back();
    bot->ResurrectPlayer(0.7f, false);
    if (position.MapId == bot->GetMapId())
        bot->NearTeleportTo(position.X, position.Y, position.Z, position.O);
    else
        bot->TeleportTo(position.MapId, position.X, position.Y, position.Z, position.O);
    result = "last_safe_position_resurrected";
    return true;
}

bool BotWorldPopulationMgr::TryConfiguredCenterDeathFallback(Player* bot, std::string& result) const
{
    if (!bot)
    {
        result = "bot_unavailable";
        return false;
    }

    bot->ResurrectPlayer(0.7f, false);
    bot->TeleportTo(_config.MapId, _config.CenterX, _config.CenterY, _config.CenterZ, bot->GetOrientation());
    result = "configured_center_fallback";
    return true;
}

void BotWorldPopulationMgr::UpdateBot(WorldBotState& state, uint32 diff)
{
    Player* bot = GetBot(state);
    if (!bot)
        return;

    _telemetryBuffer.Observe(bot, bot->IsInCombat() ? "combat" : "ambient", nullptr, nullptr, nullptr);
    _telemetryBuffer.FlushClosedClips(_experimentId, _runId, _config.BrainVersion, bot->GetGUID());

    if (!bot->IsAlive())
    {
        state.DeadTimer += diff;
        if (state.DeadTimer == diff)
        {
            ++_metrics.Deaths;
            Unit* lastTarget = state.TargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, state.TargetGuid);
            Creature const* lastCreature = lastTarget ? lastTarget->ToCreature() : nullptr;
            bool bossDeath = lastCreature && (lastCreature->IsDungeonBoss() || lastCreature->isWorldBoss());
            char const* deathSituation = bossDeath ? (bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss") : "corpse_recovery";
            std::string raw = BuildRawJson(bot, lastTarget);
            std::string semantic = BuildSemanticJson(bot, lastTarget, deathSituation);
            MarkDeathDangerZone(state, bot, lastTarget);
            RecordEvent(state, bot, "death", nullptr, "dead", raw.c_str(), semantic.c_str(), 0.0f, _metrics.Deaths);
            if (state.RecentDeathCount >= _config.MaxDeathsBeforeFallback)
                RecordEvent(state, bot, "repeated_death", nullptr, "danger_zone", raw.c_str(), semantic.c_str(), float(state.RecentDeathCount), _metrics.Deaths);
            if (bossDeath)
            {
                BossMechanicFeatures features = BuildBossMechanicFeatures(bot, lastTarget);
                if (features.RaidEncounter)
                {
                    ++state.RaidWipes;
                    BotRolePowerBreakdown deathPower = BotLongTermProgressionBrain::CalculateRolePower(bot);
                    BotProgressionStage deathStage = BotLongTermProgressionBrain::ClassifyStage(bot, deathPower);
                    RaidRoleAssignment assignment = BuildRaidRoleAssignment(bot);
                    RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(bot, lastTarget, assignment, features);
                    RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(bot, lastTarget, assignment, features);
                    RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(bot, deathPower, deathStage);
                    HeroicRaidProgression progression = BuildHeroicRaidProgression(state, bot, deathPower, deathStage);
                    RecordRaidTelemetry(state, bot, lastTarget, "raid_wipe", "death", features, assignment, anchors, adapter, gearPlan, progression, raw.c_str(), semantic.c_str(), features.DangerScore, _metrics.Deaths);
                }
                RecordBossReplay(state, bot, lastTarget, features, "boss_mechanic_failure", raw.c_str(), semantic.c_str(), "{\"action\":\"survive_boss_mechanic\"}", "{\"reason\":\"bot_died_during_boss\"}");
            }
        }

        if (state.DeadTimer >= 5000)
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "corpse_recovery");
            RecordEvent(state, bot, "death_recovery_started", nullptr, _config.DeathRecoveryMode.c_str(), raw.c_str(), semantic.c_str(), 0.0f, state.RecentDeathCount);
            DeathRecoveryResult recovery = RecoverDeadBot(state, bot);
            state.DeadTimer = 0;
            raw = BuildRawJson(bot, nullptr);
            semantic = BuildSemanticJson(bot, nullptr, "corpse_recovery");
            if (recovery.Recovered)
            {
                PersistBotPosition(bot);
                RecordEvent(state, bot, "resurrected", nullptr, recovery.Mode.c_str(), raw.c_str(), semantic.c_str());
                if (recovery.UsedFallback)
                    RecordEvent(state, bot, "teleport_fallback_used", nullptr, recovery.Result.c_str(), raw.c_str(), semantic.c_str(), float(state.RecentDeathCount), _metrics.Deaths);
            }
            else
                RecordEvent(state, bot, "death_recovery_failed", nullptr, recovery.Result.c_str(), raw.c_str(), semantic.c_str(), float(state.RecentDeathCount), _metrics.Deaths);
        }
        return;
    }
    state.DeadTimer = 0;
    RememberSafePosition(state, bot, diff);
    RememberVisiblePois(state, bot, diff);

    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
    std::vector<BotActivityScore> activityScores = _config.EnableProgression
        ? BotLongTermProgressionBrain::ScoreActivities(bot, power, stage, _config.AllowQuesting, _config.AllowCombat, &_learningConfig)
        : std::vector<BotActivityScore>(1, BotActivityScore());
    ApplyPolicyModelScores(activityScores, bot, power, stage);
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
        MarkStuckFailure(state, bot);
        Position pos = bot->GetFirstCollisionPosition(4.0f, frand(0.0f, 2.0f * float(M_PI)));
        MoveBotToPoint(state, bot, pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ());
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
    if (target && StopDisallowedDummyCombat(state, bot, target))
        target = nullptr;

    uint32 maxHealth = bot->GetMaxHealth();
    float hpPct = maxHealth ? float(bot->GetHealth()) / float(maxHealth) : 1.0f;
    std::string situation = bot->IsInCombat() ? "open_world_combat" : "travel";
    std::string action = "wander";
    QuestActionResult questAction;
    BossMechanicActionResult bossAction;
    DungeonTrashActionResult trashAction;
    QuestObjectivePlan activePlanForPriority;
    bool hasActiveQuestObjective = (state.QuestWork.ActiveQuestId && FindQuestObjective(bot, state.QuestWork.ActiveQuestId, activePlanForPriority))
        || (state.NewlyAcceptedQuestId && FindQuestObjective(bot, state.NewlyAcceptedQuestId, activePlanForPriority))
        || FindActiveQuestObjective(bot, activePlanForPriority);
    bool hasNearbyQuestGiver = _config.AllowQuesting && HasNearbySupportedQuestGiver(bot, state);

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
        && (chosenActivity.Activity == BotProgressionActivity::Questing || hasActiveQuestObjective || _config.QuestFirst || state.NewlyAcceptedQuestId || hasNearbyQuestGiver)
        && [&]() { questAction = TryQuesting(state, bot, power, stage, chosenActivity.Activity); return questAction.Handled; }())
    {
        situation = questAction.Situation;
        action = questAction.Action;
        target = questAction.Target;
    }
    else if (IsBossContext(bot, target)
        && [&]() { bossAction = TryBossMechanics(state, bot, power, stage, chosenActivity.Activity); return bossAction.Handled; }())
    {
        situation = bossAction.Situation;
        action = bossAction.Action;
        target = bossAction.Target;
    }
    else if (IsDungeonTrashContext(bot, target)
        && [&]() { trashAction = TryDungeonTrash(state, bot, power, stage, chosenActivity.Activity); return trashAction.Handled; }())
    {
        situation = trashAction.Situation;
        action = trashAction.Action;
        target = trashAction.Target;
    }
    else if (target && target->IsAlive())
    {
        char const* rejectReason = nullptr;
        if (!bot->IsInCombat() && !IsQuestRelevantTarget(bot, target) && !IsProgressionCombatTarget(bot, target, &rejectReason))
        {
            state.LastRejectedTargetReason = rejectReason ? rejectReason : "not_progression_relevant";
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "target_rejected", &power, stage, chosenActivity.Activity);
            RecordEvent(state, bot, "target_rejected", target, state.LastRejectedTargetReason.c_str(), raw.c_str(), semantic.c_str());
            bot->AttackStop();
            bot->CombatStop(true);
            state.TargetGuid.Clear();
            target = nullptr;
            situation = "target_rejected";
            action = "clear_non_progression_target";
        }
        else
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
    }
    else if (target && !target->IsAlive())
    {
        BotActionExecutor executor;
        if (Creature const* creature = target->ToCreature())
            situation = (creature->IsDungeonBoss() || creature->isWorldBoss()) ? (bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss") : "open_world_combat";
        else
            situation = "open_world_combat";

        if (!bot->IsWithinDistInMap(target, INTERACTION_DISTANCE))
        {
            MoveBotToPoint(state, bot, target->GetPositionX(), target->GetPositionY(), target->GetPositionZ());
            action = "move_to_loot";
            SetQuestWorkPhase(state, "move_to_loot");
        }
        else if (state.NextLootAttemptMs > NowMs())
        {
            action = "loot_cooldown";
        }
        else
        {
            action = "loot_target";
            SetQuestWorkPhase(state, "loot_target");
            if (state.LastKilledTargetGuid != target->GetGUID())
            {
                ++_metrics.Kills;
                state.LastKilledTargetGuid = target->GetGUID();
            }

            ++state.LootAttemptCount;
            state.LootStartedMs = NowMs();
            BotActionExecutor::LootResult loot = executor.AutoLoot(bot, target);
            state.LootCompletedMs = NowMs();
            state.LastLootTargetGuid = target->GetGUID();
            state.LastLootResult = loot.Reason.empty() ? ToString(loot.Result) : loot.Reason;
            state.LastLootItemsCount = loot.ItemsCount;
            state.LastLootMoney = loot.Money;
            state.LastLootStateCleared = loot.LootStateCleared;
            state.NextLootAttemptMs = NowMs() + (loot.Result == BotActionResult::OutOfRange ? 0 : 2500);

            QuestObjectivePlan lootPlan;
            bool hadLootPlan = FindActiveQuestObjective(bot, lootPlan);
            if (!hadLootPlan && state.QuestWork.ActiveQuestId)
                hadLootPlan = GetQuestObjectivePlan(bot, state.QuestWork.ActiveQuestId, state.QuestWork.ObjectiveIndex,
                    state.QuestWork.ObjectiveType == "collect_item" ? QuestObjectiveType::CollectItem :
                    (state.QuestWork.ObjectiveType == "use_item_on_target" ? QuestObjectiveType::UseItemOnTarget :
                    (state.QuestWork.ObjectiveType == "use_ability_on_dummy" ? QuestObjectiveType::UseAbilityOnDummy :
                    (state.QuestWork.ObjectiveType == "cast_spell_on_target" ? QuestObjectiveType::CastSpellOnTarget :
                    (state.QuestWork.ObjectiveType == "interact_gameobject" ? QuestObjectiveType::InteractGameObject : QuestObjectiveType::Kill)))), lootPlan);
            if (!hadLootPlan && state.QuestWork.ActiveQuestId)
            {
                lootPlan.QuestId = state.QuestWork.ActiveQuestId;
                lootPlan.ObjectiveIndex = state.QuestWork.ObjectiveIndex;
                lootPlan.RequiredEntry = state.QuestWork.RequiredEntry;
                lootPlan.ItemId = state.QuestWork.RequiredItem;
                lootPlan.RequiredSpellId = state.QuestWork.RequiredSpell;
                lootPlan.RequiredCount = state.QuestWork.RequiredCount;
                lootPlan.CurrentCount = state.QuestWork.CurrentCount;
                lootPlan.IsItemObjective = state.QuestWork.ObjectiveType == "collect_item" || state.QuestWork.ObjectiveType == "use_item_on_target";
                lootPlan.IsGameObject = state.QuestWork.ObjectiveType == "interact_gameobject";
                lootPlan.ObjectiveType = state.QuestWork.ObjectiveType == "collect_item" ? QuestObjectiveType::CollectItem :
                    (state.QuestWork.ObjectiveType == "use_item_on_target" ? QuestObjectiveType::UseItemOnTarget :
                    (state.QuestWork.ObjectiveType == "use_ability_on_dummy" ? QuestObjectiveType::UseAbilityOnDummy :
                    (state.QuestWork.ObjectiveType == "cast_spell_on_target" ? QuestObjectiveType::CastSpellOnTarget :
                    (state.QuestWork.ObjectiveType == "interact_gameobject" ? QuestObjectiveType::InteractGameObject : QuestObjectiveType::Kill))));
                hadLootPlan = true;
            }
            uint32 progressBefore = state.QuestWork.ProgressBefore ? state.QuestWork.ProgressBefore : state.LastQuestProgressBefore;
            if (!progressBefore && hadLootPlan)
                progressBefore = QuestObjectiveProgress(bot, lootPlan);

            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, chosenActivity.Activity);
            RecordEvent(state, bot, (situation == "dungeon_boss" || situation == "raid_boss") ? "boss_killed" : "mob_killed", target, "ok", raw.c_str(), semantic.c_str(), 0.0f, _metrics.Kills);
            if (situation == "raid_boss")
            {
                ++state.RaidBossKills;
                ++_metrics.RaidBossKills;
                if (stage == BotProgressionStage::HeroicRaid)
                {
                    ++state.HeroicRaidBossKills;
                    ++_metrics.HeroicRaidBossKills;
                }

                BossMechanicFeatures features = BuildBossMechanicFeatures(bot, target);
                RaidRoleAssignment assignment = BuildRaidRoleAssignment(bot);
                RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(bot, target, assignment, features);
                RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(bot, target, assignment, features);
                RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(bot, power, stage);
                HeroicRaidProgression progression = BuildHeroicRaidProgression(state, bot, power, stage);
                RecordRaidTelemetry(state, bot, target, "raid_boss_killed", "ok", features, assignment, anchors, adapter, gearPlan, progression, raw.c_str(), semantic.c_str(), power.Total, _metrics.RaidBossKills);
            }

            if (loot.Result == BotActionResult::Ok && (loot.ItemsCount || loot.Money))
                RecordEvent(state, bot, "loot_received", target, loot.Reason.c_str(), raw.c_str(), semantic.c_str(), float(loot.Money), loot.ItemsCount);
            else if (loot.Result == BotActionResult::NoAction)
                RecordEvent(state, bot, "loot_empty", target, loot.Reason.c_str(), raw.c_str(), semantic.c_str(), 0.0f, 0);
            else
            {
                RecordEvent(state, bot, "loot_failed", target, loot.Reason.c_str(), raw.c_str(), semantic.c_str(), 0.0f, uint32(loot.Result));
                if (state.LootAttemptCount < 3)
                    return;
            }

            if (hadLootPlan)
                VerifyQuestObjectiveProgress(state, bot, lootPlan, target, progressBefore, "kill_or_loot_verified", raw.c_str(), semantic.c_str());

            BotGearUpgradeEvaluation gear = BotLongTermProgressionBrain::EvaluateGearUpgrade(bot);
            RecordGearEvaluation(state, bot, gear, raw.c_str(), semantic.c_str());
            if (loot.Result == BotActionResult::Ok || loot.Result == BotActionResult::NoAction || state.LootAttemptCount >= 3)
            {
                state.TargetGuid.Clear();
                state.WasInCombat = false;
                state.LootAttemptCount = 0;
                SetQuestWorkPhase(state, "verify_progress");
            }
        }
    }
    else if (IsGenericGrindingAllowed(state, bot, chosenActivity.Activity, hasActiveQuestObjective) && (target = SelectSafeTarget(state, bot)))
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
    bool failure = questAction.Failure || trashAction.Failure || bossAction.Failure;
    bool rare = questAction.Rare || trashAction.Rare || bossAction.Rare;
    RecordDecision(state, bot, situation.c_str(), action.c_str(), target, raw.c_str(), semantic.c_str(), activityScores, chosenActivity, power, failure, rare);
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

bool BotWorldPopulationMgr::IsQuestRelevantTarget(Player* bot, Unit* target) const
{
    Creature const* creature = target ? target->ToCreature() : nullptr;
    if (!bot || !creature)
        return false;

    uint32 entry = creature->GetEntry();
    for (auto const& questStatus : bot->getQuestStatusMap())
    {
        if (questStatus.second.Status != QUEST_STATUS_INCOMPLETE)
            continue;

        Quest const* quest = sObjectMgr->GetQuestTemplate(questStatus.first);
        if (!quest)
            continue;

        for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
            if (quest->RequiredNpcOrGo[i] > 0 && uint32(quest->RequiredNpcOrGo[i]) == entry && questStatus.second.CreatureOrGOCount[i] < quest->RequiredNpcOrGoCount[i])
                return true;

        for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
        {
            uint32 itemId = quest->RequiredItemId[i];
            if (!itemId || questStatus.second.ItemCount[i] >= quest->RequiredItemCount[i])
                continue;
            std::vector<uint32> const* questItems = sObjectMgr->GetCreatureQuestItemList(entry);
            if (questItems && std::find(questItems->begin(), questItems->end(), itemId) != questItems->end())
                return true;
        }
    }

    return false;
}

bool BotWorldPopulationMgr::IsProgressionCombatTarget(Player* bot, Unit* target, char const** rejectReason) const
{
    auto reject = [rejectReason](char const* reason) -> bool
    {
        if (rejectReason)
            *rejectReason = reason;
        return false;
    };

    if (!bot || !target || !target->IsAlive() || !bot->IsValidAttackTarget(target) || !bot->IsWithinLOSInMap(target))
        return reject("not_progression_relevant");
    if (!bot->IsWithinDistInMap(target, 30.0f))
        return reject("not_progression_relevant");

    Creature const* creature = target->ToCreature();
    if (!creature)
        return reject("ambient");
    CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
    bool questRelevant = IsQuestRelevantTarget(bot, target);

    if (creature->IsCritter() || (tmpl && tmpl->type == CREATURE_TYPE_CRITTER))
        return reject("critter");
    if (creature->IsPet() || creature->IsTotem() || creature->IsSummon() || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
        return reject("pet_or_totem");
    if (IsTrainingDummy(target) && !questRelevant)
        return reject("dummy_without_quest");
    if (creature->IsSpiritService() || creature->IsServiceProvider() || (tmpl && (tmpl->unit_flags & (UNIT_FLAG_NON_ATTACKABLE | UNIT_FLAG_PACIFIED | UNIT_FLAG_IMMUNE_TO_PC))))
        return reject("ambient");
    if (!questRelevant && creature->HasFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_TAPPED) && !creature->HasFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_TAPPED_BY_PLAYER))
        return reject("no_loot");
    if (creature->isElite() && !(bot->GetMap() && (bot->GetMap()->IsDungeon() || bot->GetMap()->IsRaid())) && !bot->GetGroup())
        return reject("not_progression_relevant");

    bool givesXp = bot->isHonorOrXPTarget(target);
    bool hasLoot = tmpl && (tmpl->lootid || tmpl->pickpocketLootId || tmpl->SkinLootId || tmpl->mingold || tmpl->maxgold);
    if (!questRelevant && !givesXp)
        return reject("no_xp");

    if (!questRelevant && !hasLoot)
        return reject("no_loot");

    if (!questRelevant && !givesXp && !hasLoot)
        return reject("not_progression_relevant");

    if (!questRelevant && creature->GetReactionTo(bot) >= REP_NEUTRAL)
        return reject("not_progression_relevant");

    return true;
}

Unit* BotWorldPopulationMgr::SelectSafeTarget(WorldBotState& state, Player* bot)
{
    if (!bot)
        return nullptr;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 30.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 30.0f);

    Unit* best = nullptr;
    float bestScore = -100000.0f;
    for (WorldObject* object : objects)
    {
        Unit* target = object ? object->ToUnit() : nullptr;
        if (target && IsTrainingDummy(target) && !IsQuestRelevantTarget(bot, target))
        {
            state.LastRejectedTargetReason = "dummy_without_quest";
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "target_rejected");
            RecordEvent(state, bot, "target_rejected", target, "dummy_without_quest", raw.c_str(), semantic.c_str());
            continue;
        }
        char const* rejectReason = nullptr;
        if (!IsProgressionCombatTarget(bot, target, &rejectReason))
        {
            if (target && rejectReason)
            {
                state.LastRejectedTargetReason = rejectReason;
                std::string raw = BuildRawJson(bot, target);
                std::string semantic = BuildSemanticJson(bot, target, "target_rejected");
                RecordEvent(state, bot, "target_rejected", target, rejectReason, raw.c_str(), semantic.c_str());
            }
            continue;
        }

        if (Creature* creature = target->ToCreature())
            if (creature->isElite())
                continue;

        int32 levelDelta = int32(target->getLevel()) - int32(bot->getLevel());
        if (levelDelta > 1)
            continue;

        float dist = target->GetExactDist(bot);
        if (dist > 25.0f)
            continue;

        BotLearnedScore learned = BotExperienceLearningPolicy::ScoreMob(bot, target, _learningConfig);
        float score = 100.0f - dist - std::max<int32>(0, levelDelta) * 20.0f + learned.Score;
        if (!best || score > bestScore)
        {
            best = target;
            bestScore = score;
        }
    }

    return best;
}

bool BotWorldPopulationMgr::IsDummyEntryConfigured(uint32 entry, bool* explicitAllow) const
{
    if (explicitAllow)
        *explicitAllow = false;
    if (!entry || _config.TrainingDummyEntries.empty())
        return false;

    std::stringstream entries(_config.TrainingDummyEntries);
    std::string token;
    while (std::getline(entries, token, ','))
    {
        token.erase(std::remove_if(token.begin(), token.end(), [](unsigned char c) { return std::isspace(c); }), token.end());
        if (token.empty())
            continue;
        bool deny = token[0] == '!' || token[0] == '-';
        if (deny)
            token.erase(token.begin());
        if (token.empty() || token.find_first_not_of("0123456789") != std::string::npos)
            continue;
        if (uint32(strtoul(token.c_str(), nullptr, 10)) != entry)
            continue;
        if (explicitAllow)
            *explicitAllow = !deny;
        return true;
    }

    return false;
}

bool BotWorldPopulationMgr::IsTrainingDummy(Unit const* unit) const
{
    Creature const* creature = unit ? unit->ToCreature() : nullptr;
    if (!creature)
        return false;

    bool explicitAllow = false;
    if (IsDummyEntryConfigured(creature->GetEntry(), &explicitAllow))
        return explicitAllow;

    CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
    if (!tmpl)
        return false;

    if ((tmpl->unit_flags & (UNIT_FLAG_PACIFIED | UNIT_FLAG_IMMUNE_TO_NPC)) || (tmpl->unit_flags2 & UNIT_FLAG2_CANNOT_TURN))
        if (ContainsInsensitive(tmpl->Name, "training dummy"))
            return true;

    return ContainsInsensitive(tmpl->Name, "training dummy");
}

bool BotWorldPopulationMgr::IsTrainingDummyAllowedForQuest(QuestObjectivePlan const& plan, Unit const* target) const
{
    if (!target || !IsTrainingDummy(target))
        return false;
    Creature const* creature = target->ToCreature();
    if (!creature)
        return false;
    if (plan.RequiredEntry > 0 && uint32(plan.RequiredEntry) == creature->GetEntry())
        return true;
    return plan.ObjectiveType == QuestObjectiveType::UseAbilityOnDummy || plan.RequiresTrainingDummy;
}

bool BotWorldPopulationMgr::QuestTextSuggestsAbilityObjective(Quest const* quest) const
{
    if (!quest)
        return false;

    std::string text = quest->GetTitle() + " " + quest->GetObjectives() + " " + quest->GetDetails();
    for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
        text += " " + quest->ObjectiveText[i];

    bool mentionsDummy = ContainsInsensitive(text, "training dummy") || ContainsInsensitive(text, "dummy");
    bool mentionsAction = ContainsInsensitive(text, "cast") || ContainsInsensitive(text, "use ") || ContainsInsensitive(text, "practice")
        || ContainsInsensitive(text, "ability") || ContainsInsensitive(text, "spell") || ContainsInsensitive(text, "sinister strike")
        || ContainsInsensitive(text, "steady shot") || ContainsInsensitive(text, "fireball") || ContainsInsensitive(text, "smite");
    return mentionsDummy && mentionsAction;
}

uint32 BotWorldPopulationMgr::SelectQuestAbilitySpell(Player* bot, Quest const* quest, QuestObjectivePlan const& plan) const
{
    if (!bot)
        return 0;
    if (plan.RequiredSpellId && bot->HasSpell(plan.RequiredSpellId))
        return plan.RequiredSpellId;

    std::string text;
    if (quest)
        text = LowerCopy(quest->GetTitle() + " " + quest->GetObjectives() + " " + quest->GetDetails());

    struct Candidate { uint32 SpellId; char const* Name; };
    Candidate named[] =
    {
        { 1752, "sinister strike" },
        { 56641, "steady shot" },
        { 133, "fireball" },
        { 585, "smite" },
        { 5176, "wrath" },
        { 403, "lightning bolt" },
        { 78, "heroic strike" }
    };
    for (Candidate const& candidate : named)
        if ((!text.empty() && text.find(candidate.Name) != std::string::npos) && bot->HasSpell(candidate.SpellId))
            return candidate.SpellId;

    uint32 candidates[4] = { 0, 0, 0, 0 };
    switch (bot->getClass())
    {
        case CLASS_MAGE: candidates[0] = 133; break;
        case CLASS_PRIEST: candidates[0] = 585; break;
        case CLASS_WARLOCK: candidates[0] = 686; break;
        case CLASS_DRUID: candidates[0] = 5176; break;
        case CLASS_SHAMAN: candidates[0] = 403; break;
        case CLASS_PALADIN: candidates[0] = 20271; break;
        case CLASS_HUNTER: candidates[0] = 75; break;
        case CLASS_DEATH_KNIGHT: candidates[0] = 45477; candidates[1] = 45462; break;
        case CLASS_WARRIOR: candidates[0] = 78; break;
        case CLASS_ROGUE: candidates[0] = 1752; break;
        default: break;
    }
    for (uint32 spellId : candidates)
        if (spellId && bot->HasSpell(spellId))
            return spellId;
    return 0;
}

uint32 BotWorldPopulationMgr::QuestObjectiveProgress(Player* bot, QuestObjectivePlan const& plan) const
{
    if (!bot)
        return 0;
    auto itr = bot->getQuestStatusMap().find(plan.QuestId);
    if (itr == bot->getQuestStatusMap().end())
        return 0;
    if (plan.IsItemObjective)
        return plan.ObjectiveIndex < QUEST_ITEM_OBJECTIVES_COUNT ? itr->second.ItemCount[plan.ObjectiveIndex] : 0;
    return plan.ObjectiveIndex < QUEST_OBJECTIVES_COUNT ? itr->second.CreatureOrGOCount[plan.ObjectiveIndex] : 0;
}

bool BotWorldPopulationMgr::GetQuestObjectivePlan(Player* bot, uint32 questId, uint32 objectiveIndex, QuestObjectiveType type, QuestObjectivePlan& plan) const
{
    if (!bot || !questId)
        return false;

    QuestObjectivePlan active;
    if (!FindQuestObjective(bot, questId, active))
        return false;
    if (active.QuestId != questId || active.ObjectiveIndex != objectiveIndex || active.ObjectiveType != type)
        return false;

    plan = active;
    return true;
}

void BotWorldPopulationMgr::SetQuestWorkPhase(WorldBotState& state, char const* phase)
{
    std::string next = phase ? phase : "idle";
    if (state.QuestWork.Phase != next)
    {
        state.QuestWork.Phase = next;
        state.QuestWork.PhaseStartedMs = NowMs();
    }
    state.CurrentQuestState = state.QuestWork.Phase;
}

void BotWorldPopulationMgr::SetQuestWorkFromPlan(WorldBotState& state, QuestObjectivePlan const& plan)
{
    bool changed = state.QuestWork.ActiveQuestId != plan.QuestId
        || state.QuestWork.ObjectiveIndex != plan.ObjectiveIndex
        || state.QuestWork.ObjectiveType != ToString(plan.ObjectiveType);
    if (changed)
    {
        state.QuestWork.SelectedTargetGuid.Clear();
        state.QuestWork.SelectedObjectGuid.Clear();
        state.QuestWork.RetryCount = 0;
        state.QuestWork.VerifiedCasts = 0;
        state.QuestWork.VerifyAfterMs = 0;
        state.QuestWork.FailedReason.clear();
        state.QuestWork.PhaseStartedMs = NowMs();
    }

    state.QuestWork.ActiveQuestId = plan.QuestId;
    state.QuestWork.ObjectiveIndex = plan.ObjectiveIndex;
    state.QuestWork.ObjectiveType = ToString(plan.ObjectiveType);
    state.QuestWork.RequiredEntry = plan.RequiredEntry;
    state.QuestWork.RequiredItem = plan.ItemId;
    state.QuestWork.RequiredSpell = plan.RequiredSpellId;
    state.QuestWork.RequiredCount = plan.RequiredCount;
    state.QuestWork.CurrentCount = plan.CurrentCount;
    state.CurrentObjectiveType = state.QuestWork.ObjectiveType;
    state.RequiredSpellId = plan.RequiredSpellId;
    state.RequiredItemId = plan.ItemId;
    state.RequiredTargetEntry = plan.RequiredEntry > 0 ? uint32(plan.RequiredEntry) : 0;
}

void BotWorldPopulationMgr::ResetQuestWork(WorldBotState& state)
{
    state.QuestWork = WorldBotState::BotQuestWorkState();
    state.NewlyAcceptedQuestId = 0;
    state.RecentlyAcceptedQuestUntilMs = 0;
    state.ObjectiveSearchUntilMs = 0;
    state.CurrentQuestState = "idle";
    state.CurrentObjectiveType = "none";
    state.RequiredSpellId = 0;
    state.RequiredItemId = 0;
    state.RequiredTargetEntry = 0;
}

bool BotWorldPopulationMgr::VerifyQuestObjectiveProgress(WorldBotState& state, Player* bot, QuestObjectivePlan const& plan, Unit const* target, uint32 before, char const* reason, char const* rawJson, char const* semanticJson)
{
    uint32 after = QuestObjectiveProgress(bot, plan);
    bool completed = bot && bot->CanCompleteQuest(plan.QuestId);
    state.LastQuestProgressBefore = before;
    state.LastQuestProgressAfter = after;
    state.QuestWork.ProgressBefore = before;
    state.QuestWork.ProgressAfter = after;
    state.QuestWork.CurrentCount = after;

    if (after > before || completed)
    {
        ++_metrics.QuestObjectiveProgress;
        state.LastQuestObjectiveProgress = _metrics.QuestObjectiveProgress;
        state.QuestWork.LastProgressMs = NowMs();
        state.QuestWork.RetryCount = 0;
        state.QuestWork.VerifiedCasts = 0;
        state.LastNoProgressReason.clear();
        RecordQuestEvent(state, bot, "objective_progress", plan.QuestId, target, reason ? reason : ToString(plan.ObjectiveType), rawJson, semanticJson, after, plan.ItemId);
        if (completed)
            bot->CompleteQuest(plan.QuestId);
        return true;
    }

    ++state.QuestWork.RetryCount;
    state.LastNoProgressReason = reason ? reason : "no_counter_change";
    std::ostringstream cooldownKey;
    cooldownKey << plan.QuestId << ":" << plan.ObjectiveIndex << ":" << ToString(plan.ObjectiveType) << ":";
    if (target)
        cooldownKey << target->GetGUID().GetCounter();
    else
        cooldownKey << 0;
    state.NoProgressCooldownUntilMs[cooldownKey.str()] = NowMs() + 45000;

    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();
    std::ostringstream context;
    context << "{\"quest_id\":" << plan.QuestId
            << ",\"objective_index\":" << plan.ObjectiveIndex
            << ",\"objective_type\":\"" << JsonEscape(ToString(plan.ObjectiveType)) << "\""
            << ",\"required_entry\":" << (plan.RequiredEntry > 0 ? uint32(plan.RequiredEntry) : 0)
            << ",\"required_item\":" << plan.ItemId
            << ",\"target_entry\":" << targetEntry
            << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
            << ",\"progress_before\":" << before
            << ",\"progress_after\":" << after
            << ",\"reason\":\"" << JsonEscape(state.LastNoProgressReason) << "\"}";
    RecordQuestEvent(state, bot, "objective_no_progress", plan.QuestId, target, state.LastNoProgressReason.c_str(), rawJson, semanticJson, after, plan.ItemId, context.str().c_str());
    return false;
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
        float bestDist = -100000.0f;
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!creature || !creature->IsAlive() || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
                continue;
            if (IsTrainingDummy(creature) && !IsTrainingDummyAllowedForQuest(plan, creature))
                continue;

            std::vector<uint32> const* questItems = sObjectMgr->GetCreatureQuestItemList(creature->GetEntry());
            if (!questItems || std::find(questItems->begin(), questItems->end(), plan.ItemId) == questItems->end())
                continue;

            if (creature->isElite())
                continue;
            if (int32(creature->getLevel()) - int32(bot->getLevel()) > 1)
                continue;

            BotLearnedScore learned = BotExperienceLearningPolicy::ScoreMob(bot, creature, _learningConfig);
            float dist = bot->GetExactDist(creature);
            float score = 100.0f - dist + learned.Score;
            if (!best || score > bestDist)
            {
                best = creature;
                bestDist = score;
            }
        }

        if (best)
            return best;
    }

    if (!plan.RequiredEntry)
        return nullptr;

    std::vector<Creature*> creatures;
    bot->GetCreatureListWithEntryInGrid(creatures, uint32(plan.RequiredEntry), 60.0f);
    Creature* best = nullptr;
    float bestDist = -100000.0f;
    for (Creature* creature : creatures)
    {
        if (!creature || !creature->IsAlive() || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
            continue;
        if (IsTrainingDummy(creature) && !IsTrainingDummyAllowedForQuest(plan, creature))
            continue;
        std::ostringstream cooldownKey;
        cooldownKey << plan.QuestId << ":" << plan.ObjectiveIndex << ":" << ToString(plan.ObjectiveType) << ":" << creature->GetGUID().GetCounter();
        auto cooldown = [&]() -> uint64
        {
            for (WorldBotState const& state : _bots)
                if (state.Guid == bot->GetGUID())
                {
                    auto itr = state.NoProgressCooldownUntilMs.find(cooldownKey.str());
                    return itr != state.NoProgressCooldownUntilMs.end() ? itr->second : 0;
                }
            return 0;
        }();
        if (cooldown > NowMs())
            continue;
        if (creature->isElite())
            continue;
        if (int32(creature->getLevel()) - int32(bot->getLevel()) > 1)
            continue;

        BotLearnedScore learned = BotExperienceLearningPolicy::ScoreMob(bot, creature, _learningConfig);
        float dist = bot->GetExactDist(creature);
        float score = 100.0f - dist + learned.Score;
        if (!best || score > bestDist)
        {
            best = creature;
            bestDist = score;
        }
    }

    return best;
}

Unit* BotWorldPopulationMgr::SelectQuestAbilityObjectiveTarget(Player* bot, QuestObjectivePlan const& plan, WorldBotState const& state) const
{
    if (!bot)
        return nullptr;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 70.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 70.0f);

    uint64 now = NowMs();
    Unit* best = nullptr;
    float bestDist = 0.0f;
    for (WorldObject* object : objects)
    {
        Unit* target = object ? object->ToUnit() : nullptr;
        Creature const* creature = target ? target->ToCreature() : nullptr;
        if (!target || !creature || !target->IsAlive() || !bot->IsValidAttackTarget(target) || !bot->IsWithinLOSInMap(target))
            continue;
        if (plan.RequiredEntry > 0 && creature->GetEntry() != uint32(plan.RequiredEntry))
            continue;
        if (plan.RequiresTrainingDummy && !IsTrainingDummy(target))
            continue;
        if (IsTrainingDummy(target) && !IsTrainingDummyAllowedForQuest(plan, target))
            continue;
        auto cooldown = state.DummyTargetCooldownUntilMs.find(target->GetGUID().GetCounter());
        if (cooldown != state.DummyTargetCooldownUntilMs.end() && cooldown->second > now)
            continue;
        std::ostringstream abilityKey;
        abilityKey << plan.QuestId << ":" << plan.RequiredSpellId << ":" << target->GetGUID().GetCounter();
        auto abilityCooldown = state.AbilityObjectiveCooldownUntilMs.find(abilityKey.str());
        if (abilityCooldown != state.AbilityObjectiveCooldownUntilMs.end() && abilityCooldown->second > now)
            continue;

        float dist = bot->GetExactDist(target);
        if (!best || dist < bestDist)
        {
            best = target;
            bestDist = dist;
        }
    }

    return best;
}

bool BotWorldPopulationMgr::StopDisallowedDummyCombat(WorldBotState& state, Player* bot, Unit* target)
{
    if (!bot || !target || !IsTrainingDummy(target))
        return false;

    QuestObjectivePlan plan;
    bool allowed = FindActiveQuestObjective(bot, plan) && IsTrainingDummyAllowedForQuest(plan, target)
        && (plan.ObjectiveType == QuestObjectiveType::UseAbilityOnDummy || plan.ObjectiveType == QuestObjectiveType::CastSpellOnTarget);
    if (allowed)
        return false;

    bot->AttackStop();
    bot->CombatStop(true);
    bot->ClearUnitState(UNIT_STATE_CHASE);
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
    state.TargetGuid.Clear();
    state.WasInCombat = false;
    state.DummyTargetCooldownUntilMs[target->GetGUID().GetCounter()] = NowMs() + 30000;
    state.LastRejectedTargetReason = "training_dummy_without_ability_objective";
    state.CurrentTargetIsTrainingDummy = true;
    state.CurrentDummyAllowedByQuest = false;

    std::string raw = BuildRawJson(bot, target);
    std::string semantic = BuildSemanticJson(bot, target, "dummy_target_rejected");
    RecordEvent(state, bot, "dummy_target_rejected", target, "not_active_ability_objective", raw.c_str(), semantic.c_str());
    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    std::vector<BotActivityScore> activities = BotLongTermProgressionBrain::ScoreActivities(bot, power, BotLongTermProgressionBrain::ClassifyStage(bot, power), _config.AllowQuesting, _config.AllowCombat, &_learningConfig);
    BotActivityScore chosen = BotLongTermProgressionBrain::ChooseActivity(activities);
    RecordDecision(state, bot, "dummy_target_rejected", "return_to_quest_state_machine", target, raw.c_str(), semantic.c_str(), activities, chosen, power, true, true);
    return true;
}

WorldObject* BotWorldPopulationMgr::SelectQuestGiver(Player* bot, bool completeOnly, uint32* questId, WorldBotState const* state) const
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

            if (!completeOnly && state)
            {
                auto giverCooldown = state->QuestGiverCooldownUntilMs.find(object->GetGUID().GetCounter());
                if (giverCooldown != state->QuestGiverCooldownUntilMs.end() && giverCooldown->second > NowMs())
                    continue;
                auto questCooldown = state->QuestCooldownUntilMs.find(candidateQuestId);
                if (questCooldown != state->QuestCooldownUntilMs.end() && questCooldown->second > NowMs())
                    continue;
            }

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
            BotLearnedScore learned = BotExperienceLearningPolicy::ScoreQuest(bot, candidateQuestId, _learningConfig);
            float areaDanger = BotExperienceLearningPolicy::ScoreArea(bot, object->GetAreaId(), _learningConfig).Score;
            float score = (completeOnly ? 1000.0f : 100.0f) - dist + learned.Score + areaDanger;
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

    bool found = false;
    float bestScore = -100000.0f;
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

            BotLearnedScore learned = BotExperienceLearningPolicy::ScoreQuest(bot, quest->GetQuestId(), _learningConfig);
            float progress = requiredCount ? float(questStatus.second.CreatureOrGOCount[i]) / float(requiredCount) : 0.0f;
            float score = 25.0f + progress * 10.0f + learned.Score;
            if (!found || score > bestScore)
            {
                plan = QuestObjectivePlan();
                plan.QuestId = quest->GetQuestId();
                plan.RequiredEntry = required;
                plan.RequiredCount = requiredCount;
                plan.CurrentCount = questStatus.second.CreatureOrGOCount[i];
                plan.IsGameObject = required < 0;
                plan.ObjectiveIndex = i;
                if (plan.IsGameObject)
                    plan.ObjectiveType = QuestObjectiveType::InteractGameObject;
                else
                {
                    CreatureTemplate const* tmpl = required > 0 ? sObjectMgr->GetCreatureTemplate(uint32(required)) : nullptr;
                    bool configuredDummy = false;
                    bool configuredDummyAllowed = false;
                    if (tmpl)
                        configuredDummy = IsDummyEntryConfigured(tmpl->Entry, &configuredDummyAllowed);
                    bool dummyRequired = tmpl && (ContainsInsensitive(tmpl->Name, "training dummy") || (configuredDummy && configuredDummyAllowed));
                    if (dummyRequired && QuestTextSuggestsAbilityObjective(quest))
                    {
                        plan.ObjectiveType = QuestObjectiveType::UseAbilityOnDummy;
                        plan.RequiresTrainingDummy = true;
                        plan.RequiredSpellId = SelectQuestAbilitySpell(bot, quest, plan);
                    }
                }
                found = true;
                bestScore = score;
            }
        }

        for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
        {
            uint32 requiredItem = quest->RequiredItemId[i];
            uint32 requiredCount = quest->RequiredItemCount[i];
            if (!requiredItem || !requiredCount || questStatus.second.ItemCount[i] >= requiredCount)
                continue;

            BotLearnedScore learned = BotExperienceLearningPolicy::ScoreQuest(bot, quest->GetQuestId(), _learningConfig);
            float progress = requiredCount ? float(questStatus.second.ItemCount[i]) / float(requiredCount) : 0.0f;
            float score = 20.0f + progress * 10.0f + learned.Score;
            if (!found || score > bestScore)
            {
                plan = QuestObjectivePlan();
                plan.QuestId = quest->GetQuestId();
                plan.RequiredCount = requiredCount;
                plan.CurrentCount = questStatus.second.ItemCount[i];
                plan.IsItemObjective = true;
                plan.ItemId = requiredItem;
                plan.ObjectiveIndex = i;
                plan.ObjectiveType = QuestTextSuggestsAbilityObjective(quest) ? QuestObjectiveType::UseItemOnTarget : QuestObjectiveType::CollectItem;
                found = true;
                bestScore = score;
            }
        }
    }

    return found;
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

bool BotWorldPopulationMgr::HasNearbySupportedQuestGiver(Player* bot, WorldBotState const& state) const
{
    uint32 questId = 0;
    return SelectQuestGiver(bot, false, &questId, &state) != nullptr;
}

bool BotWorldPopulationMgr::IsGenericGrindingAllowed(WorldBotState& state, Player* bot, BotProgressionActivity activity, bool hasActiveQuestObjective)
{
    state.LastGrindingAllowedReason.clear();
    if (!_config.AllowCombat)
    {
        state.LastGrindingAllowedReason = "combat_disabled";
        return false;
    }
    if (!_config.AllowGrinding)
    {
        state.LastGrindingAllowedReason = "grinding_disabled";
        return false;
    }
    if (hasActiveQuestObjective || state.QuestWork.ActiveQuestId)
    {
        state.LastGrindingAllowedReason = "active_quest_objective";
        return false;
    }
    if (state.RecentlyAcceptedQuestUntilMs > NowMs())
    {
        state.LastGrindingAllowedReason = "recently_accepted_quest";
        return false;
    }
    if (!state.QuestWork.SelectedTargetGuid.IsEmpty() || !state.QuestWork.SelectedObjectGuid.IsEmpty() || state.ObjectiveSearchUntilMs > NowMs())
    {
        state.LastGrindingAllowedReason = "known_objective_target";
        return false;
    }
    if (_config.GrindOnlyWhenNoQuestAvailable && HasNearbySupportedQuestGiver(bot, state))
    {
        state.LastGrindingAllowedReason = "nearby_supported_quest";
        return false;
    }
    if (activity != BotProgressionActivity::Grinding && activity != BotProgressionActivity::ExperimentExploration)
    {
        state.LastGrindingAllowedReason = "activity_not_grinding";
        return false;
    }

    state.LastGrindingAllowedReason = activity == BotProgressionActivity::Grinding ? "explicit_grinding" : "experiment_exploration_combat_allowed";
    return true;
}

void BotWorldPopulationMgr::MoveToObjectiveSearchPoint(WorldBotState& state, Player* bot, QuestObjectivePlan const* plan, WorldObject const* avoidObject)
{
    if (!bot)
        return;

    uint64 now = NowMs();
    if (state.ObjectiveSearchUntilMs > now && Distance2d(bot->GetPositionX(), bot->GetPositionY(), state.ObjectiveSearchX, state.ObjectiveSearchY) > 3.0f)
    {
        MoveBotToPoint(state, bot, state.ObjectiveSearchX, state.ObjectiveSearchY, state.ObjectiveSearchZ);
        return;
    }

    if (plan && plan->QuestId)
    {
        QueryResult result = CharacterDatabase.PQuery(
            "SELECT x, y, z FROM bot_memory_pois "
            "WHERE bot_guid = %u AND map_id = %u AND zone_id = %u AND poi_type = 'objective_object' "
            "AND (quest_id = %u OR quest_id = 0) "
            "ORDER BY last_seen_at DESC, score DESC LIMIT 1",
            bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetZoneId(), plan->QuestId);
        if (result)
        {
            Field* fields = result->Fetch();
            state.ObjectiveSearchX = fields[0].GetFloat();
            state.ObjectiveSearchY = fields[1].GetFloat();
            state.ObjectiveSearchZ = fields[2].GetFloat();
            state.ObjectiveSearchUntilMs = now + urand(6000, 10000);
            MoveBotToPoint(state, bot, state.ObjectiveSearchX, state.ObjectiveSearchY, state.ObjectiveSearchZ);
            return;
        }
    }

    float baseAngle = avoidObject ? avoidObject->GetAngle(bot) : bot->GetOrientation();
    if (avoidObject && bot->IsWithinDistInMap(avoidObject, INTERACTION_DISTANCE + 3.0f))
        baseAngle = avoidObject->GetAngle(bot);
    else if (plan && plan->RequiredEntry)
        baseAngle += frand(-0.8f, 0.8f);
    else
        baseAngle = frand(0.0f, 2.0f * float(M_PI));

    float distance = avoidObject ? frand(12.0f, 22.0f) : frand(10.0f, 26.0f);
    Position pos = bot->GetFirstCollisionPosition(distance, baseAngle);
    state.ObjectiveSearchX = pos.GetPositionX();
    state.ObjectiveSearchY = pos.GetPositionY();
    state.ObjectiveSearchZ = pos.GetPositionZ();
    state.ObjectiveSearchUntilMs = now + urand(6000, 10000);
    MoveBotToPoint(state, bot, state.ObjectiveSearchX, state.ObjectiveSearchY, state.ObjectiveSearchZ);
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

    QuestObjectivePlan committedPlan;
    bool hasCommittedPlan = state.QuestWork.ActiveQuestId
        && FindQuestObjective(bot, state.QuestWork.ActiveQuestId, committedPlan);
    QuestObjectivePlan acceptedPlan;
    bool hasAcceptedPlan = !hasCommittedPlan && state.NewlyAcceptedQuestId && FindQuestObjective(bot, state.NewlyAcceptedQuestId, acceptedPlan);
    QuestObjectivePlan discoveredPlan;
    bool hasActiveObjective = hasCommittedPlan || hasAcceptedPlan || FindActiveQuestObjective(bot, discoveredPlan);
    if (hasCommittedPlan)
        discoveredPlan = committedPlan;
    else if (hasAcceptedPlan)
        discoveredPlan = acceptedPlan;
    if (state.QuestWork.CooldownUntilMs > NowMs())
        hasActiveObjective = false;

    if (state.QuestWork.Phase == "verify_progress" && hasCommittedPlan)
    {
        result.Handled = true;
        result.Situation = "quest_verify_progress";
        result.Action = "verify_progress";
        result.QuestId = committedPlan.QuestId;
        Unit* verifyTarget = state.QuestWork.SelectedTargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, state.QuestWork.SelectedTargetGuid);
        result.Target = verifyTarget;
        if (state.QuestWork.VerifyAfterMs && NowMs() < state.QuestWork.VerifyAfterMs)
            return result;

        std::string raw = BuildRawJson(bot, verifyTarget);
        std::string semantic = BuildSemanticJson(bot, verifyTarget, "quest_verify_progress", &power, stage, activity);
        bool progressed = VerifyQuestObjectiveProgress(state, bot, committedPlan, verifyTarget, state.QuestWork.ProgressBefore, "delayed_ability_verify", raw.c_str(), semantic.c_str());
        if (!progressed)
        {
            ++state.QuestWork.VerifiedCasts;
            if (state.QuestWork.VerifiedCasts >= 3 && verifyTarget)
            {
                std::ostringstream key;
                key << committedPlan.QuestId << ":" << state.QuestWork.RequiredSpell << ":" << verifyTarget->GetGUID().GetCounter();
                state.AbilityObjectiveCooldownUntilMs[key.str()] = NowMs() + 120000;
                state.DummyTargetCooldownUntilMs[verifyTarget->GetGUID().GetCounter()] = NowMs() + 120000;
                state.LastRejectedTargetReason = "ability_objective_no_progress_after_delay";
                result.Failure = true;
                RecordDecision(state, bot, "quest_ability_objective", "blacklist_target_spell_pair", verifyTarget, raw.c_str(), semantic.c_str(), std::vector<BotActivityScore>(), BotActivityScore(), power, true, true);
            }
            SetQuestWorkPhase(state, "search_objective");
        }
        else
            SetQuestWorkPhase(state, bot->CanCompleteQuest(committedPlan.QuestId) ? "move_to_turnin" : "choose_objective");
        return result;
    }

    uint32 questId = 0;
    WorldObject* turnIn = !hasActiveObjective ? SelectQuestGiver(bot, true, &questId, &state) : nullptr;
    if (turnIn)
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
            MoveBotToPoint(state, bot, turnIn->GetPositionX(), turnIn->GetPositionY(), turnIn->GetPositionZ());
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
        ResetQuestWork(state);
        return result;
    }

    QuestObjectivePlan plan = discoveredPlan;
    if (hasActiveObjective)
    {
        result.Handled = true;
        result.Situation = "quest_objective";
        result.QuestId = plan.QuestId;
        SetQuestWorkFromPlan(state, plan);
        if (state.QuestWork.Phase == "idle" || state.QuestWork.Phase == "choose_quest")
            SetQuestWorkPhase(state, "choose_objective");

        if (plan.ObjectiveType == QuestObjectiveType::UseAbilityOnDummy || plan.ObjectiveType == QuestObjectiveType::CastSpellOnTarget)
        {
            result.Situation = "quest_ability_objective";
            result.Action = plan.ObjectiveType == QuestObjectiveType::UseAbilityOnDummy ? "use_ability_on_dummy" : "cast_spell_on_target";
            SetQuestWorkPhase(state, "cast_spell_on_target");
            Unit* abilityTarget = SelectQuestAbilityObjectiveTarget(bot, plan, state);
            result.Target = abilityTarget;
            state.CurrentTargetIsTrainingDummy = IsTrainingDummy(abilityTarget);
            state.CurrentDummyAllowedByQuest = IsTrainingDummyAllowedForQuest(plan, abilityTarget);
            state.LastQuestProgressBefore = QuestObjectiveProgress(bot, plan);

            if (!abilityTarget)
            {
                MoveToObjectiveSearchPoint(state, bot, &plan);
                result.Action = "search_ability_target";
                SetQuestWorkPhase(state, "search_objective");
                RecordQuestEvent(state, bot, "objective_search", plan.QuestId, nullptr, "ability_target_not_found", BuildRawJson(bot, nullptr).c_str(), BuildSemanticJson(bot, nullptr, "quest_objective_search", &power, stage, activity).c_str(), plan.CurrentCount, plan.ItemId);
                return result;
            }
            state.QuestWork.SelectedTargetGuid = abilityTarget->GetGUID();

            uint32 spellId = plan.RequiredSpellId ? plan.RequiredSpellId : SelectQuestAbilitySpell(bot, sObjectMgr->GetQuestTemplate(plan.QuestId), plan);
            state.RequiredSpellId = spellId;
            if (!spellId)
            {
                result.Failure = true;
                state.LastRejectedTargetReason = "ability_spell_unavailable";
                std::string raw = BuildRawJson(bot, abilityTarget);
                std::string semantic = BuildSemanticJson(bot, abilityTarget, "quest_ability_objective_failed", &power, stage, activity);
                RecordQuestEvent(state, bot, "ability_objective_failed", plan.QuestId, abilityTarget, "spell_unavailable", raw.c_str(), semantic.c_str(), state.LastQuestProgressBefore);
                return result;
            }

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
            float maxRange = spellInfo ? std::max(5.0f, spellInfo->GetMaxRange(false)) : 5.0f;
            if (!bot->IsWithinDistInMap(abilityTarget, maxRange))
            {
                MoveBotToPoint(state, bot, abilityTarget->GetPositionX(), abilityTarget->GetPositionY(), abilityTarget->GetPositionZ());
                SetQuestWorkPhase(state, "move_to_target");
                return result;
            }

            bot->SetFacingToObject(abilityTarget);
            bool cast = TryCastCombatSpell(bot, abilityTarget, spellId);
            uint32 before = state.LastQuestProgressBefore;

            std::ostringstream key;
            key << plan.QuestId << ":" << spellId << ":" << abilityTarget->GetGUID().GetCounter();
            std::string raw = BuildRawJson(bot, abilityTarget);
            std::string semantic = BuildSemanticJson(bot, abilityTarget, "quest_ability_objective", &power, stage, activity);
            if (cast)
            {
                RecordEvent(state, bot, "spell_cast", abilityTarget, "quest_ability_objective", raw.c_str(), semantic.c_str(), 0.0f, before, spellId);
                state.QuestWork.ProgressBefore = before;
                state.LastQuestProgressAfter = QuestObjectiveProgress(bot, plan);
                state.QuestWork.RequiredSpell = spellId;
                state.QuestWork.VerifyAfterMs = NowMs() + urand(500, 1500);
                SetQuestWorkPhase(state, "verify_progress");
            }
            return result;
        }

        WorldObject* questObject = SelectQuestGameObject(bot, plan);
        if (plan.IsGameObject || questObject)
        {
            result.Action = plan.IsItemObjective ? "loot_quest_object" : "use_quest_object";
            SetQuestWorkPhase(state, plan.IsItemObjective ? "use_gameobject" : "use_gameobject");
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
                MoveBotToPoint(state, bot, questObject->GetPositionX(), questObject->GetPositionY(), questObject->GetPositionZ());
                SetQuestWorkPhase(state, "move_to_target");
                return result;
            }

            uint32 before = QuestObjectiveProgress(bot, plan);
            state.QuestWork.SelectedObjectGuid = questObject->GetGUID();
            if (GameObject* go = questObject->ToGameObject())
            {
                go->Use(bot);
                if (plan.IsItemObjective)
                    bot->SendLoot(go->GetGUID(), LOOT_CORPSE);
            }
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "quest_objective", &power, stage, activity);
            VerifyQuestObjectiveProgress(state, bot, plan, nullptr, before, plan.IsItemObjective ? "loot_object" : "use_object", raw.c_str(), semantic.c_str());
            return result;
        }

        Unit* objectiveTarget = SelectQuestObjectiveTarget(bot, plan);
        result.Target = objectiveTarget;
        result.Action = plan.IsItemObjective ? "collect_quest_item" : "kill_quest_mob";
        if (!objectiveTarget)
        {
            MoveToObjectiveSearchPoint(state, bot, &plan);
            result.Action = plan.IsItemObjective ? "search_collect_mob" : "search_quest_mob";
            SetQuestWorkPhase(state, plan.IsItemObjective ? "search_collect_mob" : "search_objective");
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "quest_objective_search", &power, stage, activity);
            RecordQuestEvent(state, bot, plan.RequiredEntry || plan.ItemId ? "objective_search" : "objective_unresolved", plan.QuestId, nullptr, plan.RequiredEntry || plan.ItemId ? "target_not_found" : "metadata_incomplete", raw.c_str(), semantic.c_str(), plan.CurrentCount, plan.ItemId);
            return result;
        }

        state.QuestWork.SelectedTargetGuid = objectiveTarget->GetGUID();
        state.LastQuestProgressBefore = QuestObjectiveProgress(bot, plan);
        SetQuestWorkPhase(state, "kill_objective_mob");
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

    if (!hasActiveObjective && (state.RecentlyAcceptedQuestUntilMs > NowMs() || state.ObjectiveSearchUntilMs > NowMs()))
    {
        result.Handled = true;
        result.Situation = "quest_objective_search";
        result.Action = state.LastObjectiveNotFoundReason == "unsupported_after_accept" ? "leave_unsupported_quest_giver" : "search_objective";
        result.QuestId = state.NewlyAcceptedQuestId;
        SetQuestWorkPhase(state, "search_objective");
        MoveToObjectiveSearchPoint(state, bot, nullptr);

        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "quest_objective_search", &power, stage, activity);
        RecordQuestEvent(state, bot, "objective_search", state.NewlyAcceptedQuestId, nullptr,
            state.LastObjectiveNotFoundReason.empty() ? "recently_accepted_waiting_for_objective" : state.LastObjectiveNotFoundReason.c_str(),
            raw.c_str(), semantic.c_str());
        return result;
    }

    WorldObject* giver = !hasActiveObjective ? SelectQuestGiver(bot, false, &questId, &state) : nullptr;
    if (giver)
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
            MoveBotToPoint(state, bot, giver->GetPositionX(), giver->GetPositionY(), giver->GetPositionZ());
            return result;
        }

        std::ostringstream attemptKey;
        attemptKey << giver->GetGUID().GetCounter() << ":" << questId;
        ++state.QuestPickupAttemptCount[attemptKey.str()];

        bot->AddQuestAndCheckCompletion(quest, giver);
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "quest_accepted", &power, stage, activity);
        RecordQuestEvent(state, bot, "quest_seen", questId, nullptr, "ok", raw.c_str(), semantic.c_str());

        QuestStatus status = bot->GetQuestStatus(questId);
        auto questItr = bot->getQuestStatusMap().find(questId);
        bool accepted = questItr != bot->getQuestStatusMap().end() && (status == QUEST_STATUS_INCOMPLETE || status == QUEST_STATUS_COMPLETE);
        uint64 cooldownMs = NowMs() + urand(15000, 30000);
        state.QuestGiverCooldownUntilMs[giver->GetGUID().GetCounter()] = cooldownMs;
        if (!accepted)
        {
            state.QuestCooldownUntilMs[questId] = NowMs() + 60000;
            state.LastObjectiveNotFoundReason = "quest_log_entry_missing";
            state.QuestWork.FailedReason = "quest_accept_failed";
            result.Failure = true;
            RecordQuestEvent(state, bot, "quest_accept_failed", questId, nullptr, "quest_log_entry_missing", raw.c_str(), semantic.c_str());
            MoveToObjectiveSearchPoint(state, bot, nullptr, giver);
            result.Action = "leave_quest_giver";
            return result;
        }

        ++_metrics.QuestsAccepted;
        state.LastQuestId = questId;
        state.NewlyAcceptedQuestId = questId;
        state.RecentlyAcceptedQuestUntilMs = NowMs() + 30000;
        state.QuestStartTime = _elapsedMs / 1000;
        state.QuestStartDeaths = _metrics.Deaths;
        RecordQuestEvent(state, bot, "quest_accepted", questId, nullptr, "ok", raw.c_str(), semantic.c_str(), _metrics.QuestsAccepted);
        result.Action = "accept_quest";

        QuestObjectivePlan acceptedObjective;
        if (FindQuestObjective(bot, questId, acceptedObjective))
        {
            SetQuestWorkFromPlan(state, acceptedObjective);
            state.QuestWork.SelectedGiverGuid = giver->GetGUID();
            SetQuestWorkPhase(state, "choose_objective");
            state.LastObjectiveNotFoundReason.clear();
            RecordQuestEvent(state, bot, "quest_work_started", questId, nullptr, ToString(acceptedObjective.ObjectiveType), raw.c_str(), semantic.c_str(), acceptedObjective.CurrentCount, acceptedObjective.ItemId);
            MoveToObjectiveSearchPoint(state, bot, &acceptedObjective, giver);
            result.Action = "choose_objective";
        }
        else
        {
            state.QuestCooldownUntilMs[questId] = NowMs() + 120000;
            state.LastObjectiveNotFoundReason = "unsupported_after_accept";
            state.QuestWork.FailedReason = "unsupported_after_accept";
            RecordQuestEvent(state, bot, "quest_unsupported_after_accept", questId, nullptr, "no_supported_objective", raw.c_str(), semantic.c_str());
            MoveToObjectiveSearchPoint(state, bot, nullptr, giver);
            result.Action = "leave_unsupported_quest_giver";
        }
        return result;
    }

    return result;
}

bool BotWorldPopulationMgr::IsBossContext(Player* bot, Unit const* target) const
{
    if (!bot || !bot->GetMap())
        return false;

    bool eligibleMap = (_config.AllowDungeons && bot->GetMap()->IsNonRaidDungeon()) || (_config.AllowRaids && bot->GetMap()->IsRaid());
    if (!eligibleMap)
        return false;

    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        if (creature->IsDungeonBoss() || creature->isWorldBoss())
            return true;

    return bot->IsInCombat() && FindBossTarget(bot) != nullptr;
}

Unit* BotWorldPopulationMgr::FindBossTarget(Player* bot) const
{
    if (!bot || !bot->GetMap())
        return nullptr;

    auto usableBoss = [bot](Unit* target) -> Unit*
    {
        if (!target || !target->IsAlive() || !bot->IsValidAttackTarget(target) || !bot->IsWithinLOSInMap(target))
            return nullptr;

        Creature* creature = target->ToCreature();
        if (!creature || (!creature->IsDungeonBoss() && !creature->isWorldBoss()))
            return nullptr;

        return target;
    };

    if (Unit* target = usableBoss(bot->GetVictim()))
        return target;

    if (Group* group = bot->GetGroup())
    {
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                continue;

            if (Unit* target = usableBoss(member->GetVictim()))
                return target;
        }
    }

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 60.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 60.0f);

    Unit* best = nullptr;
    float bestDistance = 0.0f;
    for (WorldObject* object : objects)
    {
        Unit* unit = object ? object->ToUnit() : nullptr;
        Unit* boss = usableBoss(unit);
        if (!boss)
            continue;

        float distance = bot->GetExactDist(boss);
        if (!best || distance < bestDistance)
        {
            best = boss;
            bestDistance = distance;
        }
    }

    return best;
}

BotWorldPopulationMgr::BossMechanicFeatures BotWorldPopulationMgr::BuildBossMechanicFeatures(Player* bot, Unit const* boss) const
{
    BossMechanicFeatures features;
    if (!bot)
        return features;

    features.RaidEncounter = bot->GetMap() && bot->GetMap()->IsRaid();
    features.BossPresent = boss != nullptr;
    if (boss)
    {
        features.BossGuid = boss->GetGUID();
        if (Creature const* creature = boss->ToCreature())
            features.BossEntry = creature->GetEntry();
    }

    SpellInfo const* castInfo = nullptr;
    if (boss)
    {
        if (Spell* spell = const_cast<Unit*>(boss)->GetCurrentSpell(CURRENT_GENERIC_SPELL))
        {
            castInfo = spell->GetSpellInfo();
            features.BossCasting = castInfo != nullptr;
            features.CastSpellId = castInfo ? castInfo->Id : 0;
            features.CastRemainingMs = spell->GetRemainingCastTime();
        }
    }

    features.DangerousCast = SpellLooksDangerous(castInfo) || SpellLooksLikeHeal(castInfo);
    features.GroundDanger = SpellLooksLikeGroundDanger(castInfo);
    features.MoveOut = features.GroundDanger;
    features.RaidDamage = SpellLooksRaidWide(castInfo);
    features.TankSpike = SpellLooksTankSpike(castInfo);
    features.AddsActive = SpellLooksLikeSummonOrAdds(castInfo);
    features.MustInterrupt = castInfo && features.DangerousCast && castInfo->CanBeInterrupted(boss, false);
    features.InterruptPriority = features.MustInterrupt ? 1.0f : (features.DangerousCast && features.BossCasting ? 0.45f : 0.0f);

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 45.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 45.0f);

    float bestAddScore = -1.0f;
    for (WorldObject* object : objects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || !creature->IsAlive() || creature == boss || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
            continue;
        if (creature->IsDungeonBoss() || creature->isWorldBoss())
            continue;

        ++features.AddCount;
        features.AddsActive = true;
        float score = 45.0f - bot->GetExactDist(creature);
        if (creature->GetVictim() == bot)
            score += 20.0f;
        if (creature->isElite())
            score += 10.0f;
        if (score > bestAddScore)
        {
            bestAddScore = score;
            features.PriorityAddGuid = creature->GetGUID();
        }
    }

    if (Group* group = bot->GetGroup())
    {
        float totalHp = 0.0f;
        uint32 memberCount = 0;
        float healerManaTotal = 0.0f;
        uint32 healerCount = 0;
        float tankHp = 1.0f;
        bool tankSeen = false;
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || member->GetMap() != bot->GetMap())
                continue;

            float hp = UnitHealthPct(member);
            totalHp += hp;
            features.LowestAllyHpPct = memberCount ? std::min(features.LowestAllyHpPct, hp) : hp;
            ++memberCount;

            uint8 roles = group->GetLfgRoles(member->GetGUID());
            if (roles & lfg::PLAYER_ROLE_TANK)
            {
                tankHp = hp;
                tankSeen = true;
            }
            if (roles & lfg::PLAYER_ROLE_HEALER)
            {
                uint32 maxMana = member->GetMaxPower(POWER_MANA);
                healerManaTotal += maxMana ? float(member->GetPower(POWER_MANA)) / float(maxMana) : 1.0f;
                ++healerCount;
            }
        }

        if (memberCount)
            features.PartyAverageHpPct = totalHp / float(memberCount);
        if (tankSeen)
            features.TankHpPct = tankHp;
        if (healerCount)
            features.HealerManaPct = healerManaTotal / float(healerCount);
    }
    else
    {
        features.PartyAverageHpPct = UnitHealthPct(bot);
        features.LowestAllyHpPct = features.PartyAverageHpPct;
        features.TankHpPct = features.PartyAverageHpPct;
    }

    if (features.RaidDamage && features.LowestAllyHpPct < 0.55f)
        features.StackPlaceholder = true;
    if (features.GroundDanger || features.RaidDamage)
        features.SpreadPlaceholder = true;

    features.DangerScore = std::min(1.0f,
        (features.MustInterrupt ? 0.35f : 0.0f)
        + (features.GroundDanger ? 0.25f : 0.0f)
        + (features.RaidDamage ? 0.20f : 0.0f)
        + (features.TankSpike ? 0.15f : 0.0f)
        + (features.AddsActive ? std::min(0.20f, float(features.AddCount) * 0.05f) : 0.0f)
        + (features.LowestAllyHpPct < 0.4f ? 0.20f : 0.0f));

    return features;
}

BotWorldPopulationMgr::BossMechanicActionResult BotWorldPopulationMgr::TryBossMechanics(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity)
{
    BossMechanicActionResult result;
    if (!IsBossContext(bot, nullptr))
        return result;

    result.Target = FindBossTarget(bot);
    if (!result.Target && !state.TargetGuid.IsEmpty())
        result.Target = ObjectAccessor::GetUnit(*bot, state.TargetGuid);
    if (!result.Target)
        return result;

    result.Handled = true;
    result.Situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
    result.Features = BuildBossMechanicFeatures(bot, result.Target);
    state.TargetGuid = result.Target->GetGUID();
    if (result.Features.RaidEncounter && !state.WasInCombat)
        ++state.RaidAttempts;

    std::string raw = BuildRawJson(bot, result.Target);
    std::string semantic = BuildSemanticJson(bot, result.Target, result.Situation.c_str(), &power, stage, activity);
    char const* role = GetDungeonRole(bot);
    RaidRoleAssignment raidAssignment;
    RaidPositioningAnchors raidAnchors;
    RaidMechanicAdapter raidAdapter;
    RaidGearTargetPlan raidGearPlan;
    HeroicRaidProgression heroicProgression;
    if (result.Features.RaidEncounter)
    {
        raidAssignment = BuildRaidRoleAssignment(bot);
        raidAnchors = BuildRaidPositioningAnchors(bot, result.Target, raidAssignment, result.Features);
        raidAdapter = BuildRaidMechanicAdapter(bot, result.Target, raidAssignment, result.Features);
        raidGearPlan = BuildRaidGearTargetPlan(bot, power, stage);
        heroicProgression = BuildHeroicRaidProgression(state, bot, power, stage);
    }

    if (result.Features.MoveOut && result.Features.DangerScore >= 0.25f)
    {
        Position pos = bot->GetFirstCollisionPosition(8.0f, result.Target->GetAngle(bot) + float(M_PI));
        MoveBotToPoint(state, bot, pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ());
        result.Action = "move_out_ground_danger";
        result.Rare = true;
        RecordEvent(state, bot, "boss_mechanic", result.Target, "move_out", raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.CastSpellId, result.Features.CastSpellId);
        if (result.Features.RaidEncounter)
            RecordRaidTelemetry(state, bot, result.Target, "raid_mechanic", "move_out", result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.CastSpellId, result.Features.CastSpellId);
        return result;
    }

    uint32 interruptSpell = SelectInterruptSpell(bot);
    if (result.Features.MustInterrupt && interruptSpell)
    {
        bool interrupted = TryCastCombatSpell(bot, result.Target, interruptSpell);
        result.Action = interrupted ? "interrupt_must_interrupt" : "interrupt_failed";
        result.SpellId = interruptSpell;
        result.Failure = !interrupted;
        result.Rare = true;
        RecordEvent(state, bot, interrupted ? "interrupt_success" : "interrupt_failed", result.Target, interrupted ? "ok" : "failed", raw.c_str(), semantic.c_str(), result.Features.InterruptPriority, result.Features.CastSpellId, interruptSpell);
        if (result.Features.RaidEncounter)
            RecordRaidTelemetry(state, bot, result.Target, "raid_interrupt", interrupted ? "ok" : "failed", result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), result.Features.InterruptPriority, result.Features.CastSpellId, interruptSpell);
        if (!interrupted)
            RecordBossReplay(state, bot, result.Target, result.Features, "boss_mechanic_failure", raw.c_str(), semantic.c_str(), "{\"action\":\"interrupt_must_interrupt\"}", "{\"reason\":\"must_interrupt_failed\"}");
        return result;
    }

    if (result.Features.AddsActive && !result.Features.PriorityAddGuid.IsEmpty() && std::string(role) != "healer")
    {
        if (Unit* add = ObjectAccessor::GetUnit(*bot, result.Features.PriorityAddGuid))
        {
            BotActionExecutor executor;
            BotActionResult pull = executor.Pull(bot, add);
            uint32 spellId = SelectCombatSpell(bot, add);
            bool cast = spellId && TryCastCombatSpell(bot, add, spellId);
            result.Target = add;
            result.Action = "switch_to_adds";
            result.SpellId = cast ? spellId : 0;
            result.Failure = pull != BotActionResult::Ok;
            result.Rare = true;
            RecordEvent(state, bot, "boss_adds", add, ToString(pull), raw.c_str(), semantic.c_str(), float(result.Features.AddCount), result.Features.CastSpellId, result.SpellId);
            if (result.Features.RaidEncounter)
                RecordRaidTelemetry(state, bot, add, "raid_add_wave", ToString(pull), result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), float(result.Features.AddCount), result.Features.CastSpellId, result.SpellId);
            if (result.Failure)
                RecordBossReplay(state, bot, add, result.Features, "boss_mechanic_failure", raw.c_str(), semantic.c_str(), "{\"action\":\"switch_to_adds\"}", "{\"reason\":\"add_switch_failed\"}");
            return result;
        }
    }

    if (std::string(role) == "healer")
    {
        Unit* healTarget = bot;
        if (Group* group = bot->GetGroup())
        {
            float lowestHp = 1.0f;
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap() || !bot->IsWithinLOSInMap(member))
                    continue;

                float hp = UnitHealthPct(member);
                if (hp < lowestHp)
                {
                    healTarget = member;
                    lowestHp = hp;
                }
            }
        }

        uint32 healSpell = SelectHealSpell(bot);
        if (healSpell && UnitHealthPct(healTarget) < (result.Features.RaidDamage ? 0.9f : 0.75f) && TryCastFriendlySpell(bot, healTarget, healSpell))
        {
            result.Action = result.Features.RaidDamage ? "heal_raid_damage" : "heal_boss_damage";
            result.SpellId = healSpell;
            result.Target = healTarget;
            RecordEvent(state, bot, "boss_heal", result.Target, "ok", raw.c_str(), semantic.c_str(), UnitHealthPct(healTarget), result.Features.CastSpellId, healSpell);
            if (result.Features.RaidEncounter)
                RecordRaidTelemetry(state, bot, result.Target, "raid_healer_cooldown", "ok", result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), UnitHealthPct(healTarget), result.Features.CastSpellId, healSpell);
            return result;
        }
    }

    if (result.Features.RaidEncounter && raidAnchors.Active)
    {
        bool shouldReposition = (raidAdapter.AssignmentType == "stack" && bot->GetExactDist2d(raidAnchors.StackX, raidAnchors.StackY) > 4.0f)
            || (raidAdapter.AssignmentType == "spread" && bot->GetExactDist2d(raidAnchors.SpreadX, raidAnchors.SpreadY) > 4.0f);
        if (shouldReposition)
        {
            Position pos(
                raidAdapter.AssignmentType == "stack" ? raidAnchors.StackX : raidAnchors.SpreadX,
                raidAdapter.AssignmentType == "stack" ? raidAnchors.StackY : raidAnchors.SpreadY,
                raidAdapter.AssignmentType == "stack" ? raidAnchors.StackZ : raidAnchors.SpreadZ,
                bot->GetOrientation());
            MoveBotToPoint(state, bot, pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ());
            result.Action = raidAdapter.AssignmentType == "stack" ? "raid_stack_anchor" : "raid_spread_anchor";
            result.Rare = result.Features.DangerScore >= 0.5f;
            RecordRaidTelemetry(state, bot, result.Target, "raid_position_anchor", result.Action.c_str(), result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), raidAnchors.DistanceToAnchor, result.Features.CastSpellId);
            return result;
        }
    }

    BotActionExecutor executor;
    BotActionResult pull = executor.Pull(bot, result.Target);
    uint32 spellId = SelectCombatSpell(bot, result.Target);
    bool cast = spellId && TryCastCombatSpell(bot, result.Target, spellId);
    result.Action = std::string(role) == "tank" ? "tank_boss_position" : "boss_single_target";
    result.SpellId = cast ? spellId : 0;
    result.Failure = pull != BotActionResult::Ok;
    result.Rare = result.Features.DangerScore >= 0.5f || result.Features.BossCasting || result.Features.AddsActive;

    RecordEvent(state, bot, "boss_action", result.Target, ToString(pull), raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.CastSpellId, result.SpellId);
    if (result.Features.RaidEncounter)
        RecordRaidTelemetry(state, bot, result.Target, "raid_boss_action", ToString(pull), result.Features, raidAssignment, raidAnchors, raidAdapter, raidGearPlan, heroicProgression, raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.CastSpellId, result.SpellId);
    if (!state.WasInCombat)
        RecordEvent(state, bot, "boss_started", result.Target, result.Situation.c_str(), raw.c_str(), semantic.c_str(), result.Features.DangerScore, result.Features.BossEntry);
    if (result.Failure || (result.Features.DangerScore >= 0.85f && result.Features.BossCasting))
        RecordBossReplay(state, bot, result.Target, result.Features, "boss_mechanic_failure", raw.c_str(), semantic.c_str(), "{\"action\":\"boss_single_target\"}", result.Failure ? "{\"reason\":\"boss_action_failed\"}" : "{\"reason\":\"high_danger_boss_state\"}");
    state.WasInCombat = true;
    return result;
}

BotWorldPopulationMgr::RaidRoleAssignment BotWorldPopulationMgr::BuildRaidRoleAssignment(Player* bot) const
{
    RaidRoleAssignment assignment;
    if (!bot)
        return assignment;

    assignment.Role = GetDungeonRole(bot);
    if (Group* group = bot->GetGroup())
    {
        assignment.RaidLeaderGuid = group->GetLeaderGUID();
        assignment.SubGroup = group->GetMemberGroup(bot->GetGUID());
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || member->GetMap() != bot->GetMap())
                continue;

            ++assignment.RaidSize;
            uint8 roles = group->GetLfgRoles(member->GetGUID());
            std::string role = "dps";
            if (roles & lfg::PLAYER_ROLE_TANK)
            {
                role = "tank";
                if (assignment.MainTankGuid.IsEmpty())
                    assignment.MainTankGuid = member->GetGUID();
                else if (assignment.OffTankGuid.IsEmpty())
                    assignment.OffTankGuid = member->GetGUID();
                ++assignment.TankCount;
            }
            else if (roles & lfg::PLAYER_ROLE_HEALER)
            {
                role = "healer";
                ++assignment.HealerCount;
            }
            else
                ++assignment.DpsCount;

            if (member == bot)
            {
                if (role == "tank")
                    assignment.RoleIndex = assignment.TankCount;
                else if (role == "healer")
                    assignment.RoleIndex = assignment.HealerCount;
                else
                    assignment.RoleIndex = assignment.DpsCount;
                assignment.Role = role;
            }
        }
    }

    if (!assignment.RaidSize)
    {
        assignment.RaidSize = 1;
        assignment.RoleIndex = 1;
        if (assignment.Role == "tank")
        {
            assignment.TankCount = 1;
            assignment.MainTankGuid = bot->GetGUID();
        }
        else if (assignment.Role == "healer")
            assignment.HealerCount = 1;
        else
            assignment.DpsCount = 1;
    }

    if (assignment.MainTankGuid.IsEmpty() && assignment.Role == "tank")
        assignment.MainTankGuid = bot->GetGUID();

    return assignment;
}

BotWorldPopulationMgr::RaidPositioningAnchors BotWorldPopulationMgr::BuildRaidPositioningAnchors(Player* bot, Unit const* boss, RaidRoleAssignment const& assignment, BossMechanicFeatures const& features) const
{
    RaidPositioningAnchors anchors;
    if (!bot)
        return anchors;

    anchors.Active = bot->GetMap() && bot->GetMap()->IsRaid();
    Unit const* anchor = boss;
    anchors.AnchorType = "boss";

    if (assignment.Role == "healer" || assignment.Role == "dps")
    {
        if (Group* group = bot->GetGroup())
        {
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (member && member->GetGUID() == assignment.MainTankGuid && member->IsAlive() && member->GetMap() == bot->GetMap())
                {
                    anchor = member;
                    anchors.AnchorType = "main_tank";
                    break;
                }
            }
        }
    }

    if (!anchor && !assignment.RaidLeaderGuid.IsEmpty())
        if (Player* leader = ObjectAccessor::FindPlayer(assignment.RaidLeaderGuid))
            if (leader->IsAlive() && leader->GetMap() == bot->GetMap())
            {
                anchor = leader;
                anchors.AnchorType = "raid_leader";
            }

    if (!anchor)
    {
        anchor = bot;
        anchors.AnchorType = "self";
    }

    anchors.AnchorGuid = anchor->GetGUID();
    anchors.AnchorX = anchor->GetPositionX();
    anchors.AnchorY = anchor->GetPositionY();
    anchors.AnchorZ = anchor->GetPositionZ();
    anchors.DistanceToAnchor = bot->GetExactDist(anchor);

    float baseAngle = boss ? boss->GetAngle(bot) : bot->GetOrientation();
    float stackDistance = assignment.Role == "tank" ? 4.0f : 8.0f;
    float spreadDistance = 10.0f + float(assignment.RoleIndex % 5) * 2.0f;
    float spreadAngle = baseAngle + float(assignment.SubGroup + assignment.RoleIndex) * 0.75f;

    anchors.StackX = anchors.AnchorX + std::cos(baseAngle) * stackDistance;
    anchors.StackY = anchors.AnchorY + std::sin(baseAngle) * stackDistance;
    anchors.StackZ = anchors.AnchorZ;
    anchors.SpreadX = anchors.AnchorX + std::cos(spreadAngle) * spreadDistance;
    anchors.SpreadY = anchors.AnchorY + std::sin(spreadAngle) * spreadDistance;
    anchors.SpreadZ = anchors.AnchorZ;

    if (features.MoveOut && boss)
    {
        Position safe = bot->GetFirstCollisionPosition(8.0f, boss->GetAngle(bot) + float(M_PI));
        anchors.SpreadX = safe.GetPositionX();
        anchors.SpreadY = safe.GetPositionY();
        anchors.SpreadZ = safe.GetPositionZ();
    }

    return anchors;
}

BotWorldPopulationMgr::RaidMechanicAdapter BotWorldPopulationMgr::BuildRaidMechanicAdapter(Player* bot, Unit const* /*boss*/, RaidRoleAssignment const& assignment, BossMechanicFeatures const& features) const
{
    RaidMechanicAdapter adapter;
    if (!bot)
        return adapter;

    adapter.Priority = features.DangerScore;
    adapter.AssignedTargetGuid = features.BossGuid;
    adapter.HeroicOnly = BotLongTermProgressionBrain::ClassifyStage(bot, BotLongTermProgressionBrain::CalculateRolePower(bot)) == BotProgressionStage::HeroicRaid;

    if (features.TankSpike)
    {
        adapter.MechanicFamily = "tank_swap";
        adapter.AssignmentType = assignment.Role == "tank" ? "tank_swap" : "maintain_role";
        adapter.RecommendedAction = assignment.Role == "tank" ? "tank_boss_position" : "avoid_front";
        adapter.Priority += 0.25f;
        return adapter;
    }

    if (features.MustInterrupt)
    {
        adapter.MechanicFamily = "interrupt_rotation";
        adapter.AssignmentType = "interrupt";
        adapter.RecommendedAction = "interrupt_must_interrupt";
        adapter.Priority += 0.35f;
        return adapter;
    }

    if (features.RaidDamage)
    {
        adapter.MechanicFamily = "raid_wide_aoe";
        adapter.AssignmentType = assignment.Role == "healer" ? "healer_cooldown" : "stack";
        adapter.RecommendedAction = assignment.Role == "healer" ? "heal_raid_damage" : "raid_stack_anchor";
        adapter.Priority += 0.20f;
        return adapter;
    }

    if (features.MoveOut || features.SpreadPlaceholder)
    {
        adapter.MechanicFamily = "spread";
        adapter.AssignmentType = "spread";
        adapter.RecommendedAction = "raid_spread_anchor";
        adapter.Priority += 0.20f;
        return adapter;
    }

    if (features.AddsActive)
    {
        adapter.MechanicFamily = "add_wave";
        adapter.AssignmentType = assignment.Role == "healer" ? "maintain_role" : "target_switch";
        adapter.AssignedTargetGuid = features.PriorityAddGuid;
        adapter.RecommendedAction = assignment.Role == "healer" ? "heal_boss_damage" : "switch_to_adds";
        adapter.Priority += 0.15f;
        return adapter;
    }

    adapter.RecommendedAction = assignment.Role == "tank" ? "tank_boss_position" : "boss_single_target";
    return adapter;
}

BotWorldPopulationMgr::RaidGearTargetPlan BotWorldPopulationMgr::BuildRaidGearTargetPlan(Player* bot, BotRolePowerBreakdown const& /*power*/, BotProgressionStage stage) const
{
    RaidGearTargetPlan plan;
    if (!bot)
        return plan;

    plan.CurrentItemLevel = bot->GetAverageItemLevel();
    plan.TargetItemLevel = stage == BotProgressionStage::HeroicRaid ? 372.0f : 359.0f;
    plan.NeededItemLevel = std::max(0.0f, plan.TargetItemLevel - plan.CurrentItemLevel);
    plan.ReadyForRaid = plan.CurrentItemLevel >= 346.0f;
    plan.ReadyForHeroicRaid = plan.CurrentItemLevel >= 372.0f;
    if (!plan.ReadyForRaid)
        plan.RecommendedActivity = "heroic_dungeon";
    else if (!plan.ReadyForHeroicRaid)
        plan.RecommendedActivity = "raid";
    else
        plan.RecommendedActivity = "heroic_raid";
    return plan;
}

bool BotWorldPopulationMgr::FindQuestObjective(Player* bot, uint32 questId, QuestObjectivePlan& plan) const
{
    if (!bot || !questId)
        return false;

    auto questStatus = bot->getQuestStatusMap().find(questId);
    if (questStatus == bot->getQuestStatusMap().end() || questStatus->second.Status != QUEST_STATUS_INCOMPLETE)
        return false;

    Quest const* quest = sObjectMgr->GetQuestTemplate(questId);
    if (!quest || !HasSimpleSupportedObjective(quest))
        return false;

    for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
    {
        int32 required = quest->RequiredNpcOrGo[i];
        uint32 requiredCount = quest->RequiredNpcOrGoCount[i];
        if (!required || !requiredCount || questStatus->second.CreatureOrGOCount[i] >= requiredCount)
            continue;

        plan = QuestObjectivePlan();
        plan.QuestId = quest->GetQuestId();
        plan.RequiredEntry = required;
        plan.RequiredCount = requiredCount;
        plan.CurrentCount = questStatus->second.CreatureOrGOCount[i];
        plan.IsGameObject = required < 0;
        plan.ObjectiveIndex = i;
        if (plan.IsGameObject)
            plan.ObjectiveType = QuestObjectiveType::InteractGameObject;
        else
        {
            CreatureTemplate const* tmpl = sObjectMgr->GetCreatureTemplate(uint32(required));
            bool configuredDummy = false;
            bool configuredDummyAllowed = false;
            if (tmpl)
                configuredDummy = IsDummyEntryConfigured(tmpl->Entry, &configuredDummyAllowed);
            bool dummyRequired = tmpl && (ContainsInsensitive(tmpl->Name, "training dummy") || (configuredDummy && configuredDummyAllowed));
            if (dummyRequired && QuestTextSuggestsAbilityObjective(quest))
            {
                plan.ObjectiveType = QuestObjectiveType::UseAbilityOnDummy;
                plan.RequiresTrainingDummy = true;
                plan.RequiredSpellId = SelectQuestAbilitySpell(bot, quest, plan);
            }
        }
        return true;
    }

    for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
    {
        uint32 requiredItem = quest->RequiredItemId[i];
        uint32 requiredCount = quest->RequiredItemCount[i];
        if (!requiredItem || !requiredCount || questStatus->second.ItemCount[i] >= requiredCount)
            continue;

        plan = QuestObjectivePlan();
        plan.QuestId = quest->GetQuestId();
        plan.RequiredCount = requiredCount;
        plan.CurrentCount = questStatus->second.ItemCount[i];
        plan.IsItemObjective = true;
        plan.ItemId = requiredItem;
        plan.ObjectiveIndex = i;
        plan.ObjectiveType = QuestTextSuggestsAbilityObjective(quest) ? QuestObjectiveType::UseItemOnTarget : QuestObjectiveType::CollectItem;
        return true;
    }

    return false;
}

BotWorldPopulationMgr::HeroicRaidProgression BotWorldPopulationMgr::BuildHeroicRaidProgression(WorldBotState const& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const
{
    HeroicRaidProgression progression;
    progression.TrackingEnabled = _config.TrackHeroicRaidProgression;
    progression.HeroicEligible = stage == BotProgressionStage::HeroicRaid || (bot && bot->GetAverageItemLevel() >= 372.0f);
    progression.Stage = progression.HeroicEligible ? "heroic_raid" : (stage == BotProgressionStage::RaidReady ? "raid_ready" : "normal_raid");
    progression.RaidAttempts = state.RaidAttempts;
    progression.RaidBossKills = state.RaidBossKills;
    progression.HeroicRaidBossKills = state.HeroicRaidBossKills;
    progression.Wipes = state.RaidWipes;
    progression.RolePowerScore = power.Total;
    progression.TargetItemLevel = progression.HeroicEligible ? 372.0f : 359.0f;
    return progression;
}

bool BotWorldPopulationMgr::IsDungeonTrashContext(Player* bot, Unit const* target) const
{
    if (!_config.AllowDungeons || !bot || !bot->GetMap() || !bot->GetMap()->IsNonRaidDungeon())
        return false;

    if (target && target->IsAlive())
        if (Creature const* creature = target->ToCreature())
            return !creature->IsDungeonBoss();

    return bot->GetGroup() != nullptr || bot->IsInCombat();
}

Player* BotWorldPopulationMgr::FindDungeonAnchor(Player* bot) const
{
    if (!bot)
        return nullptr;

    Group* group = bot->GetGroup();
    if (!group)
        return nullptr;

    for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
    {
        Player* member = itr->GetSource();
        if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap())
            continue;

        uint8 roles = group->GetLfgRoles(member->GetGUID());
        if (roles & lfg::PLAYER_ROLE_TANK)
            return member;
    }

    ObjectGuid leaderGuid = group->GetLeaderGUID();
    for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
    {
        Player* member = itr->GetSource();
        if (member && member != bot && member->GetGUID() == leaderGuid && member->IsAlive() && member->GetMap() == bot->GetMap())
            return member;
    }

    for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
    {
        Player* member = itr->GetSource();
        if (member && member != bot && member->IsAlive() && member->GetMap() == bot->GetMap())
            return member;
    }

    return nullptr;
}

Unit* BotWorldPopulationMgr::FindGroupCombatTarget(Player* bot, Player* anchor) const
{
    if (!bot)
        return nullptr;

    auto usableTarget = [bot](Unit* target) -> Unit*
    {
        if (!target || !target->IsAlive() || !bot->IsValidAttackTarget(target) || !bot->IsWithinLOSInMap(target))
            return nullptr;
        if (Creature* creature = target->ToCreature())
            if (creature->IsDungeonBoss())
                return nullptr;
        return target;
    };

    if (Unit* target = usableTarget(anchor ? anchor->GetVictim() : nullptr))
        return target;

    if (Group* group = bot->GetGroup())
    {
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                continue;

            if (Unit* target = usableTarget(member->GetVictim()))
                return target;
        }
    }

    return usableTarget(bot->GetVictim());
}

BotWorldPopulationMgr::DungeonTrashPackFeatures BotWorldPopulationMgr::BuildDungeonTrashPackFeatures(Player* bot, Unit const* focus) const
{
    DungeonTrashPackFeatures pack;
    if (!bot)
        return pack;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 35.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 35.0f);

    float bestScore = -1.0f;
    for (WorldObject* object : objects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || !creature->IsAlive() || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
            continue;
        if (creature->IsDungeonBoss())
            continue;

        float distance = bot->GetExactDist(creature);
        if (distance > 30.0f)
            pack.PatrolNearby = true;
        if (distance > 25.0f && creature != focus)
            continue;

        ++pack.PackSize;
        if (creature->isElite())
            ++pack.EliteCount;
        if (creature->GetMaxPower(POWER_MANA) > 0)
            ++pack.CasterCount;

        uint32 castSpellId = 0;
        bool dangerousCast = false;
        if (Spell* spell = creature->GetCurrentSpell(CURRENT_GENERIC_SPELL))
        {
            SpellInfo const* spellInfo = spell->GetSpellInfo();
            castSpellId = spellInfo ? spellInfo->Id : 0;
            ++pack.ActiveCasts;
            if (SpellLooksLikeHeal(spellInfo))
                ++pack.HealerCount;
            dangerousCast = SpellLooksDangerous(spellInfo) || SpellLooksLikeHeal(spellInfo);
            if (dangerousCast)
                ++pack.DangerousCasts;
        }

        float score = 100.0f - distance;
        if (creature == focus)
            score += 100.0f;
        if (dangerousCast)
            score += 80.0f;
        if (castSpellId)
            score += 30.0f;
        if (creature->GetVictim() == bot)
            score += 20.0f;

        if (score > bestScore)
        {
            bestScore = score;
            pack.PriorityTargetGuid = creature->GetGUID();
            pack.PriorityTargetEntry = creature->GetEntry();
            pack.PrioritySpellId = castSpellId;
        }
    }

    pack.InterruptPriority = pack.PackSize ? std::min(1.0f, float(pack.DangerousCasts) / float(pack.PackSize) + (pack.HealerCount ? 0.35f : 0.0f)) : 0.0f;
    pack.AoeValue = std::min(1.0f, float(pack.PackSize) / 5.0f);
    pack.CcValue = std::min(1.0f, float(pack.CasterCount + pack.HealerCount) / 4.0f);
    pack.PullRisk = std::min(1.0f, float(pack.PackSize + pack.EliteCount) / 7.0f + (pack.PatrolNearby ? 0.2f : 0.0f));

    if (Group* group = bot->GetGroup())
    {
        float totalHp = 0.0f;
        uint32 memberCount = 0;
        float healerManaTotal = 0.0f;
        uint32 healerCount = 0;
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
        {
            Player* member = itr->GetSource();
            if (!member || member->GetMap() != bot->GetMap())
                continue;

            float hp = UnitHealthPct(member);
            totalHp += hp;
            pack.LowestAllyHpPct = memberCount ? std::min(pack.LowestAllyHpPct, hp) : hp;
            ++memberCount;

            uint8 roles = group->GetLfgRoles(member->GetGUID());
            if (roles & lfg::PLAYER_ROLE_HEALER)
            {
                uint32 maxMana = member->GetMaxPower(POWER_MANA);
                healerManaTotal += maxMana ? float(member->GetPower(POWER_MANA)) / float(maxMana) : 1.0f;
                ++healerCount;
            }
        }

        if (memberCount)
            pack.PartyAverageHpPct = totalHp / float(memberCount);
        if (healerCount)
            pack.HealerManaPct = healerManaTotal / float(healerCount);
    }
    else
    {
        pack.PartyAverageHpPct = UnitHealthPct(bot);
        pack.LowestAllyHpPct = pack.PartyAverageHpPct;
    }

    Player* anchor = FindDungeonAnchor(bot);
    Unit* focusMutable = focus ? const_cast<Unit*>(focus) : nullptr;
    if (anchor && focusMutable && focusMutable->GetVictim() == anchor)
        pack.TankThreat = 1.0f;
    else if (focusMutable && focusMutable->GetVictim() == bot && std::string(GetDungeonRole(bot)) == "tank")
        pack.TankThreat = 1.0f;
    else if (focusMutable && focusMutable->GetVictim())
        pack.TankThreat = 0.35f;

    return pack;
}

BotWorldPopulationMgr::DungeonTrashActionResult BotWorldPopulationMgr::TryDungeonTrash(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity)
{
    DungeonTrashActionResult result;
    if (!_config.AllowDungeons || !bot || !bot->GetMap() || !bot->GetMap()->IsNonRaidDungeon())
        return result;

    result.Handled = true;
    Player* anchor = FindDungeonAnchor(bot);
    char const* role = GetDungeonRole(bot);
    Unit* groupTarget = FindGroupCombatTarget(bot, anchor);
    if (!groupTarget && !state.TargetGuid.IsEmpty())
        groupTarget = ObjectAccessor::GetUnit(*bot, state.TargetGuid);

    result.Pack = BuildDungeonTrashPackFeatures(bot, groupTarget);
    if (!groupTarget && !result.Pack.PriorityTargetGuid.IsEmpty())
        groupTarget = ObjectAccessor::GetUnit(*bot, result.Pack.PriorityTargetGuid);
    result.Target = groupTarget;

    if (anchor && !groupTarget && bot->GetExactDist(anchor) > 7.0f)
    {
        BotActionExecutor executor;
        executor.MoveFollow(anchor, bot);
        result.Action = "formation_follow";
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, result.Situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, "move_started", nullptr, "dungeon_formation", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), result.Pack.PackSize);
        return result;
    }

    if (!groupTarget)
    {
        result.Action = "wait_for_pull";
        return result;
    }

    state.TargetGuid = groupTarget->GetGUID();

    uint32 interruptSpell = SelectInterruptSpell(bot);
    if (result.Pack.InterruptPriority >= 0.5f && interruptSpell && TryCastCombatSpell(bot, groupTarget, interruptSpell))
    {
        result.Action = "interrupt_priority_cast";
        result.SpellId = interruptSpell;
        std::string raw = BuildRawJson(bot, groupTarget);
        std::string semantic = BuildSemanticJson(bot, groupTarget, result.Situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, "interrupt_success", groupTarget, "ok", raw.c_str(), semantic.c_str(), result.Pack.InterruptPriority, result.Pack.PackSize, interruptSpell);
        return result;
    }

    if (std::string(role) == "healer")
    {
        Unit* healTarget = nullptr;
        if (Group* group = bot->GetGroup())
        {
            float lowestHp = 1.0f;
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* member = itr->GetSource();
                if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap() || !bot->IsWithinLOSInMap(member))
                    continue;

                float hp = UnitHealthPct(member);
                if (!healTarget || hp < lowestHp)
                {
                    healTarget = member;
                    lowestHp = hp;
                }
            }
        }
        if (!healTarget)
            healTarget = bot;

        uint32 healSpell = SelectHealSpell(bot);
        if (healSpell && UnitHealthPct(healTarget) < 0.75f && TryCastFriendlySpell(bot, healTarget, healSpell))
        {
            result.Action = "heal_lowest_ally";
            result.SpellId = healSpell;
            result.Target = healTarget;
            std::string raw = BuildRawJson(bot, groupTarget);
            std::string semantic = BuildSemanticJson(bot, groupTarget, result.Situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, "trash_heal", groupTarget, "ok", raw.c_str(), semantic.c_str(), UnitHealthPct(healTarget), result.Pack.PackSize, healSpell);
            return result;
        }

        if (anchor && bot->GetExactDist(anchor) > 18.0f)
        {
            BotActionExecutor executor;
            executor.MoveFollow(anchor, bot);
            result.Action = "healer_follow_tank";
            return result;
        }
    }

    if (std::string(role) != "tank" && anchor && anchor->GetVictim() == nullptr && !bot->IsInCombat())
    {
        BotActionExecutor executor;
        executor.MoveFollow(anchor, bot);
        result.Action = "avoid_extra_pull";
        result.Target = nullptr;
        return result;
    }

    BotActionExecutor executor;
    BotActionResult pull = executor.Pull(bot, groupTarget);
    uint32 spellId = SelectCombatSpell(bot, groupTarget);
    bool cast = spellId && TryCastCombatSpell(bot, groupTarget, spellId);
    result.Action = std::string(role) == "tank" ? "tank_establish_threat" : (result.Pack.AoeValue >= 0.6f ? "dps_aoe_pack" : "dps_focus_target");
    result.SpellId = cast ? spellId : 0;
    result.Failure = pull != BotActionResult::Ok;
    result.Rare = result.Pack.DangerousCasts > 0 || result.Pack.PullRisk >= 0.75f;

    std::string raw = BuildRawJson(bot, groupTarget);
    std::string semantic = BuildSemanticJson(bot, groupTarget, result.Situation.c_str(), &power, stage, activity);
    RecordEvent(state, bot, "trash_action", groupTarget, ToString(pull), raw.c_str(), semantic.c_str(), result.Pack.PullRisk, result.Pack.PackSize, result.SpellId);
    if (!state.WasInCombat)
        RecordEvent(state, bot, "combat_started", groupTarget, "dungeon_trash", raw.c_str(), semantic.c_str(), result.Pack.PullRisk, result.Pack.PackSize);
    state.WasInCombat = true;
    return result;
}

char const* BotWorldPopulationMgr::GetDungeonRole(Player* bot) const
{
    if (!bot)
        return "dps";

    if (Group* group = bot->GetGroup())
    {
        uint8 roles = group->GetLfgRoles(bot->GetGUID());
        if (roles & lfg::PLAYER_ROLE_TANK)
            return "tank";
        if (roles & lfg::PLAYER_ROLE_HEALER)
            return "healer";
        if (roles & lfg::PLAYER_ROLE_DAMAGE)
            return "dps";
    }

    std::string botRole = sBotMgr->GetBotRoleName(bot->GetGUID());
    if (botRole.find("holy") != std::string::npos || botRole.find("healer") != std::string::npos)
        return "healer";
    if (botRole.find("tank") != std::string::npos)
        return "tank";

    switch (bot->getClass())
    {
        case CLASS_WARRIOR:
        case CLASS_DEATH_KNIGHT:
            return "tank";
        case CLASS_PRIEST:
            return "healer";
        default:
            return "dps";
    }
}

uint32 BotWorldPopulationMgr::SelectInterruptSpell(Player* bot) const
{
    if (!bot)
        return 0;

    uint32 candidates[4] = { 0, 0, 0, 0 };
    switch (bot->getClass())
    {
        case CLASS_WARRIOR: candidates[0] = 6552; break;       // Pummel
        case CLASS_ROGUE: candidates[0] = 1766; break;         // Kick
        case CLASS_MAGE: candidates[0] = 2139; break;          // Counterspell
        case CLASS_SHAMAN: candidates[0] = 57994; break;       // Wind Shear
        case CLASS_DEATH_KNIGHT: candidates[0] = 47528; break; // Mind Freeze
        case CLASS_PALADIN: candidates[0] = 96231; break;      // Rebuke
        case CLASS_DRUID: candidates[0] = 80965; break;        // Skull Bash
        default: break;
    }

    for (uint32 spellId : candidates)
        if (spellId && bot->HasSpell(spellId))
            return spellId;

    return 0;
}

uint32 BotWorldPopulationMgr::SelectHealSpell(Player* bot) const
{
    if (!bot)
        return 0;

    uint32 candidates[4] = { 0, 0, 0, 0 };
    switch (bot->getClass())
    {
        case CLASS_PALADIN:
            candidates[0] = 635;    // Holy Light
            candidates[1] = 19750;  // Flash of Light
            break;
        case CLASS_PRIEST:
            candidates[0] = 2061;   // Flash Heal
            candidates[1] = 2050;   // Heal
            break;
        case CLASS_SHAMAN:
            candidates[0] = 331;    // Healing Wave
            candidates[1] = 8004;   // Healing Surge
            break;
        case CLASS_DRUID:
            candidates[0] = 8936;   // Regrowth
            candidates[1] = 5185;   // Healing Touch
            break;
        default:
            break;
    }

    for (uint32 spellId : candidates)
        if (spellId && bot->HasSpell(spellId))
            return spellId;

    return 0;
}

bool BotWorldPopulationMgr::TryCastFriendlySpell(Player* bot, Unit* target, uint32 spellId) const
{
    if (!bot || !target || !spellId || !target->IsAlive() || !bot->IsValidAssistTarget(target))
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

std::string BotWorldPopulationMgr::BuildDungeonTrashPackJson(DungeonTrashPackFeatures const& pack) const
{
    std::ostringstream json;
    json << "{\"pack_size\":" << pack.PackSize
         << ",\"elite_count\":" << pack.EliteCount
         << ",\"caster_count\":" << pack.CasterCount
         << ",\"healer_count\":" << pack.HealerCount
         << ",\"active_casts\":" << pack.ActiveCasts
         << ",\"dangerous_casts\":" << pack.DangerousCasts
         << ",\"interrupt_priority\":" << pack.InterruptPriority
         << ",\"aoe_value\":" << pack.AoeValue
         << ",\"cc_value\":" << pack.CcValue
         << ",\"pull_risk\":" << pack.PullRisk
         << ",\"patrol_nearby\":" << (pack.PatrolNearby ? "true" : "false")
         << ",\"tank_threat\":" << pack.TankThreat
         << ",\"party_average_hp_pct\":" << pack.PartyAverageHpPct
         << ",\"lowest_ally_hp_pct\":" << pack.LowestAllyHpPct
         << ",\"healer_mana_pct\":" << pack.HealerManaPct
         << ",\"priority_target_guid\":" << pack.PriorityTargetGuid.GetCounter()
         << ",\"priority_target_entry\":" << pack.PriorityTargetEntry
         << ",\"priority_spell_id\":" << pack.PrioritySpellId << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildBossMechanicsJson(BossMechanicFeatures const& features) const
{
    SpellInfo const* spellInfo = features.CastSpellId ? sSpellMgr->GetSpellInfo(features.CastSpellId) : nullptr;
    std::ostringstream json;
    json << "{\"encounter_type\":\"" << (features.RaidEncounter ? "raid_boss" : "dungeon_boss") << "\""
         << ",\"boss_present\":" << (features.BossPresent ? "true" : "false")
         << ",\"boss_guid\":" << features.BossGuid.GetCounter()
         << ",\"boss_entry\":" << features.BossEntry
         << ",\"phase\":0"
         << ",\"boss_casting\":" << (features.BossCasting ? "true" : "false")
         << ",\"cast_spell_id\":" << features.CastSpellId
         << ",\"cast_remaining_ms\":" << features.CastRemainingMs
         << ",\"spell_tags\":" << BuildSpellTagJson(spellInfo, features.MustInterrupt, features.GroundDanger, features.TankSpike, features.RaidDamage, features.AddsActive)
         << ",\"dangerous_cast\":" << (features.DangerousCast ? "true" : "false")
         << ",\"requires_interrupt\":" << (features.MustInterrupt ? "true" : "false")
         << ",\"interrupt_priority\":" << features.InterruptPriority
         << ",\"ground_danger_near_me\":" << (features.GroundDanger ? features.DangerScore : 0.0f)
         << ",\"safe_position_available\":true"
         << ",\"move_out\":" << (features.MoveOut ? "true" : "false")
         << ",\"tank_spike\":" << (features.TankSpike ? "true" : "false")
         << ",\"raid_damage\":" << (features.RaidDamage ? "true" : "false")
         << ",\"adds_active\":" << (features.AddsActive ? "true" : "false")
         << ",\"add_count\":" << features.AddCount
         << ",\"priority_add_guid\":" << features.PriorityAddGuid.GetCounter()
         << ",\"requires_stack\":" << (features.StackPlaceholder ? "true" : "false")
         << ",\"requires_spread\":" << (features.SpreadPlaceholder ? "true" : "false")
         << ",\"tank_swap_pressure\":" << (features.TankSpike ? std::max(0.0f, 1.0f - features.TankHpPct) : 0.0f)
         << ",\"party\":{\"tank_hp_pct\":" << features.TankHpPct
         << ",\"party_average_hp_pct\":" << features.PartyAverageHpPct
         << ",\"lowest_ally_hp_pct\":" << features.LowestAllyHpPct
         << ",\"healer_mana_pct\":" << features.HealerManaPct << "}"
         << ",\"danger_score\":" << features.DangerScore << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRaidRoleAssignmentJson(RaidRoleAssignment const& assignment) const
{
    std::ostringstream json;
    json << "{\"role\":\"" << JsonEscape(assignment.Role) << "\""
         << ",\"subgroup\":" << uint32(assignment.SubGroup)
         << ",\"raid_size\":" << assignment.RaidSize
         << ",\"tank_count\":" << assignment.TankCount
         << ",\"healer_count\":" << assignment.HealerCount
         << ",\"dps_count\":" << assignment.DpsCount
         << ",\"role_index\":" << assignment.RoleIndex
         << ",\"main_tank_guid\":" << assignment.MainTankGuid.GetCounter()
         << ",\"off_tank_guid\":" << assignment.OffTankGuid.GetCounter()
         << ",\"raid_leader_guid\":" << assignment.RaidLeaderGuid.GetCounter() << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRaidPositioningAnchorsJson(RaidPositioningAnchors const& anchors) const
{
    std::ostringstream json;
    json << "{\"active\":" << (anchors.Active ? "true" : "false")
         << ",\"anchor_type\":\"" << JsonEscape(anchors.AnchorType) << "\""
         << ",\"anchor_guid\":" << anchors.AnchorGuid.GetCounter()
         << ",\"anchor\":{\"x\":" << anchors.AnchorX << ",\"y\":" << anchors.AnchorY << ",\"z\":" << anchors.AnchorZ << "}"
         << ",\"stack_anchor\":{\"x\":" << anchors.StackX << ",\"y\":" << anchors.StackY << ",\"z\":" << anchors.StackZ << "}"
         << ",\"spread_anchor\":{\"x\":" << anchors.SpreadX << ",\"y\":" << anchors.SpreadY << ",\"z\":" << anchors.SpreadZ << "}"
         << ",\"distance_to_anchor\":" << anchors.DistanceToAnchor << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRaidMechanicAdapterJson(RaidMechanicAdapter const& adapter) const
{
    std::ostringstream json;
    json << "{\"mechanic_family\":\"" << JsonEscape(adapter.MechanicFamily) << "\""
         << ",\"assignment_type\":\"" << JsonEscape(adapter.AssignmentType) << "\""
         << ",\"recommended_action\":\"" << JsonEscape(adapter.RecommendedAction) << "\""
         << ",\"assigned_target_guid\":" << adapter.AssignedTargetGuid.GetCounter()
         << ",\"priority\":" << adapter.Priority
         << ",\"heroic_only\":" << (adapter.HeroicOnly ? "true" : "false") << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRaidGearTargetPlanJson(RaidGearTargetPlan const& plan) const
{
    std::ostringstream json;
    json << "{\"current_item_level\":" << plan.CurrentItemLevel
         << ",\"target_item_level\":" << plan.TargetItemLevel
         << ",\"needed_item_level\":" << plan.NeededItemLevel
         << ",\"recommended_activity\":\"" << JsonEscape(plan.RecommendedActivity) << "\""
         << ",\"ready_for_raid\":" << (plan.ReadyForRaid ? "true" : "false")
         << ",\"ready_for_heroic_raid\":" << (plan.ReadyForHeroicRaid ? "true" : "false") << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildHeroicRaidProgressionJson(HeroicRaidProgression const& progression) const
{
    std::ostringstream json;
    json << "{\"tracking_enabled\":" << (progression.TrackingEnabled ? "true" : "false")
         << ",\"heroic_eligible\":" << (progression.HeroicEligible ? "true" : "false")
         << ",\"stage\":\"" << JsonEscape(progression.Stage) << "\""
         << ",\"raid_attempts\":" << progression.RaidAttempts
         << ",\"raid_boss_kills\":" << progression.RaidBossKills
         << ",\"heroic_raid_boss_kills\":" << progression.HeroicRaidBossKills
         << ",\"wipes\":" << progression.Wipes
         << ",\"role_power_score\":" << progression.RolePowerScore
         << ",\"target_item_level\":" << progression.TargetItemLevel << "}";
    return json.str();
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

void BotWorldPopulationMgr::MoveToWanderPoint(Player* bot, WorldBotState& state)
{
    if (!bot)
        return;

    uint64 poiId = 0;
    float poiX = 0.0f;
    float poiY = 0.0f;
    float poiZ = 0.0f;
    if (FindMemoryPoiTarget(bot, poiX, poiY, poiZ, poiId))
    {
        if (bot->GetExactDist2d(poiX, poiY) <= INTERACTION_DISTANCE)
            MarkPoiVisited(poiId);
        else
            MoveBotToPoint(state, bot, poiX, poiY, poiZ);
        return;
    }

    float fromCenter = Distance2d(bot->GetPositionX(), bot->GetPositionY(), _config.CenterX, _config.CenterY);
    for (uint8 attempt = 0; attempt < 8; ++attempt)
    {
        float angle = fromCenter > _config.Radius ? bot->GetAngle(_config.CenterX, _config.CenterY) : frand(0.0f, 2.0f * float(M_PI));
        float distance = frand(8.0f, 25.0f);
        Position pos = bot->GetFirstCollisionPosition(distance, angle);
        if (GetLocalDangerScore(bot->GetGUID().GetCounter(), bot->GetMapId(), pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ()) >= 3.0f)
            continue;
        if (IsFailedPathRecently(bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), pos.GetPositionX(), pos.GetPositionY()))
            continue;

        MoveBotToPoint(state, bot, pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ());
        return;
    }

    Position fallback = bot->GetFirstCollisionPosition(4.0f, bot->GetAngle(_config.CenterX, _config.CenterY));
    MoveBotToPoint(state, bot, fallback.GetPositionX(), fallback.GetPositionY(), fallback.GetPositionZ());
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
    _experimentCoordinator.Configure(_runId, _config.BrainVersion);
}

void BotWorldPopulationMgr::RecordRunStop()
{
    if (!_runId)
        return;

    std::string summary = GetSummaryJson();
    CharacterDatabase.EscapeString(summary);
    CharacterDatabase.DirectPExecute("UPDATE experiment_bot_runs SET status = 'stopped', ended_at = NOW(), summary_json = '%s' WHERE id = " UI64FMTD, summary.c_str(), _runId);
}

BotWorldPopulationMgr::ReplayRecord BotWorldPopulationMgr::LoadReplayRecord(uint64 replayId) const
{
    ReplayRecord record;
    if (!replayId)
        return record;

    QueryResult result = CharacterDatabase.PQuery(
        "SELECT id, experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, "
        "bot_snapshot_json, world_snapshot_json, COALESCE(party_snapshot_json, ''), raw_state_json, semantic_state_json, "
        "COALESCE(chosen_action_json, ''), failure_json "
        "FROM experiment_bot_replay_records WHERE id = " UI64FMTD,
        replayId);
    if (!result)
        return record;

    Field* fields = result->Fetch();
    record.Loaded = true;
    record.Id = fields[0].GetUInt64();
    record.ExperimentId = fields[1].GetUInt64();
    record.RunId = fields[2].GetUInt64();
    record.BotGuid = fields[3].GetUInt32();
    record.ReplayType = fields[4].GetString();
    record.MapId = fields[5].GetUInt32();
    record.ZoneId = fields[6].GetUInt32();
    record.X = fields[7].GetFloat();
    record.Y = fields[8].GetFloat();
    record.Z = fields[9].GetFloat();
    record.O = fields[10].GetFloat();
    record.BotSnapshotJson = fields[11].GetString();
    record.WorldSnapshotJson = fields[12].GetString();
    record.PartySnapshotJson = fields[13].GetString();
    record.RawStateJson = fields[14].GetString();
    record.SemanticStateJson = fields[15].GetString();
    record.ChosenActionJson = fields[16].GetString();
    record.FailureJson = fields[17].GetString();
    return record;
}

BotWorldPopulationMgr::ReplayRecord BotWorldPopulationMgr::LoadReplayRecord(std::string const& replayType, std::string const& selector) const
{
    if (!selector.empty() && selector != "latest" && selector.find_first_not_of("0123456789") == std::string::npos)
        return LoadReplayRecord(uint64(strtoull(selector.c_str(), nullptr, 10)));

    std::string type = replayType.empty() ? "failure" : replayType;
    std::string where;
    if (type == "failure")
        where = "replay_type LIKE '%failure%'";
    else
    {
        CharacterDatabase.EscapeString(type);
        where = "replay_type = '" + type + "'";
    }

    std::string query =
        "SELECT id FROM experiment_bot_replay_records WHERE " + where +
        " ORDER BY id DESC LIMIT 1";
    if (QueryResult result = CharacterDatabase.Query(query.c_str()))
        return LoadReplayRecord(result->Fetch()[0].GetUInt64());

    return ReplayRecord();
}

void BotWorldPopulationMgr::RecordReplayEvent(WorldBotState const& state, Player* bot, char const* eventType, ReplayRecord const& record, char const* result, char const* contextJson)
{
    if (!_runId || !bot)
        return;

    uint64 clipId = _telemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";

    std::string raw = record.RawStateJson.empty() ? "{}" : record.RawStateJson;
    std::string semantic = record.SemanticStateJson.empty() ? "{}" : record.SemanticStateJson;
    std::string event = eventType ? eventType : "replay_event";
    std::string res = result ? result : "";
    std::string brain = _config.BrainVersion;
    std::string context = contextJson ? contextJson : "{}";
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(res);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(context);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, result, value_int, raw_json, semantic_json, context_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', '%s', %u, '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), res.c_str(),
        uint32(record.Id), raw.c_str(), semantic.c_str(), context.c_str());
}

BotWorldPopulationMgr::ReplayExecutionResult BotWorldPopulationMgr::ExecuteReplayRecord(ReplayRecord const& record, std::string const& brainVersion)
{
    ReplayExecutionResult result;
    result.ReplayId = record.Id;
    result.ReplayType = record.ReplayType;
    result.BrainVersion = brainVersion.empty() ? _config.BrainVersion : brainVersion;

    if (!record.Loaded)
    {
        result.FailureReason = "replay_record_not_found";
        return result;
    }

    if (_active)
    {
        result.FailureReason = "botexp_population_active";
        return result;
    }

    if (!sConfigMgr->GetBoolDefault("BotWorld.Enable", false) || !sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
    {
        result.FailureReason = "botworld_or_playerbot_disabled";
        return result;
    }

    uint64 oldExperimentId = _experimentId;
    uint64 oldRunId = _runId;
    uint32 oldElapsedMs = _elapsedMs;
    BotWorldExperimentConfig oldConfig = _config;
    BotWorldStatus oldMetrics = _metrics;
    std::vector<WorldBotState> oldBots = _bots;
    std::set<uint32> oldFailedSpawnGuids = _failedSpawnGuids;

    _config = BotWorldExperimentConfig();
    _config.Name = "replay_" + std::to_string(record.Id);
    _config.TargetPopulation = 1;
    _config.MapId = record.MapId;
    _config.ZoneId = record.ZoneId;
    _config.CenterX = record.X;
    _config.CenterY = record.Y;
    _config.CenterZ = record.Z;
    _config.Radius = 25.0f;
    _config.AllowCombat = true;
    _config.AllowQuesting = true;
    _config.AllowDungeons = record.ReplayType.find("boss") != std::string::npos || record.ReplayType.find("trash") != std::string::npos;
    _config.AllowRaids = record.ReplayType.find("raid") != std::string::npos || record.ReplayType.find("boss") != std::string::npos;
    _config.BrainVersion = result.BrainVersion;
    _bots.clear();
    _failedSpawnGuids.clear();
    _metrics = BotWorldStatus();
    _metrics.Active = false;
    _metrics.Name = _config.Name;
    _metrics.TargetBots = 1;
    _elapsedMs = 0;

    RecordRunStart();
    result.RunId = _runId;

    Player* bot = nullptr;
    if (record.BotGuid)
        bot = sBotMgr->SpawnWorldBot("any", std::to_string(record.BotGuid), record.MapId, record.X, record.Y, record.Z, record.O);

    if (!bot)
    {
        uint32 fallbackGuid = SelectPoolCandidateGuid();
        if (fallbackGuid)
            bot = sBotMgr->SpawnWorldBot("any", std::to_string(fallbackGuid), record.MapId, record.X, record.Y, record.Z, record.O);
    }

    if (!bot)
    {
        result.FailureReason = "no_available_replay_bot";
        RecordRunStop();
        _experimentId = oldExperimentId;
        _runId = oldRunId;
        _elapsedMs = oldElapsedMs;
        _config = oldConfig;
        _metrics = oldMetrics;
        _bots = oldBots;
        _failedSpawnGuids = oldFailedSpawnGuids;
        return result;
    }

    bot->CombatStop(true);
    bot->CastStop();
    if (!bot->IsAlive())
        bot->ResurrectPlayer(1.0f, false);
    bot->TeleportTo(record.MapId, record.X, record.Y, record.Z, record.O);
    bot->SetFullHealth();
    bot->SetFullPower(bot->GetPowerType());

    WorldBotState state;
    state.Guid = bot->GetGUID();
    state.DecisionTimer = 0;
    state.LastX = record.X;
    state.LastY = record.Y;
    state.LastZ = record.Z;
    state.ActivityType = "replay";
    _bots.push_back(state);
    _metrics.ActiveBots = 1;

    RecordActivityStart(_bots.back(), bot);
    std::ostringstream startContext;
    startContext << "{\"replay_id\":" << record.Id
                 << ",\"source_experiment_id\":" << record.ExperimentId
                 << ",\"source_run_id\":" << record.RunId
                 << ",\"source_bot_guid\":" << record.BotGuid
                 << ",\"replay_type\":\"" << JsonEscape(record.ReplayType) << "\""
                 << ",\"source_failure\":" << (record.FailureJson.empty() ? "{}" : record.FailureJson)
                 << ",\"source_action\":" << (record.ChosenActionJson.empty() ? "{}" : record.ChosenActionJson) << "}";
    RecordReplayEvent(_bots.back(), bot, "replay_started", record, "ok", startContext.str().c_str());

    UpdateBot(_bots.back(), std::max<uint32>(500, sConfigMgr->GetIntDefault("BotWorld.DecisionTickMs", 3000)));

    BotRolePowerBreakdown finalPower = BotLongTermProgressionBrain::CalculateRolePower(bot);
    result.FinalPower = finalPower.Total;
    result.Decisions = _metrics.Decisions;
    result.Failures = _metrics.Failures;
    result.Deaths = _metrics.Deaths;
    result.Kills = _metrics.Kills;
    result.StuckEvents = _metrics.StuckEvents;
    result.Success = bot->IsAlive() && !_metrics.Failures && !_metrics.Deaths;
    result.Ok = true;
    result.FirstAction = record.ChosenActionJson.empty() ? "{}" : record.ChosenActionJson;

    std::ostringstream finishContext;
    finishContext << "{\"replay_id\":" << record.Id
                  << ",\"success\":" << (result.Success ? "true" : "false")
                  << ",\"decisions\":" << result.Decisions
                  << ",\"failures\":" << result.Failures
                  << ",\"deaths\":" << result.Deaths
                  << ",\"kills\":" << result.Kills
                  << ",\"stuck_events\":" << result.StuckEvents
                  << ",\"final_power\":" << result.FinalPower << "}";
    RecordReplayEvent(_bots.back(), bot, "replay_finished", record, result.Success ? "success" : "failure", finishContext.str().c_str());

    RecordActivityStop(_bots.back(), bot);
    sBotMgr->RemoveWorldBot(bot->GetGUID());
    _bots.clear();
    RecordRunStop();

    _experimentId = oldExperimentId;
    _runId = oldRunId;
    _elapsedMs = oldElapsedMs;
    _config = oldConfig;
    _metrics = oldMetrics;
    _bots = oldBots;
    _failedSpawnGuids = oldFailedSpawnGuids;
    return result;
}

std::string BotWorldPopulationMgr::BuildReplayResultJson(ReplayExecutionResult const& result) const
{
    std::ostringstream json;
    json << "{\"ok\":" << (result.Ok ? "true" : "false")
         << ",\"action\":\"botexp_replay\""
         << ",\"replay_id\":" << result.ReplayId
         << ",\"run_id\":" << result.RunId
         << ",\"replay_type\":\"" << JsonEscape(result.ReplayType) << "\""
         << ",\"brain_version\":\"" << JsonEscape(result.BrainVersion) << "\""
         << ",\"success\":" << (result.Success ? "true" : "false")
         << ",\"metrics\":{\"decisions\":" << result.Decisions
         << ",\"failures\":" << result.Failures
         << ",\"deaths\":" << result.Deaths
         << ",\"kills\":" << result.Kills
         << ",\"stuck_events\":" << result.StuckEvents
         << ",\"final_power\":" << result.FinalPower << "}"
         << ",\"failure_reason\":" << (result.FailureReason.empty() ? "null" : ("\"" + JsonEscape(result.FailureReason) + "\""))
         << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::Replay(std::string const& replayType, std::string const& selector, std::string const& brainVersion)
{
    ReplayRecord record = LoadReplayRecord(replayType, selector.empty() ? "latest" : selector);
    std::string version = brainVersion.empty() ? sConfigMgr->GetStringDefault("BotExperiment.BrainVersion", _config.BrainVersion) : brainVersion;
    return BuildReplayResultJson(ExecuteReplayRecord(record, version));
}

std::string BotWorldPopulationMgr::CompareBrains(uint64 replayId, std::string const& firstBrainVersion, std::string const& secondBrainVersion)
{
    ReplayRecord record = LoadReplayRecord(replayId);
    ReplayExecutionResult first = ExecuteReplayRecord(record, firstBrainVersion);
    ReplayExecutionResult second = ExecuteReplayRecord(record, secondBrainVersion);
    std::ostringstream json;
    json << "{\"ok\":" << ((first.Ok && second.Ok) ? "true" : "false")
         << ",\"action\":\"botexp_comparebrain\""
         << ",\"replay_id\":" << replayId
         << ",\"first\":" << BuildReplayResultJson(first)
         << ",\"second\":" << BuildReplayResultJson(second)
         << ",\"winner\":";
    if (!first.Ok || !second.Ok || first.Success == second.Success)
        json << "null";
    else
        json << "\"" << JsonEscape(first.Success ? firstBrainVersion : secondBrainVersion) << "\"";
    json << ",\"failure_reason\":";
    if (first.Ok && second.Ok)
        json << "null";
    else if (!first.FailureReason.empty())
        json << "\"" << JsonEscape(first.FailureReason) << "\"";
    else
        json << "\"" << JsonEscape(second.FailureReason) << "\"";
    json << "}";
    return json.str();
}

void BotWorldPopulationMgr::RecordActivityStart(WorldBotState& state, Player* bot)
{
    if (!_runId || !bot)
        return;

    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
    std::vector<BotActivityScore> activityScores = _config.EnableProgression
        ? BotLongTermProgressionBrain::ScoreActivities(bot, power, stage, _config.AllowQuesting, _config.AllowCombat, &_learningConfig)
        : std::vector<BotActivityScore>(1, BotActivityScore());
    ApplyPolicyModelScores(activityScores, bot, power, stage);
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

    if (bot)
    {
        std::string features = BuildEmbeddingFeaturesJson(bot, nullptr, "area", bot->GetAreaId(), state.ActivityType.c_str());
        UpdateSemanticOutcomeStats(bot, "area", bot->GetAreaId(), "activity_completed", "ok", powerDelta, powerDelta, false, features.c_str());
        std::string activityFeatures = BuildEmbeddingFeaturesJson(bot, nullptr, "activity", BotExperienceLearningPolicy::StableKey(state.ActivityType), state.ActivityType.c_str());
        UpdateSemanticOutcomeStats(bot, "activity", BotExperienceLearningPolicy::StableKey(state.ActivityType), "activity_completed", "ok", powerDelta, powerDelta, deaths > 0, activityFeatures.c_str());
    }
}

void BotWorldPopulationMgr::RecordGearEvaluation(WorldBotState& state, Player* bot, BotGearUpgradeEvaluation const& evaluation, char const* rawJson, char const* semanticJson)
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

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput("gear_evaluated", "upgrade_candidate", "gear_upgrade", nullptr, 0, 0, evaluation.ItemId, evaluation.PowerDelta, evaluation.ItemId, false, evaluation.PowerDelta > 0.0f);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), ++state.EventSequence);
    if (!policy.writeEvent)
    {
        std::string features = BuildEmbeddingFeaturesJson(bot, nullptr, "item", evaluation.ItemId, "gear_upgrade");
        UpdateSemanticOutcomeStats(bot, "item", evaluation.ItemId, "gear_upgrade", "upgrade_candidate", evaluation.PowerDelta, evaluation.PowerDelta, false, features.c_str());
        return;
    }

    uint64 clipId = _telemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";

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

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, item_id, result, value_float, value_int, raw_json, semantic_json, context_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', %u, '%s', %f, %u, '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), evaluation.ItemId,
        result.c_str(), evaluation.PowerDelta, evaluation.ItemId, raw.c_str(), semantic.c_str(), contextJson.c_str());

    std::string features = BuildEmbeddingFeaturesJson(bot, nullptr, "item", evaluation.ItemId, "gear_upgrade");
    UpdateSemanticOutcomeStats(bot, "item", evaluation.ItemId, "gear_upgrade", "upgrade_candidate", evaluation.PowerDelta, evaluation.PowerDelta, false, features.c_str());
}

void BotWorldPopulationMgr::RecordRaidTelemetry(WorldBotState& state, Player* bot, Unit const* boss, char const* eventType, char const* result, BossMechanicFeatures const& features, RaidRoleAssignment const& assignment, RaidPositioningAnchors const& anchors, RaidMechanicAdapter const& adapter, RaidGearTargetPlan const& gearPlan, HeroicRaidProgression const& progression, char const* rawJson, char const* semanticJson, float valueFloat, uint32 valueInt, uint32 spellId)
{
    if (!_runId || !bot || !features.RaidEncounter)
        return;

    ++_metrics.RaidTelemetryEvents;
    bool failure = EventLooksFailure(eventType, result) || (eventType && std::string(eventType) == "raid_wipe");
    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(eventType ? eventType : "raid_telemetry", result ? result : "ok", features.RaidEncounter ? "raid_boss" : "dungeon_boss", boss, spellId ? spellId : features.CastSpellId, 0, 0, valueFloat, valueInt, failure, true);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), ++state.EventSequence);
    if (!policy.writeEvent)
        return;

    std::ostringstream context;
    context << "{\"raid_role_assignment\":" << BuildRaidRoleAssignmentJson(assignment)
            << ",\"raid_positioning_anchors\":" << BuildRaidPositioningAnchorsJson(anchors)
            << ",\"raid_mechanic_adapter\":" << BuildRaidMechanicAdapterJson(adapter)
            << ",\"raid_boss_mechanics\":" << BuildBossMechanicsJson(features)
            << ",\"gear_target_plan\":" << BuildRaidGearTargetPlanJson(gearPlan)
            << ",\"heroic_raid_progression\":" << BuildHeroicRaidProgressionJson(progression) << "}";

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string event = eventType ? eventType : "raid_telemetry";
    std::string eventResult = result ? result : "ok";
    std::string brain = _config.BrainVersion;
    std::string contextJson = context.str();
    uint64 clipId = MaybeCaptureTelemetryClip(bot, boss, policyInput, policy, rawJson, semanticJson);
    if (!clipId)
        clipId = _telemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(eventResult);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(contextJson);

    uint64 targetGuid = boss ? boss->GetGUID().GetCounter() : features.BossGuid.GetCounter();
    uint32 targetEntry = features.BossEntry;
    if (Creature const* creature = boss ? boss->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, target_guid, target_entry, spell_id, result, value_float, value_int, raw_json, semantic_json, context_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', " UI64FMTD ", %u, %u, '%s', %f, %u, '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), targetGuid,
        targetEntry, spellId ? spellId : features.CastSpellId, eventResult.c_str(), valueFloat, valueInt, raw.c_str(), semantic.c_str(), contextJson.c_str());

    uint32 mechanicKey = features.MoveOut ? 1 : (features.MustInterrupt ? 2 : (features.AddsActive ? 5 : (features.RaidDamage ? 4 : 11)));
    std::string mechanicFeatures = BuildEmbeddingFeaturesJson(bot, boss, "mechanic", mechanicKey, adapter.MechanicFamily.c_str());
    UpdateSemanticOutcomeStats(bot, "mechanic", mechanicKey, event.c_str(), eventResult.c_str(), valueFloat, 0.0f, eventResult == "failed" || eventResult == "death", mechanicFeatures.c_str());
    if (gearPlan.NeededItemLevel > 0.0f)
    {
        std::string gearFeatures = BuildEmbeddingFeaturesJson(bot, nullptr, "item", uint32(gearPlan.TargetItemLevel), "raid_gear_target");
        UpdateSemanticOutcomeStats(bot, "item", uint32(gearPlan.TargetItemLevel), "raid_gear_target", gearPlan.RecommendedActivity.c_str(), gearPlan.NeededItemLevel, -gearPlan.NeededItemLevel, false, gearFeatures.c_str());
    }
    if (policy.writeReplay)
        RecordPolicyReplay(state, bot, boss, policyInput, rawJson, semanticJson);
}

void BotWorldPopulationMgr::RecordQuestObjectiveProgressForTarget(WorldBotState& state, Player* bot, Unit const* target, char const* rawJson, char const* semanticJson)
{
    if (!_runId || !bot || !target)
        return;

    Creature const* creature = target->ToCreature();
    if (!creature)
        return;
    QuestObjectivePlan activePlan;
    if (IsTrainingDummy(target) && (!FindActiveQuestObjective(bot, activePlan) || !IsTrainingDummyAllowedForQuest(activePlan, target)))
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

            uint32 current = questStatus.second.CreatureOrGOCount[i];
            uint32 before = state.LastQuestProgressBefore;
            bool completed = bot->CanCompleteQuest(quest->GetQuestId());
            std::ostringstream context;
            context << "{\"required_entry\":" << entry
                    << ",\"required_count\":" << quest->RequiredNpcOrGoCount[i]
                    << ",\"current_count\":" << current
                    << ",\"progress_before\":" << before
                    << ",\"progress_after\":" << current
                    << ",\"objective_index\":" << uint32(i) << "}";
            if (current > before || completed)
            {
                ++_metrics.QuestObjectiveProgress;
                state.LastQuestObjectiveProgress = _metrics.QuestObjectiveProgress;
                RecordQuestEvent(state, bot, "objective_progress", quest->GetQuestId(), target, "kill_verified", rawJson, semanticJson, current, 0, context.str().c_str());

                if (completed)
                    bot->CompleteQuest(quest->GetQuestId());
            }
            else
            {
                state.LastNoProgressReason = "counter_unchanged";
                RecordQuestEvent(state, bot, "objective_no_progress", quest->GetQuestId(), target, "counter_unchanged", rawJson, semanticJson, current, 0, context.str().c_str());
            }
        }
    }
}

void BotWorldPopulationMgr::RecordQuestEvent(WorldBotState& state, Player* bot, char const* eventType, uint32 questId, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, uint32 valueInt, uint32 itemId, char const* contextJson)
{
    if (!bot)
        return;

    RecordExperimentSegmentEvent(bot, eventType, result, questId, target, _telemetryBuffer.GetActiveClipId(bot->GetGUID()), rawJson, semanticJson);

    if (!_runId)
        return;

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(eventType ? eventType : "quest_event", result ? result : "", "quest", target, 0, questId, itemId, 0.0f, valueInt, EventLooksFailure(eventType, result), eventType && (std::string(eventType) == "quest_completed" || std::string(eventType) == "quest_accepted"));
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), ++state.EventSequence);
    if (!policy.writeEvent)
        return;

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string event = eventType ? eventType : "quest_event";
    std::string res = result ? result : "";
    std::string brain = _config.BrainVersion;
    std::string context = contextJson ? contextJson : "{}";
    uint64 clipId = MaybeCaptureTelemetryClip(bot, target, policyInput, policy, rawJson, semanticJson);
    if (!clipId)
        clipId = _telemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";
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

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, target_guid, target_entry, quest_id, item_id, result, value_int, raw_json, semantic_json, context_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', " UI64FMTD ", %u, %u, %u, '%s', %u, '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), targetGuid, targetEntry,
        questId, itemId, res.c_str(), valueInt, raw.c_str(), semantic.c_str(), context.c_str());

    UpdateSemanticStatsFromEvent(bot, target, eventType, result, 0.0f, valueInt, 0, semanticJson);
    if (questId)
    {
        std::string features = BuildEmbeddingFeaturesJson(bot, target, "quest", questId, eventType ? eventType : "quest_event");
        UpdateSemanticOutcomeStats(bot, "quest", questId, eventType, result, float(valueInt), 0.0f, EventLooksFailure(eventType, result), features.c_str());
    }
    if (itemId)
    {
        std::string features = BuildEmbeddingFeaturesJson(bot, target, "item", itemId, eventType ? eventType : "quest_reward");
        UpdateSemanticOutcomeStats(bot, "item", itemId, eventType, result, float(valueInt), 0.0f, EventLooksFailure(eventType, result), features.c_str());
    }
}

void BotWorldPopulationMgr::RecordExperimentSegmentEvent(Player* bot, char const* eventType, char const* result, uint32 questId, Unit const* target, uint64 clipId, char const* rawJson, char const* semanticJson)
{
    if (!bot || !eventType || !*eventType)
        return;

    uint64 targetGuid = target ? target->GetGUID().GetCounter() : 0;
    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();

    std::ostringstream trigger;
    trigger << "{\"event_type\":\"" << JsonEscape(eventType)
            << "\",\"result\":\"" << JsonEscape(result ? result : "")
            << "\",\"quest_id\":" << questId
            << ",\"target_guid\":" << targetGuid
            << ",\"target_entry\":" << targetEntry
            << ",\"raw\":" << (rawJson && *rawJson ? rawJson : "{}")
            << ",\"semantic\":" << (semanticJson && *semanticJson ? semanticJson : "{}") << "}";

    std::ostringstream summary;
    summary << "{\"event_type\":\"" << JsonEscape(eventType)
            << "\",\"result\":\"" << JsonEscape(result ? result : "")
            << "\",\"quest_id\":" << questId
            << ",\"clip_id\":" << clipId
            << ",\"map_id\":" << bot->GetMapId()
            << ",\"zone_id\":" << bot->GetZoneId()
            << ",\"area_id\":" << bot->GetAreaId() << "}";

    _experimentCoordinator.HandleTelemetryEvent(bot, eventType, result, questId, 0, clipId, trigger.str().c_str(), summary.str().c_str());
}

void BotWorldPopulationMgr::RecordQuestReplay(WorldBotState const& state, Player* bot, char const* replayType, uint32 questId, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson)
{
    if (!_runId || !bot)
        return;

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(replayType ? replayType : "quest_failure", "failed", "quest", nullptr, 0, questId, 0, 0.0f, 0, true, true);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), 0);
    if (!policy.writeReplay)
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

void BotWorldPopulationMgr::RecordBossReplay(WorldBotState const& state, Player* bot, Unit const* boss, BossMechanicFeatures const& features, char const* replayType, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson)
{
    if (!_runId || !bot)
        return;

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(replayType ? replayType : "boss_mechanic_failure", "failed", features.RaidEncounter ? "raid_boss" : "dungeon_boss", boss, features.CastSpellId, 0, 0, features.DangerScore, features.BossEntry, true, true);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), 0);
    if (!policy.writeReplay)
        return;

    std::ostringstream botSnapshot;
    botSnapshot << "{\"guid\":" << bot->GetGUID().GetCounter()
                << ",\"level\":" << uint32(bot->getLevel())
                << ",\"class_id\":" << uint32(bot->getClass())
                << ",\"hp\":" << bot->GetHealth()
                << ",\"max_hp\":" << bot->GetMaxHealth()
                << ",\"role\":\"" << JsonEscape(GetDungeonRole(bot)) << "\""
                << ",\"activity\":\"" << JsonEscape(state.ActivityType) << "\"}";

    std::ostringstream worldSnapshot;
    worldSnapshot << "{\"map_id\":" << bot->GetMapId()
                  << ",\"zone_id\":" << bot->GetZoneId()
                  << ",\"area_id\":" << bot->GetAreaId()
                  << ",\"x\":" << bot->GetPositionX()
                  << ",\"y\":" << bot->GetPositionY()
                  << ",\"z\":" << bot->GetPositionZ()
                  << ",\"o\":" << bot->GetOrientation()
                  << ",\"boss_guid\":" << (boss ? boss->GetGUID().GetCounter() : features.BossGuid.GetCounter())
                  << ",\"boss_entry\":" << features.BossEntry
                  << ",\"boss_spell_id\":" << features.CastSpellId
                  << ",\"mechanics\":" << BuildBossMechanicsJson(features) << "}";

    std::ostringstream partySnapshot;
    partySnapshot << "{\"tank_hp_pct\":" << features.TankHpPct
                  << ",\"party_average_hp_pct\":" << features.PartyAverageHpPct
                  << ",\"lowest_ally_hp_pct\":" << features.LowestAllyHpPct
                  << ",\"healer_mana_pct\":" << features.HealerManaPct
                  << ",\"add_count\":" << features.AddCount << "}";

    std::string type = replayType ? replayType : "boss_mechanic_failure";
    std::string botJson = botSnapshot.str();
    std::string worldJson = worldSnapshot.str();
    std::string partyJson = partySnapshot.str();
    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string action = actionJson ? actionJson : "{}";
    std::string failure = failureJson ? failureJson : "{}";
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(botJson);
    CharacterDatabase.EscapeString(worldJson);
    CharacterDatabase.EscapeString(partyJson);
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(action);
    CharacterDatabase.EscapeString(failure);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_replay_records (experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, bot_snapshot_json, world_snapshot_json, party_snapshot_json, raw_state_json, semantic_state_json, chosen_action_json, failure_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %f, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), type.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), bot->GetOrientation(), botJson.c_str(), worldJson.c_str(), partyJson.c_str(), raw.c_str(), semantic.c_str(), action.c_str(), failure.c_str());
}

BotTelemetryPolicyConfig BotWorldPopulationMgr::GetTelemetryPolicyConfig() const
{
    BotTelemetryPolicyConfig config;
    config.smartSampling = _config.SmartSampling;
    config.alwaysRecordFailures = _config.AlwaysRecordFailures;
    config.alwaysRecordInterventions = _config.AlwaysRecordInterventions;
    config.alwaysRecordRareStates = _config.AlwaysRecordRareStates;
    config.normalEventSampleRate = _config.NormalEventSampleRate;
    config.normalDecisionSampleRate = _config.NormalDecisionSampleRate;
    config.minClipImportance = _config.MinClipImportance;
    config.minReplayImportance = _config.MinReplayImportance;
    return config;
}

BotTelemetryPolicyInput BotWorldPopulationMgr::BuildTelemetryPolicyInput(char const* eventType, char const* result, char const* situation, Unit const* target, uint32 spellId, uint32 questId, uint32 itemId, float valueFloat, uint32 valueInt, bool failure, bool rare, bool intervention) const
{
    BotTelemetryPolicyInput input;
    input.eventType = eventType ? eventType : "";
    input.result = result ? result : "";
    input.situation = situation ? situation : "";
    input.spellId = spellId;
    input.questId = questId;
    input.itemId = itemId;
    input.valueFloat = valueFloat;
    input.valueInt = valueInt;
    input.failure = failure;
    input.rare = rare;
    input.intervention = intervention;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        input.targetEntry = creature->GetEntry();
        if (input.eventType == "combat_started" && (creature->isElite() || creature->IsDungeonBoss() || creature->isWorldBoss()))
            input.rare = true;
    }
    return input;
}

void BotWorldPopulationMgr::RecordPolicyReplay(WorldBotState const& state, Player* bot, Unit const* target, BotTelemetryPolicyInput const& input, char const* rawJson, char const* semanticJson)
{
    if (!_runId || !bot)
        return;

    std::ostringstream botSnapshot;
    botSnapshot << "{\"guid\":" << bot->GetGUID().GetCounter()
                << ",\"level\":" << uint32(bot->getLevel())
                << ",\"class_id\":" << uint32(bot->getClass())
                << ",\"hp\":" << bot->GetHealth()
                << ",\"max_hp\":" << bot->GetMaxHealth()
                << ",\"activity\":\"" << JsonEscape(state.ActivityType) << "\"}";

    std::ostringstream worldSnapshot;
    worldSnapshot << "{\"map_id\":" << bot->GetMapId()
                  << ",\"zone_id\":" << bot->GetZoneId()
                  << ",\"area_id\":" << bot->GetAreaId()
                  << ",\"x\":" << bot->GetPositionX()
                  << ",\"y\":" << bot->GetPositionY()
                  << ",\"z\":" << bot->GetPositionZ()
                  << ",\"o\":" << bot->GetOrientation()
                  << ",\"quest_id\":" << input.questId
                  << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
                  << ",\"target_entry\":" << input.targetEntry << "}";

    std::ostringstream action;
    action << "{\"event_type\":\"" << JsonEscape(input.eventType)
           << "\",\"situation\":\"" << JsonEscape(input.situation)
           << "\",\"spell_id\":" << input.spellId
           << ",\"item_id\":" << input.itemId << "}";

    std::ostringstream failure;
    failure << "{\"result\":\"" << JsonEscape(input.result)
            << "\",\"value_float\":" << input.valueFloat
            << ",\"value_int\":" << input.valueInt << "}";

    std::string type = input.eventType.empty() ? "telemetry_replay" : input.eventType;
    if (type == "death")
        type = "bot_death";
    else if (type == "stuck_detected")
        type = "stuck_loop";
    else if (type == "objective_failed")
        type = "quest_failure";
    else if (type == "raid_wipe")
        type = "boss_mechanic_failure";

    std::string botJson = botSnapshot.str();
    std::string worldJson = worldSnapshot.str();
    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string actionJson = action.str();
    std::string failureJson = failure.str();
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(botJson);
    CharacterDatabase.EscapeString(worldJson);
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(actionJson);
    CharacterDatabase.EscapeString(failureJson);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_replay_records (experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, bot_snapshot_json, world_snapshot_json, raw_state_json, semantic_state_json, chosen_action_json, failure_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %f, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), type.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), bot->GetOrientation(), botJson.c_str(), worldJson.c_str(), raw.c_str(), semantic.c_str(), actionJson.c_str(), failureJson.c_str());
}

uint64 BotWorldPopulationMgr::RecordDecisionReplay(WorldBotState const& state, Player* bot, Unit const* target, char const* situation, char const* action, char const* rawJson, char const* semanticJson, char const* candidateJson, BotActivityScore const& chosenActivity, bool failure)
{
    if (!_runId || !bot)
        return 0;

    uint32 targetEntry = 0;
    uint64 targetGuid = 0;
    if (target)
    {
        targetGuid = target->GetGUID().GetCounter();
        if (Creature const* creature = target->ToCreature())
            targetEntry = creature->GetEntry();
    }

    std::ostringstream botSnapshot;
    botSnapshot << "{\"guid\":" << bot->GetGUID().GetCounter()
                << ",\"level\":" << uint32(bot->getLevel())
                << ",\"class_id\":" << uint32(bot->getClass())
                << ",\"hp\":" << bot->GetHealth()
                << ",\"max_hp\":" << bot->GetMaxHealth()
                << ",\"activity\":\"" << JsonEscape(state.ActivityType) << "\""
                << ",\"progression_stage\":\"" << JsonEscape(state.ProgressionStage) << "\"}";

    std::ostringstream worldSnapshot;
    worldSnapshot << "{\"map_id\":" << bot->GetMapId()
                  << ",\"zone_id\":" << bot->GetZoneId()
                  << ",\"area_id\":" << bot->GetAreaId()
                  << ",\"x\":" << bot->GetPositionX()
                  << ",\"y\":" << bot->GetPositionY()
                  << ",\"z\":" << bot->GetPositionZ()
                  << ",\"o\":" << bot->GetOrientation()
                  << ",\"target_guid\":" << targetGuid
                  << ",\"target_entry\":" << targetEntry
                  << ",\"quest_phase\":\"" << JsonEscape(state.QuestWork.Phase) << "\""
                  << ",\"active_quest_id\":" << state.QuestWork.ActiveQuestId
                  << ",\"objective_index\":" << state.QuestWork.ObjectiveIndex
                  << ",\"objective_type\":\"" << JsonEscape(state.QuestWork.ObjectiveType) << "\""
                  << ",\"required_entry\":" << (state.QuestWork.RequiredEntry > 0 ? uint32(state.QuestWork.RequiredEntry) : 0)
                  << ",\"required_item\":" << state.QuestWork.RequiredItem
                  << ",\"required_spell\":" << state.QuestWork.RequiredSpell
                  << ",\"target_matches_objective\":" << (targetEntry && (state.QuestWork.RequiredEntry <= 0 || uint32(state.QuestWork.RequiredEntry) == targetEntry) ? "true" : "false") << "}";

    std::ostringstream actionSnapshot;
    actionSnapshot << "{\"action\":\"" << JsonEscape(action ? action : "wait") << "\""
                   << ",\"situation\":\"" << JsonEscape(situation ? situation : "idle") << "\""
                   << ",\"chosen_activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(chosenActivity.Activity)) << "\""
                   << ",\"model_version\":\"" << JsonEscape(_policyModelConfig.Version) << "\""
                   << ",\"feature_schema_version\":\"" << JsonEscape(_policyModelConfig.FeatureSchemaVersion) << "\""
                   << ",\"quest_phase\":\"" << JsonEscape(state.QuestWork.Phase) << "\""
                   << ",\"active_quest_id\":" << state.QuestWork.ActiveQuestId
                   << ",\"objective_index\":" << state.QuestWork.ObjectiveIndex
                   << ",\"candidates\":" << (candidateJson && *candidateJson ? candidateJson : "[]") << "}";

    std::ostringstream failureSnapshot;
    failureSnapshot << "{\"failure\":" << (failure ? "true" : "false")
                    << ",\"activity_score\":" << chosenActivity.Score
                    << ",\"learned_score\":" << chosenActivity.LearnedScore
                    << ",\"learned_penalty\":" << chosenActivity.LearnedPenalty
                    << ",\"danger_score\":" << chosenActivity.LearnedDangerScore
                    << ",\"progression_value\":" << chosenActivity.LearnedProgressionValue
                    << ",\"confidence\":" << chosenActivity.LearnedConfidence
                    << ",\"progress_before\":" << state.QuestWork.ProgressBefore
                    << ",\"progress_after\":" << state.QuestWork.ProgressAfter
                    << ",\"loot_result\":\"" << JsonEscape(state.LastLootResult) << "\""
                    << ",\"loot_items_count\":" << state.LastLootItemsCount
                    << ",\"loot_money\":" << state.LastLootMoney
                    << ",\"loot_state_cleared\":" << (state.LastLootStateCleared ? "true" : "false")
                    << ",\"no_progress_reason\":\"" << JsonEscape(state.LastNoProgressReason) << "\""
                    << ",\"cooldown_reason\":\"" << JsonEscape(state.QuestWork.FailedReason) << "\""
                    << ",\"dummy_allowed_by_quest\":" << (state.CurrentDummyAllowedByQuest ? "true" : "false") << "}";

    std::string type = "policy_model_prediction";
    std::string botJson = botSnapshot.str();
    std::string worldJson = worldSnapshot.str();
    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string actionJson = actionSnapshot.str();
    std::string failureJson = failureSnapshot.str();
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(botJson);
    CharacterDatabase.EscapeString(worldJson);
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(actionJson);
    CharacterDatabase.EscapeString(failureJson);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_replay_records (experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, bot_snapshot_json, world_snapshot_json, raw_state_json, semantic_state_json, chosen_action_json, failure_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %f, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), type.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), bot->GetOrientation(), botJson.c_str(), worldJson.c_str(), raw.c_str(), semantic.c_str(), actionJson.c_str(), failureJson.c_str());
    return ReadLastInsertId();
}

BotTelemetryFrame BotWorldPopulationMgr::BuildTelemetryFrame(Player* bot, Unit const* target, char const* situation, char const* action, char const* rawJson, char const* semanticJson, uint32 questId) const
{
    BotTelemetryFrame frame;
    if (!bot)
        return frame;

    frame.timestamp_ms = uint64(std::chrono::duration_cast<std::chrono::milliseconds>(GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
    frame.bot_guid = bot->GetGUID();
    frame.map_id = bot->GetMapId();
    frame.zone_id = bot->GetZoneId();
    frame.area_id = bot->GetAreaId();
    frame.x = bot->GetPositionX();
    frame.y = bot->GetPositionY();
    frame.z = bot->GetPositionZ();
    frame.o = bot->GetOrientation();
    frame.level = bot->getLevel();
    frame.hp_pct = bot->GetMaxHealth() ? float(bot->GetHealth()) / float(bot->GetMaxHealth()) : 1.0f;
    frame.power_pct = bot->GetMaxPower(bot->GetPowerType()) ? float(bot->GetPower(bot->GetPowerType())) / float(bot->GetMaxPower(bot->GetPowerType())) : 1.0f;
    frame.in_combat = bot->IsInCombat();
    if (target)
    {
        frame.target_guid = target->GetGUID();
        if (Creature const* creature = target->ToCreature())
            frame.target_entry = creature->GetEntry();
    }
    frame.quest_id = questId;
    frame.situation_type = situation ? situation : "";
    frame.action = action ? action : "";
    frame.raw_json = rawJson ? rawJson : "{}";
    frame.semantic_json = semanticJson ? semanticJson : "{}";
    return frame;
}

uint64 BotWorldPopulationMgr::MaybeCaptureTelemetryClip(Player* bot, Unit const* target, BotTelemetryPolicyInput const& input, BotTelemetryPolicyDecision const& decision, char const* rawJson, char const* semanticJson)
{
    if (!_telemetryBuffer.IsEnabled() || !decision.openClip)
        return 0;

    BotTelemetryFrame frame = BuildTelemetryFrame(bot, target, input.eventType.c_str(), input.result.c_str(), rawJson, semanticJson, input.questId);
    if (frame.bot_guid.IsEmpty())
        return 0;

    std::ostringstream summary;
    summary << "{\"event_type\":\"" << JsonEscape(input.eventType.empty() ? "unknown" : input.eventType) << "\""
            << ",\"result\":\"" << JsonEscape(input.result) << "\""
            << ",\"reason\":\"" << JsonEscape(decision.reason) << "\""
            << ",\"quest_id\":" << input.questId
            << ",\"item_id\":" << input.itemId
            << ",\"target_entry\":" << input.targetEntry
            << ",\"value_float\":" << input.valueFloat
            << ",\"value_int\":" << input.valueInt << "}";

    return _telemetryBuffer.CaptureEvent(_experimentId, _runId, _config.BrainVersion, frame, input.eventType.empty() ? "unknown" : input.eventType.c_str(), decision.score, decision.reason.c_str(), summary.str());
}

void BotWorldPopulationMgr::RecordEvent(WorldBotState& state, Player* bot, char const* eventType, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, float valueFloat, uint32 valueInt, uint32 spellId)
{
    if (!bot)
        return;

    RecordExperimentSegmentEvent(bot, eventType, result, 0, target, _telemetryBuffer.GetActiveClipId(bot->GetGUID()), rawJson, semanticJson);

    if (!_runId)
        return;

    std::string eventName = eventType ? eventType : "unknown";
    bool rareCombatStart = eventName == "combat_started" && target && target->getLevel() > bot->getLevel() + 3;
    bool recoveryRare = eventName == "repeated_death" || eventName == "death_recovery_failed";
    bool recoveryIntervention = eventName == "teleport_fallback_used";
    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(eventName.c_str(), result ? result : "", nullptr, target, spellId, 0, 0, valueFloat, valueInt, EventLooksFailure(eventType, result), rareCombatStart || recoveryRare, recoveryIntervention);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), ++state.EventSequence);
    if (!policy.writeEvent)
        return;

    uint64 clipId = MaybeCaptureTelemetryClip(bot, target, policyInput, policy, rawJson, semanticJson);
    if (!clipId)
        clipId = _telemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";

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

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, target_guid, target_entry, spell_id, result, value_float, value_int, raw_json, semantic_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', " UI64FMTD ", %u, %u, '%s', %f, %u, '%s', '%s')",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), targetGuid, targetEntry, spellId, res.c_str(), valueFloat, valueInt, raw.c_str(), semantic.c_str());

    UpdateSemanticStatsFromEvent(bot, target, eventType, result, valueFloat, valueInt, spellId, semanticJson);
    if (eventName == "resurrected" || eventName == "death_recovery_failed" || eventName == "teleport_fallback_used")
    {
        std::string mode = result && *result ? result : _config.DeathRecoveryMode;
        std::string features = BuildEmbeddingFeaturesJson(bot, target, "recovery", BotExperienceLearningPolicy::StableKey(mode), mode.c_str());
        UpdateSemanticOutcomeStats(bot, "recovery", BotExperienceLearningPolicy::StableKey(mode), eventType, result, valueFloat, 0.0f, EventLooksFailure(eventType, result), features.c_str());
    }
    if (policy.writeReplay)
        RecordPolicyReplay(state, bot, target, policyInput, rawJson, semanticJson);
}

void BotWorldPopulationMgr::RecordDecision(WorldBotState& state, Player* bot, char const* situation, char const* action, Unit const* target, char const* rawJson, char const* semanticJson, std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, BotRolePowerBreakdown const& power, bool failure, bool rare)
{
    if (!_runId || !_config.RecordDecisions || !bot)
        return;

    ++state.Sequence;
    ++_metrics.Decisions;
    if (failure)
        ++_metrics.Failures;

    _telemetryBuffer.Observe(bot, situation, action, rawJson, semanticJson);

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput("decision", failure ? "failed" : "ok", situation ? situation : "idle", target, 0, 0, 0, failure ? -1.0f : chosenActivity.Score, 0, failure, rare, action && std::string(action) == "unstuck");
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideDecision(policyInput, GetTelemetryPolicyConfig(), state.Sequence);
    if (!policy.writeDecision)
        return;

    uint64 clipId = MaybeCaptureTelemetryClip(bot, target, policyInput, policy, rawJson, semanticJson);
    if (!clipId)
        clipId = _telemetryBuffer.GetActiveClipId(bot->GetGUID());

    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string candidateJson = BuildActivityCandidatesJson(activityScores);
    uint64 replayId = _policyModelConfig.Enabled && !_policyModelConfig.Version.empty()
        ? RecordDecisionReplay(state, bot, target, situation, action, rawJson, semanticJson, candidateJson.c_str(), chosenActivity, failure)
        : 0;
    PolicyModelTrace modelTrace = BuildPolicyModelTrace(activityScores, chosenActivity, bot, clipId, replayId);
    std::ostringstream chosen;
    chosen << "{\"action\":\"" << JsonEscape(action ? action : "wait") << "\"";
    if (target)
        chosen << ",\"target_guid\":" << target->GetGUID().GetCounter();
    chosen << ",\"activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(chosenActivity.Activity)) << "\""
           << ",\"activity_score\":" << chosenActivity.Score
           << ",\"expected_power_gain\":" << chosenActivity.ExpectedPowerGain
           << ",\"learned_score\":" << chosenActivity.LearnedScore
           << ",\"learned_penalty\":" << chosenActivity.LearnedPenalty
           << ",\"learned_reason\":\"" << JsonEscape(chosenActivity.LearnedReason) << "\""
           << ",\"sample_count\":" << chosenActivity.LearnedSampleCount
           << ",\"danger_score\":" << chosenActivity.LearnedDangerScore
           << ",\"progression_value\":" << chosenActivity.LearnedProgressionValue
           << ",\"confidence\":" << chosenActivity.LearnedConfidence
           << ",\"quest_phase\":\"" << JsonEscape(state.QuestWork.Phase) << "\""
           << ",\"active_quest_id\":" << state.QuestWork.ActiveQuestId
           << ",\"objective_index\":" << state.QuestWork.ObjectiveIndex
           << ",\"objective_type\":\"" << JsonEscape(state.QuestWork.ObjectiveType) << "\""
           << ",\"required_entry\":" << (state.QuestWork.RequiredEntry > 0 ? uint32(state.QuestWork.RequiredEntry) : 0)
           << ",\"required_item\":" << state.QuestWork.RequiredItem
           << ",\"required_spell\":" << state.QuestWork.RequiredSpell;
    if (_policyModelConfig.Enabled && !_policyModelConfig.Version.empty())
        chosen << ",\"policy_model\":" << modelTrace.Json;
    chosen << "}";
    std::ostringstream outcome;
    outcome << "{\"main_goal\":\"increase_character_power\""
            << ",\"current_stage\":\"" << JsonEscape(state.ProgressionStage) << "\""
            << ",\"chosen_activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(chosenActivity.Activity)) << "\""
            << ",\"expected_value\":" << chosenActivity.Score
            << ",\"learned_score\":" << chosenActivity.LearnedScore
            << ",\"learned_penalty\":" << chosenActivity.LearnedPenalty
            << ",\"learned_reason\":\"" << JsonEscape(chosenActivity.LearnedReason) << "\""
            << ",\"sample_count\":" << chosenActivity.LearnedSampleCount
            << ",\"danger_score\":" << chosenActivity.LearnedDangerScore
            << ",\"progression_value\":" << chosenActivity.LearnedProgressionValue
            << ",\"confidence\":" << chosenActivity.LearnedConfidence
            << ",\"role_power_score\":" << power.Total
            << ",\"power_delta\":" << (power.Total - state.ActivityStartPower)
            << ",\"progress_before\":" << state.QuestWork.ProgressBefore
            << ",\"progress_after\":" << state.QuestWork.ProgressAfter
            << ",\"loot_result\":\"" << JsonEscape(state.LastLootResult) << "\""
            << ",\"loot_items_count\":" << state.LastLootItemsCount
            << ",\"loot_money\":" << state.LastLootMoney
            << ",\"loot_state_cleared\":" << (state.LastLootStateCleared ? "true" : "false")
            << ",\"no_progress_reason\":\"" << JsonEscape(state.LastNoProgressReason) << "\""
            << ",\"cooldown_reason\":\"" << JsonEscape(state.QuestWork.FailedReason) << "\""
            << ",\"dummy_allowed_by_quest\":" << (state.CurrentDummyAllowedByQuest ? "true" : "false");
    if (_policyModelConfig.Enabled && !_policyModelConfig.Version.empty())
        outcome << ",\"policy_model\":" << modelTrace.Json;
    outcome << "}";

    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    std::string chosenJson = chosen.str();
    std::string outcomeJson = outcome.str();
    std::string brain = _config.BrainVersion;
    CharacterDatabase.EscapeString(candidateJson);
    CharacterDatabase.EscapeString(chosenJson);
    CharacterDatabase.EscapeString(outcomeJson);
    CharacterDatabase.EscapeString(brain);
    std::string modelVersion = _policyModelConfig.Enabled && !_policyModelConfig.Version.empty() ? _policyModelConfig.Version : "";
    std::string featureSchemaVersion = modelTrace.Enabled ? _policyModelConfig.FeatureSchemaVersion : "";
    CharacterDatabase.EscapeString(modelVersion);
    CharacterDatabase.EscapeString(featureSchemaVersion);
    std::string sit = situation ? situation : "idle";
    CharacterDatabase.EscapeString(sit);
    std::string currentActivity = BotLongTermProgressionBrain::ToString(chosenActivity.Activity);
    CharacterDatabase.EscapeString(currentActivity);
    std::string modelVersionSql = modelVersion.empty() ? "NULL" : ("'" + modelVersion + "'");
    std::string featureSchemaSql = featureSchemaVersion.empty() ? "NULL" : ("'" + featureSchemaVersion + "'");
    std::string modelScoreSql = modelTrace.Enabled ? std::to_string(modelTrace.ModelScore) : "NULL";
    std::string modelRankSql = modelTrace.Enabled ? std::to_string(modelTrace.ModelRank) : "NULL";
    std::string modelFeaturesHashSql = modelTrace.Enabled ? std::to_string(modelTrace.FeaturesHash) : "NULL";
    std::string replaySql = replayId ? std::to_string(replayId) : "NULL";

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_decisions (experiment_id, run_id, bot_guid, brain_version, model_version, feature_schema_version, model_score, model_rank, model_features_hash, clip_id, situation_type, current_activity, current_goal, map_id, zone_id, area_id, x, y, z, raw_state_json, semantic_state_json, candidate_actions_json, chosen_action_json, outcome_json, reward, is_failure, is_rare_state, replay_key) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %s, %s, %s, %s, %s, '%s', '%s', 'increase_character_power', %u, %u, %u, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', %f, %u, %u, %s)",
        _experimentId, _runId, state.Guid.GetCounter(), brain.c_str(), modelVersionSql.c_str(), featureSchemaSql.c_str(), modelScoreSql.c_str(), modelRankSql.c_str(), modelFeaturesHashSql.c_str(), clipSql.c_str(), sit.c_str(), currentActivity.c_str(), bot->GetMapId(), bot->GetZoneId(),
        bot->GetAreaId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), raw.c_str(), semantic.c_str(), candidateJson.c_str(), chosenJson.c_str(),
        outcomeJson.c_str(), failure ? -1.0f : chosenActivity.Score, failure ? 1 : 0, rare ? 1 : 0, replaySql.c_str());

    std::string areaFeatures = BuildEmbeddingFeaturesJson(bot, target, "area", bot->GetAreaId(), situation ? situation : "decision");
    UpdateSemanticOutcomeStats(bot, "area", bot->GetAreaId(), situation, failure ? "failed" : "sampled", failure ? -1.0f : chosenActivity.Score, power.Total - state.ActivityStartPower, failure, areaFeatures.c_str());
}

void BotWorldPopulationMgr::UpdateSemanticOutcomeStats(Player* bot, char const* entityType, uint32 entityKey, char const* eventType, char const* result, float reward, float powerDelta, bool failure, char const* featuresJson)
{
    if (!_runId || !_config.UpdateSemanticOutcomeStats || !bot || !entityType || !entityKey)
        return;

    bool failed = failure || EventLooksFailure(eventType, result);
    bool death = eventType && std::string(eventType) == "death";
    bool success = !failed && EventLooksSuccessful(eventType, result);

    std::string type = entityType;
    std::string event = eventType ? eventType : "";
    std::string res = result ? result : "";
    std::string features = featuresJson ? featuresJson : "{}";
    std::ostringstream embedding;
    embedding << "{\"entity_type\":\"" << JsonEscape(type)
              << "\",\"entity_key\":" << entityKey
              << ",\"feature_schema\":\"bot_semantic_phase6_v1\""
              << ",\"features\":" << features << "}";
    std::string embeddingJson = embedding.str();
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(res);
    CharacterDatabase.EscapeString(features);
    CharacterDatabase.EscapeString(embeddingJson);

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_semantic_outcome_stats "
        "(entity_type, entity_key, samples, successes, failures, deaths, total_reward, total_power_delta, avg_reward, avg_power_delta, danger_score, progression_value, last_experiment_id, last_run_id, last_event_type, last_result, features_json, embedding_json, updated_at) "
        "VALUES ('%s', %u, 1, %u, %u, %u, %f, %f, %f, %f, %f, %f, " UI64FMTD ", " UI64FMTD ", '%s', '%s', '%s', '%s', NOW()) "
        "ON DUPLICATE KEY UPDATE "
        "danger_score = LEAST(1.0, (failures + VALUES(failures) + ((deaths + VALUES(deaths)) * 2.0)) / GREATEST(1, samples + VALUES(samples))), "
        "progression_value = GREATEST(0.0, (total_power_delta + VALUES(total_power_delta)) / GREATEST(1, samples + VALUES(samples))) + GREATEST(0.0, (total_reward + VALUES(total_reward)) / GREATEST(1, samples + VALUES(samples))), "
        "avg_reward = (total_reward + VALUES(total_reward)) / GREATEST(1, samples + VALUES(samples)), "
        "avg_power_delta = (total_power_delta + VALUES(total_power_delta)) / GREATEST(1, samples + VALUES(samples)), "
        "samples = samples + VALUES(samples), successes = successes + VALUES(successes), failures = failures + VALUES(failures), deaths = deaths + VALUES(deaths), "
        "total_reward = total_reward + VALUES(total_reward), total_power_delta = total_power_delta + VALUES(total_power_delta), "
        "last_experiment_id = VALUES(last_experiment_id), last_run_id = VALUES(last_run_id), last_event_type = VALUES(last_event_type), last_result = VALUES(last_result), "
        "features_json = VALUES(features_json), embedding_json = VALUES(embedding_json), updated_at = NOW()",
        type.c_str(), entityKey, success ? 1 : 0, failed ? 1 : 0, death ? 1 : 0, reward, powerDelta, reward, powerDelta,
        failed ? 1.0f : 0.0f, std::max(0.0f, reward) + std::max(0.0f, powerDelta), _experimentId, _runId, event.c_str(), res.c_str(), features.c_str(), embeddingJson.c_str());
}

void BotWorldPopulationMgr::UpdateSemanticStatsFromEvent(Player* bot, Unit const* target, char const* eventType, char const* result, float valueFloat, uint32 valueInt, uint32 spellId, char const* /*semanticJson*/)
{
    if (!_config.UpdateSemanticOutcomeStats || !bot)
        return;

    bool failed = EventLooksFailure(eventType, result);
    std::string areaFeatures = BuildEmbeddingFeaturesJson(bot, target, "area", bot->GetAreaId(), eventType ? eventType : "event");
    UpdateSemanticOutcomeStats(bot, "area", bot->GetAreaId(), eventType, result, valueFloat, 0.0f, failed, areaFeatures.c_str());

    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        std::string mobFeatures = BuildEmbeddingFeaturesJson(bot, target, "mob", creature->GetEntry(), eventType ? eventType : "event");
        UpdateSemanticOutcomeStats(bot, "mob", creature->GetEntry(), eventType, result, valueFloat, 0.0f, failed, mobFeatures.c_str());
    }

    if (spellId)
    {
        std::string spellFeatures = BuildEmbeddingFeaturesJson(bot, target, "spell", spellId, eventType ? eventType : "spell");
        UpdateSemanticOutcomeStats(bot, "spell", spellId, eventType, result, valueFloat, 0.0f, failed, spellFeatures.c_str());
    }

    uint32 mechanicKey = SemanticMechanicKey(eventType, result);
    if (mechanicKey)
    {
        std::string mechanicFeatures = BuildEmbeddingFeaturesJson(bot, target, "mechanic", mechanicKey, SemanticMechanicFamily(mechanicKey));
        UpdateSemanticOutcomeStats(bot, "mechanic", mechanicKey, eventType, result, valueFloat, 0.0f, failed, mechanicFeatures.c_str());
    }

    if ((eventType && (std::string(eventType) == "gear_upgrade" || std::string(eventType) == "gear_evaluated")) && valueInt)
    {
        std::string itemFeatures = BuildEmbeddingFeaturesJson(bot, target, "item", valueInt, eventType);
        UpdateSemanticOutcomeStats(bot, "item", valueInt, eventType, result, valueFloat, valueFloat, failed, itemFeatures.c_str());
    }
}

BotWorldPopulationMgr::SemanticOutcomeStats BotWorldPopulationMgr::GetSemanticOutcomeStats(char const* entityType, uint32 entityKey) const
{
    SemanticOutcomeStats stats;
    if (!sConfigMgr->GetBoolDefault("BotSemantic.Enable", true) || !entityType || !entityKey)
        return stats;

    std::string type = entityType;
    CharacterDatabase.EscapeString(type);
    if (QueryResult result = CharacterDatabase.PQuery("SELECT samples, successes, failures, deaths, avg_reward, avg_power_delta, danger_score, progression_value FROM bot_semantic_outcome_stats WHERE entity_type = '%s' AND entity_key = %u", type.c_str(), entityKey))
    {
        Field* fields = result->Fetch();
        stats.Known = true;
        stats.Samples = fields[0].GetUInt32();
        stats.Successes = fields[1].GetUInt32();
        stats.Failures = fields[2].GetUInt32();
        stats.Deaths = fields[3].GetUInt32();
        stats.AvgReward = fields[4].GetFloat();
        stats.AvgPowerDelta = fields[5].GetFloat();
        stats.DangerScore = fields[6].GetFloat();
        stats.ProgressionValue = fields[7].GetFloat();
    }
    return stats;
}

std::string BotWorldPopulationMgr::BuildOutcomeStatsJson(SemanticOutcomeStats const& stats) const
{
    std::ostringstream json;
    json << "{\"known\":" << (stats.Known ? "true" : "false")
         << ",\"samples\":" << stats.Samples
         << ",\"successes\":" << stats.Successes
         << ",\"failures\":" << stats.Failures
         << ",\"deaths\":" << stats.Deaths
         << ",\"avg_reward\":" << stats.AvgReward
         << ",\"avg_power_delta\":" << stats.AvgPowerDelta
         << ",\"danger_score\":" << stats.DangerScore
         << ",\"progression_value\":" << stats.ProgressionValue << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildEmbeddingFeaturesJson(Player const* bot, Unit const* target, char const* entityType, uint32 entityKey, char const* semanticFamily) const
{
    uint32 targetEntry = 0;
    bool elite = false;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        targetEntry = creature->GetEntry();
        elite = creature->isElite();
    }

    std::ostringstream json;
    json << "{\"entity_type\":\"" << JsonEscape(entityType ? entityType : "unknown")
         << "\",\"entity_key\":" << entityKey
         << ",\"semantic_family\":\"" << JsonEscape(semanticFamily ? semanticFamily : "unknown") << "\""
         << ",\"map_id\":" << (bot ? bot->GetMapId() : 0)
         << ",\"zone_id\":" << (bot ? bot->GetZoneId() : 0)
         << ",\"area_id\":" << (bot ? bot->GetAreaId() : 0)
         << ",\"bot_level\":" << (bot ? uint32(bot->getLevel()) : 0)
         << ",\"bot_class\":" << (bot ? uint32(bot->getClass()) : 0)
         << ",\"target_entry\":" << targetEntry
         << ",\"target_level\":" << (target ? uint32(target->getLevel()) : 0)
         << ",\"target_elite\":" << (elite ? "true" : "false")
         << ",\"feature_schema\":\"bot_semantic_phase6_v1\"}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildRawJson(Player* bot, Unit const* target) const
{
    WorldBotState const* state = nullptr;
    for (WorldBotState const& candidate : _bots)
        if (bot && candidate.Guid == bot->GetGUID())
        {
            state = &candidate;
            break;
        }

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
         << ",\"target_alive\":" << (target && target->IsAlive() ? "true" : "false")
         << ",\"target_cast_spell_id\":";
    if (target)
    {
        if (Spell* spell = target->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            json << (spell->GetSpellInfo() ? spell->GetSpellInfo()->Id : 0);
        else
            json << 0;
    }
    else
        json << 0;
    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();
    bool targetMatchesObjective = state && targetEntry && (state->QuestWork.RequiredEntry <= 0 || uint32(state->QuestWork.RequiredEntry) == targetEntry);
    bool dummyAllowed = false;
    if (state && target)
    {
        QuestObjectivePlan plan;
        dummyAllowed = GetQuestObjectivePlan(bot, state->QuestWork.ActiveQuestId, state->QuestWork.ObjectiveIndex,
            state->QuestWork.ObjectiveType == "use_ability_on_dummy" ? QuestObjectiveType::UseAbilityOnDummy :
            (state->QuestWork.ObjectiveType == "cast_spell_on_target" ? QuestObjectiveType::CastSpellOnTarget : QuestObjectiveType::Kill), plan)
            && IsTrainingDummyAllowedForQuest(plan, target);
    }
    json << ",\"quest_phase\":\"" << JsonEscape(state ? state->QuestWork.Phase : "idle") << "\""
         << ",\"active_quest_id\":" << (state ? state->QuestWork.ActiveQuestId : 0)
         << ",\"objective_index\":" << (state ? state->QuestWork.ObjectiveIndex : 0)
         << ",\"objective_type\":\"" << JsonEscape(state ? state->QuestWork.ObjectiveType : "none") << "\""
         << ",\"required_entry\":" << (state && state->QuestWork.RequiredEntry > 0 ? uint32(state->QuestWork.RequiredEntry) : 0)
         << ",\"required_item\":" << (state ? state->QuestWork.RequiredItem : 0)
         << ",\"required_spell\":" << (state ? state->QuestWork.RequiredSpell : 0)
         << ",\"target_matches_objective\":" << (targetMatchesObjective ? "true" : "false")
         << ",\"progress_before\":" << (state ? state->QuestWork.ProgressBefore : 0)
         << ",\"progress_after\":" << (state ? state->QuestWork.ProgressAfter : 0)
         << ",\"loot_result\":\"" << JsonEscape(state ? state->LastLootResult : "none") << "\""
         << ",\"loot_items_count\":" << (state ? state->LastLootItemsCount : 0)
         << ",\"loot_money\":" << (state ? state->LastLootMoney : 0)
         << ",\"loot_state_cleared\":" << (state && state->LastLootStateCleared ? "true" : "false")
         << ",\"no_progress_reason\":\"" << JsonEscape(state ? state->LastNoProgressReason : "") << "\""
         << ",\"cooldown_reason\":\"" << JsonEscape(state ? state->QuestWork.FailedReason : "") << "\""
         << ",\"dummy_allowed_by_quest\":" << (dummyAllowed ? "true" : "false")
         << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildSemanticJson(Player* bot, Unit const* target, char const* situation, BotRolePowerBreakdown const* power, BotProgressionStage stage, BotProgressionActivity activity) const
{
    float hpPct = 1.0f;
    if (bot && bot->GetMaxHealth())
        hpPct = float(bot->GetHealth()) / float(bot->GetMaxHealth());

    std::string situationType = situation ? situation : "idle";
    bool dungeonTrash = bot && bot->GetMap() && bot->GetMap()->IsNonRaidDungeon() && situationType == "dungeon_trash";
    bool bossEncounter = bot && bot->GetMap() && (situationType == "dungeon_boss" || situationType == "raid_boss");
    bool raidEncounter = bossEncounter && bot && bot->GetMap() && bot->GetMap()->IsRaid();
    bool elite = false;
    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        elite = creature->isElite();
        targetEntry = creature->GetEntry();
    }
    uint32 targetCastSpellId = 0;
    if (target)
        if (Spell* spell = const_cast<Unit*>(target)->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            targetCastSpellId = spell->GetSpellInfo() ? spell->GetSpellInfo()->Id : 0;

    BotRolePowerBreakdown localPower;
    if (!power && bot)
    {
        localPower = BotLongTermProgressionBrain::CalculateRolePower(bot);
        power = &localPower;
        stage = BotLongTermProgressionBrain::ClassifyStage(bot, *power);
    }

    std::ostringstream json;
    SemanticOutcomeStats areaStats = GetSemanticOutcomeStats("area", bot ? bot->GetAreaId() : 0);
    SemanticOutcomeStats mobStats = GetSemanticOutcomeStats("mob", targetEntry);
    SemanticOutcomeStats spellStats = GetSemanticOutcomeStats("spell", targetCastSpellId);
    BotLearnedScore activityLearned = bot ? BotExperienceLearningPolicy::ScoreActivity(bot, activity, _learningConfig) : BotLearnedScore();
    BotLearnedScore areaLearned = bot ? BotExperienceLearningPolicy::ScoreArea(bot, bot->GetAreaId(), _learningConfig) : BotLearnedScore();
    BotLearnedScore mobLearned = (bot && target) ? BotExperienceLearningPolicy::ScoreMob(bot, target, _learningConfig) : BotLearnedScore();
    WorldBotState const* workState = nullptr;
    for (WorldBotState const& state : _bots)
        if (bot && state.Guid == bot->GetGUID())
        {
            workState = &state;
            break;
        }
    bool targetMatchesObjective = workState && targetEntry && (workState->QuestWork.RequiredEntry <= 0 || uint32(workState->QuestWork.RequiredEntry) == targetEntry);

    json << "{\"situation_type\":\"" << JsonEscape(situationType) << "\""
         << ",\"role\":\"" << JsonEscape((dungeonTrash || bossEncounter) ? GetDungeonRole(bot) : "solo") << "\""
         << ",\"activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(activity)) << "\""
         << ",\"embedding_features\":{\"schema\":\"bot_semantic_phase6_v1\""
         << ",\"area\":" << BuildEmbeddingFeaturesJson(bot, target, "area", bot ? bot->GetAreaId() : 0, situationType.c_str())
         << ",\"mob\":" << BuildEmbeddingFeaturesJson(bot, target, "mob", targetEntry, situationType.c_str())
         << ",\"spell\":" << BuildEmbeddingFeaturesJson(bot, target, "spell", targetCastSpellId, situationType.c_str()) << "}"
         << ",\"learned_outcomes\":{\"area\":" << BuildOutcomeStatsJson(areaStats)
         << ",\"mob\":" << BuildOutcomeStatsJson(mobStats)
         << ",\"spell\":" << BuildOutcomeStatsJson(spellStats);
    uint32 learnedMechanicKey = 0;
    if (bossEncounter)
        learnedMechanicKey = 11;
    else if (dungeonTrash)
        learnedMechanicKey = 10;
    SemanticOutcomeStats mechanicStats = GetSemanticOutcomeStats("mechanic", learnedMechanicKey);
    json << ",\"mechanic\":" << BuildOutcomeStatsJson(mechanicStats) << "}"
         << ",\"learned_policy\":{\"activity\":" << BotExperienceLearningPolicy::ToJson(activityLearned)
         << ",\"area\":" << BotExperienceLearningPolicy::ToJson(areaLearned)
         << ",\"mob\":" << BotExperienceLearningPolicy::ToJson(mobLearned) << "}"
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
         << ",\"safe_open_world_target\":" << (target && !elite && bot && int32(target->getLevel()) <= int32(bot->getLevel()) + 1 ? "true" : "false") << "}";
    json << ",\"quest_work\":{\"quest_phase\":\"" << JsonEscape(workState ? workState->QuestWork.Phase : "idle") << "\""
         << ",\"active_quest_id\":" << (workState ? workState->QuestWork.ActiveQuestId : 0)
         << ",\"objective_index\":" << (workState ? workState->QuestWork.ObjectiveIndex : 0)
         << ",\"objective_type\":\"" << JsonEscape(workState ? workState->QuestWork.ObjectiveType : "none") << "\""
         << ",\"required_entry\":" << (workState && workState->QuestWork.RequiredEntry > 0 ? uint32(workState->QuestWork.RequiredEntry) : 0)
         << ",\"required_item\":" << (workState ? workState->QuestWork.RequiredItem : 0)
         << ",\"required_spell\":" << (workState ? workState->QuestWork.RequiredSpell : 0)
         << ",\"target_entry\":" << targetEntry
         << ",\"target_matches_objective\":" << (targetMatchesObjective ? "true" : "false")
         << ",\"progress_before\":" << (workState ? workState->QuestWork.ProgressBefore : 0)
         << ",\"progress_after\":" << (workState ? workState->QuestWork.ProgressAfter : 0)
         << ",\"loot_result\":\"" << JsonEscape(workState ? workState->LastLootResult : "none") << "\""
         << ",\"loot_items_count\":" << (workState ? workState->LastLootItemsCount : 0)
         << ",\"loot_money\":" << (workState ? workState->LastLootMoney : 0)
         << ",\"loot_state_cleared\":" << (workState && workState->LastLootStateCleared ? "true" : "false")
         << ",\"no_progress_reason\":\"" << JsonEscape(workState ? workState->LastNoProgressReason : "") << "\""
         << ",\"cooldown_reason\":\"" << JsonEscape(workState ? workState->QuestWork.FailedReason : "") << "\""
         << ",\"dummy_allowed_by_quest\":" << (workState && workState->CurrentDummyAllowedByQuest ? "true" : "false") << "}";
    if (dungeonTrash)
    {
        DungeonTrashPackFeatures pack = BuildDungeonTrashPackFeatures(bot, target);
        json << ",\"trash_pack\":" << BuildDungeonTrashPackJson(pack)
             << ",\"trash_learned_stats\":" << BuildOutcomeStatsJson(GetSemanticOutcomeStats("mechanic", 10))
             << ",\"trash_action_scores\":{\"interrupt\":" << pack.InterruptPriority
             << ",\"cc\":" << pack.CcValue
             << ",\"aoe\":" << pack.AoeValue
             << ",\"single_target\":" << (target ? 1.0f : 0.0f)
             << ",\"avoid_pull\":" << pack.PullRisk << "}";
    }
    else
        json << ",\"trash_pack\":null,\"trash_action_scores\":null";
    if (bossEncounter)
    {
        BossMechanicFeatures features = BuildBossMechanicFeatures(bot, target);
        uint32 mechanicKey = features.MoveOut ? 1 : (features.MustInterrupt ? 2 : (features.AddsActive ? 5 : (features.RaidDamage ? 4 : 11)));
        json << ",\"boss_mechanics\":" << BuildBossMechanicsJson(features)
             << ",\"boss_learned_stats\":{\"mechanic\":" << BuildOutcomeStatsJson(GetSemanticOutcomeStats("mechanic", mechanicKey))
             << ",\"boss\":" << BuildOutcomeStatsJson(GetSemanticOutcomeStats("mob", features.BossEntry))
             << ",\"cast_spell\":" << BuildOutcomeStatsJson(GetSemanticOutcomeStats("spell", features.CastSpellId)) << "}"
             << ",\"boss_action_scores\":{\"move_out\":" << (features.MoveOut ? features.DangerScore : 0.0f)
             << ",\"interrupt\":" << features.InterruptPriority
             << ",\"switch_adds\":" << (features.AddsActive ? std::min(1.0f, float(features.AddCount) / 4.0f) : 0.0f)
             << ",\"heal_raid\":" << (features.RaidDamage ? std::max(0.0f, 1.0f - features.LowestAllyHpPct) : 0.0f)
             << ",\"single_target\":" << (target ? 1.0f : 0.0f) << "}";
        if (raidEncounter)
        {
            RaidRoleAssignment assignment = BuildRaidRoleAssignment(bot);
            RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(bot, target, assignment, features);
            RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(bot, target, assignment, features);
            RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(bot, power ? *power : localPower, stage);
            WorldBotState const* botState = nullptr;
            for (WorldBotState const& state : _bots)
                if (bot && state.Guid == bot->GetGUID())
                {
                    botState = &state;
                    break;
                }
            WorldBotState emptyState;
            HeroicRaidProgression progression = BuildHeroicRaidProgression(botState ? *botState : emptyState, bot, power ? *power : localPower, stage);
            json << ",\"raid_role_assignment\":" << BuildRaidRoleAssignmentJson(assignment)
                 << ",\"raid_positioning_anchors\":" << BuildRaidPositioningAnchorsJson(anchors)
                 << ",\"raid_mechanic_adapter\":" << BuildRaidMechanicAdapterJson(adapter)
                 << ",\"raid_gear_target_plan\":" << BuildRaidGearTargetPlanJson(gearPlan)
                 << ",\"heroic_raid_progression\":" << BuildHeroicRaidProgressionJson(progression);
        }
    }
    else
        json << ",\"boss_mechanics\":null,\"boss_action_scores\":null";
    if (!raidEncounter)
        json << ",\"raid_role_assignment\":null,\"raid_positioning_anchors\":null,\"raid_mechanic_adapter\":null,\"raid_gear_target_plan\":null,\"heroic_raid_progression\":null";
    json
         << ",\"objective\":{\"main_goal\":\"increase_character_power\",\"questing_allowed\":" << (_config.AllowQuesting ? "true" : "false")
         << ",\"dungeons_allowed\":" << (_config.AllowDungeons ? "true" : "false")
         << ",\"raids_allowed\":" << (_config.AllowRaids ? "true" : "false") << "}}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildConfigJson() const
{
    BotTelemetryBufferConfig const& telemetry = _telemetryBuffer.GetConfig();
    std::ostringstream json;
    json << "{\"name\":\"" << JsonEscape(_config.Name)
         << "\",\"type\":\"bot_world_autonomy\""
         << ",\"runtime_mode\":\"" << (_runtimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy ? "always_on_autonomy" : "manual_experiment") << "\""
         << ",\"population\":" << _config.TargetPopulation
         << ",\"map\":" << _config.MapId
         << ",\"zone\":" << _config.ZoneId
         << ",\"min_level\":" << uint32(_config.MinLevel)
         << ",\"max_level\":" << uint32(_config.MaxLevel)
         << ",\"allow_combat\":" << (_config.AllowCombat ? "true" : "false")
         << ",\"allow_grinding\":" << (_config.AllowGrinding ? "true" : "false")
         << ",\"quest_first\":" << (_config.QuestFirst ? "true" : "false")
         << ",\"grind_only_when_no_quest_available\":" << (_config.GrindOnlyWhenNoQuestAvailable ? "true" : "false")
         << ",\"progression_enabled\":" << (_config.EnableProgression ? "true" : "false")
         << ",\"allow_questing\":" << (_config.AllowQuesting ? "true" : "false")
         << ",\"allow_dungeons\":" << (_config.AllowDungeons ? "true" : "false")
         << ",\"allow_raids\":" << (_config.AllowRaids ? "true" : "false")
         << ",\"track_heroic_raid_progression\":" << (_config.TrackHeroicRaidProgression ? "true" : "false")
         << ",\"record_decisions\":" << (_config.RecordDecisions ? "true" : "false")
         << ",\"record_perception\":" << (_config.RecordPerception ? "true" : "false")
         << ",\"smart_sampling\":" << (_config.SmartSampling ? "true" : "false")
         << ",\"always_record_failures\":" << (_config.AlwaysRecordFailures ? "true" : "false")
         << ",\"always_record_interventions\":" << (_config.AlwaysRecordInterventions ? "true" : "false")
         << ",\"always_record_rare_states\":" << (_config.AlwaysRecordRareStates ? "true" : "false")
         << ",\"normal_event_sample_rate\":" << _config.NormalEventSampleRate
         << ",\"normal_decision_sample_rate\":" << _config.NormalDecisionSampleRate
         << ",\"min_clip_importance\":" << _config.MinClipImportance
         << ",\"min_replay_importance\":" << _config.MinReplayImportance
         << ",\"update_semantic_outcome_stats\":" << (_config.UpdateSemanticOutcomeStats ? "true" : "false")
         << ",\"telemetry_enabled\":" << (telemetry.Enabled ? "true" : "false")
         << ",\"telemetry_frame_interval_ms\":" << telemetry.FrameIntervalMs
         << ",\"telemetry_pre_event_window_sec\":" << telemetry.PreEventWindowSec
         << ",\"telemetry_post_event_window_sec\":" << telemetry.PostEventWindowSec
         << ",\"telemetry_max_frames_per_bot\":" << telemetry.MaxFramesPerBot
         << ",\"telemetry_max_open_clips_per_bot\":" << telemetry.MaxOpenClipsPerBot
         << ",\"spawn_mode\":\"" << JsonEscape(_config.SpawnMode) << "\""
         << ",\"allow_configured_center_fallback\":" << (_config.AllowConfiguredCenterFallback ? "true" : "false")
         << ",\"use_saved_position\":" << (_config.UseSavedPosition ? "true" : "false")
         << ",\"near_player_radius\":" << _config.NearPlayerRadius
         << ",\"death_recovery_mode\":\"" << JsonEscape(_config.DeathRecoveryMode) << "\""
         << ",\"teleport_to_center_on_death\":" << (_config.TeleportToCenterOnDeath ? "true" : "false")
         << ",\"max_deaths_before_fallback\":" << _config.MaxDeathsBeforeFallback
         << ",\"safe_position_memory_sec\":" << _config.SafePositionMemorySec
         << ",\"auto_start_recording\":" << (_config.AutoStartRecording ? "true" : "false")
         << ",\"auto_recording_window_minutes\":" << _config.AutoRecordingWindowMinutes
         << ",\"auto_recording_name_prefix\":\"" << JsonEscape(_config.AutoRecordingNamePrefix) << "\""
         << ",\"bot_learning\":{\"enable\":" << (_learningConfig.Enabled ? "true" : "false")
         << ",\"min_samples_for_strong_bias\":" << _learningConfig.MinSamplesForStrongBias
         << ",\"danger_penalty_weight\":" << _learningConfig.DangerPenaltyWeight
         << ",\"progression_reward_weight\":" << _learningConfig.ProgressionRewardWeight
         << ",\"recent_failure_penalty_weight\":" << _learningConfig.RecentFailurePenaltyWeight
         << ",\"exploration_novelty_weight\":" << _learningConfig.ExplorationNoveltyWeight
         << ",\"allow_global_memory_fallback\":" << (_learningConfig.AllowGlobalMemoryFallback ? "true" : "false") << "}"
         << ",\"bot_policy_model\":{\"enable\":" << (_policyModelConfig.Enabled ? "true" : "false")
         << ",\"mode\":\"" << JsonEscape(_policyModelConfig.Mode) << "\""
         << ",\"version\":\"" << JsonEscape(_policyModelConfig.Version) << "\""
         << ",\"score_weight\":" << _policyModelConfig.ScoreWeight
         << ",\"fail_closed\":" << (_policyModelConfig.FailClosed ? "true" : "false")
         << ",\"max_decision_latency_ms\":" << _policyModelConfig.MaxDecisionLatencyMs
         << ",\"min_eval_rows\":" << _policyModelConfig.MinEvalRows
         << ",\"max_death_rate\":" << _policyModelConfig.MaxDeathRate
         << ",\"max_stuck_rate\":" << _policyModelConfig.MaxStuckRate
         << ",\"max_failure_rate\":" << _policyModelConfig.MaxFailureRate
         << ",\"assist_allowed\":" << (_policyModelConfig.AssistAllowed ? "true" : "false")
         << ",\"deployment_reason\":\"" << JsonEscape(_policyModelConfig.DeploymentReason) << "\""
         << ",\"artifact_loaded\":" << (_policyModelConfig.ArtifactLoaded ? "true" : "false")
         << ",\"artifact_path\":\"" << JsonEscape(_policyModelConfig.ArtifactPath) << "\""
         << ",\"model_type\":\"" << JsonEscape(_policyModelConfig.ModelType) << "\""
         << ",\"feature_schema_version\":\"" << JsonEscape(_policyModelConfig.FeatureSchemaVersion) << "\"}"
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
    if (!_policyModelConfig.Enabled || _policyModelConfig.Version.empty())
        return;

    auto started = std::chrono::steady_clock::now();
    std::vector<float> modelScores;
    modelScores.reserve(activityScores.size());
    for (BotActivityScore const& score : activityScores)
        modelScores.push_back(ScorePolicyModelCandidate(score, bot, power, stage));

    uint32 latencyMs = uint32(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - started).count());
    bool assist = _policyModelConfig.Mode == "assist" && _policyModelConfig.AssistAllowed;
    if (!assist || latencyMs > _policyModelConfig.MaxDecisionLatencyMs)
        return;

    for (size_t i = 0; i < activityScores.size() && i < modelScores.size(); ++i)
        activityScores[i].Score += _policyModelConfig.ScoreWeight * modelScores[i];
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
    auto ensembleItr = _policyModelConfig.ModelTreeEnsembles.find(key);
    if (ensembleItr != _policyModelConfig.ModelTreeEnsembles.end())
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
    auto meanItr = _policyModelConfig.ModelMeans.find(key);
    if (meanItr != _policyModelConfig.ModelMeans.end())
        value = meanItr->second;

    auto weightItr = _policyModelConfig.ModelWeights.find(key);
    if (weightItr != _policyModelConfig.ModelWeights.end())
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
    if (!_policyModelConfig.Enabled || _policyModelConfig.Version.empty())
        return 0.0f;
    if (!_policyModelConfig.ArtifactLoaded)
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
    if (!_policyModelConfig.Enabled || _policyModelConfig.Version.empty())
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
             << "|run_id=" << _runId
             << "|experiment_id=" << _experimentId
             << "|level=" << (bot ? uint32(bot->getLevel()) : 0)
             << "|activity=" << chosenName
             << "|clip_id=" << clipId
             << "|replay_id=" << replayId
             << "|model=" << _policyModelConfig.Version;
    uint32 featuresHash = FeatureSchemaHash(features.str());

    std::ostringstream json;
    json << "{\"enabled\":true"
         << ",\"mode\":\"" << JsonEscape(_policyModelConfig.Mode) << "\""
         << ",\"assist_allowed\":" << (_policyModelConfig.AssistAllowed ? "true" : "false")
         << ",\"deployment_reason\":\"" << JsonEscape(_policyModelConfig.DeploymentReason) << "\""
         << ",\"artifact_loaded\":" << (_policyModelConfig.ArtifactLoaded ? "true" : "false")
         << ",\"model_type\":\"" << JsonEscape(_policyModelConfig.ModelType) << "\""
         << ",\"model_version\":\"" << JsonEscape(_policyModelConfig.Version) << "\""
         << ",\"feature_schema_version\":\"" << JsonEscape(_policyModelConfig.FeatureSchemaVersion) << "\""
         << ",\"model_score\":" << chosenModelScore
         << ",\"model_rank\":" << chosenRank
         << ",\"model_reason\":\"" << JsonEscape(_policyModelConfig.Mode == "assist" && _policyModelConfig.AssistAllowed ? "assist_score_blend" : "shadow_score_only") << "\""
         << ",\"model_features_hash\":" << featuresHash
         << ",\"trace\":{\"run_id\":" << _runId
         << ",\"experiment_id\":" << _experimentId
         << ",\"decision_id\":null"
         << ",\"clip_id\":" << clipId
         << ",\"replay_id\":" << replayId
         << ",\"bot_guid\":" << (bot ? bot->GetGUID().GetCounter() : 0)
         << ",\"brain_version\":\"" << JsonEscape(_config.BrainVersion) << "\""
         << ",\"model_version\":\"" << JsonEscape(_policyModelConfig.Version) << "\""
         << ",\"feature_schema_version\":\"" << JsonEscape(_policyModelConfig.FeatureSchemaVersion) << "\"}"
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

BotWorldStatus BotWorldPopulationMgr::GetStatus() const
{
    BotWorldStatus status = _metrics;
    status.Active = _active;
    status.Mode = _runtimeMode;
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
         << ",\"mode\":\"" << (status.Mode == BotWorldRuntimeMode::AlwaysOnAutonomy ? "always_on_autonomy" : "manual_experiment") << "\""
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
         << ",\"raid_boss_kills\":" << status.RaidBossKills
         << ",\"heroic_raid_boss_kills\":" << status.HeroicRaidBossKills
         << ",\"raid_telemetry_events\":" << status.RaidTelemetryEvents
         << ",\"segment_counts\":" << _experimentCoordinator.GetCountsJson()
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
         << ",\"raid_boss_kills\":" << status.RaidBossKills
         << ",\"heroic_raid_boss_kills\":" << status.HeroicRaidBossKills
         << ",\"raid_telemetry_events\":" << status.RaidTelemetryEvents
         << ",\"segment_counts\":" << _experimentCoordinator.GetCountsJson()
         << ",\"bot_learning\":{\"enable\":" << (_learningConfig.Enabled ? "true" : "false")
         << ",\"min_samples_for_strong_bias\":" << _learningConfig.MinSamplesForStrongBias
         << ",\"danger_penalty_weight\":" << _learningConfig.DangerPenaltyWeight
         << ",\"progression_reward_weight\":" << _learningConfig.ProgressionRewardWeight
         << ",\"recent_failure_penalty_weight\":" << _learningConfig.RecentFailurePenaltyWeight
         << ",\"exploration_novelty_weight\":" << _learningConfig.ExplorationNoveltyWeight
         << ",\"allow_global_memory_fallback\":" << (_learningConfig.AllowGlobalMemoryFallback ? "true" : "false") << "}"
         << ",\"decisions\":" << status.Decisions
         << ",\"failures_recorded\":" << status.Failures << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::GetBotDebugJson(std::string const& selector) const
{
    WorldBotState const* selected = nullptr;
    if (!selector.empty() && selector != "all")
    {
        for (WorldBotState const& state : _bots)
        {
            Player* bot = GetBot(state);
            if (!bot)
                continue;
            if (selector == std::to_string(state.Guid.GetCounter()) || selector == bot->GetName())
            {
                selected = &state;
                break;
            }
        }
    }
    if (!selected && !_bots.empty())
        selected = &_bots.front();

    if (!selected)
        return "{\"ok\":false,\"action\":\"botauto_debug\",\"failure_reason\":\"no_active_bot\"}";

    Player* bot = GetBot(*selected);
    if (!bot)
        return "{\"ok\":false,\"action\":\"botauto_debug\",\"failure_reason\":\"bot_not_loaded\"}";

    uint32 savedMap = 0;
    float savedX = 0.0f;
    float savedY = 0.0f;
    float savedZ = 0.0f;
    float savedO = 0.0f;
    if (QueryResult result = CharacterDatabase.PQuery("SELECT map, position_x, position_y, position_z, orientation FROM characters WHERE guid = %u", selected->Guid.GetCounter()))
    {
        Field* fields = result->Fetch();
        savedMap = fields[0].GetUInt16();
        savedX = fields[1].GetFloat();
        savedY = fields[2].GetFloat();
        savedZ = fields[3].GetFloat();
        savedO = fields[4].GetFloat();
    }

    Unit* target = selected->TargetGuid.IsEmpty() ? bot->GetVictim() : ObjectAccessor::GetUnit(*bot, selected->TargetGuid);
    bool targetDummy = IsTrainingDummy(target);
    QuestObjectivePlan plan;
    bool hasPlan = FindActiveQuestObjective(bot, plan);
    bool dummyAllowed = hasPlan && IsTrainingDummyAllowedForQuest(plan, target);
    char const* progressionReject = nullptr;
    bool targetProgressionRelevant = target && IsProgressionCombatTarget(bot, target, &progressionReject);
    bool targetMatchesObjective = false;
    std::string targetName;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        targetMatchesObjective = selected->QuestWork.RequiredEntry <= 0 || uint32(selected->QuestWork.RequiredEntry) == creature->GetEntry();
        targetName = creature->GetName();
    }

    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_debug\""
         << ",\"bot_guid\":" << selected->Guid.GetCounter()
         << ",\"bot_name\":\"" << JsonEscape(bot->GetName()) << "\""
         << ",\"spawn_source\":\"" << JsonEscape(selected->SpawnSource) << "\""
         << ",\"saved_position\":{\"map\":" << savedMap << ",\"x\":" << savedX << ",\"y\":" << savedY << ",\"z\":" << savedZ << ",\"o\":" << savedO << "}"
         << ",\"race_start_fallback_used\":" << (selected->RaceStartFallbackUsed ? "true" : "false")
         << ",\"saved_or_race_start_status\":\"" << JsonEscape(selected->RaceStartFallbackUsed ? "race_start" : selected->SpawnSource) << "\""
         << ",\"current_quest_state\":\"" << JsonEscape(selected->CurrentQuestState) << "\""
         << ",\"chosen_activity\":\"" << JsonEscape(selected->ActivityType) << "\""
         << ",\"allow_grinding\":" << (_config.AllowGrinding ? "true" : "false")
         << ",\"quest_first\":" << (_config.QuestFirst ? "true" : "false")
         << ",\"grind_only_when_no_quest_available\":" << (_config.GrindOnlyWhenNoQuestAvailable ? "true" : "false")
         << ",\"quest_phase\":\"" << JsonEscape(selected->QuestWork.Phase) << "\""
         << ",\"active_quest_id\":" << selected->QuestWork.ActiveQuestId
         << ",\"newly_accepted_quest_id\":" << selected->NewlyAcceptedQuestId
         << ",\"objective_index\":" << selected->QuestWork.ObjectiveIndex
         << ",\"objective_type\":\"" << JsonEscape(selected->QuestWork.ObjectiveType != "none" ? selected->QuestWork.ObjectiveType : (hasPlan ? ToString(plan.ObjectiveType) : selected->CurrentObjectiveType.c_str())) << "\""
         << ",\"required_count\":" << selected->QuestWork.RequiredCount
         << ",\"current_count\":" << selected->QuestWork.CurrentCount
         << ",\"selected_target_guid\":" << selected->QuestWork.SelectedTargetGuid.GetCounter()
         << ",\"selected_object_guid\":" << selected->QuestWork.SelectedObjectGuid.GetCounter()
         << ",\"selected_giver_guid\":" << selected->QuestWork.SelectedGiverGuid.GetCounter()
         << ",\"selected_giver_cooldown_until_ms\":" << (selected->QuestWork.SelectedGiverGuid.IsEmpty() || selected->QuestGiverCooldownUntilMs.find(selected->QuestWork.SelectedGiverGuid.GetCounter()) == selected->QuestGiverCooldownUntilMs.end() ? 0 : selected->QuestGiverCooldownUntilMs.find(selected->QuestWork.SelectedGiverGuid.GetCounter())->second)
         << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
         << ",\"target_entry\":" << (target && target->ToCreature() ? target->ToCreature()->GetEntry() : 0)
         << ",\"target_name\":\"" << JsonEscape(targetName) << "\""
         << ",\"target_matches_objective\":" << (targetMatchesObjective ? "true" : "false")
         << ",\"target_progression_relevant\":" << (targetProgressionRelevant ? "true" : "false")
         << ",\"target_progression_reject_reason\":\"" << JsonEscape(progressionReject ? progressionReject : "") << "\""
         << ",\"target_training_dummy\":" << (targetDummy ? "true" : "false")
         << ",\"dummy_allowed_by_active_quest\":" << (dummyAllowed ? "true" : "false")
         << ",\"required_spell\":" << (selected->QuestWork.RequiredSpell ? selected->QuestWork.RequiredSpell : (hasPlan ? plan.RequiredSpellId : selected->RequiredSpellId))
         << ",\"required_item\":" << (selected->QuestWork.RequiredItem ? selected->QuestWork.RequiredItem : (hasPlan ? plan.ItemId : selected->RequiredItemId))
         << ",\"required_target\":" << (selected->QuestWork.RequiredEntry > 0 ? uint32(selected->QuestWork.RequiredEntry) : (hasPlan && plan.RequiredEntry > 0 ? uint32(plan.RequiredEntry) : selected->RequiredTargetEntry))
         << ",\"loot_attempt_count\":" << selected->LootAttemptCount
         << ",\"last_loot_result\":\"" << JsonEscape(selected->LastLootResult) << "\""
         << ",\"last_loot_items_count\":" << selected->LastLootItemsCount
         << ",\"last_loot_money\":" << selected->LastLootMoney
         << ",\"last_loot_state_cleared\":" << (selected->LastLootStateCleared ? "true" : "false")
         << ",\"last_quest_progress_before\":" << selected->LastQuestProgressBefore
         << ",\"last_quest_progress_after\":" << selected->LastQuestProgressAfter
         << ",\"quest_work_progress_before\":" << selected->QuestWork.ProgressBefore
         << ",\"quest_work_progress_after\":" << selected->QuestWork.ProgressAfter
         << ",\"last_no_progress_reason\":\"" << JsonEscape(selected->LastNoProgressReason) << "\""
         << ",\"last_objective_not_found_reason\":\"" << JsonEscape(selected->LastObjectiveNotFoundReason) << "\""
         << ",\"last_grinding_allowed_reason\":\"" << JsonEscape(selected->LastGrindingAllowedReason) << "\""
         << ",\"current_quest_supported\":" << (hasPlan ? "true" : "false")
         << ",\"cooldown_until_ms\":" << selected->QuestWork.CooldownUntilMs
         << ",\"failure_reason\":\"" << JsonEscape(selected->QuestWork.FailedReason) << "\""
         << ",\"last_rejected_target_reason\":\"" << JsonEscape(selected->LastRejectedTargetReason) << "\""
         << "}";
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
