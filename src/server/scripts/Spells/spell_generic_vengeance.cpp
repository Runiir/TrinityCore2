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

#include <algorithm>

namespace Spells::Generic
{
enum Vengeance
{
    SPELL_VENGEANCE_TRIGGERED = 76691
};

uint32 InitialVengeanceAttackPower(uint32 damage, uint32 cap)
{
    return std::min<uint64>(uint64(cap), uint64(damage) / 3);
}

struct VengeanceUpdate
{
    uint32 AttackPower;
    uint32 RecentMaxAttackPower;
};

VengeanceUpdate UpdateVengeanceAttackPower(uint32 attackPower, uint32 recentMaxAttackPower,
    uint64 eligibleDamage, uint64 recentDamage, uint32 cap)
{
    uint64 nextAttackPower = attackPower;
    if (recentDamage)
    {
        nextAttackPower = (nextAttackPower * 95 + eligibleDamage * 5) / 100;
        nextAttackPower = std::max<uint64>(nextAttackPower, recentDamage / 3);
    }
    else if (nextAttackPower * 10 > recentMaxAttackPower)
        nextAttackPower = (nextAttackPower * 10 - recentMaxAttackPower) / 10;
    else
        nextAttackPower = 0;

    uint32 cappedAttackPower = uint32(std::min<uint64>(nextAttackPower, cap));
    return { cappedAttackPower, std::max(recentMaxAttackPower, cappedAttackPower) };
}

class VengeanceState
{
public:
    void Initialize(uint32 attackPower, uint32 timestamp)
    {
        _attackPower = attackPower;
        _recentMaxAttackPower = attackPower;
        _lastDamageTimestamp = timestamp;
        _hasDamageTimestamp = true;
        _eligibleDamage = 0;
    }

    void RecordDamage(uint32 damage, uint32 timestamp)
    {
        if (!damage)
            return;

        _eligibleDamage += damage;
        _lastDamageTimestamp = timestamp;
        _hasDamageTimestamp = true;
    }

    uint32 Update(uint32 timestamp, uint32 cap)
    {
        bool hasRecentDamage = _hasDamageTimestamp
            && (timestamp - _lastDamageTimestamp) < 2 * IN_MILLISECONDS;
        VengeanceUpdate update = UpdateVengeanceAttackPower(
            _attackPower, _recentMaxAttackPower, _eligibleDamage,
            hasRecentDamage ? _eligibleDamage : 0, cap);
        _attackPower = update.AttackPower;
        _recentMaxAttackPower = update.RecentMaxAttackPower;
        _eligibleDamage = 0;
        return _attackPower;
    }

private:
    uint64 _eligibleDamage = 0;
    uint32 _attackPower = 0;
    uint32 _recentMaxAttackPower = 0;
    uint32 _lastDamageTimestamp = 0;
    bool _hasDamageTimestamp = false;
};

// 93098 - 93099 - 84839 - 84840 - Vengeance
class spell_gen_vengeance : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_VENGEANCE_TRIGGERED });
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        return eventInfo.GetDamageInfo() && eventInfo.GetDamageInfo()->GetAttacker()
            && eventInfo.GetDamageInfo()->GetAttacker()->GetTypeId() != TYPEID_PLAYER;
    }

    void HandleEffectProc(AuraEffect const* /*aurEff*/, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();
        Unit* caster = GetTarget();

        if (!caster->GetAura(SPELL_VENGEANCE_TRIGGERED, caster->GetGUID()))
        {
            uint32 healthCap = CalculatePct(caster->GetCreateHealth(), 10) + caster->GetStat(STAT_STAMINA);
            int32 bp = InitialVengeanceAttackPower(eventInfo.GetDamageInfo()->GetDamage(), healthCap);
            caster->CastSpell(caster, SPELL_VENGEANCE_TRIGGERED, CastSpellExtraArgs(true).AddSpellBP0(bp).AddSpellMod(SPELLVALUE_BASE_POINT1, bp).AddSpellMod(SPELLVALUE_BASE_POINT2, bp));
        }
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_gen_vengeance::CheckProc);
        OnEffectProc.Register(&spell_gen_vengeance::HandleEffectProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// 76691 - Vengeance
class spell_gen_vengeance_triggered : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_VENGEANCE_TRIGGERED });
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        return eventInfo.GetDamageInfo() && eventInfo.GetDamageInfo()->GetAttacker()
            && eventInfo.GetDamageInfo()->GetAttacker()->GetTypeId() != TYPEID_PLAYER;
    }

    void HandleEffectProc(AuraEffect const* /*aurEff*/, ProcEventInfo& eventInfo)
    {
        _vengeance.RecordDamage(eventInfo.GetDamageInfo()->GetDamage(), GameTime::GetGameTimeMS());
    }

    void HandleEffectApply(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
    {
        _vengeance.Initialize(aurEff->GetAmount(), GameTime::GetGameTimeMS());
    }

    void HandleEffectPeriodic(AuraEffect const* /*aurEff*/)
    {
        Unit* target = GetTarget();
        uint32 healthCap = CalculatePct(target->GetCreateHealth(), 10) + target->GetStat(STAT_STAMINA);
        int32 attackPower = _vengeance.Update(GameTime::GetGameTimeMS(), healthCap);
        if (attackPower)
            target->CastSpell(target, SPELL_VENGEANCE_TRIGGERED, CastSpellExtraArgs(true).AddSpellBP0(attackPower).AddSpellMod(SPELLVALUE_BASE_POINT1, attackPower).AddSpellMod(SPELLVALUE_BASE_POINT2, attackPower));
        else
            Remove();
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_gen_vengeance_triggered::CheckProc);
        OnEffectProc.Register(&spell_gen_vengeance_triggered::HandleEffectProc, EFFECT_0, SPELL_AURA_MOD_ATTACK_POWER);
        AfterEffectApply.Register(&spell_gen_vengeance_triggered::HandleEffectApply, EFFECT_0, SPELL_AURA_MOD_ATTACK_POWER, AURA_EFFECT_HANDLE_REAL);
        OnEffectPeriodic.Register(&spell_gen_vengeance_triggered::HandleEffectPeriodic, EFFECT_2, SPELL_AURA_PERIODIC_DUMMY);
    }
private:
    VengeanceState _vengeance;
};


void RegisterVengeance()
{
    RegisterSpellScript(spell_gen_vengeance);
    RegisterSpellScript(spell_gen_vengeance_triggered);
}
}
