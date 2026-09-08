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

#include "Unit.h"
#include "Creature.h"
#include "DBCStores.h"
#include "Item.h"
#include "ObjectMgr.h"
#include "Pet.h"
#include "Player.h"
#include "SharedDefines.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellMgr.h"
#include "World.h"
#include <G3D/g3dmath.h>
#include <numeric>

/*#######################################
########                         ########
########    PETS STAT SYSTEM     ########
########                         ########
#######################################*/

bool Guardian::UpdateStats(Stats stat)
{
    if (stat >= MAX_STATS)
        return false;

    // value = ((base_value * base_pct) + total_value) * total_pct
    float value  = GetTotalStatValue(stat);
    //ApplyStatBuffMod(stat, m_statFromOwner[stat], false);
    float ownersBonus = 0.0f;

    SetStat(stat, int32(value));
    m_statFromOwner[stat] = ownersBonus;
    UpdateStatBuffMod(stat);

    switch (stat)
    {
        case STAT_STRENGTH:
            UpdateAttackPowerAndDamage();
            break;
        case STAT_AGILITY:
            UpdateArmor();
            break;
        case STAT_STAMINA:
            UpdateMaxHealth();
            break;
        case STAT_INTELLECT:
            UpdateMaxPower(POWER_MANA);
            break;
        case STAT_SPIRIT:
            break;
        default:
            break;
    }

    return true;
}

bool Guardian::UpdateAllStats()
{
    UpdateMaxHealth();

    for (uint8 i = STAT_STRENGTH; i < MAX_STATS; ++i)
        UpdateStats(Stats(i));

    for (uint8 i = POWER_MANA; i < MAX_POWERS; ++i)
        UpdateMaxPower(Powers(i));

    UpdateAllResistances();

    return true;
}

void Guardian::UpdateResistances(uint32 school)
{
    if (school > SPELL_SCHOOL_NORMAL)
    {
        float value  = GetTotalAuraModValue(UnitMods(UNIT_MOD_RESISTANCE_START + school));
        SetResistance(SpellSchools(school), int32(value));
    }
    else
        UpdateArmor();
}

void Guardian::UpdateArmor()
{
    float value = 0.0f;
    UnitMods unitMod = UNIT_MOD_ARMOR;

    value  = GetFlatModifierValue(unitMod, BASE_VALUE);
    value *= GetPctModifierValue(unitMod, BASE_PCT);
    //value += GetStat(STAT_AGILITY) * 2.0f; (deprecated since 4.x)
    value += GetFlatModifierValue(unitMod, TOTAL_VALUE);
    value *= GetPctModifierValue(unitMod, TOTAL_PCT);


    SetArmor(int32(value));
}

void Guardian::UpdateMaxHealth()
{
    UnitMods unitMod = UNIT_MOD_HEALTH;
    float stamina = GetStat(STAT_STAMINA) - GetCreateStat(STAT_STAMINA);
    float multiplicator = 10.0f;

    float value = GetFlatModifierValue(unitMod, BASE_VALUE) + GetCreateHealth();
    value *= GetPctModifierValue(unitMod, BASE_PCT);
    value += GetFlatModifierValue(unitMod, TOTAL_VALUE) + stamina * multiplicator;
    value *= GetPctModifierValue(unitMod, TOTAL_PCT);

    SetMaxHealth((uint32)value);
}

void Guardian::UpdateMaxPower(Powers power)
{
    if (GetPowerIndex(power) == MAX_POWERS)
        return;

    UnitMods unitMod = UnitMods(UNIT_MOD_POWER_START + AsUnderlyingType(power));

    float addValue = (power == POWER_MANA) ? GetStat(STAT_INTELLECT) - GetCreateStat(STAT_INTELLECT) : 0.0f;
    float multiplicator = 15.0f;

    float value  = GetFlatModifierValue(unitMod, BASE_VALUE) + GetCreatePowerValue(power);
    value *= GetPctModifierValue(unitMod, BASE_PCT);
    value += GetFlatModifierValue(unitMod, TOTAL_VALUE) + addValue * multiplicator;
    value *= GetPctModifierValue(unitMod, TOTAL_PCT);

    SetMaxPower(power, int32(value));
}

void Guardian::UpdateAttackPowerAndDamage(bool ranged)
{
    if (ranged)
        return;

    float ap_per_strength = 2.0f;
    float val = GetStat(STAT_STRENGTH) - 20.0f;

    val *= ap_per_strength;

    // WoWSims Cata 70d87383, sim/shaman/fire_elemental_pet.go: estimated
    // owner-SP-to-AP contribution. Local native stats remain separate.
    if (GetEntry() == ENTRY_FIRE_ELEMENTAL)
        if (Unit* owner = GetStatOwner())
            if (owner->GetTypeId() == TYPEID_PLAYER)
                val += 4.9f * owner->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_FIRE, false);

    UnitMods unitMod = UNIT_MOD_ATTACK_POWER;

    SetStatFlatModifier(UNIT_MOD_ATTACK_POWER, BASE_VALUE, val);

    // in BASE_VALUE of UNIT_MOD_ATTACK_POWER for creatures we store data of meleeattackpower field in DB
    float base_attPower  = GetFlatModifierValue(unitMod, BASE_VALUE) * GetPctModifierValue(unitMod, BASE_PCT);
    float attPowerMod = GetFlatModifierValue(unitMod, TOTAL_VALUE);
    float attPowerMultiplier = GetPctModifierValue(unitMod, TOTAL_PCT) - 1.0f;

    // UNIT_FIELD_(RANGED)_ATTACK_POWER field
    SetInt32Value(UNIT_FIELD_ATTACK_POWER, int32(base_attPower));
    // UNIT_FIELD_(RANGED)_ATTACK_POWER_MOD_POS field
    SetInt32Value(UNIT_FIELD_ATTACK_POWER_MOD_POS, int32(attPowerMod > 0.f ? attPowerMod : 0.f));
    // UNIT_FIELD_(RANGED)_ATTACK_POWER_MOD_NEG field
    SetInt32Value(UNIT_FIELD_ATTACK_POWER_MOD_NEG, int32(attPowerMod < 0.f ? -attPowerMod : 0.f));
    // UNIT_FIELD_(RANGED)_ATTACK_POWER_MULTIPLIER field
    SetFloatValue(UNIT_FIELD_ATTACK_POWER_MULTIPLIER, attPowerMultiplier);

    // automatically update weapon damage after attack power modification
    UpdateDamagePhysical(BASE_ATTACK);

    // update pet spell power
    int32 spellDamage = 0;
    for (auto itr : GetAuraEffectsByType(SPELL_AURA_MOD_DAMAGE_DONE))
        spellDamage += itr->GetAmount();

    SetBonusDamage(spellDamage);

    m_ownerSpellDamageBonus = 0;
    if (GetEntry() == ENTRY_FIRE_ELEMENTAL)
        if (Unit* owner = GetStatOwner())
            if (owner->GetTypeId() == TYPEID_PLAYER)
                m_ownerSpellDamageBonus = int32(owner->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_FIRE) * 0.5f);
}

void Guardian::UpdateDamagePhysical(WeaponAttackType attType)
{
    if (attType > BASE_ATTACK)
        return;

    float bonusDamage = 0.0f;
    if (m_owner && m_owner->GetTypeId() == TYPEID_PLAYER)
    {
        //force of nature
        if (GetEntry() == ENTRY_TREANT)
        {
            int32 spellDmg = int32(m_owner->GetUInt32Value(PLAYER_FIELD_MOD_DAMAGE_DONE_POS + AsUnderlyingType(SPELL_SCHOOL_NATURE))) + m_owner->GetUInt32Value(PLAYER_FIELD_MOD_DAMAGE_DONE_NEG + AsUnderlyingType(SPELL_SCHOOL_NATURE));
            if (spellDmg > 0)
                bonusDamage = spellDmg * 0.09f;
        }
    }

    UnitMods unitMod = UNIT_MOD_DAMAGE_MAINHAND;

    float att_speed = float(GetBaseAttackTime(BASE_ATTACK))/1000.0f;

    float base_value  = GetFlatModifierValue(unitMod, BASE_VALUE) + GetTotalAttackPowerValue(attType) / 14.0f * att_speed + bonusDamage;
    float base_pct    = GetPctModifierValue(unitMod, BASE_PCT);
    float total_value = GetFlatModifierValue(unitMod, TOTAL_VALUE);
    float total_pct   = GetPctModifierValue(unitMod, TOTAL_PCT);

    float weapon_mindamage = GetWeaponDamageRange(BASE_ATTACK, MINDAMAGE);
    float weapon_maxdamage = GetWeaponDamageRange(BASE_ATTACK, MAXDAMAGE);

    float mindamage = ((base_value + weapon_mindamage) * base_pct + total_value) * total_pct;
    float maxdamage = ((base_value + weapon_maxdamage) * base_pct + total_value) * total_pct;

    /// @todo: remove this
    Unit::AuraEffectList const& mDummy = GetAuraEffectsByType(SPELL_AURA_MOD_ATTACKSPEED);
    for (Unit::AuraEffectList::const_iterator itr = mDummy.begin(); itr != mDummy.end(); ++itr)
    {
        switch ((*itr)->GetSpellInfo()->Id)
        {
            case 61682:
            case 61683:
                AddPct(mindamage, -(*itr)->GetAmount());
                AddPct(maxdamage, -(*itr)->GetAmount());
                break;
            default:
                break;
        }
    }

    SetStatFloatValue(UNIT_FIELD_MINDAMAGE, mindamage);
    SetStatFloatValue(UNIT_FIELD_MAXDAMAGE, maxdamage);
}

void Guardian::SetBonusDamage(int32 damage)
{
    m_bonusSpellDamage = damage;
    if (GetOwner()->GetTypeId() == TYPEID_PLAYER)
        GetOwner()->SetUInt32Value(PLAYER_PET_SPELL_POWER, damage);
}
