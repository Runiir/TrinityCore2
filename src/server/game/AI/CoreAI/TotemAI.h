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

#ifndef TRINITY_TOTEMAI_H
#define TRINITY_TOTEMAI_H

#include "CreatureAI.h"
#include "PassiveAI.h"
#include "SpellDefines.h"
#include "Timer.h"

class Creature;
class Totem;

class TC_GAME_API TotemAI : public NullCreatureAI
{
    public:

        explicit TotemAI(Creature* c);

        void AttackStart(Unit* victim) override;

        void UpdateAI(uint32 diff) override;
        static int32 Permissible(Creature const* creature);

        uint64 GetCastAttempts() const { return _castAttempts; }
        uint64 GetCastSuccesses() const { return _castSuccesses; }
        uint64 GetUpdateCalls() const { return _updateCalls; }
        SpellCastResult GetLastCastResult() const { return _lastCastResult; }
        bool WasLastTargetValidForTotem() const { return _lastTotemTargetValid; }
        bool WasLastTargetValidForOwner() const { return _lastOwnerTargetValid; }
        uint64 GetCastingSkips() const { return _castingSkips; }
        uint64 GetMissingSpellSkips() const { return _missingSpellSkips; }
        uint64 GetNoTargetSkips() const { return _noTargetSkips; }

    private:
        ObjectGuid _victimGUID;
        uint64 _updateCalls = 0;
        uint64 _castAttempts = 0;
        uint64 _castSuccesses = 0;
        SpellCastResult _lastCastResult = SPELL_FAILED_DONT_REPORT;
        bool _lastTotemTargetValid = false;
        bool _lastOwnerTargetValid = false;
        uint64 _castingSkips = 0;
        uint64 _missingSpellSkips = 0;
        uint64 _noTargetSkips = 0;
};
#endif
