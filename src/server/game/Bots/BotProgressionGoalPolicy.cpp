#include "Bots/BotProgressionGoalPolicy.h"
#include "Player.h"
#include "DataStores/DBCEnums.h"
#include <sstream>

namespace
{
std::string ProgressionGoalEscape(std::string const& value)
{
    std::ostringstream out;
    for (char c : value)
    {
        if (c == '\\' || c == '"')
            out << '\\';
        out << c;
    }
    return out.str();
}
}

std::string BotProgressionGoalPolicy::RoleGoal(std::string const& role)
{
    if (role == "healer")
        return "keep_group_alive_triage_dispel_mana_efficiency_then_safe_dps";
    if (role == "tank")
        return "survive_hold_threat_position_control_then_safe_dps";
    return "maximize_effective_dps_correct_targets_interrupts_mechanics_survival";
}

std::string BotProgressionGoalPolicy::ProgressionReason(Player const* bot, char const* activity, char const* situation)
{
    std::ostringstream json;
    float itemLevel = bot ? bot->GetAverageItemLevel() : 0.0f;
    json << "{\"core_objective\":\"class_spec_power\""
         << ",\"priority_order\":[\"combat_effectiveness\",\"dungeon_completion\",\"raid_completion\",\"fast_quest_leveling\",\"supporting_professions_reputation_currency_gold\"]"
         << ",\"activity\":\"" << ProgressionGoalEscape(activity ? activity : "unknown") << "\""
         << ",\"situation\":\"" << ProgressionGoalEscape(situation ? situation : "unknown") << "\""
         << ",\"bot_level\":" << (bot ? uint32(bot->getLevel()) : 0)
         << ",\"average_item_level\":" << itemLevel
         << ",\"reason\":\"choose actions that improve survivability role output completion speed or gear readiness\"}";
    return json.str();
}

std::string BotProgressionGoalPolicy::ProfessionGoalJson(Player const* bot, std::string const& role, char const* activity)
{
    uint32 armorSkill = 0;
    uint32 consumableSkill = SKILL_COOKING;
    switch (bot ? bot->getClass() : 0)
    {
        case CLASS_WARRIOR:
        case CLASS_PALADIN:
        case CLASS_DEATH_KNIGHT:
            armorSkill = SKILL_BLACKSMITHING;
            break;
        case CLASS_HUNTER:
        case CLASS_SHAMAN:
        case CLASS_ROGUE:
        case CLASS_DRUID:
            armorSkill = SKILL_LEATHERWORKING;
            break;
        case CLASS_MAGE:
        case CLASS_PRIEST:
        case CLASS_WARLOCK:
            armorSkill = SKILL_TAILORING;
            break;
        default:
            break;
    }

    bool activityProfession = activity && std::string(activity) == "profession_farm";
    std::ostringstream json;
    json << "{\"profession_secondary\":true"
         << ",\"role\":\"" << ProgressionGoalEscape(role) << "\""
         << ",\"desired_recipe\":\"" << (role == "healer" ? "healing_intellect_spirit_gear_or_consumable" : (role == "tank" ? "stamina_mitigation_gear_or_consumable" : "primary_stat_damage_gear_or_consumable")) << "\""
         << ",\"material_requirement\":\"known_recipe_mats_when_available\""
         << ",\"farm_source\":\"nearby_safe_nodes_mobs_vendors_or_memory_poi\""
         << ",\"trainer_recipe_source\":\"class_profession_trainer_vendor_drop_reputation_when_known\""
         << ",\"daily_cooldown_status\":\"unknown_record_only\""
         << ",\"crafted_item_improves_power\":\"" << (activityProfession ? "evaluate_before_delaying_main_progression" : "only_if_material_to_power_or_speed") << "\""
         << ",\"armor_profession_skill\":" << armorSkill
         << ",\"consumable_skill\":" << consumableSkill << "}";
    return json.str();
}

std::string BotProgressionGoalPolicy::QuestPortfolioSummaryJson(uint32 activeQuestCount, uint32 clusterId, char const* phase, char const* unsupportedReason)
{
    std::ostringstream json;
    json << "{\"active_quest_count\":" << activeQuestCount
         << ",\"quest_cluster_id\":" << clusterId
         << ",\"quest_phase\":\"" << ProgressionGoalEscape(phase ? phase : "idle") << "\""
         << ",\"route_policy\":\"accept_nearby_supported_before_cluster_travel_turn_in_completed_efficiently\""
         << ",\"unsupported_reason\":\"" << ProgressionGoalEscape(unsupportedReason ? unsupportedReason : "") << "\"}";
    return json.str();
}
