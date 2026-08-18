#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_SPELL_SEMANTICS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_SPELL_SEMANTICS_H

#include "Define.h"

#include <string>

class Player;
class SpellInfo;
class Unit;

namespace BotWorldPopulationMgrSpellSemantics
{
uint64 NowMs();
bool SpellLooksLikeHeal(SpellInfo const* spellInfo);
bool SpellLooksDangerous(SpellInfo const* spellInfo);
bool SpellLooksLikeSummonOrAdds(SpellInfo const* spellInfo);
bool SpellLooksLikeGroundDanger(SpellInfo const* spellInfo);
bool SpellLooksRaidWide(SpellInfo const* spellInfo);
bool SpellLooksTankSpike(SpellInfo const* spellInfo);
uint32 SemanticMechanicKey(char const* eventType, char const* result);
char const* SemanticMechanicFamily(uint32 key);
bool EventLooksSuccessful(char const* eventType, char const* result);
bool EventLooksFailure(char const* eventType, char const* result);
std::string BuildSpellTagJson(SpellInfo const* spellInfo, bool mustInterrupt,
    bool groundDanger, bool tankSpike, bool raidDamage, bool adds);
bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth = 0);
bool HasNearbyProtectedEncounterTarget(Player* owner, Unit const* target);
}

#endif
