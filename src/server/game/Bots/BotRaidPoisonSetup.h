#ifndef TRINITY_BOT_RAID_POISON_SETUP_H
#define TRINITY_BOT_RAID_POISON_SETUP_H

#include "Group.h"
#include "Map.h"
#include "Player.h"

// Raid rogue poisons (round 3). The raid roster carries Deadly Poison 43233
// (main hand) and Instant Poison 43231 (off hand); r02-b1 rogues never
// applied them. Outside calibration the setup is best effort:
//   * it may start only while the whole group rests: the rogue and every
//     group member on its map out of combat, nothing attacking the rogue and
//     no engaged target. That is the readiness barrier or the prepull staging
//     gate, never the first action of a pull (a 3 s item cast would suppress
//     the rotation);
//   * a hand with no weapon, no stack or no spell contract is skipped, and
//     one native attempt per hand is made per rest window (WindowSpent), so
//     setup never holds forever. Leaving the rest window resets the receipts.
// Calibration keeps its fail-closed receipt contract unchanged.
namespace BotRaidPoisonSetup
{
inline constexpr uint32 DeadlyPoisonItem = 43233;
inline constexpr uint32 InstantPoisonItem = 43231;
inline constexpr uint64 WindowSpent = ~uint64(0);

inline bool GroupAtRest(Player* bot, Unit const* target)
{
    if (!bot || bot->IsInCombat() || !bot->getAttackers().empty()
        || (target && target->IsInCombat()))
        return false;
    if (Group* group = bot->GetGroup())
        for (GroupReference* itr = group->GetFirstMember(); itr; itr = itr->next())
            if (Player* member = itr->GetSource();
                member && member->IsInMap(bot) && member->IsInCombat())
                return false;
    return true;
}

inline bool InRaidMap(Player const* bot)
{
    return bot && bot->GetMap() && bot->GetMap()->IsRaid();
}

inline bool HasAnyStack(Player const* bot)
{
    return bot && (bot->GetItemCount(DeadlyPoisonItem) > 0
        || bot->GetItemCount(InstantPoisonItem) > 0);
}
}

#endif
