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

void SpellMgrCorrections::ApplyPart03()
{

    // Helix Gearbreaker
    // Charge
    ApplySpellFix({ 88295 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetARadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_100_YARDS);
    });

    // "Captain" Cookie
    // Rotten Aura
    ApplySpellFix({
        89735,
        92065,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesCu |= SPELL_ATTR0_CU_NO_INITIAL_THREAT;
    });

    // Vanessa VanCleef
    // Spark
    ApplySpellFix({ 95520 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetARadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_1_YARD);
    });

    // Summon Defias
    ApplySpellFix({
        92616,
        92617,
        92618
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_DEST_DEST);
        spellInfo->AttributesEx2 |= SPELL_ATTR2_IGNORE_LINE_OF_SIGHT;
    });

    // Fiery Blaze
    ApplySpellFix({ 93485 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesCu |= SPELL_ATTR0_CU_NO_INITIAL_THREAT;
    });

    // END OF DEADMINES SPELLS

    //
    // THRONE OF THE TIDES SPELLS
    //

    // Shock Defense
    ApplySpellFix({ 86618 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_DEST_TARGET_RANDOM);
    });

    // Commander Ulthok
    // Dark Fissure
    ApplySpellFix({ 96311 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(21); // Infinite
    });

    // Ozumat
    // Purify
    ApplySpellFix({ 76953 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 5;
        spellInfo->Effects[EFFECT_0].TargetARadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_100_YARDS);
    });

    // Summon Murloc Add Trigger
    ApplySpellFix({ 83360 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Summon Caster Add Trigger
    ApplySpellFix({ 83441 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Summon Lt Add Trigger
    ApplySpellFix({ 83437 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Summon Kite Add Trigger
    ApplySpellFix({ 83648 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Blight of Ozumat
    ApplySpellFix({ 83518 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Grab Neptulon
    ApplySpellFix({ 94171 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(6);  // 100yd
    });

    // Waterspout
    ApplySpellFix({ 90461 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Speed = 6.0f;
    });

    // END OF THRONE OF THE TIDES SPELLS

    //
    // GRIM BATOL SPELLS
    //
    // General Umbriss
    // Ground Siege
    ApplySpellFix({ 74634, 90249 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx3 &= ~SPELL_ATTR3_ONLY_ON_PLAYER;
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(6);  // 100yd
    });

    // Drahga Shadowburner
    // Ride Vehicle
    ApplySpellFix({ 43671 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_IGNORE_LINE_OF_SIGHT;
    });

    // Devouring Flames
    ApplySpellFix({ 90945 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Burning Shadowbolt
    ApplySpellFix({
        75245,
        90915
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Erudax
    // Twilight Blast
    ApplySpellFix({ 76194, 91042 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
        spellInfo->AttributesEx2 |= SPELL_ATTR2_NO_INITIAL_THREAT;
    });

    // Gronn Knockback Cosmetic
    ApplySpellFix({ 76138 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // ENDOF GRIM_BATOL SPELLS

    //
    // THE LOST CITY OF THE TOL'VIR SPELLS
    //
    // General Husam

    // Hurl
    ApplySpellFix({ 83235 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].Effect = SPELL_EFFECT_APPLY_AURA;
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_TARGET_ANY);
    });

    // High Prophet Barim
    // Blaze of the Heavens
    ApplySpellFix({ 91196 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetARadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_3_YARDS);
    });

    // Soul Fragment
    ApplySpellFix({ 82224 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx5 |= SPELL_ATTR5_ALLOW_ACTIONS_DURING_CHANNEL;
    });

    // Generic Spells
    // Slipstream
    ApplySpellFix({ 91872 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // ENDOF THE LOST CITY OF THE TOL'VIR SPELLS

    //
    // THE HALLS OF ORIGINATION SPELLS
    //
    ApplySpellFix({
        76606, // Disable Beacon Beams L
        76608  // Disable Beacon Beams R
    }, [](SpellInfo* spellInfo)
    {
        // Little hack, Increase the radius so it can hit the Cave In Stalkers in the platform.
        spellInfo->Effects[EFFECT_0].TargetBRadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_45_YARDS);
    });

    // Destruction Protocoll
    ApplySpellFix({ 77437 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_NO_INITIAL_THREAT;
    });

    // Spore Cloud
    ApplySpellFix({ 75701 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx &= ~SPELL_ATTR1_IS_CHANNELLED;
    });

    ApplySpellFix({
        73847, // Summon Sun-Touched Sprite
        73848  // Summon Sun-Touched Spriteling
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(7); // 10yd
    });

    // END OF HALLS OF ORIGINATION SPELLS

    //
    // SHADOWFANG KEEP SPELLS
    //

    // Toxic Coagulant
    ApplySpellFix({ 93617 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AuraInterruptFlags = SpellAuraInterruptFlags::Moving;
    });

    // END OF SHADOWFANG KEEP SPELLS

    // Threatening Gaze
    ApplySpellFix({ 24314 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AuraInterruptFlags |= SpellAuraInterruptFlags::Action | SpellAuraInterruptFlags::Moving | SpellAuraInterruptFlags::Anim;
    });

    //
    // BARADIN HOLD SPELLS
    //
    // Gaze of Occu'thar
    ApplySpellFix({ 96942, 101009 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx &= ~SPELL_ATTR1_IS_CHANNELLED;
    });

    // ENDOF BARADIN HOLD SPELLS

    //
    // BLACKROCK CAVERNS SPELLS
    //
    // Evolution
    ApplySpellFix({ 75610 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Bound Flames
    ApplySpellFix({ 93499 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 3;
    });

    // Furious Swipe
    ApplySpellFix({ 80340 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(7); // 10yd
    });

    // Transformation
    ApplySpellFix({ 76196 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Twilight Portal
    ApplySpellFix({
        95210,
        95012
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].AuraPeriod = 1250;
    });

    // ENDOF BLACKROCK CAVERNS SPELLS

    //
    // ISLE OF CONQUEST SPELLS
    //
    // Teleport
    ApplySpellFix({ 66551 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(13); // 50000yd
    });
    // ENDOF ISLE OF CONQUEST SPELLS

    // Deadly Poison - Black Temple
    ApplySpellFix({ 66551 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx6 |= SPELL_ATTR6_IGNORE_PHASE_SHIFT;
    });

    // Envenom - Black Temple
    ApplySpellFix({ 41487 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx6 |= SPELL_ATTR6_IGNORE_PHASE_SHIFT;
    });

    //
    // FIRELANDS SPELLS
    //
    // Torment
    ApplySpellFix({ 99256, 100230, 100231, 100232 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Attributes |= SPELL_ATTR0_AURA_IS_DEBUFF;
    });

    // Summon Fragment of Rhyolith
    ApplySpellFix({ 98136 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(21); // Infinite
    });

    // Summon Spark of Rhyolith
    ApplySpellFix({ 98552 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(21); // Infinite
    });

    // Summon Armor Fragment
    ApplySpellFix({ 98557 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(21); // Infinite
    });

    // World in Flames
    // There is no channel update packet in sniffs so we can assume that this is a leftover from a redesign
    ApplySpellFix({
        100171,
        100190
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx &= ~SPELL_ATTR1_IS_CHANNELLED;
    });

    // Fixate
    ApplySpellFix({ 99849 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx5 |= SPELL_ATTR5_ALLOW_ACTIONS_DURING_CHANNEL;
    });

    // Lava Bolt (25 player)
    ApplySpellFix({
        100289,
        100291
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 10;
    });

    // Lava Bolt (10 player)
    ApplySpellFix({
        98981,
        100290
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 4;
    });

    // Sulfuras Smash
    // Sniffs cast packets show immunities so we can assume that Sulfuras Smash does have interrupt flags internally.
    // We are going with SpellInterruptFlags::Stun so SMSG_SPELL_START sends the correct immunities
    ApplySpellFix({
        98710,
        100890,
        100891,
        100892
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->InterruptFlags |= SpellInterruptFlags::Stun;
    });

    // Sulfuras Smash
    ApplySpellFix({
        98708,
        100256,
        100257,
        100258
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx7 |= SPELL_ATTR7_NO_ATTACK_MISS;
    });

    // Entrapping Roots
    ApplySpellFix({
        100653,
        101237,
    }, [](SpellInfo* spellInfo)
    {
        // HACK! Caster - Target radius calculation needs corrections
        spellInfo->Effects[EFFECT_0].TargetBRadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_10_YARDS);
        spellInfo->Effects[EFFECT_1].TargetBRadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_10_YARDS);
    });

    // ENDOF FIRELANDS SPELLS

    //
    // GILNEAS SPELLS
    //
    // Curse of the Worgen
    ApplySpellFix({ 69123 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(135); // 100yd
    });

    // Forcecast summon personal Godfrey
    ApplySpellFix({ 68635, 68636 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_SUMMONER);
    });

    // ENDOF GILNEAS SPELLS

    //
    // ZUL'GURUB SPELLS
    //

    // Wave of Agony
    ApplySpellFix({ 96461 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetARadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_2_YARDS);
    });

    // Wave of Agony (Damage)
    ApplySpellFix({ 96460 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesCu |= SPELL_ATTR0_CU_CONE_LINE;
    });

    // Gaping Wound
    ApplySpellFix({ 97355 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(5); // 40yd
        spellInfo->Effects[EFFECT_1].TargetB = SpellImplicitTargetInfo(TARGET_DEST_DEST);
    });

    // Cave In
    ApplySpellFix({ 97380 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesCu |= SPELL_ATTR0_CU_NEGATIVE_EFF0;
    });

    // Zanzil's Resurrection Elixir
    ApplySpellFix({
        96316,
        96319
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetBRadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_200_YARDS);
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_DEST_DEST);
    });

    // Zanzil's Resurrection Elixir
    ApplySpellFix({
        96317,
        96470
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_DEST_DEST);
    });

    // Shadow Spike
    ApplySpellFix({ 97158 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Call Spirit
    ApplySpellFix({ 97152 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Spirit Warrior's Gaze
    ApplySpellFix({ 97597 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Rolling Boulders Search Effect
    ApplySpellFix({ 96839 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Sunder Rift
    ApplySpellFix({ 96964 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(18); // 20seconds
    });

   // Yoga Flame
    ApplySpellFix({
        97001,
        97352
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_NO_INITIAL_THREAT;
    });

    // Poison Bolt Volley
    ApplySpellFix({ 97018 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Sigil Shatter
    ApplySpellFix({ 98033 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].TriggerSpell = 98014;
    });

    // Sigil Shatter
    ApplySpellFix({ 98038 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_2].TriggerSpell = 98016;
    });

    // Sigil Shatter
    ApplySpellFix({ 98040 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].TriggerSpell = 98019;
    });

    // Boulder Smash
    ApplySpellFix({ 96834 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetBRadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_5_YARDS);
        spellInfo->Effects[EFFECT_1].TargetBRadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_5_YARDS);
        spellInfo->Effects[EFFECT_2].TargetBRadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_5_YARDS);
    });

    // ENDOF ZUL'GURUB SPELLS

    //
    // THRONE OF THE FOUR WINDS SPELLS
    //

    // Conclave of Wind
    // Teleport to Center
    ApplySpellFix({
        89844, // West
        89843  // North
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(135); // 100yd
    });

    // Nurture
    ApplySpellFix({ 85425 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx &= ~SPELL_ATTR1_IS_CHANNELLED;
    });

    // Soothing Breeze
    ApplySpellFix({ 86204 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(9); // 30seconds
    });

    // Ice Patch
    ApplySpellFix({ 86122 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(9); // 30seconds
    });

    // Tornado
    ApplySpellFix({
        86189,
        86190,
        86191
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetARadiusEntry = sSpellRadiusStore.LookupEntry(EFFECT_RADIUS_3_YARDS);
    });

    // Al'Akir

    // Wind Burst
    ApplySpellFix({
        87770,
        93261,
        93262,
        93261
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_IGNORE_LINE_OF_SIGHT;
    });

    // Lightning Strike (Force Cast)
    ApplySpellFix({ 91327 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Lightning Strike (Visual)
    ApplySpellFix({ 88230 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_IGNORE_LINE_OF_SIGHT;
    });

    // Lightning Strike (Damage)
    ApplySpellFix({
        88214,
        93255,
        93256,
        93257,
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->ConeAngle = 60.0f;
    });

    // Lightning Strike (Periodic Aura)
    ApplySpellFix({ 93247 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(387); // 16 seconds
    });

    // Lightning Strike (Heroic Chain-Caster Summon)
    ApplySpellFix({ 93247 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(467); // 22 seconds
    });

    // Ice Storm
    ApplySpellFix({ 87055 }, [](SpellInfo* spellInfo)
    {
        spellInfo->DurationEntry = sSpellDurationStore.LookupEntry(63); // 25 seconds
    });
}
