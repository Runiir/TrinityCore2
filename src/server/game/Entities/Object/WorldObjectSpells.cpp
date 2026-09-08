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

#include "Object.h"
#include "BattlefieldMgr.h"
#include "Battleground.h"
#include "CellImpl.h"
#include "Chat.h"
#include "CinematicMgr.h"
#include "CombatLogPackets.h"
#include "Common.h"
#include "Creature.h"
#include "DBCStores.h"
#include "G3DPosition.hpp"
#include "GameTime.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "Item.h"
#include "Log.h"
#include "MapManager.h"
#include "MiscPackets.h"
#include "MovementPacketBuilder.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "OutdoorPvPMgr.h"
#include "PhasingHandler.h"
#include "PathGenerator.h"
#include "Player.h"
#include "ReputationMgr.h"
#include "SpellAuraEffects.h"
#include "SpellDefines.h"
#include "SpellMgr.h"
#include "StringConvert.h"
#include "TemporarySummon.h"
#include "Totem.h"
#include "Transport.h"
#include "Unit.h"
#include "UpdateData.h"
#include "UpdateFieldFlags.h"
#include "UpdateMask.h"
#include "Util.h"
#include "Vehicle.h"
#include "VMapFactory.h"
#include "VMapManager2.h"
#include "WaypointMovementGenerator.h"
#include "World.h"
#include "WorldPacket.h"

// function uses real base points (typically value - 1)
int32 WorldObject::CalculateSpellDamage(Unit const* target, SpellInfo const* spellProto, uint8 effIndex, int32 const* basePoints /*= nullptr*/) const
{
    return spellProto->Effects[effIndex].CalcValue(this, basePoints, target);
}

float WorldObject::GetSpellMaxRangeForTarget(Unit const* target, SpellInfo const* spellInfo) const
{
    if (!spellInfo->RangeEntry)
        return 0;
    if (spellInfo->RangeEntry->RangeMax[1] == spellInfo->RangeEntry->RangeMax[0])
        return spellInfo->GetMaxRange();
    if (!target)
        return spellInfo->GetMaxRange(true);
    return spellInfo->GetMaxRange(!IsHostileTo(target));
}

float WorldObject::GetSpellMinRangeForTarget(Unit const* target, SpellInfo const* spellInfo) const
{
    if (!spellInfo->RangeEntry)
        return 0;
    if (spellInfo->RangeEntry->RangeMin[1] == spellInfo->RangeEntry->RangeMin[0])
        return spellInfo->GetMinRange();
    if (!target)
        return spellInfo->GetMinRange(true);
    return spellInfo->GetMinRange(!IsHostileTo(target));
}

float WorldObject::ApplyEffectModifiers(SpellInfo const* spellProto, uint8 effect_index, float value) const
{
    if (Player* modOwner = GetSpellModOwner())
    {
        modOwner->ApplySpellMod(spellProto, SpellModOp::Points, value);
        switch (effect_index)
        {
            case EFFECT_0:
                modOwner->ApplySpellMod(spellProto, SpellModOp::PointsIndex0, value);
                break;
            case EFFECT_1:
                modOwner->ApplySpellMod(spellProto, SpellModOp::PointsIndex1, value);
                break;
            case EFFECT_2:
                modOwner->ApplySpellMod(spellProto, SpellModOp::PointsIndex2, value);
                break;
            default:
                break;
        }
    }
    return value;
}

int32 WorldObject::CalcSpellDuration(SpellInfo const* spellInfo) const
{
    uint8 comboPoints = 0;
    if (Unit const* unit = ToUnit())
        comboPoints = unit->GetComboPoints();

    int32 minduration = spellInfo->GetDuration();
    int32 maxduration = spellInfo->GetMaxDuration();

    int32 duration = 0;
    if (spellInfo->HasAttribute(SPELL_ATTR1_FINISHING_MOVE_DURATION) && comboPoints && minduration != -1 && minduration != maxduration)
        duration = minduration + int32((maxduration - minduration) * comboPoints / 5);
    else
        duration = minduration;

    return duration;
}

int32 WorldObject::ModSpellDuration(SpellInfo const* spellInfo, WorldObject const* target, int32 duration, bool positive, uint32 effectMask)
{
    // don't mod permanent auras duration
    if (duration < 0)
        return duration;

    // some auras are not affected by duration modifiers
    if (spellInfo->HasAttribute(SPELL_ATTR7_NO_TARGET_DURATION_MOD))
        return duration;

    // cut duration only of negative effects
    Unit const* unitTarget = target->ToUnit();
    if (!unitTarget)
        return duration;

    // cut duration only of negative effects
    if (!positive)
    {
        int32 mechanicMask = spellInfo->GetSpellMechanicMaskByEffectMask(effectMask);
        auto mechanicCheck = [mechanicMask](AuraEffect const* aurEff) -> bool
        {
            if (mechanicMask & (1 << aurEff->GetMiscValue()))
                return true;
            return false;
        };

        // Find total mod value (negative bonus)
        int32 durationMod_always = unitTarget->GetTotalAuraModifier(SPELL_AURA_MECHANIC_DURATION_MOD, mechanicCheck);
        // Find max mod (negative bonus)
        int32 durationMod_not_stack = unitTarget->GetMaxNegativeAuraModifier(SPELL_AURA_MECHANIC_DURATION_MOD_NOT_STACK, mechanicCheck);

        // Select strongest negative mod
        int32 durationMod = std::min(durationMod_always, durationMod_not_stack);
        if (durationMod != 0)
            AddPct(duration, durationMod);

        // there are only negative mods currently
        durationMod_always = unitTarget->GetTotalAuraModifierByMiscValue(SPELL_AURA_MOD_AURA_DURATION_BY_DISPEL, spellInfo->Dispel);
        durationMod_not_stack = unitTarget->GetMaxNegativeAuraModifierByMiscValue(SPELL_AURA_MOD_AURA_DURATION_BY_DISPEL_NOT_STACK, spellInfo->Dispel);

        durationMod = std::min(durationMod_always, durationMod_not_stack);
        if (durationMod != 0)
            AddPct(duration, durationMod);

    }
    else
    {
        // else positive mods here, there are no currently
        // when there will be, change GetTotalAuraModifierByMiscValue to GetMaxPositiveAuraModifierByMiscValue

        // Mixology - duration boost
        if (unitTarget->GetTypeId() == TYPEID_PLAYER)
        {
            if (spellInfo->SpellFamilyName == SPELLFAMILY_POTION && (
                sSpellMgr->IsSpellMemberOfSpellGroup(spellInfo->Id, SPELL_GROUP_ELIXIR_BATTLE) ||
                sSpellMgr->IsSpellMemberOfSpellGroup(spellInfo->Id, SPELL_GROUP_ELIXIR_GUARDIAN)))
            {
                if (unitTarget->HasAura(53042) && unitTarget->HasSpell(spellInfo->Effects[0].TriggerSpell))
                    duration *= 2;
            }
        }
    }
    return std::max(duration, 0);
}

void WorldObject::ModSpellCastTime(SpellInfo const* spellInfo, int32& castTime, Spell* spell)
{
    if (!spellInfo || castTime < 0)
        return;

    // called from caster
    if (Player* modOwner = GetSpellModOwner())
        modOwner->ApplySpellMod(spellInfo, SpellModOp::ChangeCastTime, castTime, spell);

    Unit const* unitCaster = ToUnit();
    if (!unitCaster)
        return;

    if (unitCaster->IsPlayer() && unitCaster->ToPlayer()->GetCommandStatus(CHEAT_CASTTIME))
        castTime = 0;
    if (!(spellInfo->HasAttribute(SPELL_ATTR0_IS_ABILITY) || spellInfo->HasAttribute(SPELL_ATTR0_IS_TRADESKILL) || spellInfo->HasAttribute(SPELL_ATTR3_IGNORE_CASTER_MODIFIERS)) &&
        ((GetTypeId() == TYPEID_PLAYER && spellInfo->SpellFamilyName) || GetTypeId() == TYPEID_UNIT))
        castTime = int32(float(castTime) * GetFloatValue(UNIT_MOD_CAST_SPEED));
    else if (spellInfo->HasAttribute(SPELL_ATTR0_USES_RANGED_SLOT) && !spellInfo->HasAttribute(SPELL_ATTR2_AUTO_REPEAT))
        castTime = int32(float(castTime) * unitCaster->m_modAttackSpeedPct[RANGED_ATTACK]);
    else if (spellInfo->SpellVisual[0] == 3881 && unitCaster->HasAura(67556)) // cooking with Chef Hat.
        castTime = 500;
}

float WorldObject::MeleeSpellMissChance(Unit const* /*victim*/, WeaponAttackType /*attType*/, SpellInfo const* /*spellInfo*/) const
{
    return 0.0f;
}

SpellMissInfo WorldObject::MeleeSpellHitResult(Unit* /*victim*/, SpellInfo const* /*spellInfo*/) const
{
    return SPELL_MISS_NONE;
}

SpellMissInfo WorldObject::MagicSpellHitResult(Unit* victim, SpellInfo const* spellInfo) const
{
    // Can`t miss on dead target (on skinning for example)
    if (!victim->IsAlive() && !victim->IsPlayer())
        return SPELL_MISS_NONE;

    if (spellInfo->HasAttribute(SPELL_ATTR3_NO_AVOIDANCE))
        return SPELL_MISS_NONE;

    if (spellInfo->HasAttribute(SPELL_ATTR7_NO_ATTACK_MISS))
        return SPELL_MISS_NONE;

    SpellSchoolMask schoolMask = spellInfo->GetSchoolMask();

    // PvP - PvE spell misschances per leveldif > 2
    int32 lchance = victim->IsPlayer() ? 7 : 11;
    int32 thisLevel = getLevelForTarget(victim);
    if (GetTypeId() == TYPEID_UNIT && ToCreature()->IsTrigger())
        thisLevel = std::max<int32>(thisLevel, spellInfo->SpellLevel);
    int32 leveldif = int32(victim->getLevelForTarget(this)) - thisLevel;
    int32 levelBasedHitDiff = leveldif;

    // Base hit chance from attacker and victim levels
    int32 modHitChance = 100;
    if (levelBasedHitDiff >= 0)
    {
        if (victim->IsPlayer())
        {
            modHitChance = 94 - 3 * std::min(levelBasedHitDiff, 3);
            levelBasedHitDiff -= 3;
        }
        else
        {
            modHitChance = 96 - std::min(levelBasedHitDiff, 2);
            levelBasedHitDiff -= 2;
        }
        if (levelBasedHitDiff > 0)
            modHitChance -= lchance * std::min(levelBasedHitDiff, 7);
    }
    else
        modHitChance = 97 - levelBasedHitDiff;

    // Spellmod from SpellModOp::HitChance
    if (Player* modOwner = GetSpellModOwner())
        modOwner->ApplySpellMod(spellInfo, SpellModOp::HitChance, modHitChance);

    // Spells with SPELL_ATTR3_ALWAYS_HIT will ignore target's avoidance effects
    if (!spellInfo->HasAttribute(SPELL_ATTR3_ALWAYS_HIT))
    {
        // Chance hit from victim SPELL_AURA_MOD_ATTACKER_SPELL_HIT_CHANCE auras
        modHitChance += victim->GetTotalAuraModifierByMiscMask(SPELL_AURA_MOD_ATTACKER_SPELL_HIT_CHANCE, schoolMask);
    }
    // Decrease hit chance from victim rating bonus
    if (victim->IsPlayer())
        modHitChance -= int32(victim->ToPlayer()->GetRatingBonusValue(CR_HIT_TAKEN_SPELL));

    int32 hitChance = modHitChance * 100;
    // Increase hit chance from attacker SPELL_AURA_MOD_SPELL_HIT_CHANCE and attacker ratings
        // Increase hit chance from attacker SPELL_AURA_MOD_SPELL_HIT_CHANCE and attacker ratings
    if (Unit const* unit = ToUnit())
        hitChance += int32(unit->m_modSpellHitChance * 100.0f);

    RoundToInterval(hitChance, 0, 10000);

    int32 tmp = 10000 - hitChance;

    int32 rand = irand(0, 9999);
    if (tmp > 0 && rand < tmp)
        return SPELL_MISS_MISS;

    // Chance resist mechanic (select max value from every mechanic spell effect)
    int32 resist_chance = victim->GetMechanicResistChance(spellInfo) * 100;

    // Roll chance
    if (resist_chance > 0 && rand < (tmp += resist_chance))
        return SPELL_MISS_RESIST;

    // cast by caster in front of victim
    if (!victim->HasUnitState(UNIT_STATE_CONTROLLED) && (victim->HasInArc(float(M_PI), this) || victim->HasAuraType(SPELL_AURA_IGNORE_HIT_DIRECTION)))
    {
        int32 deflect_chance = victim->GetTotalAuraModifier(SPELL_AURA_DEFLECT_SPELLS) * 100;
        if (deflect_chance > 0 && rand < (tmp += deflect_chance))
            return SPELL_MISS_DEFLECT;
    }

    return SPELL_MISS_NONE;
}

// Calculate spell hit result can be:
// Every spell can: Evade/Immune/Reflect/Sucesful hit
// For melee based spells:
//   Miss
//   Dodge
//   Parry
// For spells
//   Resist
SpellMissInfo WorldObject::SpellHitResult(Unit* victim, SpellInfo const* spellInfo, bool canReflect /*= false*/) const
{
    // Check for immune
    if (victim->IsImmunedToSpell(spellInfo, this))
        return SPELL_MISS_IMMUNE;

    // Damage immunity is only checked if the spell has damage effects, this immunity must not prevent aura apply
    // returns SPELL_MISS_IMMUNE in that case, for other spells, the SMSG_SPELL_GO must show hit
    if (spellInfo->HasOnlyDamageEffects() && victim->IsImmunedToDamage(spellInfo))
        return SPELL_MISS_IMMUNE;

    // All positive spells can`t miss
    /// @todo client not show miss log for this spells - so need find info for this in dbc and use it!
    if (spellInfo->IsPositive() && !IsHostileTo(victim)) // prevent from affecting enemy by "positive" spell
        return SPELL_MISS_NONE;

    if (this == victim)
        return SPELL_MISS_NONE;

    // Return evade for units in evade mode
    if (victim->GetTypeId() == TYPEID_UNIT && victim->ToCreature()->IsEvadingAttacks())
        return SPELL_MISS_EVADE;

    // Try victim reflect spell
    if (canReflect)
    {
        int32 reflectchance = victim->GetTotalAuraModifier(SPELL_AURA_REFLECT_SPELLS);
        reflectchance += victim->GetTotalAuraModifierByMiscMask(SPELL_AURA_REFLECT_SPELLS_SCHOOL, spellInfo->GetSchoolMask());

        if (reflectchance > 0 && roll_chance_i(reflectchance))
            return spellInfo->HasAttribute(SPELL_ATTR7_REFLECTION_ONLY_DEFENDS) ? SPELL_MISS_DEFLECT : SPELL_MISS_REFLECT;
    }

    if (spellInfo->HasAttribute(SPELL_ATTR3_ALWAYS_HIT))
        return SPELL_MISS_NONE;

    switch (spellInfo->DmgClass)
    {
        case SPELL_DAMAGE_CLASS_RANGED:
        case SPELL_DAMAGE_CLASS_MELEE:
            return MeleeSpellHitResult(victim, spellInfo);
        case SPELL_DAMAGE_CLASS_NONE:
            return SPELL_MISS_NONE;
        case SPELL_DAMAGE_CLASS_MAGIC:
            return MagicSpellHitResult(victim, spellInfo);
    }
    return SPELL_MISS_NONE;
}

void WorldObject::SendSpellMiss(Unit* target, uint32 spellID, SpellMissInfo missInfo)
{
    WorldPackets::CombatLog::SpellMissLog spellMissLog;
    spellMissLog.SpellID = spellID;
    spellMissLog.Caster = GetGUID();
    spellMissLog.Entries.emplace_back(target->GetGUID(), missInfo);
    SendMessageToSet(spellMissLog.Write(), true);
}

FactionTemplateEntry const* WorldObject::GetFactionTemplateEntry() const
{
    uint32 factionId = GetFaction();
    FactionTemplateEntry const* entry = sFactionTemplateStore.LookupEntry(factionId);
    if (!entry)
    {
        switch (GetTypeId())
        {
            case TYPEID_PLAYER:
                TC_LOG_ERROR("entities.unit", "Player %s has invalid faction (faction template id) #%u", ToPlayer()->GetName().c_str(), factionId);
                break;
            case TYPEID_UNIT:
                TC_LOG_ERROR("entities.unit", "Creature (template id: %u) has invalid faction (faction template Id) #%u", ToCreature()->GetCreatureTemplate()->Entry, factionId);
                break;
            case TYPEID_GAMEOBJECT:
                if (factionId) // Gameobjects may have faction template id = 0
                    TC_LOG_ERROR("entities.faction", "GameObject (template id: %u) has invalid faction (faction template Id) #%u", ToGameObject()->GetGOInfo()->entry, factionId);
                break;
            default:
                TC_LOG_ERROR("entities.unit", "Object (name=%s, type=%u) has invalid faction (faction template Id) #%u", GetName().c_str(), uint32(GetTypeId()), factionId);
                break;
        }
    }

    return entry;
}

// function based on function Unit::UnitReaction from 13850 client
ReputationRank WorldObject::GetReactionTo(WorldObject const* target) const
{
    // always friendly to self
    if (this == target)
        return REP_FRIENDLY;

    // always friendly to charmer or owner
    if (GetCharmerOrOwnerOrSelf() == target->GetCharmerOrOwnerOrSelf())
        return REP_FRIENDLY;

    Player const* selfPlayerOwner = GetAffectingPlayer();
    Player const* targetPlayerOwner = target->GetAffectingPlayer();

    // check forced reputation to support SPELL_AURA_FORCE_REACTION
    if (selfPlayerOwner)
    {
        if (FactionTemplateEntry const* targetFactionTemplateEntry = target->GetFactionTemplateEntry())
            if (ReputationRank const* repRank = selfPlayerOwner->GetReputationMgr().GetForcedRankIfAny(targetFactionTemplateEntry))
                return *repRank;
    }
    else if (targetPlayerOwner)
    {
        if (FactionTemplateEntry const* selfFactionTemplateEntry = GetFactionTemplateEntry())
            if (ReputationRank const* repRank = targetPlayerOwner->GetReputationMgr().GetForcedRankIfAny(selfFactionTemplateEntry))
                return *repRank;
    }

    Unit const* unit = Coalesce<const Unit>(ToUnit(), selfPlayerOwner);
    Unit const* targetUnit = Coalesce<const Unit>(target->ToUnit(), targetPlayerOwner);
    if (unit && unit->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
    {
        if (targetUnit && targetUnit->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
        {
            if (selfPlayerOwner && targetPlayerOwner)
            {
                // always friendly to other unit controlled by player, or to the player himself
                if (selfPlayerOwner == targetPlayerOwner)
                    return REP_FRIENDLY;

                // duel - always hostile to opponent
                if (selfPlayerOwner->duel && selfPlayerOwner->duel->opponent == targetPlayerOwner && selfPlayerOwner->duel->startTime != 0)
                    return REP_HOSTILE;

                // same group - checks dependant only on our faction - skip FFA_PVP for example
                if (selfPlayerOwner->IsInRaidWith(targetPlayerOwner))
                    return REP_FRIENDLY; // return true to allow config option AllowTwoSide.Interaction.Group to work
                // however client seems to allow mixed group parties, because in 13850 client it works like:
                // return GetFactionReactionTo(GetFactionTemplateEntry(), target);
            }

            // check FFA_PVP
            if (unit->IsFFAPvP() && targetUnit->IsFFAPvP())
                return REP_HOSTILE;

            if (selfPlayerOwner)
            {
                if (FactionTemplateEntry const* targetFactionTemplateEntry = targetUnit->GetFactionTemplateEntry())
                {
                    if (ReputationRank const* repRank = selfPlayerOwner->GetReputationMgr().GetForcedRankIfAny(targetFactionTemplateEntry))
                        return *repRank;
                    if (!selfPlayerOwner->HasFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_IGNORE_REPUTATION))
                    {
                        if (FactionEntry const* targetFactionEntry = sFactionStore.LookupEntry(targetFactionTemplateEntry->Faction))
                        {
                            if (targetFactionEntry->CanHaveReputation())
                            {
                                // check contested flags
                                if (targetFactionTemplateEntry->IsHostileToPvpActivePlayers()
                                    && selfPlayerOwner->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_CONTESTED_PVP))
                                    return REP_HOSTILE;

                                // if faction has reputation, hostile state depends only from AtWar state
                                if (selfPlayerOwner->GetReputationMgr().IsAtWar(targetFactionEntry))
                                    return REP_HOSTILE;
                                return REP_FRIENDLY;
                            }
                        }
                    }
                }
            }
        }
    }

    // do checks dependant only on our faction
    return WorldObject::GetFactionReactionTo(GetFactionTemplateEntry(), target);
}


/*static*/ ReputationRank WorldObject::GetFactionReactionTo(FactionTemplateEntry const* factionTemplateEntry, WorldObject const* target)
{
    // always neutral when no template entry found
    if (!factionTemplateEntry)
        return REP_NEUTRAL;

    FactionTemplateEntry const* targetFactionTemplateEntry = target->GetFactionTemplateEntry();
    if (!targetFactionTemplateEntry)
        return REP_NEUTRAL;

    if (Player const* targetPlayerOwner = target->GetAffectingPlayer())
    {
        // check contested flags
        if (factionTemplateEntry->IsHostileToPvpActivePlayers()
            && targetPlayerOwner->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_CONTESTED_PVP))
            return REP_HOSTILE;
        if (ReputationRank const* repRank = targetPlayerOwner->GetReputationMgr().GetForcedRankIfAny(factionTemplateEntry))
            return *repRank;
        if (target->IsUnit() && !target->HasFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_IGNORE_REPUTATION))
        {
            if (FactionEntry const* factionEntry = sFactionStore.LookupEntry(factionTemplateEntry->Faction))
            {
                if (factionEntry->CanHaveReputation())
                {
                    // CvP case - check reputation, don't allow state higher than neutral when at war
                    ReputationRank repRank = targetPlayerOwner->GetReputationMgr().GetRank(factionEntry);
                    if (targetPlayerOwner->GetReputationMgr().IsAtWar(factionEntry))
                        repRank = std::min(REP_NEUTRAL, repRank);
                    return repRank;
                }
            }
        }
    }

    // common faction based check
    if (factionTemplateEntry->IsHostileTo(targetFactionTemplateEntry))
        return REP_HOSTILE;
    if (factionTemplateEntry->IsFriendlyTo(targetFactionTemplateEntry))
        return REP_FRIENDLY;
    if (targetFactionTemplateEntry->IsFriendlyTo(factionTemplateEntry))
        return REP_FRIENDLY;
    // neutral by default
    return REP_NEUTRAL;
}

bool WorldObject::IsHostileTo(WorldObject const* target) const
{
    return GetReactionTo(target) <= REP_HOSTILE;
}

bool WorldObject::IsFriendlyTo(WorldObject const* target) const
{
    return GetReactionTo(target) >= REP_FRIENDLY;
}

bool WorldObject::IsHostileToPlayers() const
{
    FactionTemplateEntry const* my_faction = GetFactionTemplateEntry();
    if (!my_faction->Faction)
        return false;

    FactionEntry const* raw_faction = sFactionStore.LookupEntry(my_faction->Faction);
    if (raw_faction && raw_faction->ReputationIndex >= 0)
        return false;

    return my_faction->IsHostileToPlayers();
}

bool WorldObject::IsNeutralToAll() const
{
    FactionTemplateEntry const* my_faction = GetFactionTemplateEntry();
    if (!my_faction->Faction)
        return true;

    FactionEntry const* raw_faction = sFactionStore.LookupEntry(my_faction->Faction);
    if (raw_faction && raw_faction->ReputationIndex >= 0)
        return false;

    return my_faction->IsNeutralToAll();
}

SpellCastResult WorldObject::CastSpell(CastSpellTargetArg const& targets, uint32 spellId, CastSpellExtraArgs const& args /*= { }*/)
{
    SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
    if (!info)
    {
        TC_LOG_ERROR("entities.unit", "CastSpell: unknown spell %u by caster %s", spellId, GetGUID().ToString().c_str());
        return SPELL_FAILED_SPELL_UNAVAILABLE;
    }

    if (!targets.Targets)
    {
        TC_LOG_ERROR("entities.unit", "CastSpell: Invalid target passed to spell cast %u by %s", spellId, GetGUID().ToString().c_str());
        return SPELL_FAILED_BAD_TARGETS;
    }

    Spell* spell = new Spell(this, info, args.TriggerFlags, args.OriginalCaster);
    for (CastSpellExtraArgsInit::SpellValueOverride const& value : args.SpellValueOverrides)
        spell->SetSpellValue(value);

    spell->m_CastItem = args.CastItem;

    if (!spell->m_CastItem && info->HasAttribute(SPELL_ATTR2_RETAIN_ITEM_CAST))
    {
        if (args.TriggeringSpell)
            spell->m_CastItem = args.TriggeringSpell->m_CastItem;
        else if (args.TriggeringAura && !args.TriggeringAura->GetBase()->GetCastItemGUID().IsEmpty())
            if (Unit const* auraCaster = args.TriggeringAura->GetCaster())
                if (Player const* triggeringAuraCaster = auraCaster->ToPlayer())
                    spell->m_CastItem = triggeringAuraCaster->GetItemByGuid(args.TriggeringAura->GetBase()->GetCastItemGUID());
    }

    spell->m_customArg = args.CustomArg;

    return spell->prepare(*targets.Targets, args.TriggeringAura);
}

// function based on function Unit::CanAttack from 13850 client
bool WorldObject::IsValidAttackTarget(WorldObject const* target, SpellInfo const* bySpell /*= nullptr*/) const
{
    ASSERT(target);

    // some positive spells can be casted at hostile target
    bool isPositiveSpell = bySpell && bySpell->IsPositive();

    // can't attack self (spells can, attribute check)
    if (!bySpell && this == target)
        return false;

    // can't attack unattackable units
    Unit const* unitTarget = target->ToUnit();
    if (unitTarget && unitTarget->HasUnitState(UNIT_STATE_UNATTACKABLE))
        return false;

    // can't attack GMs
    if (target->GetTypeId() == TYPEID_PLAYER && target->ToPlayer()->IsGameMaster())
        return false;

    Unit const* unit = ToUnit();
    // visibility checks (only units)
    if (unit)
    {
        // can't attack invisible
        if (!bySpell || !bySpell->HasAttribute(SPELL_ATTR6_IGNORE_PHASE_SHIFT))
        {
            if (!unit->CanSeeOrDetect(target, bySpell && bySpell->IsAffectingArea()))
                return false;
        }
    }

    // can't attack dead
    if ((!bySpell || !bySpell->IsAllowingDeadTarget()) && unitTarget && !unitTarget->IsAlive())
        return false;

    // can't attack untargetable
    if ((!bySpell || !bySpell->HasAttribute(SPELL_ATTR6_CAN_TARGET_UNTARGETABLE)) && unitTarget && unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE))
        return false;

    if (Player const* playerAttacker = ToPlayer())
    {
        if (playerAttacker->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_UBER))
            return false;
    }

    // check flags
    if (unitTarget && unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NON_ATTACKABLE | UNIT_FLAG_ON_TAXI | UNIT_FLAG_NOT_ATTACKABLE_1 | UNIT_FLAG_NON_ATTACKABLE_2))
        return false;

    Unit const* unitOrOwner = unit;
    GameObject const* go = ToGameObject();
    if (go && go->GetGoType() == GAMEOBJECT_TYPE_TRAP)
        unitOrOwner = go->GetOwner();

    // ignore immunity flags when assisting
    if (unitOrOwner && unitTarget && !(isPositiveSpell && bySpell->HasAttribute(SPELL_ATTR6_CAN_ASSIST_IMMUNE_PC)))
    {
        if (!unitOrOwner->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED) && unitTarget->IsImmuneToNPC())
            return false;

        if (!unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED) && unitOrOwner->IsImmuneToNPC())
            return false;

        if (!bySpell || !bySpell->HasAttribute(SPELL_ATTR8_ATTACK_IGNORE_IMMUNE_TO_PC_FLAG))
        {
            if (unitOrOwner->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED) && unitTarget->IsImmuneToPC())
                return false;

            if (unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED) && unitOrOwner->IsImmuneToPC())
                return false;
        }
    }

    // CvC case - can attack each other only when one of them is hostile
    if (unit && !unit->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED) && unitTarget && !unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
        return IsHostileTo(unitTarget) || unitTarget->IsHostileTo(this);

    // Traps without owner or with NPC owner versus Creature case - can attack to creature only when one of them is hostile
    if (go && go->GetGoType() == GAMEOBJECT_TYPE_TRAP)
    {
        Unit const* goOwner = go->GetOwner();
        if (!goOwner || !goOwner->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
            if (unitTarget && !unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
                return IsHostileTo(unitTarget) || unitTarget->IsHostileTo(this);
    }

    // PvP, PvC, CvP case
    // can't attack friendly targets
    if (IsFriendlyTo(target) || target->IsFriendlyTo(this))
        return false;

    Player const* playerAffectingAttacker = unit && HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED) ? GetAffectingPlayer() : go ? GetAffectingPlayer() : nullptr;
    Player const* playerAffectingTarget = unitTarget && unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED) ? unitTarget->GetAffectingPlayer() : nullptr;

    // Not all neutral creatures can be attacked (even some unfriendly faction does not react aggresive to you, like Sporaggar)
    if ((playerAffectingAttacker && !playerAffectingTarget) || (!playerAffectingAttacker && playerAffectingTarget))
    {
        Player const* player = playerAffectingAttacker ? playerAffectingAttacker : playerAffectingTarget;

        if (Unit const* creature = playerAffectingAttacker ? unitTarget : unit)
        {
            if (creature->IsContestedGuard() && player->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_CONTESTED_PVP))
                return true;

            if (FactionTemplateEntry const* factionTemplate = creature->GetFactionTemplateEntry())
            {
                if (!(player->GetReputationMgr().GetForcedRankIfAny(factionTemplate)))
                    if (FactionEntry const* factionEntry = sFactionStore.LookupEntry(factionTemplate->Faction))
                        if (FactionState const* repState = player->GetReputationMgr().GetState(factionEntry))
                            if (!(repState->Flags & FACTION_FLAG_AT_WAR))
                                return false;
            }
        }
    }

    if (playerAffectingAttacker && playerAffectingTarget)
        if (playerAffectingAttacker->duel && playerAffectingAttacker->duel->opponent == playerAffectingTarget && playerAffectingAttacker->duel->startTime != 0)
            return true;

    // PvP case - can't attack when attacker or target are in sanctuary
    // however, 13850 client doesn't allow to attack when one of the unit's has sanctuary flag and is pvp
    if (unitTarget && unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED)
        && unitOrOwner && unitOrOwner->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED)
        && (unitTarget->IsInSanctuary() || unitOrOwner->IsInSanctuary())
        && (!bySpell || bySpell->HasAttribute(SPELL_ATTR8_IGNORE_SANCTUARY)))
        return false;

    // additional checks - only PvP case
    if (playerAffectingAttacker && playerAffectingTarget)
    {
        if (playerAffectingTarget->IsPvP() || (bySpell && bySpell->HasAttribute(SPELL_ATTR5_IGNORE_AREA_EFFECT_PVP_CHECK)))
            return true;

        if (playerAffectingAttacker->IsFFAPvP() && playerAffectingTarget->IsFFAPvP())
            return true;

        return playerAffectingAttacker->HasByteFlag(UNIT_FIELD_BYTES_2, UNIT_BYTES_2_OFFSET_PVP_FLAG, UNIT_BYTE2_FLAG_UNK1)
            || playerAffectingTarget->HasByteFlag(UNIT_FIELD_BYTES_2, UNIT_BYTES_2_OFFSET_PVP_FLAG, UNIT_BYTE2_FLAG_UNK1);
    }

    return true;
}

// function based on function Unit::CanAssist from 13850 client
bool WorldObject::IsValidAssistTarget(WorldObject const* target, SpellInfo const* bySpell /*= nullptr*/) const
{
    ASSERT(target);

    // some negative spells can be casted at friendly target
    bool isNegativeSpell = bySpell && !bySpell->IsPositive();

    // can assist to self
    if (this == target)
        return true;

    // can't assist unattackable units
    Unit const* unitTarget = target->ToUnit();
    if (unitTarget && unitTarget->HasUnitState(UNIT_STATE_UNATTACKABLE))
        return false;

    // can't assist GMs
    if (target->GetTypeId() == TYPEID_PLAYER && target->ToPlayer()->IsGameMaster())
        return false;

    // can't assist own vehicle or passenger
    Unit const* unit = ToUnit();
    if (unit && unitTarget && unit->GetVehicle())
    {
        if (unit->IsOnVehicle(unitTarget))
            return false;

        if (unit->GetVehicleBase()->IsOnVehicle(unitTarget))
            return false;
    }

    // can't assist invisible
    if ((!bySpell || !bySpell->HasAttribute(SPELL_ATTR6_IGNORE_PHASE_SHIFT)) && !CanSeeOrDetect(target, bySpell && bySpell->IsAffectingArea()))
        return false;

    // can't assist dead
    if ((!bySpell || !bySpell->IsAllowingDeadTarget()) && unitTarget && !unitTarget->IsAlive())
        return false;

    // can't assist untargetable
    if ((!bySpell || !bySpell->HasAttribute(SPELL_ATTR6_CAN_TARGET_UNTARGETABLE)) && unitTarget && unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE))
        return false;

    // check flags for negative spells
    if (isNegativeSpell && unitTarget && unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NON_ATTACKABLE | UNIT_FLAG_ON_TAXI | UNIT_FLAG_NOT_ATTACKABLE_1 | UNIT_FLAG_NON_ATTACKABLE_2))
        return false;

    if (isNegativeSpell || !bySpell || !bySpell->HasAttribute(SPELL_ATTR6_CAN_ASSIST_IMMUNE_PC))
    {
        if (unit && HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
        {
            if (unitTarget && unitTarget->IsImmuneToPC())
                return false;
        }
        else
        {
            if (unitTarget && unitTarget->IsImmuneToNPC())
                return false;
        }
    }

    // can't assist non-friendly targets
    if (GetReactionTo(target) < REP_NEUTRAL && target->GetReactionTo(this) < REP_NEUTRAL && (!ToCreature() || !ToCreature()->HasStaticFlag(CREATURE_STATIC_FLAG_4_TREAT_AS_RAID_UNIT_FOR_HELPFUL_SPELLS)))
        return false;

    // PvP case
    if (unitTarget && unitTarget->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
    {
        if (unit && unit->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
        {
            Player const* selfPlayerOwner = GetAffectingPlayer();
            Player const* targetPlayerOwner = unitTarget->GetAffectingPlayer();
            if (selfPlayerOwner && targetPlayerOwner)
            {
                // can't assist player which is dueling someone
                if (selfPlayerOwner != targetPlayerOwner && targetPlayerOwner->duel)
                    return false;
            }
            // can't assist player in ffa_pvp zone from outside
            if (unitTarget->IsFFAPvP() && !unit->IsFFAPvP())
                return false;

            // can't assist player out of sanctuary from sanctuary if has pvp enabled
            if (unitTarget->IsPvP() && (!bySpell || bySpell->HasAttribute(SPELL_ATTR8_IGNORE_SANCTUARY)))
                if (unit->IsInSanctuary() && !unitTarget->IsInSanctuary())
                    return false;
        }
    }
    // PvC case - player can assist creature only if has specific type flags
    // !target->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PVP_ATTACKABLE) &&
    else if (unit && unit->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED))
    {
        if (!bySpell || !bySpell->HasAttribute(SPELL_ATTR6_CAN_ASSIST_IMMUNE_PC))
            if (unitTarget && !unitTarget->IsPvP())
                if (Creature const* creatureTarget = target->ToCreature())
                    return creatureTarget->HasStaticFlag(CREATURE_STATIC_FLAG_4_TREAT_AS_RAID_UNIT_FOR_HELPFUL_SPELLS) || (creatureTarget->GetCreatureTemplate()->type_flags & CREATURE_TYPE_FLAG_CAN_ASSIST);
    }

    return true;
}

Unit* WorldObject::GetMagicHitRedirectTarget(Unit* victim, SpellInfo const* spellInfo)
{
    // Patch 1.2 notes: Spell Reflection no longer reflects abilities
    if (spellInfo->HasAttribute(SPELL_ATTR0_IS_ABILITY) || spellInfo->HasAttribute(SPELL_ATTR1_NO_REDIRECTION) || spellInfo->HasAttribute(SPELL_ATTR0_NO_IMMUNITIES))
        return victim;

    Unit::AuraEffectList const& magnetAuras = victim->GetAuraEffectsByType(SPELL_AURA_SPELL_MAGNET);
    for (AuraEffect const* aurEff : magnetAuras)
    {
        if (Unit* magnet = aurEff->GetBase()->GetCaster())
        {
            if (spellInfo->CheckExplicitTarget(this, magnet) == SPELL_CAST_OK && IsValidAttackTarget(magnet, spellInfo))
            {
                /// @todo handle this charge drop by proc in cast phase on explicit target
                if (spellInfo->Speed > 0.0f)
                {
                    // Set up missile speed based delay
                    uint32 delay = uint32(std::floor(std::max<float>(victim->GetDistance(this), 5.0f) / spellInfo->Speed * 1000.0f));
                    // Schedule charge drop
                    aurEff->GetBase()->DropChargeDelayed(delay, AuraRemoveFlags::Expired);
                }
                else
                    aurEff->GetBase()->DropCharge(AuraRemoveFlags::Expired);

                return magnet;
            }
        }
    }
    return victim;
}
