#ifndef TRINITY_BOT_MAGMAW_SUPPORT_TARGET_OPPORTUNITY_H
#define TRINITY_BOT_MAGMAW_SUPPORT_TARGET_OPPORTUNITY_H

#include "ObjectGuid.h"
#include <algorithm>
#include <cmath>
#include <vector>

namespace BotEncounter
{
struct MagmawStaticDamageRange
{
    float Minimum = 0.0f;
    float Maximum = 0.0f;
};

struct MagmawSupportTargetOpportunities
{
    std::vector<ObjectGuid> Targets;

    bool Contains(ObjectGuid guid) const
    {
        return std::find(Targets.begin(), Targets.end(), guid) != Targets.end();
    }

    void Admit(ObjectGuid guid)
    {
        if (!guid.IsEmpty() && !Contains(guid))
            Targets.push_back(guid);
    }
};

// Observe only stable actor/target geometry here. Cooldowns, the GCD, power,
// auras, and cast-time state remain owned by the ordinary action resolver.
template<class Actor, class Target>
bool ObserveMagmawStaticDamageOpportunity(Actor const* actor,
    Target const* target, std::vector<MagmawStaticDamageRange> const& ranges)
{
    if (!actor || !target || !target->IsInWorld() || !target->IsAlive()
        || actor->GetMap() != target->GetMap()
        || actor->GetInstanceId() != target->GetInstanceId()
        || !actor->IsValidAttackTarget(target)
        || !actor->IsWithinLOSInMap(target))
        return false;

    float const distance = actor->GetExactDist(target);
    if (!std::isfinite(distance))
        return false;
    return std::any_of(ranges.begin(), ranges.end(), [distance](
        MagmawStaticDamageRange const& range)
    {
        return std::isfinite(range.Minimum) && std::isfinite(range.Maximum)
            && range.Minimum >= 0.0f && range.Maximum > range.Minimum
            && distance >= range.Minimum && distance <= range.Maximum;
    });
}
}

#endif
