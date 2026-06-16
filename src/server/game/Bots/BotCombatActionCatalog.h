#ifndef TRINITY_BOT_COMBAT_ACTION_CATALOG_H
#define TRINITY_BOT_COMBAT_ACTION_CATALOG_H

#include "Define.h"
#include <string>
#include <vector>

enum class BotCombatActionCategory : uint8
{
    Movement,
    Wait,
    TargetSelect,
    TargetSwitch,
    AutoAttack,
    Builder,
    Spender,
    Dot,
    Buff,
    Debuff,
    Interrupt,
    StunCc,
    Defensive,
    OffensiveCooldown,
    Execute,
    Aoe,
    Cleave,
    DispelCleanse,
    Taunt,
    ThreatBuild,
    Mitigation,
    HealEfficient,
    HealFast,
    HealAoe,
    ExternalDefensive,
    ResurrectRecover,
    Loot,
    QuestInteract,
    UseItem,
    EmoteMechanic,
    ProfessionAction
};

struct BotCombatActionDefinition
{
    uint32 Id = 0;
    BotCombatActionCategory Category = BotCombatActionCategory::Wait;
    std::string Name;
    std::string SemanticFamily;
};

class BotCombatActionCatalog
{
public:
    static char const* ToString(BotCombatActionCategory category);
    static BotCombatActionCategory CategoryFromString(std::string const& value);
    static uint32 StableActionId(BotCombatActionCategory category, uint32 concreteId = 0);
    static BotCombatActionDefinition Get(BotCombatActionCategory category, uint32 concreteId = 0);
    static std::vector<BotCombatActionDefinition> BaseTaxonomy();
    static std::string TaxonomyJson();
};

#endif
