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

/*
 * Scripts for spells with SPELLFAMILY_GENERIC which cannot be included in AI script file
 * of creature using it or can't be bound to any player class.
 * Ordered alphabetically using scriptname.
 * Scriptnames of files in this file should be prefixed with "spell_gen_"
 */

#include "ScriptMgr.h"
#include "Battleground.h"
#include "CellImpl.h"
#include "Containers.h"
#include "DBCStores.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "InstanceScript.h"
#include "Item.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "ReputationMgr.h"
#include "SkillDiscovery.h"
#include "SpellAuraEffects.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "Vehicle.h"
#include "CreatureAIImpl.h"

#include "spell_generic_registration.h"

namespace Spells::Generic
{
enum RequiredMixologySpells
{
    SPELL_MIXOLOGY                      = 53042,
    // Flasks
    SPELL_FLASK_OF_THE_FROST_WYRM       = 53755,
    SPELL_FLASK_OF_STONEBLOOD           = 53758,
    SPELL_FLASK_OF_ENDLESS_RAGE         = 53760,
    SPELL_FLASK_OF_PURE_MOJO            = 54212,
    SPELL_LESSER_FLASK_OF_RESISTANCE    = 62380,
    SPELL_LESSER_FLASK_OF_TOUGHNESS     = 53752,
    SPELL_FLASK_OF_BLINDING_LIGHT       = 28521,
    SPELL_FLASK_OF_CHROMATIC_WONDER     = 42735,
    SPELL_FLASK_OF_FORTIFICATION        = 28518,
    SPELL_FLASK_OF_MIGHTY_RESTORATION   = 28519,
    SPELL_FLASK_OF_PURE_DEATH           = 28540,
    SPELL_FLASK_OF_RELENTLESS_ASSAULT   = 28520,
    SPELL_FLASK_OF_CHROMATIC_RESISTANCE = 17629,
    SPELL_FLASK_OF_DISTILLED_WISDOM     = 17627,
    SPELL_FLASK_OF_SUPREME_POWER        = 17628,
    SPELL_FLASK_OF_THE_TITANS           = 17626,
    // Elixirs
    SPELL_ELIXIR_OF_MIGHTY_AGILITY      = 28497,
    SPELL_ELIXIR_OF_ACCURACY            = 60340,
    SPELL_ELIXIR_OF_DEADLY_STRIKES      = 60341,
    SPELL_ELIXIR_OF_MIGHTY_DEFENSE      = 60343,
    SPELL_ELIXIR_OF_EXPERTISE           = 60344,
    SPELL_ELIXIR_OF_ARMOR_PIERCING      = 60345,
    SPELL_ELIXIR_OF_LIGHTNING_SPEED     = 60346,
    SPELL_ELIXIR_OF_MIGHTY_FORTITUDE    = 53751,
    SPELL_ELIXIR_OF_MIGHTY_MAGEBLOOD    = 53764,
    SPELL_ELIXIR_OF_MIGHTY_STRENGTH     = 53748,
    SPELL_ELIXIR_OF_MIGHTY_TOUGHTS      = 60347,
    SPELL_ELIXIR_OF_PROTECTION          = 53763,
    SPELL_ELIXIR_OF_SPIRIT              = 53747,
    SPELL_GURUS_ELIXIR                  = 53749,
    SPELL_SHADOWPOWER_ELIXIR            = 33721,
    SPELL_WRATH_ELIXIR                  = 53746,
    SPELL_ELIXIR_OF_EMPOWERMENT         = 28514,
    SPELL_ELIXIR_OF_MAJOR_MAGEBLOOD     = 28509,
    SPELL_ELIXIR_OF_MAJOR_SHADOW_POWER  = 28503,
    SPELL_ELIXIR_OF_MAJOR_DEFENSE       = 28502,
    SPELL_FEL_STRENGTH_ELIXIR           = 38954,
    SPELL_ELIXIR_OF_IRONSKIN            = 39628,
    SPELL_ELIXIR_OF_MAJOR_AGILITY       = 54494,
    SPELL_ELIXIR_OF_DRAENIC_WISDOM      = 39627,
    SPELL_ELIXIR_OF_MAJOR_FIREPOWER     = 28501,
    SPELL_ELIXIR_OF_MAJOR_FROST_POWER   = 28493,
    SPELL_EARTHEN_ELIXIR                = 39626,
    SPELL_ELIXIR_OF_MASTERY             = 33726,
    SPELL_ELIXIR_OF_HEALING_POWER       = 28491,
    SPELL_ELIXIR_OF_MAJOR_FORTITUDE     = 39625,
    SPELL_ELIXIR_OF_MAJOR_STRENGTH      = 28490,
    SPELL_ADEPTS_ELIXIR                 = 54452,
    SPELL_ONSLAUGHT_ELIXIR              = 33720,
    SPELL_MIGHTY_TROLLS_BLOOD_ELIXIR    = 24361,
    SPELL_GREATER_ARCANE_ELIXIR         = 17539,
    SPELL_ELIXIR_OF_THE_MONGOOSE        = 17538,
    SPELL_ELIXIR_OF_BRUTE_FORCE         = 17537,
    SPELL_ELIXIR_OF_SAGES               = 17535,
    SPELL_ELIXIR_OF_SUPERIOR_DEFENSE    = 11348,
    SPELL_ELIXIR_OF_DEMONSLAYING        = 11406,
    SPELL_ELIXIR_OF_GREATER_FIREPOWER   = 26276,
    SPELL_ELIXIR_OF_SHADOW_POWER        = 11474,
    SPELL_MAGEBLOOD_ELIXIR              = 24363,
    SPELL_ELIXIR_OF_GIANTS              = 11405,
    SPELL_ELIXIR_OF_GREATER_AGILITY     = 11334,
    SPELL_ARCANE_ELIXIR                 = 11390,
    SPELL_ELIXIR_OF_GREATER_INTELLECT   = 11396,
    SPELL_ELIXIR_OF_GREATER_DEFENSE     = 11349,
    SPELL_ELIXIR_OF_FROST_POWER         = 21920,
    SPELL_ELIXIR_OF_AGILITY             = 11328,
    SPELL_MAJOR_TROLLS_BLLOOD_ELIXIR    =  3223,
    SPELL_ELIXIR_OF_FORTITUDE           =  3593,
    SPELL_ELIXIR_OF_OGRES_STRENGTH      =  3164,
    SPELL_ELIXIR_OF_FIREPOWER           =  7844,
    SPELL_ELIXIR_OF_LESSER_AGILITY      =  3160,
    SPELL_ELIXIR_OF_DEFENSE             =  3220,
    SPELL_STRONG_TROLLS_BLOOD_ELIXIR    =  3222,
    SPELL_ELIXIR_OF_MINOR_ACCURACY      = 63729,
    SPELL_ELIXIR_OF_WISDOM              =  3166,
    SPELL_ELIXIR_OF_GIANTH_GROWTH       =  8212,
    SPELL_ELIXIR_OF_MINOR_AGILITY       =  2374,
    SPELL_ELIXIR_OF_MINOR_FORTITUDE     =  2378,
    SPELL_WEAK_TROLLS_BLOOD_ELIXIR      =  3219,
    SPELL_ELIXIR_OF_LIONS_STRENGTH      =  2367,
    SPELL_ELIXIR_OF_MINOR_DEFENSE       =   673
};

class spell_gen_mixology_bonus : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MIXOLOGY });
    }

    bool Load() override
    {
        return GetCaster() && GetCaster()->GetTypeId() == TYPEID_PLAYER;
    }

    void SetBonusValueForEffect(SpellEffIndex effIndex, int32 value, AuraEffect const* aurEff)
    {
        if (aurEff->GetEffIndex() == uint32(effIndex))
            bonus = value;
    }

    void CalculateAmount(AuraEffect const* aurEff, int32& amount, bool& /*canBeRecalculated*/)
        {
            if (GetCaster()->HasAura(SPELL_MIXOLOGY) && GetCaster()->HasSpell(GetSpellInfo()->Effects[EFFECT_0].TriggerSpell))
            {
                switch (GetId())
                {
                    case SPELL_WEAK_TROLLS_BLOOD_ELIXIR:
                    case SPELL_MAGEBLOOD_ELIXIR:
                        bonus = amount;
                        break;
                    case SPELL_ELIXIR_OF_FROST_POWER:
                    case SPELL_LESSER_FLASK_OF_TOUGHNESS:
                    case SPELL_LESSER_FLASK_OF_RESISTANCE:
                        bonus = CalculatePct(amount, 80);
                        break;
                    case SPELL_ELIXIR_OF_MINOR_DEFENSE:
                    case SPELL_ELIXIR_OF_LIONS_STRENGTH:
                    case SPELL_ELIXIR_OF_MINOR_AGILITY:
                    case SPELL_MAJOR_TROLLS_BLLOOD_ELIXIR:
                    case SPELL_ELIXIR_OF_SHADOW_POWER:
                    case SPELL_ELIXIR_OF_BRUTE_FORCE:
                    case SPELL_MIGHTY_TROLLS_BLOOD_ELIXIR:
                    case SPELL_ELIXIR_OF_GREATER_FIREPOWER:
                    case SPELL_ONSLAUGHT_ELIXIR:
                    case SPELL_EARTHEN_ELIXIR:
                    case SPELL_ELIXIR_OF_MAJOR_AGILITY:
                    case SPELL_FLASK_OF_THE_TITANS:
                    case SPELL_FLASK_OF_RELENTLESS_ASSAULT:
                    case SPELL_FLASK_OF_STONEBLOOD:
                    case SPELL_ELIXIR_OF_MINOR_ACCURACY:
                        bonus = CalculatePct(amount, 50);
                        break;
                    case SPELL_ELIXIR_OF_PROTECTION:
                        bonus = 280;
                        break;
                    case SPELL_ELIXIR_OF_MAJOR_DEFENSE:
                        bonus = 200;
                        break;
                    case SPELL_ELIXIR_OF_GREATER_DEFENSE:
                    case SPELL_ELIXIR_OF_SUPERIOR_DEFENSE:
                        bonus = 140;
                        break;
                    case SPELL_ELIXIR_OF_FORTITUDE:
                        bonus = 100;
                        break;
                    case SPELL_FLASK_OF_ENDLESS_RAGE:
                        bonus = 82;
                        break;
                    case SPELL_ELIXIR_OF_DEFENSE:
                        bonus = 70;
                        break;
                    case SPELL_ELIXIR_OF_DEMONSLAYING:
                        bonus = 50;
                        break;
                    case SPELL_FLASK_OF_THE_FROST_WYRM:
                        bonus = 47;
                        break;
                    case SPELL_WRATH_ELIXIR:
                        bonus = 32;
                        break;
                    case SPELL_ELIXIR_OF_MAJOR_FROST_POWER:
                    case SPELL_ELIXIR_OF_MAJOR_FIREPOWER:
                    case SPELL_ELIXIR_OF_MAJOR_SHADOW_POWER:
                        bonus = 29;
                        break;
                    case SPELL_ELIXIR_OF_MIGHTY_TOUGHTS:
                        bonus = 27;
                        break;
                    case SPELL_FLASK_OF_SUPREME_POWER:
                    case SPELL_FLASK_OF_BLINDING_LIGHT:
                    case SPELL_FLASK_OF_PURE_DEATH:
                    case SPELL_SHADOWPOWER_ELIXIR:
                        bonus = 23;
                        break;
                    case SPELL_ELIXIR_OF_MIGHTY_AGILITY:
                    case SPELL_FLASK_OF_DISTILLED_WISDOM:
                    case SPELL_ELIXIR_OF_SPIRIT:
                    case SPELL_ELIXIR_OF_MIGHTY_STRENGTH:
                    case SPELL_FLASK_OF_PURE_MOJO:
                    case SPELL_ELIXIR_OF_ACCURACY:
                    case SPELL_ELIXIR_OF_DEADLY_STRIKES:
                    case SPELL_ELIXIR_OF_MIGHTY_DEFENSE:
                    case SPELL_ELIXIR_OF_EXPERTISE:
                    case SPELL_ELIXIR_OF_ARMOR_PIERCING:
                    case SPELL_ELIXIR_OF_LIGHTNING_SPEED:
                        bonus = 20;
                        break;
                    case SPELL_FLASK_OF_CHROMATIC_RESISTANCE:
                        bonus = 17;
                        break;
                    case SPELL_ELIXIR_OF_MINOR_FORTITUDE:
                    case SPELL_ELIXIR_OF_MAJOR_STRENGTH:
                        bonus = 15;
                        break;
                    case SPELL_FLASK_OF_MIGHTY_RESTORATION:
                        bonus = 13;
                        break;
                    case SPELL_ARCANE_ELIXIR:
                        bonus = 12;
                        break;
                    case SPELL_ELIXIR_OF_GREATER_AGILITY:
                    case SPELL_ELIXIR_OF_GIANTS:
                        bonus = 11;
                        break;
                    case SPELL_ELIXIR_OF_AGILITY:
                    case SPELL_ELIXIR_OF_GREATER_INTELLECT:
                    case SPELL_ELIXIR_OF_SAGES:
                    case SPELL_ELIXIR_OF_IRONSKIN:
                    case SPELL_ELIXIR_OF_MIGHTY_MAGEBLOOD:
                        bonus = 10;
                        break;
                    case SPELL_ELIXIR_OF_HEALING_POWER:
                        bonus = 9;
                        break;
                    case SPELL_ELIXIR_OF_DRAENIC_WISDOM:
                    case SPELL_GURUS_ELIXIR:
                        bonus = 8;
                        break;
                    case SPELL_ELIXIR_OF_FIREPOWER:
                    case SPELL_ELIXIR_OF_MAJOR_MAGEBLOOD:
                    case SPELL_ELIXIR_OF_MASTERY:
                        bonus = 6;
                        break;
                    case SPELL_ELIXIR_OF_LESSER_AGILITY:
                    case SPELL_ELIXIR_OF_OGRES_STRENGTH:
                    case SPELL_ELIXIR_OF_WISDOM:
                    case SPELL_ELIXIR_OF_THE_MONGOOSE:
                        bonus = 5;
                        break;
                    case SPELL_STRONG_TROLLS_BLOOD_ELIXIR:
                    case SPELL_FLASK_OF_CHROMATIC_WONDER:
                        bonus = 4;
                        break;
                    case SPELL_ELIXIR_OF_EMPOWERMENT:
                        bonus = -10;
                        break;
                    case SPELL_ADEPTS_ELIXIR:
                        SetBonusValueForEffect(EFFECT_0, 13, aurEff);
                        SetBonusValueForEffect(EFFECT_1, 13, aurEff);
                        SetBonusValueForEffect(EFFECT_2, 8, aurEff);
                        break;
                    case SPELL_ELIXIR_OF_MIGHTY_FORTITUDE:
                        SetBonusValueForEffect(EFFECT_0, 160, aurEff);
                        break;
                    case SPELL_ELIXIR_OF_MAJOR_FORTITUDE:
                        SetBonusValueForEffect(EFFECT_0, 116, aurEff);
                        SetBonusValueForEffect(EFFECT_1, 6, aurEff);
                        break;
                    case SPELL_FEL_STRENGTH_ELIXIR:
                        SetBonusValueForEffect(EFFECT_0, 40, aurEff);
                        SetBonusValueForEffect(EFFECT_1, 40, aurEff);
                        break;
                    case SPELL_FLASK_OF_FORTIFICATION:
                        SetBonusValueForEffect(EFFECT_0, 210, aurEff);
                        SetBonusValueForEffect(EFFECT_1, 5, aurEff);
                        break;
                    case SPELL_GREATER_ARCANE_ELIXIR:
                        SetBonusValueForEffect(EFFECT_0, 19, aurEff);
                        SetBonusValueForEffect(EFFECT_1, 19, aurEff);
                        SetBonusValueForEffect(EFFECT_2, 5, aurEff);
                        break;
                    case SPELL_ELIXIR_OF_GIANTH_GROWTH:
                        SetBonusValueForEffect(EFFECT_0, 5, aurEff);
                        break;
                    default:
                        TC_LOG_ERROR("spells", "SpellId %u couldn't be processed in spell_gen_mixology_bonus", GetId());
                        break;
                }
                amount += bonus;
            }
        }

    int32 bonus = 0;

    void Register() override
    {
        DoEffectCalcAmount.Register(&spell_gen_mixology_bonus::CalculateAmount, EFFECT_ALL, SPELL_AURA_ANY);
    }
};

enum LandmineKnockbackAchievement
{
    SPELL_LANDMINE_KNOCKBACK_ACHIEVEMENT = 57064
};

class spell_gen_landmine_knockback_achievement : public SpellScript
{
    void HandleScript(SpellEffIndex /*effIndex*/)
    {
        if (Player* target = GetHitPlayer())
        {
            Aura const* aura = GetHitAura();
            if (!aura || aura->GetStackAmount() < 10)
                return;

            target->CastSpell(target, SPELL_LANDMINE_KNOCKBACK_ACHIEVEMENT, true);
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_landmine_knockback_achievement::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

// 34098 - ClearAllDebuffs
class spell_gen_clear_debuffs : public SpellScript
{
    void HandleScript(SpellEffIndex /*effIndex*/)
    {
        if (Unit* target = GetHitUnit())
        {
            target->RemoveOwnedAuras([](Aura const* aura)
            {
                SpellInfo const* spellInfo = aura->GetSpellInfo();
                return !spellInfo->IsPositive() && !spellInfo->IsPassive();
            });
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_clear_debuffs::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

enum PonySpells
{
    ACHIEV_PONY_UP              = 3736,
    MOUNT_PONY                  = 29736
};

class spell_gen_pony_mount_check : public AuraScript
{
    void HandleEffectPeriodic(AuraEffect const* /*aurEff*/)
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;
        Player* owner = caster->GetOwner()->ToPlayer();
        if (!owner || !owner->HasAchieved(ACHIEV_PONY_UP))
            return;

        if (owner->IsMounted())
        {
            caster->Mount(MOUNT_PONY);
            caster->SetSpeedRate(MOVE_RUN, owner->GetSpeedRate(MOVE_RUN));
        }
        else if (caster->IsMounted())
        {
            caster->Dismount();
            caster->SetSpeedRate(MOVE_RUN, owner->GetSpeedRate(MOVE_RUN));
        }
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_gen_pony_mount_check::HandleEffectPeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

class spell_gen_shroud_of_death : public AuraScript
{
    void OnApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        PreventDefaultAction();
        GetUnitOwner()->m_serverSideVisibility.SetValue(SERVERSIDE_VISIBILITY_GHOST, GHOST_VISIBILITY_GHOST);
        GetUnitOwner()->m_serverSideVisibilityDetect.SetValue(SERVERSIDE_VISIBILITY_GHOST, GHOST_VISIBILITY_GHOST);
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        PreventDefaultAction();
        GetUnitOwner()->m_serverSideVisibility.SetValue(SERVERSIDE_VISIBILITY_GHOST, GHOST_VISIBILITY_ALIVE);
        GetUnitOwner()->m_serverSideVisibilityDetect.SetValue(SERVERSIDE_VISIBILITY_GHOST, GHOST_VISIBILITY_ALIVE);
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_shroud_of_death::OnApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        OnEffectRemove.Register(&spell_gen_shroud_of_death::OnRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

enum ArmorSpecializationSpells
{
    // Warrior
    SPELL_ARMOR_SPEC_WAR_ARMS           = 86110,
    SPELL_ARMOR_SPEC_WAR_FURY           = 86101,
    SPELL_ARMOR_SPEC_WAR_PROTECTION     = 86535,

    // Paladin
    SPELL_ARMOR_SPEC_PAL_HOLY           = 86103,
    SPELL_ARMOR_SPEC_PAL_PROTECTOION    = 86102,
    SPELL_ARMOR_SPEC_PAL_RETRIBUTION    = 86539,

    // Hunter
    SPELL_ARMOR_SPEC_HUN                = 86538,

    // Rogue
    SPELL_ARMOR_SPEC_ROG                = 86092,

    // Death Knight
    SPELL_ARMOR_SPEC_DK_BLOOD           = 86537,
    SPELL_ARMOR_SPEC_DK_FROST           = 86536,
    SPELL_ARMOR_SPEC_DK_UNHOLY          = 86113,

    // Shaman
    SPELL_ARMOR_SPEC_SHA_ELEMENTAL      = 86100,
    SPELL_ARMOR_SPEC_SHA_ENHANCEMENT    = 86099,
    SPELL_ARMOR_SPEC_SHA_RESTORATION    = 86108,

    // Druid
    SPELL_ARMOR_SPEC_DRU_BALANCE        = 86093,
    SPELL_ARMOR_SPEC_DRU_FREAL_BEAR     = 86096,
    SPELL_ARMOR_SPEC_DRU_FERAL          = 86097,
    SPELL_ARMOR_SPEC_DRU_RESTORATION    = 86104
};

class spell_gen_armor_specialization : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_ARMOR_SPEC_WAR_ARMS,
                SPELL_ARMOR_SPEC_WAR_FURY,
                SPELL_ARMOR_SPEC_WAR_PROTECTION,
                SPELL_ARMOR_SPEC_PAL_HOLY,
                SPELL_ARMOR_SPEC_PAL_PROTECTOION,
                SPELL_ARMOR_SPEC_PAL_RETRIBUTION,
                SPELL_ARMOR_SPEC_HUN,
                SPELL_ARMOR_SPEC_ROG,
                SPELL_ARMOR_SPEC_DK_BLOOD,
                SPELL_ARMOR_SPEC_DK_FROST,
                SPELL_ARMOR_SPEC_DK_UNHOLY,
                SPELL_ARMOR_SPEC_SHA_ELEMENTAL,
                SPELL_ARMOR_SPEC_SHA_ENHANCEMENT,
                SPELL_ARMOR_SPEC_SHA_RESTORATION,
                SPELL_ARMOR_SPEC_DRU_BALANCE,
                SPELL_ARMOR_SPEC_DRU_FREAL_BEAR,
                SPELL_ARMOR_SPEC_DRU_FERAL,
                SPELL_ARMOR_SPEC_DRU_RESTORATION
            });
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        Player* player = GetHitPlayer();
        if (!player)
            return;

        uint32 spellId = 0;

        switch (player->GetPrimaryTalentTree(player->GetActiveSpec()))
        {
            case TALENT_TREE_WARRIOR_ARMS:
                spellId = SPELL_ARMOR_SPEC_WAR_ARMS;
                break;
            case TALENT_TREE_WARRIOR_FURY:
                spellId = SPELL_ARMOR_SPEC_WAR_FURY;
                break;
            case TALENT_TREE_WARRIOR_PROTECTION:
                spellId = SPELL_ARMOR_SPEC_WAR_PROTECTION;
                break;
            case TALENT_TREE_PALADIN_HOLY:
                spellId = SPELL_ARMOR_SPEC_PAL_HOLY;
                break;
            case TALENT_TREE_PALADIN_PROTECTION:
                spellId = SPELL_ARMOR_SPEC_PAL_PROTECTOION;
                break;
            case TALENT_TREE_PALADIN_RETRIBUTION:
                spellId = SPELL_ARMOR_SPEC_PAL_RETRIBUTION;
                break;
            case TALENT_TREE_HUNTER_BEAST_MASTERY:
            case TALENT_TREE_HUNTER_MARKSMANSHIP:
            case TALENT_TREE_HUNTER_SURVIVAL:
                spellId = SPELL_ARMOR_SPEC_HUN;
                break;
            case TALENT_TREE_ROGUE_ASSASSINATION:
            case TALENT_TREE_ROGUE_COMBAT:
            case TALENT_TREE_ROGUE_SUBTLETY:
                spellId = SPELL_ARMOR_SPEC_ROG;
                break;
            case TALENT_TREE_DEATH_KNIGHT_BLOOD:
                spellId = SPELL_ARMOR_SPEC_DK_BLOOD;
                break;
            case TALENT_TREE_DEATH_KNIGHT_FROST:
                spellId = SPELL_ARMOR_SPEC_DK_FROST;
                break;
            case TALENT_TREE_DEATH_KNIGHT_UNHOLY:
                spellId = SPELL_ARMOR_SPEC_DK_UNHOLY;
                break;
            case TALENT_TREE_SHAMAN_ELEMENTAL:
                spellId = SPELL_ARMOR_SPEC_SHA_ELEMENTAL;
                break;
            case TALENT_TREE_SHAMAN_ENHANCEMENT:
                spellId = SPELL_ARMOR_SPEC_SHA_ENHANCEMENT;
                break;
            case TALENT_TREE_SHAMAN_RESTORATION:
                spellId = SPELL_ARMOR_SPEC_SHA_RESTORATION;
                break;
            case TALENT_TREE_DRUID_BALANCE:
                spellId = SPELL_ARMOR_SPEC_DRU_BALANCE;
                break;
            case TALENT_TREE_DRUID_FERAL_COMBAT:
            {
                if (player->GetShapeshiftForm() == FORM_BEAR)
                    spellId = SPELL_ARMOR_SPEC_DRU_FREAL_BEAR;
                else
                    spellId = SPELL_ARMOR_SPEC_DRU_FERAL;
                break;
            }
            case TALENT_TREE_DRUID_RESTORATION:
                spellId = SPELL_ARMOR_SPEC_DRU_RESTORATION;
                break;
            default:
                return;
        }

        if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId))
            if (player->HasAllItemsToFitToSpellRequirements(spellInfo))
                player->CastSpell(player, spellId, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_armor_specialization::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

enum PvPTrinket
{
    SPELL_PVP_TRINKET_ALLIANCE  = 97403,
    SPELL_PVP_TRINKET_HORDE     = 97404,
    SPELL_PVP_TRINKET_NEUTRAL   = 97979,
    SPELL_EVERY_MAN_FOR_HIMSELF = 59752
};

class spell_gen_pvp_trinket : public SpellScript
{
    void HandlePvPTrinketVisual()
    {
        if (Unit* caster = GetCaster())
        {
            if (caster->GetTypeId() == TYPEID_PLAYER && GetSpellInfo()->Id != SPELL_EVERY_MAN_FOR_HIMSELF)
                caster->CastSpell(caster, caster->ToPlayer()->GetTeam() == ALLIANCE ? SPELL_PVP_TRINKET_ALLIANCE : SPELL_PVP_TRINKET_HORDE, true);
            else
                caster->CastSpell(caster, SPELL_PVP_TRINKET_NEUTRAL, true);
        }
    }

    void Register() override
    {
        AfterHit.Register(&spell_gen_pvp_trinket::HandlePvPTrinketVisual);
    }
};

enum Blink
{
    SPELL_BLINK_TARGET = 28401
};

class spell_gen_blink : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_BLINK_TARGET });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        Trinity::Containers::RandomResize(targets, 1);
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        if (!caster || !caster->IsCreature())
            return;

        Creature* creature = caster->ToCreature();
        if (Unit* target = creature->GetThreatManager().GetCurrentVictim())
        {
            creature->GetThreatManager().ResetThreat(target);
            if (creature->IsAIEnabled())
            {
                creature->CastSpell(target, SPELL_BLINK_TARGET, true);
                creature->AI()->AttackStart(target);
            }
        }
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_gen_blink::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
        OnEffectHitTarget.Register(&spell_gen_blink::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_gen_toxic_blow_dart : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        Trinity::Containers::RandomResize(targets, 1);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_gen_toxic_blow_dart::FilterTargets, EFFECT_ALL, TARGET_UNIT_SRC_AREA_ENEMY);
    }
};

enum ProjectileGoods
{
    SPELL_PROJECTILE_GOODS_1    = 84136,
    SPELL_PROJECTILE_GOODS_2    = 84138,
    SPELL_PROJECTILE_GOODS_3    = 84141,
    SPELL_PROJECTILE_GOODS_4    = 84142
};

class spell_gen_projectile_goods : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_PROJECTILE_GOODS_1,
                SPELL_PROJECTILE_GOODS_2,
                SPELL_PROJECTILE_GOODS_3,
                SPELL_PROJECTILE_GOODS_4,
            });
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        uint32 spellId = 0;
        switch (RAND(0, 3))
        {
            case 0:
                spellId = SPELL_PROJECTILE_GOODS_1;
                break;
            case 1:
                spellId = SPELL_PROJECTILE_GOODS_2;
                break;
            case 2:
                spellId = SPELL_PROJECTILE_GOODS_3;
                break;
            case 3:
                spellId = SPELL_PROJECTILE_GOODS_4;
                break;
        }
        GetCaster()->CastSpell(GetHitUnit(), spellId, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_projectile_goods::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};


void RegisterBonusesUtilities13()
{
    RegisterSpellScript(spell_gen_mixology_bonus);
    RegisterSpellScript(spell_gen_landmine_knockback_achievement);
    RegisterSpellScript(spell_gen_clear_debuffs);
    RegisterSpellScript(spell_gen_pony_mount_check);
    RegisterSpellScript(spell_gen_shroud_of_death);
    RegisterSpellScript(spell_gen_armor_specialization);
    RegisterSpellScript(spell_gen_pvp_trinket);
    RegisterSpellScript(spell_gen_blink);
    RegisterSpellScript(spell_gen_toxic_blow_dart);
    RegisterSpellScript(spell_gen_projectile_goods);
}
}
