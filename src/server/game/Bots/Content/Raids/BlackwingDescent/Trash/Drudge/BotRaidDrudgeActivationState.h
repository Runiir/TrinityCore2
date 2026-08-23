#ifndef TRINITY_BOT_RAID_DRUDGE_ACTIVATION_STATE_H
#define TRINITY_BOT_RAID_DRUDGE_ACTIVATION_STATE_H

namespace BotRaidDrudgeActivation
{
// This is the shared authority boundary for the exact typed lane profile.  It
// deliberately consumes evidence booleans only: native source target choice,
// movement, timers, spell effects, and geometry remain owned by TrinityCore
// and the typed route.
struct Input
{
    bool ExactRouteProfile = false;
    bool ExactRosterPrepullStaged = false;
    bool BothTankAnchorsAccepted = false;
    bool BothTankVictimsAccepted = false;
    bool SeedProfileActionsAccepted = false;
    bool FirstNativeRushObserved = false;
    bool ExactRosterReseparated = false;
    bool ProfileActionAccepted = false;
};

enum class Blocker
{
    None,
    NotExactRoute,
    ExactRosterPrepull,
    TankAnchors,
    TankVictims,
    SeedProfileActions,
    FirstNativeRush,
    ExactRosterReseparation,
    ProfileAction,
};

struct Result
{
    bool CombatAuthorityAllowed = false;
    Blocker BlockingEvidence = Blocker::ExactRosterPrepull;
};

inline Result Evaluate(Input const& input)
{
    if (!input.ExactRouteProfile)
        return { true, Blocker::NotExactRoute };
    if (!input.ExactRosterPrepullStaged)
        return { false, Blocker::ExactRosterPrepull };
    if (!input.BothTankAnchorsAccepted)
        return { false, Blocker::TankAnchors };
    if (!input.BothTankVictimsAccepted)
        return { false, Blocker::TankVictims };
    if (!input.SeedProfileActionsAccepted)
        return { false, Blocker::SeedProfileActions };
    if (!input.FirstNativeRushObserved)
        return { false, Blocker::FirstNativeRush };
    if (!input.ExactRosterReseparated)
        return { false, Blocker::ExactRosterReseparation };
    if (!input.ProfileActionAccepted)
        return { false, Blocker::ProfileAction };
    return { true, Blocker::None };
}
}

#endif
