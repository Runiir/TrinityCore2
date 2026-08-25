#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_COMBAT_RANGE_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_COMBAT_RANGE_H

namespace BotWorldPopulationMgrCombatRange
{
// Only a native hostile self-centered spell gets a profile range envelope.
// Positive self-target actions are cast at the bot and must not reconcile
// combat range against an unrelated hostile target.
constexpr float ResolveSelfCenteredHostileMaxRange(
    bool selfTarget, bool distinctHostileTarget, bool spellIsHostile,
    float configuredMaxRange)
{
    return selfTarget && distinctHostileTarget && spellIsHostile
        && configuredMaxRange > 0.0f ? configuredMaxRange : 0.0f;
}
}

#endif
