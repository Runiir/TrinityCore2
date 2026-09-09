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

void AddSC_generic_spell_scripts()
{
    Spells::Generic::RegisterAbsorption1();
    Spells::Generic::RegisterGreetingsRacial2();
    Spells::Generic::RegisterAbsorption3();
    Spells::Generic::RegisterCloningDisguises4();
    Spells::Generic::RegisterGreetingsRacial5();
    Spells::Generic::RegisterCloningDisguises6();
    Spells::Generic::RegisterQuestsGuild7();
    Spells::Generic::RegisterPetsTransport8();
    Spells::Generic::RegisterQuestsGuild9();
    Spells::Generic::RegisterPetsTransport10();
    Spells::Generic::RegisterProcsProfessions11();
    Spells::Generic::RegisterVehiclesTournament12();
    Spells::Generic::RegisterBonusesUtilities13();
    Spells::Generic::RegisterVengeance();
    Spells::Generic::RegisterQuestsGuild15();
    Spells::Generic::RegisterProcsProfessions16();
}
