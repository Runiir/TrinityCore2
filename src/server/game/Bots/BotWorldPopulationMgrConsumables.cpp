#include "Bots/BotWorldPopulationMgrConsumables.h"

#include "Bag.h"
#include "Item.h"
#include "ItemTemplate.h"
#include "Player.h"

namespace BotWorldPopulationMgrConsumables
{
Item* FindNativeConsumable(Player* player, uint32 itemId, uint32 spellId)
{
    if (!player || !itemId || !spellId)
        return nullptr;

    auto matches = [itemId, spellId](Item* item)
    {
        ItemTemplate const* itemTemplate = item ? item->GetTemplate() : nullptr;
        if (!itemTemplate || item->GetEntry() != itemId || !item->GetCount())
            return false;
        for (ItemEffect const& effect : itemTemplate->Effects)
            if (effect.SpellID == int32(spellId)
                && effect.Trigger == ITEM_SPELLTRIGGER_ON_USE)
                return true;
        return false;
    };

    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        if (Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot); matches(item))
            return item;
    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        if (Bag* bag = player->GetBagByPos(bagSlot))
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                if (Item* item = bag->GetItemByPos(slot); matches(item))
                    return item;
    return nullptr;
}

uint32 CountNativeConsumable(Player* player, uint32 itemId)
{
    if (!player || !itemId)
        return 0;
    uint32 count = 0;
    auto add = [&count, itemId](Item* item)
    {
        if (item && item->GetEntry() == itemId)
            count += item->GetCount();
    };
    for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        add(player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot));
    for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        if (Bag* bag = player->GetBagByPos(bagSlot))
            for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                add(bag->GetItemByPos(slot));
    return count;
}
}
