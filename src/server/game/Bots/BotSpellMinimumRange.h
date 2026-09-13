#ifndef TRINITY_BOT_SPELL_MINIMUM_RANGE_H
#define TRINITY_BOT_SPELL_MINIMUM_RANGE_H

#include "Spell.h"
#include "SpellInfo.h"
#include "Unit.h"

#include <algorithm>

namespace BotSpellMinimumRange
{
// Match the unit-target minimum in Spell::GetMinMaxRange. Ranged profile
// classification alone does not impose a dead zone on zero-minimum spells.
inline float Effective(Unit const* caster, Unit const* target,
    SpellInfo const* spellInfo, float configuredMinimum)
{
    if (!caster || !target || !spellInfo || !spellInfo->RangeEntry
        || (spellInfo->RangeEntry->Flags & SPELL_RANGE_MELEE))
        return configuredMinimum;

    float nativeMinimum = caster->GetSpellMinRangeForTarget(target, spellInfo);
    if (spellInfo->RangeEntry->Flags & SPELL_RANGE_RANGED)
        nativeMinimum += caster->GetMeleeRange(target);
    else if (nativeMinimum > 0.0f)
        nativeMinimum += caster->GetCombatReach() + target->GetCombatReach();
    return std::max(configuredMinimum, nativeMinimum);
}
}

#endif
