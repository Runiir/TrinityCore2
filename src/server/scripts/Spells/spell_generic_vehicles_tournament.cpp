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
enum SeaforiumSpells
{
    SPELL_PLANT_CHARGES_CREDIT_ACHIEVEMENT  = 60937
};

class spell_gen_seaforium_blast : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_PLANT_CHARGES_CREDIT_ACHIEVEMENT });
    }

    bool Load() override
    {
        return GetGObjCaster()->GetOwnerGUID().IsPlayer();
    }

    void AchievementCredit(SpellEffIndex /*effIndex*/)
    {
        if (Unit* owner = GetGObjCaster()->GetOwner())
            if (GameObject* go = GetHitGObj())
                if (go->GetGOInfo()->type == GAMEOBJECT_TYPE_DESTRUCTIBLE_BUILDING)
                    owner->CastSpell(nullptr, SPELL_PLANT_CHARGES_CREDIT_ACHIEVEMENT, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_seaforium_blast::AchievementCredit, EFFECT_1, SPELL_EFFECT_GAMEOBJECT_DAMAGE);
    }
};

enum SpectatorCheerTrigger
{
    EMOTE_ONE_SHOT_CHEER        = 4,
    EMOTE_ONE_SHOT_EXCLAMATION  = 5,
    EMOTE_ONE_SHOT_APPLAUD      = 21
};

uint8 const EmoteArray[3] = { EMOTE_ONE_SHOT_CHEER, EMOTE_ONE_SHOT_EXCLAMATION, EMOTE_ONE_SHOT_APPLAUD };

class spell_gen_spectator_cheer_trigger : public SpellScript
{
    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        GetCaster()->HandleEmoteCommand(EmoteArray[urand(0, 2)]);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_spectator_cheer_trigger::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_gen_spirit_healer_res : public SpellScript
{
    bool Load() override
    {
        return GetOriginalCaster() && GetOriginalCaster()->GetTypeId() == TYPEID_PLAYER;
    }

    void HandleDummy(SpellEffIndex /* effIndex */)
    {
        Player* originalCaster = GetOriginalCaster()->ToPlayer();
        if (Unit* target = GetHitUnit())
        {
            WorldPacket data(SMSG_SPIRIT_HEALER_CONFIRM, 8);
            data << uint64(target->GetGUID());
            originalCaster->SendDirectMessage(&data);
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_spirit_healer_res::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

enum SummonElemental
{
    SPELL_SUMMON_FIRE_ELEMENTAL  = 8985,
    SPELL_SUMMON_EARTH_ELEMENTAL = 19704
};

class spell_gen_summon_elemental : public AuraScript
{
public:
    spell_gen_summon_elemental(uint32 spellId) : AuraScript(), _spellId(spellId) { }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ _spellId });
    }

    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (GetCaster())
            if (Unit* owner = GetCaster()->GetOwner())
                owner->CastSpell(owner, _spellId, true);
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (GetCaster())
            if (Unit* owner = GetCaster()->GetOwner())
                if (owner->GetTypeId() == TYPEID_PLAYER) /// @todo this check is maybe wrong
                    owner->ToPlayer()->RemovePet(nullptr, PET_SAVE_DISMISS, true);
    }

    void Register() override
    {
         AfterEffectApply.Register(&spell_gen_summon_elemental::AfterApply, EFFECT_1, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
         AfterEffectRemove.Register(&spell_gen_summon_elemental::AfterRemove, EFFECT_1, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }

private:
    uint32 _spellId;
};

enum TournamentMountsSpells
{
    SPELL_LANCE_EQUIPPED     = 62853
};

class spell_gen_summon_tournament_mount : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_LANCE_EQUIPPED });
    }

    SpellCastResult CheckIfLanceEquiped()
    {
        if (GetCaster()->IsInDisallowedMountForm())
            GetCaster()->RemoveAurasByType(SPELL_AURA_MOD_SHAPESHIFT);

        if (!GetCaster()->HasAura(SPELL_LANCE_EQUIPPED))
        {
            SetCustomCastResultMessage(SPELL_CUSTOM_ERROR_MUST_HAVE_LANCE_EQUIPPED);
            return SPELL_FAILED_CUSTOM_ERROR;
        }

        return SPELL_CAST_OK;
    }

    void Register() override
    {
        OnCheckCast.Register(&spell_gen_summon_tournament_mount::CheckIfLanceEquiped);
    }
};

// 41213, 43416, 69222, 73076 - Throw Shield
class spell_gen_throw_shield : public SpellScript
{
    void HandleScriptEffect(SpellEffIndex effIndex)
    {
        PreventHitDefaultEffect(effIndex);
        GetCaster()->CastSpell(GetHitUnit(), uint32(GetEffectValue()), true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_throw_shield::HandleScriptEffect, EFFECT_1, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

enum MountedDuelSpells
{
    SPELL_ON_TOURNAMENT_MOUNT = 63034,
    SPELL_MOUNTED_DUEL        = 62875
};

class spell_gen_tournament_duel : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
        {
            SPELL_ON_TOURNAMENT_MOUNT,
            SPELL_MOUNTED_DUEL
        });
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        if (Unit* rider = GetCaster()->GetCharmer())
        {
            if (Player* playerTarget = GetHitPlayer())
            {
                if (playerTarget->HasAura(SPELL_ON_TOURNAMENT_MOUNT) && playerTarget->GetVehicleBase())
                    rider->CastSpell(playerTarget, SPELL_MOUNTED_DUEL, true);
            }
            else if (Unit* unitTarget = GetHitUnit())
            {
                if (unitTarget->GetCharmer() && unitTarget->GetCharmer()->GetTypeId() == TYPEID_PLAYER && unitTarget->GetCharmer()->HasAura(SPELL_ON_TOURNAMENT_MOUNT))
                    rider->CastSpell(unitTarget->GetCharmer(), SPELL_MOUNTED_DUEL, true);
            }
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_tournament_duel::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_gen_tournament_pennant : public AuraScript
{
    bool Load() override
    {
        return GetCaster() && GetCaster()->GetTypeId() == TYPEID_PLAYER;
    }

    void HandleApplyEffect(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Unit* caster = GetCaster())
            if (!caster->GetVehicleBase())
                caster->RemoveAurasDueToSpell(GetId());
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_tournament_pennant::HandleApplyEffect, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
    }
};

enum FriendOrFowl
{
    SPELL_TURKEY_VENGEANCE      = 25285
};

class spell_gen_turkey_marker : public AuraScript
{
    void OnApply(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
    {
        // store stack apply times, so we can pop them while they expire
        _applyTimes.push_back(GameTime::GetGameTimeMS());
        Unit* target = GetTarget();

        // on stack 15 cast the achievement crediting spell
        if (GetStackAmount() >= 15)
            target->CastSpell(target, SPELL_TURKEY_VENGEANCE, CastSpellExtraArgs(aurEff).SetOriginalCaster(GetCasterGUID()));
    }

    void OnPeriodic(AuraEffect const* /*aurEff*/)
    {
        if (_applyTimes.empty())
            return;

        // pop stack if it expired for us
        if (_applyTimes.front() + GetMaxDuration() < GameTime::GetGameTimeMS())
            ModStackAmount(-1, AuraRemoveFlags::Expired);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_gen_turkey_marker::OnApply, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY, AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
        OnEffectPeriodic.Register(&spell_gen_turkey_marker::OnPeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }

    std::list<uint32> _applyTimes;
};

enum FoamSword
{
    ITEM_FOAM_SWORD_GREEN   = 45061,
    ITEM_FOAM_SWORD_PINK    = 45176,
    ITEM_FOAM_SWORD_BLUE    = 45177,
    ITEM_FOAM_SWORD_RED     = 45178,
    ITEM_FOAM_SWORD_YELLOW  = 45179
};

class spell_gen_upper_deck_create_foam_sword : public SpellScript
{
    void HandleScript(SpellEffIndex effIndex)
    {
        if (Player* player = GetHitPlayer())
        {
            static uint32 const itemId[5] = { ITEM_FOAM_SWORD_GREEN, ITEM_FOAM_SWORD_PINK, ITEM_FOAM_SWORD_BLUE, ITEM_FOAM_SWORD_RED, ITEM_FOAM_SWORD_YELLOW };
            // player can only have one of these items
            for (uint8 i = 0; i < 5; ++i)
            {
                if (player->HasItemCount(itemId[i], 1, true))
                    return;
            }

            CreateItem(effIndex, itemId[urand(0, 4)]);
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_upper_deck_create_foam_sword::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

enum VampiricTouch
{
    SPELL_VAMPIRIC_TOUCH_HEAL   = 52724
};

// 52723 - Vampiric Touch
// 60501 - Vampiric Touch
class spell_gen_vampiric_touch : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_VAMPIRIC_TOUCH_HEAL });
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();
        DamageInfo* damageInfo = eventInfo.GetDamageInfo();
        if (!damageInfo || !damageInfo->GetDamage())
            return;

        Unit* caster = eventInfo.GetActor();
        int32 bp = damageInfo->GetDamage() / 2;
        caster->CastSpell(caster, SPELL_VAMPIRIC_TOUCH_HEAL, CastSpellExtraArgs(aurEff).AddSpellBP0(bp));
    }

    void Register() override
    {
        OnEffectProc.Register(&spell_gen_vampiric_touch::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

class spell_gen_vehicle_scaling_trigger : public SpellScript
{
    bool Validate(SpellInfo const* spellInfo) override
    {
        return ValidateSpellInfo({ uint32(spellInfo->Effects[EFFECT_0].BasePoints) });
    }

    void HandleEffect(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
            GetHitUnit()->CastSpell(caster, GetSpellInfo()->Effects[effIndex].BasePoints, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_vehicle_scaling_trigger::HandleEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

enum VehicleScaling
{
    SPELL_GEAR_SCALING_1        = 66668,
    SPELL_GEAR_SCALING_CATA_N   = 91401,
    SPELL_GEAR_SCALING_CATA_HC  = 91405

};

class spell_gen_vehicle_scaling : public AuraScript
{
    bool Load() override
    {
        return GetCaster() && GetCaster()->GetTypeId() == TYPEID_PLAYER;
    }

    void CalculateAmount(AuraEffect const* /*aurEff*/, int32& amount, bool& /*canBeRecalculated*/)
    {
        Unit* caster = GetCaster();
        float factor = 0.0f;
        uint16 baseItemLevel = 0;

        /// @todo Reserach coeffs for different vehicles
        switch (GetId())
        {
            case SPELL_GEAR_SCALING_1:
                factor = 1.0f;
                baseItemLevel = 205;
                break;
            case SPELL_GEAR_SCALING_CATA_N:
                factor = 1.0f;
                baseItemLevel = 305;
                break;
            case SPELL_GEAR_SCALING_CATA_HC:
                factor = 1.0f;
                baseItemLevel = 329;
                break;
            default:
                factor = 1.0f;
                baseItemLevel = 170;
                break;
        }

        float avgILvl = caster->ToPlayer()->GetAverageItemLevel();
        if (avgILvl < baseItemLevel)
            return;                     /// @todo Research possibility of scaling down

        amount = uint16((avgILvl - baseItemLevel) * factor);
    }

    void Register() override
    {
        switch (m_scriptSpellId)
        {
            case SPELL_GEAR_SCALING_CATA_N:
            case SPELL_GEAR_SCALING_CATA_HC:
                DoEffectCalcAmount.Register(&spell_gen_vehicle_scaling::CalculateAmount, EFFECT_0, SPELL_AURA_MOD_HEALING_DONE_PERCENT);
                break;
            default:
                DoEffectCalcAmount.Register(&spell_gen_vehicle_scaling::CalculateAmount, EFFECT_0, SPELL_AURA_MOD_HEALING_PCT);
                break;
        }

        DoEffectCalcAmount.Register(&spell_gen_vehicle_scaling::CalculateAmount, EFFECT_1, SPELL_AURA_MOD_DAMAGE_PERCENT_DONE);
        DoEffectCalcAmount.Register(&spell_gen_vehicle_scaling::CalculateAmount, EFFECT_2, SPELL_AURA_MOD_INCREASE_HEALTH_PERCENT);
    }
};

enum VendorBarkTrigger
{
    NPC_AMPHITHEATER_VENDOR     = 30098,
    SAY_AMPHITHEATER_VENDOR     = 0
};

class spell_gen_vendor_bark_trigger : public SpellScript
{
    void HandleDummy(SpellEffIndex /* effIndex */)
    {
        if (Creature* vendor = GetCaster()->ToCreature())
            if (vendor->GetEntry() == NPC_AMPHITHEATER_VENDOR)
                vendor->AI()->Talk(SAY_AMPHITHEATER_VENDOR);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_vendor_bark_trigger::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_gen_wg_water : public SpellScript
{
    SpellCastResult CheckCast()
    {
        if (!GetSpellInfo()->CheckTargetCreatureType(GetCaster()))
            return SPELL_FAILED_DONT_REPORT;
        return SPELL_CAST_OK;
    }

    void Register() override
    {
        OnCheckCast.Register(&spell_gen_wg_water::CheckCast);
    }
};

enum WhisperGulchYoggSaronWhisper
{
    SPELL_YOGG_SARON_WHISPER_DUMMY  = 29072
};

class spell_gen_whisper_gulch_yogg_saron_whisper : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_YOGG_SARON_WHISPER_DUMMY });
    }

    void HandleEffectPeriodic(AuraEffect const* /*aurEff*/)
    {
        PreventDefaultAction();
        GetTarget()->CastSpell((Unit*)nullptr, SPELL_YOGG_SARON_WHISPER_DUMMY, true);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_gen_whisper_gulch_yogg_saron_whisper::HandleEffectPeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

class spell_gen_eject_all_passengers : public SpellScript
{
    void RemoveVehicleAuras()
    {
        if (Vehicle* vehicle = GetHitUnit()->GetVehicleKit())
            vehicle->RemoveAllPassengers();
    }

    void Register() override
    {
        AfterHit.Register(&spell_gen_eject_all_passengers::RemoveVehicleAuras);
    }
};

enum EjectPassenger
{
    SPELL_GEN_EJECT_PASSENGER_1 = 77946,
    SPELL_GEN_EJECT_PASSENGER_3 = 95204
};

class spell_gen_eject_passenger : public SpellScript
{
    bool Validate(SpellInfo const* spellInfo) override
    {
        if (spellInfo->Effects[EFFECT_0].CalcValue() < 1)
        {
            switch (spellInfo->Id)
            {
                case SPELL_GEN_EJECT_PASSENGER_1:
                case SPELL_GEN_EJECT_PASSENGER_3:
                    return ValidateSpellInfo({ spellInfo->Id });
                default:
                    return false;
            }
            return false;
        }
        return true;
    }

    void EjectPassenger(SpellEffIndex /*effIndex*/)
    {
        if (Vehicle* vehicle = GetHitUnit()->GetVehicleKit())
        {
            uint8 seatId = 0;
            switch (GetSpellInfo()->Id)
            {
                case SPELL_GEN_EJECT_PASSENGER_1:
                    seatId = 0;
                    break;
                case SPELL_GEN_EJECT_PASSENGER_3:
                    seatId = 2;
                    break;
                default:
                    seatId = GetEffectValue() - 1;
                    break;
            }

            if (Unit* passenger = vehicle->GetPassenger(seatId))
                passenger->ExitVehicle();
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_eject_passenger::EjectPassenger, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

enum GMFreeze
{
    SPELL_GM_FREEZE = 9454
};

class spell_gen_gm_freeze : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_GM_FREEZE });
    }

    void OnApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        // Do what was done before to the target in HandleFreezeCommand
        if (Player* player = GetTarget()->ToPlayer())
        {
            // stop combat + make player unattackable + duel stop + stop some spells
            player->SetFaction(FACTION_FRIENDLY);
            player->CombatStop();
            if (player->IsNonMeleeSpellCast(true))
                player->InterruptNonMeleeSpells(true);
            player->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NON_ATTACKABLE);

            // if player class = hunter || warlock remove pet if alive
            if ((player->getClass() == CLASS_HUNTER) || (player->getClass() == CLASS_WARLOCK))
            {
                if (Pet* pet = player->GetPet())
                {
                    pet->SavePetToDB(PET_SAVE_CURRENT_STATE);
                    // not let dismiss dead pet
                    if (pet->IsAlive())
                        player->RemovePet(pet, PET_SAVE_DISMISS);
                }
            }
        }
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        // Do what was done before to the target in HandleUnfreezeCommand
        if (Player* player = GetTarget()->ToPlayer())
        {
            // Reset player faction + allow combat + allow duels
            player->SetFactionForRace(player->getRace());
            player->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NON_ATTACKABLE);
            // save player
            player->SaveToDB();
        }
    }

    void Register() override
    {
        OnEffectApply.Register(&spell_gen_gm_freeze::OnApply, EFFECT_0, SPELL_AURA_MOD_STUN, AURA_EFFECT_HANDLE_REAL);
        OnEffectRemove.Register(&spell_gen_gm_freeze::OnRemove, EFFECT_0, SPELL_AURA_MOD_STUN, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_gen_stand : public SpellScript
{
    void HandleScript(SpellEffIndex /*eff*/)
    {
        Creature* target = GetHitCreature();
        if (!target)
            return;

        target->SetStandState(UNIT_STAND_STATE_STAND);
        target->HandleEmoteCommand(EMOTE_STATE_NONE);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_stand::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};


void RegisterVehiclesTournament12()
{
    /*                          */
    RegisterSpellScript(spell_gen_seaforium_blast);
    RegisterSpellScript(spell_gen_spectator_cheer_trigger);
    RegisterSpellScript(spell_gen_spirit_healer_res);
    RegisterSpellScriptWithArgs(spell_gen_summon_elemental, "spell_gen_summon_fire_elemental", SPELL_SUMMON_FIRE_ELEMENTAL);
    RegisterSpellScriptWithArgs(spell_gen_summon_elemental, "spell_gen_summon_earth_elemental", SPELL_SUMMON_EARTH_ELEMENTAL);
    RegisterSpellScript(spell_gen_summon_tournament_mount);
    RegisterSpellScript(spell_gen_throw_shield);
    RegisterSpellScript(spell_gen_tournament_duel);
    RegisterSpellScript(spell_gen_tournament_pennant);
    RegisterSpellScript(spell_gen_turkey_marker);
    RegisterSpellScript(spell_gen_upper_deck_create_foam_sword);
    RegisterSpellScript(spell_gen_vampiric_touch);
    RegisterSpellScript(spell_gen_vehicle_scaling_trigger);
    RegisterSpellScript(spell_gen_vehicle_scaling);
    RegisterSpellScript(spell_gen_vendor_bark_trigger);
    RegisterSpellScript(spell_gen_wg_water);
    RegisterSpellScript(spell_gen_whisper_gulch_yogg_saron_whisper);
    RegisterSpellScript(spell_gen_eject_all_passengers);
    RegisterSpellScript(spell_gen_eject_passenger);
    RegisterSpellScript(spell_gen_gm_freeze);
    RegisterSpellScript(spell_gen_stand);
}
}
