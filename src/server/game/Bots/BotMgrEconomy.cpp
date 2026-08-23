#include "Bots/BotMgr.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Chat.h"
#include "Config.h"
#include "DataStores/DBCStores.h"
#include "DataStores/DBCStructure.h"
#include "DatabaseEnv.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "Entities/Unit/CharmInfo.h"
#include "GameClient.h"
#include "Group.h"
#include "GroupMgr.h"
#include "LFG.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Pet.h"
#include "Player.h"
#include "QueryHolder.h"
#include "SpellInfo.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "World.h"
#include "WorldSession.h"
#include <algorithm>
#include <memory>
#include <sstream>

namespace
{
float GetStatWeight(uint8 classId, uint32 statType)
{
    switch (classId)
    {
        case CLASS_WARRIOR:
        case CLASS_DEATH_KNIGHT:
            if (statType == ITEM_MOD_STRENGTH) return 2.0f;
            if (statType == ITEM_MOD_STAMINA) return 1.1f;
            break;
        case CLASS_HUNTER:
        case CLASS_ROGUE:
            if (statType == ITEM_MOD_AGILITY) return 2.0f;
            if (statType == ITEM_MOD_STAMINA) return 0.9f;
            break;
        case CLASS_MAGE:
        case CLASS_PRIEST:
        case CLASS_WARLOCK:
            if (statType == ITEM_MOD_INTELLECT) return 2.0f;
            if (statType == ITEM_MOD_SPIRIT) return 1.0f;
            if (statType == ITEM_MOD_STAMINA) return 0.7f;
            break;
        case CLASS_DRUID:
        case CLASS_SHAMAN:
        case CLASS_PALADIN:
            if (statType == ITEM_MOD_INTELLECT || statType == ITEM_MOD_STRENGTH || statType == ITEM_MOD_AGILITY) return 1.4f;
            if (statType == ITEM_MOD_STAMINA) return 1.0f;
            break;
        default:
            break;
    }

    switch (statType)
    {
        case ITEM_MOD_HIT_RATING:
        case ITEM_MOD_CRIT_RATING:
        case ITEM_MOD_HASTE_RATING:
        case ITEM_MOD_MASTERY_RATING:
            return 1.2f;
        case ITEM_MOD_STAMINA:
            return 0.8f;
        default:
            return 0.25f;
    }
}

float ScoreItemForBot(Player const* bot, ItemTemplate const* proto)
{
    if (!bot || !proto)
        return 0.0f;

    float score = float(proto->GetBaseItemLevel()) * 0.5f;
    for (uint32 i = 0; i < MAX_ITEM_PROTO_STATS; ++i)
    {
        int32 statValue = proto->GetItemStatValue(i);
        if (!statValue)
            continue;

        score += float(statValue) * GetStatWeight(bot->getClass(), uint32(proto->GetItemStatType(i)));
    }

    return score;
}

uint8 GetRepresentativeEquipSlot(uint8 inventoryType)
{
    switch (inventoryType)
    {
        case INVTYPE_HEAD: return EQUIPMENT_SLOT_HEAD;
        case INVTYPE_NECK: return EQUIPMENT_SLOT_NECK;
        case INVTYPE_SHOULDERS: return EQUIPMENT_SLOT_SHOULDERS;
        case INVTYPE_BODY: return EQUIPMENT_SLOT_BODY;
        case INVTYPE_CHEST:
        case INVTYPE_ROBE: return EQUIPMENT_SLOT_CHEST;
        case INVTYPE_WAIST: return EQUIPMENT_SLOT_WAIST;
        case INVTYPE_LEGS: return EQUIPMENT_SLOT_LEGS;
        case INVTYPE_FEET: return EQUIPMENT_SLOT_FEET;
        case INVTYPE_WRISTS: return EQUIPMENT_SLOT_WRISTS;
        case INVTYPE_HANDS: return EQUIPMENT_SLOT_HANDS;
        case INVTYPE_FINGER: return EQUIPMENT_SLOT_FINGER1;
        case INVTYPE_TRINKET: return EQUIPMENT_SLOT_TRINKET1;
        case INVTYPE_CLOAK: return EQUIPMENT_SLOT_BACK;
        case INVTYPE_WEAPON:
        case INVTYPE_2HWEAPON:
        case INVTYPE_WEAPONMAINHAND: return EQUIPMENT_SLOT_MAINHAND;
        case INVTYPE_WEAPONOFFHAND:
        case INVTYPE_SHIELD:
        case INVTYPE_HOLDABLE: return EQUIPMENT_SLOT_OFFHAND;
        case INVTYPE_RANGED:
        case INVTYPE_THROWN:
        case INVTYPE_RANGEDRIGHT:
        case INVTYPE_RELIC: return EQUIPMENT_SLOT_RANGED;
        case INVTYPE_TABARD: return EQUIPMENT_SLOT_TABARD;
        default: return EQUIPMENT_SLOT_END;
    }
}
}

std::map<ObjectGuid, BotActionResult> BotMgr::CraftCookingRecipe(Player* owner, uint32 recipeSpellId, uint32 count, std::string const& selector)
{
    std::map<ObjectGuid, BotActionResult> results;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        Player* bot = FindLoadedPlayer(botGuid);
        results[botGuid] = _executor.CraftRecipe(owner, bot, recipeSpellId, count);
    }

    return results;
}

std::map<ObjectGuid, BotEconomyActionResult> BotMgr::VendorTrash(Player* owner, std::string const& selector)
{
    std::map<ObjectGuid, BotEconomyActionResult> results;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        Player* bot = FindLoadedPlayer(botGuid);
        results[botGuid] = _executor.VendorTrash(owner, bot);
    }

    return results;
}

std::map<ObjectGuid, BotEconomyActionResult> BotMgr::Repair(Player* owner, std::string const& selector)
{
    std::map<ObjectGuid, BotEconomyActionResult> results;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        Player* bot = FindLoadedPlayer(botGuid);
        results[botGuid] = _executor.Repair(owner, bot);
    }

    return results;
}

std::map<ObjectGuid, std::vector<BotGearEvaluation>> BotMgr::EvaluateGear(Player* owner, std::string const& selector) const
{
    std::map<ObjectGuid, std::vector<BotGearEvaluation>> results;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        Player* bot = FindLoadedPlayer(botGuid);
        if (!bot)
            continue;

        std::vector<Item*> items;
        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
            if (Item* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                items.push_back(item);

        for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        {
            if (Bag* bag = bot->GetBagByPos(bagSlot))
                for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                    if (Item* item = bag->GetItemByPos(slot))
                        items.push_back(item);
        }

        std::vector<BotGearEvaluation>& evaluations = results[botGuid];
        for (Item* item : items)
        {
            ItemTemplate const* proto = item->GetTemplate();
            if (!proto || (proto->GetClass() != ITEM_CLASS_ARMOR && proto->GetClass() != ITEM_CLASS_WEAPON))
                continue;

            uint16 equipDest = 0;
            bool canEquip = bot->CanEquipItem(NULL_SLOT, equipDest, item, false) == EQUIP_ERR_OK;
            uint8 representativeSlot = GetRepresentativeEquipSlot(proto->GetInventoryType());
            float equippedScore = 0.0f;
            if (representativeSlot < EQUIPMENT_SLOT_END)
                if (Item* equipped = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, representativeSlot))
                    equippedScore = ScoreItemForBot(bot, equipped->GetTemplate());

            BotGearEvaluation evaluation;
            evaluation.ItemId = item->GetEntry();
            evaluation.Bag = item->GetBagSlot();
            evaluation.Slot = item->GetSlot();
            evaluation.Quality = proto->GetQuality();
            evaluation.InventoryType = proto->GetInventoryType();
            evaluation.Score = ScoreItemForBot(bot, proto);
            evaluation.EquippedScore = equippedScore;

            if (canEquip && representativeSlot < EQUIPMENT_SLOT_END && evaluation.Score > equippedScore + 0.5f)
                evaluation.Decision = "equip";
            else if (proto->GetQuality() == ITEM_QUALITY_POOR || (!canEquip && proto->GetSellPrice() > 0))
                evaluation.Decision = "vendor";
            else
                evaluation.Decision = "keep";

            evaluations.push_back(evaluation);
        }

        std::sort(evaluations.begin(), evaluations.end(), [](BotGearEvaluation const& left, BotGearEvaluation const& right)
        {
            if (left.Decision != right.Decision)
                return left.Decision < right.Decision;
            return left.Score > right.Score;
        });
    }

    return results;
}

bool BotMgr::SetRecording(Player* owner, bool enabled)
{
    bool changed = false;
    for (ObjectGuid botGuid : GetOwnedBots(owner ? owner->GetGUID() : ObjectGuid::Empty))
    {
        if (BotController* controller = GetController(botGuid))
        {
            controller->SetRecording(enabled);
            changed = true;
        }
    }

    return changed;
}

std::string BotMgr::GetStatus(Player* owner) const
{
    std::vector<ObjectGuid> botGuids = GetOwnedBots(owner ? owner->GetGUID() : ObjectGuid::Empty);
    std::ostringstream ss;
    ss << "{\"ok\":true,\"count\":" << botGuids.size() << ",\"bots\":[";
    bool first = true;
    for (ObjectGuid botGuid : botGuids)
    {
        if (BotController const* controller = GetController(botGuid))
        {
            if (!first)
                ss << ',';
            ss << controller->GetStatus(FindLoadedPlayer(controller->GetOwnerGuid()), FindLoadedPlayer(botGuid));
            first = false;
        }
    }

    ss << "],\"failure_reason\":null}";
    return ss.str();
}

char const* BotMgr::GetBotRoleName(ObjectGuid botGuid) const
{
    if (BotController const* controller = GetController(botGuid))
        return ToString(controller->GetRole());

    return "unknown";
}

Player* BotMgr::GetLoadedPlayer(ObjectGuid guid) const
{
    return FindLoadedPlayer(guid);
}

BotRecentEvents BotMgr::ConsumeRecentEvents(ObjectGuid botGuid)
{
    BotRecentEvents events;
    auto itr = _recentEventsByBot.find(botGuid);
    if (itr == _recentEventsByBot.end())
        return events;

    events = itr->second;
    _recentEventsByBot.erase(itr);
    return events;
}
