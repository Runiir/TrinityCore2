#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Map.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <functional>
#include <string>
#include <vector>

bool BotWorldPopulationMgr::CurrentLiveValidationRoutePackCanContinue(
    std::function<bool()> const& persistedValidationRoutePackHasLiveMembers,
    std::function<bool(uint32)> const& isValidationRoutePackEntry,
    std::function<uint32(Creature const*)> const& resolvedScriptedTransitionAuraId)
{
    if (Cohort().Config.ValidationRouteKind == "boss"
        || !Cohort().Raid.RosterComplete || !Cohort().Raid.UniqueLeases
        || !Cohort().Raid.RosterCompositionValid
        || Cohort().Raid.RosterByGuid.size() != Party().Bots.size()
        || !persistedValidationRoutePackHasLiveMembers())
        return false;

    auto frozenRaidRole = [&](WorldBotState const& cohortState, Player const* member) -> std::string
    {
        if (!member || cohortState.Guid.IsEmpty() || cohortState.Guid != member->GetGUID())
            return {};
        auto rosterItr = Cohort().Raid.RosterByGuid.find(cohortState.Guid.GetCounter());
        if (rosterItr == Cohort().Raid.RosterByGuid.end())
            return {};
        RaidRosterSlot const& rosterSlot = rosterItr->second;
        if (rosterSlot.Guid != member->GetGUID() || !rosterSlot.Active || !rosterSlot.LeaseOwned
            || cohortState.RosterSlotId.empty() || rosterSlot.RosterSlotId != cohortState.RosterSlotId
            || !LeaseOwnedByCurrentCohort(cohortState.Guid.GetCounter(), rosterSlot.RosterSlotId))
            return {};
        return rosterSlot.Role;
    };

    auto hasStrictNativePath = [](Player* source, Creature const* target) -> bool
    {
        if (!source || !target || !source->GetMap() || target->GetMap() != source->GetMap())
            return false;

        PathGenerator path(source);
        bool pathOk = path.CalculatePath(target->GetPositionX(), target->GetPositionY(), target->GetPositionZ(), false);
        PathType pathType = path.GetPathType();
        return pathOk
            && !(pathType & PATHFIND_NOPATH)
            && !(pathType & PATHFIND_NOT_USING_PATH)
            && !(pathType & PATHFIND_INCOMPLETE)
            && !(pathType & PATHFIND_SHORTCUT)
            && !(pathType & PATHFIND_FARFROMPOLY);
    };
    auto isSharedValidationCohortCombatLinked = [&](Creature const* creature, Map* map) -> bool
    {
        if (!creature || !map || creature->GetMap() != map)
            return false;

        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (!member || !member->IsInWorld() || member->GetMap() != map)
                continue;
            if (frozenRaidRole(cohortState, member).empty())
                continue;

            auto const& combatReferences = member->GetCombatManager().GetPvECombatRefs();
            auto referenceItr = combatReferences.find(creature->GetGUID());
            if (referenceItr == combatReferences.end())
                continue;
            auto const* combatReference = referenceItr->second;
            if (combatReference && !combatReference->IsSuppressedFor(member) && !combatReference->IsSuppressedFor(creature))
                return true;
        }
        return false;
    };

    std::vector<Player*> livingTanks;
    for (WorldBotState const& cohortState : Party().Bots)
    {
        Player* member = GetLoadedBot(cohortState);
        if (!member || !member->IsInWorld() || !member->IsAlive()
            || !member->GetMap() || !IsValidationCohortMemberInOriginalInstance(cohortState, member)
            || frozenRaidRole(cohortState, member) != "tank")
            continue;
        livingTanks.push_back(member);
    }
    std::sort(livingTanks.begin(), livingTanks.end(), [](Player const* left, Player const* right)
    {
        return left->GetGUID().GetRawValue() < right->GetGUID().GetRawValue();
    });
    if (livingTanks.empty())
        return false;

    std::vector<ObjectGuid> packGuids(Party().ValidationRoutePackMemberGuids.begin(), Party().ValidationRoutePackMemberGuids.end());
    std::sort(packGuids.begin(), packGuids.end(), [](ObjectGuid const& left, ObjectGuid const& right)
    {
        return left.GetRawValue() < right.GetRawValue();
    });

    Player* selectedTank = nullptr;
    Creature* selectedLivePackTarget = nullptr;
    for (Player* tank : livingTanks)
    {
        for (ObjectGuid const& guid : packGuids)
        {
            if (Party().ValidationRoutePackDeathGuids.find(guid) != Party().ValidationRoutePackDeathGuids.end()
                || Party().ValidationRoutePackTransitionGuids.find(guid) != Party().ValidationRoutePackTransitionGuids.end())
                continue;
            Creature* creature = tank->GetMap()->GetCreature(guid);
            if (!creature || !creature->IsAlive() || !creature->GetHealth()
                || !isValidationRoutePackEntry(creature->GetEntry())
                || creature->IsInEvadeMode() || creature->HasUnitState(UNIT_STATE_EVADE)
                || creature->IsDungeonBoss() || creature->isWorldBoss()
                || resolvedScriptedTransitionAuraId(creature)
                || !tank->IsValidAttackTarget(creature)
                || !isSharedValidationCohortCombatLinked(creature, tank->GetMap())
                || !hasStrictNativePath(tank, creature))
                continue;
            selectedTank = tank;
            selectedLivePackTarget = creature;
            break;
        }
        if (selectedTank)
            break;
    }
    if (!selectedTank || !selectedLivePackTarget)
        return false;

    uint32 livingTanksCount = 0;
    uint32 livingHealers = 0;
    uint32 livingDps = 0;
    for (WorldBotState const& cohortState : Party().Bots)
    {
        Player* member = GetLoadedBot(cohortState);
        if (!member || !member->IsInWorld() || !member->IsAlive()
            || member->GetMap() != selectedTank->GetMap()
            || !IsValidationCohortMemberInOriginalInstance(cohortState, member))
            continue;
        std::string role = frozenRaidRole(cohortState, member);
        if (role == "tank")
            ++livingTanksCount;
        else if (role == "healer")
            ++livingHealers;
        else if (role == "dps")
            ++livingDps;
    }
    return livingTanksCount > 0 && livingHealers > 0 && livingDps > 0;
}

