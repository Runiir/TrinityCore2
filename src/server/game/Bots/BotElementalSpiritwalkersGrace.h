#ifndef TRINITY_BOT_ELEMENTAL_SPIRITWALKERS_GRACE_H
#define TRINITY_BOT_ELEMENTAL_SPIRITWALKERS_GRACE_H

#include "Define.h"

#include <algorithm>
#include <string>
#include <string_view>

namespace BotElementalSpiritwalkersGrace
{
constexpr uint32 LavaBurstSpellId = 51505;
constexpr uint32 SpiritwalkersGraceSpellId = 79206;
constexpr std::string_view ElementalSpec = "elemental_shaman";
constexpr std::string_view MovementRejection = "movement_requires_instant_action";

inline bool DeferLavaBurstMovementRejection(std::string const& specTag,
    uint32 spellId, bool rejectedByMovement)
{
    return rejectedByMovement && specTag == ElementalSpec
        && spellId == LavaBurstSpellId;
}

template <typename Candidates>
void EvaluateGraceAfterDamageOpportunities(Candidates& candidates)
{
    std::stable_partition(candidates.begin(), candidates.end(),
        [](auto const& candidate)
        {
            return candidate.SpellId != SpiritwalkersGraceSpellId;
        });
}

template <typename Candidates>
bool HasMovementBlockedLavaBurst(Candidates const& candidates)
{
    for (auto const& candidate : candidates)
        if (candidate.SpellId == LavaBurstSpellId
            && candidate.RejectReason == MovementRejection)
            return true;
    return false;
}
}

#endif
