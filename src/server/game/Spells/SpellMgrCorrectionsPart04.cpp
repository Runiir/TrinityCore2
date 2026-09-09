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

#include "SpellMgr.h"
#include "BattlefieldMgr.h"
#include "BattlegroundMgr.h"
#include "Chat.h"
#include "Containers.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "Log.h"
#include "Map.h"
#include "MotionMaster.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "SharedDefines.h"
#include "Spell.h"
#include "SpellAuraDefines.h"
#include "SpellInfo.h"
#include <G3D/g3dmath.h>

#include "SpellMgrCorrectionsInternal.h"

void SpellMgrCorrections::ApplyPart04()
{

    // Stormling
    ApplySpellFix({ 88272 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(1); // 10 seconds
    });

    // Squall Line
    ApplySpellFix({
        88781,
        91104,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(245); // 50 seconds
    });

    // Lightning Clouds
    ApplySpellFix({
        89583,
        89592,
        89628
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Lightning Clouds
    ApplySpellFix({
        89588,
        93297,
        93298,
        93299
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_NO_INITIAL_THREAT;
    });

    // Lightning Clouds
    ApplySpellFix({
        89565,
        89577
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(570); // 32 seconds
    });

    // Lightning Rod
    ApplySpellFix({ 89668 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Lightning
    ApplySpellFix({
        89644,
        101465,
        101466,
        101467
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetB = SpellImplicitTargetInfo(0);
    });

    // Lightning
    ApplySpellFix({
        89644,
        101466,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Lightning
    ApplySpellFix({
        101465,
        101467,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 3;
    });

    // Static Shock
    ApplySpellFix({ 87873 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_IGNORE_LINE_OF_SIGHT;
    });

    // ENDOF THRONE OF THE FOUR WINDS SPELLS

    // DRAGON SOUL SPELLS

    ApplySpellFix({
        106028, // Alexstrasza's Presence
        109571,
        109572,
        109573,
        106457, // Ysera's Presence
        109640,
        109641,
        109642,
        106027, // Nozdormu's Presence
        109622,
        109623,
        109624,
        106029, // Kalecgos' Presence
        109606,
        109607,
        109608,
        106040, // Spellweaving
        106464  // Enter the Dream
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_NO_INITIAL_THREAT;
    });

    // Root
    ApplySpellFix({ 105451 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_MOD_ROOT;
    });

    // ENDOF DRAGON SOUL SPELLS

    // Disenchant
    ApplySpellFix({ 13262 }, [](SpellInfo* spellInfo)
    {
        spellInfo->BaseLevel = 0;
        spellInfo->SpellLevel = 0;
    });

    // Glyph of Mirror Image
    ApplySpellFix({ 63093 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].Effect = SPELL_EFFECT_APPLY_AURA;
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_DUMMY;
    });

    // Grace
    ApplySpellFix({
        47930,
        77613
    },[](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(6);  // 100yd
    });

    // Hyjal Intro Flight
    ApplySpellFix({ 73518 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(7);  // 10yd
    });

    // Strengh of Soul
    ApplySpellFix({ 89490 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(5); // 40yd
    });

    // Explosive Trap
    ApplySpellFix({ 13812 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(13); // Anywhere
    });

    // Ancient Crusader
    ApplySpellFix({ 86701 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(9); // 30 seconds
    });

    // Blood Craze
    ApplySpellFix({
        16488,
        16490,
        16491
    },[](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_PERIODIC_HEAL;
    });

    // Desecration
    ApplySpellFix({
        55741,
        68766
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(7);  // 10yd
    });

    // Ebon Plague
    ApplySpellFix({ 65142 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].Effect = SPELL_EFFECT_APPLY_AURA;
        spellInfo->Effects[EFFECT_1].ApplyAuraName = SPELL_AURA_MOD_DAMAGE_PERCENT_TAKEN;
        spellInfo->Effects[EFFECT_1].MiscValue = 126;
        spellInfo->Effects[EFFECT_1].TriggerSpell = 0;
    });

    // Glyph of Exorcism
    ApplySpellFix({ 86701 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_CASTER);
    });

    // Soulburn: Seed of Corruption
    ApplySpellFix({ 86664 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].Effect = SPELL_EFFECT_APPLY_AURA;
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_DUMMY;
    });

    // Gout of Flame
    ApplySpellFix({ 80550 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].BasePoints = 7;
    });

    // Whack!
    ApplySpellFix({ 102022 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesCu |= SPELL_ATTR0_CU_CONE_LINE;
    });

    // Atonement
    ApplySpellFix({
        81751,
        94472
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_IGNORE_LINE_OF_SIGHT;
    });

    //
    // BLACKWING DESCENT SPELLS
    //

    // Eject Passenger
    ApplySpellFix({ 78643 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_IGNORE_LINE_OF_SIGHT;
    });

    // Flamethrower
    ApplySpellFix({
        79505,
        91531,
        91532,
        91533
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_TARGET_ENEMY);
    });

    // Power Generator
    ApplySpellFix({ 79624 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_CASTER);
        spellInfo->Effects[EFFECT_0].TargetB = SpellImplicitTargetInfo(0);
    });

    // Arcane Annihiliation
    ApplySpellFix({
        91540,
        91542
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 3;
    });

    // Overcharged Power Generator
    ApplySpellFix({ 91858 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].TargetARadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_5_YARDS);
    });

    // Sonar Pulse
    ApplySpellFix({
        77672,
        92412,
        92411,
        92413
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 4;
    });

    // Searing Flame
    ApplySpellFix({ 77840 }, [](SpellInfo* spellInfo)
    {

        spellInfo->Effects[EFFECT_1].Effect = SPELL_EFFECT_APPLY_AURA;
        spellInfo->Effects[EFFECT_1].ApplyAuraName = SPELL_AURA_PERIODIC_TRIGGER_SPELL;
        spellInfo->Effects[EFFECT_1].AuraPeriod = 2000;
    });

    // Sonar Pulse (10 player)
    ApplySpellFix({
        92526,
        92532,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 5;
    });

    // Sonar Pulse (25 player)
    ApplySpellFix({
        92531,
        92533
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 12;
    });

    // Roaring Flame Breath
    ApplySpellFix({ 78207 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Sonic Flames
    ApplySpellFix({ 77782 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_TARGET_ANY);
    });

    // Pestered!
    ApplySpellFix({ 92685 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesCu |= SPELL_ATTR0_CU_NEGATIVE_EFF1;
    });

    // Building Speed Effect
    ApplySpellFix({
        78218,
        92463,
        92464,
        92465
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->StackAmount = 10;
    });

    // Break
    ApplySpellFix({ 82881 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesCu |= SPELL_ATTR0_CU_NEGATIVE_EFF0;
    });

    // Biting Chill
    ApplySpellFix({ 77760 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_TARGET_ENEMY);
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(0);
    });

    // Growth Catalyst
    ApplySpellFix({
        77987,
        101440,
        101441,
        101442
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx3 |= SPELL_ATTR3_DOT_STACKING_RULE;
    });

    // Release Aberrations
    ApplySpellFix({ 77569 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx8 |= SPELL_ATTR7_NO_ATTACK_MISS;
    });

    // Release All Minions
    ApplySpellFix({ 77991 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx8 |= SPELL_ATTR7_NO_ATTACK_MISS;
    });

    // Debilitating Slime
    ApplySpellFix({ 77615 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_NO_INITIAL_THREAT;
    });

    // Shadowflame Breath
    ApplySpellFix({
        77826,
        94124,
        94125,
        94126,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].AuraPeriod = 1500;
    });

    // Electrical Charge
    ApplySpellFix({ 78949 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].AuraPeriod = 3000;
    });

    // Hail of Bones
    ApplySpellFix({
        78684,
        94104,
        94105,
        94106,
    }, [](SpellInfo* spellInfo)
    {
       spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(21); // Infinite
    });

    // Shadowflame Barrage (10 players)
    ApplySpellFix({
        78621,
        94122,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 4;
    });

    // Shadowflame Barrage (25 players)
    ApplySpellFix({
        94121,
        94123,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 8;
    });

    // Brushfire Start
    ApplySpellFix({ 79813 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Explosive Cinders
    ApplySpellFix({ 79339 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Constricting Chains
    ApplySpellFix({ 79589 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 2;
    });

    // Constricting Chains
    ApplySpellFix({ 91911 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 4;
    });

    // Laser Strike
    ApplySpellFix({
        81067,
        91884
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_NO_INITIAL_THREAT;
    });

    // Mangle (Hotfix: 2011-03-16: Magmaw overall damage and health was a little too high on all difficulties and has been reduced slightly)
    // For some reason this didn't seem to have found its way into the dbc as sniffs confirm 100% melee damage instead of 150%.
    ApplySpellFix({
        89773,
        91912,
        94616,
        94617
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_2].BasePoints = 100;
    });

    // Shadow Conductor
    ApplySpellFix({ 92053 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(29); // 12 seconds
    });

    // ENDOF BLACKWING DESCENT SPELLS

    // Living Bomb
    ApplySpellFix({ 44457 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx5 |= SPELL_ATTR5_LIMIT_N;
        spellInfo->MaxAffectedTargets = 3;
    });

    // Overhead Smash
    ApplySpellFix({
        79580,
        91906,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(6); // 100 yards
    });

    // Living Bomb
    ApplySpellFix({ 44461 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 3;
    });

    // Lifebloom
    ApplySpellFix({ 33763 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx5 |= SPELL_ATTR5_LIMIT_N;
    });

    // Tree of Life (Passive)
    ApplySpellFix({ 81098 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].ApplyAuraName = SPELL_AURA_OVERRIDE_ACTIONBAR_SPELLS;
    });

    // Light of Dawn
    ApplySpellFix({ 85222 }, [](SpellInfo* spellInfo)
    {
       spellInfo->DmgClass = SPELL_DAMAGE_CLASS_MAGIC;
    });

    // Improved Blood Presence
    ApplySpellFix({
        50365,
        50371,
    }, [](SpellInfo* spellInfo)
    {
       spellInfo->SpellFamilyName = SPELLFAMILY_DEATHKNIGHT;
    });

    // Enhanced Elements
    ApplySpellFix({ 77223 }, [](SpellInfo* spellInfo)
    {
        spellInfo->SpellFamilyName = SPELLFAMILY_SHAMAN;
    });

    // Fulmination
    ApplySpellFix({ 88767 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx3 |= SPELL_ATTR3_IGNORE_CASTER_MODIFIERS;
    });

    // Blood in the Water (Rank 1)
    ApplySpellFix({ 80318 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_DUMMY;
    });

    // Tamed Pet Passive 07 (DND)
    ApplySpellFix({ 20784 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_PROC_TRIGGER_SPELL_WITH_VALUE;
    });

    // Blade Twisting
    ApplySpellFix({
        31125,
        51585,
    }, [](SpellInfo* spellInfo)
    {
       spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(2); // 5 yards (combat range)
    });

    // Gift of the Earthmother (Rank 2)
    ApplySpellFix({ 51180 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].Effect = SPELL_EFFECT_APPLY_AURA;
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_DUMMY;

        spellInfo->Effects[EFFECT_1].Effect = SPELL_EFFECT_APPLY_AURA;
        spellInfo->Effects[EFFECT_1].ApplyAuraName = SPELL_AURA_DUMMY;
    });

    // Divine Purpose
    ApplySpellFix({ 90174 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].SpellClassMask[1] = 0;
    });

    // Zero Power
    ApplySpellFix({ 87239 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].MiscValue = 3;
    });

    // Sanguinary Vein
    ApplySpellFix({
        79146,
        79147,
    },[](SpellInfo* spellInfo)
    {
            spellInfo->SpellFamilyName = SPELLFAMILY_ROGUE;
    });

    // Serpent Spread
    ApplySpellFix({
        87934,
        87935
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_DUMMY;
        spellInfo->Effects[EFFECT_0].Effect = SPELL_EFFECT_APPLY_AURA;
    });

    // Furious Attacks
    ApplySpellFix({ 56112 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(2); // Combat Range
    });

    // Expose Armor
    ApplySpellFix({ 8647 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx |= SPELL_ATTR1_FINISHING_MOVE_DURATION;
        spellInfo->AttributesEx &= ~SPELL_ATTR1_FINISHING_MOVE_DAMAGE;
    });

    // Rupture
    ApplySpellFix({ 1943 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx |= SPELL_ATTR1_FINISHING_MOVE_DURATION;
    });

    // Combustion
    // Patch 4.3.0 (2011-11-29): Combustion's periodic damage can now critically hit.
    ApplySpellFix({ 83853 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx8 |= SPELL_ATTR8_PERIODIC_CAN_CRIT;
    });

    // Rip
    ApplySpellFix({ 1079 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx8 |= SPELL_ATTR8_PERIODIC_CAN_CRIT;
    });

    // Body Slam
    ApplySpellFix({ 97252 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Attributes |= SPELL_ATTR0_NO_IMMUNITIES;
    });

    // Cauldron of Battle
    ApplySpellFix({ 92612 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(12); // Interact Range
    });

    // [DND] Dalaran - Shop Keeper Greeting
    ApplySpellFix({ 60909 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_IGNORE_LINE_OF_SIGHT;
    });

    // Fire (82926) uses aura 333 to select this instant Aimed Shot! variant;
    // it does not modify cast time. Scaling 578 otherwise shadows its zero
    // CastTimeEntry with 2400 ms. Keep normal Aimed Shot and all effect data.
    ApplySpellFix({ 82928 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Scaling.CastTimeMin = 0;
        spellInfo->Scaling.CastTimeMax = 0;
        spellInfo->Scaling.CastTimeMaxLevel = 0;
    });

}
