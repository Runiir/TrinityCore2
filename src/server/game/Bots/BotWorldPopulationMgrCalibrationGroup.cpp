#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotMgr.h"
#include "Group.h"
#include "GroupMgr.h"
#include "LFG.h"
#include "Log.h"

#include <limits>
#include <map>
#include <string>
#include <vector>

void BotWorldPopulationMgr::EnsureCalibrationCohortGroup()
{
    std::vector<Player*> members;
    members.reserve(Party().CalibrationBots.size());
    for (WorldBotState const& state : Party().CalibrationBots)
    {
        Player* bot = GetLoadedBot(state);
        if (bot && bot->IsInWorld())
            members.push_back(bot);
    }
    if (members.empty())
        return;

    std::vector<RaidRosterPlanSlot> const rosterPlan = BuildRosterPlan();
    bool const configuredRaid = Cohort().Config.AllowRaids;
    if (configuredRaid && (rosterPlan.empty() || Cohort().Config.TargetPopulation != rosterPlan.size()))
    {
        Cohort().LastPopulationFailureReason = "exact_raid_roster_plan_unavailable";
        return;
    }

    std::map<std::string, uint32> rosterOrder;
    for (RaidRosterPlanSlot const& slot : rosterPlan)
        rosterOrder.emplace(slot.RosterSlotId, slot.SlotIndex);
    std::stable_sort(members.begin(), members.end(), [this, &rosterOrder](Player const* left, Player const* right)
    {
        auto slotIndex = [this, &rosterOrder](Player const* member) -> uint32
        {
            for (WorldBotState const& state : Party().Bots)
                if (state.Guid == member->GetGUID())
                {
                    auto itr = rosterOrder.find(state.RosterSlotId);
                    return itr == rosterOrder.end() ? std::numeric_limits<uint32>::max() : itr->second;
                }
            return std::numeric_limits<uint32>::max();
        };
        return slotIndex(left) < slotIndex(right);
    });

    Player* leader = members.front();
    Group* group = leader->GetGroup();
    if (!group)
    {
        group = new Group();
        if (!group->Create(leader))
        {
            delete group;
            return;
        }
        sGroupMgr->AddGroup(group);
        TC_LOG_INFO("server", "BotWorld calibration group created leader=%s group=%s",
            leader->GetGUID().ToString().c_str(), group->GetGUID().ToString().c_str());
    }

    for (Player* bot : members)
    {
        if (!bot || bot == leader)
            continue;
        if (!bot->GetGroup() && !group->AddMember(bot))
        {
            TC_LOG_ERROR("server", "BotWorld calibration group add failed leader=%s bot=%s",
                leader->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str());
            continue;
        }
        if (bot->GetGroup() != group)
            continue;

        std::string role = sBotMgr->GetBotRoleName(bot->GetGUID());
        group->SetLfgRoles(bot->GetGUID(), role == "tank" ? lfg::PLAYER_ROLE_TANK
            : (role == "healer" ? lfg::PLAYER_ROLE_HEALER : lfg::PLAYER_ROLE_DAMAGE));
    }
}

