#ifndef TRINITY_BOT_COMBAT_DAMAGE_ATTRIBUTION_H
#define TRINITY_BOT_COMBAT_DAMAGE_ATTRIBUTION_H

namespace BotCombatDamageAttribution
{
struct NativeRelationship
{
    bool Self = false;
    bool CohortTarget = false;
    bool AttackerFriendly = false;
    bool VictimFriendly = false;
};

constexpr bool IsFriendlyOrCohortTarget(NativeRelationship const& relationship) noexcept
{
    return relationship.Self
        || relationship.CohortTarget
        || relationship.AttackerFriendly
        || relationship.VictimFriendly;
}
}

#endif
