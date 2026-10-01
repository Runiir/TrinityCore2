#ifndef TRINITY_BOT_RAID_CANONICAL_ASSASSINATION_H
#define TRINITY_BOT_RAID_CANONICAL_ASSASSINATION_H

#include "Bots/BotClassSpecActionProfile.h"

#include <algorithm>
#include <string>

// BWD 10N round 4 Assassination repairs, canonical-composition raids only
// (applied by the canonical class rotation, BotRaidCanonicalClassRotation.h,
// through BotRaidRotationOverrides::ApplyCanonical). The Phase 8, Stonecore and
// legacy Magmaw rows are untouched.
//
// Evidence: round 3 (label blackwing_descent_10n-r03-a3864fcf6d), Maloriak
// batch cd3009, the rogue's 268 s boss window: Slice and Dice cast 10 times,
// Rupture 5, Envenom 6, Mutilate 48 (combat log action outcomes). The pinned
// rows cast Slice and Dice whenever it is down, at any combo point count, and
// have no row that refreshes it early, so every expiry spends a short
// finisher on it; Magmaw r02: 23.6 casts per minute against 33.1 on WCL.
//
// Assassination standard (the pinned Cataclysm APL): keep Slice and Dice up,
// keep Rupture up, Envenom at 4-5 combo points, Mutilate below 4. With Cut to
// the Chase (talent 51667, on the canonical rogue) Envenom refreshes Slice
// and Dice to its five-point duration, and the APL spends
//     envenom,if=combo_points>=2&buff.slice_and_dice.remains<3
// before the buff can drop. That row is added here. The existing rows keep
// their order: Slice and Dice when down (bucket 2), Rupture when missing or
// below 2 s at 4+ points (3), Envenom at 4+ (4), Mutilate at 3 or fewer (5).
//
// Fan of Knives (user decision 2026-09-27: never in raid) is removed from the
// canonical profile. The round 2 self-health ceiling did not stop it: an
// enemy row rejected out_of_range before admission is kept as the resolver's
// range-recovery action ahead of the self-health gate, and r03 cd3009 still
// submitted it 8 times (all out_of_range).
namespace BotRaidCanonicalAssassination
{
inline constexpr uint32 FanOfKnives = 51723;
inline constexpr float FanOfKnivesRadius = 10.0f;
inline constexpr uint32 Envenom = 32645;
inline constexpr uint32 SliceAndDice = 5171;
inline constexpr uint8 EnvenomComboPoints = 4;
inline constexpr uint8 SliceRefreshComboPoints = 2;
inline constexpr uint32 SliceRefreshBelowMs = 3000;
inline constexpr uint8 SliceRefreshBucket = 2;
inline constexpr uint32 SliceRefreshSortOrder = 45;
inline constexpr char const* SliceRefreshTags =
    "envenom,slice_and_dice_refresh,cut_to_the_chase";

// The pinned Phase 8 Fan of Knives row (enemy, 10 yd), with or without the
// round 2 self-health ceiling.
inline bool IsPinnedFanOfKnives(BotActionProfileSpell const& spell)
{
    return spell.SpellId == FanOfKnives && spell.TargetSelector == "enemy"
        && spell.MaxRange == FanOfKnivesRadius;
}

inline bool IsSliceRefreshRow(BotActionProfileSpell const& spell)
{
    return spell.SpellId == Envenom && spell.RequiredSelfAura == SliceAndDice;
}

// The pinned four-point Envenom row.
inline BotActionProfileSpell const* FindPinnedEnvenom(BotClassSpecActionProfile const& profile)
{
    for (BotActionProfileSpell const& spell : profile.Spells)
        if (spell.SpellId == Envenom && spell.TargetSelector == "enemy"
            && spell.MinComboPoints == EnvenomComboPoints && !spell.RequiredSelfAura)
            return &spell;
    return nullptr;
}

// The pinned Envenom row, gated to refresh a live Slice and Dice below 3 s
// from 2 combo points, ahead of Rupture and the four-point Envenom.
inline BotActionProfileSpell SliceRefreshRow(BotActionProfileSpell envenom)
{
    envenom.MechanicTags = SliceRefreshTags;
    envenom.PriorityBucket = SliceRefreshBucket;
    envenom.SortOrder = SliceRefreshSortOrder;
    envenom.MinComboPoints = SliceRefreshComboPoints;
    envenom.MaxComboPoints = 0;
    envenom.RequiredSelfAura = SliceAndDice;
    envenom.ForbiddenSelfAura = 0;
    envenom.MinSelfAuraRemainingMs = 0;
    envenom.MaxSelfAuraRemainingMs = SliceRefreshBelowMs;
    return envenom;
}

// Returns the removed plus added rows; tag(row) marks each added row.
template <typename Tag>
uint32 Apply(BotClassSpecActionProfile& profile, Tag&& tag)
{
    if (profile.ClassId != 4 || profile.SpecTag != "assassination_rogue"
        || profile.Role != "dps")
        return 0;
    size_t const before = profile.Spells.size();
    profile.Spells.erase(std::remove_if(profile.Spells.begin(), profile.Spells.end(),
        IsPinnedFanOfKnives), profile.Spells.end());
    uint32 changed = uint32(before - profile.Spells.size());
    bool const refreshPresent = std::any_of(profile.Spells.begin(),
        profile.Spells.end(), IsSliceRefreshRow);
    if (!refreshPresent)
        if (BotActionProfileSpell const* envenom = FindPinnedEnvenom(profile))
        {
            BotActionProfileSpell const row = SliceRefreshRow(*envenom);
            profile.Spells.push_back(row);
            tag(profile.Spells.back());
            ++changed;
        }
    return changed;
}
}

#endif
