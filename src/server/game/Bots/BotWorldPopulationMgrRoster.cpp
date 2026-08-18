#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotMgr.h"

#include "DatabaseEnv.h"
#include "Group.h"
#include "Player.h"

#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

Player* BotWorldPopulationMgr::GetLoadedBot(WorldBotState const& state) const
{
    return sBotMgr->GetLoadedPlayer(state.Guid);
}

Player* BotWorldPopulationMgr::GetBot(WorldBotState const& state) const
{
    Player* bot = GetLoadedBot(state);
    return bot && bot->IsInWorld() ? bot : nullptr;
}

std::vector<BotWorldPopulationMgr::RaidRosterPlanSlot> BotWorldPopulationMgr::BuildRosterPlan() const
{
    std::vector<RaidRosterPlanSlot> plan;
    bool const raidMode = Cohort().Config.AllowRaids;
    if (raidMode)
    {
        uint32 const raidSize = Cohort().Config.RaidSize;
        if (raidSize != 10 && raidSize != 25)
            return plan;

        uint32 const healerCount = raidSize == 10 ? 3 : 6;
        uint32 const dpsCount = raidSize == 10 ? 5 : 17;
        plan.reserve(raidSize);
        for (uint32 index = 0; index < raidSize; ++index)
        {
            RaidRosterPlanSlot slot;
            slot.SlotIndex = index;
            slot.SubGroup = uint8(index / MAXGROUPSIZE);
            if (index < 2)
            {
                slot.Role = "tank";
                slot.RosterSlotId = "raid_tank_" + std::to_string(index + 1);
            }
            else if (index < 2 + healerCount)
            {
                slot.Role = "healer";
                slot.RosterSlotId = "raid_healer_" + std::to_string(index - 1);
            }
            else
            {
                slot.Role = "dps";
                slot.RosterSlotId = "raid_dps_" + std::to_string(index - 1 - healerCount);
            }
            plan.push_back(std::move(slot));
        }
        return plan;
    }

    uint32 const partySize = Cohort().Config.TargetPopulation;
    plan.reserve(partySize);
    for (uint32 index = 0; index < partySize; ++index)
    {
        RaidRosterPlanSlot slot;
        slot.SlotIndex = index;
        if (Cohort().Config.ValidationRouteEnable && partySize == MAXGROUPSIZE)
        {
            if (index == 0)
            {
                slot.Role = "tank";
                slot.RosterSlotId = "party_tank_1";
            }
            else if (index == 1)
            {
                slot.Role = "healer";
                slot.RosterSlotId = "party_healer_1";
            }
            else
            {
                slot.Role = "dps";
                slot.RosterSlotId = "party_dps_" + std::to_string(index - 1);
            }
        }
        else
            slot.RosterSlotId = "party_" + std::to_string(index);
        plan.push_back(std::move(slot));
    }
    return plan;
}

std::string BotWorldPopulationMgr::SelectNextRosterSlot() const
{
    std::vector<RaidRosterPlanSlot> plan = BuildRosterPlan();
    for (RaidRosterPlanSlot const& candidate : plan)
    {
        bool occupied = false;
        for (WorldBotState const& state : Party().Bots)
            if (state.RosterSlotId == candidate.RosterSlotId)
            {
                occupied = true;
                break;
            }
        if (!occupied)
            return candidate.RosterSlotId;
    }
    return {};
}

std::string BotWorldPopulationMgr::GetBotClassSpec(Player const* bot) const
{
    if (!bot)
        return {};

    if (QueryResult result = CharacterDatabase.PQuery("SELECT class_spec FROM character_bot_pool WHERE guid = %u LIMIT 1", bot->GetGUID().GetCounter()))
        return result->Fetch()[0].GetString();

    return {};
}

uint32 BotWorldPopulationMgr::SelectPoolCandidateGuid(std::string const& rosterSlotId,
    std::set<uint32> const* excludedGuids, uint32 expectedGuid,
    std::string const& expectedName, std::string const& expectedClassSpec) const
{
    std::ostringstream query;
    query << "SELECT cbp.guid FROM character_bot_pool cbp INNER JOIN characters c ON c.guid = cbp.guid "
          << "WHERE cbp.enabled = 1 AND cbp.in_use = 0 "
          << "AND c.level BETWEEN " << uint32(Cohort().Config.MinLevel) << " AND " << uint32(Cohort().Config.MaxLevel);
    if (expectedGuid)
    {
        if (expectedName.empty() || expectedClassSpec.empty())
            return 0;
        std::string escapedName = expectedName;
        std::string escapedExpectedSpec = expectedClassSpec;
        CharacterDatabase.EscapeString(escapedName);
        CharacterDatabase.EscapeString(escapedExpectedSpec);
        query << " AND cbp.guid = " << expectedGuid
              << " AND c.name = '" << escapedName << "'"
              << " AND cbp.class_spec = '" << escapedExpectedSpec << "'";
    }
    if (!Cohort().Config.PoolTagFilter.empty())
    {
        std::string escapedTag = Cohort().Config.PoolTagFilter;
        CharacterDatabase.EscapeString(escapedTag);
        query << " AND cbp.experiment_tags = '" << escapedTag << "'";
    }
    std::vector<RaidRosterPlanSlot> const rosterPlan = BuildRosterPlan();
    RaidRosterPlanSlot const* selectedSlot = nullptr;
    for (RaidRosterPlanSlot const& slot : rosterPlan)
        if (slot.RosterSlotId == rosterSlotId)
        {
            selectedSlot = &slot;
            break;
        }

    if (selectedSlot && !selectedSlot->Role.empty())
        query << " AND cbp.role = '" << selectedSlot->Role << "'";

    if (!Cohort().Config.PoolClassSpecFilter.empty())
    {
        if (!selectedSlot || selectedSlot->SlotIndex >= Cohort().Config.PoolClassSpecFilter.size())
            return 0;
        std::string escapedSpec = Cohort().Config.PoolClassSpecFilter[selectedSlot->SlotIndex];
        CharacterDatabase.EscapeString(escapedSpec);
        query << " AND cbp.class_spec = '" << escapedSpec << "'";
    }

    std::set<uint32> rejectedGuids = Cohort().FailedSpawnGuids;
    if (excludedGuids)
        rejectedGuids.insert(excludedGuids->begin(), excludedGuids->end());
    if (!rejectedGuids.empty())
    {
        query << " AND cbp.guid NOT IN (";
        bool first = true;
        for (uint32 guid : rejectedGuids)
        {
            if (!first)
                query << ',';
            query << guid;
            first = false;
        }
        query << ")";
    }

    query << " ORDER BY cbp.guid LIMIT 1";

    if (QueryResult result = CharacterDatabase.Query(query.str().c_str()))
        return result->Fetch()[0].GetUInt32();

    return 0;
}

uint32 BotWorldPopulationMgr::SelectCalibrationPoolCandidateGuid(size_t slot) const
{
    std::string targetSpec = Cohort().CalibrationTargetSpec;
    CharacterDatabase.EscapeString(targetSpec);
    if (slot == 0)
    {
        if (QueryResult result = CharacterDatabase.PQuery(
            "SELECT cbp.guid FROM character_bot_pool cbp INNER JOIN characters c ON c.guid = cbp.guid "
            "WHERE cbp.enabled = 1 AND cbp.in_use = 0 AND c.level = 85 "
            "AND cbp.experiment_tags = 'all_spec_candidate_pool' AND cbp.class_spec = '%s' "
            "ORDER BY cbp.guid LIMIT 1", targetSpec.c_str()))
            return result->Fetch()[0].GetUInt32();
        return 0;
    }

    std::string supportRole;
    if (Cohort().CalibrationMode == "tank_threat_300")
        supportRole = "healer";
    else if (Cohort().CalibrationMode == "healer_controlled_damage_300")
        supportRole = slot == 1 ? "tank" : "dps";
    if (supportRole.empty())
        return 0;

    uint32 targetGuid = Cohort().CalibrationTargetGuid.GetCounter();
    if (QueryResult result = CharacterDatabase.PQuery(
        "SELECT cbp.guid FROM character_bot_pool cbp INNER JOIN characters c ON c.guid = cbp.guid "
        "WHERE cbp.enabled = 1 AND cbp.in_use = 0 AND c.level = 85 "
        "AND cbp.experiment_tags = 'all_spec_candidate_pool' AND cbp.role = '%s' AND cbp.guid <> %u "
        "ORDER BY SHA2(CONCAT(cbp.guid, ':', %u, ':', %u), 256), cbp.guid LIMIT 1",
        supportRole.c_str(), targetGuid, Cohort().CalibrationSeed, uint32(slot)))
        return result->Fetch()[0].GetUInt32();
    return 0;
}

