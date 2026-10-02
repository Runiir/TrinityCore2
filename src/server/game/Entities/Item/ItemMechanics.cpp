/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#include "Item.h"
#include "Bag.h"
#include "Common.h"
#include "ConditionMgr.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "ItemEnchantmentMgr.h"
#include "Log.h"
#include "LootItemStorage.h"
#include "LootMgr.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "StringConvert.h"
#include "TradeData.h"
#include "UpdateData.h"
#include "World.h"
#include "WorldPacket.h"
#include "WorldSession.h"

bool Item::HasEnchantRequiredSkill(Player const* player) const
{
    // Check all enchants for required skill
    for (uint32 enchant_slot = PERM_ENCHANTMENT_SLOT; enchant_slot < MAX_ENCHANTMENT_SLOT; ++enchant_slot)
    {
        if (enchant_slot > PRISMATIC_ENCHANTMENT_SLOT && enchant_slot < PROP_ENCHANTMENT_SLOT_0)    // not holding enchantment id
            continue;

        if (uint32 enchant_id = GetEnchantmentId(EnchantmentSlot(enchant_slot)))
            if (SpellItemEnchantmentEntry const* enchantEntry = sSpellItemEnchantmentStore.LookupEntry(enchant_id))
                if (enchantEntry->RequiredSkillID && player->GetSkillValue(enchantEntry->RequiredSkillID) < enchantEntry->RequiredSkillRank)
                    return false;
    }

  return true;
}

uint32 Item::GetEnchantRequiredLevel() const
{
    uint32 level = 0;

    // Check all enchants for required level
    for (uint32 enchant_slot = PERM_ENCHANTMENT_SLOT; enchant_slot < MAX_ENCHANTMENT_SLOT; ++enchant_slot)
    {
        if (enchant_slot > PRISMATIC_ENCHANTMENT_SLOT && enchant_slot < PROP_ENCHANTMENT_SLOT_0)    // not holding enchantment id
            continue;

        if (uint32 enchant_id = GetEnchantmentId(EnchantmentSlot(enchant_slot)))
            if (SpellItemEnchantmentEntry const* enchantEntry = sSpellItemEnchantmentStore.LookupEntry(enchant_id))
                if (enchantEntry->MinLevel > level)
                    level = enchantEntry->MinLevel;
    }

    return level;
}

bool Item::IsBoundByEnchant() const
{
    // Check all enchants for soulbound
    for (uint32 enchant_slot = PERM_ENCHANTMENT_SLOT; enchant_slot < MAX_ENCHANTMENT_SLOT; ++enchant_slot)
    {
        if (enchant_slot > PRISMATIC_ENCHANTMENT_SLOT && enchant_slot < PROP_ENCHANTMENT_SLOT_0)    // not holding enchantment id
            continue;

        if (uint32 enchant_id = GetEnchantmentId(EnchantmentSlot(enchant_slot)))
            if (SpellItemEnchantmentEntry const* enchantEntry = sSpellItemEnchantmentStore.LookupEntry(enchant_id))
                if (enchantEntry->GetFlags().HasFlag(SpellItemEnchantmentFlags::Soulbound))
                    return true;
    }

    return false;
}

InventoryResult Item::CanBeMergedPartlyWith(ItemTemplate const* proto) const
{
    // not allow merge looting currently items
    if (m_lootGenerated)
        return EQUIP_ERR_LOOT_GONE;

    // check item type
    if (GetEntry() != proto->GetId())
        return EQUIP_ERR_CANT_STACK;

    // check free space (full stacks can't be target of merge
    if (GetCount() >= proto->GetMaxStackSize())
        return EQUIP_ERR_CANT_STACK;

    return EQUIP_ERR_OK;
}

bool Item::IsFitToSpellRequirements(SpellInfo const* spellInfo) const
{
    ItemTemplate const* proto = GetTemplate();

    bool isEnchantSpell = spellInfo->HasEffect(SPELL_EFFECT_ENCHANT_ITEM) || spellInfo->HasEffect(SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY) || spellInfo->HasEffect(SPELL_EFFECT_ENCHANT_ITEM_PRISMATIC);
    if (spellInfo->EquippedItemClass != -1)                 // -1 == any item class
    {
        if (isEnchantSpell && (spellInfo->EquippedItemClass == ITEM_CLASS_ARMOR ||
            spellInfo->EquippedItemClass == ITEM_CLASS_WEAPON) && proto->IsVellum())
            if (spellInfo->IsAbilityOfSkillType(SKILL_ENCHANTING)) // only for enchanting spells
                return true;

        if (spellInfo->EquippedItemClass != int32(proto->GetClass()))
            return false;                                   //  wrong item class

        if (spellInfo->EquippedItemSubClassMask != 0)        // 0 == any subclass
        {
            if ((spellInfo->EquippedItemSubClassMask & (1 << proto->GetSubClass())) == 0)
                return false;                               // subclass not present in mask
        }
    }

    if (isEnchantSpell && spellInfo->EquippedItemInventoryTypeMask != 0)       // 0 == any inventory type
    {
        // Special case - accept weapon type for main and offhand requirements
        if (proto->GetInventoryType() == INVTYPE_WEAPON &&
            (spellInfo->EquippedItemInventoryTypeMask & (1 << INVTYPE_WEAPONMAINHAND) ||
             spellInfo->EquippedItemInventoryTypeMask & (1 << INVTYPE_WEAPONOFFHAND)))
            return true;
        else if ((spellInfo->EquippedItemInventoryTypeMask & (1 << proto->GetInventoryType())) == 0)
            return false;                                   // inventory type not present in mask
    }

    return true;
}

void Item::SetEnchantment(EnchantmentSlot slot, uint32 id, uint32 duration, uint32 charges, ObjectGuid caster /*= ObjectGuid::Empty*/)
{
    // Better lost small time at check in comparison lost time at item save to DB.
    if ((GetEnchantmentId(slot) == id) && (GetEnchantmentDuration(slot) == duration) && (GetEnchantmentCharges(slot) == charges))
        return;

    Player* owner = GetOwner();
    if (slot < MAX_INSPECTED_ENCHANTMENT_SLOT)
    {
        if (SpellItemEnchantmentEntry const* oldEnchant = sSpellItemEnchantmentStore.LookupEntry(GetEnchantmentId(slot)))
            if (!oldEnchant->GetFlags().HasFlag(SpellItemEnchantmentFlags::DoNotLog))
                owner->GetSession()->SendEnchantmentLog(GetOwnerGUID(), ObjectGuid::Empty, GetEntry(), oldEnchant->ID);

        if (SpellItemEnchantmentEntry const* newEnchant = sSpellItemEnchantmentStore.LookupEntry(id))
            if (!newEnchant->GetFlags().HasFlag(SpellItemEnchantmentFlags::DoNotLog))
                owner->GetSession()->SendEnchantmentLog(GetOwnerGUID(), caster, GetEntry(), id);
    }

    SetUInt32Value(ITEM_FIELD_ENCHANTMENT_1_1 + slot*MAX_ENCHANTMENT_OFFSET + ENCHANTMENT_ID_OFFSET, id);
    SetUInt32Value(ITEM_FIELD_ENCHANTMENT_1_1 + slot*MAX_ENCHANTMENT_OFFSET + ENCHANTMENT_DURATION_OFFSET, duration);
    SetUInt32Value(ITEM_FIELD_ENCHANTMENT_1_1 + slot*MAX_ENCHANTMENT_OFFSET + ENCHANTMENT_CHARGES_OFFSET, charges);
    SetState(ITEM_CHANGED, owner);
}

void Item::SetEnchantmentDuration(EnchantmentSlot slot, uint32 duration, Player* owner)
{
    if (GetEnchantmentDuration(slot) == duration)
        return;

    SetUInt32Value(ITEM_FIELD_ENCHANTMENT_1_1 + slot*MAX_ENCHANTMENT_OFFSET + ENCHANTMENT_DURATION_OFFSET, duration);
    SetState(ITEM_CHANGED, owner);
    // Cannot use GetOwner() here, has to be passed as an argument to avoid freeze due to hashtable locking
}

void Item::SetEnchantmentCharges(EnchantmentSlot slot, uint32 charges)
{
    if (GetEnchantmentCharges(slot) == charges)
        return;

    SetUInt32Value(ITEM_FIELD_ENCHANTMENT_1_1 + slot*MAX_ENCHANTMENT_OFFSET + ENCHANTMENT_CHARGES_OFFSET, charges);
    SetState(ITEM_CHANGED, GetOwner());
}

void Item::ClearEnchantment(EnchantmentSlot slot)
{
    if (!GetEnchantmentId(slot))
        return;

    for (uint8 x = 0; x < MAX_ITEM_ENCHANTMENT_EFFECTS; ++x)
        SetUInt32Value(ITEM_FIELD_ENCHANTMENT_1_1 + slot*MAX_ENCHANTMENT_OFFSET + x, 0);
    SetState(ITEM_CHANGED, GetOwner());
}

bool Item::GemsFitSockets() const
{
    for (uint32 enchant_slot = SOCK_ENCHANTMENT_SLOT; enchant_slot < SOCK_ENCHANTMENT_SLOT+MAX_GEM_SOCKETS; ++enchant_slot)
    {
        uint8 SocketColor = GetTemplate()->GetSocketColor(enchant_slot - SOCK_ENCHANTMENT_SLOT);

        if (!SocketColor) // no socket slot
            continue;

        uint32 enchant_id = GetEnchantmentId(EnchantmentSlot(enchant_slot));
        if (!enchant_id) // no gems on this socket
            return false;

        SpellItemEnchantmentEntry const* enchantEntry = sSpellItemEnchantmentStore.LookupEntry(enchant_id);
        if (!enchantEntry) // invalid gem id on this socket
            return false;

        uint8 GemColor = 0;

        uint32 gemid = enchantEntry->Src_itemID;
        if (gemid)
        {
            ItemTemplate const* gemProto = sObjectMgr->GetItemTemplate(gemid);
            if (gemProto)
            {
                GemPropertiesEntry const* gemProperty = sGemPropertiesStore.LookupEntry(gemProto->GetGemProperties());
                if (gemProperty)
                    GemColor = gemProperty->Type;
            }
        }

        if (!(GemColor & SocketColor)) // bad gem color on this socket
            return false;
    }
    return true;
}

uint8 Item::GetGemCountWithID(uint32 GemID) const
{
    uint8 count = 0;
    for (uint32 enchant_slot = SOCK_ENCHANTMENT_SLOT; enchant_slot < SOCK_ENCHANTMENT_SLOT+MAX_GEM_SOCKETS; ++enchant_slot)
    {
        uint32 enchant_id = GetEnchantmentId(EnchantmentSlot(enchant_slot));
        if (!enchant_id)
            continue;

        SpellItemEnchantmentEntry const* enchantEntry = sSpellItemEnchantmentStore.LookupEntry(enchant_id);
        if (!enchantEntry)
            continue;

        if (GemID == enchantEntry->Src_itemID)
            ++count;
    }
    return count;
}

uint8 Item::GetGemCountWithLimitCategory(uint32 limitCategory) const
{
    uint8 count = 0;
    for (uint32 enchant_slot = SOCK_ENCHANTMENT_SLOT; enchant_slot < SOCK_ENCHANTMENT_SLOT+MAX_GEM_SOCKETS; ++enchant_slot)
    {
        uint32 enchant_id = GetEnchantmentId(EnchantmentSlot(enchant_slot));
        if (!enchant_id)
            continue;

        SpellItemEnchantmentEntry const* enchantEntry = sSpellItemEnchantmentStore.LookupEntry(enchant_id);
        if (!enchantEntry)
            continue;

        ItemTemplate const* gemProto = sObjectMgr->GetItemTemplate(enchantEntry->Src_itemID);
        if (!gemProto)
            continue;

        if (gemProto->GetItemLimitCategory() == limitCategory)
            ++count;
    }
    return count;
}

bool Item::IsLimitedToAnotherMapOrZone(uint32 cur_mapId, uint32 cur_zoneId) const
{
    ItemTemplate const* proto = GetTemplate();
    return proto && ((proto->GetMap() && proto->GetMap() != cur_mapId) || (proto->GetArea() && proto->GetArea() != cur_zoneId));
}

void Item::SendUpdateSockets()
{
    WorldPacket data(SMSG_SOCKET_GEMS_RESULT, 8+4+4+4+4);
    data << uint64(GetGUID());
    for (uint32 i = SOCK_ENCHANTMENT_SLOT; i <= BONUS_ENCHANTMENT_SLOT; ++i)
        data << uint32(GetEnchantmentId(EnchantmentSlot(i)));

    GetOwner()->SendDirectMessage(&data);
}

// Though the client has the information in the item's data field,
// we have to send SMSG_ITEM_TIME_UPDATE to display the remaining
// time.
void Item::SendTimeUpdate(Player* owner)
{
    uint32 duration = GetUInt32Value(ITEM_FIELD_DURATION);
    if (!duration)
        return;

    WorldPacket data(SMSG_ITEM_TIME_UPDATE, (8+4));
    data << uint64(GetGUID());
    data << uint32(duration);
    owner->SendDirectMessage(&data);
}

Item* Item::CreateItem(uint32 itemEntry, uint32 count, Player const* player /*= nullptr*/)
{
    if (count < 1)
        return nullptr;                                        //don't create item at zero count

    ItemTemplate const* proto = sObjectMgr->GetItemTemplate(itemEntry);
    if (proto)
    {
        if (count > proto->GetMaxStackSize())
            count = proto->GetMaxStackSize();

        ASSERT(count != 0 && "pProto->Stackable == 0 but checked at loading already");

        Item* item = NewItemOrBag(proto);
        if (item->Create(sObjectMgr->GetGenerator<HighGuid::Item>().Generate(), itemEntry, player))
        {
            item->SetCount(count);
            return item;
        }
        else
            delete item;
    }
    else
        ABORT();
    return nullptr;
}

Item* Item::CloneItem(uint32 count, Player const* player /*= nullptr*/) const
{
    Item* newItem = CreateItem(GetEntry(), count, player);
    if (!newItem)
        return nullptr;

    newItem->SetGuidValue(ITEM_FIELD_CREATOR,        GetGuidValue(ITEM_FIELD_CREATOR));
    newItem->SetGuidValue(ITEM_FIELD_GIFTCREATOR,    GetGuidValue(ITEM_FIELD_GIFTCREATOR));
    newItem->SetUInt32Value(ITEM_FIELD_FLAGS,        GetUInt32Value(ITEM_FIELD_FLAGS) & ~(ITEM_FIELD_FLAG_REFUNDABLE | ITEM_FIELD_FLAG_BOP_TRADEABLE));
    newItem->SetUInt32Value(ITEM_FIELD_DURATION,     GetUInt32Value(ITEM_FIELD_DURATION));
    // player CAN be nullptr in which case we must not update random properties because that accesses player's item update queue
    if (player)
        newItem->SetItemRandomProperties(GetItemRandomEnchantmentId());
    return newItem;
}

bool Item::IsBindedNotWith(Player const* player) const
{
    // not binded item
    if (!IsSoulBound())
        return false;

    // own item
    if (GetOwnerGUID() == player->GetGUID())
        return false;

    if (HasFlag(ITEM_FIELD_FLAGS, ITEM_FIELD_FLAG_BOP_TRADEABLE))
        if (allowedGUIDs.find(player->GetGUID()) != allowedGUIDs.end())
            return false;

    // BOA item case
    if (IsBoundAccountWide())
        return false;

    return true;
}

void Item::BuildUpdate(UpdateDataMapType& data_map)
{
    if (Player* owner = GetOwner())
        BuildFieldsUpdate(owner, data_map);
    ClearUpdateMask(false);
}

bool Item::AddToObjectUpdate()
{
    if (Player* owner = GetOwner())
    {
        owner->GetMap()->AddUpdateObject(this);
        return true;
    }

    return false;
}

void Item::RemoveFromObjectUpdate()
{
    if (Player* owner = GetOwner())
        owner->GetMap()->RemoveUpdateObject(this);
}

void Item::SaveRefundDataToDB()
{
    CharacterDatabaseTransaction trans = CharacterDatabase.BeginTransaction();

    CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_ITEM_REFUND_INSTANCE);
    stmt->setUInt32(0, GetGUID().GetCounter());
    trans->Append(stmt);

    stmt = CharacterDatabase.GetPreparedStatement(CHAR_INS_ITEM_REFUND_INSTANCE);
    stmt->setUInt32(0, GetGUID().GetCounter());
    stmt->setUInt32(1, GetRefundRecipient());
    stmt->setUInt32(2, GetPaidMoney());
    stmt->setUInt16(3, uint16(GetPaidExtendedCost()));
    trans->Append(stmt);

    CharacterDatabase.CommitTransaction(trans);
}

void Item::DeleteRefundDataFromDB(CharacterDatabaseTransaction* trans)
{
    if (trans)
    {
        CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_ITEM_REFUND_INSTANCE);
        stmt->setUInt32(0, GetGUID().GetCounter());
        (*trans)->Append(stmt);

    }
}

void Item::SetNotRefundable(Player* owner, bool changestate /*= true*/, CharacterDatabaseTransaction* trans /*=nullptr*/)
{
    if (!HasFlag(ITEM_FIELD_FLAGS, ITEM_FIELD_FLAG_REFUNDABLE))
        return;

    RemoveFlag(ITEM_FIELD_FLAGS, ITEM_FIELD_FLAG_REFUNDABLE);
    // Following is not applicable in the trading procedure
    if (changestate)
        SetState(ITEM_CHANGED, owner);

    SetRefundRecipient(0);
    SetPaidMoney(0);
    SetPaidExtendedCost(0);
    DeleteRefundDataFromDB(trans);

    owner->DeleteRefundReference(GetGUID());
}

void Item::UpdatePlayedTime(Player* owner)
{
    // Check if the refund timer has expired yet
    if (GetPlayedTime(owner) <= 2 * HOUR)
        return;

    // Flag as changed to get saved to DB
    SetState(ITEM_CHANGED, owner);
    SetNotRefundable(owner);
}

uint32 Item::GetPlayedTime(Player const* owner) const
{
    return owner->GetTotalPlayedTime() - GetUInt32Value(ITEM_FIELD_CREATE_PLAYED_TIME);
}

bool Item::IsRefundExpired(Player const* owner) const
{
    return (GetPlayedTime(owner) > 2 * HOUR);
}

void Item::SetSoulboundTradeable(GuidSet const& allowedLooters)
{
    SetFlag(ITEM_FIELD_FLAGS, ITEM_FIELD_FLAG_BOP_TRADEABLE);
    allowedGUIDs = allowedLooters;
}

void Item::ClearSoulboundTradeable(Player* currentOwner)
{
    RemoveFlag(ITEM_FIELD_FLAGS, ITEM_FIELD_FLAG_BOP_TRADEABLE);
    if (allowedGUIDs.empty())
        return;

    allowedGUIDs.clear();
    SetState(ITEM_CHANGED, currentOwner);
    CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_ITEM_BOP_TRADE);
    stmt->setUInt32(0, GetGUID().GetCounter());
    CharacterDatabase.Execute(stmt);
}

bool Item::CheckSoulboundTradeExpire()
{
    // called from owner's update - GetOwner() MUST be valid
    if (GetUInt32Value(ITEM_FIELD_CREATE_PLAYED_TIME) + 2*HOUR < GetOwner()->GetTotalPlayedTime())
    {
        ClearSoulboundTradeable(GetOwner());
        return true; // remove from tradeable list
    }

    return false;
}

bool Item::CanBeTransmogrified() const
{
    ItemTemplate const* proto = GetTemplate();

    if (!proto)
        return false;

    if (proto->GetQuality() == ITEM_QUALITY_LEGENDARY)
        return false;

    if (proto->GetClass() != ITEM_CLASS_ARMOR &&
        proto->GetClass() != ITEM_CLASS_WEAPON)
        return false;

    if (proto->GetClass() == ITEM_CLASS_WEAPON && proto->GetSubClass() == ITEM_SUBCLASS_WEAPON_FISHING_POLE)
        return false;

    if (proto->GetFlags2() & ITEM_FLAG2_NO_ALTER_ITEM_VISUAL)
        return false;

    if (!HasStats())
        return false;

    return true;
}

bool Item::CanTransmogrify() const
{
    ItemTemplate const* proto = GetTemplate();

    if (!proto)
        return false;

    if (proto->GetFlags2() & ITEM_FLAG2_NO_SOURCE_FOR_ITEM_VISUAL)
        return false;

    if (proto->GetQuality() == ITEM_QUALITY_LEGENDARY)
        return false;

    if (proto->GetClass() != ITEM_CLASS_ARMOR &&
        proto->GetClass() != ITEM_CLASS_WEAPON)
        return false;

    if (proto->GetClass() == ITEM_CLASS_WEAPON && proto->GetSubClass() == ITEM_SUBCLASS_WEAPON_FISHING_POLE)
        return false;

    if (proto->GetFlags2() & ITEM_FLAG2_IGNORE_QUALITY_FOR_ITEM_VISUAL_SOURCE)
        return true;

    if (!HasStats())
        return false;

    return true;
}

// Based on client function CheckTransmogrificationQualityAndClass (build 15595)
inline bool CheckTransmogrificationQualityAndClass(ItemTemplate const* sourceItem)
{
    // Only weapons and armor can be transmogrified
    if (sourceItem->GetClass() != ITEM_CLASS_WEAPON && sourceItem->GetClass() != ITEM_CLASS_ARMOR)
        return false;

    // Legendary items cannot be transmogrified
    if (sourceItem->GetQuality() == ITEM_QUALITY_LEGENDARY)
        return false;

    // Fishing poles cannot be transmogrified
    if (sourceItem->GetClass() == ITEM_CLASS_WEAPON && sourceItem->GetSubClass() == ITEM_SUBCLASS_WEAPON_FISHING_POLE)
        return false;

    return true;
}

bool Item::CanTransmogrifyItemWithItem(Item const* transmogrified, Item const* transmogrifier)
{
    if (!transmogrifier || !transmogrified)
        return false;

    ItemTemplate const* sourceItem = transmogrifier->GetTemplate(); // source
    ItemTemplate const* targetItem = transmogrified->GetTemplate(); // dest

    // check source item's validity. The client does check these conditions so we should do as well.
    if (!CheckTransmogrificationQualityAndClass(sourceItem))
        return false;

    if (sourceItem->GetId() == targetItem->GetId())
        return false;

    if (!transmogrified->CanTransmogrify() || !transmogrifier->CanBeTransmogrified())
        return false;

    // Check items which can never be transmogrified.
    if (sourceItem->GetInventoryType() == INVTYPE_BAG ||
        sourceItem->GetInventoryType() == INVTYPE_RELIC ||
        sourceItem->GetInventoryType() == INVTYPE_BODY ||
        sourceItem->GetInventoryType() == INVTYPE_FINGER ||
        sourceItem->GetInventoryType() == INVTYPE_TRINKET ||
        sourceItem->GetInventoryType() == INVTYPE_AMMO ||
        sourceItem->GetInventoryType() == INVTYPE_QUIVER)
        return false;

    if (sourceItem->GetSubClass() != targetItem->GetSubClass() && (sourceItem->GetClass() != ITEM_CLASS_WEAPON || !sourceItem->IsRangedWeapon() || !targetItem->IsRangedWeapon()))
        return false;

    if (sourceItem->GetInventoryType() != targetItem->GetInventoryType() &&
        (sourceItem->GetClass() != ITEM_CLASS_WEAPON || (targetItem->GetInventoryType() != INVTYPE_WEAPONMAINHAND && targetItem->GetInventoryType() != INVTYPE_WEAPONOFFHAND)) &&
        (sourceItem->GetClass() != ITEM_CLASS_ARMOR || (sourceItem->GetInventoryType() != INVTYPE_CHEST && targetItem->GetInventoryType() != INVTYPE_ROBE && sourceItem->GetInventoryType() != INVTYPE_ROBE && targetItem->GetInventoryType() != INVTYPE_CHEST)))
        return false;

    return true;
}

bool Item::HasStats() const
{
    if (GetItemRandomPropertyId() != 0)
        return true;

    ItemTemplate const* proto = GetTemplate();
    for (uint8 i = 0; i < MAX_ITEM_PROTO_STATS; ++i)
        if (proto->GetItemStatValue(i) != 0)
            return true;

    return false;
}

// used by mail items, transmog cost, stationeryinfo and others
uint32 Item::GetSellPrice(ItemTemplate const* proto, bool& normalSellPrice)
{
    normalSellPrice = true;

    if (proto->GetFlags2() & ITEM_FLAG2_OVERRIDE_GOLD_COST)
    {
        return proto->GetBuyPrice();
    }
    else
    {
        ImportPriceQualityEntry const* qualityPrice = sImportPriceQualityStore.LookupEntry(proto->GetQuality() + 1);
        ItemPriceBaseEntry const* basePrice = sItemPriceBaseStore.LookupEntry(proto->GetBaseItemLevel());

        if (!qualityPrice || !basePrice)
            return 0;

        float qualityFactor = qualityPrice->Factor;
        float baseFactor = 0.0f;

        uint32 inventoryType = proto->GetInventoryType();

        if (inventoryType == INVTYPE_WEAPON ||
            inventoryType == INVTYPE_2HWEAPON ||
            inventoryType == INVTYPE_WEAPONMAINHAND ||
            inventoryType == INVTYPE_WEAPONOFFHAND ||
            inventoryType == INVTYPE_RANGED ||
            inventoryType == INVTYPE_THROWN ||
            inventoryType == INVTYPE_RANGEDRIGHT)
            baseFactor = basePrice->Weapon;
        else
            baseFactor = basePrice->Armor;

        if (inventoryType == INVTYPE_ROBE)
            inventoryType = INVTYPE_CHEST;

        float typeFactor = 0.0f;
        int8 weapType = -1;

        switch (inventoryType)
        {
            case INVTYPE_HEAD:
            case INVTYPE_SHOULDERS:
            case INVTYPE_CHEST:
            case INVTYPE_WAIST:
            case INVTYPE_LEGS:
            case INVTYPE_FEET:
            case INVTYPE_WRISTS:
            case INVTYPE_HANDS:
            case INVTYPE_CLOAK:
            {
                ImportPriceArmorEntry const* armorPrice = sImportPriceArmorStore.LookupEntry(inventoryType);
                if (!armorPrice)
                    return 0;

                switch (proto->GetSubClass())
                {
                    case ITEM_SUBCLASS_ARMOR_MISCELLANEOUS:
                    case ITEM_SUBCLASS_ARMOR_CLOTH:
                        typeFactor = armorPrice->ClothModifier;
                        break;
                    case ITEM_SUBCLASS_ARMOR_LEATHER:
                        typeFactor = armorPrice->LeatherModifier;
                        break;
                    case ITEM_SUBCLASS_ARMOR_MAIL:
                        typeFactor = armorPrice->ChainModifier;
                        break;
                    case ITEM_SUBCLASS_ARMOR_PLATE:
                        typeFactor = armorPrice->PlateModifier;
                        break;
                    default:
                        return 0;
                }

                break;
            }
            case INVTYPE_SHIELD:
            {
                ImportPriceShieldEntry const* shieldPrice = sImportPriceShieldStore.LookupEntry(1); // it only has two rows, it's unclear which is the one used
                if (!shieldPrice)
                    return 0;

                typeFactor = shieldPrice->Data;
                break;
            }
            case INVTYPE_WEAPONMAINHAND:
                weapType = 0;
                break;
            case INVTYPE_WEAPONOFFHAND:
                weapType = 1;
                break;
            case INVTYPE_WEAPON:
                weapType = 2;
                break;
            case INVTYPE_2HWEAPON:
                weapType = 3;
                break;
            case INVTYPE_RANGED:
            case INVTYPE_RANGEDRIGHT:
            case INVTYPE_RELIC:
                weapType = 4;
                break;
            default:
                return proto->GetBuyPrice();
        }

        if (weapType != -1)
        {
            ImportPriceWeaponEntry const* weaponPrice = sImportPriceWeaponStore.LookupEntry(weapType + 1);
            if (!weaponPrice)
                return 0;

            typeFactor = weaponPrice->Data;
        }

        normalSellPrice = false;
        return uint32(qualityFactor * proto->GetPriceRandomValue() * proto->GetPriceVariance() * typeFactor * baseFactor);
    }
}

uint32 Item::GetSpecialPrice(ItemTemplate const* proto, uint32 minimumPrice /*= 10000*/)
{
    uint32 cost = 0;

    if (proto->GetFlags2() & ITEM_FLAG2_OVERRIDE_GOLD_COST)
        cost = proto->GetSellPrice();
    else
    {
        bool normalPrice;
        cost = Item::GetSellPrice(proto, normalPrice);

        if (!normalPrice)
        {
            if (proto->GetBuyCount() <= 1)
            {
                ItemClassEntry const* classEntry = sItemClassStore.LookupEntry(proto->GetClass());
                if (classEntry)
                    cost *= classEntry->PriceModifier;
                else
                    cost = 0;
            }
            else
                cost /= 4 * proto->GetBuyCount();
        }
        else
            cost = proto->GetSellPrice();
    }

    if (cost < minimumPrice)
        cost = minimumPrice;

    return cost;
}

int32 Item::GetReforgableStat(ItemModType statType) const
{
    ItemTemplate const* proto = GetTemplate();
    for (uint32 i = 0; i < MAX_ITEM_PROTO_STATS; ++i)
        if (ItemModType(proto->GetItemStatType(i)) == statType)
            return proto->GetItemStatValue(i);

    int32 randomPropId = GetItemRandomPropertyId();
    if (!randomPropId)
        return 0;

    if (randomPropId < 0)
    {
        ItemRandomSuffixEntry const* randomSuffix = sItemRandomSuffixStore.LookupEntry(-randomPropId);
        if (!randomSuffix)
            return 0;

        for (uint32 e = PROP_ENCHANTMENT_SLOT_0; e <= PROP_ENCHANTMENT_SLOT_4; ++e)
            if (SpellItemEnchantmentEntry const* enchant = sSpellItemEnchantmentStore.LookupEntry(GetEnchantmentId(EnchantmentSlot(e))))
                for (uint32 f = 0; f < MAX_ITEM_ENCHANTMENT_EFFECTS; ++f)
                    if (enchant->Effect[f] == ITEM_ENCHANTMENT_TYPE_STAT && ItemModType(enchant->EffectArg[f]) == statType)
                        for (int k = 0; k < 5; ++k)
                            if (randomSuffix->Enchantment[k] == enchant->ID)
                                return int32((randomSuffix->AllocationPct[k] * GetItemSuffixFactor()) / 10000);
    }
    else
    {
        ItemRandomPropertiesEntry const* randomProp = sItemRandomPropertiesStore.LookupEntry(randomPropId);
        if (!randomProp)
            return 0;

        for (uint32 e = PROP_ENCHANTMENT_SLOT_0; e <= PROP_ENCHANTMENT_SLOT_4; ++e)
            if (SpellItemEnchantmentEntry const* enchant = sSpellItemEnchantmentStore.LookupEntry(GetEnchantmentId(EnchantmentSlot(e))))
                for (uint32 f = 0; f < MAX_ITEM_ENCHANTMENT_EFFECTS; ++f)
                    if (enchant->Effect[f] == ITEM_ENCHANTMENT_TYPE_STAT && ItemModType(enchant->EffectArg[f]) == statType)
                        for (int k = 0; k < MAX_ITEM_ENCHANTMENT_EFFECTS; ++k)
                            if (randomProp->Enchantment[k] == enchant->ID)
                                return int32(enchant->EffectPointsMin[k]);
    }

    return 0;
}

void Item::SetCount(uint32 value)
{
    SetUInt32Value(ITEM_FIELD_STACK_COUNT, value);

    if (Player* player = GetOwner())
    {
        if (TradeData* tradeData = player->GetTradeData())
        {
            TradeSlots slot = tradeData->GetTradeSlotForItem(GetGUID());

            if (slot != TRADE_SLOT_INVALID)
                tradeData->SetItem(slot, this, true);
        }
    }
}
