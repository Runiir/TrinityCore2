#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDutyPlan.h"

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBaiterRotation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"

#include <optional>
#include <sstream>

namespace BotEncounter
{
// Friend of AdaptiveMagmawStrategy: reads its private selectors without
// copying them. Baiter observation is idempotent per snapshot revision and
// reads only the snapshot, so a status read cannot move the rotation.
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
            MagmawParasitePolicy::ResolveFixedBaiters(board);
        plan.BaitMage = baiters.first;
        plan.BaitHunter = baiters.second;

        std::vector<ObjectGuid> const hookUsers =
            AdaptiveMagmawStrategy::BuildHookUsers(board);
        for (std::size_t index = 0; index < hookUsers.size() && index < 2; ++index)
            plan.HookRiders.push_back(hookUsers[index]);

        for (ActorSnapshot const& member : board.Players)
        {
            if (plan.PullTank.IsEmpty()
                && AdaptiveMagmawStrategy::IsDesignatedPullTank(
                    board, member.Guid, member.Role))
                plan.PullTank = member.Guid;
            if (member.ClassSpec == "balance_druid")
                plan.MushroomOwners.push_back(member.Guid);
        }

        if (std::optional<ObjectGuid> const owner =
                MagmawBloodlust::FindSingleElementalShaman(board))
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

std::string BuildMagmawDutyPlanStatusJson(Blackboard const* board)
{
    if (!board)
        return "{\"applies\":false,\"revision\":0}";
    return MagmawDutyPlanJson(BuildMagmawDutyPlan(*board));
}
}
