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

#include "TotemAI.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Totem.h"
#include "Creature.h"
#include "ObjectAccessor.h"
#include "SpellDefines.h"
#include "SpellMgr.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "CellImpl.h"

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

bool ProtectedTotemTarget(Unit const* owner, Unit const* target)
{
    Creature const* creature = target ? target->ToCreature() : nullptr;
    return owner && creature
        && BotRaidAreaAuthority::IsProtectedEncounterTarget(
            owner->GetGUID().GetRawValue(), creature->GetEntry(),
            creature->GetSpawnId(), creature->GetGUID().GetRawValue());
}
}

int32 TotemAI::Permissible(Creature const* creature)
{
    if (creature->IsTotem())
        return PERMIT_BASE_PROACTIVE;

    return PERMIT_BASE_NO;
}

TotemAI::TotemAI(Creature* creature) : NullCreatureAI(creature), _victimGUID()
{
    ASSERT(creature->IsTotem(), "TotemAI: AI assigned to a non-totem creature (%s)!", creature->GetGUID().ToString().c_str());
}

void TotemAI::UpdateAI(uint32 /*diff*/)
{
    ++_updateCalls;

    if (me->ToTotem()->GetTotemType() != TOTEM_ACTIVE)
        return;

    if (!me->IsAlive())
        return;

    if (me->IsNonMeleeSpellCast(false))
    {
        ++_castingSkips;
        return;
    }

    // Search spell
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(me->ToTotem()->GetSpell());
    if (!spellInfo)
    {
        ++_missingSpellSkips;
        return;
    }

    // Get spell range
    float max_range = spellInfo->GetMaxRange(false);

    // SpellModOp::Range not applied in this place just because not existence range mods for attacking totems

    // pointer to appropriate target if found any
    Unit* victim = _victimGUID ? ObjectAccessor::GetUnit(*me, _victimGUID) : nullptr;
    // Totems keep their authoritative summoner on Totem::GetOwner().  The
    // generic charmer/owner accessor can be empty for a freshly summoned
    // player totem, which made offensive totems reject their owner's valid
    // target and idle for their entire lifetime.
    Unit* owner = me->ToTotem()->GetOwner();
    if (owner && owner->GetTypeId() == TYPEID_PLAYER)
        me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED);
    uint64 const ownerGuid = owner ? owner->GetGUID().GetRawValue() : 0;
    if (ownerGuid && BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid))
    {
        me->InterruptNonMeleeSpells(false);
        _victimGUID.Clear();
        ++_noTargetSkips;
        return;
    }
    if (ownerGuid && BotRaidAreaAuthority::HasProtectedEncounterEntries(ownerGuid)
        && SpellHasHostileMultiTargetSemantics(spellInfo))
    {
        me->InterruptNonMeleeSpells(false);
        _victimGUID.Clear();
        ++_noTargetSkips;
        return;
    }
    if (ProtectedTotemTarget(owner, victim))
        victim = nullptr;
    bool totemCanAttack = victim && me->IsValidAttackTarget(victim, spellInfo);
    bool ownerCanAttack = victim && owner && owner->IsValidAttackTarget(victim, spellInfo);

    // Search victim if no, not attackable, or out of range, or friendly (possible in case duel end)
    if (!victim || !victim->isTargetableForAttack() || !me->IsWithinDistInMap(victim, max_range)
        || (!totemCanAttack && !ownerCanAttack) || !me->CanSeeOrDetect(victim))
    {
        victim = nullptr;
        Trinity::NearestAttackableUnitInObjectRangeCheck u_check(me, owner ? owner : me, max_range);
        Trinity::UnitLastSearcher<Trinity::NearestAttackableUnitInObjectRangeCheck> checker(me, victim, u_check);
        Cell::VisitAllObjects(me, checker, max_range);
        if (ProtectedTotemTarget(owner, victim))
            victim = nullptr;
        totemCanAttack = victim && me->IsValidAttackTarget(victim, spellInfo);
        ownerCanAttack = victim && owner && owner->IsValidAttackTarget(victim, spellInfo);
    }

    // If have target
    if (victim)
    {
        // remember
        _victimGUID = victim->GetGUID();

        // attack
        TriggerCastFlags flags = !totemCanAttack && ownerCanAttack
            ? TRIGGERED_IGNORE_TARGET_CHECK : TRIGGERED_NONE;
        _lastTotemTargetValid = totemCanAttack;
        _lastOwnerTargetValid = ownerCanAttack;
        ++_castAttempts;
        _lastCastResult = me->CastSpell(victim, me->ToTotem()->GetSpell(), CastSpellExtraArgs(flags));
        if (_lastCastResult == SPELL_CAST_OK)
            ++_castSuccesses;
    }
    else
    {
        ++_noTargetSkips;
        _victimGUID.Clear();
    }
}

void TotemAI::AttackStart(Unit* victim)
{
    Unit* owner = me->ToTotem()->GetOwner();
    if (owner && (BotRaidAreaAuthority::IsAllOffenseSuppressed(owner->GetGUID().GetRawValue())
        || ProtectedTotemTarget(owner, victim)))
    {
        _victimGUID.Clear();
        return;
    }
    _victimGUID = victim ? victim->GetGUID() : ObjectGuid::Empty;
}
