#include "Bots/BotWorldPopulationMgr.h"

#include "Cryptography/CryptoHash.h"
#include "DataStores/DBCStores.h"
#include "Entities/Item/Item.h"
#include "Player.h"

#include <algorithm>
#include <cctype>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

bool BotWorldPopulationMgr::ObserveEquippedGearIdentity(Player const* bot,
    std::vector<RaidRosterItemIdentity>& manifest,
    std::string& manifestSha256) const
{
    manifest.clear();
    manifestSha256.clear();
    if (!bot)
        return false;

    for (uint8 equipmentSlot = EQUIPMENT_SLOT_START;
        equipmentSlot < EQUIPMENT_SLOT_END; ++equipmentSlot)
    {
        Item const* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, equipmentSlot);
        if (!item)
            continue;

        RaidRosterItemIdentity row;
        row.Slot = equipmentSlot;
        row.Entry = item->GetEntry();
        row.EnchantId = item->GetEnchantmentId(PERM_ENCHANTMENT_SLOT);
        row.ReforgeId = item->GetEnchantmentId(REFORGE_ENCHANTMENT_SLOT);
        for (uint8 gemSlot = 0; gemSlot < MAX_GEM_SOCKETS; ++gemSlot)
        {
            uint32 gemItemId = 0;
            uint32 const gemEnchantId = item->GetEnchantmentId(
                EnchantmentSlot(SOCK_ENCHANTMENT_SLOT + gemSlot));
            if (SpellItemEnchantmentEntry const* enchant =
                sSpellItemEnchantmentStore.LookupEntry(gemEnchantId))
                gemItemId = enchant->Src_itemID;
            row.GemItemIds.push_back(gemItemId);
        }
        while (!row.GemItemIds.empty() && row.GemItemIds.back() == 0)
            row.GemItemIds.pop_back();
        manifest.push_back(std::move(row));
    }

    // Match Python canonical_sha256(canonical_gear_manifest): dictionary keys
    // are lexicographically sorted and no insignificant whitespace is present.
    std::ostringstream canonical;
    canonical << '[';
    for (size_t index = 0; index < manifest.size(); ++index)
    {
        if (index)
            canonical << ',';
        RaidRosterItemIdentity const& row = manifest[index];
        canonical << "{\"enchant_id\":" << row.EnchantId
                  << ",\"gem_item_ids\":[";
        for (size_t gemIndex = 0; gemIndex < row.GemItemIds.size(); ++gemIndex)
        {
            if (gemIndex)
                canonical << ',';
            canonical << row.GemItemIds[gemIndex];
        }
        canonical << "],\"item_id\":" << row.Entry
                  << ",\"reforge_id\":" << row.ReforgeId
                  << ",\"slot\":" << uint32(row.Slot) << '}';
    }
    canonical << ']';
    manifestSha256 = ByteArrayToHexStr(
        Trinity::Crypto::SHA256::GetDigestOf(canonical.str()));
    std::transform(manifestSha256.begin(), manifestSha256.end(),
        manifestSha256.begin(),
        [](unsigned char c) { return char(std::tolower(c)); });
    return manifest.size() >= 16;
}

bool BotWorldPopulationMgr::EquippedGearManifestsEqual(
    std::vector<RaidRosterItemIdentity> const& left,
    std::vector<RaidRosterItemIdentity> const& right) const
{
    if (left.size() != right.size())
        return false;
    for (size_t index = 0; index < left.size(); ++index)
    {
        RaidRosterItemIdentity const& lhs = left[index];
        RaidRosterItemIdentity const& rhs = right[index];
        if (lhs.Slot != rhs.Slot || lhs.Entry != rhs.Entry
            || lhs.EnchantId != rhs.EnchantId
            || lhs.ReforgeId != rhs.ReforgeId
            || lhs.GemItemIds != rhs.GemItemIds)
            return false;
    }
    return true;
}

