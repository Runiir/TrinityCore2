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
#include "AbstractPursuer.h"
#include "Archaeology.h"
#include "Battlefield.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "BattlefieldMgr.h"
#include "Battleground.h"
#include "BattlegroundScore.h"
#include "CellImpl.h"
#include "CharacterCache.h"
#include "CharmInfo.h"
#include "Chat.h"
#include "ChatTextBuilder.h"
#include "ChatPackets.h"
#include "CombatLogPackets.h"
#include "CombatPackets.h"
#include "Common.h"
#include "ConditionMgr.h"
#include "Containers.h"
#include "CreatureAI.h"
#include "CreatureAIImpl.h"
#include "CreatureGroups.h"
#include "Formulas.h"
#include "GameClient.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "InstanceSaveMgr.h"
#include "InstanceScript.h"
#include "Item.h"
#include "ListUtils.h"
#include "Log.h"
#include "LootMgr.h"
#include "LootPackets.h"
#include "MiscPackets.h"
#include "MotionMaster.h"
#include "MovementGenerator.h"
#include "MovementPackets.h"
#include "MovementPacketBuilder.h"
#include "MovementStructures.h"
#include "MoveSpline.h"
#include "MoveSplineInit.h"
#include "MovementPacketSender.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Opcodes.h"
#include "OutdoorPvP.h"
#include "PassiveAI.h"
#include "Pet.h"
#include "PetPackets.h"
#include "PetAI.h"
#include "PhasingHandler.h"
#include "Player.h"
#include "PlayerAI.h"
#include "QuestDef.h"
#include "ReputationMgr.h"
#include "ScheduledChangeAI.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellCastRequest.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "SpellPackets.h"
#include "TemporarySummon.h"
#include "Totem.h"
#include "Transport.h"
#include "UnitAI.h"
#include "UpdateFieldFlags.h"
#include "Util.h"
#include "Vehicle.h"
#include "VehiclePackets.h"
#include "World.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include <cmath>
#include <queue>

static_assert(uint8(BASE_ATTACK) == 0 && uint8(OFF_ATTACK) == 1
    && uint8(RANGED_ATTACK) == 2, "melee telemetry attack type names require update");
static_assert(uint8(MELEE_HIT_EVADE) == 0 && uint8(MELEE_HIT_MISS) == 1
    && uint8(MELEE_HIT_DODGE) == 2 && uint8(MELEE_HIT_BLOCK) == 3
    && uint8(MELEE_HIT_PARRY) == 4 && uint8(MELEE_HIT_GLANCING) == 5
    && uint8(MELEE_HIT_CRIT) == 6 && uint8(MELEE_HIT_CRUSHING) == 7
    && uint8(MELEE_HIT_NORMAL) == 8,
    "melee telemetry outcome names require update");

/// @todo for melee need create structure as in
void Unit::CalculateMeleeDamage(Unit* victim, CalcDamageInfo* damageInfo, WeaponAttackType attackType /*= BASE_ATTACK*/)
{
    damageInfo->Attacker = this;
    damageInfo->Target = victim;

    damageInfo->DamageSchoolMask = GetMeleeDamageSchoolMask(attackType);
    damageInfo->Damage = 0;
    damageInfo->OriginalDamage = 0;
    damageInfo->Absorb = 0;
    damageInfo->Resist = 0;

    damageInfo->Blocked = 0;
    damageInfo->HitInfo = 0;
    damageInfo->TargetState = 0;

    damageInfo->AttackType = attackType;
    damageInfo->ProcAttacker = PROC_FLAG_NONE;
    damageInfo->ProcVictim = PROC_FLAG_NONE;
    damageInfo->UnmitigatedDamage = 0;
    damageInfo->HitOutCome = MELEE_HIT_EVADE;
    damageInfo->RageGained = 0;
    damageInfo->ResolutionObservation = MeleeDamageResolutionObservation{};

    if (!victim)
        return;

    if (!IsAlive() || !victim->IsAlive())
        return;

    MeleeDamageResolutionObservation& observation = damageInfo->ResolutionObservation;
    observation.StageMask |= MeleeDamageResolutionObservation::Inputs;
    observation.AttackType = uint8(attackType);
    observation.AttackerLevel = getLevel();
    observation.AttackerAttackPower = GetTotalAttackPowerValue(attackType);
    observation.AttackerBaseAttackTimeMs = GetBaseAttackTime(attackType);
    observation.AttackerBaseWeaponMinDamage = GetWeaponDamageRange(attackType, MINDAMAGE);
    observation.AttackerBaseWeaponMaxDamage = GetWeaponDamageRange(attackType, MAXDAMAGE);
    switch (attackType)
    {
        case BASE_ATTACK:
            observation.AttackerPublishedMinDamage = GetFloatValue(UNIT_FIELD_MINDAMAGE);
            observation.AttackerPublishedMaxDamage = GetFloatValue(UNIT_FIELD_MAXDAMAGE);
            break;
        case OFF_ATTACK:
            observation.AttackerPublishedMinDamage = GetFloatValue(UNIT_FIELD_MINOFFHANDDAMAGE);
            observation.AttackerPublishedMaxDamage = GetFloatValue(UNIT_FIELD_MAXOFFHANDDAMAGE);
            break;
        case RANGED_ATTACK:
            observation.AttackerPublishedMinDamage = GetFloatValue(UNIT_FIELD_MINRANGEDDAMAGE);
            observation.AttackerPublishedMaxDamage = GetFloatValue(UNIT_FIELD_MAXRANGEDDAMAGE);
            break;
        default:
            break;
    }
    observation.TargetArmor = victim->GetArmor();
    if (Creature const* creature = ToCreature())
    {
        if (CreatureTemplate const* creatureTemplate = creature->GetCreatureTemplate())
        {
            observation.AttackerTemplateInputsAvailable = true;
            observation.AttackerRank = creatureTemplate->rank;
            observation.AttackerTemplateDamageModifier = creatureTemplate->ModDamage;
            observation.AttackerTemplateBaseVariance = creatureTemplate->BaseVariance;
        }
    }

    // Select HitInfo/procAttacker/procVictim flag based on attack type
    switch (attackType)
    {
        case BASE_ATTACK:
            damageInfo->ProcAttacker = PROC_FLAG_DEAL_MELEE_SWING | PROC_FLAG_MAIN_HAND_WEAPON_SWING;
            damageInfo->ProcVictim   = PROC_FLAG_TAKE_MELEE_SWING;
            break;
        case OFF_ATTACK:
            damageInfo->ProcAttacker = PROC_FLAG_DEAL_MELEE_SWING | PROC_FLAG_OFF_HAND_WEAPON_SWING;
            damageInfo->ProcVictim   = PROC_FLAG_TAKE_MELEE_SWING;
            damageInfo->HitInfo      = HITINFO_OFFHAND;
            break;
        default:
            return;
    }

    // Physical Immune check
    if (damageInfo->Target->IsImmunedToDamage(SpellSchoolMask(damageInfo->DamageSchoolMask)))
    {
       damageInfo->HitInfo       |= HITINFO_NORMALSWING;
       damageInfo->TargetState    = VICTIMSTATE_IS_IMMUNE;

       damageInfo->Damage = 0;
       damageInfo->UnmitigatedDamage = 0;
       observation.ResolvedDamageAmount = 0;
       observation.TargetState = damageInfo->TargetState;
       observation.HitInfo = damageInfo->HitInfo;
       observation.StageMask |= MeleeDamageResolutionObservation::Resolution;
       return;
    }

    uint32 damage = 0;
    damage += CalculateDamage(damageInfo->AttackType, false, true);
    observation.WeaponRollAmount = damage;
    observation.StageMask |= MeleeDamageResolutionObservation::WeaponRoll;
    // Add melee damage bonus
    damage = MeleeDamageBonusDone(damageInfo->Target, damage, damageInfo->AttackType, DIRECT_DAMAGE, nullptr, MECHANIC_NONE, SpellSchoolMask(damageInfo->DamageSchoolMask));
    observation.AfterAttackerBonusAmount = damage;
    observation.StageMask |= MeleeDamageResolutionObservation::AttackerBonus;
    damage = damageInfo->Target->MeleeDamageBonusTaken(this, damage, damageInfo->AttackType, nullptr, SpellSchoolMask(damageInfo->DamageSchoolMask));
    observation.AfterTargetBonusAmount = damage;
    observation.StageMask |= MeleeDamageResolutionObservation::TargetBonus;

    // Script Hook For CalculateMeleeDamage -- Allow scripts to change the Damage pre class mitigation calculations
    sScriptMgr->ModifyMeleeDamage(damageInfo->Target, damageInfo->Attacker, damage);
    observation.AfterScriptHookAmount = damage;
    observation.StageMask |= MeleeDamageResolutionObservation::ScriptHook;

    // Calculate armor reduction
    if (Unit::IsDamageReducedByArmor((SpellSchoolMask)(damageInfo->DamageSchoolMask)))
    {
        observation.ArmorApplied = true;
        damageInfo->Damage = Unit::CalcArmorReducedDamage(damageInfo->Attacker, damageInfo->Target,
            damage, nullptr, damageInfo->AttackType, 0, &observation.EffectiveArmor);
    }
    else
        damageInfo->Damage = damage;
    observation.AfterArmorAmount = damageInfo->Damage;
    observation.StageMask |= MeleeDamageResolutionObservation::Armor;

    // Store unmitigated damage to reward rage later
    damageInfo->UnmitigatedDamage = damage;

    damageInfo->HitOutCome = RollMeleeOutcomeAgainst(damageInfo->Target, damageInfo->AttackType);
    observation.HitOutcome = uint8(damageInfo->HitOutCome);

    switch (damageInfo->HitOutCome)
    {
        case MELEE_HIT_EVADE:
            damageInfo->HitInfo        |= HITINFO_MISS | HITINFO_SWINGNOHITSOUND;
            damageInfo->TargetState     = VICTIMSTATE_EVADES;
            damageInfo->OriginalDamage  = damageInfo->Damage;

            damageInfo->Damage          = 0;
            observation.AfterHitOutcomeAmount = 0;
            observation.ResolvedDamageAmount = 0;
            observation.HitInfo = damageInfo->HitInfo;
            observation.TargetState = damageInfo->TargetState;
            observation.StageMask |= MeleeDamageResolutionObservation::HitOutcomeStage
                | MeleeDamageResolutionObservation::Resolution;
            return;
        case MELEE_HIT_MISS:
            damageInfo->HitInfo        |= HITINFO_MISS;
            damageInfo->TargetState     = VICTIMSTATE_INTACT;
            damageInfo->OriginalDamage = damageInfo->Damage;

            damageInfo->Damage          = 0;
            damageInfo->UnmitigatedDamage = 0;
            break;
        case MELEE_HIT_NORMAL:
            damageInfo->TargetState     = VICTIMSTATE_HIT;
            damageInfo->OriginalDamage = damageInfo->Damage;
            break;
        case MELEE_HIT_CRIT:
        {
            damageInfo->HitInfo        |= HITINFO_CRITICALHIT;
            damageInfo->TargetState     = VICTIMSTATE_HIT;

            // Crit bonus calc
            damageInfo->Damage *= 2;
            float mod = 0.0f;
            // Apply SPELL_AURA_MOD_ATTACKER_RANGED_CRIT_DAMAGE or SPELL_AURA_MOD_ATTACKER_MELEE_CRIT_DAMAGE
            if (damageInfo->AttackType == RANGED_ATTACK)
                mod += damageInfo->Target->GetTotalAuraModifier(SPELL_AURA_MOD_ATTACKER_RANGED_CRIT_DAMAGE);
            else
                mod += damageInfo->Target->GetTotalAuraModifier(SPELL_AURA_MOD_ATTACKER_MELEE_CRIT_DAMAGE);

            // Increase crit damage from SPELL_AURA_MOD_CRIT_DAMAGE_BONUS
            mod += (GetTotalAuraMultiplierByMiscMask(SPELL_AURA_MOD_CRIT_DAMAGE_BONUS, damageInfo->DamageSchoolMask) - 1.0f) * 100;

            if (mod != 0)
                AddPct(damageInfo->Damage, mod);

            damageInfo->OriginalDamage = damageInfo->Damage;
            break;
        }
        case MELEE_HIT_PARRY:
            damageInfo->TargetState  = VICTIMSTATE_PARRY;
            damageInfo->OriginalDamage = damageInfo->Damage;
            damageInfo->Damage = 0;
            break;
        case MELEE_HIT_DODGE:
            damageInfo->TargetState = VICTIMSTATE_DODGE;
            damageInfo->OriginalDamage = damageInfo->Damage;
            damageInfo->Damage = 0;
            break;
        case MELEE_HIT_BLOCK:
            damageInfo->TargetState = VICTIMSTATE_HIT;
            damageInfo->HitInfo |= HITINFO_BLOCK;
            // 30% damage blocked, double blocked amount if block is critical
            damageInfo->Blocked = CalculatePct(damageInfo->Damage, damageInfo->Target->GetBlockPercent());
            if (damageInfo->Target->IsBlockCritical())
                damageInfo->Blocked *= 2;

            damageInfo->OriginalDamage = damageInfo->Damage;
            damageInfo->Damage -= damageInfo->Blocked;
            break;
        case MELEE_HIT_GLANCING:
        {
            damageInfo->HitInfo     |= HITINFO_GLANCING;
            damageInfo->TargetState  = VICTIMSTATE_HIT;
            int32 leveldif = int32(victim->getLevel()) - int32(getLevel());
            if (leveldif > 3)
                leveldif = 3;

            damageInfo->OriginalDamage = damageInfo->Damage;
            float reducePercent = 1.f - leveldif * 0.1f;
            damageInfo->Damage = uint32(reducePercent * damageInfo->Damage);
            break;
        }
        case MELEE_HIT_CRUSHING:
            damageInfo->HitInfo     |= HITINFO_CRUSHING;
            damageInfo->TargetState  = VICTIMSTATE_HIT;
            // 150% normal damage
            damageInfo->Damage += (damageInfo->Damage / 2);
            damageInfo->OriginalDamage = damageInfo->Damage;
            break;
        default:
            break;
    }

    // Always apply HITINFO_AFFECTS_VICTIM in case its not a miss
    if (!(damageInfo->HitInfo & HITINFO_MISS))
        damageInfo->HitInfo |= HITINFO_AFFECTS_VICTIM;

    observation.AfterHitOutcomeAmount = damageInfo->Damage;
    observation.StageMask |= MeleeDamageResolutionObservation::HitOutcomeStage;

    int32 resilienceReduction = damageInfo->Damage;
    if (CanApplyResilience())
        Unit::ApplyResilience(victim, &resilienceReduction);
    resilienceReduction = damageInfo->Damage - resilienceReduction;
    damageInfo->Damage      -= resilienceReduction;
    observation.AfterResilienceAmount = damageInfo->Damage;
    observation.StageMask |= MeleeDamageResolutionObservation::Resilience;

    // Calculate absorb resist
    if (int32(damageInfo->Damage) > 0)
    {
        damageInfo->ProcVictim |= PROC_FLAG_TAKE_ANY_DAMAGE;
        // Calculate absorb & resists
        DamageInfo dmgInfo(*damageInfo);
        Unit::CalcAbsorbResist(dmgInfo);
        damageInfo->Absorb = dmgInfo.GetAbsorb();
        damageInfo->Resist = dmgInfo.GetResist();

        if (damageInfo->Absorb)
            damageInfo->HitInfo |= (damageInfo->Damage - damageInfo->Absorb == 0 ? HITINFO_FULL_ABSORB : HITINFO_PARTIAL_ABSORB);

        if (damageInfo->Resist)
            damageInfo->HitInfo |= (damageInfo->Damage - damageInfo->Resist == 0 ? HITINFO_FULL_RESIST : HITINFO_PARTIAL_RESIST);

        damageInfo->Damage = dmgInfo.GetDamage();
    }
    else // Impossible get negative result but....
        damageInfo->Damage = 0;

    observation.ResolvedDamageAmount = damageInfo->Damage;
    observation.BlockedAmount = damageInfo->Blocked;
    observation.AbsorbedAmount = damageInfo->Absorb;
    observation.ResistedAmount = damageInfo->Resist;
    observation.HitInfo = damageInfo->HitInfo;
    observation.TargetState = damageInfo->TargetState;
    observation.StageMask |= MeleeDamageResolutionObservation::Resolution;
}

void Unit::DealMeleeDamage(CalcDamageInfo* damageInfo, bool durabilityLoss, uint64 resolutionEventSequence)
{
    Unit* victim = damageInfo->Target;

    if (!victim->IsAlive() || victim->HasUnitState(UNIT_STATE_IN_FLIGHT) || (victim->GetTypeId() == TYPEID_UNIT && victim->ToCreature()->IsEvadingAttacks()))
        return;

    if (damageInfo->TargetState == VICTIMSTATE_PARRY &&
        (GetTypeId() != TYPEID_UNIT || (ToCreature()->GetCreatureTemplate()->flags_extra & CREATURE_FLAG_EXTRA_NO_PARRY_HASTEN) == 0))
    {
        // Get attack timers
        float offtime  = float(victim->getAttackTimer(OFF_ATTACK));
        float basetime = float(victim->getAttackTimer(BASE_ATTACK));
        // Reduce attack time
        if (victim->haveOffhandWeapon() && offtime < basetime)
        {
            float percent20 = victim->GetBaseAttackTime(OFF_ATTACK) * 0.20f;
            float percent60 = 3.0f * percent20;
            if (offtime > percent20 && offtime <= percent60)
                victim->setAttackTimer(OFF_ATTACK, uint32(percent20));
            else if (offtime > percent60)
            {
                offtime -= 2.0f * percent20;
                victim->setAttackTimer(OFF_ATTACK, uint32(offtime));
            }
        }
        else
        {
            float percent20 = victim->GetBaseAttackTime(BASE_ATTACK) * 0.20f;
            float percent60 = 3.0f * percent20;
            if (basetime > percent20 && basetime <= percent60)
                victim->setAttackTimer(BASE_ATTACK, uint32(percent20));
            else if (basetime > percent60)
            {
                basetime -= 2.0f * percent20;
                victim->setAttackTimer(BASE_ATTACK, uint32(basetime));
            }
        }
    }

    // Call default DealDamage
    Unit::DealDamage(this, victim, damageInfo->Damage, damageInfo->UnmitigatedDamage,
        DIRECT_DAMAGE, SpellSchoolMask(damageInfo->DamageSchoolMask), nullptr,
        durabilityLoss, resolutionEventSequence);

    // If this is a creature and it attacks from behind it has a probability to daze it's victim
    if ((damageInfo->HitOutCome == MELEE_HIT_CRIT || damageInfo->HitOutCome == MELEE_HIT_CRUSHING || damageInfo->HitOutCome == MELEE_HIT_NORMAL || damageInfo->HitOutCome == MELEE_HIT_GLANCING) &&
        IsCreature() && !ToCreature()->IsControlledByPlayer() && !ToCreature()->HasStaticFlag(CREATURE_STATIC_FLAG_4_CANNOT_DAZE) &&
        !victim->HasInArc(float(M_PI), this) && (victim->IsPlayer() || (victim->IsCreature() && !victim->ToCreature()->isWorldBoss())) && !victim->IsVehicle())
    {
        // 20% base chance
        float chance = 20.0f;

        // there is a newbie protection, at level 10 just 7% base chance; assuming linear function
        if (victim->getLevel() < 30)
            chance = 0.65f * victim->getLevel() + 0.5f;

        uint32 const victimDefense = victim->GetMaxSkillValueForLevel(this);
        uint32 const attackerMeleeSkill = GetMaxSkillValueForLevel();

        chance *= attackerMeleeSkill / float(victimDefense) * 0.16f;

        // -probability is between 0% and 40%
        RoundToInterval(chance, 0.0f, 40.0f);
        if (roll_chance_f(chance))
            CastSpell(victim, 1604 /*SPELL_DAZED*/, true);
    }

    if (GetTypeId() == TYPEID_PLAYER)
    {
        DamageInfo dmgInfo(*damageInfo);
        ToPlayer()->CastItemCombatSpell(dmgInfo);
    }

    // Do effect if any damage done to target
    if (damageInfo->Damage)
    {
        // We're going to call functions which can modify content of the list during iteration over it's elements
        // Let's copy the list so we can prevent iterator invalidation
        AuraEffectList vDamageShieldsCopy(victim->GetAuraEffectsByType(SPELL_AURA_DAMAGE_SHIELD));
        for (AuraEffect const* aurEff : vDamageShieldsCopy)
        {
            SpellInfo const* spellInfo = aurEff->GetSpellInfo();

            // Damage shield can be resisted...
            SpellMissInfo missInfo = victim->SpellHitResult(this, spellInfo, false);
            if (missInfo != SPELL_MISS_NONE)
            {
                victim->SendSpellMiss(this, spellInfo->Id, missInfo);
                continue;
            }

            // ...or immuned
            if (IsImmunedToDamage(spellInfo))
            {
                victim->SendSpellDamageImmune(this, spellInfo->Id);
                continue;
            }

            uint32 damage = aurEff->GetAmount();
            if (Unit* caster = aurEff->GetCaster())
            {
                damage = caster->SpellDamageBonusDone(this, spellInfo, damage, SPELL_DIRECT_DAMAGE, aurEff->GetEffIndex());
                damage = SpellDamageBonusTaken(caster, spellInfo, damage, SPELL_DIRECT_DAMAGE);
            }

            DamageInfo dmgInfo(this, victim, damage, spellInfo, spellInfo->GetSchoolMask(), SPELL_DIRECT_DAMAGE, BASE_ATTACK);
            victim->CalcAbsorbResist(dmgInfo);
            damage = dmgInfo.GetDamage();
            Unit::DealDamageMods(victim, damage, nullptr);

            /// @todo Move this to a packet handler
            WorldPackets::CombatLog::SpellDamageShield damageShield;
            damageShield.Attacker = victim->GetGUID();
            damageShield.Defender = GetGUID();
            damageShield.SpellID = spellInfo->Id;
            damageShield.TotalDamage = damage;
            damageShield.OverKill = std::max(int32(damage) - int32(GetHealth()), 0);
            damageShield.SchoolMask = spellInfo->SchoolMask;
            damageShield.LogAbsorbed = dmgInfo.GetAbsorb();
            victim->SendMessageToSet(damageShield.Write(), true);

            Unit::DealDamage(victim, this, damage, 0, SPELL_DIRECT_DAMAGE, spellInfo->GetSchoolMask(), spellInfo, true);
        }
    }
}
