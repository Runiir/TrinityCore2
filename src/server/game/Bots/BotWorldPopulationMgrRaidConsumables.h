#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_RAID_CONSUMABLES_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_RAID_CONSUMABLES_H

#include <cstdint>
#include <string_view>

namespace BotWorldPopulationMgrRaidConsumables
{
struct Contract
{
    char const* ClassSpec = nullptr;
    uint32_t FlaskItemId = 0;
    uint32_t FlaskItemSpellId = 0;
    uint32_t FlaskAuraSpellId = 0;
    uint32_t FoodItemId = 0;
    uint32_t FoodItemSpellId = 0;
    uint32_t FoodAuraSpellId = 0;
    uint32_t PrepotItemId = 0;
    uint32_t PrepotItemSpellId = 0;
    uint32_t PrepotAuraSpellId = 0;
    uint32_t CombatPotionItemId = 0;
    uint32_t CombatPotionItemSpellId = 0;
    uint32_t CombatPotionAuraSpellId = 0;
};

Contract const* FindContract(std::string_view classSpec);
}

#endif
