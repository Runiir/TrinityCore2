#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace
{
float Distance2d(float leftX, float leftY, float rightX, float rightY)
{
    return std::hypot(leftX - rightX, leftY - rightY);
}

}

bool BotWorldPopulationMgr::IsValidationRoutePatrolCombatPointSafe(
    Unit const* target, float x, float y, float /*z*/) const
{
    if (!target || !target->ToCreature() || !target->GetMap()
        || Cohort().Config.ValidationRouteKind == "boss"
        || Cohort().Config.ValidationRoutePatrolPullPolicy
            != "ranged_patrol_to_anchor"
        || !Cohort().Config.ValidationRoutePatrolCombatAnchor.X
        || !Cohort().Config.ValidationRoutePatrolCombatAnchorToleranceYards
        || !Cohort().Config.ValidationRoutePatrolCombatClearanceYards
        || Party().ValidationRouteManifestIndex
            >= Party().ValidationRouteManifest.size())
        return true;
    ValidationRouteManifestNode const& node = Party().ValidationRouteManifest[
        Party().ValidationRouteManifestIndex];
    if (node.Kind != "trash"
        || target->GetEntry() != Cohort().Config.ValidationRouteTargetEntry)
        return true;

    float const liveClearance =
        Cohort().Config.ValidationRoutePatrolCombatClearanceYards;
    float const homeClearance = std::max(liveClearance,
        Cohort().Config.ValidationRouteClusterRadiusYards
            + Cohort().Config.ValidationRoutePatrolFutureGuardMarginYards);
    if (homeClearance <= 0.0f)
        return true;

    for (size_t routeIndex = Party().ValidationRouteManifestIndex + 1;
        routeIndex < Party().ValidationRouteManifest.size(); ++routeIndex)
    {
        ValidationRouteManifestNode const& futureNode =
            Party().ValidationRouteManifest[routeIndex];
        if (futureNode.Kind != "trash" || !futureNode.TargetSpawnId
            || futureNode.MapId != target->GetMapId())
            continue;

        std::vector<ObjectGuid::LowType> sourceIds = {
            futureNode.TargetSpawnId,
        };
        sourceIds.insert(sourceIds.end(), futureNode.SplitSourceGuids.begin(),
            futureNode.SplitSourceGuids.end());
        std::sort(sourceIds.begin(), sourceIds.end());
        sourceIds.erase(std::unique(sourceIds.begin(), sourceIds.end()),
            sourceIds.end());
        for (ObjectGuid::LowType sourceId : sourceIds)
        {
            CreatureData const* data = sObjectMgr->GetCreatureData(sourceId);
            if (data && data->mapId == target->GetMapId()
                && Distance2d(x, y, data->spawnPoint.GetPositionX(),
                    data->spawnPoint.GetPositionY()) <= homeClearance)
                return false;

            Creature* source = target->GetMap()->GetCreatureBySpawnId(sourceId);
            if (source && source->IsAlive()
                && Distance2d(x, y, source->GetPositionX(),
                    source->GetPositionY()) <= liveClearance)
                return false;
        }
    }
    return true;
}

bool BotWorldPopulationMgr::TryValidationRoutePatrolCombatAnchor(
    WorldBotState& state, Player* bot, Unit* target,
    ResolvedCombatAction const& profileAction)
{
    if (!bot || !target || profileAction.AutoAttackMode == "melee"
        || std::string(GetDungeonRole(bot)) == "tank"
        || !target->ToCreature()
        || Cohort().Config.ValidationRouteKind == "boss"
        || Cohort().Config.ValidationRoutePatrolPullPolicy
            != "ranged_patrol_to_anchor"
        || !Cohort().Config.ValidationRoutePatrolCombatAnchor.X
        || !Cohort().Config.ValidationRoutePatrolCombatAnchorToleranceYards
        || !Cohort().Config.ValidationRoutePatrolCombatClearanceYards
        || Party().ValidationRouteManifestIndex
            >= Party().ValidationRouteManifest.size())
        return false;
    ValidationRouteManifestNode const& node = Party().ValidationRouteManifest[
        Party().ValidationRouteManifestIndex];
    if (node.Kind != "trash"
        || target->GetEntry() != Cohort().Config.ValidationRouteTargetEntry)
        return false;

    ValidationRouteMemberAnchor const& anchor =
        Cohort().Config.ValidationRoutePatrolCombatAnchor;
    if (!IsValidationRoutePatrolCombatPointSafe(target, anchor.X, anchor.Y,
            anchor.Z)
        || !IsValidationRoutePatrolCombatPointSafe(target,
            target->GetPositionX(), target->GetPositionY(),
            target->GetPositionZ()))
        return false;

    if (bot->GetExactDist(anchor.X, anchor.Y, anchor.Z)
        <= Cohort().Config.ValidationRoutePatrolCombatAnchorToleranceYards)
        return false;

    return MoveBotToPoint(state, bot, anchor.X, anchor.Y, anchor.Z, false,
        BotMovementArbitration::Owner::Route,
        BotMovementArbitration::Priority::Route, nullptr, 0.0f,
        "validation_route_patrol_combat_anchor");
}
