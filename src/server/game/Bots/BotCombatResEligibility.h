#ifndef TRINITY_BOT_COMBAT_RES_ELIGIBILITY_H
#define TRINITY_BOT_COMBAT_RES_ELIGIBILITY_H

#include "Bots/BotCanonicalRaidScope.h"

#include <string_view>

// Who may be a native combat-res caster, shared by the reconciler's owner
// list (BotWorldPopulationMgrCombatRes.cpp) and the route group recovery's
// "living combat-res caster" (BotWorldPopulationMgrValidationRouteGroupRecovery.cpp).
//
// A canonical-composition raid never makes a tank the caster (round 4): a
// Feral or Blood tank that turns from its target mid-pull to cast Rebirth or
// Raise Ally drops threat. The group recovery counted every living member with
// a ready combat res, tanks included, so once the Feral tank knew Rebirth
// (round 5) a trash pull that lost its healers kept fighting: the living tank
// suppressed the tactical retreat while the reconciler declined every corpse.
// One rule for both sites closes that gap. Legacy accepted scenarios keep the
// old owner set (BotCanonicalRaidScope.h).
namespace BotCombatResEligibility
{
inline bool RoleMayCast(bool canonicalRaid, std::string_view role)
{
    return !canonicalRaid || role != "tank";
}

// The eligible role first, then the member's native spell probe (a learned,
// active, ready combat res it has the power to cast:
// BotWorldPopulationMgrNativeHelpers::HasReadyNativeCombatRes). The role is
// read only in a canonical raid (GetDungeonRole can fall back to a database
// lookup) and the spell probe only for an eligible role.
template <typename RoleProbe, typename ReadyCombatResProbe>
bool CountsAsLivingCaster(bool canonicalRaid, RoleProbe&& role,
    ReadyCombatResProbe&& hasReadyCombatRes)
{
    if (canonicalRaid && !RoleMayCast(canonicalRaid, role()))
        return false;
    return hasReadyCombatRes();
}
}

#endif
