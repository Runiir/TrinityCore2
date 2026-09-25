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

#include "ObjectMgr.h"
#include "ScriptMgr.h"
#include "CommonPredicates.h"
#include "GameObjectAI.h"
#include "GossipDef.h"
#include "GridNotifiers.h"
#include "MoveSpline.h"
#include "MoveSplineInit.h"
#include "PassiveAI.h"
#include "PhasingHandler.h"
#include "ScriptedCreature.h"
#include "SpellScript.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"
#include "Transport.h"
#include "InstanceScript.h"
#include "MotionMaster.h"
#include "TemporarySummon.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "blackwing_descent.h"
#include "boss_nefarians_end.h"

namespace BlackwingDescent::NefariansEnd
{
static constexpr uint8 const DominionStalkerSpellCount = 4;
uint32 const DominionStalkerSummonSpells[DominionStalkerSpellCount] =
{
    SPELL_SUMMON_DOMINION_STALKER_NORTH,
    SPELL_SUMMON_DOMINION_STALKER_EAST,
    SPELL_SUMMON_DOMINION_STALKER_SOUTH,
    SPELL_SUMMON_DOMINION_STALKER_WEST
};

Position const ChromaticPrototypeJumpPositions[MaxChromaticPrototypes]
{
    { 40.50549f, -0.06254366f, 9.92507f },
    { -20.47418f, -34.21686f, 9.925069f },
    { -20.44454f,  34.39596f, 9.925069f }
};

class spell_nefarians_end_electrical_charge : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_ELECTRICAL_CHARGE_ONYXIA });
    }

    void HandlePeriodic(AuraEffect const* /*aurEff*/)
    {
        Creature* target = GetTarget()->ToCreature();
        InstanceScript* instance = GetTarget()->GetInstanceScript();
        if (!target || !instance)
            return;

        switch (target->GetEntry())
        {
            case BOSS_NEFARIAN:
                if (target->GetReactState() == REACT_AGGRESSIVE)
                {
                    if (Creature* onyxia = instance->GetCreature(DATA_ONYXIA))
                    {
                        if (Aura* charge = onyxia->GetAura(SPELL_ELECTRICAL_CHARGE_ONYXIA))
                            charge->ModStackAmount(1, AuraRemoveFlags::Expired | AuraRemoveFlags::DontResetPeriodicTimer);
                    }
                }
                break;
            case NPC_ONYXIA:
                ModStackAmount(1);
                if (target->IsAIEnabled())
                    target->AI()->DoAction(ACTION_UPDATE_ELECTRICAL_CHARGE);
                break;
            default:
                break;
        }
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_nefarians_end_electrical_charge::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

class spell_nefarians_end_lightning_discharge_triggered_periodic_aura : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_LIGHTNING_DISCHARGE_VISUAL_LEFT_1,
                SPELL_LIGHTNING_DISCHARGE_VISUAL_LEFT_2,
                SPELL_LIGHTNING_DISCHARGE_VISUAL_RIGHT_1,
                SPELL_LIGHTNING_DISCHARGE_VISUAL_RIGHT_2,
                SPELL_LIGHTNING_DISCHARGE_CONE_BACK
            });
    }

    void HandlePeriodic(AuraEffect const* /*aurEff*/)
    {
        Unit* target = GetTarget();
        for (uint8 i = 0; i < 4; i++)
        {
            target->CastSpell(target, SPELL_LIGHTNING_DISCHARGE_VISUAL_LEFT_1, true);
            target->CastSpell(target, SPELL_LIGHTNING_DISCHARGE_VISUAL_LEFT_2, true);
            target->CastSpell(target, SPELL_LIGHTNING_DISCHARGE_VISUAL_RIGHT_1, true);
            target->CastSpell(target, SPELL_LIGHTNING_DISCHARGE_VISUAL_RIGHT_2, true);
        }

        target->CastSpell(target, SPELL_LIGHTNING_DISCHARGE_CONE_BACK, true);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_nefarians_end_lightning_discharge_triggered_periodic_aura::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_nefarians_end_lightning_discharge_cone : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_LIGHTNING_DISCHARGE_DAMAGE });
    }

    void HandleImmunity(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        Unit* target = GetHitUnit();
        if (!caster || !target)
            return;

        uint32 spellId = sSpellMgr->GetSpellIdForDifficulty(SPELL_LIGHTNING_DISCHARGE_DAMAGE, caster);
        target->ApplySpellImmune(0, IMMUNITY_ID, spellId, true);

        target->m_Events.AddEventAtOffset([spellId, target]()
        {
            target->ApplySpellImmune(0, IMMUNITY_ID, spellId, false);
        }, 500ms);
    }

    void Register() override
    {
        OnEffectLaunchTarget.Register(&spell_nefarians_end_lightning_discharge_cone::HandleImmunity, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_nefarians_end_lightning_discharge_damage : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        SpellInfo const* spell = GetSpellInfo();
        Unit* caster = GetCaster();

        targets.remove_if([spell, caster](WorldObject const* obj)->bool
        {
            Unit const* target = obj->ToUnit();
            return !target || target->IsImmunedToSpell(spell, caster);
        });
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_nefarians_end_lightning_discharge_damage::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
    }
};

class spell_nefarians_end_children_of_deathwing : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_CHILDREN_OF_DEATHWING_NEFARIAN });
    }

    void HandlePeriodic(AuraEffect const* /*aurEff*/)
    {
        Unit* target = GetTarget();
        uint32 type = GetSpellInfo()->Id == SPELL_CHILDREN_OF_DEATHWING_NEFARIAN ? DATA_ONYXIA : DATA_NEFARIANS_END;
        if (InstanceScript* instance = target->GetInstanceScript())
            if (Creature* sibling = instance->GetCreature(type))
                if (target->GetExactDist2d(sibling) <= 50.f)
                    target->CastSpell(target, GetSpellInfo()->Effects[EFFECT_0].BasePoints, true);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_nefarians_end_children_of_deathwing::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

class spell_nefarians_end_animate_bones : public AuraScript
{
    void HandlePeriodicTick(AuraEffect const* /*aurEff*/)
    {
        PreventDefaultAction();
        GetTarget()->CastSpell(GetTarget(), GetSpellInfo()->Effects[EFFECT_1].TriggerSpell, TriggerCastFlags(TRIGGERED_FULL_MASK & ~TRIGGERED_IGNORE_POWER_COST));
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_nefarians_end_animate_bones::HandlePeriodicTick, EFFECT_1, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_nefarians_end_animate_bones_dummy : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_PERMANENT_FEIGN_DEATH_2,
                SPELL_CLEAR_ALL_DEBUFFS,
                SPELL_EMPOWER
            });
    }

    void HandleHit(SpellEffIndex /*effIndex*/)
    {
        Creature* target = GetHitCreature();
        if (!target || target->GetPower(POWER_ENERGY) > 1)
            return;

        target->RemoveAurasDueToSpell(SPELL_FULL_POWER_NO_REGEN);
        target->RemoveAurasDueToSpell(SPELL_ANIMATE_BONES);
        target->RemoveAurasDueToSpell(sSpellMgr->GetSpellIdForDifficulty(SPELL_EMPOWER, target));
        target->CastSpell(target, SPELL_CLEAR_ALL_DEBUFFS, true);
        target->AttackStop();
        target->GetThreatManager().ClearAllThreat();
        target->SetReactState(REACT_PASSIVE);
        target->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
        target->CastSpell(target, SPELL_PERMANENT_FEIGN_DEATH_2);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_nefarians_end_animate_bones_dummy::HandleHit, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_nefarians_end_shadowflame_breath : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_PERMANENT_FEIGN_DEATH_2,
                SPELL_FULL_POWER_NO_REGEN
            });
    }

    void HandleHit(SpellEffIndex effIndex)
    {
        Creature* target = GetHitCreature();
        if (!target)
            return;

        if (target->HasAura(SPELL_PERMANENT_FEIGN_DEATH_2))
        {
            target->SetReactState(REACT_AGGRESSIVE);
            if (target->IsAIEnabled())
                target->AI()->DoZoneInCombat();

            target->RemoveAurasDueToSpell(SPELL_PERMANENT_FEIGN_DEATH_2);
            target->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
        }

        target->CastSpell(target, SPELL_FULL_POWER_NO_REGEN);
        target->CastSpell(target, GetSpellInfo()->Effects[effIndex].BasePoints);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_nefarians_end_shadowflame_breath::HandleHit, EFFECT_2, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_nefarians_end_jump_down_to_platform : public SpellScript
{
    void SetDest(SpellDestination& dest)
    {
        Position positions[MaxChromaticPrototypes];

        InstanceScript* instance = GetCaster()->GetInstanceScript();
        if (!instance)
            return;

        GameObject* elevator = instance->GetGameObject(DATA_BLACKWING_ELEVATOR_ONYXIA);
        if (!elevator)
            return;

        TransportBase* transport = elevator->ToTransportBase();
        if (!transport)
            return;

        // Transform sniffed transport destinations into map coordinates so we can use them for real time transport position based offsets
        for (uint8 i = 0; i < MaxChromaticPrototypes; i++)
        {
            positions[i] = ChromaticPrototypeJumpPositions[i];
            transport->CalculatePassengerPosition(positions[i].m_positionX, positions[i].m_positionY, positions[i].m_positionZ);
        }

        // Pick the closest jump destination
        Position pos = positions[0];
        for (uint8 i = 1; i < MaxChromaticPrototypes; i++)
            if (GetCaster()->GetExactDist2d(positions[i]) < GetCaster()->GetExactDist2d(pos))
                pos = positions[i];

        dest.Relocate(pos);
    }

    void Register()
    {
        OnDestinationTargetSelect.Register(&spell_nefarians_end_jump_down_to_platform::SetDest, EFFECT_0, TARGET_DEST_NEARBY_ENTRY);
    }
};

class spell_nefarians_end_shadow_of_cowardice : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_SHADOW_OF_COWARDICE_DAMAGE });
    }

    void HandleHit(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;

        Unit* target = GetHitUnit();
        if (target->GetTransport() && target->GetTransOffsetZ() > 9.5f)
            caster->CastSpell(target, SPELL_SHADOW_OF_COWARDICE_DAMAGE, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_nefarians_end_shadow_of_cowardice::HandleHit, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_nefarians_end_onyxia_start_fight_2_effect : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_SHADOW_OF_COWARDICE_DAMAGE });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        targets.remove_if([](WorldObject const* target)->bool
        {
            return !target->GetTransGUID();
        });
    }

    void HandleHit(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();

        if (Creature* caster = GetCaster()->ToCreature())
        {
            if (caster->IsAIEnabled() && !caster->IsInCombat())
                caster->AI()->DoZoneInCombat();

            if (target->GetTransOffsetZ() > 9.5f)
                caster->CastSpell(target, SPELL_SHADOW_OF_COWARDICE_DAMAGE, true);
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_nefarians_end_onyxia_start_fight_2_effect::HandleHit, EFFECT_0, SPELL_EFFECT_DUMMY);
        OnObjectAreaTargetSelect.Register(&spell_nefarians_end_onyxia_start_fight_2_effect::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
    }
};

class spell_nefarians_end_empowering_strikes : public AuraScript
{
    void HandlePeriodicTick(AuraEffect const* /*aurEff*/)
    {
        PreventDefaultAction();
        GetTarget()->CastSpell(GetTarget(), GetSpellInfo()->Effects[EFFECT_0].TriggerSpell, TriggerCastFlags(TRIGGERED_FULL_MASK & ~TRIGGERED_IGNORE_CASTER_AURAS));
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_nefarians_end_empowering_strikes::HandlePeriodicTick, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_nefarians_end_brushfire_pre_start_periodic : public AuraScript
{
    bool Load() override
    {
        _nextTriggerTickNumber = 1;
        return true;
    }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_BRUSHFIRE_START });
    }

    void HandlePeriodicTick(AuraEffect const* /*aurEff*/)
    {
        Unit* target = GetTarget();
        _ticksSinceLastTrigger++;
        if (_ticksSinceLastTrigger == _nextTriggerTickNumber)
        {
            target->CastSpell(target, SPELL_BRUSHFIRE_START, true);
            _ticksSinceLastTrigger = 0;

            if (_nextTriggerTickNumber == 1)
                _nextTriggerTickNumber = 6;
            else
                _nextTriggerTickNumber = std::max<uint32>(MinimumTriggerTicks(target), _nextTriggerTickNumber - 1);
        }
    }

    // The aura ticks every 5 s, so sparks come 30, 25, 20 and 15 s apart and
    // then settle at 15 s on normal and 10 s on heroic. BigWigs_Cataclysm
    // v11.0.13 (650bab0, Nefarian.lua ShadowblazeSpark: "self:Normal() and 15
    // or 10") and DBM-Cataclysm 4b02efe (ShadowBlazeFunction: 10-second floor
    // on heroic only) agree on that floor.
    static uint8 MinimumTriggerTicks(Unit const* target)
    {
        return target->GetMap()->IsHeroic() ? 2 : 3;
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_nefarians_end_brushfire_pre_start_periodic::HandlePeriodicTick, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }

private:
    uint8 _nextTriggerTickNumber = 0;
    uint8 _ticksSinceLastTrigger = 0;
};

class spell_nefarians_end_brushfire_start : public SpellScript
{
    void HandleDummyEffect(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
            caster->CastSpell(GetHitUnit(), GetSpellInfo()->Effects[effIndex].BasePoints, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_nefarians_end_brushfire_start::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_nefarians_end_brushfire_growth : public AuraScript
{
    void HandlePeriodicTick(AuraEffect const* /*aurEff*/)
    {
        if (Creature* creature = GetTarget()->ToCreature())
            if (creature->IsAIEnabled())
                creature->AI()->DoAction(ACTION_SPREAD_FLAMES);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_nefarians_end_brushfire_growth::HandlePeriodicTick, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

class spell_nefarians_end_shadowblaze : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_PERMANENT_FEIGN_DEATH_2,
                SPELL_FULL_POWER_NO_REGEN,
                SPELL_CLEAR_ALL_DEBUFFS
            });
    }

    void HandleHit(SpellEffIndex effIndex)
    {
        Creature* target = GetHitCreature();
        if (!target)
            return;

        if (target->HasAura(SPELL_PERMANENT_FEIGN_DEATH_2))
        {
            target->SetReactState(REACT_AGGRESSIVE);
            if (target->IsAIEnabled())
                target->AI()->DoZoneInCombat();

            target->RemoveAurasDueToSpell(SPELL_PERMANENT_FEIGN_DEATH_2);
            target->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
        }

        target->CastSpell(target, SPELL_CLEAR_ALL_DEBUFFS, true);
        target->CastSpell(target, SPELL_FULL_POWER_NO_REGEN);
        target->CastSpell(target, GetSpellInfo()->Effects[effIndex].BasePoints);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_nefarians_end_shadowblaze::HandleHit, EFFECT_1, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_nefarians_end_dominion_dummy : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_DOMINION_OVERRIDE_ACTION_BAR });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        Unit* caster = GetCaster();
        uint8 size = caster->GetMap()->Is25ManRaid() ? 2 : 5;
        if (!targets.empty())
            caster->CastSpell(caster, SPELL_DOMINION_OVERRIDE_ACTION_BAR, CastSpellExtraArgs(true).AddSpellMod(SPELLVALUE_MAX_TARGETS, size));
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_nefarians_end_dominion_dummy::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
    }
};

class spell_nefarians_end_dominion : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_SUMMON_DOMINION_STALKER_NORTH,
                SPELL_SUMMON_DOMINION_STALKER_SOUTH,
                SPELL_SUMMON_DOMINION_STALKER_EAST,
                SPELL_SUMMON_DOMINION_STALKER_WEST,
                SPELL_DOMINION_IMMUNITY
            });
    }

    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();

        for (uint8 i = 0; i < DominionStalkerSpellCount; i++)
            target->CastSpell(target, DominionStalkerSummonSpells[i], true);

        target->CastSpell(target, SPELL_DOMINION_IMMUNITY, true);
        target->SetByteFlag(UNIT_FIELD_BYTES_2, UNIT_BYTES_2_OFFSET_PVP_FLAG, UNIT_BYTE2_FLAG_UNK1);
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->RemoveAurasDueToSpell(SPELL_DOMINION_IMMUNITY);
        target->RemoveByteFlag(UNIT_FIELD_BYTES_2, UNIT_BYTES_2_OFFSET_PVP_FLAG, UNIT_BYTE2_FLAG_UNK1);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_nefarians_end_dominion::AfterApply, EFFECT_0, SPELL_AURA_OVERRIDE_SPELLS, AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove.Register(&spell_nefarians_end_dominion::AfterRemove, EFFECT_0, SPELL_AURA_OVERRIDE_SPELLS, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_nefarians_end_determine_farthest_portal_stalker : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_DOMINION_PORTAL_TRIGGER });
    }

    void HandlePeriodicTick(AuraEffect const* /*aurEff*/)
    {
        TempSummon* target = GetTarget()->ToTempSummon();
        if (!target)
            return;

        bool farthest = true;

        // This is very ugly and should be changed asap when we have a clean way to select all summoned units of a player
        std::list<Creature*> portalStalkers;
        Unit* summoner = target->GetSummoner();
        target->GetCreatureListWithEntryInGrid(portalStalkers, NPC_DOMINION_STALKER, 100.f);

        // Iterating through all stalkers of a player and select his furthest stalker
        for (Creature* stalker : portalStalkers)
        {
            TempSummon* summon = stalker->ToTempSummon();
            if (!summon || summon->GetSummonerGUID() != target->GetSummonerGUID() || summon == target)
                continue;

            if (summon->GetExactDist2d(summoner) > target->GetExactDist2d(summoner))
                farthest = false;
        }

        if (farthest)
        {
            target->CastSpell(target, SPELL_DOMINION_PORTAL_TRIGGER);
            Remove();
        }
        else
            target->DespawnOrUnsummon();
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_nefarians_end_determine_farthest_portal_stalker::HandlePeriodicTick, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

class spell_nefarians_end_dominion_portal_trigger : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_DOMINION_PORTAL_BEAM,
                SPELL_INSTAKILL_SELF
            });
    }

    void HandleHit(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();
        if (Unit* caster = GetCaster())
        {
            caster->CastSpell(caster, SPELL_DOMINION_PORTAL_BEAM);

            Movement::MoveSplineInit init(target);
            init.SetWalk(true);
            init.SetVelocity(3.5f);
            init.MoveTo(caster->GetPositionX(), caster->GetPositionY(), caster->GetPositionZ(), false); // Todo: enable pathfinding when mmaps for transports have arrived
            target->m_Events.AddEventAtOffset([target, caster]()
            {
                if (target->HasAura(SPELL_DOMINION_OVERRIDE_ACTION_BAR))
                    target->CastSpell(target, SPELL_INSTAKILL_SELF, true);

                if (Creature* creature = caster->ToCreature())
                    creature->DespawnOrUnsummon();
            }, Milliseconds(init.Launch()));
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_nefarians_end_dominion_portal_trigger::HandleHit, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_nefarians_end_free_your_mind : public AuraScript
{
    void AfterRemove(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->RemoveAurasDueToSpell(aurEff->GetAmount());
        target->StopMoving();
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_nefarians_end_free_your_mind::AfterRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_nefarians_end_siphon_power : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_STOLEN_POWER });
    }

    void HandleHit(SpellEffIndex /*effIndex*/)
    {
        GetHitUnit()->CastSpell(GetHitUnit(), SPELL_STOLEN_POWER);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_nefarians_end_siphon_power::HandleHit, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_nefarians_end_explosive_cinders : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_EXPLOSIVE_CINDERS_EXPLOSION });
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (GetTargetApplication()->GetRemoveMode().HasFlag(AuraRemoveFlags::Expired))
            GetTarget()->CastSpell(GetTarget(), SPELL_EXPLOSIVE_CINDERS_EXPLOSION, true);
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_nefarians_end_explosive_cinders::AfterRemove, EFFECT_0, SPELL_AURA_PERIODIC_DAMAGE, AURA_EFFECT_HANDLE_REAL);
    }
};
}

void AddSC_boss_nefarians_end_spells()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::NefariansEnd;
    RegisterSpellScript(spell_nefarians_end_electrical_charge);
    RegisterSpellScript(spell_nefarians_end_lightning_discharge_triggered_periodic_aura);
    RegisterSpellScript(spell_nefarians_end_lightning_discharge_cone);
    RegisterSpellScript(spell_nefarians_end_lightning_discharge_damage);
    RegisterSpellScript(spell_nefarians_end_children_of_deathwing);
    RegisterSpellScript(spell_nefarians_end_animate_bones);
    RegisterSpellScript(spell_nefarians_end_animate_bones_dummy);
    RegisterSpellScript(spell_nefarians_end_shadowflame_breath);
    RegisterSpellScript(spell_nefarians_end_jump_down_to_platform);
    RegisterSpellScript(spell_nefarians_end_shadow_of_cowardice);
    RegisterSpellScript(spell_nefarians_end_onyxia_start_fight_2_effect);
    RegisterSpellScript(spell_nefarians_end_empowering_strikes);
    RegisterSpellScript(spell_nefarians_end_brushfire_pre_start_periodic);
    RegisterSpellScript(spell_nefarians_end_brushfire_start);
    RegisterSpellScript(spell_nefarians_end_brushfire_growth);
    RegisterSpellScript(spell_nefarians_end_shadowblaze);
    RegisterSpellScript(spell_nefarians_end_dominion_dummy);
    RegisterSpellScript(spell_nefarians_end_dominion);
    RegisterSpellScript(spell_nefarians_end_determine_farthest_portal_stalker);
    RegisterSpellScript(spell_nefarians_end_dominion_portal_trigger);
    RegisterSpellScript(spell_nefarians_end_free_your_mind);
    RegisterSpellScript(spell_nefarians_end_siphon_power);
    RegisterSpellScript(spell_nefarians_end_explosive_cinders);
}
