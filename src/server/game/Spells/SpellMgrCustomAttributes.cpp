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

#include "SpellMgr.h"
#include "BattlefieldMgr.h"
#include "BattlegroundMgr.h"
#include "Chat.h"
#include "Containers.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "Log.h"
#include "Map.h"
#include "MotionMaster.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "SharedDefines.h"
#include "Spell.h"
#include "SpellAuraDefines.h"
#include "SpellInfo.h"
#include <G3D/g3dmath.h>

void SpellMgr::LoadSpellInfoCustomAttributes()
{
    uint32 oldMSTime = getMSTime();
    uint32 oldMSTime2 = oldMSTime;

    QueryResult result = WorldDatabase.Query("SELECT entry, attributes FROM spell_custom_attr");

    if (!result)
        TC_LOG_INFO("server.loading", ">> Loaded 0 spell custom attributes from DB. DB table `spell_custom_attr` is empty.");
    else
    {
        uint32 count = 0;
        do
        {
            Field* fields = result->Fetch();

            uint32 spellId = fields[0].GetUInt32();
            uint32 attributes = fields[1].GetUInt32();

            SpellInfo* spellInfo = _GetSpellInfo(spellId);
            if (!spellInfo)
            {
                TC_LOG_ERROR("sql.sql", "Table `spell_custom_attr` has wrong spell (entry: %u), ignored.", spellId);
                continue;
            }

            if ((attributes & SPELL_ATTR0_CU_NEGATIVE) != 0)
            {
                for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
                {
                    if (spellInfo->Effects[i].IsEffect())
                        continue;

                    if ((attributes & (SPELL_ATTR0_CU_NEGATIVE_EFF0 << i)) != 0)
                    {
                        TC_LOG_ERROR("sql.sql", "Table `spell_custom_attr` has attribute SPELL_ATTR0_CU_NEGATIVE_EFF%u for spell %u with no EFFECT_%u", uint32(i), spellId, uint32(i));
                        continue;
                    }
                }
            }

            spellInfo->AttributesCu |= attributes;
            ++count;
        } while (result->NextRow());

        TC_LOG_INFO("server.loading", ">> Loaded %u spell custom attributes from DB in %u ms", count, GetMSTimeDiffToNow(oldMSTime2));
    }

    std::set<uint32> talentSpells;
    for (TalentEntry const* talentInfo : sTalentStore)
        for (uint8 i = 0; i < MAX_TALENT_RANK; ++i)
            if (uint32 spellId = talentInfo->SpellRank[i])
                talentSpells.insert(spellId);

    for (SpellInfo* spellInfo : mSpellInfoMap)
    {
        if (!spellInfo)
            continue;

        for (uint8 j = 0; j < MAX_SPELL_EFFECTS; ++j)
        {
            // all bleed effects and spells ignore armor
            if (spellInfo->GetEffectMechanicMask(j) & (1 << MECHANIC_BLEED))
                spellInfo->AttributesCu |= SPELL_ATTR0_CU_IGNORE_ARMOR;

            switch (spellInfo->Effects[j].ApplyAuraName)
            {
                case SPELL_AURA_MOD_POSSESS:
                case SPELL_AURA_MOD_CONFUSE:
                case SPELL_AURA_MOD_CHARM:
                case SPELL_AURA_AOE_CHARM:
                case SPELL_AURA_MOD_FEAR:
                case SPELL_AURA_MOD_STUN:
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_AURA_CC;
                    break;
                case SPELL_AURA_PERIODIC_HEAL:
                case SPELL_AURA_PERIODIC_DAMAGE:
                case SPELL_AURA_PERIODIC_DAMAGE_PERCENT:
                case SPELL_AURA_PERIODIC_LEECH:
                case SPELL_AURA_PERIODIC_MANA_LEECH:
                case SPELL_AURA_PERIODIC_HEALTH_FUNNEL:
                case SPELL_AURA_PERIODIC_ENERGIZE:
                case SPELL_AURA_OBS_MOD_HEALTH:
                case SPELL_AURA_OBS_MOD_POWER:
                case SPELL_AURA_POWER_BURN:
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_NO_INITIAL_THREAT;
                    break;
            }

            switch (spellInfo->Effects[j].ApplyAuraName)
            {
                case SPELL_AURA_OPEN_STABLE:    // No point in saving this, since the stable dialog can't be open on aura load anyway.
                    // Auras that require both caster & target to be in world cannot be saved
                case SPELL_AURA_CONTROL_VEHICLE:
                case SPELL_AURA_BIND_SIGHT:
                case SPELL_AURA_MOD_POSSESS:
                case SPELL_AURA_MOD_CHARM:
                case SPELL_AURA_AOE_CHARM:
                case SPELL_AURA_CONVERT_RUNE:
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_AURA_CANNOT_BE_SAVED;
                    break;
            }

            switch (spellInfo->Effects[j].Effect)
            {
                case SPELL_EFFECT_SCHOOL_DAMAGE:
                case SPELL_EFFECT_HEALTH_LEECH:
                case SPELL_EFFECT_HEAL:
                case SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL:
                case SPELL_EFFECT_WEAPON_PERCENT_DAMAGE:
                case SPELL_EFFECT_WEAPON_DAMAGE:
                case SPELL_EFFECT_POWER_BURN:
                case SPELL_EFFECT_HEAL_MECHANICAL:
                case SPELL_EFFECT_NORMALIZED_WEAPON_DMG:
                case SPELL_EFFECT_HEAL_PCT:
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_CAN_CRIT;
                    break;
            }

            switch (spellInfo->Effects[j].Effect)
            {
                case SPELL_EFFECT_SCHOOL_DAMAGE:
                case SPELL_EFFECT_WEAPON_DAMAGE:
                case SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL:
                case SPELL_EFFECT_NORMALIZED_WEAPON_DMG:
                case SPELL_EFFECT_WEAPON_PERCENT_DAMAGE:
                case SPELL_EFFECT_HEAL:
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_DIRECT_DAMAGE;
                    break;
                case SPELL_EFFECT_POWER_DRAIN:
                case SPELL_EFFECT_POWER_BURN:
                case SPELL_EFFECT_HEAL_MAX_HEALTH:
                case SPELL_EFFECT_HEALTH_LEECH:
                case SPELL_EFFECT_HEAL_PCT:
                case SPELL_EFFECT_ENERGIZE_PCT:
                case SPELL_EFFECT_ENERGIZE:
                case SPELL_EFFECT_HEAL_MECHANICAL:
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_NO_INITIAL_THREAT;
                    break;
                case SPELL_EFFECT_CHARGE:
                case SPELL_EFFECT_CHARGE_DEST:
                case SPELL_EFFECT_JUMP:
                case SPELL_EFFECT_JUMP_DEST:
                case SPELL_EFFECT_LEAP_BACK:
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_CHARGE;
                    break;
                case SPELL_EFFECT_PICKPOCKET:
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_PICKPOCKET;
                    break;
                case SPELL_EFFECT_ENCHANT_ITEM:
                case SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY:
                case SPELL_EFFECT_ENCHANT_ITEM_PRISMATIC:
                case SPELL_EFFECT_ENCHANT_HELD_ITEM:
                {
                    // only enchanting profession enchantments procs can stack
                    if (IsPartOfSkillLine(SKILL_ENCHANTING, spellInfo->Id))
                    {
                        uint32 enchantId = spellInfo->Effects[j].MiscValue;
                        SpellItemEnchantmentEntry const* enchant = sSpellItemEnchantmentStore.LookupEntry(enchantId);
                        if (!enchant)
                            break;

                        for (uint8 s = 0; s < MAX_ITEM_ENCHANTMENT_EFFECTS; ++s)
                        {
                            if (enchant->Effect[s] != ITEM_ENCHANTMENT_TYPE_COMBAT_SPELL)
                                continue;

                            SpellInfo* procInfo = _GetSpellInfo(enchant->EffectArg[s]);
                            if (!procInfo)
                                continue;

                            // if proced directly from enchantment, not via proc aura
                            // NOTE: Enchant Weapon - Blade Ward also has proc aura spell and is proced directly
                            // however its not expected to stack so this check is good
                            if (procInfo->HasAura(SPELL_AURA_PROC_TRIGGER_SPELL))
                                continue;

                            procInfo->AttributesCu |= SPELL_ATTR0_CU_ENCHANT_PROC;
                        }
                    }
                    break;
                }
            }
        }

        // spells ignoring hit result should not be binary
        if (!spellInfo->HasAttribute(SPELL_ATTR3_ALWAYS_HIT))
        {
            bool setFlag = false;
            for (uint8 j = 0; j < MAX_SPELL_EFFECTS; ++j)
            {
                if (spellInfo->Effects[j].IsEffect())
                {
                    switch (spellInfo->Effects[j].Effect)
                    {
                    case SPELL_EFFECT_SCHOOL_DAMAGE:
                    case SPELL_EFFECT_WEAPON_DAMAGE:
                    case SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL:
                    case SPELL_EFFECT_NORMALIZED_WEAPON_DMG:
                    case SPELL_EFFECT_WEAPON_PERCENT_DAMAGE:
                    case SPELL_EFFECT_TRIGGER_SPELL:
                    case SPELL_EFFECT_TRIGGER_SPELL_WITH_VALUE:
                        break;
                    case SPELL_EFFECT_PERSISTENT_AREA_AURA:
                    case SPELL_EFFECT_APPLY_AURA:
                    case SPELL_EFFECT_APPLY_AREA_AURA_PARTY:
                    case SPELL_EFFECT_APPLY_AREA_AURA_RAID:
                    case SPELL_EFFECT_APPLY_AREA_AURA_FRIEND:
                    case SPELL_EFFECT_APPLY_AREA_AURA_ENEMY:
                    case SPELL_EFFECT_APPLY_AREA_AURA_PET:
                    case SPELL_EFFECT_APPLY_AREA_AURA_OWNER:
                        if (spellInfo->Effects[j].ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE ||
                            spellInfo->Effects[j].ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE_PERCENT ||
                            spellInfo->Effects[j].ApplyAuraName == SPELL_AURA_DUMMY ||
                            spellInfo->Effects[j].ApplyAuraName == SPELL_AURA_PERIODIC_LEECH ||
                            spellInfo->Effects[j].ApplyAuraName == SPELL_AURA_PERIODIC_HEALTH_FUNNEL ||
                            spellInfo->Effects[j].ApplyAuraName == SPELL_AURA_PERIODIC_DUMMY)
                            break;
                        [[fallthrough]];
                    default:
                    {
                        // No value and not interrupt cast or crowd control without SPELL_ATTR0_NO_IMMUNITIES flag
                        if (!spellInfo->Effects[j].CalcValue() && !((spellInfo->Effects[j].Effect == SPELL_EFFECT_INTERRUPT_CAST || spellInfo->HasAttribute(SPELL_ATTR0_CU_AURA_CC)) && !spellInfo->HasAttribute(SPELL_ATTR0_NO_IMMUNITIES)))
                            break;

                        // Sindragosa Frost Breath
                        if (spellInfo->Id == 69649 || spellInfo->Id == 71056 || spellInfo->Id == 71057 || spellInfo->Id == 71058 || spellInfo->Id == 73061 || spellInfo->Id == 73062 || spellInfo->Id == 73063 || spellInfo->Id == 73064)
                            break;

                        // Frostbolt
                        if (spellInfo->SpellFamilyName == SPELLFAMILY_MAGE && (spellInfo->SpellFamilyFlags[0] & 0x20))
                            break;

                        // Frost Fever
                        if (spellInfo->Id == 55095)
                            break;

                        // Haunt
                        if (spellInfo->SpellFamilyName == SPELLFAMILY_WARLOCK && (spellInfo->SpellFamilyFlags[1] & 0x40000))
                            break;

                        setFlag = true;
                        break;
                    }
                    }

                    if (setFlag)
                    {
                        spellInfo->AttributesCu |= SPELL_ATTR0_CU_BINARY_SPELL;
                        break;
                    }
                }
            }
        }

        // Remove normal school mask to properly calculate damage
        if ((spellInfo->SchoolMask & SPELL_SCHOOL_MASK_NORMAL) && (spellInfo->SchoolMask & SPELL_SCHOOL_MASK_MAGIC))
        {
            spellInfo->SchoolMask &= ~SPELL_SCHOOL_MASK_NORMAL;
            spellInfo->AttributesCu |= SPELL_ATTR0_CU_SCHOOLMASK_NORMAL_WITH_MAGIC;
        }

        spellInfo->_InitializeSpellPositivity();

        if (talentSpells.count(spellInfo->Id))
            spellInfo->AttributesCu |= SPELL_ATTR0_CU_IS_TALENT;

        switch (spellInfo->SpellFamilyName)
        {
            case SPELLFAMILY_WARRIOR:
                // Shout / Piercing Howl
                if (spellInfo->SpellFamilyFlags[0] & 0x20000/* || spellInfo->SpellFamilyFlags[1] & 0x20*/)
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_AURA_CC;
                break;
            case SPELLFAMILY_DRUID:
                // Roar
                if (spellInfo->SpellFamilyFlags[0] & 0x8)
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_AURA_CC;
                break;
            case SPELLFAMILY_GENERIC:
                // Stoneclaw Totem effect
                if (spellInfo->Id == 5729)
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_AURA_CC;
                break;
            default:
                break;
        }

        spellInfo->_InitializeExplicitTargetMask();

        // Saving to DB happens before removing from world - skip saving these auras
        if (spellInfo->HasAuraInterruptFlag(SpellAuraInterruptFlags::LeaveWorld))
            spellInfo->AttributesCu |= SPELL_ATTR0_CU_AURA_CANNOT_BE_SAVED;
    }

    // addition for binary spells, omit spells triggering other spells
    for (SpellInfo* spellInfo : mSpellInfoMap)
    {
        if (!spellInfo)
            continue;

        if (spellInfo->HasAttribute(SPELL_ATTR0_CU_BINARY_SPELL))
            continue;

        bool allNonBinary = true;
        bool overrideAttr = false;
        for (uint8 j = 0; j < MAX_SPELL_EFFECTS; ++j)
        {
            if (spellInfo->Effects[j].IsAura() && spellInfo->Effects[j].TriggerSpell)
            {
                switch (spellInfo->Effects[j].ApplyAuraName)
                {
                case SPELL_AURA_PERIODIC_TRIGGER_SPELL:
                case SPELL_AURA_PERIODIC_TRIGGER_SPELL_WITH_VALUE:
                    if (SpellInfo const* triggerSpell = sSpellMgr->GetSpellInfo(spellInfo->Effects[j].TriggerSpell))
                    {
                        overrideAttr = true;
                        if (triggerSpell->HasAttribute(SPELL_ATTR0_CU_BINARY_SPELL))
                            allNonBinary = false;
                    }
                    break;
                default:
                    break;
                }
            }
        }

        if (overrideAttr && allNonBinary)
            spellInfo->AttributesCu &= ~SPELL_ATTR0_CU_BINARY_SPELL;
    }

    // remove attribute from spells that can't crit
    for (SpellInfo* spellInfo : mSpellInfoMap)
    {
        if (!spellInfo)
            continue;

        if (!spellInfo->HasAttribute(SPELL_ATTR0_CU_CAN_CRIT))
            continue;

        if (spellInfo->HasAttribute(SPELL_ATTR2_CANT_CRIT))
            spellInfo->AttributesCu &= ~SPELL_ATTR0_CU_CAN_CRIT;
    }

    // add custom attribute to liquid auras
    for (LiquidTypeEntry const* liquid : sLiquidTypeStore)
    {
        if (liquid->SpellID)
        {
            if (uint32 spellId = liquid->SpellID)
                if (SpellInfo* spellInfo = _GetSpellInfo(spellId))
                    spellInfo->AttributesCu |= SPELL_ATTR0_CU_AURA_CANNOT_BE_SAVED;
        }
    }

    TC_LOG_INFO("server.loading", ">> Loaded SpellInfo custom attributes in %u ms", GetMSTimeDiffToNow(oldMSTime));
}
