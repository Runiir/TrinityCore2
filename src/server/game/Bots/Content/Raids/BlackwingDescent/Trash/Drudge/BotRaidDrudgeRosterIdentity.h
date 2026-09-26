#ifndef TRINITY_BOT_RAID_DRUDGE_ROSTER_IDENTITY_H
#define TRINITY_BOT_RAID_DRUDGE_ROSTER_IDENTITY_H

#include "Define.h"
#include <algorithm>
#include <array>
#include <string_view>
#include <vector>

// Which roster slot a Drudge-lane member may be (round 10, first BWD 10N
// end-to-end run: every bot of blackwing_descent_10n_full_c0 held offense
// with drudge_lane_roster_slot_identity_mismatch at bwd.magmaw.drudges).
//
// The legacy full-raid scenario (blackwing_descent_10n, roster 30001-30010)
// declares the generated slot ids raid_tank_1 .. raid_dps_5, and its lane
// contract proves each slot by that exact id; its raid_tank_1 is the Balance
// druid, so the id, not the role, is the identity there. Kept unchanged.
//
// A canonical-composition cohort (BotCanonicalRaidScope.h) declares
// "<cohort>:<character_key>" ids (tools/raid_program/raid_shard_plan.py), so
// no id ever matched. There the route row itself names the slots: a lane tank
// slot must hold a tank, a split healer slot a healer, every other slot a
// damage dealer. The contract already proved each healer and seed slot's role;
// this adds the tanks and the remaining damage dealers.
namespace BotRaidDrudgeRosterIdentity
{
inline constexpr std::array<std::string_view, 10> LegacySlotIds = {
    "raid_tank_1", "raid_tank_2", "raid_healer_1", "raid_healer_2",
    "raid_healer_3", "raid_dps_1", "raid_dps_2", "raid_dps_3",
    "raid_dps_4", "raid_dps_5"
};

inline std::string_view ExpectedCanonicalRole(uint32 oneBasedSlot,
    std::vector<uint32> const& laneTankSlots, std::vector<uint32> const& healerSlots)
{
    if (std::find(laneTankSlots.begin(), laneTankSlots.end(), oneBasedSlot) != laneTankSlots.end())
        return "tank";
    if (std::find(healerSlots.begin(), healerSlots.end(), oneBasedSlot) != healerSlots.end())
        return "healer";
    return "dps";
}

inline bool Matches(bool canonicalRaid, uint32 slotIndex, std::string_view rosterSlotId,
    std::string_view role, std::vector<uint32> const& laneTankSlots,
    std::vector<uint32> const& healerSlots)
{
    if (slotIndex >= LegacySlotIds.size())
        return false;
    if (!canonicalRaid)
        return rosterSlotId == LegacySlotIds[slotIndex];
    return !rosterSlotId.empty()
        && role == ExpectedCanonicalRole(slotIndex + 1, laneTankSlots, healerSlots);
}
}

#endif
