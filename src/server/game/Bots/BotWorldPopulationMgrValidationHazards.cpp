#include "Bots/BotWorldPopulationMgrValidationHazards.h"

#include "Bots/BotRaidHazardState.h"
#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"
#include "Object.h"

#include <algorithm>
#include <cmath>

namespace
{
float Distance2d(float ax, float ay, float bx, float by)
{
    float const dx = ax - bx;
    float const dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}
}

namespace BotWorldValidationHazards
{
std::vector<Definition> BuildDefinitions(
    uint32 sourceEntry, uint32 detectionSpellId, uint32 damageSpellId,
    std::string const& shape, float radiusYards, float safetyMarginYards)
{
    std::vector<Definition> definitions;
    if (sourceEntry)
        definitions.push_back({ sourceEntry, detectionSpellId, damageSpellId,
            shape, radiusYards, safetyMarginYards });
    return definitions;
}

Definition const* FindDefinition(std::vector<Definition> const& definitions,
    uint32 sourceEntry, uint32 spellId)
{
    for (Definition const& definition : definitions)
        if (definition.SourceEntry == sourceEntry
            && (!spellId || definition.DamageSpellId == spellId
                || definition.DetectionSpellId == spellId))
            return &definition;
    return nullptr;
}

bool IsActive(Player* bot, Creature* hazard, Definition const* definition)
{
    if (!bot || !hazard || !definition || !hazard->IsAlive())
        return false;

    // Most non-attackable radial hazards are persistent ground objects. The
    // Chainwielder marker is dangerous only during its native cast/effect
    // window, despite the summon living longer than that window.
    bool active = definition->Shape == "radial"
        && !bot->IsValidAttackTarget(hazard);
    if (active && definition->SourceEntry == 42690
        && definition->DamageSpellId == 79580)
    {
        TempSummon const* summon = hazard->ToTempSummon();
        SpellInfo const* damageSpell = sSpellMgr->GetSpellInfo(
            definition->DamageSpellId);
        if (!summon || !damageSpell)
            return true;

        uint32 castTimeMs = uint32(std::max<int32>(
            0, damageSpell->CalcCastTime(hazard->getLevel())));
        uint32 effectDurationMs = uint32(std::max<int32>(
            0, damageSpell->GetDuration()));
        active = BotRaidHazard::TimedMarkerDangerActive(
            summon->GetTimer(), summon->GetLifetime(), castTimeMs,
            effectDurationMs);
    }
    if (definition->DetectionSpellId)
        for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL,
            CURRENT_CHANNELED_SPELL })
            if (Spell* spell = hazard->GetCurrentSpell(spellType))
                if (SpellInfo const* spellInfo = spell->GetSpellInfo(); spellInfo
                    && (spellInfo->Id == definition->DetectionSpellId
                        || spellInfo->Id == definition->DamageSpellId))
                    active = true;
    return active;
}

std::vector<Active> FindActive(Player* bot,
    std::vector<Definition> const& definitions, bool requiresMovement)
{
    std::vector<Active> activeHazards;
    if (!bot || !requiresMovement || definitions.empty())
        return activeHazards;

    std::vector<WorldObject*> hazardObjects;
    Trinity::AllWorldObjectsInRange hazardCheck(bot, 35.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange>
        hazardSearcher(bot, hazardObjects, hazardCheck);
    Cell::VisitAllObjects(bot, hazardSearcher, 35.0f);
    for (WorldObject* object : hazardObjects)
    {
        Creature* hazard = object ? object->ToCreature() : nullptr;
        Definition const* definition = FindDefinition(definitions,
            hazard ? hazard->GetEntry() : 0, 0);
        if (!IsActive(bot, hazard, definition))
            continue;

        activeHazards.push_back({ hazard, definition,
            std::max(1.0f, definition->RadiusYards
                + definition->SafetyMarginYards) });
    }
    return activeHazards;
}

bool PositionOutside(Active const& hazard, float x, float y)
{
    if (!hazard.Source || !hazard.HazardDefinition)
        return true;

    bool inside = Distance2d(x, y,
        hazard.Source->GetPositionX(), hazard.Source->GetPositionY())
        <= hazard.SafeRadius;
    if (hazard.HazardDefinition->Shape == "frontal_cone")
    {
        float bearing = std::atan2(
            y - hazard.Source->GetPositionY(),
            x - hazard.Source->GetPositionX());
        float relative = bearing - hazard.Source->GetOrientation();
        while (relative > float(M_PI))
            relative -= float(2.0 * M_PI);
        while (relative < -float(M_PI))
            relative += float(2.0 * M_PI);
        inside = inside && std::fabs(relative) <= float(M_PI_2);
    }
    return !inside;
}

bool PositionsOutside(std::vector<Active> const& hazards, float x, float y)
{
    for (Active const& hazard : hazards)
        if (!PositionOutside(hazard, x, y))
            return false;
    return true;
}

bool PathOutside(Player* bot, std::vector<Active> const& hazards,
    float x, float y, float z)
{
    if (!bot || hazards.empty())
        return true;

    PathGenerator path(bot);
    if (!path.CalculatePath(x, y, z, false))
        return false;
    PathType const pathType = path.GetPathType();
    if ((pathType & PATHFIND_NOPATH)
        || (pathType & PATHFIND_NOT_USING_PATH)
        || (pathType & PATHFIND_INCOMPLETE)
        || (pathType & PATHFIND_SHORTCUT)
        || (pathType & PATHFIND_FARFROMPOLY))
        return false;

    std::vector<float> previousDistances;
    std::vector<bool> startedOutside;
    std::vector<bool> exitedHazards;
    previousDistances.reserve(hazards.size());
    startedOutside.reserve(hazards.size());
    exitedHazards.reserve(hazards.size());
    for (Active const& hazard : hazards)
    {
        previousDistances.push_back(bot->GetExactDist2d(hazard.Source));
        startedOutside.push_back(PositionOutside(hazard,
            bot->GetPositionX(), bot->GetPositionY()));
        exitedHazards.push_back(false);
    }

    bool endpointOutside = false;
    for (G3D::Vector3 const& point : path.GetPath())
    {
        endpointOutside = PositionsOutside(hazards, point.x, point.y);
        for (size_t index = 0; index < hazards.size(); ++index)
        {
            Active const& hazard = hazards[index];
            float distance = Distance2d(point.x, point.y,
                hazard.Source->GetPositionX(), hazard.Source->GetPositionY());
            bool outside = PositionOutside(hazard, point.x, point.y);
            if (startedOutside[index])
            {
                if (!outside)
                    return false;
                continue;
            }

            // The initial path prefix may be contaminated because the bot is
            // already standing in a strike. Require a non-worsening radial
            // exit, then stay outside the exact damage radius.
            if (!exitedHazards[index])
            {
                if (distance + 0.5f < previousDistances[index])
                    return false;
                previousDistances[index] = std::max(previousDistances[index],
                    distance);
                if (distance > hazard.SafeRadius)
                    exitedHazards[index] = true;
            }
            else if (!outside)
                return false;
        }
    }
    return endpointOutside;
}
}
