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

#include "Totem.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Group.h"
#include "Opcodes.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "SpellInfo.h"
#include "WorldPacket.h"

namespace
{
bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth = 0)
{
    if (!spellInfo || depth > 4)
        return false;
    if (spellInfo->Id == 48505 || spellInfo->Id == 89751)
        return true;
    for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[effectIndex];
        if (!effect.IsEffect())
            continue;
        if (!spellInfo->IsPositiveEffect(effectIndex)
            && (effect.ChainTarget > 1 || effect.IsTargetingArea()
                || effect.IsEffect(SPELL_EFFECT_PERSISTENT_AREA_AURA)
                || effect.IsAreaAuraEffect()))
            return true;
        if (effect.TriggerSpell
            && SpellHasHostileMultiTargetSemantics(
                sSpellMgr->GetSpellInfo(effect.TriggerSpell), depth + 1))
            return true;
    }
    return false;
}

bool RaidTotemSpellSuppressed(Totem const* totem, uint32 spellId)
{
    Unit const* owner = totem ? totem->GetOwner() : nullptr;
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!owner || !spellInfo)
        return false;
    uint64 const ownerGuid = owner->GetGUID().GetRawValue();
    if (BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid)
        && !spellInfo->IsPositive())
        return true;
    return BotRaidAreaAuthority::HasProtectedEncounterEntries(ownerGuid)
        && SpellHasHostileMultiTargetSemantics(spellInfo);
}
}

Totem::Totem(SummonPropertiesEntry const* properties, Unit* owner) : Minion(properties, owner, false)
{
    m_unitTypeMask |= UNIT_MASK_TOTEM;
    m_duration = 0;
    m_type = TOTEM_PASSIVE;
}

void Totem::Update(uint32 time)
{
    if (!GetOwner()->IsAlive() || !IsAlive())
    {
        UnSummon();                                         // remove self
        return;
    }

    // Offensive totems own independent AI/passive aura cast paths.  Remove
    // the native summon when its owner enters a full offensive hold, or when
    // a hostile multi-target totem could reach an immediate-next protected
    // encounter.  Positive support totems remain untouched; a later ordinary
    // bot decision may natively summon an offensive totem again after release.
    if (RaidTotemSpellSuppressed(this, GetSpell())
        || RaidTotemSpellSuppressed(this, GetSpell(1)))
    {
        UnSummon();
        return;
    }

    if (m_duration <= time)
    {
        UnSummon();                                         // remove self
        return;
    }
    else
        m_duration -= time;

    Creature::Update(time);
}

void Totem::InitStats(uint32 duration)
{
    // client requires SMSG_TOTEM_CREATED to be sent before adding to world and before removing old totem
    if (GetOwner()->GetTypeId() == TYPEID_PLAYER
            && m_Properties->Slot >= SUMMON_SLOT_TOTEM_FIRE
            && m_Properties->Slot < MAX_TOTEM_SLOT)
    {
        WorldPacket data(SMSG_TOTEM_CREATED, 1 + 8 + 4 + 4);
        data << uint8(m_Properties->Slot - 1);
        data << uint64(GetGUID());
        data << uint32(duration);
        data << uint32(GetUInt32Value(UNIT_CREATED_BY_SPELL));
        GetOwner()->ToPlayer()->SendDirectMessage(&data);

        // set display id depending on caster's race
        SetDisplayId(GetOwner()->GetModelForTotem(PlayerTotemType(m_Properties->ID)));
    }

    Minion::InitStats(duration);

    // Get spell cast by totem
    if (SpellInfo const* totemSpell = sSpellMgr->GetSpellInfo(GetSpell()))
        if (totemSpell->CalcCastTime(getLevel()))   // If spell has cast time -> its an active totem
            m_type = TOTEM_ACTIVE;

    m_duration = duration;

    SetLevel(GetOwner()->getLevel());
}

void Totem::InitSummon()
{
    if (m_type == TOTEM_PASSIVE && GetSpell()
        && !RaidTotemSpellSuppressed(this, GetSpell()))
        CastSpell(this, GetSpell(), true);

    // Some totems can have both instant effect and passive spell
    if (GetSpell(1) && !RaidTotemSpellSuppressed(this, GetSpell(1)))
        CastSpell(this, GetSpell(1), true);

    if (m_Properties->ID == SUMMON_TYPE_TOTEM_FIRE && GetOwner()->HasAura(SPELL_TOTEMIC_WRATH_TALENT))
        CastSpell(this, SPELL_TOTEMIC_WRATH, true);
}

void Totem::UnSummon(uint32 msTime)
{
    if (msTime)
    {
        m_Events.AddEvent(new ForcedUnsummonDelayEvent(*this), m_Events.CalculateTime(msTime));
        return;
    }

    CombatStop();
    RemoveAurasDueToSpell(GetSpell(), GetGUID());

    // clear owner's totem slot
    for (uint8 i = SUMMON_SLOT_TOTEM_FIRE; i < MAX_TOTEM_SLOT; ++i)
    {
        if (GetOwner()->m_SummonSlot[i] == GetGUID())
        {
            GetOwner()->m_SummonSlot[i].Clear();
            break;
        }
    }

    GetOwner()->RemoveAurasDueToSpell(GetSpell(), GetGUID());

    // remove aura all party members too
    if (Player* owner = GetOwner()->ToPlayer())
    {
        owner->SendAutoRepeatCancel(this);

        if (SpellInfo const* spell = sSpellMgr->GetSpellInfo(GetUInt32Value(UNIT_CREATED_BY_SPELL)))
            GetSpellHistory()->SendCooldownEvent(spell, 0, nullptr, false);

        if (Group* group = owner->GetGroup())
        {
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* target = itr->GetSource();
                if (target && target->IsInMap(owner) && group->SameSubGroup(owner, target))
                    target->RemoveAurasDueToSpell(GetSpell(), GetGUID());
            }
        }
    }

    // Despawn elementals
    RemoveAllControlled();

    // any totem unsummon look like as totem kill, req. for proper animation
    if (IsAlive())
        setDeathState(DEAD);

    AddObjectToRemoveList();
}

bool Totem::IsImmunedToSpellEffect(SpellInfo const* spellInfo, uint32 index, WorldObject const* caster,
    bool requireImmunityPurgesEffectAttribute /*= false*/) const
{
    // immune to all positive spells, except of stoneclaw totem absorb and sentry totem bind sight
    // totems positive spells have unit_caster target
    if (spellInfo->Effects[index].Effect != SPELL_EFFECT_DUMMY &&
        spellInfo->Effects[index].Effect != SPELL_EFFECT_SCRIPT_EFFECT &&
        spellInfo->IsPositive() && spellInfo->Effects[index].TargetA.GetTarget() != TARGET_UNIT_CASTER &&
        spellInfo->Effects[index].TargetA.GetCheckType() != TARGET_CHECK_ENTRY && spellInfo->Id != SENTRY_STONECLAW_SPELLID && spellInfo->Id != SENTRY_BIND_SIGHT_SPELLID)
        return true;

    switch (spellInfo->Effects[index].ApplyAuraName)
    {
        case SPELL_AURA_PERIODIC_DAMAGE:
        case SPELL_AURA_PERIODIC_LEECH:
        case SPELL_AURA_MOD_FEAR:
        case SPELL_AURA_TRANSFORM:
            return true;
        default:
            break;
    }

    return Creature::IsImmunedToSpellEffect(spellInfo, index, caster, requireImmunityPurgesEffectAttribute);
}
