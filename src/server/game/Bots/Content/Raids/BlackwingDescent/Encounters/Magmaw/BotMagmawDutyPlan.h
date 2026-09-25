#ifndef TRINITY_BOT_MAGMAW_DUTY_PLAN_H
#define TRINITY_BOT_MAGMAW_DUTY_PLAN_H

#include "ObjectGuid.h"

#include <string>
#include <vector>

namespace BotEncounter
{
struct Blackboard;

// Read-only receipt of who owns each Magmaw duty on one encounter snapshot.
// Every field comes from the live selectors (baiter rotation, hook rider
// list, designated pull tank, Bloodlust owner, mushroom duty), so the plan
// is exactly what the bots act on. Kill evidence keeps it through the
// status JSON; play mode compares against it (docs/bot_raids/human_play_mode.md).
// Owners follow spec capabilities, not roster slots (BotMagmawDutyCapabilities.h),
// so the same plan covers the accepted shard and the canonical composition.
struct MagmawDutyPlan
{
    bool Applies = false;
    uint64 Revision = 0;
    ObjectGuid PullTank;
    ObjectGuid BaitMage;
    ObjectGuid BaitHunter;
    // The two assigned pincer riders, in selector order.
    std::vector<ObjectGuid> HookRiders;
    std::vector<ObjectGuid> MushroomOwners;
    // Board-level owner (a single Elemental Shaman in a ten-player snapshot,
    // else the single DPS shaman, else the single shaman; SelectBloodlustOwner).
    // The runtime adds scenario and admission gates before any cast.
    ObjectGuid BloodlustOwner;
    // No tank-swap or battle-res owner here: the generic runtime owns both
    // (the route mechanic contract's tank swap, the combat-res reconciler),
    // and the status receipt stays byte-identical for the accepted roster.
};

MagmawDutyPlan BuildMagmawDutyPlan(Blackboard const& board);
// The status receipt (unchanged field set; kill evidence and play mode read it).
std::string MagmawDutyPlanJson(MagmawDutyPlan const& plan);
// Status field: the plan of a Magmaw encounter snapshot, or
// {"applies":false} for any other snapshot or none.
std::string BuildMagmawDutyPlanStatusJson(Blackboard const* board);
}

#endif
