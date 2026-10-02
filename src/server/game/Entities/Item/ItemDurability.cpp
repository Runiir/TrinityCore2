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
#include "ItemRepairCost.h"
#include "Config.h"
#include "DBCStores.h"
#include "ItemTemplate.h"
#include "World.h"

uint32 Item::CalculateDurabilityRepairCost(float discount) const
{
    uint32 maxDurability = GetUInt32Value(ITEM_FIELD_MAXDURABILITY);
    if (!maxDurability)
        return 0;

    uint32 curDurability = GetUInt32Value(ITEM_FIELD_DURABILITY);
    ASSERT(maxDurability >= curDurability);

    uint32 lostDurability = maxDurability - curDurability;
    if (!lostDurability)
        return 0;

    ItemTemplate const* itemTemplate = GetTemplate();

    DurabilityCostsEntry const* durabilityCost = sDurabilityCostsStore.LookupEntry(itemTemplate->GetBaseItemLevel());
    if (!durabilityCost)
        return 0;

    uint32 durabilityQualityEntryId = (itemTemplate->GetQuality() + 1) * 2;
    DurabilityQualityEntry const* durabilityQualityEntry = sDurabilityQualityStore.LookupEntry(durabilityQualityEntryId);
    if (!durabilityQualityEntry)
        return 0;

    uint32 dmultiplier;
    switch (itemTemplate->GetClass())
    {
        case ITEM_CLASS_WEAPON:
            dmultiplier = durabilityCost->Multiplier[ItemSubClassToDurabilityMultiplierId(itemTemplate->GetClass(), itemTemplate->GetSubClass())];
            break;
        case ITEM_CLASS_ARMOR:
            dmultiplier = durabilityCost->Multiplier[ItemSubClassToDurabilityMultiplierId(itemTemplate->GetClass(), itemTemplate->GetSubClass())];
            break;
        default:
            dmultiplier = 0;
            break;
    }

    return ItemRepairCost::Calculate(lostDurability, dmultiplier, durabilityQualityEntry->Data,
        discount, sWorld->getRate(RATE_REPAIRCOST), sConfigMgr->GetBoolDefault("Client442.RepairCostRounding", false));
}

