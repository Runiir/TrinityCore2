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
    // Board-level owner (a single Elemental Shaman in a ten-player snapshot).
    // The runtime adds scenario and admission gates before any cast.
    ObjectGuid BloodlustOwner;
};

MagmawDutyPlan BuildMagmawDutyPlan(Blackboard const& board);
std::string MagmawDutyPlanJson(MagmawDutyPlan const& plan);
// Status field: the plan of a Magmaw encounter snapshot, or
// {"applies":false} for any other snapshot or none.
std::string BuildMagmawDutyPlanStatusJson(Blackboard const* board);
}

#endif
