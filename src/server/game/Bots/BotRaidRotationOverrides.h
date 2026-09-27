#ifndef TRINITY_BOT_RAID_ROTATION_OVERRIDES_H
#define TRINITY_BOT_RAID_ROTATION_OVERRIDES_H

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRaidCanonicalClassRotation.h"
#include "Bots/BotRaidMajorArmor.h"
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"

#include <initializer_list>
#include <string>

// Raid-only profile row overrides for the canonical raid roster (round 3).
//
// Round 2 BWD 10N starved four DPS rotations. The world-DB rows are shared
// with the accepted Stonecore canaries and the Phase 8 calibrations, which
// must stay exactly reproducible (rows and profile content hash), so the fix
// is applied here, to ResolveProfileCombatAction's copy of the profile, and
// only while the bot is in raid scope (a raid cohort in a raid map). Nothing
// changes for a dungeon or calibration bot: the resolver does not call Apply.
//
// Each override matches the exact pre-round-3 value it replaces, so a later DB
// change to the row wins over it, and it tags the row (RaidScopeTag) so the
// diagnose mask shows which rows it touched.
//   * Beast Mastery: the Phase 1 coverage rows gave every single-target shot
//     max_enemies = 1 and Multi-Shot min_enemies = 3, so two enemies left no
//     legal action and three or more starved focus (Cobra Shot, the focus
//     generator, was gated too). Atramedes: 543 no_valid_profile_action
//     enemy_count_too_high.
//   * Retribution: the same coverage ceiling on Crusader Strike, Templar's
//     Verdict, Judgement, Exorcism and Hammer of Wrath (Divine Storm needs
//     four enemies), so two or three enemies left no Holy Power generator.
//     Divine Storm was an 'enemy' row capped at 5 yd for a zero-range
//     self-centred spell. Inquisition is a Holy Power buff that the raid
//     offensive-cooldown reservation held on every trash node; it keeps its
//     category and is exempted by ReservationExemptTag.
//   * Demonology: Summon Doomguard 18540 and Shadowflame 47897 are native
//     self-cast (SpellRange 1) but targeted the enemy, so they were
//     out_of_range (Maloriak: Doomguard chosen in 16 of 16 snapshots over
//     valid actions); the rotation's single-target rows had max_enemies = 1.
//     Affliction already has self-cast rows for both spells.
//   * Assassination: Vendetta 79140 is a 30 yd spell held at melee by
//     requires_melee_range; its 5 yd centre-distance cap rejected it 1,831
//     times on Magmaw.
namespace BotRaidRotationOverrides
{
inline constexpr char const* RaidScopeTag = "raid_rotation_20260926";
inline constexpr char const* ReservationExemptTag =
    BotRaidCooldownReservation::ReservationExemptTag;

inline bool IsSpell(BotActionProfileSpell const& spell,
    std::initializer_list<uint32> spellIds)
{
    for (uint32 spellId : spellIds)
        if (spell.SpellId == spellId)
            return true;
    return false;
}

inline bool ReplaceEnemyCeiling(BotActionProfileSpell& spell, uint8 from, uint8 to)
{
    if (spell.MaxEnemies != from)
        return false;
    spell.MaxEnemies = to;
    return true;
}

inline void AppendTag(BotActionProfileSpell& spell, char const* tag)
{
    spell.MechanicTags += spell.MechanicTags.empty() ? tag : std::string(",") + tag;
}

inline bool ApplyBeastMastery(BotActionProfileSpell& spell)
{
    if (IsSpell(spell, { 1978, 34026, 53351, 77767 }))
        return ReplaceEnemyCeiling(spell, 1, 0);
    // At three or more enemies Multi-Shot (bucket 2) is the focus dump.
    if (spell.SpellId == 3044)
        return ReplaceEnemyCeiling(spell, 1, 2);
    return false;
}

inline bool ApplyRetribution(BotActionProfileSpell& spell)
{
    if (IsSpell(spell, { 35395, 85256, 20271, 879, 24275 }))
        return ReplaceEnemyCeiling(spell, 1, 0);
    if (spell.SpellId == 53385 && spell.TargetSelector == "enemy")
    {
        // Native 8 yd radius around the paladin; at four or more enemies it
        // outranks Crusader Strike (bucket 1, damage weight 0.94).
        spell.TargetSelector = "self";
        spell.MaxRange = 8.0f;
        spell.PriorityBucket = 1;
        spell.SortOrder = 19;
        spell.DamageWeight = 1.00f;
        return true;
    }
    if (spell.SpellId == 84963
        && !BotRaidCooldownReservation::HasTag(spell.MechanicTags, ReservationExemptTag))
    {
        AppendTag(spell, ReservationExemptTag);
        return true;
    }
    return false;
}

inline bool ApplyDemonology(BotActionProfileSpell& spell)
{
    if (spell.SpellId == 18540 && spell.TargetSelector == "enemy")
    {
        spell.TargetSelector = "self";
        spell.MinRange = 0.0f;
        spell.MaxRange = 0.0f;
        spell.RequiresRangedRange = false;
        spell.MaxEnemies = 0;
        return true;
    }
    if (spell.SpellId == 47897 && spell.TargetSelector == "enemy")
    {
        spell.TargetSelector = "self";
        spell.MinRange = 0.0f;
        spell.MaxRange = 8.0f;
        return true;
    }
    // Boss plus one add; three or more keep the AoE rows and the filler.
    if (IsSpell(spell, { 348, 172, 603, 71521, 74434, 6353 }))
        return ReplaceEnemyCeiling(spell, 1, 2);
    return false;
}

inline bool ApplyAssassination(BotActionProfileSpell& spell)
{
    // An unset maximum falls back to the native 30 yd; requires_melee_range
    // still holds Vendetta to native melee reach.
    if (spell.SpellId == 79140 && spell.RequiresMeleeRange && spell.MaxRange == 5.0f)
    {
        spell.MaxRange = 0.0f;
        return true;
    }
    return false;
}

// Returns the number of rows changed. Call only in raid scope.
inline uint32 Apply(BotClassSpecActionProfile& profile)
{
    if (profile.Role != "dps")
        return 0;
    bool (*apply)(BotActionProfileSpell&) = nullptr;
    if (profile.ClassId == 3 && profile.SpecTag == "beast_mastery_hunter")
        apply = &ApplyBeastMastery;
    else if (profile.ClassId == 2 && profile.SpecTag == "retribution_paladin")
        apply = &ApplyRetribution;
    else if (profile.ClassId == 9 && profile.SpecTag == "demonology_warlock")
        apply = &ApplyDemonology;
    else if (profile.ClassId == 4 && profile.SpecTag == "assassination_rogue")
        apply = &ApplyAssassination;
    if (!apply)
        return 0;
    uint32 changed = 0;
    for (BotActionProfileSpell& spell : profile.Spells)
        if (apply(spell))
        {
            AppendTag(spell, RaidScopeTag);
            ++changed;
        }
    return changed;
}

// Round 4, canonical-composition raids only (BotCanonicalRaidScope.h): the
// Orc Survival hunter is also the legacy accepted Magmaw hunter 30009, so a
// raid-wide Survival fix would change that accepted result.
//   * Blood Fury 20572 carries the pinned single-target fixture's one-enemy
//     ceiling (max_enemies = 1), so a boss with one engaged add within 12 yd
//     (Magmaw's parasites, Maloriak's aberrations, a second Omnotron
//     construct) never saw it. The raid cooldown reservation still holds it
//     on trash and pre-pull, as it holds every offensive cooldown.
inline constexpr char const* CanonicalScopeTag = "canonical_raid_rotation_20260926";
inline constexpr char const* CanonicalClassRotationTag = "canonical_raid_rotation_20260927";

inline bool ApplySurvival(BotActionProfileSpell& spell)
{
    if (spell.SpellId == 20572)
        return ReplaceEnemyCeiling(spell, 1, 0);
    return false;
}

// Round 5: the canonical druid (Balance DPS or Feral tank) gains a Faerie
// Fire row that keeps the major armor debuff on the boss
// (BotRaidMajorArmor.h). The legacy accepted Magmaw druid 30001 is Balance,
// so this too stays out of the legacy raid scope.

// Returns the number of rows changed or added. Call only in canonical raid
// scope.
inline uint32 ApplyCanonical(BotClassSpecActionProfile& profile)
{
    if (BotActionProfileSpell* upkeep = BotRaidMajorArmor::AppendUpkeepRow(profile))
    {
        AppendTag(*upkeep, CanonicalScopeTag);
        return 1;
    }
    // BWD program round 2: Demonology lane, Fel Flame and Drain Life,
    // Assassination Fan of Knives disabled (user decision 2026-09-27),
    // Elemental Mastery
    // (BotRaidCanonicalClassRotation.h).
    if (uint32 const classRows = BotRaidCanonicalClassRotation::Apply(profile,
            [](BotActionProfileSpell& spell) { AppendTag(spell, CanonicalClassRotationTag); }))
        return classRows;
    if (profile.Role != "dps" || profile.ClassId != 3 || profile.SpecTag != "survival")
        return 0;
    uint32 changed = 0;
    for (BotActionProfileSpell& spell : profile.Spells)
        if (ApplySurvival(spell))
        {
            AppendTag(spell, CanonicalScopeTag);
            ++changed;
        }
    return changed;
}
}

#endif
