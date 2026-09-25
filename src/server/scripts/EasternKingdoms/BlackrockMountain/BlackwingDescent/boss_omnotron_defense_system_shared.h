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

#ifndef DEF_BOSS_OMNOTRON_DEFENSE_SYSTEM_SHARED_H
#define DEF_BOSS_OMNOTRON_DEFENSE_SYSTEM_SHARED_H

// Shared identifiers of the Omnotron Defense System scripts. The controller and
// construct AIs live in boss_omnotron_defense_system.cpp; Lord Victor Nefarius,
// the Poison Bomb and the spell scripts live in boss_omnotron_defense_system_spells.cpp.
namespace BlackwingDescent::OmnotronDefenseSystem
{
enum Spells
{
    // Omnotron
    SPELL_COUNCIL_ENERGY_DRAIN                  = 78725,
    SPELL_CONTROLLER_RECHARGE                   = 78696,
    SPELL_RECHARGING_ELECTRON                   = 78697,
    SPELL_RECHARGING_MAGMATRON                  = 78698,
    SPELL_RECHARGING_ARCANOTRON                 = 78699,
    SPELL_RECHARGING_TOXITRON                   = 78700,

    // Omnotron Defense System
    SPELL_INACTIVE                              = 78726,
    SPELL_POWERED_DOWN                          = 82265,
    SPELL_SHARED_HEALTH                         = 79920,
    SPELL_SHUTTING_DOWN                         = 78746,
    SPELL_INVISIBILITY_AND_STEALTH_DETECTION    = 67236,

    // Electron
    SPELL_ELECTRICAL_DISCHARGE_TRIGGER          = 95499,
    SPELL_ELECTRICAL_DISCHARGE                  = 79879,
    SPELL_UNSTABLE_SHIELD                       = 79900,
    SPELL_STATIC_SHOCK                          = 79912,
    SPELL_LIGHTNING_CONDUCTOR_10N               = 79888,

    // Magmatron
    SPELL_INCINERATION_SECURITY_MEASURE         = 79023,
    SPELL_ACQUIRING_TARGET                      = 79499,
    SPELL_BARRIER                               = 79582,
    SPELL_BACKDRAFT                             = 79617,

    // Toxitron
    SPELL_CHEMICAL_BOMB                         = 80157,
    SPELL_POISON_PROTOCOL                       = 80053,
    SPELL_POISON_SOAKED_SHELL                   = 79835,

    // Arcanotron
    SPELL_POWER_GENERATOR                       = 79624,
    SPELL_POWER_CONVERSION                      = 79729,

    // Poison Bomb
    SPELL_FIXATE_DUMMY                          = 80094,
    SPELL_QUIETE_SUICIDE                        = 3617,
    SPELL_POISON_BOMB_DAMAGE                    = 80092,
    SPELL_POISON_BOMB_SUMMON_PUDDLE             = 80089,

    // Power Generator
    SPELL_OVERCHARGED_POWER_GENERATOR           = 91857,
    SPELL_GROW_STACKER                          = 91861,
    SPELL_ARCANE_BLOWBACK                       = 91880,
    SPELL_POWER_GENERATOR_NORMAL                = 79628,

    // Lord Victor Nefarius
    SPELL_SHADOW_INFUSION                       = 92048,
    SPELL_SHADOW_TELEPORT                       = 91823,
    SPELL_SHADOW_TELEPORT_BACK                  = 91854,
    SPELL_GRIP_OF_DEATH                         = 91849,
    SPELL_SHADOW_CONDUCTOR                      = 92053,
    SPELL_ENCASING_SHADOWS                      = 92023,
    SPELL_OVERCHARGE                            = 91881
};

#define SPELL_LIGHTNING_CONDUCTOR   RAID_MODE<uint32>(79888, 91431, 91432, 91433)
#define SPELL_SOAKED_IN_POISON      RAID_MODE<uint32>(80011, 91504, 91505, 91506)
#define SPELL_ARCANE_ANNIHILATION   RAID_MODE<uint32>(79710, 91540, 91541, 91542)
#define SPELL_ACTIVATED             RAID_MODE<uint32>(78740, 95016, 95017, 95018)

enum Texts
{
    // Omnotron
    SAY_ACTIVATE_ELECTRON               = 0,
    SAY_ACTIVATE_TOXITRON               = 1,
    SAY_ACTIVATE_MAGMATRON              = 2,
    SAY_ACTIVATE_ARCANOTRON             = 3,
    SAY_SHIELD_ELECTRON                 = 4,
    SAY_SHIELD_TOXITRON                 = 5,
    SAY_SHIELD_ARCANOTRON               = 6,
    SAY_SHIELD_MAGMATRON                = 7,
    SAY_ACQUIRING_TARGET                = 8,
    SAY_POWERING_DOWN                   = 9,

    // Omnotron Defense System
    SAY_ANNOUNCE_ABILITY_1              = 0,
    SAY_ANNOUNCE_ABILITY_2              = 1,

    // Lord Victor Nefarius
    SAY_INTRO_HEROIC                    = 0,
    SAY_MANIPULATE_LIGHTNING_CONDUCTOR  = 1,
    SAY_PULL_INTO_CHEMICAL_CLOUD        = 2,
    SAY_ROOT_PLAYER_IN_PLACE            = 3,
    SAY_OVERCHARGE_POWER_GENERATOR      = 4
};

enum Events
{
    // Omnotron
    EVENT_LINK_GOLEM_HEALTH = 1,
    EVENT_POWER_UP_FIRST_GOLEM,
    EVENT_TALK_ACTIVATED_GOLEM,

    // Omnotron Defense System

    // Electron
    EVENT_LIGHTNING_CONDUCTOR,
    EVENT_ELECTRICAL_DISCHARGE,
    EVENT_UNSTABLE_SHIELD,

    // Magmatron
    EVENT_INCINERATION_SECURITY_MEASURE,
    EVENT_ACQUIRING_TARGET,
    EVENT_BARRIER,

    // Toxitron
    EVENT_CHEMICAL_BOMB,
    EVENT_POISON_PROTOCOL,
    EVENT_POISON_SOAKED_SHELL,

    // Arcanotron
    EVENT_POWER_GENERATOR,
    EVENT_ARCANE_ANNIHILATION,
    EVENT_POWER_CONVERSION,

    // Lord Victor Nefarius
    EVENT_TALK_INTRO,
    EVENT_TELEPORT_INTO_CHEMICAL_CLOUD,
    EVENT_GRIP_OF_DEATH,
    EVENT_TALK_PULL_PLAYERS_INTO_CHEMICAL_CLOUD,
    EVENT_TELEPORT_BACK,
    EVENT_TALK_MANIPULATE_LIGHTNING_CONDUCTOR,
    EVENT_ENCASING_SHADOWS,
    EVENT_TALK_ROOT_PLAYER,
    EVENT_OVERCHARGE,
    EVENT_TALK_OVERCHARGE_POWER_GENERATOR,
    EVENT_CLEAR_ABILITY_COOLDOWN
};

enum Actions
{
    // Omnotron
    ACTION_GOLEM_ACTIVATED                  = 0,
    ACTION_START_ENCOUNTER                  = 1,
    ACTION_STOP_ENCOUNTER                   = 2,
    ACTION_FINISH_ENCOUNTER                 = 3,
    ACTION_SAY_ACQUIRING_TARGET             = 4,

    // Omnotron Defense System
    ACTION_ACTIVATE_GOLEM                   = 0,
    ACTION_DEACTIVATE_GOLEM                 = 1,

    // Lord Victor Nefarius
    ACTION_CAST_SHADOW_INFUSION             = 0,
    ACTION_CAST_ENCASING_SHADOWS            = 1
};

enum Data
{
    // Omnotron
    DATA_NEXT_GOLEM_IN_QUEUE                = 0,
    DATA_SAY_GOLEM_SHIELD                   = 0
};

enum MovePoints
{
    POINT_START_WAYPOINTS = 1
};

enum SummonGroups
{
    SUMMON_GROUP_GOLEMS = 0
};
}

void AddSC_boss_omnotron_defense_system_spells();

#endif
