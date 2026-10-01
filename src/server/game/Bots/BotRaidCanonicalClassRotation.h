#ifndef TRINITY_BOT_RAID_CANONICAL_CLASS_ROTATION_H
#define TRINITY_BOT_RAID_CANONICAL_CLASS_ROTATION_H

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRaidCanonicalAssassination.h"

#include <string>

// BWD 10N program round 2 class-rotation repairs, canonical-composition raid
// cohorts only (BotCanonicalRaidScope.h, via
// BotRaidRotationOverrides::ApplyCanonical). The world-DB rows stay the
// accepted Phase 8 calibration and Stonecore rows, and the legacy BWD shards
// (Assassination 30107-30507, no Demonology) never see these edits. Each edit
// matches the exact DB value it replaces, so a later DB change wins.
//
// Evidence: round 1, label blackwing_descent_10n-r01-553da85c98.
//   * Demonology: the Phase 8 short-range lane caps every hostile row at
//     18 yd (2026_07_25_12_phase8_demonology_melee_burst.sql). Raid ranged
//     positions are 23-35 yd out; on Atramedes the warlock landed 12-14 casts
//     in 130 s (damage uptime 0.13-0.30), the decision trace alternating
//     max_range_exceeded runs with profile_max_range_reconciled approaches
//     that the Sonar Pulse movement undid. The cap is centre to centre, so a
//     boss with a 20 yd combat reach (Atramedes, Chimaeron) left almost no
//     legal cast point. The enemy rows use the native spell range (an unset
//     maximum, 40 yd for every one of them); the profile lane becomes 40 yd.
//     Shadowflame (8 yd, self), Immolation Aura (self) and Hellfire (self,
//     10 yd) keep their short envelopes.
//   * Demonology has no instant filler: moving, no row was legal
//     (movement_requires_instant_action 72-103 times per Atramedes kill,
//     189 on the long Chimaeron attempt). Fel Flame is Affliction's moving
//     filler (2026_09_12_02_affliction_moving_fel_flame.sql); the same last-
//     choice row is added. The canonical composition declares the spell.
//   * Demonology Drain Life is the calibration lane's self-heal (bucket 0,
//     below 90% health). BotRaidHealthRecoveryGate releases it at 35% health,
//     where a Chimaeron raid lives (Finkle's Mixture floors health): the
//     warlock channelled it 10-34 times per Chimaeron attempt, its most cast
//     spell, for 24 channels and 75.5k damage in the counted kill. Healers own
//     raid health, so in a canonical raid the row is never admitted.
//   * Assassination: Fan of Knives 51723 never landed (its enemy-targeted row
//     was out_of_range on every attempt: Maloriak 24, Omnotron 13, 0 damage).
//     Source: user decision 2026-09-27, "Assasination rogue dont need to use
//     fok. Its always a dps loss". Round 2 set its self health ceiling to 0
//     (as Drain Life); that still let the range-recovery lane submit it, so
//     since round 4 the canonical profile drops the row
//     (BotRaidCanonicalAssassination.h). The Phase 8 and Stonecore rows keep
//     it.
//   * Elemental: the canonical shaman has the Elemental Mastery talent 16166
//     (self, instant, SpellRange 1) but the Phase 8 profile has no row for it,
//     so it was never cast in any round 1 kill. An offensive-cooldown row is
//     added; the raid cooldown reservation holds it on trash like every other.
namespace BotRaidCanonicalClassRotation
{
inline constexpr float DemonologyShortLane = 18.0f;
inline constexpr float DemonologyRaidLane = 40.0f;
// An unset row maximum: the resolver uses the spell's native range.
inline constexpr float NativeRange = 0.0f;
inline constexpr uint32 FelFlame = 77799;
inline constexpr uint32 DrainLife = 689;
inline constexpr float DrainLifeCalibrationHealth = 0.90f;
inline constexpr uint32 FanOfKnives = 51723;
inline constexpr float FanOfKnivesRadius = 10.0f;
inline constexpr uint32 ElementalMastery = 16166;

inline bool HasSpellRow(BotClassSpecActionProfile const& profile, uint32 spellId)
{
    for (BotActionProfileSpell const& spell : profile.Spells)
        if (spell.SpellId == spellId)
            return true;
    return false;
}

// Mirrors the Affliction row: builder, bucket 14, sort 140, moving only.
inline BotActionProfileSpell FelFlameMovingRow()
{
    BotActionProfileSpell spell;
    spell.SpellId = FelFlame;
    spell.Category = BotCombatActionCategory::Builder;
    spell.MechanicTags = "fel_flame,moving_filler";
    spell.DamageWeight = 0.10f;
    spell.SortOrder = 140;
    spell.PriorityBucket = 14;
    spell.MinEnemies = 1;
    spell.MaxEnemies = 0;
    spell.TargetSelector = "enemy";
    spell.MovementDirective = "ranged";
    spell.AutoAttackMode = "none";
    spell.MinRange = 0.0f;
    spell.MaxRange = NativeRange;
    spell.RequiresMoving = true;
    return spell;
}

inline BotActionProfileSpell ElementalMasteryRow()
{
    BotActionProfileSpell spell;
    spell.SpellId = ElementalMastery;
    spell.Category = BotCombatActionCategory::OffensiveCooldown;
    spell.MechanicTags = "elemental_mastery,self,burst";
    spell.DamageWeight = 1.0f;
    spell.SortOrder = 12;
    spell.PriorityBucket = 1;
    spell.MinEnemies = 1;
    spell.MaxEnemies = 0;
    spell.TargetSelector = "self";
    return spell;
}

inline bool WidenDemonologyLane(BotActionProfileSpell& spell)
{
    if (spell.TargetSelector != "enemy" || spell.MaxRange != DemonologyShortLane)
        return false;
    spell.MaxRange = NativeRange;
    return true;
}

inline bool HoldDrainLife(BotActionProfileSpell& spell)
{
    if (spell.SpellId != DrainLife || spell.MaxSelfHealthPct != DrainLifeCalibrationHealth)
        return false;
    spell.MaxSelfHealthPct = 0.0f;
    return true;
}

// Returns the changed or added rows; the caller tags them. The Demonology
// profile-level lane (the resolver's default and no-action range) widens with
// its rows but is not a row, so it is not counted.
template <typename Tag>
uint32 Apply(BotClassSpecActionProfile& profile, Tag&& tag)
{
    if (profile.Role != "dps")
        return 0;
    uint32 changed = 0;
    if (profile.ClassId == 9 && profile.SpecTag == "demonology_warlock")
    {
        if (profile.MaxRange == DemonologyShortLane)
            profile.MaxRange = DemonologyRaidLane;
        for (BotActionProfileSpell& spell : profile.Spells)
        {
            bool const widened = WidenDemonologyLane(spell);
            bool const held = HoldDrainLife(spell);
            if (widened || held)
            {
                tag(spell);
                ++changed;
            }
        }
        if (!HasSpellRow(profile, FelFlame))
        {
            profile.Spells.push_back(FelFlameMovingRow());
            tag(profile.Spells.back());
            ++changed;
        }
    }
    else if (profile.ClassId == 7 && profile.SpecTag == "elemental_shaman"
        && !HasSpellRow(profile, ElementalMastery))
    {
        profile.Spells.push_back(ElementalMasteryRow());
        tag(profile.Spells.back());
        ++changed;
    }
    else if (profile.ClassId == 4 && profile.SpecTag == "assassination_rogue")
        // Round 4: Fan of Knives removed, the Slice and Dice refresh Envenom
        // added (BotRaidCanonicalAssassination.h).
        changed += BotRaidCanonicalAssassination::Apply(profile, tag);
    return changed;
}
}

#endif
