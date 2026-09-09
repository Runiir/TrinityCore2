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
enum ObsidianArmor
{
    SPELL_GEN_OBSIDIAN_ARMOR_HOLY       = 27536,
    SPELL_GEN_OBSIDIAN_ARMOR_FIRE       = 27533,
    SPELL_GEN_OBSIDIAN_ARMOR_NATURE     = 27538,
    SPELL_GEN_OBSIDIAN_ARMOR_FROST      = 27534,
    SPELL_GEN_OBSIDIAN_ARMOR_SHADOW     = 27535,
    SPELL_GEN_OBSIDIAN_ARMOR_ARCANE     = 27540
};

// 27539 - Obsidian Armor
class spell_gen_obsidian_armor : public SpellScriptLoader
{
    public:
        spell_gen_obsidian_armor() : SpellScriptLoader("spell_gen_obsidian_armor") { }

        class spell_gen_obsidian_armor_AuraScript : public AuraScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                return ValidateSpellInfo(
                {
                    SPELL_GEN_OBSIDIAN_ARMOR_HOLY,
                    SPELL_GEN_OBSIDIAN_ARMOR_FIRE,
                    SPELL_GEN_OBSIDIAN_ARMOR_NATURE,
                    SPELL_GEN_OBSIDIAN_ARMOR_FROST,
                    SPELL_GEN_OBSIDIAN_ARMOR_SHADOW,
                    SPELL_GEN_OBSIDIAN_ARMOR_ARCANE
                });
            }

            bool CheckProc(ProcEventInfo& eventInfo)
            {
                DamageInfo* damageInfo = eventInfo.GetDamageInfo();
                if (!damageInfo || !damageInfo->GetSpellInfo())
                    return false;

                if (GetFirstSchoolInMask(eventInfo.GetSchoolMask()) == SPELL_SCHOOL_NORMAL)
                    return false;

                return true;
            }

            void OnProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
            {
                PreventDefaultAction();

                uint32 spellId = 0;
                switch (GetFirstSchoolInMask(eventInfo.GetSchoolMask()))
                {
                    case SPELL_SCHOOL_HOLY:
                        spellId = SPELL_GEN_OBSIDIAN_ARMOR_HOLY;
                        break;
                    case SPELL_SCHOOL_FIRE:
                        spellId = SPELL_GEN_OBSIDIAN_ARMOR_FIRE;
                        break;
                    case SPELL_SCHOOL_NATURE:
                        spellId = SPELL_GEN_OBSIDIAN_ARMOR_NATURE;
                        break;
                    case SPELL_SCHOOL_FROST:
                        spellId = SPELL_GEN_OBSIDIAN_ARMOR_FROST;
                        break;
                    case SPELL_SCHOOL_SHADOW:
                        spellId = SPELL_GEN_OBSIDIAN_ARMOR_SHADOW;
                        break;
                    case SPELL_SCHOOL_ARCANE:
                        spellId = SPELL_GEN_OBSIDIAN_ARMOR_ARCANE;
                        break;
                    default:
                        return;
                }
                GetTarget()->CastSpell(GetTarget(), spellId, aurEff);
            }

            void Register() override
            {
                DoCheckProc.Register(&spell_gen_obsidian_armor_AuraScript::CheckProc);
                OnEffectProc.Register(&spell_gen_obsidian_armor_AuraScript::OnProc, EFFECT_0, SPELL_AURA_DUMMY);
            }
        };

        AuraScript* GetAuraScript() const override
        {
            return new spell_gen_obsidian_armor_AuraScript();
        }
};

class spell_gen_oracle_wolvar_reputation : public SpellScriptLoader
{
    public:
        spell_gen_oracle_wolvar_reputation() : SpellScriptLoader("spell_gen_oracle_wolvar_reputation") { }

        class spell_gen_oracle_wolvar_reputation_SpellScript : public SpellScript
        {
            bool Load() override
            {
                return GetCaster()->GetTypeId() == TYPEID_PLAYER;
            }

            void HandleDummy(SpellEffIndex effIndex)
            {
                Player* player = GetCaster()->ToPlayer();
                uint32 factionId = GetSpellInfo()->Effects[effIndex].CalcValue();
                int32  repChange = GetSpellInfo()->Effects[EFFECT_1].CalcValue();

                FactionEntry const* factionEntry = sFactionStore.LookupEntry(factionId);
                if (!factionEntry)
                    return;

                // Set rep to baserep + basepoints (expecting spillover for oposite faction -> become hated)
                // Not when player already has equal or higher rep with this faction
                if (player->GetReputationMgr().GetReputation(factionEntry) < repChange)
                    player->GetReputationMgr().SetReputation(factionEntry, repChange);

                // EFFECT_INDEX_2 most likely update at war state, we already handle this in SetReputation
            }

            void Register() override
            {
                OnEffectHit.Register(&spell_gen_oracle_wolvar_reputation_SpellScript::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
            }
        };

        SpellScript* GetSpellScript() const override
        {
            return new spell_gen_oracle_wolvar_reputation_SpellScript();
        }
};

enum OrcDisguiseSpells
{
    SPELL_ORC_DISGUISE_TRIGGER       = 45759,
    SPELL_ORC_DISGUISE_MALE          = 45760,
    SPELL_ORC_DISGUISE_FEMALE        = 45762
};

class spell_gen_orc_disguise : public SpellScriptLoader
{
    public:
        spell_gen_orc_disguise() : SpellScriptLoader("spell_gen_orc_disguise") { }

        class spell_gen_orc_disguise_SpellScript : public SpellScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                return ValidateSpellInfo(
                {
                    SPELL_ORC_DISGUISE_TRIGGER,
                    SPELL_ORC_DISGUISE_MALE,
                    SPELL_ORC_DISGUISE_FEMALE
                });
            }

            void HandleScript(SpellEffIndex /*effIndex*/)
            {
                Unit* caster = GetCaster();
                if (Player* target = GetHitPlayer())
                {
                    uint8 gender = target->getGender();
                    if (!gender)
                        caster->CastSpell(target, SPELL_ORC_DISGUISE_MALE, true);
                    else
                        caster->CastSpell(target, SPELL_ORC_DISGUISE_FEMALE, true);
                }
            }

            void Register() override
            {
                OnEffectHitTarget.Register(&spell_gen_orc_disguise_SpellScript::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
            }
        };

        SpellScript* GetSpellScript() const override
        {
            return new spell_gen_orc_disguise_SpellScript();
        }
};

enum ParalyticPoison
{
    SPELL_PARALYSIS = 35202
};

// 35201 - Paralytic Poison
class spell_gen_paralytic_poison : public SpellScriptLoader
{
    public:
        spell_gen_paralytic_poison() : SpellScriptLoader("spell_gen_paralytic_poison") { }

        class spell_gen_paralytic_poison_AuraScript : public AuraScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                return ValidateSpellInfo({ SPELL_PARALYSIS });
            }

            void HandleStun(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
            {
                if (!GetTargetApplication()->GetRemoveMode().HasFlag(AuraRemoveFlags::Expired))
                    return;

                GetTarget()->CastSpell(nullptr, SPELL_PARALYSIS, aurEff);
            }

            void Register() override
            {
                AfterEffectRemove.Register(&spell_gen_paralytic_poison_AuraScript::HandleStun, EFFECT_0, SPELL_AURA_PERIODIC_DAMAGE, AURA_EFFECT_HANDLE_REAL);
            }
        };

        AuraScript* GetAuraScript() const override
        {
            return new spell_gen_paralytic_poison_AuraScript();
        }
};

class spell_gen_prevent_emotes : public AuraScript
{
    void HandleEffectApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT);
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT);
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_prevent_emotes::HandleEffectApply, SpellEffIndex(EFFECT_FIRST_FOUND), SPELL_AURA_ANY, AURA_EFFECT_HANDLE_REAL);
        OnEffectRemove.Register(&spell_gen_prevent_emotes::OnRemove, SpellEffIndex(EFFECT_FIRST_FOUND), SPELL_AURA_ANY, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_gen_proc_below_pct_damaged : public AuraScript
{
    bool CheckProc(ProcEventInfo& eventInfo)
    {
        DamageInfo* damageInfo = eventInfo.GetDamageInfo();
        if (!damageInfo || !damageInfo->GetDamage())
            return false;

        int32 pct = GetSpellInfo()->Effects[EFFECT_0].CalcValue();

        if (eventInfo.GetActionTarget()->HealthBelowPctDamaged(pct, damageInfo->GetDamage()))
            return true;

        return false;
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_gen_proc_below_pct_damaged::CheckProc);
    }
};

class spell_gen_proc_charge_drop_only : public SpellScriptLoader
{
    public:
        spell_gen_proc_charge_drop_only() : SpellScriptLoader("spell_gen_proc_charge_drop_only") { }

        class spell_gen_proc_charge_drop_only_AuraScript : public AuraScript
        {
            void HandleChargeDrop(ProcEventInfo& /*eventInfo*/)
            {
                PreventDefaultAction();
            }

            void Register() override
            {
                OnProc.Register(&spell_gen_proc_charge_drop_only_AuraScript::HandleChargeDrop);
            }
        };

        AuraScript* GetAuraScript() const override
        {
            return new spell_gen_proc_charge_drop_only_AuraScript();
        }
};

enum ParachuteSpells
{
    SPELL_PARACHUTE         = 45472,
    SPELL_PARACHUTE_BUFF    = 44795,
};

// 45472 Parachute
class spell_gen_parachute : public SpellScriptLoader
{
    public:
        spell_gen_parachute() : SpellScriptLoader("spell_gen_parachute") { }

        class spell_gen_parachute_AuraScript : public AuraScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                return ValidateSpellInfo(
                {
                    SPELL_PARACHUTE,
                    SPELL_PARACHUTE_BUFF
                });
            }

            void HandleEffectPeriodic(AuraEffect const* /*aurEff*/)
            {
                if (Player* target = GetTarget()->ToPlayer())
                    if (target->IsFalling())
                    {
                        target->RemoveAurasDueToSpell(SPELL_PARACHUTE);
                        target->CastSpell(target, SPELL_PARACHUTE_BUFF, true);
                    }
            }

            void Register() override
            {
                OnEffectPeriodic.Register(&spell_gen_parachute_AuraScript::HandleEffectPeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
            }
        };

        AuraScript* GetAuraScript() const override
        {
            return new spell_gen_parachute_AuraScript();
        }
};

enum PetSummoned
{
    NPC_DOOMGUARD       = 11859,
    NPC_INFERNAL        = 89,
    NPC_IMP             = 416
};

class spell_gen_pet_summoned : public SpellScriptLoader
{
    public:
        spell_gen_pet_summoned() : SpellScriptLoader("spell_gen_pet_summoned") { }

        class spell_gen_pet_summoned_SpellScript : public SpellScript
        {
            bool Load() override
            {
                return GetCaster()->GetTypeId() == TYPEID_PLAYER;
            }

            void HandleScript(SpellEffIndex /*effIndex*/)
            {
                Player* player = GetCaster()->ToPlayer();
                if (player->GetLastPetNumber())
                {
                    PetType newPetType = (player->getClass() == CLASS_HUNTER) ? HUNTER_PET : SUMMON_PET;
                    Pet* newPet = new Pet(player, newPetType);
                    if (newPet->LoadPetData(player, 0, player->GetLastPetNumber(), true))
                    {
                        // revive the pet if it is dead
                        if (newPet->getDeathState() == DEAD)
                            newPet->setDeathState(ALIVE);

                        newPet->SetFullHealth();
                        newPet->SetPower(newPet->GetPowerType(), newPet->GetMaxPower(newPet->GetPowerType()));

                        switch (newPet->GetEntry())
                        {
                            case NPC_DOOMGUARD:
                            case NPC_INFERNAL:
                                newPet->SetEntry(NPC_IMP);
                                break;
                            default:
                                break;
                        }
                    }
                    else
                        delete newPet;
                }
            }

            void Register() override
            {
                OnEffectHitTarget.Register(&spell_gen_pet_summoned_SpellScript::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
            }
        };

        SpellScript* GetSpellScript() const override
        {
            return new spell_gen_pet_summoned_SpellScript();
        }
};

class spell_gen_profession_research : public SpellScript
{
    bool Load() override
    {
        return GetCaster()->GetTypeId() == TYPEID_PLAYER;
    }

    SpellCastResult CheckRequirement()
    {
        if (HasDiscoveredAllSpells(GetSpellInfo()->Id, GetCaster()->ToPlayer()))
        {
            SetCustomCastResultMessage(SPELL_CUSTOM_ERROR_NOTHING_TO_DISCOVER);
            return SPELL_FAILED_CUSTOM_ERROR;
        }

        return SPELL_CAST_OK;
    }

    void HandleScript(SpellEffIndex /*effIndex*/)
    {
        Player* caster = GetCaster()->ToPlayer();
        uint32 spellId = GetSpellInfo()->Id;

        // learn random explicit discovery recipe (if any)
        if (uint32 discoveredSpellId = GetExplicitDiscoverySpell(spellId, caster))
            caster->LearnSpell(discoveredSpellId, false);

        caster->UpdateCraftSkill(GetSpellInfo());
    }

    void Register() override
    {
        OnCheckCast.Register(&spell_gen_profession_research::CheckRequirement);
        OnEffectHitTarget.Register(&spell_gen_profession_research::HandleScript, EFFECT_1, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_gen_remove_flight_auras : public SpellScript
{
    void HandleScript(SpellEffIndex /*effIndex*/)
    {
        if (Unit* target = GetHitUnit())
        {
            target->RemoveAurasByType(SPELL_AURA_FLY);
            target->RemoveAurasByType(SPELL_AURA_MOD_INCREASE_MOUNTED_FLIGHT_SPEED);
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_remove_flight_auras::HandleScript, EFFECT_1, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

enum Replenishment
{
    SPELL_REPLENISHMENT             = 57669,
    SPELL_INFINITE_REPLENISHMENT    = 61782
};

class ReplenishmentCheck
{
public:
    bool operator()(WorldObject* obj) const
    {
        if (Unit* target = obj->ToUnit())
            return target->GetPowerType() != POWER_MANA;

        return true;
    }
};

class spell_gen_replenishment : public SpellScript
{
    void RemoveInvalidTargets(std::list<WorldObject*>& targets)
    {
        // In arenas Replenishment may only affect the caster
        if (Player* caster = GetCaster()->ToPlayer())
        {
            if (caster->InArena())
            {
                targets.clear();
                targets.push_back(caster);
                return;
            }
        }

        targets.remove_if(ReplenishmentCheck());

        uint8 const maxTargets = 10;

        if (targets.size() > maxTargets)
        {
            targets.sort(Trinity::PowerPctOrderPred(POWER_MANA));
            targets.resize(maxTargets);
        }
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_gen_replenishment::RemoveInvalidTargets, EFFECT_ALL, TARGET_UNIT_CASTER_AREA_RAID);
    }
};

class spell_gen_replenishment_AuraScript : public AuraScript
{
    bool Load() override
    {
        return GetUnitOwner()->GetPowerType() == POWER_MANA;
    }

    void CalculateAmount(AuraEffect const* /*aurEff*/, int32& amount, bool& /*canBeRecalculated*/)
    {
        switch (GetSpellInfo()->Id)
        {
            case SPELL_REPLENISHMENT:
            case SPELL_INFINITE_REPLENISHMENT:
                amount = CalculatePct(GetUnitOwner()->GetMaxPower(POWER_MANA), 0.1f);
                break;
            default:
                break;
        }
    }

    void Register() override
    {
        DoEffectCalcAmount.Register(&spell_gen_replenishment_AuraScript::CalculateAmount, EFFECT_0, SPELL_AURA_PERIODIC_ENERGIZE);
    }
};

enum RunningWildMountIds
{
    RUNNING_WILD_MODEL_MALE     = 29422,
    RUNNING_WILD_MODEL_FEMALE   = 29423,
    SPELL_ALTERED_FORM          = 97709
};

class spell_gen_running_wild_AuraScript : public AuraScript
{
    bool Validate(SpellInfo const* /*spell*/) override
    {
        if (!sCreatureDisplayInfoStore.LookupEntry(RUNNING_WILD_MODEL_MALE))
            return false;
        if (!sCreatureDisplayInfoStore.LookupEntry(RUNNING_WILD_MODEL_FEMALE))
            return false;
        return true;
    }

    void HandleMount(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        PreventDefaultAction();

        target->Mount(target->getGender() == GENDER_FEMALE ? RUNNING_WILD_MODEL_FEMALE : RUNNING_WILD_MODEL_MALE, 0, 0);

        // cast speed aura
        if (MountCapabilityEntry const* mountCapability = sMountCapabilityStore.LookupEntry(aurEff->GetAmount()))
            target->CastSpell(target, mountCapability->ModSpellAuraID, TRIGGERED_FULL_MASK);
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_running_wild_AuraScript::HandleMount, EFFECT_1, SPELL_AURA_MOUNTED, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_gen_running_wild : public SpellScript
{
    bool Validate(SpellInfo const* /*spell*/) override
    {
        return ValidateSpellInfo({ SPELL_ALTERED_FORM });
    }

    bool Load() override
    {
        // Definitely not a good thing, but currently the only way to do something at cast start
        // Should be replaced as soon as possible with a new hook: BeforeCastStart
        GetCaster()->CastSpell(GetCaster(), SPELL_ALTERED_FORM, TRIGGERED_FULL_MASK);
        return false;
    }

    void Register() override
    {
    }
};

class spell_gen_two_forms : public SpellScript
{
    SpellCastResult CheckCast()
    {
        if (GetCaster()->IsInCombat())
        {
            SetCustomCastResultMessage(SPELL_CUSTOM_ERROR_CANT_TRANSFORM);
            return SPELL_FAILED_CUSTOM_ERROR;
        }

        // Player cannot transform to human form if he is forced to be worgen for some reason (Darkflight)
        Unit::AuraEffectList const& alteredFormAuras = GetCaster()->GetAuraEffectsByType(SPELL_AURA_WORGEN_ALTERED_FORM);
        if (std::distance(alteredFormAuras.begin(), alteredFormAuras.end()) > 1)
        {
            SetCustomCastResultMessage(SPELL_CUSTOM_ERROR_CANT_TRANSFORM);
            return SPELL_FAILED_CUSTOM_ERROR;
        }

        return SPELL_CAST_OK;
    }

    void HandleTransform(SpellEffIndex effIndex)
    {
        Unit* target = GetHitUnit();
        PreventHitDefaultEffect(effIndex);
        if (target->HasAuraType(SPELL_AURA_WORGEN_ALTERED_FORM))
            target->RemoveAurasByType(SPELL_AURA_WORGEN_ALTERED_FORM);
        else    // Basepoints 1 for this aura control whether to trigger transform transition animation or not.
            target->CastSpell(target, SPELL_ALTERED_FORM, CastSpellExtraArgs(true).AddSpellBP0(1));
    }

    void Register() override
    {
        OnCheckCast.Register(&spell_gen_two_forms::CheckCast);
        OnEffectHitTarget.Register(&spell_gen_two_forms::HandleTransform, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_gen_darkflight : public SpellScript
{
    void TriggerTransform()
    {
        GetCaster()->CastSpell(GetCaster(), SPELL_ALTERED_FORM, TRIGGERED_FULL_MASK);
    }

    void Register() override
    {
        AfterCast.Register(&spell_gen_darkflight::TriggerTransform);
    }
};

enum AlteredForm
{
    SPELL_ALTERED_FORM_PROC_AURA = 97681 // Serverside spell
};

class spell_gen_enable_worgen_altered_form : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_ALTERED_FORM_PROC_AURA });
    }

    void HandleApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        GetTarget()->CastSpell(nullptr, SPELL_ALTERED_FORM_PROC_AURA, true);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_gen_enable_worgen_altered_form::HandleApply, EFFECT_0, SPELL_AURA_ENABLE_ALTERED_FORM, AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
    }
};


void RegisterProcsProfessions11()
{
    new spell_gen_obsidian_armor();
    new spell_gen_oracle_wolvar_reputation();
    new spell_gen_orc_disguise();
    new spell_gen_paralytic_poison();
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_soul_harvesters_charm");
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_commendation_of_kaelthas");
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_corpse_tongue_coin");
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_corpse_tongue_coin_heroic");
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_petrified_twilight_scale");
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_petrified_twilight_scale_heroic");
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_proc_armor");
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_proc_mastery_below_35");
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_proc_dodge_below_35");
    RegisterSpellScriptWithArgs(spell_gen_proc_below_pct_damaged, "spell_item_loom_of_fate");
    new spell_gen_proc_charge_drop_only();
    new spell_gen_parachute();
    new spell_gen_pet_summoned();
    RegisterSpellScript(spell_gen_profession_research);
    RegisterSpellScript(spell_gen_remove_flight_auras);
    RegisterSpellAndAuraScriptPair(spell_gen_replenishment, spell_gen_replenishment_AuraScript);
    // Running Wild
    RegisterSpellAndAuraScriptPair(spell_gen_running_wild, spell_gen_running_wild_AuraScript);
    RegisterSpellScript(spell_gen_two_forms);
    RegisterSpellScript(spell_gen_darkflight);
    RegisterSpellScript(spell_gen_enable_worgen_altered_form);
}

void RegisterProcsProfessions16()
{
    RegisterSpellScript(spell_gen_prevent_emotes);
}
}
