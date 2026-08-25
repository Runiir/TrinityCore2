#ifndef TRINITY_BOT_RAID_DRUDGE_OWNERSHIP_ACTION_STATE_H
#define TRINITY_BOT_RAID_DRUDGE_OWNERSHIP_ACTION_STATE_H

namespace BotRaidDrudgeOwnership
{
inline bool NativeOwnershipActionReady(bool chargePending,
    bool recoveryAnchorsReached, bool earlyPullRecovery,
    bool crossLaneSeedComplete)
{
    return (earlyPullRecovery && !crossLaneSeedComplete)
        || (chargePending && recoveryAnchorsReached);
}
}

#endif
