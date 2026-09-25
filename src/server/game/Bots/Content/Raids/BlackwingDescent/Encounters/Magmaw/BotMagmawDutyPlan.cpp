#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDutyPlan.h"

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBaiterRotation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDutyCapabilities.h"

#include <algorithm>
#include <optional>
#include <sstream>

namespace BotEncounter
{
// Friend of AdaptiveMagmawStrategy: reads its private selectors without
// copying them. It must never observe the shared baiter rotation: a status
// read sees snapshot revisions no bot observes, so it peeks at a copy and
// hands those baiters to the hook-rider list.
struct MagmawDutyPlanBuilder
{
    static MagmawDutyPlan Build(Blackboard const& board)
    {
        MagmawDutyPlan plan;
        plan.Revision = board.Revision;
        plan.Applies = MagmawBaiterRotation::AppliesTo(board);
        if (!plan.Applies)
            return plan;

        std::pair<ObjectGuid, ObjectGuid> const baiters =
            MagmawBaiterRotationRegistry::PeekBaiters(board);
        plan.BaitMage = baiters.first;
        plan.BaitHunter = baiters.second;

        std::vector<ObjectGuid> const hookUsers =
            AdaptiveMagmawStrategy::BuildHookUsers(board, baiters);
        for (std::size_t index = 0; index < hookUsers.size() && index < 2; ++index)
            plan.HookRiders.push_back(hookUsers[index]);

        std::vector<ObjectGuid> livingTanks;
        for (ActorSnapshot const& member : board.Players)
        {
            if (plan.PullTank.IsEmpty()
                && AdaptiveMagmawStrategy::IsDesignatedPullTank(
                    board, member.Guid, member.Role))
                plan.PullTank = member.Guid;
            if (MagmawDutyCapabilities::IsMushroomCaster(member.ClassSpec))
                plan.MushroomOwners.push_back(member.Guid);
            if (member.Alive && member.Role == "tank")
                livingTanks.push_back(member.Guid);
            if (member.Alive
                && MagmawDutyCapabilities::IsBattleResCaster(member.ClassSpec))
                plan.BattleResCasters.push_back(member.Guid);
        }
        auto byRawGuid = [](ObjectGuid left, ObjectGuid right)
        {
            return left.GetRawValue() < right.GetRawValue();
        };
        std::sort(livingTanks.begin(), livingTanks.end(), byRawGuid);
        std::sort(plan.BattleResCasters.begin(), plan.BattleResCasters.end(),
            byRawGuid);
        for (ObjectGuid tank : livingTanks)
            if (tank != plan.PullTank)
            {
                plan.TankSwapOwner = tank;
                break;
            }

        if (std::optional<ObjectGuid> const owner =
                MagmawBloodlust::FindBloodlustOwner(board))
            plan.BloodlustOwner = *owner;
        return plan;
    }
};

MagmawDutyPlan BuildMagmawDutyPlan(Blackboard const& board)
{
    return MagmawDutyPlanBuilder::Build(board);
}

std::string MagmawDutyPlanJson(MagmawDutyPlan const& plan)
{
    std::ostringstream json;
    json << "{\"applies\":" << (plan.Applies ? "true" : "false")
         << ",\"revision\":" << plan.Revision;
    if (plan.Applies)
    {
        auto list = [&json](char const* key, std::vector<ObjectGuid> const& guids)
        {
            json << ",\"" << key << "\":[";
            for (std::size_t index = 0; index < guids.size(); ++index)
                json << (index ? "," : "") << guids[index].GetCounter();
            json << ']';
        };
        json << ",\"pull_tank\":" << plan.PullTank.GetCounter()
             << ",\"bait_mage\":" << plan.BaitMage.GetCounter()
             << ",\"bait_hunter\":" << plan.BaitHunter.GetCounter();
        list("hook_riders", plan.HookRiders);
        list("mushroom_owners", plan.MushroomOwners);
        json << ",\"bloodlust_owner\":" << plan.BloodlustOwner.GetCounter();
    }
    json << '}';
    return json.str();
}

std::string MagmawDutyPlanCapabilityJson(MagmawDutyPlan const& plan)
{
    std::string json = MagmawDutyPlanJson(plan);
    if (!plan.Applies)
        return json;
    std::ostringstream extra;
    extra << ",\"tank_swap_owner\":" << plan.TankSwapOwner.GetCounter()
          << ",\"battle_res_casters\":[";
    for (std::size_t index = 0; index < plan.BattleResCasters.size(); ++index)
        extra << (index ? "," : "") << plan.BattleResCasters[index].GetCounter();
    extra << ']';
    json.insert(json.size() - 1, extra.str());
    return json;
}

std::string BuildMagmawDutyPlanStatusJson(Blackboard const* board)
{
    if (!board)
        return "{\"applies\":false,\"revision\":0}";
    return MagmawDutyPlanJson(BuildMagmawDutyPlan(*board));
}
}
