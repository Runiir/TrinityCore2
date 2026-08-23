#ifndef TRINITY_BOT_ROUTE_COMBAT_TARGET_POLICY_H
#define TRINITY_BOT_ROUTE_COMBAT_TARGET_POLICY_H

#include <cstdint>

namespace BotRouteCombatTargetPolicy
{
// A live encounter target may not have normal world progression signals such
// as XP or loot.  Route ownership can admit only the declared native entry,
// and only after the caller has established ordinary unit validity.
inline bool IsOwnedNativeEncounterTarget(
    bool routeOwnsNode, bool targetAlive, bool targetAttackable,
    bool sameMap, bool sameInstance, std::uint32_t targetEntry,
    std::uint32_t declaredEntry)
{
    return routeOwnsNode && targetAlive && targetAttackable
        && sameMap && sameInstance && targetEntry != 0
        && targetEntry == declaredEntry;
}
}

#endif
