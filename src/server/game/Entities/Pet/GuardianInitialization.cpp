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


#include "Common.h"
#include "Pet.h"
#include "Player.h"
#include "ObjectMgr.h"
#include "Log.h"
#include "SpellAuraEffects.h"
#include "Unit.h"

namespace
{
constexpr float GUARDIAN_INITIALIZATION_PET_XP_FACTOR = 0.05f;
}

bool Guardian::InitStatsForLevel(uint8 petlevel)
{
    CreatureTemplate const* cinfo = GetCreatureTemplate();
    ASSERT(cinfo);

    SetLevel(petlevel);

    //Determine pet type
    PetType petType = MAX_PET_TYPE;
    if (IsPet() && GetOwner()->GetTypeId() == TYPEID_PLAYER)
    {
        switch (m_owner->getClass())
        {
            case CLASS_WARLOCK:
            case CLASS_SHAMAN:
            case CLASS_DEATH_KNIGHT:
            case CLASS_MAGE:
            case CLASS_PRIEST:
                petType = SUMMON_PET;
                break;
            case CLASS_HUNTER:
                petType = HUNTER_PET;
                m_unitTypeMask |= UNIT_MASK_HUNTER_PET;
                break;
            default:
                TC_LOG_ERROR("entities.pet", "Unknown type pet %u is summoned by player class %u",
                    GetEntry(), GetOwner()->getClass());
                break;
        }
    }

    uint32 creature_ID = (petType == HUNTER_PET) ? 1 : cinfo->Entry;

    SetMeleeDamageSchool(SpellSchools(cinfo->dmgschool));

    SetBaseAttackTime(BASE_ATTACK, BASE_ATTACK_TIME);
    SetBaseAttackTime(OFF_ATTACK, BASE_ATTACK_TIME);
    SetBaseAttackTime(RANGED_ATTACK, BASE_ATTACK_TIME);

    SetFloatValue(UNIT_MOD_CAST_SPEED, 1.0f);
    SetFloatValue(UNIT_MOD_CAST_HASTE, 1.0f);

    //scale
    SetObjectScale(GetNativeObjectScale());

    // Resistance
    // Hunters pets should not inherit resistances from creature_template, they have separate auras for that
    if (!IsHunterPet())
        for (uint8 i = SPELL_SCHOOL_HOLY; i < MAX_SPELL_SCHOOL; ++i)
            SetStatFlatModifier(UnitMods(UNIT_MOD_RESISTANCE_START + i), BASE_VALUE, float(cinfo->resistance[i]));

    Powers powerType = CalculateDisplayPowerType();

    // Health, mana, armor and resistance
    PetLevelInfo const* pInfo = sObjectMgr->GetPetLevelInfo(creature_ID, petlevel);
    if (pInfo)                                      // exist in DB
    {
        SetCreateHealth(pInfo->health);
        SetCreateMana(pInfo->mana);

        SetStatPctModifier(UnitMods(UNIT_MOD_POWER_START + AsUnderlyingType(powerType)), BASE_PCT, 1.0f);

        if (pInfo->armor > 0)
            SetStatFlatModifier(UNIT_MOD_ARMOR, BASE_VALUE, float(pInfo->armor));

        for (uint8 stat = 0; stat < MAX_STATS; ++stat)
            SetCreateStat(Stats(stat), float(pInfo->stats[stat]));
    }
    else                                            // not exist in DB, use some default fake data
    {
        // remove elite bonuses included in DB values
        // remove elite bonuses included in DB values
        CreatureBaseStats const* stats = sObjectMgr->GetCreatureBaseStats(petlevel, cinfo->unit_class);
        float healthmod = _GetHealthMod(cinfo->rank);
        uint32 basehp = stats->GenerateHealth(cinfo);
        uint32 health = uint32(basehp * healthmod);

        SetCreateHealth(health);
        SetCreateMana(stats->BaseMana);
        SetCreateStat(STAT_STRENGTH, 22);
        SetCreateStat(STAT_AGILITY, 22);
        SetCreateStat(STAT_STAMINA, 25);
        SetCreateStat(STAT_INTELLECT, 28);
        SetCreateStat(STAT_SPIRIT, 27);

        SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float(petlevel - (petlevel / 4)));
        SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float(petlevel + (petlevel / 4)));
    }

    // Power
    SetPowerType(powerType);

    // Damage
    SetBonusDamage(0);
    switch (petType)
    {
        case SUMMON_PET:
        {
            SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float(petlevel - (petlevel / 4)));
            SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float(petlevel + (petlevel / 4)));
            break;
        }
        case HUNTER_PET:
        {
            SetUInt32Value(UNIT_FIELD_PETNEXTLEVELEXP, uint32(sObjectMgr->GetXPForLevel(petlevel) * GUARDIAN_INITIALIZATION_PET_XP_FACTOR));
            //these formula may not be correct; however, it is designed to be close to what it should be
            //this makes dps 0.5 of pets level
            SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float(petlevel - (petlevel / 4)));
            //damage range is then petlevel / 2
            SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float(petlevel + (petlevel / 4)));
            //damage is increased afterwards as strength and pet scaling modify attack power
            break;
        }
        default:
        {
            switch (GetEntry())
            {
                case ENTRY_TREANT:
                {
                    float bonusDmg = GetOwner()->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_NATURE) * 0.15f;
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float(petlevel * 2.5f - (petlevel / 2) + bonusDmg));
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float(petlevel * 2.5f + (petlevel / 2) + bonusDmg));
                    SetCreateHealth(m_owner->CountPctFromMaxHealth(10));
                    break;
                }
                case ENTRY_EARTH_ELEMENTAL:
                {
                    if (Unit* owner = m_owner->GetOwner())
                        SetCreateHealth(owner->CountPctFromMaxHealth(75));

                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float(petlevel * 4 - petlevel));
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float(petlevel * 4 + petlevel));
                    break;
                }
                case ENTRY_FIRE_ELEMENTAL:
                {
                    if (Unit* owner = m_owner && m_owner->IsTotem() ? GetStatOwner() : (m_owner ? m_owner->GetOwner() : nullptr))
                    {
                        SetCreateHealth(owner->CountPctFromMaxHealth(75));
                        SetBonusDamage(int32(owner->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_FIRE) * 0.5f));
                    }

                    SetCreateMana(28 + 10 * petlevel);
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float(petlevel * 4 - petlevel));
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float(petlevel * 4 + petlevel));
                    break;
                }
                case ENTRY_SHADOWFIEND:
                {
                    SetCreateMana(28 + 10 * petlevel);
                    SetCreateHealth(28 + 30 * petlevel);
                    int32 bonus_dmg = int32(GetOwner()->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_SHADOW)* 0.375f);
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float((petlevel * 4 - petlevel) + bonus_dmg));
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float((petlevel * 4 + petlevel) + bonus_dmg));

                    break;
                }
                case ENTRY_VENOMOUS_SNAKE:
                {
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float((petlevel / 2) - 25));
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float((petlevel / 2) - 18));
                    break;
                }
                case ENTRY_VIPER:
                {
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float(petlevel / 2 - 10));
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float(petlevel / 2));
                    break;
                }
                case ENTRY_SPIRIT_WOLF:
                {
                    SetCreateHealth(30 * petlevel);
                    float dmg_multiplier = 0.50f;
                    if (m_owner->GetAuraEffect(63271, 0)) // Glyph of Feral Spirit
                        dmg_multiplier = 0.80f;

                    SetBonusDamage(int32(m_owner->GetTotalAttackPowerValue(BASE_ATTACK) * dmg_multiplier));

                    // wolf attack speed is 1.5s
                    SetBaseAttackTime(BASE_ATTACK, cinfo->BaseAttackTime);

                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float((petlevel * 4 - petlevel)));
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float((petlevel * 4 + petlevel)));

                    // 14AP == 1dps, wolf's strike speed == 1.5s so dmg = AP / 14 * 1.5
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, m_owner->GetTotalAttackPowerValue(BASE_ATTACK) * dmg_multiplier / 14);
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, m_owner->GetTotalAttackPowerValue(BASE_ATTACK) * dmg_multiplier / 14);

                    SetStatFlatModifier(UNIT_MOD_ARMOR, BASE_VALUE, float(GetOwner()->GetArmor()) * 0.35f);  // Bonus Armor (35% of player armor)
                    SetStatFlatModifier(UNIT_MOD_STAT_STAMINA, BASE_VALUE, float(GetOwner()->GetStat(STAT_STAMINA)) * 0.3f);  // Bonus Stamina (30% of player stamina)
                    if (!HasAura(58877))        // Spirit Hunt
                        AddAura(58877, this);
                    if (!HasAura(61783))        // Feral Pet Scaling
                        AddAura(61783, this);
                    break;
                }
                case ENTRY_GARGOYLE:
                {
                    SetCreateHealth(m_owner->CountPctFromMaxHealth(70));
                    if (Player* owner = m_owner->ToPlayer())
                    {
                        float bonus = owner->GetRatingBonusValue(CR_HASTE_MELEE);
                        bonus += owner->GetTotalAuraModifier(SPELL_AURA_MOD_MELEE_HASTE_3) +
                            owner->GetTotalAuraModifier(SPELL_AURA_MOD_MELEE_RANGED_HASTE);
                        ApplyCastTimePercentMod(bonus, true);
                    }

                    SetBonusDamage(int32(GetOwner()->GetTotalAttackPowerValue(BASE_ATTACK) * 0.5f));
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, float(petlevel - (petlevel / 4)));
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, float(petlevel + (petlevel / 4)));
                    break;
                }
                case ENTRY_BLOODWORM:
                {
                    SetCreateHealth(m_owner->CountPctFromMaxHealth(18));
                    SetBaseAttackTime(BASE_ATTACK, 1400);
                    SetBonusDamage(int32(m_owner->GetTotalAttackPowerValue(BASE_ATTACK) * 0.006f));
                    float minDamage = m_owner->GetTotalAttackPowerValue(BASE_ATTACK) * 0.05f;
                    float maxDamage = m_owner->GetTotalAttackPowerValue(BASE_ATTACK) * 0.05f;
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, minDamage);
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, maxDamage);
                    if (!HasAura(50453))        // Blood Siphon
                        CastSpell(this, 50453, true);
                    break;
                }
                case ENTRY_INFERNAL:
                {
                    if (m_owner->GetTypeId() == TYPEID_PLAYER) // Infernal get 100% of owners spell, Immolation has his own coef.
                        SetBonusDamage(int32(m_owner->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_SPELL)));

                    float mod = 1;
                    if (petlevel < 60)
                        mod = 5 + (petlevel - 50) / 4;
                    if (petlevel < 70)
                        mod = 10 + (petlevel - 70) / 4;
                    else if (petlevel <= 80)
                        mod = 15 + (petlevel - 80) / 2;
                    else
                        mod = 20 + (petlevel - 85) / 2;
                    if (mod < 0)
                        mod = 0;
                    float minDamage = (petlevel - (petlevel / 4)) * mod;
                    float maxDamage = (petlevel + (petlevel / 4)) * mod;
                    float attackPower = ((minDamage + maxDamage) /4) * 7;
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, minDamage);
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, maxDamage);
                    SetStatFlatModifier(UNIT_MOD_ATTACK_POWER, BASE_VALUE, attackPower);
                    SetCreateHealth(m_owner->CountPctFromMaxHealth(40));
                    break;
                }
                case ENTRY_EBON_IMP:
                    SetBonusDamage(m_owner->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_FIRE));
                    break;
                case ENTRY_ARMY_OF_THE_DEAD_GHOUL:
                {
                    SetCreateHealth(m_owner->CountPctFromMaxHealth(30));
                    SetBonusDamage(int32(GetOwner()->GetTotalAttackPowerValue(BASE_ATTACK) * 0.5f));
                    float minDamage = m_owner->GetTotalAttackPowerValue(BASE_ATTACK) * 0.05f;
                    float maxDamage = m_owner->GetTotalAttackPowerValue(BASE_ATTACK) * 0.05f;
                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, minDamage);
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, maxDamage);
                    if (!HasAura(62137))        // Avoidance
                        CastSpell(this, 62137, true);
                    break;
                }
                case ENTRY_GHOUL:
                    if (!HasAura(62137))        // Avoidance
                        CastSpell(this, 62137, true);
                    break;
                default:
                {
                    /* ToDo: Check what 5f5d2028 broke/fixed and how much of Creature::UpdateLevelDependantStats()
                     * should be copied here (or moved to another method or if that function should be called here
                     * or not just for this default case)
                     */
                    CreatureBaseStats const* stats = sObjectMgr->GetCreatureBaseStats(petlevel, cinfo->unit_class);
                    float basedamage = stats->GenerateBaseDamage(cinfo);

                    float weaponBaseMinDamage = basedamage;
                    float weaponBaseMaxDamage = basedamage * 1.5f;

                    SetBaseWeaponDamage(BASE_ATTACK, MINDAMAGE, weaponBaseMinDamage);
                    SetBaseWeaponDamage(BASE_ATTACK, MAXDAMAGE, weaponBaseMaxDamage);
                    break;
                }
            }
            break;
        }
    }

    UpdateAllStats();

    SetFullHealth();
    SetPower(POWER_MANA, GetMaxPower(POWER_MANA));
    return true;
}
