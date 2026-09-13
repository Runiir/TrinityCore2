/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 * This program is free software; you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free Software
 * Foundation; either version 2 of the License, or (at your option) any later version.
 */

#include "ScriptMgr.h"
#include "CombatAI.h"
#include "CombatManager.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Creature.h"
#include "CreatureAIImpl.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include <algorithm>
#include <vector>

namespace Pets::Warlock
{
constexpr uint32 DoomBolt = 85692;
constexpr uint32 CastDoomBoltEvent = 1; // EventMap stores only 16-bit event IDs.

// A temporary guardian is not a primary Pet. Doomguard assists only targets
// carrying its owner's Bane of Doom or Bane of Agony, never arbitrary hostiles.
struct npc_pet_warlock_doomguard : CasterAI
{
    explicit npc_pet_warlock_doomguard(Creature* creature) : CasterAI(creature) { }

    void Reset() override
    {
        CombatAI::Reset();
        _lastOwnerTarget.Clear();
        _castScheduled = false;
    }

    void IsSummonedBy(Unit* summoner) override
    {
        if (summoner && summoner == Owner())
            RememberPendingTarget(summoner->GetVictim());
    }

    void MoveInLineOfSight(Unit*) override { }
    void OwnerAttackedBy(Unit*) override { }
    void JustEngagedWith(Unit*) override { }
    void OwnerAttacked(Unit* target) override { RememberPendingTarget(target); }
    void SpellInterrupted(uint32 spellId, uint32 unTimeMs) override
    {
        if (spellId == DoomBolt)
            events.RescheduleEvent(CastDoomBoltEvent, unTimeMs);
    }

    void AttackStart(Unit* target) override
    {
        Player* owner = Owner();
        if (owner && owner->IsInCombat() && me->IsAlive()
            && target && target == PreferredTarget() && sSpellMgr->GetSpellInfo(DoomBolt))
            AttackStartCaster(target, GetAISpellInfo(DoomBolt)->maxRange);
    }

    void UpdateAI(uint32 diff) override
    {
        events.Update(diff);
        Player* owner = Owner();
        if (!owner || !owner->IsAlive() || !owner->IsInWorld() || !owner->IsInMap(me)
            || !owner->IsInCombat() || !me->IsAlive())
        {
            StopOffense(owner);
            _lastOwnerTarget.Clear();
            return;
        }

        Unit* target = PreferredTarget();
        if (!target || !sSpellMgr->GetSpellInfo(DoomBolt) || GetAISpellInfo(DoomBolt)->maxRange <= 0)
        {
            StopOffense(owner);
            return;
        }
        if (me->GetVictim() != target)
        {
            StopOffense(owner);
            AttackStart(target);
        }
        if (me->GetVictim() != target || me->HasUnitState(UNIT_STATE_CASTING))
            return;

        if (!_castScheduled)
        {
            events.ScheduleEvent(CastDoomBoltEvent, 0);
            _castScheduled = true;
        }
        if (events.ExecuteEvent() == CastDoomBoltEvent)
        {
            DoCast(target, DoomBolt);
            // Match native CasterAI scheduling, including its failed/instant retry.
            uint32 const castTime = me->GetCurrentSpellCastTime(DoomBolt);
            events.ScheduleEvent(CastDoomBoltEvent, (castTime ? castTime : 500) + GetAISpellInfo(DoomBolt)->realCooldown);
        }
    }

private:
    Player* Owner() const
    {
        Unit* owner = me->GetOwner();
        Player* player = owner ? owner->ToPlayer() : nullptr;
        return player && player->getClass() == CLASS_WARLOCK ? player : nullptr;
    }

    bool LegalTarget(Unit* target) const
    {
        Player* owner = Owner();
        if (!owner || !owner->IsAlive() || !owner->IsInWorld() || !owner->IsInMap(me)
            || !target || !target->IsAlive() || !target->IsInWorld()
            || !me->IsInMap(target) || !owner->IsValidAttackTarget(target)
            || !me->IsValidAttackTarget(target) || target->HasBreakableByDamageCrowdControlAura(me))
            return false;
        uint64 const ownerGuid = owner->GetGUID().GetRawValue();
        if (BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid))
            return false;
        Creature const* creature = target->ToCreature();
        return !creature || !BotRaidAreaAuthority::IsProtectedEncounterTarget(ownerGuid,
            creature->GetEntry(), creature->GetSpawnId(), creature->GetGUID().GetRawValue());
    }

    bool EligibleTarget(Unit* target) const
    {
        return LegalTarget(target)
            && (target->GetAuraApplication(603, Owner()->GetGUID())
                || target->GetAuraApplication(980, Owner()->GetGUID()));
    }

    void RememberPendingTarget(Unit* target)
    {
        Player* owner = Owner();
        // Spell::cast notifies controlled AI before applying the Bane aura.
        // Remember identity here; only UpdateAI may promote it after application.
        if (owner && target && target->IsAlive() && target->IsInWorld()
            && owner->IsInMap(target) && me->IsInMap(target))
            _lastOwnerTarget = target->GetGUID();
    }

    Unit* PreferredTarget()
    {
        Player* owner = Owner();
        if (!owner)
            return nullptr;
        if (EligibleTarget(me->GetVictim()))
            return me->GetVictim();

        std::vector<Unit*> candidates;
        auto remember = [&](Unit* target)
        {
            if (EligibleTarget(target))
                candidates.push_back(target);
        };
        Unit* pending = ObjectAccessor::GetUnit(*me, _lastOwnerTarget);
        if (!pending || !pending->IsAlive() || !pending->IsInWorld() || !me->IsInMap(pending))
            _lastOwnerTarget.Clear();
        else
            remember(pending);
        remember(owner->GetVictim());
        for (auto const& entry : owner->GetCombatManager().GetPvECombatRefs())
            if (!entry.second->IsSuppressedFor(owner))
                remember(entry.second->GetOther(owner));
        for (auto const& entry : owner->GetCombatManager().GetPvPCombatRefs())
            if (!entry.second->IsSuppressedFor(owner))
                remember(entry.second->GetOther(owner));
        // Multiple Agonies (or Doom plus Agony on another target) can coexist.
        // Stable raw-GUID fallback is inferred; historical tie-breaking is unknown.
        std::sort(candidates.begin(), candidates.end(), [](Unit* a, Unit* b) { return a->GetGUID() < b->GetGUID(); });
        candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());
        return candidates.empty() ? nullptr : candidates.front();
    }

    void StopOffense(Unit* owner)
    {
        if (!me->GetVictim() && !me->HasUnitState(UNIT_STATE_CASTING))
            return;
        me->InterruptNonMeleeSpells(false);
        me->AttackStop();
        if (owner && owner->IsInWorld() && owner->IsInMap(me))
            me->FollowTarget(owner);
        else
        {
            me->GetMotionMaster()->Clear();
            me->StopMoving();
        }
    }

    ObjectGuid _lastOwnerTarget;
    bool _castScheduled = false;
};
}

void AddSC_warlock_pet_scripts()
{
    using namespace Pets::Warlock;
    RegisterCreatureAI(npc_pet_warlock_doomguard);
}
