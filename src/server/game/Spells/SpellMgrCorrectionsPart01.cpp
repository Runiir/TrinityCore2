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

void SpellMgrCorrections::ApplyPart01()
{
    ApplySpellFix({
        63026, // Force Cast (HACK: Target shouldn't be changed)
        63137  // Force Cast (HACK: Target shouldn't be changed; summon position should be untied from spell destination)
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[0].TargetA = SpellImplicitTargetInfo(TARGET_DEST_DB);
    });

    // Drink! (Brewfest)
    ApplySpellFix({ 42436 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_TARGET_ANY);
    });

    // Summon Skeletons
    ApplySpellFix({ 52611, 52612 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].MiscValueB = 64;
    });

    ApplySpellFix({
        40244, // Simon Game Visual
        40245, // Simon Game Visual
        40246, // Simon Game Visual
        40247, // Simon Game Visual
        42835  // Spout, remove damage effect, only anim is needed
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].Effect = 0;
    });

    // Immolate
    ApplySpellFix({ 348 }, [](SpellInfo* spellInfo)
    {
        // copy SP scaling data from direct damage to DoT
        spellInfo->Effects[EFFECT_0].BonusMultiplier = spellInfo->Effects[EFFECT_1].BonusMultiplier;
    });

    // These Cataclysm warlock spells have a zero EffectBonusCoefficient in the
    // client SpellEffect data.  Their retail coefficients were formerly
    // supplied by spell_bonus_data before that legacy override table was
    // removed in favour of DBC coefficients.  Keep the exceptional values as
    // SpellInfo corrections so the normal native damage pipeline (owner spell
    // power inheritance, spell mods, crit, target mitigation) remains the
    // authority.
    ApplySpellFix({ 6353 }, [](SpellInfo* spellInfo) // Soul Fire
    {
        spellInfo->Effects[EFFECT_0].BonusMultiplier = 0.726f;
    });

    ApplySpellFix({ 48181 }, [](SpellInfo* spellInfo) // Haunt
    {
        spellInfo->Effects[EFFECT_0].BonusMultiplier = 0.5577f;
    });

    ApplySpellFix({ 54049 }, [](SpellInfo* spellInfo) // Shadow Bite
    {
        spellInfo->Effects[EFFECT_0].BonusMultiplier = 1.228f;
        spellInfo->CritDamageMultiplier = 2.0f;
    });

    // Death's Embrace also increases Drain Soul shadow damage during execute.
    // The client class mask omits Drain Soul's 0x4000 family flag, so the
    // native done-percent stage otherwise misses this rank-scaled bonus.
    ApplySpellFix({ 47198, 47199, 47200 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].SpellClassMask[0] |= 0x00004000;
    });

    ApplySpellFix({
        82690, // Flame Orb
        84717  // Frostfire Orb
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].AuraPeriod = 1000;
    });

    ApplySpellFix({
        63665, // Charge (Argent Tournament emote on riders)
        31298, // Sleep (needs target selection script)
        51904, // Summon Ghouls On Scarlet Crusade (this should use conditions table, script for this spell needs to be fixed)
        2895,  // Wrath of Air Totem rank 1 (Aura)
        68933, // Wrath of Air Totem rank 2 (Aura)
        29200  // Purify Helboar Meat
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_CASTER);
        spellInfo->Effects[EFFECT_0].TargetB = SpellImplicitTargetInfo();
    });

    ApplySpellFix({
        56690, // Thrust Spear
        60586, // Mighty Spear Thrust
        60776, // Claw Swipe
        60881, // Fatal Strike
        60864  // Jaws of Death
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx4 |= SPELL_ATTR4_IGNORE_DAMAGE_TAKEN_MODIFIERS;
    });

    // Immolate
    ApplySpellFix({ 348 }, [](SpellInfo* spellInfo)
    {
        // copy SP scaling data from direct damage to DoT
        spellInfo->Effects[EFFECT_0].BonusMultiplier = spellInfo->Effects[EFFECT_1].BonusMultiplier;
    });

    ApplySpellFix({
        42818, // Headless Horseman - Wisp Flight Port
        42821  // Headless Horseman - Wisp Flight Missile
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(6); // 100 yards
    });

    // They Must Burn Bomb Aura (self)
    ApplySpellFix({ 36350 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TriggerSpell = 36325; // They Must Burn Bomb Drop (DND)
    });

    ApplySpellFix({
        61407, // Energize Cores
        62136, // Energize Cores
        54069, // Energize Cores
        56251  // Energize Cores
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_SRC_AREA_ENTRY);
    });

    ApplySpellFix({
        50785, // Energize Cores
        59372  // Energize Cores
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_SRC_AREA_ENEMY);
    });

    ApplySpellFix({
        31347, // Doom
        36327, // Shoot Arcane Explosion Arrow
        39365, // Thundering Storm
        41071, // Raise Dead (HACK)
        42442, // Vengeance Landing Cannonfire
        42611, // Shoot
        44978, // Wild Magic
        45001, // Wild Magic
        45002, // Wild Magic
        45004, // Wild Magic
        45006, // Wild Magic
        45010, // Wild Magic
        45761, // Shoot Gun
        45863, // Cosmetic - Incinerate to Random Target
        48246, // Ball of Flame
        41635, // Prayer of Mending
        44869, // Spectral Blast
        45027, // Revitalize
        45976, // Muru Portal Channel
        52124, // Sky Darkener Assault
        52479, // Gift of the Harvester
        61588, // Blazing Harpoon
        55479, // Force Obedience
        28560, // Summon Blizzard (Sapphiron)
        53096, // Quetz'lun's Judgment
        70743, // AoD Special
        70614, // AoD Special - Vegard
        4020,  // Safirdrang's Chill
        52438, // Summon Skittering Swarmer (Force Cast)
        52449, // Summon Skittering Infector (Force Cast)
        53609, // Summon Anub'ar Assassin (Force Cast)
        53457,  // Summon Impale Trigger (AoE)
        45907  // Torch Target Picker
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
    });

    // Skartax Purple Beam
    ApplySpellFix({ 36384 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 2;
    });

    ApplySpellFix({
        28542, // Life Drain - Sapphiron
        29213, // Curse of the Plaguebringer - Noth
        29576, // Multi-Shot
        37790, // Spread Shot
        39992, // Needle Spine
        40816, // Saber Lash
        41303, // Soul Drain
        41376, // Spite
        45248, // Shadow Blades
        46771, // Flame Sear
        66588 // Flaming Spear
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 3;
    });

    ApplySpellFix({
        42005, // Bloodboil
        38296, // Spitfire Totem
        37676, // Insidious Whisper
        46008, // Negative Energy
        45641, // Fire Bloom
        55665, // Life Drain - Sapphiron (H)
        28796  // Poison Bolt Volly - Faerlina
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 5;
    });

    // Curse of the Plaguebringer - Noth (H)
    ApplySpellFix({ 54835 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 8;
    });

    ApplySpellFix({
        40827, // Sinful Beam
        40859, // Sinister Beam
        40860, // Vile Beam
        40861, // Wicked Beam
        54098  // Poison Bolt Volly - Faerlina (H)
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 10;
    });

    // Unholy Frenzy
    ApplySpellFix({ 50312 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 15;
    });

    // Murmur's Touch
    ApplySpellFix({ 33711, 38794 }, [](SpellInfo* spellInfo)
    {
        spellInfo->MaxAffectedTargets = 1;
        spellInfo->Effects[EFFECT_0].TriggerSpell = 33760;
    });

    // Magic Suppression - DK
    ApplySpellFix({ 49224, 49610, 49611 }, [](SpellInfo* spellInfo)
    {
        spellInfo->ProcCharges = 0;
    });

    // Oscillation Field
    ApplySpellFix({ 37408 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx3 |= SPELL_ATTR3_DOT_STACKING_RULE;
    });

    // Everlasting Affliction
    ApplySpellFix({ 47201, 47202, 47203 }, [](SpellInfo* spellInfo)
    {
        // add corruption to affected spells
        spellInfo->Effects[EFFECT_1].SpellClassMask[0] |= 2;
    });

    // Summon Ravenous Worgen
    // Serverside dummy target so we have to change to spell_target_position
    ApplySpellFix({ 66925, 66836 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = TARGET_DEST_DB;
    });

    // Renewed Hope
    ApplySpellFix({
        57470, // (Rank 1)
        57472  // (Rank 2)
    }, [](SpellInfo* spellInfo)
    {
        // should also affect Flash Heal
        spellInfo->Effects[EFFECT_0].SpellClassMask[0] |= 0x800;
    });

    // Cobra Strikes
    ApplySpellFix({ 53257 }, [](SpellInfo* spellInfo)
    {
        spellInfo->ProcCharges = 2;
        spellInfo->StackAmount = 0;
    });

    // Wrecking Crew
    ApplySpellFix({ 46867, 56611, 56612 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].SpellClassMask = flag96(0x02000000, 0, 0);
    });

    // Death and Decay
    ApplySpellFix({ 52212 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx6 |= SPELL_ATTR6_IGNORE_PHASE_SHIFT;
    });

    // Crafty's Ultra-Advanced Proto-Typical Shortening Blaster
    ApplySpellFix({ 51912 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].AuraPeriod = 3000;
    });

    // Master Shapeshifter: missing stance data for forms other than bear - bear version has correct data
    // To prevent aura staying on target after talent unlearned
    ApplySpellFix({
        48420, // Master Shapeshifter
        24900  // Heart of the Wild - Cat Effect
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Stances = UI64LIT(1) << (FORM_CAT - 1);
    });

    ApplySpellFix({ 48421 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Stances = UI64LIT(1) << (FORM_MOONKIN - 1);
    });

    ApplySpellFix({ 24899 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Stances = UI64LIT(1) << (FORM_BEAR - 1);
    });

    // Tree of Life passives
    ApplySpellFix({
        5420,
        81097
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Stances = UI64LIT(1) << (FORM_TREE - 1);
    });

    // Improved Shadowform (Rank 1)
    ApplySpellFix({ 47569 }, [](SpellInfo* spellInfo)
    {
        // with this spell atrribute aura can be stacked several times
        spellInfo->Attributes &= ~SPELL_ATTR0_NOT_SHAPESHIFTED;
    });

    // Hymn of Hope
    ApplySpellFix({ 64904 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_1].ApplyAuraName = SPELL_AURA_MOD_INCREASE_ENERGY_PERCENT;
    });

    // Nether Portal - Perseverence
    ApplySpellFix({ 30421 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_2].BasePoints += 30000;
    });

    // Parasitic Shadowfiend Passive
    ApplySpellFix({ 41913 }, [](SpellInfo* spellInfo)
    {
        // proc debuff, and summon infinite fiends
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_DUMMY;
    });

    ApplySpellFix({
        27892, // To Anchor 1
        27928, // To Anchor 1
        27935, // To Anchor 1
        27915, // Anchor to Skulls
        27931, // Anchor to Skulls
        27937, // Anchor to Skulls
        16177, // Ancestral Fortitude (Rank 1)
        16236, // Ancestral Fortitude (Rank 2)
        47930, // Grace
        48714, // Compelled
        7853,  // The Art of Being a Water Terror: Force Cast on Player
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(13);
    });

    // Wrath of the Plaguebringer
    ApplySpellFix({ 29214, 54836 }, [](SpellInfo* spellInfo)
    {
        // target allys instead of enemies, target A is src_caster, spells with effect like that have ally target
        // this is the only known exception, probably just wrong data
        spellInfo->Effects[EFFECT_0].TargetB = SpellImplicitTargetInfo(TARGET_UNIT_SRC_AREA_ALLY);
        spellInfo->Effects[EFFECT_1].TargetB = SpellImplicitTargetInfo(TARGET_UNIT_SRC_AREA_ALLY);
    });

    // Vampiric Touch (dispel effect)
    ApplySpellFix({ 64085 }, [](SpellInfo* spellInfo)
    {
        // copy from similar effect of Unstable Affliction (31117)
        spellInfo->AttributesEx4 |= SPELL_ATTR4_IGNORE_DAMAGE_TAKEN_MODIFIERS;
        spellInfo->AttributesEx6 |= SPELL_ATTR6_IGNORE_CASTER_DAMAGE_MODIFIERS;
    });

    // Improved Devouring Plague
    ApplySpellFix({ 63675 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx6 |= SPELL_ATTR6_IGNORE_CASTER_DAMAGE_MODIFIERS;
    });

    // Tremor Totem (instant pulse)
    ApplySpellFix({ 8145 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_IGNORE_LINE_OF_SIGHT;
        spellInfo->AttributesEx5 |= SPELL_ATTR5_EXTRA_INITIAL_PERIOD;
    });

    // Earthbind Totem (instant pulse)
    ApplySpellFix({ 6474 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx5 |= SPELL_ATTR5_EXTRA_INITIAL_PERIOD;
    });

    // Marked for Death
    ApplySpellFix({
        53241, // (Rank 1)
        53243, // (Rank 2)
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].SpellClassMask = flag96(0x00067801, 0x10820001, 0x00000801);
    });

    ApplySpellFix({
        70728, // Exploit Weakness (needs target selection script)
        70840  // Devious Minds (needs target selection script)
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_CASTER);
        spellInfo->Effects[EFFECT_0].TargetB = SpellImplicitTargetInfo(TARGET_UNIT_PET);
    });

    // Culling The Herd (needs target selection script)
    ApplySpellFix({ 70893 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_CASTER);
        spellInfo->Effects[EFFECT_0].TargetB = SpellImplicitTargetInfo(TARGET_UNIT_MASTER);
    });

    // Sigil of the Frozen Conscience
    ApplySpellFix({ 54800 }, [](SpellInfo* spellInfo)
    {
        // change class mask to custom extended flags of Icy Touch
        // this is done because another spell also uses the same SpellFamilyFlags as Icy Touch
        // SpellFamilyFlags[0] & 0x00000040 in SPELLFAMILY_DEATHKNIGHT is currently unused (3.3.5a)
        // this needs research on modifier applying rules, does not seem to be in Attributes fields
        spellInfo->Effects[EFFECT_0].SpellClassMask = flag96(0x00000040, 0x00000000, 0x00000000);
    });

    // Idol of the Flourishing Life
    ApplySpellFix({ 64949 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].SpellClassMask = flag96(0x00000000, 0x02000000, 0x00000000);
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_ADD_FLAT_MODIFIER;
    });

    ApplySpellFix({
        34231, // Libram of the Lightbringer
        60792, // Libram of Tolerance
        64956  // Libram of the Resolute
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].SpellClassMask = flag96(0x80000000, 0x00000000, 0x00000000);
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_ADD_FLAT_MODIFIER;
    });

    ApplySpellFix({
        28851, // Libram of Light
        28853, // Libram of Divinity
        32403  // Blessed Book of Nagrand
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].SpellClassMask = flag96(0x40000000, 0x00000000, 0x00000000);
        spellInfo->Effects[EFFECT_0].ApplyAuraName = SPELL_AURA_ADD_FLAT_MODIFIER;
    });

    // Ride Carpet
    ApplySpellFix({ 45602 }, [](SpellInfo* spellInfo)
    {
        // force seat 0, vehicle doesn't have the required seat flags for "no seat specified (-1)"
        spellInfo->Effects[EFFECT_0].BasePoints = 0;
    });

    // Easter Lay Noblegarden Egg Aura - Interrupt flags copied from aura which this aura is linked with
    ApplySpellFix({ 61719 }, [](SpellInfo* spellInfo)
    {
        spellInfo->AuraInterruptFlags = SpellAuraInterruptFlags::HostileActionReceived | SpellAuraInterruptFlags::Damage;
    });

    ApplySpellFix({
        71838, // Drain Life - Bryntroll Normal
        71839  // Drain Life - Bryntroll Heroic
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx2 |= SPELL_ATTR2_CANT_CRIT;
    });

    ApplySpellFix({
        56606, // Ride Jokkum
        61791  // Ride Vehicle (Yogg-Saron)
    }, [](SpellInfo* spellInfo)
    {
        /// @todo: remove this when basepoints of all Ride Vehicle auras are calculated correctly
        spellInfo->Effects[EFFECT_0].BasePoints = 1;
    });

    // Black Magic
    ApplySpellFix({ 59630 }, [](SpellInfo* spellInfo)
    {
        spellInfo->Attributes |= SPELL_ATTR0_PASSIVE;
    });

    ApplySpellFix({
        17364, // Stormstrike
        48278, // Paralyze
        53651  // Light's Beacon
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx3 |= SPELL_ATTR3_DOT_STACKING_RULE;
    });

    ApplySpellFix({
        51798, // Brewfest - Relay Race - Intro - Quest Complete
        47134  // Quest Complete
    }, [](SpellInfo* spellInfo)
    {
        //! HACK: This spell break quest complete for alliance and on retail not used �_O
        spellInfo->Effects[EFFECT_0].Effect = 0;
    });

    ApplySpellFix({
        42490, // Energized!
        42492, // Cast Energized
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx |= SPELL_ATTR1_NO_THREAT;
    });

    ApplySpellFix({
        46842, // Flame Ring
        46836  // Flame Patch
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo();
    });

    // Test Ribbon Pole Channel
    ApplySpellFix({ 29726 }, [](SpellInfo* spellInfo)
    {
        spellInfo->ChannelInterruptFlags &= ~SpellAuraInterruptFlags::Action;
    });

    ApplySpellFix({
        42767, // Sic'em
        43092  // Stop the Ascension!: Halfdan's Soul Destruction
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Effects[EFFECT_0].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_NEARBY_ENTRY);
    });

    ApplySpellFix({
        19503, // Scatter Shot
        34490  // Silencing Shot
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->Speed = 0.f;
    });

    // Safeguard
    ApplySpellFix({
        46946, // (Rank 1)
        46947  // (Rank 2)
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(34); // Twenty-Five yards
    });

    // Concussive Barrage
    ApplySpellFix({ 35101 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(173); // Anywhere
    });

    // Survey Sinkholes
    ApplySpellFix({ 45853 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RangeEntry = sSpellRangeStore.LookupEntry(5); // 40 yards
    });

    //
    // BLACK TEMPLE SPELLS
    //
    ApplySpellFix({
        41485, // Deadly Poison
        41487  // Envenom
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->AttributesEx6 |= SPELL_ATTR6_IGNORE_PHASE_SHIFT;
    });
    // ENDOF BLACK TEMPLE SPELLS

    // Tag Greater Felfire Diemetradon
    ApplySpellFix({ 37851 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RecoveryTime = 3000;
    });

    // Jormungar Strike
    ApplySpellFix({ 56513 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RecoveryTime = 2000;
    });

    ApplySpellFix({
        54997, // Cast Net (tooltip says 10s but sniffs say 6s)
        56524  // Acid Breath
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RecoveryTime = 6000;
    });

    ApplySpellFix({
        47911, // EMP
        48620, // Wing Buffet
        51752  // Stampy's Stompy-Stomp
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RecoveryTime = 10000;
    });

    ApplySpellFix({
        37727, // Touch of Darkness
        54996  // Ice Slick (tooltip says 20s but sniffs say 12s)
    }, [](SpellInfo* spellInfo)
    {
        spellInfo->RecoveryTime = 12000;
    });

    // Signal Helmet to Attack
    ApplySpellFix({ 51748 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RecoveryTime = 15000;
    });

    // Charge
    ApplySpellFix({ 51756 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RecoveryTime = 20000;
    });

    // Engulfing Flames
    ApplySpellFix({ 74039 }, [](SpellInfo* spellInfo)
    {
        spellInfo->RecoveryTime = 1000;
    });
}
