#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_CONSUMABLES_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_CONSUMABLES_H

#include "Define.h"

class Item;
class Player;

namespace BotWorldPopulationMgrConsumables
{
Item* FindNativeConsumable(Player* player, uint32 itemId, uint32 spellId);
uint32 CountNativeConsumable(Player* player, uint32 itemId);
}

#endif
