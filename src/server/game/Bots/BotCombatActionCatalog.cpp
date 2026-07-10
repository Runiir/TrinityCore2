#include "Bots/BotCombatActionCatalog.h"
#include <sstream>

namespace
{
std::string CombatCatalogEscape(std::string const& value)
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

char const* BotCombatActionCatalog::ToString(BotCombatActionCategory category)
{
    switch (category)
    {
        case BotCombatActionCategory::Movement: return "movement";
        case BotCombatActionCategory::Wait: return "wait";
        case BotCombatActionCategory::TargetSelect: return "target_select";
        case BotCombatActionCategory::TargetSwitch: return "target_switch";
        case BotCombatActionCategory::AutoAttack: return "auto_attack";
        case BotCombatActionCategory::Builder: return "builder";
        case BotCombatActionCategory::Spender: return "spender";
        case BotCombatActionCategory::Dot: return "dot";
        case BotCombatActionCategory::Buff: return "buff";
        case BotCombatActionCategory::Debuff: return "debuff";
        case BotCombatActionCategory::Interrupt: return "interrupt";
        case BotCombatActionCategory::StunCc: return "stun_cc";
        case BotCombatActionCategory::Defensive: return "defensive";
        case BotCombatActionCategory::OffensiveCooldown: return "offensive_cooldown";
        case BotCombatActionCategory::Execute: return "execute";
        case BotCombatActionCategory::Aoe: return "aoe";
        case BotCombatActionCategory::Cleave: return "cleave";
        case BotCombatActionCategory::DispelCleanse: return "dispel_cleanse";
        case BotCombatActionCategory::Taunt: return "taunt";
        case BotCombatActionCategory::ThreatBuild: return "threat_build";
        case BotCombatActionCategory::Mitigation: return "mitigation";
        case BotCombatActionCategory::HealEfficient: return "heal_efficient";
        case BotCombatActionCategory::HealFast: return "heal_fast";
        case BotCombatActionCategory::HealAoe: return "heal_aoe";
        case BotCombatActionCategory::ExternalDefensive: return "external_defensive";
        case BotCombatActionCategory::ResurrectRecover: return "resurrect_recover";
        case BotCombatActionCategory::Loot: return "loot";
        case BotCombatActionCategory::QuestInteract: return "quest_interact";
        case BotCombatActionCategory::UseItem: return "use_item";
        case BotCombatActionCategory::EmoteMechanic: return "emote_mechanic";
        case BotCombatActionCategory::ProfessionAction: return "profession_action";
        case BotCombatActionCategory::ResourceGenerator: return "resource_generator";
        default: return "wait";
    }
}

BotCombatActionCategory BotCombatActionCatalog::CategoryFromString(std::string const& value)
{
#define MAP_CATEGORY(name, enumValue) if (value == name) return BotCombatActionCategory::enumValue
    MAP_CATEGORY("movement", Movement);
    MAP_CATEGORY("wait", Wait);
    MAP_CATEGORY("target_select", TargetSelect);
    MAP_CATEGORY("target_switch", TargetSwitch);
    MAP_CATEGORY("auto_attack", AutoAttack);
    MAP_CATEGORY("builder", Builder);
    MAP_CATEGORY("spender", Spender);
    MAP_CATEGORY("dot", Dot);
    MAP_CATEGORY("buff", Buff);
    MAP_CATEGORY("debuff", Debuff);
    MAP_CATEGORY("interrupt", Interrupt);
    MAP_CATEGORY("stun_cc", StunCc);
    MAP_CATEGORY("defensive", Defensive);
    MAP_CATEGORY("offensive_cooldown", OffensiveCooldown);
    MAP_CATEGORY("execute", Execute);
    MAP_CATEGORY("aoe", Aoe);
    MAP_CATEGORY("cleave", Cleave);
    MAP_CATEGORY("dispel_cleanse", DispelCleanse);
    MAP_CATEGORY("taunt", Taunt);
    MAP_CATEGORY("threat_build", ThreatBuild);
    MAP_CATEGORY("mitigation", Mitigation);
    MAP_CATEGORY("heal_efficient", HealEfficient);
    MAP_CATEGORY("heal_fast", HealFast);
    MAP_CATEGORY("heal_aoe", HealAoe);
    MAP_CATEGORY("external_defensive", ExternalDefensive);
    MAP_CATEGORY("resurrect_recover", ResurrectRecover);
    MAP_CATEGORY("loot", Loot);
    MAP_CATEGORY("quest_interact", QuestInteract);
    MAP_CATEGORY("use_item", UseItem);
    MAP_CATEGORY("emote_mechanic", EmoteMechanic);
    MAP_CATEGORY("profession_action", ProfessionAction);
    MAP_CATEGORY("resource_generator", ResourceGenerator);
#undef MAP_CATEGORY
    return BotCombatActionCategory::Wait;
}

uint32 BotCombatActionCatalog::StableActionId(BotCombatActionCategory category, uint32 concreteId)
{
    return (uint32(category) + 1u) * 100000u + concreteId;
}

BotCombatActionDefinition BotCombatActionCatalog::Get(BotCombatActionCategory category, uint32 concreteId)
{
    BotCombatActionDefinition def;
    def.Id = StableActionId(category, concreteId);
    def.Category = category;
    def.Name = ToString(category);
    def.SemanticFamily = def.Name;
    return def;
}

std::vector<BotCombatActionDefinition> BotCombatActionCatalog::BaseTaxonomy()
{
    std::vector<BotCombatActionDefinition> result;
    for (uint8 i = uint8(BotCombatActionCategory::Movement); i <= uint8(BotCombatActionCategory::ResourceGenerator); ++i)
        result.push_back(Get(BotCombatActionCategory(i)));
    return result;
}

std::string BotCombatActionCatalog::TaxonomyJson()
{
    std::ostringstream json;
    json << "[";
    bool first = true;
    for (BotCombatActionDefinition const& def : BaseTaxonomy())
    {
        if (!first)
            json << ",";
        first = false;
        json << "{\"action_id\":" << def.Id
             << ",\"category\":\"" << CombatCatalogEscape(ToString(def.Category)) << "\""
             << ",\"semantic_family\":\"" << CombatCatalogEscape(def.SemanticFamily) << "\"}";
    }
    json << "]";
    return json.str();
}
