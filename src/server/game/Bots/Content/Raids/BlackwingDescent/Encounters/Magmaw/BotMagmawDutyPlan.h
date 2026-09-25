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
    // The second living tank by raw GUID when two or more tanks live: the
    // taunt owner of a two-tank swap (the mechanic contract decides whether
    // one is declared). Empty with one tank, as on the accepted shard.
    ObjectGuid TankSwapOwner;
    // Living members that can cast a combat resurrection (Rebirth, Raise
    // Ally), by raw GUID; the runtime reconciler picks the caster per death.
    std::vector<ObjectGuid> BattleResCasters;
};

MagmawDutyPlan BuildMagmawDutyPlan(Blackboard const& board);
// The status receipt (unchanged field set; kill evidence and play mode read it).
std::string MagmawDutyPlanJson(MagmawDutyPlan const& plan);
// The receipt plus the capability-only duties (tank swap, battle res).
std::string MagmawDutyPlanCapabilityJson(MagmawDutyPlan const& plan);
// Status field: the plan of a Magmaw encounter snapshot, or
// {"applies":false} for any other snapshot or none.
std::string BuildMagmawDutyPlanStatusJson(Blackboard const* board);
}

#endif
