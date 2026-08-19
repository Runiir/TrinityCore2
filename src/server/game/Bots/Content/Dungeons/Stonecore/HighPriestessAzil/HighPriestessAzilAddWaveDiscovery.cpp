#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveDiscovery.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"
#include "WorldObject.h"

#include <algorithm>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

AddWaveDiscoveryResult Context::Run(
    AddWaveDiscoveryRequest const& request)
{
    AddWaveDiscoveryResult result;
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;

    Unit*& add = result.Add;
    bool& sharedFocusValid = result.SharedFocusValid;
    uint32& addCount = result.AddCount;
    uint32& engagedAddCount = result.EngagedAddCount;
    uint32& nearbyAddCount = result.NearbyAddCount;
    float& addX = result.AddX;
    float& addY = result.AddY;
    std::vector<Creature*>& localAdds = result.LocalAdds;
    GuidSet& cohortAddGuids = result.CohortAddGuids;

    auto isUsableListedAdd = [manager = request.Manager](Player* observer,
        Unit* candidate) -> bool
    {
        Creature* creature = candidate ? candidate->ToCreature() : nullptr;
        return observer && creature && creature->IsAlive() && creature->GetHealth()
            && creature->GetMap() == observer->GetMap()
            && std::find(manager->Cohort().Config.ValidationRouteAddTargetEntries.begin(), manager->Cohort().Config.ValidationRouteAddTargetEntries.end(), creature->GetEntry()) != manager->Cohort().Config.ValidationRouteAddTargetEntries.end()
            && observer->IsValidAttackTarget(creature);
    };
    result.IsUsableListedAdd = isUsableListedAdd;
    auto isUsableUnexpectedPartyHostile = [manager = request.Manager](
        Player* observer, Unit* candidate) -> bool
    {
        Creature* creature = candidate ? candidate->ToCreature() : nullptr;
        if (!observer || !creature || !creature->IsAlive() || !creature->GetHealth()
            || creature->GetMap() != observer->GetMap()
            || !observer->IsValidAttackTarget(creature))
            return false;

        uint32 entry = creature->GetEntry();
        if (entry == manager->Cohort().Config.ValidationRouteTargetEntry
            || std::find(manager->Cohort().Config.ValidationRouteAlternateTargetEntries.begin(),
                manager->Cohort().Config.ValidationRouteAlternateTargetEntries.end(), entry)
                != manager->Cohort().Config.ValidationRouteAlternateTargetEntries.end()
            || std::find(manager->Cohort().Config.ValidationRoutePackTargetEntries.begin(),
                manager->Cohort().Config.ValidationRoutePackTargetEntries.end(), entry)
                != manager->Cohort().Config.ValidationRoutePackTargetEntries.end())
            return false;

        Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr;
        return victim && (observer->GetGroup()
            ? victim->GetGroup() == observer->GetGroup()
            : victim == observer);
    };
    if (manager.Party().ValidationRouteAddFocusGeneration
        != manager.Party().ValidationRouteGeneration)
    {
        manager.Party().ValidationRouteAddFocusGuid.Clear();
        manager.Party().ValidationRouteAddFocusGeneration = 0;
    }
    if (!manager.Party().ValidationRouteAddFocusGuid.IsEmpty())
    {
        add = ObjectAccessor::GetUnit(*bot,
            manager.Party().ValidationRouteAddFocusGuid);
        if (!add)
        {
            manager.Party().ValidationRouteAddFocusGuid.Clear();
        }
        else if (!add->IsAlive() || !add->GetHealth())
        {
            std::string raw = manager.BuildRawJson(bot, add);
            std::string semantic = manager.BuildSemanticJson(
                bot, add, "dungeon_boss", &power,
                request.Stage, request.Activity);
            manager.RecordEvent(state, bot, "boss_add_killed", add,
                "observed_dead", raw.c_str(), semantic.c_str());
            manager.Party().ValidationRouteAddFocusGuid.Clear();
            add = nullptr;
        }
        else if (!isUsableListedAdd(bot, add))
        {
            manager.Party().ValidationRouteAddFocusGuid.Clear();
            add = nullptr;
        }
        else
            sharedFocusValid = true;
    }

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 45.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(
        bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 45.0f);
    uint8 bestPriority = 0;
    float bestHealthPct = 1.0f;
    uint32 bestGuid = 0;
    auto considerLocalAdd = [&](Creature* creature)
    {
        cohortAddGuids.insert(creature->GetGUID());
        localAdds.push_back(creature);
        ++addCount;
        if (creature->GetVictim())
            ++engagedAddCount;
        addX += creature->GetPositionX();
        addY += creature->GetPositionY();
        if (bot->GetExactDist2d(creature) <= 12.0f)
            ++nearbyAddCount;
        if (sharedFocusValid)
            return;
        uint8 priority = 1;
        if (Player* victim = creature->GetVictim() ? creature->GetVictim()->ToPlayer() : nullptr)
        {
            std::string victimRole = manager.GetDungeonRole(victim);
            priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 2 : 1);
        }
        float healthPct = UnitHealthPct(creature);
        uint32 guid = creature->GetGUID().GetCounter();
        if (!add
            || priority > bestPriority
            || (priority == bestPriority && healthPct < bestHealthPct)
            || (priority == bestPriority && healthPct == bestHealthPct && guid < bestGuid))
        {
            add = creature;
            bestPriority = priority;
            bestHealthPct = healthPct;
            bestGuid = guid;
        }
    };
    std::vector<Creature*> unexpectedPartyHostiles;
    for (WorldObject* object : objects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        bool listedAdd = isUsableListedAdd(bot, creature);
        bool unexpectedPartyHostile = !listedAdd
            && isUsableUnexpectedPartyHostile(bot, creature);
        if ((!listedAdd && !unexpectedPartyHostile)
            || !bot->IsWithinLOSInMap(creature))
            continue;
        if (unexpectedPartyHostile)
        {
            unexpectedPartyHostiles.push_back(creature);
            continue;
        }
        considerLocalAdd(creature);
    }
    // The authoritative retention audit includes every hostile creature
    // attacking this exact party. Admit a real unexpected swarm here, while
    // ordinary route targets remain owned by the route-pack logic.
    //
    // Rerun211's final generation retained one Stonecore Bruiser beside the
    // tank and healer after three Azil recoveries. The shared density phase
    // was still active, but the three-hostile admission floor discarded that
    // exact healer attacker. It therefore remained visible to the strict
    // threat audit while the add handler returned no_compatible_density_anchor
    // and never exposed it to the Warrior's native Taunt. During an already
    // active generation-scoped density recovery, admit every real party-
    // targeting unexpected hostile; initial natural overlap still requires
    // the unchanged three-hostile proof.
    bool sharedDensityRecoveryActive =
        manager.Party().ValidationRouteBossAddDensityPhase
        && manager.Party().ValidationRouteBossAddDensityGeneration
            == manager.Party().ValidationRouteGeneration;
    if (unexpectedPartyHostiles.size() >= 3
        || sharedDensityRecoveryActive)
        for (Creature* creature : unexpectedPartyHostiles)
            considerLocalAdd(creature);
    if (manager.Party().ValidationRouteBossAddDensityPhase && addCount < 3)
    {
        for (BotWorldPopulationMgrBotState::WorldBotState const& cohortState
            : manager.Party().Bots)
        {
            Player* observer = manager.GetLoadedBot(cohortState);
            if (!observer || !observer->IsAlive() || observer->GetMap() != bot->GetMap())
                continue;

            std::vector<WorldObject*> cohortObjects;
            Trinity::AllWorldObjectsInRange cohortCheck(observer, 45.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> cohortSearcher(
                observer, cohortObjects, cohortCheck);
            Cell::VisitAllObjects(observer, cohortSearcher, 45.0f);
            for (WorldObject* object : cohortObjects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (isUsableListedAdd(observer, creature)
                    && observer->IsWithinLOSInMap(creature))
                    cohortAddGuids.insert(creature->GetGUID());
            }
            if (cohortAddGuids.size() >= 3)
                break;
        }
    }
    result.CohortSwarmActive = cohortAddGuids.size() >= 3;
    return result;
}

AddWaveDiscoveryResult DiscoverAddWave(AddWaveDiscoveryRequest const& request)
{
    return Context::Run(request);
}
}
