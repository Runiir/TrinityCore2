#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Map.h"
#include "Player.h"

#include <algorithm>

bool BotWorldPopulationMgr::HasCompletedValidationRouteDrudgeEntrancePull(
    Player const* member) const
{
    auto const& config = Cohort().Config;
    auto const& party = Party();
    if (!member || !member->GetMap()
        || config.ValidationRouteKind != "trash"
        || config.ValidationRouteNodeId != "bwd.magmaw.drudges"
        || config.ValidationRouteMechanicProfile
            != "trash_two_tank_charge_lanes"
        || config.ValidationRouteTargetEntry != 42362
        || config.ValidationRouteSplitSourceGuids.size() != 2
        || std::find(config.ValidationRouteSplitSourceGuids.begin(),
               config.ValidationRouteSplitSourceGuids.end(), 250140)
            == config.ValidationRouteSplitSourceGuids.end()
        || std::find(config.ValidationRouteSplitSourceGuids.begin(),
               config.ValidationRouteSplitSourceGuids.end(), 250141)
            == config.ValidationRouteSplitSourceGuids.end())
        return false;

    if (!party.ValidationRouteDrudgePrepullStaged
        || party.ValidationRouteDrudgePrepullAttemptId != Cohort().AttemptId
        || party.ValidationRouteDrudgePrepullWipeGeneration
            != Cohort().Raid.WipeGeneration
        || party.ValidationRouteDrudgePrepullRouteGeneration
            != party.ValidationRouteGeneration
        || party.ValidationRoutePackGeneration
            != party.ValidationRouteGeneration
        || !party.ValidationRoutePackObservedEngagement
        || party.ValidationRoutePackMemberGuids.size() != 2
        || party.ValidationRoutePackEngagedGuids.size() != 2)
        return false;

    bool sourceA = false;
    bool sourceB = false;
    bool memberInsideDoorwayEnvelope = false;
    for (ObjectGuid const& guid : party.ValidationRoutePackMemberGuids)
    {
        if (!party.ValidationRoutePackEngagedGuids.count(guid)
            || !party.ValidationRoutePackDeathGuids.count(guid))
            return false;
        Creature* source = member->GetMap()->GetCreature(guid);
        if (!source || source->IsAlive() || source->GetEntry() != 42362)
            return false;

        sourceA = sourceA || source->GetSpawnId() == 250140;
        sourceB = sourceB || source->GetSpawnId() == 250141;
        memberInsideDoorwayEnvelope = memberInsideDoorwayEnvelope
            || member->GetExactDist(source) <= 55.0f;
    }
    return sourceA && sourceB && memberInsideDoorwayEnvelope;
}
