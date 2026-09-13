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
 * Ordered alphabetically using scriptname.
 * Scriptnames of files in this file should be prefixed with "npc_pet_sha_".
 */

#include "ScriptMgr.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "CombatManager.h"
#include "ScriptedCreature.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellScript.h"
#include "TemporarySummon.h"
#include "Totem.h"
#include <algorithm>
#include <tuple>
#include <vector>

namespace Pets::Shaman
{
Unit* ShamanElementalOwner(Creature* elemental)
{
    if (!elemental)
        return nullptr;
    TempSummon* summon = elemental->ToTempSummon();
    Unit* owner = summon ? summon->GetSummoner() : elemental->GetCharmerOrOwner();
    return owner && owner->IsTotem() ? owner->ToTotem()->GetOwner() : owner;
}

bool ShamanAuthorityAllows(Unit* owner, Unit* target)
{
    if (!owner || !target)
        return false;
    uint64 const ownerGuid = owner->GetGUID().GetRawValue();
    if (BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid))
        return false;
    Creature const* creature = target->ToCreature();
    return !creature || !BotRaidAreaAuthority::IsProtectedEncounterTarget(ownerGuid,
        creature->GetEntry(), creature->GetSpawnId(), creature->GetGUID().GetRawValue());
}

void StopShamanProtectedVictim(Creature* elemental)
{
    Unit* owner = ShamanElementalOwner(elemental);
    if (owner && elemental->GetVictim() && !ShamanAuthorityAllows(owner, elemental->GetVictim()))
    {
        elemental->InterruptNonMeleeSpells(false);
        elemental->AttackStop();
    }
}

bool AcquireShamanOwnerVictim(Creature* elemental)
{
    Unit* owner = ShamanElementalOwner(elemental);
    if (!owner)
        return false;
    auto tryTarget = [&](Unit* victim)
    {
        if (!victim || !victim->IsAlive() || !owner->IsValidAttackTarget(victim)
            || !ShamanAuthorityAllows(owner, victim))
            return false;
        if (owner->GetTypeId() == TYPEID_PLAYER)
            elemental->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED);
        elemental->AI()->AttackStart(victim);
        return elemental->GetVictim() == victim;
    };
    Unit* victim = owner->GetVictim();
    if (victim && tryTarget(victim))
        return true;

    uint64 const ownerGuid = owner->GetGUID().GetRawValue();
    if (!BotRaidAreaAuthority::HasProtectedEncounterEntries(ownerGuid))
        return !victim && tryTarget(owner->getAttackerForHelper());

    // Protected first candidates must not hide established legal combat refs.
    // Explicit owner victim wins above; fallback prefers ordinary targets and
    // stable GUID order instead of unordered CombatManager iteration order.
    std::vector<Unit*> candidates;
    auto remember = [&](Unit* candidate)
    {
        if (candidate && candidate->IsAlive() && owner->IsValidAttackTarget(candidate)
            && ShamanAuthorityAllows(owner, candidate))
            candidates.push_back(candidate);
    };
    remember(owner->getAttackerForHelper());
    for (auto const& entry : owner->GetCombatManager().GetPvECombatRefs())
        if (!entry.second->IsSuppressedFor(owner))
            remember(entry.second->GetOther(owner));
    for (auto const& entry : owner->GetCombatManager().GetPvPCombatRefs())
        if (!entry.second->IsSuppressedFor(owner))
            remember(entry.second->GetOther(owner));
    auto rank = [&](Unit* candidate)
    {
        return std::make_tuple(BotRaidAreaAuthority::IsCurrentEncounterRestrictedEntry(ownerGuid, candidate->GetEntry()),
            candidate->GetGUID().GetRawValue());
    };
    std::sort(candidates.begin(), candidates.end(), [&](Unit* a, Unit* b) { return rank(a) < rank(b); });
    candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());
    for (Unit* candidate : candidates)
        if (tryTarget(candidate))
            return true;
    return false;
}

enum ShamanSpells
{
    SPELL_SHAMAN_ANGEREDEARTH   = 36213,
    SPELL_SHAMAN_FIREBLAST      = 57984,
    SPELL_SHAMAN_FIRENOVA       = 12470,
    SPELL_SHAMAN_FIRESHIELD     = 13376
};

enum ShamanEvents
{
    // Earth Elemental
    EVENT_SHAMAN_ANGEREDEARTH   = 1,
    // Fire Elemental
    EVENT_SHAMAN_FIRENOVA       = 1,
    EVENT_SHAMAN_FIRESHIELD     = 2,
    EVENT_SHAMAN_FIREBLAST      = 3
};

// All three configured spells are native effect-0 SCHOOL_DAMAGE, including
// Fire Shield (13376), which the AI recasts rather than applying a periodic aura.
class spell_sha_fire_elemental_spell_scaling : public SpellScript
{
    void CalculateDamage(Unit* /*victim*/, int32& /*damage*/, int32& flatMod, float& /*pctMod*/)
    {
        Unit* caster = GetCaster();
        SpellInfo const* spellInfo = GetSpellInfo();
        if (!caster || !caster->IsGuardian() || caster->GetEntry() != 15438
            || !spellInfo || (spellInfo->Id != SPELL_SHAMAN_FIREBLAST
                && spellInfo->Id != SPELL_SHAMAN_FIRENOVA
                && spellInfo->Id != SPELL_SHAMAN_FIRESHIELD)
            || spellInfo->Effects[EFFECT_0].Effect != SPELL_EFFECT_SCHOOL_DAMAGE)
            return;

        Guardian* guardian = static_cast<Guardian*>(caster);
        Unit* owner = guardian->GetStatOwner();
        if (!owner || owner->GetTypeId() != TYPEID_PLAYER)
            return;

        float coefficient = spellInfo->Effects[EFFECT_0].BonusMultiplier
            * spellInfo->GetSpellScalingMultiplier(caster->getLevel(), false);
        // Preserve the core coefficient spellmod path, including its percent
        // units and caster-derived mod owner; stat ownership is separate.
        if (Player* modOwner = caster->GetSpellModOwner())
        {
            coefficient *= 100.0f;
            modOwner->ApplySpellMod(spellInfo, SpellModOp::BonusCoefficient, coefficient);
            coefficient /= 100.0f;
        }
        // Guardian-local spell power is already present in native flatMod.
        flatMod += int32(guardian->GetOwnerSpellDamageBonus() * coefficient);
    }

    void Register() override
    {
        CalcDamage.Register(&spell_sha_fire_elemental_spell_scaling::CalculateDamage);
    }
};

class npc_pet_shaman_earth_elemental : public CreatureScript
{
    public:
        npc_pet_shaman_earth_elemental() : CreatureScript("npc_pet_shaman_earth_elemental") { }

        struct npc_pet_shaman_earth_elementalAI : public ScriptedAI
        {
            npc_pet_shaman_earth_elementalAI(Creature* creature) : ScriptedAI(creature) { }


            void Reset() override
            {
                _events.Reset();
                _events.ScheduleEvent(EVENT_SHAMAN_ANGEREDEARTH, 0);
                me->ApplySpellImmune(0, IMMUNITY_SCHOOL, SPELL_SCHOOL_MASK_NATURE, true);
            }

            void AttackStart(Unit* target) override
            {
                Unit* owner = ShamanElementalOwner(me);
                if (!owner || ShamanAuthorityAllows(owner, target))
                    ScriptedAI::AttackStart(target);
            }

            void UpdateAI(uint32 diff) override
            {
                StopShamanProtectedVictim(me);
                if (!UpdateVictim() && (!AcquireShamanOwnerVictim(me) || !UpdateVictim()))
                    return;

                _events.Update(diff);

                if (_events.ExecuteEvent() == EVENT_SHAMAN_ANGEREDEARTH)
                {
                    DoCastVictim(SPELL_SHAMAN_ANGEREDEARTH);
                    _events.ScheduleEvent(EVENT_SHAMAN_ANGEREDEARTH, urand(5000, 20000));
                }

                DoMeleeAttackIfReady();
            }

        private:
            EventMap _events;
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_pet_shaman_earth_elementalAI(creature);
        }
};

class npc_pet_shaman_fire_elemental : public CreatureScript
{
    public:
        npc_pet_shaman_fire_elemental() : CreatureScript("npc_pet_shaman_fire_elemental") { }

        struct npc_pet_shaman_fire_elementalAI : public ScriptedAI
        {
            npc_pet_shaman_fire_elementalAI(Creature* creature) : ScriptedAI(creature) { }

            void Reset() override
            {
                _events.Reset();
                _events.ScheduleEvent(EVENT_SHAMAN_FIRENOVA, urand(5000, 20000));
                _events.ScheduleEvent(EVENT_SHAMAN_FIREBLAST, urand(5000, 20000));
                _events.ScheduleEvent(EVENT_SHAMAN_FIRESHIELD, 0);
                me->ApplySpellImmune(0, IMMUNITY_SCHOOL, SPELL_SCHOOL_MASK_FIRE, true);
            }

            void AttackStart(Unit* target) override
            {
                Unit* owner = ShamanElementalOwner(me);
                if (!owner || ShamanAuthorityAllows(owner, target))
                    ScriptedAI::AttackStart(target);
            }

            void UpdateAI(uint32 diff) override
            {
                StopShamanProtectedVictim(me);
                if (!UpdateVictim() && (!AcquireShamanOwnerVictim(me) || !UpdateVictim()))
                    return;

                if (me->HasUnitState(UNIT_STATE_CASTING))
                    return;

                _events.Update(diff);

                while (uint32 eventId = _events.ExecuteEvent())
                {
                    switch (eventId)
                    {
                        case EVENT_SHAMAN_FIRENOVA:
                            DoCastVictim(SPELL_SHAMAN_FIRENOVA);
                            _events.ScheduleEvent(EVENT_SHAMAN_FIRENOVA, urand(5000, 20000));
                            break;
                        case EVENT_SHAMAN_FIRESHIELD:
                            DoCastVictim(SPELL_SHAMAN_FIRESHIELD);
                            _events.ScheduleEvent(EVENT_SHAMAN_FIRESHIELD, 2000);
                            break;
                        case EVENT_SHAMAN_FIREBLAST:
                            DoCastVictim(SPELL_SHAMAN_FIREBLAST);
                            _events.ScheduleEvent(EVENT_SHAMAN_FIREBLAST, urand(5000, 20000));
                            break;
                        default:
                            break;
                    }
                }

                DoMeleeAttackIfReady();
            }

        private:
            EventMap _events;
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_pet_shaman_fire_elementalAI(creature);
        }
};
}

void AddSC_shaman_pet_scripts()
{
    using namespace Pets::Shaman;
    RegisterSpellScript(spell_sha_fire_elemental_spell_scaling);
    new npc_pet_shaman_earth_elemental();
    new npc_pet_shaman_fire_elemental();
}
