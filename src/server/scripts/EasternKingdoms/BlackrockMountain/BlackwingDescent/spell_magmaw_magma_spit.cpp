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

#include "ScriptMgr.h"
#include "SpellScript.h"

namespace BlackwingDescent::Magmaw
{
enum Spells
{
    SPELL_MAGMA_SPIT_MISSILE = 78359
};

class spell_magmaw_magma_spit_missile : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        Unit* explicitTarget = GetExplTargetUnit();
        if (!explicitTarget)
        {
            targets.clear();
            return;
        }

        targets.remove_if([explicitTarget](WorldObject* target)
        {
            return target != explicitTarget;
        });
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_magmaw_magma_spit_missile::FilterTargets,
            EFFECT_0, TARGET_UNIT_DEST_AREA_ENEMY);
    }
};
}

void AddSC_boss_magmaw_spells()
{
    using namespace BlackwingDescent::Magmaw;
    RegisterSpellScript(spell_magmaw_magma_spit_missile);
}
