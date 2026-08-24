#ifndef TRINITY_BOT_RAID_DRUDGE_MOVEMENT_LEASE_H
#define TRINITY_BOT_RAID_DRUDGE_MOVEMENT_LEASE_H

#include "Bots/BotMovementArbiter.h"

namespace BotRaidDrudgeMovement
{
// A landed Rush invalidates the old point approach, but only the Drudge
// mechanic lease in the current route scope may be released. Returning the
// transition result makes the edge one-shot for each observed charge.
inline bool ReleaseInvalidatedMechanicLease(
    BotMovementArbitration::Lease& lease,
    BotMovementArbitration::Scope const& scope)
{
    if (lease.MovementOwner != BotMovementArbitration::Owner::Mechanic
        || lease.MovementPriority != BotMovementArbitration::Priority::Mechanic
        || !BotMovementArbitration::SameScope(lease.MovementScope, scope))
        return false;

    BotMovementArbitration::Clear(lease);
    return true;
}
}

#endif
