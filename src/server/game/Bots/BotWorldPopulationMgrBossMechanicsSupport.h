#ifndef TRINITYCORE_BOT_WORLD_POPULATION_MGR_BOSS_MECHANICS_SUPPORT_H
#define TRINITYCORE_BOT_WORLD_POPULATION_MGR_BOSS_MECHANICS_SUPPORT_H

#include "Define.h"

class Player;
class SpellInfo;
class Unit;

namespace BotWorldBossMechanics
{
uint64 NowMs();
bool IsNativeCombatObserved(Player const* bot, Unit const* target);
float UnitHealthPct(Unit const* unit);
bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo,
    uint8 depth = 0);
}

#endif
