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
enum EtherealPet
{
    NPC_ETHEREAL_SOUL_TRADER        = 27914,

    SAY_STEAL_ESSENCE               = 1,
    SAY_CREATE_TOKEN                = 2,

    SPELL_PROC_TRIGGER_ON_KILL_AURA = 50051,
    SPELL_ETHEREAL_PET_AURA         = 50055,
    SPELL_CREATE_TOKEN              = 50063,
    SPELL_STEAL_ESSENCE_VISUAL      = 50101
};

// 50051 - Ethereal Pet Aura
class spell_ethereal_pet_aura : public AuraScript
{
    bool CheckProc(ProcEventInfo& eventInfo)
    {
        uint32 levelDiff = std::abs(GetTarget()->getLevel() - eventInfo.GetProcTarget()->getLevel());
        return levelDiff <= 9;
    }

    void HandleProc(AuraEffect const* /*aurEff*/, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();

        std::list<Creature*> minionList;
        GetUnitOwner()->GetAllMinionsByEntry(minionList, NPC_ETHEREAL_SOUL_TRADER);
        for (Creature* minion : minionList)
        {
            if (minion->IsAIEnabled())
            {
                minion->AI()->Talk(SAY_STEAL_ESSENCE);
                minion->CastSpell(eventInfo.GetProcTarget(), SPELL_STEAL_ESSENCE_VISUAL);
            }
        }
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_ethereal_pet_aura::CheckProc);
        OnEffectProc.Register(&spell_ethereal_pet_aura::HandleProc, EFFECT_0, SPELL_AURA_PROC_TRIGGER_SPELL);
    }
};

// 50052 - Ethereal Pet onSummon
class spell_ethereal_pet_onsummon : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_PROC_TRIGGER_ON_KILL_AURA });
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();
        target->CastSpell(target, SPELL_PROC_TRIGGER_ON_KILL_AURA, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_ethereal_pet_onsummon::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

// 50055 - Ethereal Pet Aura Remove
class spell_ethereal_pet_aura_remove : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_ETHEREAL_PET_AURA });
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        GetHitUnit()->RemoveAurasDueToSpell(SPELL_ETHEREAL_PET_AURA);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_ethereal_pet_aura_remove::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

// 50101 - Steal Essence Visual
class spell_steal_essence_visual : public AuraScript
{
    void HandleRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Unit* caster = GetCaster())
        {
            caster->CastSpell(caster, SPELL_CREATE_TOKEN, true);
            if (Creature* soulTrader = caster->ToCreature())
                soulTrader->AI()->Talk(SAY_CREATE_TOKEN);
        }
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_steal_essence_visual::HandleRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

/*
There are only 3 possible flags Feign Death auras can apply: UNIT_DYNFLAG_DEAD, UNIT_FLAG2_FEIGN_DEATH
and UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT. Some auras can apply only 2 flags

spell_gen_feign_death_all_flags applies all 3 flags
spell_gen_feign_death_all_flags_uninteractible applies all 3 flags and additionally sets UNIT_FLAG_IMMUNE_TO_PC | UNIT_FLAG_IMMUNE_TO_NPC | UNIT_FLAG_UNINTERACTIBLE
spell_gen_feign_death_all_flags_no_uninteractible applies all 3 flags and additionally sets UNIT_FLAG_IMMUNE_TO_PC | UNIT_FLAG_IMMUNE_TO_NPC
spell_gen_feign_death_no_dyn_flag applies no UNIT_DYNFLAG_DEAD (does not make the creature appear dead)
spell_gen_feign_death_no_prevent_emotes applies no UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT

REACT_PASSIVE should be handled directly in scripts since not all creatures should be passive. Otherwise
creature will be not able to aggro or execute MoveInLineOfSight events. Removing may cause more issues
than already exists
*/

class spell_gen_feign_death_all_flags : public AuraScript
{
    void HandleEffectApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->SetFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_DEAD);
        target->SetFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_FEIGN_DEATH);
        target->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT);

        if (Creature* creature = target->ToCreature())
            creature->SetReactState(REACT_PASSIVE);
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->RemoveFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_DEAD);
        target->RemoveFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_FEIGN_DEATH);
        target->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT);

        if (Creature* creature = target->ToCreature())
            creature->InitializeReactState();
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_feign_death_all_flags::HandleEffectApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        OnEffectRemove.Register(&spell_gen_feign_death_all_flags::OnRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_gen_feign_death_all_flags_uninteractible : public AuraScript
{
    void HandleEffectApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->SetFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_FEIGN_DEATH);
        target->SetImmuneToAll(true);
        target->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT | UNIT_FLAG_NOT_SELECTABLE);

        if (Creature* creature = target->ToCreature())
            creature->SetReactState(REACT_PASSIVE);
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->RemoveFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_FEIGN_DEATH);
        target->SetImmuneToAll(false);
        target->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT| UNIT_FLAG_NOT_SELECTABLE);

        if (Creature* creature = target->ToCreature())
            creature->InitializeReactState();
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_feign_death_all_flags_uninteractible::HandleEffectApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        OnEffectRemove.Register(&spell_gen_feign_death_all_flags_uninteractible::OnRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

// 96733 - Permanent Feign Death (Stun)
class spell_gen_feign_death_all_flags_no_uninteractible : public AuraScript
{
    void HandleEffectApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG2_FEIGN_DEATH);
        target->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT);
        target->SetImmuneToAll(true);

        if (Creature* creature = target->ToCreature())
            creature->SetReactState(REACT_PASSIVE);
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG2_FEIGN_DEATH);
        target->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT);
        target->SetImmuneToAll(false);

        if (Creature* creature = target->ToCreature())
            creature->InitializeReactState();
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_feign_death_all_flags_no_uninteractible::HandleEffectApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        OnEffectRemove.Register(&spell_gen_feign_death_all_flags_no_uninteractible::OnRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

// 35357 - Spawn Feign Death
// 51329 - Feign Death
class spell_gen_feign_death_no_dyn_flag : public AuraScript
{
    void HandleEffectApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->SetFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_FEIGN_DEATH);
        target->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT);

        if (Creature* creature = target->ToCreature())
            creature->SetReactState(REACT_PASSIVE);
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->RemoveFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_FEIGN_DEATH);
        target->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PREVENT_EMOTES_FROM_CHAT_TEXT);

        if (Creature* creature = target->ToCreature())
            creature->InitializeReactState();
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_feign_death_no_dyn_flag::HandleEffectApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        OnEffectRemove.Register(&spell_gen_feign_death_no_dyn_flag::OnRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

// 58951 - Permanent Feign Death
class spell_gen_feign_death_no_prevent_emotes : public AuraScript
{
    void HandleEffectApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->SetFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_DEAD);
        target->SetFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_FEIGN_DEATH);

        if (Creature* creature = target->ToCreature())
            creature->SetReactState(REACT_PASSIVE);
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->RemoveFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_DEAD);
        target->RemoveFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_FEIGN_DEATH);

        if (Creature* creature = target->ToCreature())
            creature->InitializeReactState();
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_feign_death_no_prevent_emotes::HandleEffectApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        OnEffectRemove.Register(&spell_gen_feign_death_no_prevent_emotes::OnRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

enum TransporterBackfires
{
    SPELL_TRANSPORTER_MALFUNCTION_POLYMORPH     = 23444,
    SPELL_TRANSPORTER_EVIL_TWIN                 = 23445,
    SPELL_TRANSPORTER_MALFUNCTION_MISS          = 36902
};

class spell_gen_gadgetzan_transporter_backfire : public SpellScriptLoader
{
    public:
        spell_gen_gadgetzan_transporter_backfire() : SpellScriptLoader("spell_gen_gadgetzan_transporter_backfire") { }

        class spell_gen_gadgetzan_transporter_backfire_SpellScript : public SpellScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                return ValidateSpellInfo(
                {
                    SPELL_TRANSPORTER_MALFUNCTION_POLYMORPH,
                    SPELL_TRANSPORTER_EVIL_TWIN,
                    SPELL_TRANSPORTER_MALFUNCTION_MISS
                });
            }

            void HandleDummy(SpellEffIndex /* effIndex */)
            {
                Unit* caster = GetCaster();
                int32 r = irand(0, 119);
                if (r < 20)                           // Transporter Malfunction - 1/6 polymorph
                    caster->CastSpell(caster, SPELL_TRANSPORTER_MALFUNCTION_POLYMORPH, true);
                else if (r < 100)                     // Evil Twin               - 4/6 evil twin
                    caster->CastSpell(caster, SPELL_TRANSPORTER_EVIL_TWIN, true);
                else                                    // Transporter Malfunction - 1/6 miss the target
                    caster->CastSpell(caster, SPELL_TRANSPORTER_MALFUNCTION_MISS, true);
            }

            void Register() override
            {
                OnEffectHitTarget.Register(&spell_gen_gadgetzan_transporter_backfire_SpellScript::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
            }
        };

        SpellScript* GetSpellScript() const override
        {
            return new spell_gen_gadgetzan_transporter_backfire_SpellScript();
        }
};


class spell_gen_gift_of_naaru : public SpellScriptLoader
{
    public:
        spell_gen_gift_of_naaru() : SpellScriptLoader("spell_gen_gift_of_naaru") { }

        class spell_gen_gift_of_naaru_AuraScript : public AuraScript
        {
            void CalculateAmount(AuraEffect const* aurEff, int32& amount, bool& /*canBeRecalculated*/)
            {
                Unit* target = GetOwner()->ToUnit();
                if (!target)
                    return;

                uint64 health = target->GetMaxHealth();
                int32 healthPct = CalculatePct(health, GetSpellInfo()->Effects[EFFECT_1].BasePoints);

                if (healthPct)
                    amount = std::floor(healthPct / aurEff->GetTotalTicks());
            }

            void Register() override
            {
                DoEffectCalcAmount.Register(&spell_gen_gift_of_naaru_AuraScript::CalculateAmount, EFFECT_0, SPELL_AURA_PERIODIC_HEAL);
            }
        };

        AuraScript* GetAuraScript() const override
        {
            return new spell_gen_gift_of_naaru_AuraScript();
        }
};

enum GnomishTransporter
{
    SPELL_TRANSPORTER_SUCCESS                   = 23441,
    SPELL_TRANSPORTER_FAILURE                   = 23446
};

class spell_gen_gnomish_transporter : public SpellScriptLoader
{
    public:
        spell_gen_gnomish_transporter() : SpellScriptLoader("spell_gen_gnomish_transporter") { }

        class spell_gen_gnomish_transporter_SpellScript : public SpellScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                return ValidateSpellInfo(
                {
                    SPELL_TRANSPORTER_SUCCESS,
                    SPELL_TRANSPORTER_FAILURE
                });
            }

            void HandleDummy(SpellEffIndex /* effIndex */)
            {
                GetCaster()->CastSpell(GetCaster(), roll_chance_i(50) ? SPELL_TRANSPORTER_SUCCESS : SPELL_TRANSPORTER_FAILURE, true);
            }

            void Register() override
            {
                OnEffectHitTarget.Register(&spell_gen_gnomish_transporter_SpellScript::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
            }
        };

        SpellScript* GetSpellScript() const override
        {
            return new spell_gen_gnomish_transporter_SpellScript();
        }
};

enum Interrupt
{
    SPELL_GEN_INTERRUPT = 32747
};

// 32748 - Deadly Throw Interrupt
// 44835 - Maim Interrupt
class spell_gen_interrupt : public SpellScriptLoader
{
    public:
        spell_gen_interrupt() : SpellScriptLoader("spell_gen_interrupt") { }

        class spell_gen_interrupt_AuraScript : public AuraScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                return ValidateSpellInfo({ SPELL_GEN_INTERRUPT });
            }

            void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
            {
                PreventDefaultAction();
                GetTarget()->CastSpell(eventInfo.GetProcTarget(), SPELL_GEN_INTERRUPT, aurEff);
            }

            void Register() override
            {
                OnEffectProc.Register(&spell_gen_interrupt_AuraScript::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
            }
        };

        AuraScript* GetAuraScript() const override
        {
            return new spell_gen_interrupt_AuraScript();
        }
};

class spell_gen_increase_stats_buff : public SpellScript
{
    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        if (GetHitUnit()->IsInRaidWith(GetCaster()))
            GetCaster()->CastSpell(GetCaster(), GetEffectValue() + 1, true); // raid buff
        else
            GetCaster()->CastSpell(GetHitUnit(), GetEffectValue(), true); // single-target buff
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_increase_stats_buff::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

enum GenericLifebloom
{
    SPELL_HEXLORD_MALACRASS_LIFEBLOOM_FINAL_HEAL        = 43422,
    SPELL_TUR_RAGEPAW_LIFEBLOOM_FINAL_HEAL              = 52552,
    SPELL_CENARION_SCOUT_LIFEBLOOM_FINAL_HEAL           = 53692,
    SPELL_TWISTED_VISAGE_LIFEBLOOM_FINAL_HEAL           = 57763,
    SPELL_FACTION_CHAMPIONS_DRU_LIFEBLOOM_FINAL_HEAL    = 66094
};

class spell_gen_lifebloom : public AuraScript
{
public:
    spell_gen_lifebloom(uint32 spellId) : AuraScript(), _spellId(spellId) { }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ _spellId });
    }

    void AfterRemove(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
    {
        // Final heal only on duration end
        if (!GetTargetApplication()->GetRemoveMode().HasAllFlags(AuraRemoveFlags::Expired | AuraRemoveFlags::ByEnemySpell))
            return;

        // final heal
        GetTarget()->CastSpell(GetTarget(), _spellId, CastSpellExtraArgs(aurEff).SetOriginalCaster(GetCasterGUID()));
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_gen_lifebloom::AfterRemove, EFFECT_0, SPELL_AURA_PERIODIC_HEAL, AURA_EFFECT_HANDLE_REAL);
    }

private:
    uint32 _spellId;
};

/* DOCUMENTATION: Charge spells
    Charge spells can be classified in four groups:

        - Spells on vehicle bar used by players:
            + EFFECT_0: SCRIPT_EFFECT
            + EFFECT_1: TRIGGER_SPELL
            + EFFECT_2: NONE
        - Spells cast by player's mounts triggered by script:
            + EFFECT_0: CHARGE
            + EFFECT_1: TRIGGER_SPELL
            + EFFECT_2: APPLY_AURA
        - Spells cast by players on the target triggered by script:
            + EFFECT_0: SCHOOL_DAMAGE
            + EFFECT_1: SCRIPT_EFFECT
            + EFFECT_2: NONE
        - Spells cast by NPCs on players:
            + EFFECT_0: SCHOOL_DAMAGE
            + EFFECT_1: CHARGE
            + EFFECT_2: SCRIPT_EFFECT

    In the following script we handle the SCRIPT_EFFECT and CHARGE
        - When handling SCRIPT_EFFECT:
            + EFFECT_0: Corresponds to "Spells on vehicle bar used by players" and we make player's mount cast
              the charge effect on the current target ("Spells cast by player's mounts triggered by script").
            + EFFECT_1 and EFFECT_2: Triggered when "Spells cast by player's mounts triggered by script" hits target,
              corresponding to "Spells cast by players on the target triggered by script" and "Spells cast by
              NPCs on players" and we check Defend layers and drop a charge of the first found.
        - When handling CHARGE:
            + Only launched for "Spells cast by player's mounts triggered by script", makes the player cast the
              damaging spell on target with a small chance of failing it.
*/

enum ChargeSpells
{
    SPELL_CHARGE_DAMAGE_8K5             = 62874,
    SPELL_CHARGE_DAMAGE_20K             = 68498,
    SPELL_CHARGE_DAMAGE_45K             = 64591,

    SPELL_CHARGE_CHARGING_EFFECT_8K5    = 63661,
    SPELL_CHARGE_CHARGING_EFFECT_20K_1  = 68284,
    SPELL_CHARGE_CHARGING_EFFECT_20K_2  = 68501,
    SPELL_CHARGE_CHARGING_EFFECT_45K_1  = 62563,
    SPELL_CHARGE_CHARGING_EFFECT_45K_2  = 66481,

    SPELL_CHARGE_TRIGGER_FACTION_MOUNTS = 62960,
    SPELL_CHARGE_TRIGGER_TRIAL_CHAMPION = 68282,

    SPELL_CHARGE_MISS_EFFECT            = 62977,
};

class spell_gen_mounted_charge: public SpellScriptLoader
{
    public:
        spell_gen_mounted_charge() : SpellScriptLoader("spell_gen_mounted_charge") { }

        class spell_gen_mounted_charge_SpellScript : public SpellScript
        {
            void HandleScriptEffect(SpellEffIndex effIndex)
            {
                Unit* target = GetHitUnit();

                switch (effIndex)
                {
                    case EFFECT_0: // On spells wich trigger the damaging spell (and also the visual)
                    {
                        uint32 spellId;

                        switch (GetSpellInfo()->Id)
                        {
                            case SPELL_CHARGE_TRIGGER_TRIAL_CHAMPION:
                                spellId = SPELL_CHARGE_CHARGING_EFFECT_20K_1;
                                break;
                            case SPELL_CHARGE_TRIGGER_FACTION_MOUNTS:
                                spellId = SPELL_CHARGE_CHARGING_EFFECT_8K5;
                                break;
                            default:
                                return;
                        }

                        // If target isn't a training dummy there's a chance of failing the charge
                        if (!target->IsCharmedOwnedByPlayerOrPlayer() && roll_chance_f(12.5f))
                            spellId = SPELL_CHARGE_MISS_EFFECT;

                        if (Unit* vehicle = GetCaster()->GetVehicleBase())
                            vehicle->CastSpell(target, spellId, false);
                        else
                            GetCaster()->CastSpell(target, spellId, false);
                        break;
                    }
                    case EFFECT_1: // On damaging spells, for removing a defend layer
                    case EFFECT_2:
                    {
                        Unit::AuraApplicationMap const& auras = target->GetAppliedAuras();
                        for (Unit::AuraApplicationMap::const_iterator itr = auras.begin(); itr != auras.end(); ++itr)
                        {
                            if (Aura* aura = itr->second->GetBase())
                            {
                                SpellInfo const* auraInfo = aura->GetSpellInfo();
                                if (auraInfo && auraInfo->SpellIconID == 2007 && aura->HasEffectType(SPELL_AURA_MOD_DAMAGE_PERCENT_TAKEN))
                                {
                                    aura->ModStackAmount(-1, AuraRemoveFlags::ByEnemySpell);
                                    // Remove dummys from rider (Necessary for updating visual shields)
                                    if (Unit* rider = target->GetCharmer())
                                        if (Aura* defend = rider->GetAura(aura->GetId()))
                                            defend->ModStackAmount(-1, AuraRemoveFlags::ByEnemySpell);
                                    break;
                                }
                            }
                        }
                        break;
                    }
                }
            }

            void HandleChargeEffect(SpellEffIndex /*effIndex*/)
            {
                uint32 spellId;

                switch (GetSpellInfo()->Id)
                {
                    case SPELL_CHARGE_CHARGING_EFFECT_8K5:
                        spellId = SPELL_CHARGE_DAMAGE_8K5;
                        break;
                    case SPELL_CHARGE_CHARGING_EFFECT_20K_1:
                    case SPELL_CHARGE_CHARGING_EFFECT_20K_2:
                        spellId = SPELL_CHARGE_DAMAGE_20K;
                        break;
                    case SPELL_CHARGE_CHARGING_EFFECT_45K_1:
                    case SPELL_CHARGE_CHARGING_EFFECT_45K_2:
                        spellId = SPELL_CHARGE_DAMAGE_45K;
                        break;
                    default:
                        return;
                }

                if (Unit* rider = GetCaster()->GetCharmer())
                    rider->CastSpell(GetHitUnit(), spellId, false);
                else
                    GetCaster()->CastSpell(GetHitUnit(), spellId, false);
            }

            void Register() override
            {
                SpellInfo const* spell = sSpellMgr->AssertSpellInfo(m_scriptSpellId);

                if (spell->HasEffect(SPELL_EFFECT_SCRIPT_EFFECT))
                    OnEffectHitTarget.Register(&spell_gen_mounted_charge_SpellScript::HandleScriptEffect, EFFECT_FIRST_FOUND, SPELL_EFFECT_SCRIPT_EFFECT);

                if (spell->Effects[EFFECT_0].Effect == SPELL_EFFECT_CHARGE)
                    OnEffectHitTarget.Register(&spell_gen_mounted_charge_SpellScript::HandleChargeEffect, EFFECT_0, SPELL_EFFECT_CHARGE);
            }
        };

        SpellScript* GetSpellScript() const override
        {
            return new spell_gen_mounted_charge_SpellScript();
        }
};

enum MossCoveredFeet
{
    SPELL_FALL_DOWN = 6869
};

// 6870 Moss Covered Feet
// 31399 Moss Covered Feet
class spell_gen_moss_covered_feet : public SpellScriptLoader
{
    public:
        spell_gen_moss_covered_feet() : SpellScriptLoader("spell_gen_moss_covered_feet") { }

        class spell_gen_moss_covered_feet_AuraScript : public AuraScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                return ValidateSpellInfo({ SPELL_FALL_DOWN });
            }

            void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
            {
                PreventDefaultAction();
                eventInfo.GetActionTarget()->CastSpell(nullptr, SPELL_FALL_DOWN, aurEff);
            }

            void Register() override
            {
                OnEffectProc.Register(&spell_gen_moss_covered_feet_AuraScript::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
            }
        };

        AuraScript* GetAuraScript() const override
        {
            return new spell_gen_moss_covered_feet_AuraScript();
        }
};

enum Netherbloom : uint32
{
    SPELL_NETHERBLOOM_POLLEN_1      = 28703
};

// 28702 - Netherbloom
class spell_gen_netherbloom : public SpellScriptLoader
{
    public:
        spell_gen_netherbloom() : SpellScriptLoader("spell_gen_netherbloom") { }

        class spell_gen_netherbloom_SpellScript : public SpellScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                for (uint8 i = 0; i < 5; ++i)
                    if (!ValidateSpellInfo({ SPELL_NETHERBLOOM_POLLEN_1 + i }))
                        return false;

                return true;
            }

            void HandleScript(SpellEffIndex effIndex)
            {
                PreventHitDefaultEffect(effIndex);

                if (Unit* target = GetHitUnit())
                {
                    // 25% chance of casting a random buff
                    if (roll_chance_i(75))
                        return;

                    // triggered spells are 28703 to 28707
                    // Note: some sources say, that there was the possibility of
                    //       receiving a debuff. However, this seems to be removed by a patch.

                    // don't overwrite an existing aura
                    for (uint8 i = 0; i < 5; ++i)
                        if (target->HasAura(SPELL_NETHERBLOOM_POLLEN_1 + i))
                            return;

                    target->CastSpell(target, SPELL_NETHERBLOOM_POLLEN_1 + urand(0, 4), true);
                }
            }

            void Register() override
            {
                OnEffectHitTarget.Register(&spell_gen_netherbloom_SpellScript::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
            }
        };

        SpellScript* GetSpellScript() const override
        {
            return new spell_gen_netherbloom_SpellScript();
        }
};

enum NightmareVine
{
    SPELL_NIGHTMARE_POLLEN      = 28721
};

// 28720 - Nightmare Vine
class spell_gen_nightmare_vine : public SpellScriptLoader
{
    public:
        spell_gen_nightmare_vine() : SpellScriptLoader("spell_gen_nightmare_vine") { }

        class spell_gen_nightmare_vine_SpellScript : public SpellScript
        {
            bool Validate(SpellInfo const* /*spellInfo*/) override
            {
                return ValidateSpellInfo({ SPELL_NIGHTMARE_POLLEN });
            }

            void HandleScript(SpellEffIndex effIndex)
            {
                PreventHitDefaultEffect(effIndex);

                if (Unit* target = GetHitUnit())
                {
                    // 25% chance of casting Nightmare Pollen
                    if (roll_chance_i(25))
                        target->CastSpell(target, SPELL_NIGHTMARE_POLLEN, true);
                }
            }

            void Register() override
            {
                OnEffectHitTarget.Register(&spell_gen_nightmare_vine_SpellScript::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
            }
        };

        SpellScript* GetSpellScript() const override
        {
            return new spell_gen_nightmare_vine_SpellScript();
        }
};


// 25046 - Arcane Torrent (Racial)
// 28730 - Arcane Torrent (Racial)
// 50613 - Arcane Torrent (Racial)
// 69179 - Arcane Torrent (Racial)
// 80483 - Arcane Torrent (Racial)
class spell_gen_arcane_torrent_racial : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfi*/) override
    {
        return ValidateSpellInfo({ SPELL_GEN_INTERRUPT });
    }

    void HandleCreatureInterrupt(SpellEffIndex /*effIndex*/)
    {
        Creature* target = GetHitCreature();
        if (!target)
            return;

        if (Unit* caster = GetCaster())
            caster->CastSpell(target, SPELL_GEN_INTERRUPT, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_arcane_torrent_racial::HandleCreatureInterrupt, EFFECT_0, SPELL_EFFECT_APPLY_AURA);
    }
};
void RegisterGreetingsRacial2()
{
    RegisterSpellScript(spell_gen_arcane_torrent_racial);
}

void RegisterPetsTransport8()
{
    RegisterSpellScript(spell_gen_feign_death_all_flags);
    RegisterSpellScript(spell_gen_feign_death_all_flags_uninteractible);
    RegisterSpellScript(spell_gen_feign_death_all_flags_no_uninteractible);
    RegisterSpellScript(spell_gen_feign_death_no_dyn_flag);
    RegisterSpellScript(spell_gen_feign_death_no_prevent_emotes);
    new spell_gen_gadgetzan_transporter_backfire();
    new spell_gen_gift_of_naaru();
    new spell_gen_gnomish_transporter();
    RegisterSpellScriptWithArgs(spell_gen_increase_stats_buff, "spell_pal_blessing_of_kings");
    RegisterSpellScriptWithArgs(spell_gen_increase_stats_buff, "spell_pal_blessing_of_might");
    RegisterSpellScriptWithArgs(spell_gen_increase_stats_buff, "spell_dru_mark_of_the_wild");
    RegisterSpellScriptWithArgs(spell_gen_increase_stats_buff, "spell_pri_power_word_fortitude");
    RegisterSpellScriptWithArgs(spell_gen_increase_stats_buff, "spell_pri_shadow_protection");
    RegisterSpellScriptWithArgs(spell_gen_increase_stats_buff, "spell_mage_arcane_brilliance");
    RegisterSpellScriptWithArgs(spell_gen_increase_stats_buff, "spell_mage_dalaran_brilliance");
    new spell_gen_interrupt();
}

void RegisterPetsTransport10()
{
    RegisterSpellScriptWithArgs(spell_gen_lifebloom, "spell_hexlord_lifebloom", SPELL_HEXLORD_MALACRASS_LIFEBLOOM_FINAL_HEAL);
    RegisterSpellScriptWithArgs(spell_gen_lifebloom, "spell_tur_ragepaw_lifebloom", SPELL_TUR_RAGEPAW_LIFEBLOOM_FINAL_HEAL);
    RegisterSpellScriptWithArgs(spell_gen_lifebloom, "spell_cenarion_scout_lifebloom", SPELL_CENARION_SCOUT_LIFEBLOOM_FINAL_HEAL);
    RegisterSpellScriptWithArgs(spell_gen_lifebloom, "spell_twisted_visage_lifebloom", SPELL_TWISTED_VISAGE_LIFEBLOOM_FINAL_HEAL);
    RegisterSpellScriptWithArgs(spell_gen_lifebloom, "spell_faction_champion_dru_lifebloom", SPELL_FACTION_CHAMPIONS_DRU_LIFEBLOOM_FINAL_HEAL);
    new spell_gen_mounted_charge();
    new spell_gen_moss_covered_feet();
    new spell_gen_netherbloom();
}
}
