#include "Bots/BotMemberInstanceState.h"

#include "Bots/BotMgr.h"
#include "Item.h"
#include "ObjectGuid.h"
#include "Player.h"

namespace BotMemberInstanceState
{
Reading Read(Player const* bot)
{
    Reading reading;
    if (!bot)
        return reading;
    reading.Loaded = true;
    reading.InstanceValid = bot->m_InstanceValid;
    reading.HomebindTimerMs = bot->m_HomebindTimer;
    std::vector<Durability> items;
    for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
        if (Item const* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
            items.push_back({ item->GetUInt32Value(ITEM_FIELD_DURABILITY),
                item->GetUInt32Value(ITEM_FIELD_MAXDURABILITY) });
    reading.DurabilityKnown = MinDurabilityFraction(items, reading.MinDurability);
    return reading;
}

std::string MemberObjectJson(Player const* bot)
{
    return ObjectJson(Read(bot));
}

std::string RosterFieldsJson(uint32 guidCounter)
{
    // The same lookup as BotWorldPopulationMgr::GetLoadedBot.
    return FieldsJson(Read(guidCounter
        ? sBotMgr->GetLoadedPlayer(ObjectGuid(HighGuid::Player, guidCounter)) : nullptr));
}
}
