#ifndef TRINITY_BOT_COMBAT_DAMAGE_ATTRIBUTION_H
#define TRINITY_BOT_COMBAT_DAMAGE_ATTRIBUTION_H

#include <cstdint>
#include <vector>

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

// One application of the ticking periodic spell on the damaged unit.
struct PeriodicCasterCandidate
{
    std::uint64_t CasterGuid = 0;
    bool CasterIsPlayer = false;
    // The native tick resolves its caster on the victim's map.  A caster that
    // is still there was passed to the damage callback as the attacker.
    bool CasterOnVictimMap = false;
};

// A periodic aura keeps ticking after its caster died and released: the
// ghost leaves the instance, so the native tick carries no caster unit.  The
// aura still names its caster.  Return that player when exactly one absent
// player cast the ticking spell on the victim; zero when none did or when
// two absent players did, because the tick cannot be told apart.
inline std::uint64_t AbsentPeriodicCaster(
    std::vector<PeriodicCasterCandidate> const& candidates)
{
    std::uint64_t selected = 0;
    for (PeriodicCasterCandidate const& candidate : candidates)
    {
        if (!candidate.CasterGuid || !candidate.CasterIsPlayer
            || candidate.CasterOnVictimMap)
            continue;
        if (selected && selected != candidate.CasterGuid)
            return 0;
        selected = candidate.CasterGuid;
    }
    return selected;
}
}

#endif
