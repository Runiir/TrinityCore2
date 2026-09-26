#ifndef TRINITY_BOT_CANONICAL_RAID_SCOPE_H
#define TRINITY_BOT_CANONICAL_RAID_SCOPE_H

#include <string_view>

// Canonical-composition raid cohorts, the only scope for class fixes that a
// legacy accepted raid scenario would otherwise also see.
//
// tools/raid_program/raid_shard_plan.py names every cohort of a raid
// composition with a copy token: boss shards
// "<raid>_<size><mode>_<boss>_c<copy>_diagnostic" and the full raid
// "<raid>_<size><mode>_full_c<copy>". The legacy accepted Magmaw 10N scenario
// (blackwing_descent_10n_magmaw_diagnostic, roster 30001-30010) and the other
// legacy rows carry no copy token. Its Survival hunter 30009 is the same
// Orc Survival spec the canonical roster now uses, so a Survival fix scoped to
// "any raid" would change that accepted result; scoped here it cannot.
namespace BotCanonicalRaidScope
{
inline bool IsCopyToken(std::string_view token)
{
    if (token.size() < 2 || token.front() != 'c')
        return false;
    for (char character : token.substr(1))
        if (character < '0' || character > '9')
            return false;
    return true;
}

inline bool IsCanonicalCompositionScenario(std::string_view scenarioId)
{
    constexpr std::string_view DiagnosticSuffix = "_diagnostic";
    if (scenarioId.size() > DiagnosticSuffix.size()
        && scenarioId.substr(scenarioId.size() - DiagnosticSuffix.size()) == DiagnosticSuffix)
        scenarioId.remove_suffix(DiagnosticSuffix.size());
    std::string_view::size_type const cut = scenarioId.rfind('_');
    return cut != std::string_view::npos && IsCopyToken(scenarioId.substr(cut + 1));
}
}

#endif
