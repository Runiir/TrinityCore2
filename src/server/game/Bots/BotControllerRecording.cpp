#include "Bots/BotController.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotDatasetEvent.h"
#include "Bots/BotMgr.h"
#include "Config.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupReference.h"
#include "Log.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "DataStores/DBCStructure.h"
#include "DungeonFinding/LFG.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "Transport.h"
#include "Spell.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include <algorithm>
#include <boost/filesystem.hpp>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <map>
#include <sstream>
#include <utility>

namespace
{
std::string JsonEscape(std::string const& value)
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

uint64 PlayerBotNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

std::string PlayerBotExperimentId()
{
    std::string experimentId = sConfigMgr->GetStringDefault("PlayerBot.ExperimentId", "playerbot");
    return experimentId.empty() ? "playerbot" : experimentId;
}

BotCombatArchetype CombatArchetypeForClass(uint8 classId, std::string const& runtimeRole, std::string const& classSpec = "")
{
    if (runtimeRole == "tank")
        return BotCombatArchetype::TankLikeMelee;
    if (runtimeRole == "healer")
        return BotCombatArchetype::HealerSolo;
    if (classSpec == "enhancement_shaman")
        return BotCombatArchetype::MeleeDps;

    switch (classId)
    {
        case CLASS_HUNTER:
            return BotCombatArchetype::RangedPhysical;
        case CLASS_MAGE:
        case CLASS_PRIEST:
        case CLASS_SHAMAN:
            return BotCombatArchetype::RangedCaster;
        case CLASS_WARLOCK:
            return BotCombatArchetype::PetClass;
        default:
            return BotCombatArchetype::MeleeDps;
    }
}
}

BotProfessionFrame BotController::BuildProfessionFrame(Player* owner, Player* bot) const
{
    BotProfessionFrame frame;
    frame.OwnerGuid = owner ? owner->GetGUID() : ObjectGuid::Empty;
    frame.BotGuid = bot ? bot->GetGUID() : ObjectGuid::Empty;
    if (!bot)
        return frame;

    frame.ClassId = bot->getClass();
    frame.SpecId = 0;
    frame.Profession.ProfessionId = "cooking";
    frame.Profession.SkillId = SKILL_COOKING;
    frame.Profession.SkillCurrent = bot->HasSkill(SKILL_COOKING) ? bot->GetSkillValue(SKILL_COOKING) : 0;
    frame.Profession.SkillTarget = bot->HasSkill(SKILL_COOKING) ? bot->GetMaxSkillValue(SKILL_COOKING) : 0;
    frame.Profession.BagFreeSlots = bot->GetFreeInventorySpace();
    frame.Inventory.Gold = bot->GetMoney();

    if (std::vector<SkillLineAbilityEntry const*> const* abilities = sDBCManager.GetSkillLineAbilitiesBySkill(SKILL_COOKING))
    {
        for (SkillLineAbilityEntry const* ability : *abilities)
        {
            if (!ability || !ability->Spell)
                continue;

            if (bot->HasSpell(ability->Spell))
                frame.Profession.KnownRecipes.push_back(ability->Spell);
            else if (bot->HasSkill(SKILL_COOKING) && ability->MinSkillLineRank <= frame.Profession.SkillCurrent)
                frame.Profession.TrainableRecipes.push_back(ability->Spell);
        }
    }

    std::map<uint32, uint32> itemCounts;
    auto addItem = [&itemCounts](Item const* item)
    {
        if (!item)
            return;

        itemCounts[item->GetEntry()] += item->GetCount();
    };

    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        addItem(bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));

    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
    {
        if (Bag const* bag = bot->GetBagByPos(bagSlot))
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                addItem(bag->GetItemByPos(slot));
    }

    for (auto const& itemCount : itemCounts)
        frame.Inventory.Materials.push_back(BotInventoryMaterial{ itemCount.first, itemCount.second });

    return frame;
}

void BotController::RecordFrame(HealerFrame const& frame, HealerDecision const& decision, ResolvedBotAction const* action, BotActionResult result, Player* owner, Player* bot) const
{
    std::string path = sConfigMgr->GetStringDefault("PlayerBot.Record.Path", "dataset/raw/healer_frames_playerbot.jsonl");
    boost::filesystem::path outputPath(path);
    if (outputPath.has_parent_path())
        boost::filesystem::create_directories(outputPath.parent_path());

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out)
        return;

    uint64 seq = ++_sequence;
    std::ostringstream observation;
    observation << "{\"owner_guid\":" << frame.OwnerGuid.GetCounter()
                << ",\"map_id\":" << frame.MapId
                << ",\"instance_id\":" << (bot ? bot->GetInstanceId() : 0)
                << ",\"bot_hp_pct\":" << frame.BotHealthPct
                << ",\"bot_mana_pct\":" << frame.BotManaPct
                << ",\"bot_cast_spell_id\":" << frame.BotCastSpellId
                << ",\"bot_channel_spell_id\":" << frame.BotChannelSpellId
                << ",\"bot_aura_count\":" << frame.BotAuraCount
                << ",\"bot_debuff_count\":" << frame.BotDebuffCount
                << ",\"recent_damage_taken\":" << frame.RecentDamageTaken
                << ",\"recent_healing_done\":" << frame.RecentHealingDone
                << ",\"recent_healing_received\":" << frame.RecentHealingReceived
                << ",\"party_size\":" << frame.Party.size() << "}";

    std::ostringstream chosen;
    chosen << "{\"mode\":\"" << JsonEscape(ToString(decision.Mode))
           << "\",\"intent\":\"" << JsonEscape(ToString(decision.Intent))
           << "\",\"target_guid\":" << decision.TargetGuid.GetCounter()
           << ",\"spell_id\":" << (action ? action->SpellId : 0)
           << ",\"action\":\"" << JsonEscape(action ? action->DebugName : "wait") << "\"}";

    BotDatasetEvent dataset;
    dataset.run_id = PlayerBotRunId();
    dataset.experiment_id = PlayerBotExperimentId();
    dataset.episode_id = dataset.run_id;
    dataset.bot_guid = frame.BotGuid;
    dataset.bot_role = ToString(_role);
    dataset.bot_level = bot ? uint32(bot->getLevel()) : 0;
    dataset.policy_source = BotPolicySource::Rule;
    dataset.policy_version = "playerbot_rule_v1";
    dataset.timestamp_ms = PlayerBotNowMs();
    dataset.tick_id = seq;
    dataset.domain = "party_healing";
    dataset.situation = ToString(decision.Intent);
    dataset.observation_json = observation.str();
    dataset.semantic_json = "{\"role\":\"" + std::string(ToString(_role)) + "\"}";
    dataset.valid_action_mask_json = _lastHealerCandidateMaskJson;
    dataset.chosen_action_json = _lastHealerChosenActionJson;
    dataset.action_result = ToString(result);
    dataset.outcome_json = "{\"result\":\"" + std::string(ToString(result)) + "\"}";
    dataset.quality_flags_json = "{\"source\":\"playerbot_jsonl\"}";
    if (dataset.Validate())
        out << dataset.ToJson() << "\n";
}
void BotController::RecordProfessionFrame(BotProfessionFrame const& frame, Player* owner, Player* bot) const
{
    std::string path = sConfigMgr->GetStringDefault("PlayerBot.Record.Path", "dataset/raw/healer_frames_playerbot.jsonl");
    boost::filesystem::path outputPath(path);
    if (outputPath.has_parent_path())
        boost::filesystem::create_directories(outputPath.parent_path());

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out)
        return;

    uint64 seq = ++_sequence;
    std::ostringstream observation;
    observation << "{\"owner_guid\":" << frame.OwnerGuid.GetCounter()
                << ",\"class_id\":" << uint32(frame.ClassId)
                << ",\"spec_id\":" << frame.SpecId
                << ",\"profession_id\":\"" << JsonEscape(frame.Profession.ProfessionId)
                << "\",\"skill_id\":" << frame.Profession.SkillId
                << ",\"skill_current\":" << frame.Profession.SkillCurrent
                << ",\"skill_target\":" << frame.Profession.SkillTarget
                << ",\"known_recipe_count\":" << frame.Profession.KnownRecipes.size()
                << ",\"trainable_recipe_count\":" << frame.Profession.TrainableRecipes.size()
                << ",\"bag_free_slots\":" << frame.Profession.BagFreeSlots
                << ",\"gold\":" << frame.Inventory.Gold
                << ",\"material_count\":" << frame.Inventory.Materials.size() << "}";

    BotDatasetEvent dataset;
    dataset.run_id = PlayerBotRunId();
    dataset.experiment_id = PlayerBotExperimentId();
    dataset.episode_id = dataset.run_id;
    dataset.bot_guid = frame.BotGuid;
    dataset.bot_role = ToString(_role);
    dataset.bot_level = bot ? uint32(bot->getLevel()) : 0;
    dataset.policy_source = BotPolicySource::Rule;
    dataset.policy_version = "playerbot_rule_v1";
    dataset.timestamp_ms = PlayerBotNowMs();
    dataset.tick_id = seq;
    dataset.domain = "profession";
    dataset.situation = "profession_tick";
    dataset.observation_json = observation.str();
    dataset.semantic_json = "{\"profession_id\":\"" + JsonEscape(frame.Profession.ProfessionId) + "\"}";
    dataset.valid_action_mask_json = "{\"wait\":true}";
    dataset.chosen_action_json = "{\"type\":\"wait\",\"valid\":true}";
    dataset.action_result = "observed";
    dataset.outcome_json = "{\"skill_delta\":0,\"materials_spent_value\":0,\"time_spent_sec\":0}";
    dataset.quality_flags_json = "{\"source\":\"playerbot_jsonl\"}";
    if (dataset.Validate())
        out << dataset.ToJson() << "\n";
}

void BotController::RecordCombatFrame(BotCombatState const& frame, BotCombatDecision const& decision, ResolvedCombatAction const& action, BotActionResult result, Player* owner, Player* bot) const
{
    std::string path = sConfigMgr->GetStringDefault("PlayerBot.Record.Path", "dataset/raw/healer_frames_playerbot.jsonl");
    boost::filesystem::path outputPath(path);
    if (outputPath.has_parent_path())
        boost::filesystem::create_directories(outputPath.parent_path());

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out)
        return;

    uint64 seq = ++_sequence;
    std::ostringstream observation;
    observation << "{\"self\":{\"hp_pct\":" << frame.SelfHpPct
                << ",\"power_pct\":" << frame.SelfPowerPct
                << ",\"class_id\":" << uint32(frame.ClassId)
                << ",\"spec_id\":" << frame.SpecId
                << ",\"moving\":" << (frame.Moving ? "true" : "false")
                << ",\"casting\":" << (frame.Casting ? "true" : "false")
                << ",\"gcd_ready\":" << (frame.GcdReady ? "true" : "false") << "}"
                << ",\"target\":{\"guid\":" << frame.TargetGuid.GetCounter()
                << ",\"entry_id\":" << frame.TargetEntry
                << ",\"hp_pct\":" << frame.TargetHpPct
                << ",\"distance\":" << frame.TargetDistance
                << ",\"interruptible\":" << (frame.TargetInterruptible ? "true" : "false")
                << ",\"dead\":" << (frame.TargetDead ? "true" : "false")
                << ",\"lootable\":" << (frame.TargetLootable ? "true" : "false") << "}"
                << ",\"environment\":{\"nearby_hostile_count\":" << frame.NearbyHostileCount
                << ",\"elite_nearby\":" << (frame.EliteNearby ? "true" : "false")
                << ",\"extra_pull_risk\":" << frame.ExtraPullRisk << "}}";
    std::ostringstream chosen;
    chosen << "{\"type\":\"" << JsonEscape(action.Type)
           << "\",\"spell_id\":" << action.SpellId
           << ",\"target_guid\":" << action.TargetGuid.GetCounter()
           << ",\"intent\":\"" << ToString(decision.Intent)
           << "\",\"valid\":" << (action.Valid ? "true" : "false") << "}";

    BotDatasetEvent dataset;
    dataset.run_id = PlayerBotRunId();
    dataset.experiment_id = PlayerBotExperimentId();
    dataset.episode_id = dataset.run_id;
    dataset.bot_guid = bot ? bot->GetGUID() : _botGuid;
    dataset.bot_role = ToString(_role);
    dataset.bot_level = bot ? uint32(bot->getLevel()) : 0;
    dataset.policy_source = BotPolicySource::Rule;
    dataset.policy_version = "playerbot_rule_v1";
    dataset.timestamp_ms = PlayerBotNowMs();
    dataset.tick_id = seq;
    dataset.domain = "combat";
    dataset.situation = ToString(decision.Intent);
    dataset.observation_json = observation.str();
    dataset.semantic_json = "{\"runtime_role\":\"" + JsonEscape(_runtimeRole) + "\",\"class_spec\":\"" + JsonEscape(_classSpec) + "\",\"archetype\":\"" + std::string(ToString(CombatArchetypeForClass(frame.ClassId, _runtimeRole, _classSpec))) + "\"}";
    dataset.valid_action_mask_json = "{\"intents\":[\"pull_target\",\"maintain_rotation\",\"interrupt\",\"use_defensive\",\"heal_self\",\"move_to_range\",\"loot\",\"recover\",\"wait\"]}";
    dataset.chosen_action_json = chosen.str();
    dataset.action_result = ToString(result);
    dataset.outcome_json = "{\"target_dead_10s\":" + std::string(frame.TargetDead ? "true" : "false") + ",\"loot_success\":" + std::string(decision.Intent == BotCombatIntent::Loot && result == BotActionResult::Ok ? "true" : "false") + "}";
    dataset.quality_flags_json = "{\"source\":\"playerbot_jsonl\"}";
    if (dataset.Validate())
        out << dataset.ToJson() << "\n";
}

void BotController::RecordMovementFrame(BotMovementFrame const& frame, char const* policyMode, char const* intent, char const* action, bool valid, Player* owner, Player* bot) const
{
    std::string path = sConfigMgr->GetStringDefault("PlayerBot.Record.Path", "dataset/raw/healer_frames_playerbot.jsonl");
    boost::filesystem::path outputPath(path);
    if (outputPath.has_parent_path())
        boost::filesystem::create_directories(outputPath.parent_path());

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out)
        return;

    char const* resolvedAction = action && *action ? action : "wait";
    uint64 seq = ++_sequence;
    std::ostringstream observation;
    observation << "{\"self\":{\"position\":[" << frame.X << "," << frame.Y << "," << frame.Z << "]"
                << ",\"orientation\":" << frame.Orientation
                << ",\"moving\":" << (frame.Moving ? "true" : "false")
                << ",\"mounted\":" << (frame.Mounted ? "true" : "false")
                << ",\"in_combat\":" << (frame.InCombat ? "true" : "false")
                << ",\"hp_pct\":" << frame.HpPct
                << ",\"distance_to_leader\":" << frame.DistanceToLeader
                << ",\"distance_to_group_center\":" << frame.DistanceToGroupCenter
                << ",\"line_of_sight_to_leader\":" << (frame.LineOfSightToLeader ? "true" : "false") << "}"
                << ",\"navigation\":{\"current_path_length\":" << frame.CurrentPathLength
                << ",\"path_available\":" << (frame.PathAvailable ? "true" : "false")
                << ",\"stuck_score\":" << frame.StuckScore
                << ",\"last_progress_time_ms\":" << frame.LastProgressTimeMs << "}}";

    BotDatasetEvent dataset;
    dataset.run_id = PlayerBotRunId();
    dataset.experiment_id = PlayerBotExperimentId();
    dataset.episode_id = dataset.run_id;
    dataset.bot_guid = bot ? bot->GetGUID() : _botGuid;
    dataset.bot_role = ToString(_role);
    dataset.bot_level = bot ? uint32(bot->getLevel()) : 0;
    dataset.policy_source = BotPolicySource::Rule;
    dataset.policy_version = "playerbot_rule_v1";
    dataset.timestamp_ms = PlayerBotNowMs();
    dataset.tick_id = seq;
    dataset.domain = "movement";
    dataset.situation = intent && *intent ? intent : "movement_tick";
    dataset.observation_json = observation.str();
    dataset.semantic_json = "{\"policy_mode\":\"" + JsonEscape(policyMode ? policyMode : "follow") + "\"}";
    dataset.valid_action_mask_json = "{\"movement_actions\":true}";
    dataset.chosen_action_json = "{\"type\":\"" + JsonEscape(resolvedAction) + "\",\"valid\":" + std::string(valid ? "true" : "false") + "}";
    dataset.action_result = valid ? "ok" : "invalid";
    dataset.outcome_json = "{\"distance_to_leader_after_2s\":" + std::to_string(frame.DistanceToLeader) + ",\"stuck\":" + std::string(frame.StuckScore >= 1.0f ? "true" : "false") + "}";
    dataset.quality_flags_json = "{\"source\":\"playerbot_jsonl\"}";
    if (dataset.Validate())
        out << dataset.ToJson() << "\n";
}
