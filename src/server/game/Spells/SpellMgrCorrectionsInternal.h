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

#ifndef TRINITY_SPELL_MGR_CORRECTIONS_INTERNAL_H
#define TRINITY_SPELL_MGR_CORRECTIONS_INTERNAL_H

#include "Common.h"
#include "SpellMgr.h"
#include "SpellInfo.h"
#include "Log.h"
#include <initializer_list>

inline void ApplySpellFix(std::initializer_list<uint32> spellIds, void(*fix)(SpellInfo*))
{
    for (uint32 spellId : spellIds)
    {
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
        if (!spellInfo)
        {
            TC_LOG_ERROR("server.loading", "Spell info correction specified for non-existing spell %u", spellId);
            continue;
        }

        fix(const_cast<SpellInfo*>(spellInfo));
    }
}

namespace SpellMgrCorrections
{
void ApplyPart01();
void ApplyPart02();
void ApplyPart03();
void ApplyPart04();
}

#endif
