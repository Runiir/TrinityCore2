#ifndef TRINITY_BOT_RAID_PERSISTENT_BUFFS_H
#define TRINITY_BOT_RAID_PERSISTENT_BUFFS_H

#include "Bots/BotPersistentSelfBuffContract.h"

#include <cstddef>
#include <iterator>
#include <string>
#include <vector>

// Round 5, canonical-composition raids only (BotCanonicalRaidScope.h): raid
// buffs the buff audit credited but no runtime path kept up. Persistent setup
// re-casts a row whenever the caster lacks its aura, so a buff lost to a
// death or a wipe comes back. Outside a canonical raid the contract is the
// unchanged BotPersistentSelfBuffContract table, row for row.
//
// 4.3.4 facts (Spell.dbc, TDB spell_group, spell_gen_increase_stats_buff):
//   * Power Word: Fortitude 21562 is a dummy. Its script casts the raid aura
//     79105 when the target is in the caster's raid and 79104 otherwise; the
//     persistent row casts on the priest itself, and IsInRaidWith(self) is
//     true, so it is always 79105 (79104 stays as the alternate aura). Nothing
//     ever carries 21562, so the readiness row's aura list {21562} never
//     matched and its cast_once latch left the raid without stamina after the
//     first wipe.
//   * Blessing of Kings 20217 (raid aura 79063) and Mark of the Wild 1126
//     (79061) share spell_group 1136 (stack rule 3: only the strongest
//     applies), so with a druid in the group Kings adds nothing. Kings and
//     Blessing of Might 19740 (raid aura 79102: 20% attack power and mana per
//     5 s) share spell_group 1148 (rule 1: one of them per target). With a
//     Mark of the Wild druid the paladins bless Might instead; without one
//     they keep Kings, so the stats category is never left uncovered.
//   * Paladin auras are permanent raid area auras on the paladin (465, 7294)
//     with SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD: they survive death and a wipe,
//     so the row casts once and re-casts only if the aura is otherwise lost
//     (another aura, a cancel). Devotion Aura 465 shares spell_group 1125
//     only with the Stoneskin totem aura 8072, and the canonical shaman never
//     places Stoneskin (Strength of Earth or no earth totem), so the Holy
//     paladin keeps Devotion. Communion's +3% party damage modifies
//     Retribution Aura Overflow 63531 (family flags[2] 0x1000), which no
//     script or spell_linked_spell applies in this core: Retribution Aura
//     7294 gives its damage shield only until the core applies 63531.
namespace BotRaidPersistentBuffs
{
using BotPersistentSelfBuffContract::SelfBuff;

inline constexpr uint32 BlessingOfKings = 20217;
inline constexpr uint32 MarkOfTheWild = 1126;
inline constexpr uint32 PowerWordFortitude = 21562;

inline constexpr SelfBuff BlessingOfMight =
    { CLASS_PALADIN, nullptr, nullptr, 19740, 79102, 79101, "blessing_of_might" };

inline constexpr SelfBuff CanonicalRows[] =
{
    { CLASS_PRIEST, nullptr, nullptr, PowerWordFortitude, 79105, 79104, "power_word_fortitude" },
    { CLASS_PALADIN, "dps", "retribution_paladin", 7294, 7294, 0, "retribution_aura" },
    { CLASS_PALADIN, "healer", "holy_paladin", 465, 465, 0, "devotion_aura" },
};

// The rows a bot of classId follows, from the base table
// (BotPersistentSelfBuffContract::Buffs). The Mark probe runs only for a
// paladin in a canonical raid. A canonical row, and Might, need a spell the
// bot knows (PR_04: known active spells only): a spell the composition does
// not provision is left out rather than logged as a persistent-setup blocker
// on every tick; tests/test_raid_support_runtime.py fails on the missing
// declaration instead.
template <std::size_t Count, typename MarkProbe, typename SpellKnown>
std::vector<SelfBuff> Contract(SelfBuff const (&base)[Count], bool canonicalRaid,
    uint8 classId, MarkProbe&& markOfTheWildInGroup, SpellKnown&& knows)
{
    std::vector<SelfBuff> buffs(std::begin(base), std::end(base));
    if (!canonicalRaid)
        return buffs;
    if (classId == CLASS_PALADIN && knows(BlessingOfMight.SpellId)
        && markOfTheWildInGroup())
        for (SelfBuff& buff : buffs)
            if (buff.SpellId == BlessingOfKings)
                buff = BlessingOfMight;
    for (SelfBuff const& row : CanonicalRows)
        if (row.ClassId == classId && knows(row.SpellId))
            buffs.push_back(row);
    return buffs;
}

// The route readiness party-buff rows this contract replaces in a canonical
// raid: Fortitude (its readiness aura list cannot match) and Kings where Might
// replaces it (a readiness Kings would displace Might through spell_group 1148).
template <typename MarkProbe>
bool ReadinessOwnedByContract(bool canonicalRaid, uint32 spellId,
    MarkProbe&& markOfTheWildInGroup)
{
    if (!canonicalRaid)
        return false;
    if (spellId == PowerWordFortitude)
        return true;
    return spellId == BlessingOfKings && markOfTheWildInGroup();
}

// A raid-wide row is kept for the raid, not only for its caster. Round 5 ran
// its rows on the caster's own aura alone: a member that died and came back
// while the caster lived (a combat res, a slower ghost run) stayed without
// the buff. The characters database saved at the round 5 clears shows both
// Retribution paladins without Fortitude, one also without Mark of the Wild,
// while their casters and the other nine carried them.
inline constexpr uint32 RaidWideRowSpells[] =
    { MarkOfTheWild, BlessingOfKings, 19740, PowerWordFortitude, 1459 };
// The raid auras reach 100 yd around the caster (SpellRadius 12) and need
// line of sight (none ignores it); a member inside 90 yd and in sight is one
// the re-cast certainly reaches.
inline constexpr float RaidCoverageRangeYards = 90.0f;
// A member the aura still cannot reach (a vehicle seat, an immunity) re-opens
// the row at most once per window, never on every tick.
inline constexpr uint64 RaidCoverageRetryMs = 30000;

inline bool IsRaidWideRow(uint32 spellId)
{
    for (uint32 raidWide : RaidWideRowSpells)
        if (raidWide == spellId)
            return true;
    return false;
}

inline bool IsBlessingRow(uint32 spellId)
{
    return spellId == BlessingOfKings || spellId == BlessingOfMight.SpellId;
}

// Blessing coverage has one owner, the lowest-GUID living paladin of the
// group, so two paladins never re-bless the raid for the same member. The
// paladins' own-aura rows are unchanged (each still blesses when it lacks
// the blessing itself).
template <typename PlayerT>
bool OwnsBlessingCoverage(PlayerT* bot)
{
    auto* group = bot->GetGroup();
    if (!group)
        return true;
    for (auto* itr = group->GetFirstMember(); itr; itr = itr->next())
        if (auto* member = itr->GetSource(); member && member != bot
            && member->IsAlive() && member->getClass() == CLASS_PALADIN
            && member->GetGUID() < bot->GetGUID())
            return false;
    return true;
}

// True when the row needs no cast for the raid. Otherwise (false) it opens a
// retry window and lets persistent setup re-cast the row now; the caster's
// own aura check is the caller's. The row holds when:
//   * it is not raid-wide;
//   * the caster is in combat, except Fortitude (health after a combat res):
//     no GCD or mana is spent re-buffing mid-fight otherwise;
//   * it is a blessing and another paladin owns blessing coverage;
//   * every living group member on the caster's map within
//     RaidCoverageRangeYards and in its line of sight carries the aura or its
//     alternate;
//   * its window is still open, or the caster cannot cast it now (casting, on
//     the GCD or cooldown, a form that forbids it: castReadyNow). The window
//     is opened only for a cast that can start on this tick, so a busy caster
//     does not spend it.
template <typename PlayerT, typename RetryMap, typename CastReadyProbe>
bool RaidCoverageHolds(PlayerT* bot, SelfBuff const& buff, RetryMap& retryUntilMs,
    uint64 nowMs, CastReadyProbe&& castReadyNow)
{
    if (!bot || !IsRaidWideRow(buff.SpellId))
        return true;
    if (bot->IsInCombat() && buff.SpellId != PowerWordFortitude)
        return true;
    if (IsBlessingRow(buff.SpellId) && !OwnsBlessingCoverage(bot))
        return true;
    auto* group = bot->GetGroup();
    if (!group)
        return true;
    bool missing = false;
    for (auto* itr = group->GetFirstMember(); itr && !missing; itr = itr->next())
        if (auto* member = itr->GetSource(); member && member != bot
            && member->IsAlive() && member->IsInMap(bot)
            && bot->GetExactDist(member) <= RaidCoverageRangeYards
            && bot->IsWithinLOSInMap(member)
            && !member->HasAura(buff.AuraId)
            && !(buff.AlternateAuraId && member->HasAura(buff.AlternateAuraId)))
            missing = true;
    if (!missing)
        return true;
    auto& retryUntil = retryUntilMs[std::string("raid_buff_coverage:") + std::to_string(buff.SpellId)];
    if (retryUntil > nowMs || !castReadyNow())
        return true;
    retryUntil = nowMs + RaidCoverageRetryMs;
    return false;
}

// Another group member is a druid that knows Mark of the Wild; its own
// persistent row keeps the mark up. Membership only, not life or map: a dead
// druid's mark stays on the raid and the druid re-casts it after a wipe, and
// a released druid running back from BWD's graveyard (outside the instance)
// is still the provider, so the blessing never flips to Kings (which would
// replace Might raid-wide through spell_group 1148) and back.
template <typename PlayerT>
bool GroupHasMarkOfTheWild(PlayerT* bot)
{
    auto* group = bot ? bot->GetGroup() : nullptr;
    if (!group)
        return false;
    for (auto* itr = group->GetFirstMember(); itr; itr = itr->next())
        if (auto* member = itr->GetSource(); member && member != bot
            && member->getClass() == CLASS_DRUID && member->HasSpell(MarkOfTheWild))
            return true;
    return false;
}
}

#endif
