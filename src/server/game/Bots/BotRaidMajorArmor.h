#ifndef TRINITY_BOT_RAID_MAJOR_ARMOR_H
#define TRINITY_BOT_RAID_MAJOR_ARMOR_H

#include "Bots/BotClassSpecActionProfile.h"

#include <initializer_list>
#include <string>

// Round 5, canonical-composition raids only (BotCanonicalRaidScope.h): keep
// the major armor debuff on the boss. The round 5 buff audit found that no
// canonical action profile applied Faerie Fire, Expose Armor or Sunder Armor,
// so every physical hit on a BWD boss met full armor. The canonical 10N
// roster has one druid in every shard (Balance on Magmaw and Atramedes, the
// Feral tank elsewhere and in the full raid), so the druid owns the upkeep;
// the rogue's Expose Armor (8647) would spend its combo points and is not
// needed while a druid is present.
//
// 4.3.4 DBC facts (data/dbc/enUS, checked by tests/test_raid_major_armor.py):
//   * Faerie Fire 770 (Tree/Moonkin or caster form, 35 yd, no cooldown) and
//     Faerie Fire (Feral) 16857 (Cat/Bear, 30 yd, 6 s cooldown) both trigger
//     91565: 300 s, up to 3 stacks, -4% armor per stack. One cast adds one
//     stack, so full strength (-12%) takes three casts. 91565 has no
//     per-caster stacking attribute, so both druid casts share one aura.
//   * spell_group 1139 (stack rule 3, only the strongest applies) holds the
//     equivalents: Expose Armor 8647 (-12% in one application), Sunder Armor
//     58567, Corrosive Spit 95466 and Tear Armor 95467 (-4% per stack, 3
//     stacks, 30 s).
// The rows are added by BotRaidRotationOverrides::ApplyCanonical and admitted
// by BotWorldPopulationMgrCombatResolverAdmission.cpp through AdmissionRejection:
// boss targets in combat only, only while the debuff (or an equivalent at full
// strength) is missing or about to expire, and never as a range-recovery
// movement. That is three GCDs at the pull and one refresh per 270 s. The
// admission keys on the spell id in raid scope (IsUpkeepSpell), not on the
// Tag: the phase 4 rotation contract keeps mechanic tags descriptive. No
// world-DB profile row casts either spell today.
namespace BotRaidMajorArmor
{
inline constexpr char const* Tag = "raid_major_armor";

inline constexpr uint32 FaerieFireSpellId = 770;
inline constexpr uint32 FaerieFireFeralSpellId = 16857;
inline constexpr uint32 FaerieFireAuraId = 91565;
inline constexpr uint32 ExposeArmorAuraId = 8647;
inline constexpr uint32 SunderArmorAuraId = 58567;
inline constexpr uint32 CorrosiveSpitAuraId = 95466;
inline constexpr uint32 TearArmorAuraId = 95467;
inline constexpr uint8 FullStacks = 3;
// Refresh with 30 s left of the 300 s debuff: several GCDs of margin for a
// bot that is busy with a higher-priority row or an encounter duty.
inline constexpr uint32 RefreshBelowMs = 30000;

inline bool IsUpkeepSpell(uint32 spellId)
{
    return spellId == FaerieFireSpellId || spellId == FaerieFireFeralSpellId;
}

inline constexpr char const* NotBossReason = "major_armor_boss_only";
inline constexpr char const* NotEngagedReason = "major_armor_target_not_engaged";
inline constexpr char const* CoveredReason = "major_armor_debuff_covered";
inline constexpr char const* OutOfRangeReason = "major_armor_out_of_range";

struct Observation
{
    uint8 FaerieFireStacks = 0;
    int32 FaerieFireRemainingMs = 0; // negative: no expiry
    bool ExposeArmor = false;
    uint8 StackingEquivalentStacks = 0; // highest of Sunder, Corrosive Spit, Tear Armor
};

// True when a cast would add armor reduction or save the debuff from expiry.
inline bool Needed(Observation const& observation)
{
    if (observation.ExposeArmor || observation.StackingEquivalentStacks >= FullStacks)
        return false;
    if (observation.FaerieFireStacks < FullStacks)
        return true;
    return observation.FaerieFireRemainingMs >= 0
        && uint32(observation.FaerieFireRemainingMs) < RefreshBelowMs;
}

// TargetT is Unit in the admission; tests pass a fake with the same calls.
template <typename TargetT>
Observation Observe(TargetT const& target)
{
    Observation observation;
    if (auto const* faerieFire = target.GetAura(FaerieFireAuraId))
    {
        observation.FaerieFireStacks = faerieFire->GetStackAmount();
        observation.FaerieFireRemainingMs = faerieFire->GetDuration();
    }
    observation.ExposeArmor = target.GetAura(ExposeArmorAuraId) != nullptr;
    for (uint32 auraId : { SunderArmorAuraId, CorrosiveSpitAuraId, TearArmorAuraId })
        if (auto const* equivalent = target.GetAura(auraId))
            if (equivalent->GetStackAmount() > observation.StackingEquivalentStacks)
                observation.StackingEquivalentStacks = equivalent->GetStackAmount();
    return observation;
}

// Encounter bosses: instance_encounters credit (IsDungeonBoss) or the boss
// type flag (isWorldBoss), as Hunter's Mark decides in persistent setup. In
// BWD every boss and all four Omnotron constructs carry the boss type flag;
// so does Magmaw's Exposed Head, which persists for the whole encounter and
// takes the physical damage of each exposed window.
template <typename TargetT>
bool IsBossTarget(TargetT const* target)
{
    auto const* creature = target ? target->ToCreature() : nullptr;
    return creature && (creature->IsDungeonBoss() || creature->isWorldBoss());
}

// The admission gate for an upkeep spell in raid scope. Returns the reject
// reason, or nullptr to leave the candidate to the ordinary gates. A needed
// cast that BuildCandidates rejected as out_of_range keeps waiting instead of
// becoming the range-recovery action: the upkeep never moves the bot.
template <typename TargetT>
char const* AdmissionRejection(TargetT const* target, std::string const& currentReason)
{
    if (!IsBossTarget(target))
        return NotBossReason;
    if (!target->IsInCombat())
        return NotEngagedReason;
    if (!Needed(Observe(*target)))
        return CoveredReason;
    if (currentReason == "out_of_range")
        return OutOfRangeReason;
    return nullptr;
}

inline bool HasSpellRow(BotClassSpecActionProfile const& profile, uint32 spellId)
{
    for (BotActionProfileSpell const& spell : profile.Spells)
        if (spell.SpellId == spellId)
            return true;
    return false;
}

// The canonical druid's upkeep row, or SpellId 0 for any other profile.
//   * Balance: bucket 1 after the DoTs, Starsurge and Starfall (damage weight
//     0.90 is below their 0.92-1.00) and ahead of Force of Nature (bucket 2)
//     and the Starfire and Wrath nukes (bucket 3). Native 35 yd range.
//   * Feral tank: bucket 1 behind Mangle (0.92 damage, 1.0 threat) and ahead
//     of Lacerate and Pulverize (bucket 2), Bear Form only; there it also
//     deals damage with bonus threat. Native 30 yd range.
inline BotActionProfileSpell UpkeepRow(BotClassSpecActionProfile const& profile)
{
    BotActionProfileSpell spell;
    spell.SpellId = 0;
    if (profile.ClassId != 11)
        return spell;
    if (profile.Role == "dps" && profile.SpecTag == "balance_druid")
    {
        spell.SpellId = FaerieFireSpellId;
        spell.MechanicTags = "faerie_fire,major_armor_debuff";
        spell.DamageWeight = 0.90f;
        spell.SortOrder = 38;
    }
    else if (profile.Role == "tank" && profile.SpecTag == "feral_druid_tank")
    {
        spell.SpellId = FaerieFireFeralSpellId;
        spell.MechanicTags = "faerie_fire_feral,major_armor_debuff,threat";
        spell.DamageWeight = 0.50f;
        spell.ThreatWeight = 1.00f;
        spell.SortOrder = 35;
        // FORM_BEAR, as the Feral tank's other bear rows (phase 8 migration).
        spell.RequiredShapeshiftForm = 5;
    }
    else
        return spell;
    spell.MechanicTags += std::string(",") + Tag;
    spell.Category = BotCombatActionCategory::Debuff;
    spell.PriorityBucket = 1;
    spell.MinEnemies = 1;
    spell.MaxEnemies = 0;
    spell.TargetSelector = "enemy";
    return spell;
}

// Appends the upkeep row once and returns it; nullptr when the profile gets
// none. A profile that already has the spell (a later world-DB row) keeps its
// own row.
inline BotActionProfileSpell* AppendUpkeepRow(BotClassSpecActionProfile& profile)
{
    BotActionProfileSpell spell = UpkeepRow(profile);
    if (!spell.SpellId || HasSpellRow(profile, spell.SpellId))
        return nullptr;
    profile.Spells.push_back(spell);
    return &profile.Spells.back();
}
}

#endif
