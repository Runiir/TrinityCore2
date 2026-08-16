#include "Bots/BotClassSpecActionProfile.h"
#include "Cryptography/CryptoHash.h"
#include "DataStores/DBCStores.h"
#include "DatabaseEnv.h"
#include "Bag.h"
#include "Item.h"
#include "Pet.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Util.h"
#include "Creature.h"
#include "DataStores/DBCEnums.h"
#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>

namespace
{
constexpr uint32 ProfileDarkTransformationSpellId = 63560;

std::string ClassSpecProfileEscape(std::string const& value)
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

char const* PowerName(Powers power)
{
    switch (power)
    {
        case POWER_RAGE: return "rage";
        case POWER_FOCUS: return "focus";
        case POWER_ENERGY: return "energy";
        case POWER_RUNIC_POWER: return "runic_power";
        default: return "mana";
    }
}

bool MaintainedAuraBlocksRefresh(Unit const* target, uint32 auraId, uint32 refreshBelowMs)
{
    Aura const* aura = target && auraId ? target->GetAura(auraId) : nullptr;
    if (!aura)
        return false;
    int32 durationMs = aura->GetDuration();
    return !refreshBelowMs || durationMs < 0 || uint32(durationMs) > refreshBelowMs;
}

bool HasMechanicTag(std::string const& tags, char const* required)
{
    size_t start = 0;
    while (start <= tags.size())
    {
        size_t end = tags.find(',', start);
        if (tags.compare(start, (end == std::string::npos ? tags.size() : end) - start, required) == 0)
            return true;
        if (end == std::string::npos)
            break;
        start = end + 1;
    }
    return false;
}

Item* FindOnUseItemForSpell(Player const* player, uint32 spellId)
{
    if (!player || !spellId)
        return nullptr;

    auto matches = [player, spellId](Item* item) -> bool
    {
        ItemTemplate const* itemTemplate = item ? item->GetTemplate() : nullptr;
        if (!itemTemplate || (item->IsPotion() && player->GetLastPotionId()))
            return false;
        for (uint8 index = 0; index < itemTemplate->Effects.size(); ++index)
        {
            ItemEffect const& effect = itemTemplate->Effects[index];
            if (effect.SpellID == int32(spellId) && effect.Trigger == ITEM_SPELLTRIGGER_ON_USE
                && (!effect.Charges || item->GetSpellCharges(index)
                    || (itemTemplate->GetClass() == ITEM_CLASS_CONSUMABLE && item->GetCount())))
                return true;
        }
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

struct CanonicalRotationKey
{
    uint8 ClassId;
    char const* SpecTag;
    char const* Role;
};

std::array<CanonicalRotationKey, 31> const CanonicalRotationKeys = {{
    { 1, "protection_warrior", "tank" },
    { 2, "protection", "tank" },
    { 6, "blood_death_knight", "tank" },
    { 11, "feral_druid_tank", "tank" },
    { 2, "holy_paladin", "healer" },
    { 5, "discipline_priest", "healer" },
    { 5, "holy_priest", "healer" },
    { 7, "restoration_shaman", "healer" },
    { 11, "restoration_druid", "healer" },
    { 1, "arms_warrior", "dps" },
    { 1, "fury_warrior", "dps" },
    { 2, "retribution_paladin", "dps" },
    { 3, "beast_mastery_hunter", "dps" },
    { 3, "marksmanship", "dps" },
    { 3, "survival", "dps" },
    { 4, "assassination_rogue", "dps" },
    { 4, "combat_rogue", "dps" },
    { 4, "subtlety_rogue", "dps" },
    { 6, "frost_death_knight", "dps" },
    { 6, "unholy_death_knight", "dps" },
    { 7, "elemental_shaman", "dps" },
    { 7, "enhancement", "dps" },
    { 8, "arcane_mage", "dps" },
    { 8, "fire", "dps" },
    { 8, "frost_mage", "dps" },
    { 9, "affliction_warlock", "dps" },
    { 9, "demonology_warlock", "dps" },
    { 9, "destruction_warlock", "dps" },
    { 5, "shadow_priest", "dps" },
    { 11, "balance_druid", "dps" },
    { 11, "feral_druid_dps", "dps" }
}};

struct DbRotationSnapshot
{
    std::map<std::string, BotClassSpecActionProfile> Profiles;
    std::vector<std::string> Order;
    uint64 Generation = 0;
    std::string ContentHash;
};

std::mutex g_dbRotationMutex;
std::shared_ptr<DbRotationSnapshot const> g_activeDbRotationSnapshot;
std::shared_ptr<DbRotationSnapshot const> g_previousDbRotationSnapshot;
std::string g_dbRotationLastError;

std::string DbRotationKey(uint8 classId, std::string const& specTag, std::string const& role)
{
    std::ostringstream key;
    key << uint32(classId) << ":" << specTag << ":" << role;
    return key.str();
}

std::string CanonicalSpecTag(std::string specTag)
{
    std::transform(specTag.begin(), specTag.end(), specTag.begin(), [](unsigned char c) { return std::tolower(c); });
    std::replace(specTag.begin(), specTag.end(), '-', '_');
    std::replace(specTag.begin(), specTag.end(), ' ', '_');
    static std::map<std::string, std::string> const aliases = {
        { "protection_paladin", "protection" },
        { "marksmanship_hunter", "marksmanship" },
        { "survival_hunter", "survival" },
        { "enhancement_shaman", "enhancement" },
        { "fire_mage", "fire" }
    };
    auto itr = aliases.find(specTag);
    return itr == aliases.end() ? specTag : itr->second;
}

std::set<std::string> CanonicalKeySet()
{
    std::set<std::string> keys;
    for (CanonicalRotationKey const& key : CanonicalRotationKeys)
        keys.insert(DbRotationKey(key.ClassId, key.SpecTag, key.Role));
    return keys;
}

bool HasAny(Player const* bot, std::vector<uint32> const& ids)
{
    if (!bot)
        return false;
    for (uint32 id : ids)
        if (bot->HasSpell(id))
            return true;
    return false;
}

std::string InferSpecTag(Player const* bot, std::string const& role)
{
    if (!bot)
        return "generic";

    if (QueryResult result = CharacterDatabase.PQuery("SELECT class_spec FROM character_bot_pool WHERE guid = %u LIMIT 1", bot->GetGUID().GetCounter()))
    {
        std::string classSpec = CanonicalSpecTag(result->Fetch()[0].GetString());
        if (!classSpec.empty())
            return classSpec;
    }

    switch (bot->getClass())
    {
        case CLASS_MAGE:
            return HasAny(bot, {44457, 11366, 31661}) ? "fire" : "mage_generic";
        case CLASS_PRIEST:
            return role == "healer" ? "holy_priest" : "priest_generic";
        case CLASS_SHAMAN:
            return role == "healer" ? "restoration_shaman" : (HasAny(bot, {17364, 60103}) ? "enhancement" : "shaman_generic");
        case CLASS_PALADIN:
            return role == "tank" ? "protection" : (role == "healer" ? "holy_paladin" : "paladin_generic");
        case CLASS_HUNTER:
            return HasAny(bot, {53301, 3674}) ? "survival"
                : (HasAny(bot, {53209, 19434}) ? "marksmanship" : "hunter_generic");
        case CLASS_DEATH_KNIGHT:
            return role == "tank" ? "blood" : "death_knight_generic";
        case CLASS_WARRIOR:
            return role == "tank" ? "protection" : "warrior_generic";
        case CLASS_DRUID:
            return role == "healer" ? "restoration_druid" : "druid_generic";
        case CLASS_ROGUE:
            return "rogue_generic";
        case CLASS_WARLOCK:
            return "warlock_generic";
        default:
            return "generic";
    }
}

bool HasEnoughPowerForProfileSpell(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return false;

    // Dark Transformation consumes the ghoul's Shadow Infusion stacks.  Its
    // SQL profile requires the owner-side ready aura before this resource check.
    if (spellInfo->Id == ProfileDarkTransformationSpellId)
        return true;

    if (spellInfo->PowerType == POWER_RUNE && spellInfo->RuneCostID && bot->getClass() == CLASS_DEATH_KNIGHT)
    {
        SpellRuneCostEntry const* runeCost = sSpellRuneCostStore.LookupEntry(spellInfo->RuneCostID);
        if (runeCost && !runeCost->NoRuneCost())
        {
            std::array<int32, 3> required = { int32(runeCost->RuneCost[0]), int32(runeCost->RuneCost[1]), int32(runeCost->RuneCost[2]) };
            // Native rune validation applies the player's current spell-cost
            // modifiers (for example a free-rune proc) before examining ready
            // runes.  Candidate preflight must observe the same player-visible
            // state or it can reject a cast that Spell::CheckRuneCost accepts.
            if (Player* modOwner = bot->GetSpellModOwner())
                for (int32& runeRequirement : required)
                    modOwner->ApplySpellMod(spellInfo, SpellModOp::PowerCost0, runeRequirement);
            uint8 deathRunes = 0;
            for (uint8 i = 0; i < MAX_RUNES; ++i)
            {
                if (std::abs(bot->GetRuneCooldown(i)) > 0.0001f)
                    continue;

                switch (bot->GetCurrentRune(i))
                {
                    case RuneType::Blood:
                        if (required[0] > 0)
                            --required[0];
                        break;
                    case RuneType::Unholy:
                        if (required[1] > 0)
                            --required[1];
                        break;
                    case RuneType::Frost:
                        if (required[2] > 0)
                            --required[2];
                        break;
                    case RuneType::Death:
                        ++deathRunes;
                        break;
                    default:
                        break;
                }
            }

            int32 deficit = 0;
            for (int32 count : required)
                deficit += std::max<int32>(0, count);
            if (deficit > deathRunes)
                return false;
        }
    }

    int32 cost = spellInfo->CalcPowerCost(bot, spellInfo->GetSchoolMask());
    if (cost <= 0)
        return true;
    if (spellInfo->PowerType >= MAX_POWERS)
        return true;
    if (spellInfo->PowerType == POWER_HEALTH)
        return int64(bot->GetHealth()) > cost;
    return bot->GetPower(Powers(spellInfo->PowerType)) >= uint32(cost);
}

uint32 ProfileSpellCastTimeMs(Player const* bot, SpellInfo const* spellInfo)
{
    if (!bot || !spellInfo)
        return 0;
    return uint32(std::max<int32>(0, spellInfo->CalcCastTime(bot->getLevel())));
}

struct ReadyRuneObservation
{
    uint8 Total = 0;
    uint8 Blood = 0;
    uint8 Unholy = 0;
    uint8 Frost = 0;
    uint8 Death = 0;
};

ReadyRuneObservation ObserveReadyRunes(Player const* bot)
{
    ReadyRuneObservation observation;
    if (!bot || bot->getClass() != CLASS_DEATH_KNIGHT)
        return observation;
    for (uint8 rune = 0; rune < MAX_RUNES; ++rune)
        if (std::abs(bot->GetRuneCooldown(rune)) <= 0.0001f)
        {
            ++observation.Total;
            switch (bot->GetCurrentRune(rune))
            {
                case RuneType::Blood: ++observation.Blood; break;
                case RuneType::Unholy: ++observation.Unholy; break;
                case RuneType::Frost: ++observation.Frost; break;
                case RuneType::Death: ++observation.Death; break;
                default: break;
            }
        }
    return observation;
}

uint8 ReadyRuneCount(Player const* bot)
{
    return ObserveReadyRunes(bot).Total;
}

uint32 EquippedTemporaryEnchant(Player const* bot, uint8 slot)
{
    Item const* item = bot ? bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot) : nullptr;
    return item ? item->GetEnchantmentId(TEMP_ENCHANTMENT_SLOT) : 0;
}

std::string EvaluateCompiledConditions(Player const* bot, Unit const* target, Unit const* comboTarget, BotActionProfileSpell const& spell)
{
    if (!bot)
        return "missing_bot";
    Aura const* selfAura = spell.RequiredSelfAura ? bot->GetAura(spell.RequiredSelfAura) : nullptr;
    if (spell.RequiredSelfAura && !selfAura)
        return "missing_required_self_aura";
    if (spell.ForbiddenSelfAura && bot->HasAura(spell.ForbiddenSelfAura))
        return "forbidden_self_aura_active";
    if (spell.RequiredSelfAuraStacks && (!selfAura || selfAura->GetStackAmount() < spell.RequiredSelfAuraStacks))
        return "insufficient_self_aura_stacks";
    if (spell.MaxSelfAuraStacks && selfAura && selfAura->GetStackAmount() > spell.MaxSelfAuraStacks)
        return "self_aura_stacks_too_high";
    if (selfAura && (spell.MinSelfAuraRemainingMs || spell.MaxSelfAuraRemainingMs))
    {
        int32 remaining = selfAura->GetDuration();
        if (remaining >= 0 && spell.MinSelfAuraRemainingMs && uint32(remaining) < spell.MinSelfAuraRemainingMs)
            return "self_aura_duration_too_low";
        if ((remaining < 0 && spell.MaxSelfAuraRemainingMs)
            || (remaining >= 0 && spell.MaxSelfAuraRemainingMs && uint32(remaining) > spell.MaxSelfAuraRemainingMs))
            return "self_aura_duration_too_high";
    }
    if (spell.RequiredTargetAura && (!target || !target->HasAura(spell.RequiredTargetAura)))
        return "missing_required_target_aura";
    if (spell.ForbiddenTargetAura && target && target->HasAura(spell.ForbiddenTargetAura))
        return "forbidden_target_aura_active";
    Aura const* lacerate = target ? target->GetAura(33745, bot->GetGUID()) : nullptr;
    if (HasMechanicTag(spell.MechanicTags, "lacerate_spender")
        && (!lacerate || lacerate->GetStackAmount() < 3))
        return "insufficient_lacerate_stacks";
    if (HasMechanicTag(spell.MechanicTags, "lacerate")
        && !HasMechanicTag(spell.MechanicTags, "lacerate_spender")
        && lacerate && lacerate->GetStackAmount() >= 3 && lacerate->GetDuration() > 3000)
        return "lacerate_stacks_ready";
    if (spell.RequiredOwnedTargetAura && (!target || !target->HasAura(spell.RequiredOwnedTargetAura, bot->GetGUID())))
        return "missing_required_owned_target_aura";
    if (spell.ForbiddenOwnedTargetAura && target && target->HasAura(spell.ForbiddenOwnedTargetAura, bot->GetGUID()))
        return "forbidden_owned_target_aura_active";
    if (HasMechanicTag(spell.MechanicTags, "holy_power_3") && bot->GetPower(POWER_HOLY_POWER) < 3)
        return "insufficient_holy_power";
    if (spell.MaintainAuraId && !spell.RequiredOwnedTargetAura
        && !spell.ForbiddenOwnedTargetAura)
    {
        if (HasMechanicTag(spell.MechanicTags, "maintain_owned_aura"))
        {
            Aura const* ownedAura = target
                ? target->GetAura(spell.MaintainAuraId, bot->GetGUID()) : nullptr;
            if (ownedAura)
            {
                int32 const remainingMs = ownedAura->GetDuration();
                if (!spell.RefreshAuraBelowMs || remainingMs < 0
                    || uint32(remainingMs) > spell.RefreshAuraBelowMs)
                    return "maintain_owned_aura_active";
            }
        }
        else if (MaintainedAuraBlocksRefresh(target, spell.MaintainAuraId,
                spell.RefreshAuraBelowMs))
            return "maintain_aura_active";
    }

    uint8 comboPoints = bot->GetComboTarget() == (comboTarget ? comboTarget->GetGUID() : ObjectGuid::Empty)
        ? bot->GetComboPoints() : 0;
    if (comboPoints < spell.MinComboPoints || (spell.MaxComboPoints && comboPoints > spell.MaxComboPoints))
        return "combo_point_gate";
    if (spell.MinReadyRunes && ReadyRuneCount(bot) < spell.MinReadyRunes)
        return "ready_rune_gate";
    if (spell.RequiredShapeshiftForm && uint8(bot->GetShapeshiftForm()) != spell.RequiredShapeshiftForm)
        return "shapeshift_form_gate";
    if (spell.RequiresPet && (!bot->GetPet() || !bot->GetPet()->IsAlive()))
        return "living_pet_required";
    if (spell.ForbidsPet && bot->GetPet())
        return "pet_forbidden";
    if (spell.RequiredMainHandEnchant
        && EquippedTemporaryEnchant(bot, EQUIPMENT_SLOT_MAINHAND) != spell.RequiredMainHandEnchant)
        return "main_hand_enchant_gate";
    if (spell.RequiredOffHandEnchant
        && EquippedTemporaryEnchant(bot, EQUIPMENT_SLOT_OFFHAND) != spell.RequiredOffHandEnchant)
        return "off_hand_enchant_gate";
    if (spell.TargetCreatureTypeMask && (!target || !(target->GetCreatureTypeMask() & spell.TargetCreatureTypeMask)))
        return "target_creature_type_gate";

    float manaPct = bot->GetMaxPower(POWER_MANA)
        ? float(bot->GetPower(POWER_MANA)) / float(bot->GetMaxPower(POWER_MANA)) : 0.0f;
    if (manaPct < spell.MinManaPct || manaPct > spell.MaxManaPct)
        return "mana_gate";
    Powers primaryPower = bot->GetPowerType();
    uint32 maxPrimaryPower = bot->GetMaxPower(primaryPower);
    float primaryPowerPct = maxPrimaryPower ? float(bot->GetPower(primaryPower)) / float(maxPrimaryPower) : 0.0f;
    if (primaryPowerPct < spell.MinPrimaryPowerPct || primaryPowerPct > spell.MaxPrimaryPowerPct)
        return "primary_power_gate";
    uint32 attackers = uint32(bot->getAttackers().size());
    if (attackers < spell.MinAttackers || (spell.MaxAttackers && attackers > spell.MaxAttackers))
        return "attacker_count_gate";
    if ((spell.RequiresStationary && bot->isMoving()) || (spell.RequiresMoving && !bot->isMoving()))
        return "movement_gate";
    return "";
}

std::string SnapshotPayload(DbRotationSnapshot const& snapshot)
{
    std::ostringstream payload;
    payload.precision(9);
    for (std::string const& key : snapshot.Order)
    {
        BotClassSpecActionProfile const& profile = snapshot.Profiles.at(key);
        payload << key << '|' << profile.ResourceType << '|' << profile.RangeBand << '|'
                << profile.MovementDirective << '|' << profile.AutoAttackMode << '|'
                << profile.MinRange << '|' << profile.MaxRange << '\n';
        for (BotActionProfileSpell const& spell : profile.Spells)
            payload << spell.SortOrder << '|' << spell.SpellId << '|'
                    << BotCombatActionCatalog::ToString(spell.Category) << '|' << spell.MechanicTags << '|'
                    << spell.DamageWeight << '|' << spell.HealingWeight << '|' << spell.ThreatWeight << '|'
                    << spell.MitigationWeight << '|' << spell.SurvivalWeight << '|' << spell.MovementWeight << '|'
                    << spell.ProgressionWeight << '|' << spell.ProfessionWeight << '|'
                    << uint32(spell.PriorityBucket) << '|' << uint32(spell.MinEnemies) << '|'
                    << uint32(spell.MaxEnemies) << '|' << spell.MinTargetHealthPct << '|'
                    << spell.MaxTargetHealthPct << '|' << spell.MinSelfHealthPct << '|'
                    << spell.MaxSelfHealthPct << '|' << spell.RequiredSelfAura << '|'
                    << spell.ForbiddenSelfAura << '|' << spell.RequiredTargetAura << '|'
                    << spell.ForbiddenTargetAura << '|' << spell.RequiresInterruptibleTarget << '|'
                    << spell.RequiresTargetNotVictim << '|' << spell.RequiresTargetVictim << '|'
                    << spell.RequiresMeleeRange << '|' << spell.RequiresRangedRange << '|'
                    << spell.TargetSelector << '|' << spell.MovementDirective << '|'
                    << spell.AutoAttackMode << '|' << spell.MinRange << '|' << spell.MaxRange << '|'
                    << spell.RequiresInstantCast << '|' << spell.MaxCastTimeMs << '|'
                    << spell.MaintainAuraId << '|' << spell.RefreshAuraBelowMs << '|'
                    << uint32(spell.MinInjuredPlayers) << '|' << uint32(spell.MaxInjuredPlayers) << '|'
                    << spell.InjuredHealthPct << '|' << spell.MinManaPct << '|' << spell.MaxManaPct << '|'
                    << uint32(spell.MinAttackers) << '|' << uint32(spell.MaxAttackers) << '|'
                    << spell.RequiresStationary << '|' << spell.RequiresMoving << '|'
                    << uint32(spell.RequiredSelfAuraStacks) << '|' << spell.MinPrimaryPowerPct << '|'
                    << spell.MaxPrimaryPowerPct << '|' << uint32(spell.MaxSelfAuraStacks) << '|'
                    << spell.MinSelfAuraRemainingMs << '|' << spell.MaxSelfAuraRemainingMs << '|'
                    << spell.RequiredOwnedTargetAura << '|' << spell.ForbiddenOwnedTargetAura << '|'
                    << uint32(spell.MinComboPoints) << '|' << uint32(spell.MaxComboPoints) << '|'
                    << uint32(spell.MinReadyRunes) << '|' << uint32(spell.RequiredShapeshiftForm) << '|'
                    << spell.RequiresPet << '|' << spell.ForbidsPet << '|'
                    << spell.RequiredMainHandEnchant << '|' << spell.RequiredOffHandEnchant << '|'
                    << spell.CooldownGroup << '|' << spell.TargetCreatureTypeMask << '|'
                    << spell.RequiresGroundTarget << '\n';
    }
    return payload.str();
}

std::string SnapshotHash(DbRotationSnapshot const& snapshot)
{
    return ByteArrayToHexStr(Trinity::Crypto::SHA256::GetDigestOf(SnapshotPayload(snapshot)));
}

std::shared_ptr<DbRotationSnapshot> LoadDbSnapshot(std::string& failureReason)
{
    std::set<std::string> const expectedKeys = CanonicalKeySet();
    std::shared_ptr<DbRotationSnapshot> snapshot = std::make_shared<DbRotationSnapshot>();
    QueryResult result = WorldDatabase.Query(
        "SELECT p.id, p.class_id, p.spec_tag, p.role, p.resource_type, p.range_band, p.version, "
        "p.movement_directive, p.auto_attack_mode, p.min_range, p.max_range, "
        "a.sort_order, a.spell_id, a.category, a.mechanic_tags, a.damage_weight, a.healing_weight, a.threat_weight, "
        "a.mitigation_weight, a.survival_weight, a.movement_weight, a.progression_weight, "
        "a.profession_weight, a.priority_bucket, a.min_enemies, a.max_enemies, "
        "a.min_target_health_pct, a.max_target_health_pct, a.min_self_health_pct, a.max_self_health_pct, "
        "a.required_self_aura, a.forbidden_self_aura, a.required_target_aura, a.forbidden_target_aura, "
        "a.requires_interruptible_target, a.requires_target_not_victim, a.requires_target_victim, "
        "a.requires_melee_range, a.requires_ranged_range, a.target_selector, a.movement_directive, "
        "a.auto_attack_mode, a.min_range, a.max_range, a.requires_instant_cast, a.max_cast_time_ms, "
        "a.maintain_aura_id, a.refresh_aura_below_ms, a.min_injured_players, a.max_injured_players, "
        "a.injured_health_pct, a.min_mana_pct, a.max_mana_pct, a.min_attackers, a.max_attackers, "
        "a.requires_stationary, a.requires_moving, a.required_self_aura_stacks, "
        "a.min_primary_power_pct, a.max_primary_power_pct, a.max_self_aura_stacks, "
        "a.min_self_aura_remaining_ms, a.max_self_aura_remaining_ms, "
        "a.required_owned_target_aura, a.forbidden_owned_target_aura, "
        "a.min_combo_points, a.max_combo_points, a.min_ready_runes, a.required_shapeshift_form, "
        "a.requires_pet, a.forbids_pet, a.required_main_hand_enchant, a.required_off_hand_enchant, "
        "a.cooldown_group, a.target_creature_type_mask, a.requires_ground_target "
        "FROM bot_rotation_profile p "
        "JOIN bot_rotation_action a ON a.profile_id = p.id "
        "WHERE p.enabled = 1 AND a.enabled = 1 "
        "ORDER BY p.class_id, p.spec_tag, p.role, a.priority_bucket, a.sort_order, a.id");
    if (!result)
    {
        failureReason = "no_enabled_rotation_profiles";
        return nullptr;
    }

    std::set<std::string> invalidReasons;
    std::map<std::string, uint32> profileIds;
    do
    {
        Field* fields = result->Fetch();
        uint32 profileId = fields[0].GetUInt32();
        uint8 classId = fields[1].GetUInt8();
        std::string specTag = CanonicalSpecTag(fields[2].GetString());
        std::string role = fields[3].GetString();
        std::string key = DbRotationKey(classId, specTag, role);
        if (!expectedKeys.count(key))
            continue;
        auto profileIdItr = profileIds.find(key);
        if (profileIdItr != profileIds.end() && profileIdItr->second != profileId)
        {
            invalidReasons.insert("duplicate_profile_" + key);
            continue;
        }
        profileIds[key] = profileId;

        auto [profileItr, inserted] = snapshot->Profiles.emplace(key, BotClassSpecActionProfile());
        BotClassSpecActionProfile& profile = profileItr->second;
        if (inserted)
        {
            profile.ClassId = classId;
            profile.SpecTag = specTag;
            profile.Role = role;
            profile.ResourceType = fields[4].GetString();
            profile.RangeBand = fields[5].GetString();
            profile.ProfileSource = "world_db_bot_rotation_profile_" + std::to_string(profileId) + "_v" + fields[6].GetString();
            profile.MovementDirective = fields[7].GetString();
            profile.AutoAttackMode = fields[8].GetString();
            profile.MinRange = fields[9].GetFloat();
            profile.MaxRange = fields[10].GetFloat();
            profile.MissingProfile = false;
            snapshot->Order.push_back(key);
            if (profile.MovementDirective.empty() || profile.AutoAttackMode.empty())
                invalidReasons.insert("missing_movement_directives_" + key);
        }

        uint32 spellId = fields[12].GetUInt32();
        SpellInfo const* spellInfo = spellId ? sSpellMgr->GetSpellInfo(spellId) : nullptr;
        if (spellId && !spellInfo)
        {
            invalidReasons.insert("invalid_spell_id_" + std::to_string(spellId));
            continue;
        }
        std::string categoryName = fields[13].GetString();
        BotCombatActionCategory category = BotCombatActionCatalog::CategoryFromString(categoryName);
        if (category == BotCombatActionCategory::Wait && categoryName != "wait")
        {
            invalidReasons.insert("invalid_category_" + categoryName);
            continue;
        }

        BotActionProfileSpell spell;
        spell.SortOrder = fields[11].GetUInt16();
        spell.SpellId = spellId;
        spell.Category = category;
        spell.MechanicTags = fields[14].GetString();
        spell.DamageWeight = fields[15].GetFloat();
        spell.HealingWeight = fields[16].GetFloat();
        spell.ThreatWeight = fields[17].GetFloat();
        spell.MitigationWeight = fields[18].GetFloat();
        spell.SurvivalWeight = fields[19].GetFloat();
        spell.MovementWeight = fields[20].GetFloat();
        spell.ProgressionWeight = fields[21].GetFloat();
        spell.ProfessionWeight = fields[22].GetFloat();
        spell.PriorityBucket = fields[23].GetUInt8();
        spell.MinEnemies = fields[24].GetUInt8();
        spell.MaxEnemies = fields[25].GetUInt8();
        spell.MinTargetHealthPct = fields[26].GetFloat();
        spell.MaxTargetHealthPct = fields[27].GetFloat();
        spell.MinSelfHealthPct = fields[28].GetFloat();
        spell.MaxSelfHealthPct = fields[29].GetFloat();
        spell.RequiredSelfAura = fields[30].GetUInt32();
        spell.ForbiddenSelfAura = fields[31].GetUInt32();
        spell.RequiredTargetAura = fields[32].GetUInt32();
        spell.ForbiddenTargetAura = fields[33].GetUInt32();
        spell.RequiresInterruptibleTarget = fields[34].GetBool();
        spell.RequiresTargetNotVictim = fields[35].GetBool();
        spell.RequiresTargetVictim = fields[36].GetBool();
        spell.RequiresMeleeRange = fields[37].GetBool();
        spell.RequiresRangedRange = fields[38].GetBool();
        spell.TargetSelector = fields[39].GetString();
        spell.MovementDirective = fields[40].GetString();
        spell.AutoAttackMode = fields[41].GetString();
        spell.MinRange = fields[42].GetFloat();
        spell.MaxRange = fields[43].GetFloat();
        spell.RequiresInstantCast = fields[44].GetBool();
        spell.MaxCastTimeMs = fields[45].GetUInt32();
        spell.MaintainAuraId = fields[46].GetUInt32();
        spell.RefreshAuraBelowMs = fields[47].GetUInt32();
        spell.MinInjuredPlayers = fields[48].GetUInt8();
        spell.MaxInjuredPlayers = fields[49].GetUInt8();
        spell.InjuredHealthPct = fields[50].GetFloat();
        spell.MinManaPct = fields[51].GetFloat();
        spell.MaxManaPct = fields[52].GetFloat();
        spell.MinAttackers = fields[53].GetUInt8();
        spell.MaxAttackers = fields[54].GetUInt8();
        spell.RequiresStationary = fields[55].GetBool();
        spell.RequiresMoving = fields[56].GetBool();
        spell.RequiredSelfAuraStacks = fields[57].GetUInt8();
        spell.MinPrimaryPowerPct = fields[58].GetFloat();
        spell.MaxPrimaryPowerPct = fields[59].GetFloat();
        spell.MaxSelfAuraStacks = fields[60].GetUInt8();
        spell.MinSelfAuraRemainingMs = fields[61].GetUInt32();
        spell.MaxSelfAuraRemainingMs = fields[62].GetUInt32();
        spell.RequiredOwnedTargetAura = fields[63].GetUInt32();
        spell.ForbiddenOwnedTargetAura = fields[64].GetUInt32();
        spell.MinComboPoints = fields[65].GetUInt8();
        spell.MaxComboPoints = fields[66].GetUInt8();
        spell.MinReadyRunes = fields[67].GetUInt8();
        spell.RequiredShapeshiftForm = fields[68].GetUInt8();
        spell.RequiresPet = fields[69].GetBool();
        spell.ForbidsPet = fields[70].GetBool();
        spell.RequiredMainHandEnchant = fields[71].GetUInt32();
        spell.RequiredOffHandEnchant = fields[72].GetUInt32();
        spell.CooldownGroup = fields[73].GetString();
        spell.TargetCreatureTypeMask = fields[74].GetUInt32();
        spell.RequiresGroundTarget = fields[75].GetBool();

        static std::set<std::string> const targetSelectors = {
            "enemy", "self", "party", "lowest_ally", "tank", "ground_enemy"
        };
        if (!targetSelectors.count(spell.TargetSelector))
            invalidReasons.insert("invalid_target_selector_" + spell.TargetSelector);
        if (spell.MinEnemies > spell.MaxEnemies && spell.MaxEnemies)
            invalidReasons.insert("invalid_enemy_range_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.MinTargetHealthPct > spell.MaxTargetHealthPct || spell.MinSelfHealthPct > spell.MaxSelfHealthPct)
            invalidReasons.insert("invalid_health_range_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.MinComboPoints > spell.MaxComboPoints && spell.MaxComboPoints)
            invalidReasons.insert("invalid_combo_range_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.MinManaPct > spell.MaxManaPct || spell.MinPrimaryPowerPct > spell.MaxPrimaryPowerPct)
            invalidReasons.insert("invalid_power_range_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.MinSelfAuraRemainingMs > spell.MaxSelfAuraRemainingMs && spell.MaxSelfAuraRemainingMs)
            invalidReasons.insert("invalid_aura_duration_range_" + key + "_" + std::to_string(spell.SortOrder));
        if ((spell.RequiredSelfAuraStacks || spell.MaxSelfAuraStacks || spell.MinSelfAuraRemainingMs || spell.MaxSelfAuraRemainingMs)
            && !spell.RequiredSelfAura)
            invalidReasons.insert("self_aura_gate_without_aura_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.RequiresPet && spell.ForbidsPet)
            invalidReasons.insert("contradictory_pet_gate_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.RequiresStationary && spell.RequiresMoving)
            invalidReasons.insert("contradictory_movement_gate_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.RequiresGroundTarget && (!spellInfo || !(spellInfo->GetExplicitTargetMask() & TARGET_FLAG_DEST_LOCATION)))
            invalidReasons.insert("invalid_ground_target_spell_" + key + "_" + std::to_string(spell.SortOrder));
        if (spell.TargetSelector == "ground_enemy" && !spell.RequiresGroundTarget)
            invalidReasons.insert("ground_selector_without_ground_gate_" + key + "_" + std::to_string(spell.SortOrder));
        std::array<uint32, 7> const predicateSpellIds = {{
            spell.RequiredSelfAura, spell.ForbiddenSelfAura, spell.RequiredTargetAura,
            spell.ForbiddenTargetAura, spell.MaintainAuraId, spell.RequiredOwnedTargetAura,
            spell.ForbiddenOwnedTargetAura
        }};
        for (uint32 predicateSpellId : predicateSpellIds)
            if (predicateSpellId && !sSpellMgr->GetSpellInfo(predicateSpellId))
                invalidReasons.insert("invalid_predicate_spell_id_" + std::to_string(predicateSpellId));
        profile.Spells.push_back(spell);
    } while (result->NextRow());

    for (CanonicalRotationKey const& expected : CanonicalRotationKeys)
    {
        std::string key = DbRotationKey(expected.ClassId, expected.SpecTag, expected.Role);
        auto itr = snapshot->Profiles.find(key);
        if (itr == snapshot->Profiles.end())
            invalidReasons.insert("missing_profile_" + key);
        else if (itr->second.Spells.empty())
            invalidReasons.insert("profile_without_actions_" + key);
    }
    if (!invalidReasons.empty() || snapshot->Profiles.size() != CanonicalRotationKeys.size())
    {
        std::ostringstream failure;
        bool first = true;
        for (std::string const& reason : invalidReasons)
        {
            if (!first)
                failure << ',';
            first = false;
            failure << reason;
        }
        failureReason = failure.str();
        return nullptr;
    }

    snapshot->ContentHash = SnapshotHash(*snapshot);
    return snapshot;
}

bool PublishDbSnapshot(std::shared_ptr<DbRotationSnapshot> snapshot, std::string& failureReason)
{
    if (!snapshot || snapshot->Profiles.size() != CanonicalRotationKeys.size() || snapshot->ContentHash.empty())
    {
        if (failureReason.empty())
            failureReason = "candidate_snapshot_incomplete";
        return false;
    }
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);
    snapshot->Generation = g_activeDbRotationSnapshot ? g_activeDbRotationSnapshot->Generation + 1 : 1;
    for (auto& [key, profile] : snapshot->Profiles)
    {
        profile.SnapshotGeneration = snapshot->Generation;
        profile.SnapshotContentHash = snapshot->ContentHash;
    }
    g_previousDbRotationSnapshot = g_activeDbRotationSnapshot;
    g_activeDbRotationSnapshot = snapshot;
    g_dbRotationLastError.clear();
    return true;
}

bool EnsureDbSnapshotLoaded()
{
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        if (g_activeDbRotationSnapshot)
            return true;
    }
    std::string failureReason;
    std::shared_ptr<DbRotationSnapshot> snapshot = LoadDbSnapshot(failureReason);
    if (!PublishDbSnapshot(snapshot, failureReason))
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        g_dbRotationLastError = failureReason;
        return false;
    }
    return true;
}

}

std::string BotClassSpecActionProfile::EmbeddingJson() const
{
    std::ostringstream json;
    json << "{\"class_id\":" << uint32(ClassId)
         << ",\"spec_tag\":\"" << ClassSpecProfileEscape(SpecTag) << "\""
         << ",\"role\":\"" << ClassSpecProfileEscape(Role) << "\""
         << ",\"resource_type\":\"" << ClassSpecProfileEscape(ResourceType) << "\""
         << ",\"range_band\":\"" << ClassSpecProfileEscape(RangeBand) << "\""
         << ",\"movement_directive\":\"" << ClassSpecProfileEscape(MovementDirective) << "\""
         << ",\"auto_attack_mode\":\"" << ClassSpecProfileEscape(AutoAttackMode) << "\""
         << ",\"min_range\":" << MinRange
         << ",\"max_range\":" << MaxRange
         << ",\"profile_source\":\"" << ClassSpecProfileEscape(ProfileSource) << "\""
         << ",\"snapshot_generation\":" << SnapshotGeneration
         << ",\"snapshot_content_hash\":\"" << ClassSpecProfileEscape(SnapshotContentHash) << "\""
         << ",\"missing_profile\":" << (MissingProfile ? "true" : "false")
         << ",\"known_spell_count\":" << Spells.size() << "}";
    return json.str();
}

std::string BotClassSpecActionProfile::QualityFlagsJson() const
{
    std::ostringstream json;
    json << "{\"missing_profile\":" << (MissingProfile ? "true" : "false")
         << ",\"profile_source\":\"" << ClassSpecProfileEscape(ProfileSource) << "\""
         << ",\"coverage_tags\":\"proc_or_opener\""
         << ",\"coverage_spell_ids\":\"53595,31935,26573,53600,56641,2643,8042,17364,60103,421,2120,1449\"}";
    return json.str();
}

BotClassSpecActionProfile BotClassSpecActionProfileStore::Build(Player const* bot, char const* roleHint)
{
    BotClassSpecActionProfile profile;
    if (!bot)
        return profile;

    profile.ClassId = bot->getClass();
    profile.ResourceType = PowerName(bot->GetPowerType());
    profile.Role = roleHint && *roleHint ? roleHint : "dps";
    profile.SpecTag = InferSpecTag(bot, profile.Role);
    profile.RangeBand = "mixed";
    profile.ProfileSource = "missing_db_rotation_profile";
    profile.MissingProfile = true;

    EnsureDbSnapshotLoaded();
    {
        std::shared_ptr<DbRotationSnapshot const> snapshot;
        {
            std::lock_guard<std::mutex> guard(g_dbRotationMutex);
            snapshot = g_activeDbRotationSnapshot;
        }
        if (snapshot)
        {
            auto itr = snapshot->Profiles.find(DbRotationKey(profile.ClassId, CanonicalSpecTag(profile.SpecTag), profile.Role));
            if (itr != snapshot->Profiles.end())
                profile = itr->second;
        }
    }

    if (!profile.MissingProfile)
    {
        profile.Spells.erase(std::remove_if(profile.Spells.begin(), profile.Spells.end(), [bot](BotActionProfileSpell const& spell)
        {
            return spell.SpellId && spell.Category != BotCombatActionCategory::UseItem
                && !bot->HasSpell(spell.SpellId);
        }), profile.Spells.end());
        if (profile.Spells.empty())
        {
            profile.MissingProfile = true;
            profile.ProfileSource = "db_rotation_profile_has_no_known_spells";
        }
        else if (profile.MovementDirective.empty() || profile.AutoAttackMode.empty())
        {
            profile.MissingProfile = true;
            profile.ProfileSource = "db_rotation_profile_missing_movement_directives";
            profile.Spells.clear();
        }
    }
    if (profile.MissingProfile && profile.ClassId == CLASS_SHAMAN)
        profile.SpecTag = profile.Role == "healer" ? "restoration_or_elemental_generic" : "enhancement_or_elemental_generic";
    if (profile.MissingProfile && profile.ClassId == CLASS_PRIEST)
        profile.SpecTag = profile.Role == "healer" ? "holy_disc_generic" : "shadow_or_generic";
    return profile;
}

std::vector<BotActionCandidate> BotClassSpecActionProfileStore::BuildCandidates(Player const* bot, Unit const* target, BotClassSpecActionProfile const& profile)
{
    std::vector<BotActionCandidate> candidates;
    if (!bot)
        return candidates;

    std::map<std::string, bool> cooldownGroupsReady;
    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        if (spell.CooldownGroup.empty() || !spell.SpellId)
            continue;
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId);
        bool ready = spellInfo && bot->GetSpellHistory()->IsReady(spellInfo);
        auto [itr, inserted] = cooldownGroupsReady.emplace(spell.CooldownGroup, ready);
        if (!inserted)
            itr->second = itr->second && ready;
    }

    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        bool selfTarget = spell.TargetSelector == "self";
        bool allyTarget = spell.TargetSelector == "party" || spell.TargetSelector == "lowest_ally" || spell.TargetSelector == "tank";
        Unit const* actionTarget = selfTarget ? static_cast<Unit const*>(bot) : target;
        uint64 targetGuid = actionTarget ? actionTarget->GetGUID().GetCounter() : 0;
        uint32 targetEntry = 0;
        if (Creature const* creature = actionTarget ? actionTarget->ToCreature() : nullptr)
            targetEntry = creature->GetEntry();

        BotActionCandidate candidate;
        candidate.ActionId = BotCombatActionCatalog::StableActionId(spell.Category, spell.SpellId);
        candidate.SpellId = spell.SpellId;
        candidate.Category = spell.Category;
        candidate.TargetType = selfTarget ? "self" : (allyTarget ? "ally" : "enemy");
        candidate.TargetGuid = targetGuid;
        candidate.TargetEntry = targetEntry;
        candidate.Profile = spell;
        candidate.Score = spell.DamageWeight + spell.HealingWeight + spell.ThreatWeight
            + spell.MitigationWeight + spell.SurvivalWeight + spell.ProgressionWeight
            - float(spell.PriorityBucket) * 0.03f;
        candidate.Reason = "observed_profile_priority";

        // The detailed observation is currently consumed by the Frost
        // compatibility fixture. Keep it scoped to that spec so the shared
        // decision stream does not repeat irrelevant proc/rune payloads for
        // every other class.
        if (profile.SpecTag == "frost_death_knight")
        {
            ReadyRuneObservation const runes = ObserveReadyRunes(bot);
            Powers const primaryPowerType = bot->GetPowerType();
            uint32 const currentPrimaryPower = bot->GetPower(primaryPowerType);
            uint32 const maximumPrimaryPower = bot->GetMaxPower(primaryPowerType);
            Aura const* maintainedAura = actionTarget && spell.MaintainAuraId
                ? actionTarget->GetAura(spell.MaintainAuraId) : nullptr;
            Aura const* ownedMaintainedAura = actionTarget && spell.MaintainAuraId
                ? actionTarget->GetAura(spell.MaintainAuraId, bot->GetGUID()) : nullptr;
            Aura const* ownedBloodPlague = target
                ? target->GetAura(55078, bot->GetGUID()) : nullptr;
            Aura const* ownedFrostFever = target
                ? target->GetAura(55095, bot->GetGUID()) : nullptr;
            std::ostringstream observation;
            observation << "{\"schema\":\"bot_action_observation_v1\""
                        << ",\"primary_power_type\":\"" << PowerName(primaryPowerType) << "\""
                        << ",\"current_primary_power\":" << currentPrimaryPower
                        << ",\"maximum_primary_power\":" << maximumPrimaryPower
                        << ",\"primary_power_ratio\":"
                        << (maximumPrimaryPower
                                ? float(currentPrimaryPower) / float(maximumPrimaryPower)
                                : 0.0f)
                        << ",\"ready_runes\":{\"total\":" << uint32(runes.Total)
                        << ",\"blood\":" << uint32(runes.Blood)
                        << ",\"unholy\":" << uint32(runes.Unholy)
                        << ",\"frost\":" << uint32(runes.Frost)
                        << ",\"death\":" << uint32(runes.Death) << '}'
                        << ",\"required_self_aura\":{\"spell_id\":"
                        << spell.RequiredSelfAura << ",\"active\":"
                        << (spell.RequiredSelfAura && bot->HasAura(spell.RequiredSelfAura)
                                ? "true" : "false") << '}'
                        << ",\"forbidden_self_aura\":{\"spell_id\":"
                        << spell.ForbiddenSelfAura << ",\"active\":"
                        << (spell.ForbiddenSelfAura && bot->HasAura(spell.ForbiddenSelfAura)
                                ? "true" : "false") << '}'
                        << ",\"maintained_aura\":{\"spell_id\":"
                        << spell.MaintainAuraId << ",\"active\":"
                        << (maintainedAura ? "true" : "false")
                        << ",\"remaining_ms\":"
                        << (maintainedAura ? maintainedAura->GetDuration() : 0)
                        << ",\"owned_active\":"
                        << (ownedMaintainedAura ? "true" : "false")
                        << ",\"owned_remaining_ms\":"
                        << (ownedMaintainedAura ? ownedMaintainedAura->GetDuration() : 0)
                        << ",\"refresh_below_ms\":" << spell.RefreshAuraBelowMs << '}'
                        << ",\"observed_aura_flags\":{\"48265\":"
                        << (bot->HasAura(48265) ? "true" : "false")
                        << ",\"51124\":" << (bot->HasAura(51124) ? "true" : "false")
                        << ",\"59052\":" << (bot->HasAura(59052) ? "true" : "false")
                        << ",\"owned_55078\":" << (ownedBloodPlague ? "true" : "false")
                        << ",\"owned_55078_remaining_ms\":"
                        << (ownedBloodPlague ? ownedBloodPlague->GetDuration() : 0)
                        << ",\"owned_55095\":" << (ownedFrostFever ? "true" : "false")
                        << ",\"owned_55095_remaining_ms\":"
                        << (ownedFrostFever ? ownedFrostFever->GetDuration() : 0)
                        << "}}";
            candidate.ObservationJson = observation.str();
        }

        SpellInfo const* spellInfo = spell.SpellId ? sSpellMgr->GetSpellInfo(spell.SpellId) : nullptr;
        Unit const* comboTarget = selfTarget ? target : actionTarget;
        std::string conditionRejection = EvaluateCompiledConditions(bot, actionTarget, comboTarget, spell);
        if (!selfTarget && !actionTarget)
            candidate.RejectReason = allyTarget ? "missing_ally_target" : "missing_enemy_target";
        else if (spell.SpellId && !spellInfo)
            candidate.RejectReason = "missing_spell_info";
        else if (spell.Category == BotCombatActionCategory::UseItem
            && !FindOnUseItemForSpell(bot, spell.SpellId))
            candidate.RejectReason = "missing_or_depleted_item";
        else if (!conditionRejection.empty())
            candidate.RejectReason = conditionRejection;
        else if (bot->HasUnitState(UNIT_STATE_CASTING))
            candidate.RejectReason = "already_casting";
        else if (spellInfo && bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))
            candidate.RejectReason = "global_cooldown";
        else if (spellInfo && !bot->GetSpellHistory()->IsReady(spellInfo))
            candidate.RejectReason = "cooldown_not_ready";
        else if (spellInfo && spellInfo->CasterAuraState
            && !bot->HasAuraState(AuraStateType(spellInfo->CasterAuraState), spellInfo, bot))
            candidate.RejectReason = "missing_caster_aura_state";
        else if (spellInfo && spellInfo->CasterAuraStateNot
            && bot->HasAuraState(AuraStateType(spellInfo->CasterAuraStateNot), spellInfo, bot))
            candidate.RejectReason = "forbidden_caster_aura_state";
        else if (spellInfo && spellInfo->CasterAuraSpell && !bot->HasAura(spellInfo->CasterAuraSpell))
            candidate.RejectReason = "missing_caster_aura";
        else if (spellInfo && spellInfo->ExcludeCasterAuraSpell && bot->HasAura(spellInfo->ExcludeCasterAuraSpell))
            candidate.RejectReason = "forbidden_caster_aura";
        else if (spellInfo && actionTarget && spellInfo->TargetAuraState
            && !actionTarget->HasAuraState(AuraStateType(spellInfo->TargetAuraState), spellInfo, bot))
            candidate.RejectReason = "missing_target_aura_state";
        else if (spellInfo && actionTarget && spellInfo->TargetAuraStateNot
            && actionTarget->HasAuraState(AuraStateType(spellInfo->TargetAuraStateNot), spellInfo, bot))
            candidate.RejectReason = "forbidden_target_aura_state";
        else if (spellInfo && actionTarget && spellInfo->TargetAuraSpell
            && !actionTarget->HasAura(spellInfo->TargetAuraSpell))
            candidate.RejectReason = "missing_spell_target_aura";
        else if (spellInfo && actionTarget && spellInfo->ExcludeTargetAuraSpell
            && actionTarget->HasAura(spellInfo->ExcludeTargetAuraSpell))
            candidate.RejectReason = "forbidden_spell_target_aura";
        else if (!spell.CooldownGroup.empty() && !cooldownGroupsReady[spell.CooldownGroup])
            candidate.RejectReason = "cooldown_group_not_aligned";
        else if (spell.RequiresInterruptibleTarget && actionTarget
            && !actionTarget->GetCurrentSpell(CURRENT_GENERIC_SPELL)
            && !actionTarget->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
            candidate.RejectReason = "target_not_interruptible";
        else if (spell.RequiresTargetNotVictim && actionTarget && actionTarget->GetVictim() == bot)
            candidate.RejectReason = "target_already_on_bot";
        else if (spell.RequiresTargetVictim && actionTarget && actionTarget->GetVictim() != bot)
            candidate.RejectReason = "target_not_on_bot";
        else if (spell.RequiresMeleeRange && actionTarget && !bot->IsWithinMeleeRange(actionTarget))
            candidate.RejectReason = "melee_range_required";
        else if (spell.RequiresRangedRange && actionTarget && bot->GetExactDist(actionTarget) < 5.0f)
            candidate.RejectReason = "ranged_range_required";
        else if (spellInfo && spellInfo->NeedsComboPoints()
            && (!comboTarget || bot->GetComboTarget() != comboTarget->GetGUID() || !bot->GetComboPoints()))
            candidate.RejectReason = "insufficient_combo_points";
        else if (spellInfo && spell.RequiresInstantCast && ProfileSpellCastTimeMs(bot, spellInfo) > 0)
            candidate.RejectReason = "instant_cast_required";
        else if (spellInfo && spell.MaxCastTimeMs && ProfileSpellCastTimeMs(bot, spellInfo) > spell.MaxCastTimeMs)
            candidate.RejectReason = "cast_time_too_long";
        else if (spellInfo && actionTarget
            && !bot->IsWithinDistInMap(actionTarget, std::max(5.0f, spellInfo->GetMaxRange(false))))
            candidate.RejectReason = "out_of_range";
        else if (spellInfo && !HasEnoughPowerForProfileSpell(bot, spellInfo))
            candidate.RejectReason = "insufficient_resource";

        candidates.push_back(candidate);
    }
    return candidates;
}

std::string BotClassSpecActionProfileStore::CandidateMaskJson(std::vector<BotActionCandidate> const& candidates, BotClassSpecActionProfile const& profile, char const* roleGoal, char const* saturationJson, char const* profileSourceOverride)
{
    std::ostringstream json;
    json << "{\"schema\":\"bot_valid_action_mask_v2\""
         << ",\"profile\":" << profile.EmbeddingJson()
         << ",\"profile_source\":\"" << ClassSpecProfileEscape(profileSourceOverride ? profileSourceOverride : profile.ProfileSource) << "\""
         << ",\"role_goal\":\"" << ClassSpecProfileEscape(roleGoal ? roleGoal : profile.Role) << "\""
         << ",\"role_saturation_state\":" << (saturationJson && *saturationJson ? saturationJson : "{}")
         << ",\"observation\":"
         << (candidates.empty() || candidates.front().ObservationJson.empty()
                ? "{}" : candidates.front().ObservationJson)
         << ",\"actions\":[";
    bool first = true;
    for (BotActionCandidate const& candidate : candidates)
    {
        if (!first)
            json << ",";
        first = false;
        json << "{\"action_id\":" << candidate.ActionId
             << ",\"spell_id\":" << candidate.SpellId
             << ",\"action_category\":\"" << ClassSpecProfileEscape(BotCombatActionCatalog::ToString(candidate.Category)) << "\""
             << ",\"target_guid\":" << candidate.TargetGuid
             << ",\"target_entry\":" << candidate.TargetEntry
             << ",\"score\":" << candidate.Score
             << ",\"sort_order\":" << candidate.Profile.SortOrder
             << ",\"priority_bucket\":" << uint32(candidate.Profile.PriorityBucket)
             << ",\"score_inputs\":{\"damage_weight\":" << candidate.Profile.DamageWeight
             << ",\"healing_weight\":" << candidate.Profile.HealingWeight
             << ",\"threat_weight\":" << candidate.Profile.ThreatWeight
             << ",\"mitigation_weight\":" << candidate.Profile.MitigationWeight
             << ",\"survival_weight\":" << candidate.Profile.SurvivalWeight
             << ",\"movement_weight\":" << candidate.Profile.MovementWeight
             << ",\"progression_weight\":" << candidate.Profile.ProgressionWeight
             << ",\"profession_weight\":" << candidate.Profile.ProfessionWeight << "}"
             << ",\"mechanic_tags\":\"" << ClassSpecProfileEscape(candidate.Profile.MechanicTags) << "\""
             << ",\"target_selector\":\"" << ClassSpecProfileEscape(candidate.Profile.TargetSelector) << "\""
             << ",\"movement_directive\":\"" << ClassSpecProfileEscape(candidate.Profile.MovementDirective) << "\""
             << ",\"auto_attack_mode\":\"" << ClassSpecProfileEscape(candidate.Profile.AutoAttackMode) << "\""
             << ",\"valid\":" << (candidate.RejectReason.empty() ? "true" : "false")
             << ",\"predicted_raw_heal\":" << candidate.PredictedRawHeal
             << ",\"predicted_effective_heal\":" << candidate.PredictedEffectiveHeal
             << ",\"predicted_overheal\":" << candidate.PredictedOverheal
             << ",\"mana_cost\":" << candidate.ManaCost
             << ",\"cast_time_ms\":" << candidate.CastTimeMs
             << ",\"reject_reason\":\"" << ClassSpecProfileEscape(candidate.RejectReason) << "\""
             << ",\"role_goal\":\"" << ClassSpecProfileEscape(roleGoal ? roleGoal : profile.Role) << "\"}";
    }
    json << "]}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::ChosenActionJson(BotActionCandidate const* candidate, BotClassSpecActionProfile const& profile, char const* roleGoal, char const* balanceMode, float confidence)
{
    std::ostringstream json;
    json << "{\"action\":\"" << (candidate && candidate->SpellId ? "cast_combat_spell" : "attack") << "\""
         << ",\"action_id\":" << (candidate ? candidate->ActionId : BotCombatActionCatalog::StableActionId(BotCombatActionCategory::Wait))
         << ",\"spell_id\":" << (candidate ? candidate->SpellId : 0)
         << ",\"action_category\":\"" << ClassSpecProfileEscape(candidate ? BotCombatActionCatalog::ToString(candidate->Category) : "wait") << "\""
         << ",\"target_guid\":" << (candidate ? candidate->TargetGuid : 0)
         << ",\"target_entry\":" << (candidate ? candidate->TargetEntry : 0)
         << ",\"class_spec_profile\":" << profile.EmbeddingJson()
         << ",\"role_goal\":\"" << ClassSpecProfileEscape(roleGoal ? roleGoal : profile.Role) << "\""
         << ",\"adaptive_balance_mode\":\"" << ClassSpecProfileEscape(balanceMode ? balanceMode : "role_first") << "\""
         << ",\"experiment_confidence\":" << confidence
         << ",\"reason\":\"" << ClassSpecProfileEscape(candidate ? candidate->Reason : "no_valid_action") << "\""
         << ",\"sort_order\":" << (candidate ? candidate->Profile.SortOrder : 0)
         << ",\"priority_bucket\":" << (candidate ? uint32(candidate->Profile.PriorityBucket) : 0)
         << ",\"mechanic_tags\":\""
         << ClassSpecProfileEscape(candidate ? candidate->Profile.MechanicTags : "") << "\""
         << ",\"expected_damage\":" << (candidate ? candidate->Profile.DamageWeight : 0.0f)
         << ",\"expected_heal\":" << (candidate ? candidate->Profile.HealingWeight : 0.0f)
         << ",\"expected_threat\":" << (candidate ? candidate->Profile.ThreatWeight : 0.0f)
         << ",\"expected_mitigation\":" << (candidate ? candidate->Profile.MitigationWeight : 0.0f)
         << ",\"observation\":"
         << (candidate && !candidate->ObservationJson.empty()
                ? candidate->ObservationJson : "{}")
         << ",\"reject_reason\":\"" << ClassSpecProfileEscape(candidate ? candidate->RejectReason : "no_valid_action") << "\"}";
    return json.str();
}

uint64 BotClassSpecActionProfileStore::ActiveDbGeneration()
{
    EnsureDbSnapshotLoaded();
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);
    return g_activeDbRotationSnapshot ? g_activeDbRotationSnapshot->Generation : 0;
}

std::string BotClassSpecActionProfileStore::ActiveDbContentHash()
{
    EnsureDbSnapshotLoaded();
    std::lock_guard<std::mutex> guard(g_dbRotationMutex);
    return g_activeDbRotationSnapshot ? g_activeDbRotationSnapshot->ContentHash : "";
}

std::string BotClassSpecActionProfileStore::ReloadDbProfiles()
{
    std::string failureReason;
    std::shared_ptr<DbRotationSnapshot> candidate = LoadDbSnapshot(failureReason);
    bool ok = PublishDbSnapshot(candidate, failureReason);
    std::shared_ptr<DbRotationSnapshot const> active;
    if (!ok)
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        g_dbRotationLastError = failureReason;
        active = g_activeDbRotationSnapshot;
    }
    else
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        active = g_activeDbRotationSnapshot;
    }

    std::ostringstream json;
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_rotations_reload\""
         << ",\"expected_profile_count\":" << CanonicalRotationKeys.size()
         << ",\"profile_count\":" << (active ? active->Profiles.size() : 0)
         << ",\"active_generation\":" << (active ? active->Generation : 0)
         << ",\"active_content_hash\":\"" << ClassSpecProfileEscape(active ? active->ContentHash : "") << "\""
         << ",\"failure_reason\":" << (failureReason.empty() ? "null" : ("\"" + ClassSpecProfileEscape(failureReason) + "\""))
         << "}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::RollbackDbProfiles()
{
    std::shared_ptr<DbRotationSnapshot const> active;
    std::shared_ptr<DbRotationSnapshot const> previous;
    std::string failureReason;
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        if (!g_previousDbRotationSnapshot)
            failureReason = "previous_snapshot_unavailable";
        else
        {
            std::shared_ptr<DbRotationSnapshot> rollback = std::make_shared<DbRotationSnapshot>(*g_previousDbRotationSnapshot);
            rollback->Generation = g_activeDbRotationSnapshot ? g_activeDbRotationSnapshot->Generation + 1 : 1;
            for (auto& [key, profile] : rollback->Profiles)
            {
                profile.SnapshotGeneration = rollback->Generation;
                profile.SnapshotContentHash = rollback->ContentHash;
            }
            g_previousDbRotationSnapshot = g_activeDbRotationSnapshot;
            g_activeDbRotationSnapshot = rollback;
            g_dbRotationLastError.clear();
        }
        active = g_activeDbRotationSnapshot;
        previous = g_previousDbRotationSnapshot;
    }

    bool ok = failureReason.empty();
    std::ostringstream json;
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_rotations_rollback\""
         << ",\"profile_count\":" << (active ? active->Profiles.size() : 0)
         << ",\"active_generation\":" << (active ? active->Generation : 0)
         << ",\"active_content_hash\":\"" << ClassSpecProfileEscape(active ? active->ContentHash : "") << "\""
         << ",\"previous_generation\":" << (previous ? previous->Generation : 0)
         << ",\"previous_content_hash\":\"" << ClassSpecProfileEscape(previous ? previous->ContentHash : "") << "\""
         << ",\"failure_reason\":" << (failureReason.empty() ? "null" : ("\"" + ClassSpecProfileEscape(failureReason) + "\""))
         << "}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::DbProfilesJson()
{
    EnsureDbSnapshotLoaded();
    std::shared_ptr<DbRotationSnapshot const> active;
    std::shared_ptr<DbRotationSnapshot const> previous;
    std::string failureReason;
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        active = g_activeDbRotationSnapshot;
        previous = g_previousDbRotationSnapshot;
        failureReason = g_dbRotationLastError;
    }

    std::set<std::string> loaded;
    if (active)
        for (auto const& [key, profile] : active->Profiles)
            loaded.insert(key);

    std::ostringstream json;
    bool ok = active && active->Profiles.size() == CanonicalRotationKeys.size();
    json << "{\"ok\":" << (ok ? "true" : "false")
         << ",\"action\":\"botauto_rotations_list\""
         << ",\"load_mode\":\"immutable_full_catalog_snapshot\""
         << ",\"expected_profile_count\":" << CanonicalRotationKeys.size()
         << ",\"profile_count\":" << loaded.size()
         << ",\"active_generation\":" << (active ? active->Generation : 0)
         << ",\"active_content_hash\":\"" << ClassSpecProfileEscape(active ? active->ContentHash : "") << "\""
         << ",\"previous_generation\":" << (previous ? previous->Generation : 0)
         << ",\"previous_content_hash\":\"" << ClassSpecProfileEscape(previous ? previous->ContentHash : "") << "\""
         << ",\"failure_reason\":" << (failureReason.empty() ? "null" : ("\"" + ClassSpecProfileEscape(failureReason) + "\""))
         << ",\"missing_keys\":[";
    bool first = true;
    for (CanonicalRotationKey const& expected : CanonicalRotationKeys)
    {
        std::string key = DbRotationKey(expected.ClassId, expected.SpecTag, expected.Role);
        if (loaded.count(key))
            continue;
        if (!first)
            json << ',';
        first = false;
        json << '"' << ClassSpecProfileEscape(key) << '"';
    }
    json << "],\"profiles\":[";
    first = true;
    if (active)
        for (std::string const& key : active->Order)
        {
            auto itr = active->Profiles.find(key);
            if (itr == active->Profiles.end())
                continue;
            if (!first)
                json << ',';
            first = false;
            BotClassSpecActionProfile const& profile = itr->second;
            json << "{\"class_id\":" << uint32(profile.ClassId)
                 << ",\"spec_tag\":\"" << ClassSpecProfileEscape(profile.SpecTag) << "\""
                 << ",\"role\":\"" << ClassSpecProfileEscape(profile.Role) << "\""
                 << ",\"range_band\":\"" << ClassSpecProfileEscape(profile.RangeBand) << "\""
                 << ",\"movement_directive\":\"" << ClassSpecProfileEscape(profile.MovementDirective) << "\""
                 << ",\"auto_attack_mode\":\"" << ClassSpecProfileEscape(profile.AutoAttackMode) << "\""
                 << ",\"profile_source\":\"" << ClassSpecProfileEscape(profile.ProfileSource) << "\""
                 << ",\"snapshot_generation\":" << profile.SnapshotGeneration
                 << ",\"snapshot_content_hash\":\"" << ClassSpecProfileEscape(profile.SnapshotContentHash) << "\""
                 << ",\"action_count\":" << profile.Spells.size() << "}";
        }
    json << "]}";
    return json.str();
}

std::string BotClassSpecActionProfileStore::DbProfileDumpJson(uint8 classId, std::string const& specTag, std::string const& role)
{
    EnsureDbSnapshotLoaded();
    std::shared_ptr<DbRotationSnapshot const> snapshot;
    {
        std::lock_guard<std::mutex> guard(g_dbRotationMutex);
        snapshot = g_activeDbRotationSnapshot;
    }

    std::string canonicalSpecTag = CanonicalSpecTag(specTag);
    auto itr = snapshot ? snapshot->Profiles.find(DbRotationKey(classId, canonicalSpecTag, role)) : std::map<std::string, BotClassSpecActionProfile>::const_iterator();
    if (!snapshot || itr == snapshot->Profiles.end())
    {
        std::ostringstream missing;
        missing << "{\"ok\":false,\"action\":\"botauto_rotations_dump\",\"failure_reason\":\"profile_not_found\""
                << ",\"class_id\":" << uint32(classId)
                << ",\"spec_tag\":\"" << ClassSpecProfileEscape(canonicalSpecTag) << "\""
                << ",\"role\":\"" << ClassSpecProfileEscape(role) << "\"}";
        return missing.str();
    }

    BotClassSpecActionProfile const& profile = itr->second;
    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_rotations_dump\""
         << ",\"dump_schema\":\"bot_db_rotation_profile_dump_v2\""
         << ",\"snapshot_generation\":" << snapshot->Generation
         << ",\"snapshot_content_hash\":\"" << ClassSpecProfileEscape(snapshot->ContentHash) << "\""
         << ",\"profile\":" << profile.EmbeddingJson()
         << ",\"actions\":[";
    bool first = true;
    for (BotActionProfileSpell const& spell : profile.Spells)
    {
        if (!first)
            json << ',';
        first = false;
        json << "{\"sort_order\":" << spell.SortOrder
             << ",\"spell_id\":" << spell.SpellId
             << ",\"category\":\"" << ClassSpecProfileEscape(BotCombatActionCatalog::ToString(spell.Category)) << "\""
             << ",\"tags\":\"" << ClassSpecProfileEscape(spell.MechanicTags) << "\""
             << ",\"target_selector\":\"" << ClassSpecProfileEscape(spell.TargetSelector) << "\""
             << ",\"movement_directive\":\"" << ClassSpecProfileEscape(spell.MovementDirective) << "\""
             << ",\"auto_attack_mode\":\"" << ClassSpecProfileEscape(spell.AutoAttackMode) << "\""
             << ",\"priority_bucket\":" << uint32(spell.PriorityBucket)
             << ",\"weights\":{\"damage\":" << spell.DamageWeight
             << ",\"healing\":" << spell.HealingWeight
             << ",\"threat\":" << spell.ThreatWeight
             << ",\"mitigation\":" << spell.MitigationWeight
             << ",\"survival\":" << spell.SurvivalWeight
             << ",\"movement\":" << spell.MovementWeight
             << ",\"progression\":" << spell.ProgressionWeight
             << ",\"profession\":" << spell.ProfessionWeight << "}"
             << ",\"gates\":{\"min_enemies\":" << uint32(spell.MinEnemies)
             << ",\"max_enemies\":" << uint32(spell.MaxEnemies)
             << ",\"min_target_health_pct\":" << spell.MinTargetHealthPct
             << ",\"max_target_health_pct\":" << spell.MaxTargetHealthPct
             << ",\"min_self_health_pct\":" << spell.MinSelfHealthPct
             << ",\"max_self_health_pct\":" << spell.MaxSelfHealthPct
             << ",\"required_self_aura\":" << spell.RequiredSelfAura
             << ",\"forbidden_self_aura\":" << spell.ForbiddenSelfAura
             << ",\"required_target_aura\":" << spell.RequiredTargetAura
             << ",\"forbidden_target_aura\":" << spell.ForbiddenTargetAura
             << ",\"requires_interruptible_target\":" << (spell.RequiresInterruptibleTarget ? "true" : "false")
             << ",\"requires_target_not_victim\":" << (spell.RequiresTargetNotVictim ? "true" : "false")
             << ",\"requires_target_victim\":" << (spell.RequiresTargetVictim ? "true" : "false")
             << ",\"requires_melee_range\":" << (spell.RequiresMeleeRange ? "true" : "false")
             << ",\"requires_ranged_range\":" << (spell.RequiresRangedRange ? "true" : "false")
             << ",\"min_range\":" << spell.MinRange
             << ",\"max_range\":" << spell.MaxRange
             << ",\"requires_instant_cast\":" << (spell.RequiresInstantCast ? "true" : "false")
             << ",\"max_cast_time_ms\":" << spell.MaxCastTimeMs
             << ",\"maintain_aura_id\":" << spell.MaintainAuraId
             << ",\"refresh_aura_below_ms\":" << spell.RefreshAuraBelowMs
             << ",\"min_injured_players\":" << uint32(spell.MinInjuredPlayers)
             << ",\"max_injured_players\":" << uint32(spell.MaxInjuredPlayers)
             << ",\"injured_health_pct\":" << spell.InjuredHealthPct
             << ",\"min_mana_pct\":" << spell.MinManaPct
             << ",\"max_mana_pct\":" << spell.MaxManaPct
             << ",\"min_primary_power_pct\":" << spell.MinPrimaryPowerPct
             << ",\"max_primary_power_pct\":" << spell.MaxPrimaryPowerPct
             << ",\"min_attackers\":" << uint32(spell.MinAttackers)
             << ",\"max_attackers\":" << uint32(spell.MaxAttackers)
             << ",\"requires_stationary\":" << (spell.RequiresStationary ? "true" : "false")
             << ",\"requires_moving\":" << (spell.RequiresMoving ? "true" : "false")
             << ",\"required_owned_target_aura\":" << spell.RequiredOwnedTargetAura
             << ",\"forbidden_owned_target_aura\":" << spell.ForbiddenOwnedTargetAura
             << ",\"required_self_aura_stacks\":" << uint32(spell.RequiredSelfAuraStacks)
             << ",\"max_self_aura_stacks\":" << uint32(spell.MaxSelfAuraStacks)
             << ",\"min_self_aura_remaining_ms\":" << spell.MinSelfAuraRemainingMs
             << ",\"max_self_aura_remaining_ms\":" << spell.MaxSelfAuraRemainingMs
             << ",\"min_combo_points\":" << uint32(spell.MinComboPoints)
             << ",\"max_combo_points\":" << uint32(spell.MaxComboPoints)
             << ",\"min_ready_runes\":" << uint32(spell.MinReadyRunes)
             << ",\"required_shapeshift_form\":" << uint32(spell.RequiredShapeshiftForm)
             << ",\"requires_pet\":" << (spell.RequiresPet ? "true" : "false")
             << ",\"forbids_pet\":" << (spell.ForbidsPet ? "true" : "false")
             << ",\"required_main_hand_enchant\":" << spell.RequiredMainHandEnchant
             << ",\"required_off_hand_enchant\":" << spell.RequiredOffHandEnchant
             << ",\"cooldown_group\":\"" << ClassSpecProfileEscape(spell.CooldownGroup) << "\""
             << ",\"target_creature_type_mask\":" << spell.TargetCreatureTypeMask
             << ",\"requires_ground_target\":" << (spell.RequiresGroundTarget ? "true" : "false")
             << "}}";
    }
    json << "]}";
    return json.str();
}
