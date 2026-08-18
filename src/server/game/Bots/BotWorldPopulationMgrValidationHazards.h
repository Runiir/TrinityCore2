#ifndef TRINITYCORE_BOT_WORLD_POPULATION_MGR_VALIDATION_HAZARDS_H
#define TRINITYCORE_BOT_WORLD_POPULATION_MGR_VALIDATION_HAZARDS_H

#include "Define.h"

#include <string>
#include <vector>

class Creature;
class Player;

namespace BotWorldValidationHazards
{
struct Definition
{
    uint32 SourceEntry = 0;
    uint32 DetectionSpellId = 0;
    uint32 DamageSpellId = 0;
    std::string Shape;
    float RadiusYards = 0.0f;
    float SafetyMarginYards = 0.0f;
};

struct Active
{
    Creature* Source = nullptr;
    Definition const* HazardDefinition = nullptr;
    float SafeRadius = 0.0f;
};

std::vector<Definition> BuildDefinitions(
    uint32 sourceEntry, uint32 detectionSpellId, uint32 damageSpellId,
    std::string const& shape, float radiusYards, float safetyMarginYards);
Definition const* FindDefinition(std::vector<Definition> const& definitions,
    uint32 sourceEntry, uint32 spellId);
bool IsActive(Player* bot, Creature* hazard, Definition const* definition);
std::vector<Active> FindActive(Player* bot,
    std::vector<Definition> const& definitions, bool requiresMovement);
bool PositionOutside(Active const& hazard, float x, float y);
bool PositionsOutside(std::vector<Active> const& hazards, float x, float y);
bool PathOutside(Player* bot, std::vector<Active> const& hazards,
    float x, float y, float z);
}

#endif
