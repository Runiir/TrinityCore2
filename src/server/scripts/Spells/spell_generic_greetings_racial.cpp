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
enum DalaranShopKeeper
{
    SPELL_DALARAN_SHOP_KEEPER_AOE           = 60912,
    SPELL_DALARAN_SHOP_KEEPER_PING          = 60909,
    SPELL_DALARAN_SHOP_KEEPER_DUMMY_AURA    = 61354
};

// 60913 - [DND] Dalaran - Shop Keeper Greeting
class spell_gen_dalaran_shop_keeper_greeting_periodic : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_DALARAN_SHOP_KEEPER_AOE, SPELL_DALARAN_SHOP_KEEPER_DUMMY_AURA });
    }

    void HandlePeriodic(AuraEffect const* /*aurEff*/)
    {
        if (!GetTarget()->HasAura(SPELL_DALARAN_SHOP_KEEPER_DUMMY_AURA))
            GetTarget()->CastSpell(nullptr, SPELL_DALARAN_SHOP_KEEPER_AOE);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_gen_dalaran_shop_keeper_greeting_periodic::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

// 60912 - [DND] Dalaran - Shop Keeper Greeting
class spell_gen_dalaran_shop_keeper_greeting_aoe : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_DALARAN_SHOP_KEEPER_PING });
    }

    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Unit* caster = GetCaster())
            GetTarget()->CastSpell(nullptr, SPELL_DALARAN_SHOP_KEEPER_PING, CastSpellExtraArgs(TRIGGERED_FULL_MASK).SetCustomArg(caster->GetGUID()));
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_gen_dalaran_shop_keeper_greeting_aoe::AfterApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

// 60909 - [DND] Dalaran - Shop Keeper Greeting
class spell_gen_dalaran_shop_keeper_greeting_ping : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_DALARAN_SHOP_KEEPER_DUMMY_AURA });
    }

    // We are going to skip an endless number of condition entries and just provide the target guid right away.
    void SelectVendor(WorldObject*& target)
    {
        if (GetSpell()->m_customArg.has_value())
        {
            ObjectGuid targetGuid = std::any_cast<ObjectGuid>(GetSpell()->m_customArg);
            target = ObjectAccessor::GetCreature(*GetCaster(), targetGuid);
        }
    }

    void HandleDummyEffect(SpellEffIndex /*effIndex*/)
    {
        GetHitUnit()->CastSpell(nullptr, SPELL_DALARAN_SHOP_KEEPER_DUMMY_AURA);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_dalaran_shop_keeper_greeting_ping::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
        OnObjectTargetSelect.Register(&spell_gen_dalaran_shop_keeper_greeting_ping::SelectVendor, EFFECT_0, TARGET_UNIT_NEARBY_ENTRY);
    }
};


void RegisterGreetingsRacial5()
{
    RegisterSpellScript(spell_gen_dalaran_shop_keeper_greeting_periodic);
    RegisterSpellScript(spell_gen_dalaran_shop_keeper_greeting_aoe);
    RegisterSpellScript(spell_gen_dalaran_shop_keeper_greeting_ping);
}
}
