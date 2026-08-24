#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_ENCOUNTER_HAZARDS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_ENCOUNTER_HAZARDS_H

#include "Bots/BotEncounterBlackboard.h"

class Player;

namespace BotEncounterHazards
{
// Publish hazards visible around every same-map cohort observer. The
// blackboard owns the resulting value objects, so no WorldObject pointer
// survives the refresh.
void Populate(BotEncounter::Blackboard& board,
    std::vector<Player*> const& observers,
    uint64 observedAtMs);
}

#endif
