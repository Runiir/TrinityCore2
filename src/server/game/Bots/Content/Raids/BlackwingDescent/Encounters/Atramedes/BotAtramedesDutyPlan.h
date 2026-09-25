#ifndef TRINITY_BOT_ATRAMEDES_DUTY_PLAN_H
#define TRINITY_BOT_ATRAMEDES_DUTY_PLAN_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesMobility.h"
#include <array>
#include <cmath>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

// Atramedes duties chosen by capability from the snapshot roster (class
// spec and role), never by fixed roster slot. Every bot derives the same
// plan from the same snapshot, so exactly one bot owns each duty.
namespace BotEncounter::Atramedes
{
inline bool IsTank(ActorSnapshot const& actor)
{
    return actor.Role == "tank";
}

inline bool IsHealer(ActorSnapshot const& actor)
{
    return actor.Role == "healer";
}

inline bool IsMeleeDpsSpec(std::string_view spec)
{
    static constexpr std::array<std::string_view, 10> melee = {
        "arms_warrior", "fury_warrior", "assassination_rogue", "combat_rogue",
        "subtlety_rogue", "retribution_paladin", "enhancement_shaman",
        "feral_druid", "frost_death_knight", "unholy_death_knight" };
    return std::find(melee.begin(), melee.end(), spec) != melee.end();
}

inline bool IsMelee(ActorSnapshot const& actor)
{
    return !IsTank(actor) && !IsHealer(actor) && IsMeleeDpsSpec(actor.ClassSpec);
}

// Gong duty needs a ranged damage dealer that can keep casting from a shield
// 35-60 yd from the boss (spell reach 40 + 1.5 + 20 boss combat reach) and
// move without losing much damage. Lower rank is preferred.
inline int GongRank(ActorSnapshot const& actor)
{
    if (IsTank(actor))
        return -1;
    if (IsHealer(actor))
        return 40;
    if (IsMelee(actor))
        return 50;
    static constexpr std::array<std::string_view, 12> ranged = {
        "beast_mastery_hunter", "marksmanship_hunter", "survival_hunter",
        "fire_mage", "arcane_mage", "frost_mage", "elemental_shaman",
        "balance_druid", "demonology_warlock", "affliction_warlock",
        "destruction_warlock", "shadow_priest" };
    auto itr = std::find(ranged.begin(), ranged.end(), actor.ClassSpec);
    return itr == ranged.end() ? 30 : int(itr - ranged.begin());
}

struct DutyPlan
{
    bool Applies = false;
    ObjectGuid Tank;
    ObjectGuid GongOwner;
    ObjectGuid GongBackup;
    // Third air gonger (user raid experience, 2026-09-25: "the hunter, maybe
    // the mage, and another very fast player"): the most mobile remaining
    // player, melee first at equal capability (they cannot reach the flying
    // boss anyway), then GUID.
    ObjectGuid GongThird;
    // Every roster member in GUID order, dead or alive, so formation and air
    // ring slots do not shift when someone dies.
    std::vector<ObjectGuid> RosterOrder;
    // Ranged damage dealers and healers (excluding the gong owner) in GUID
    // order; ground formation arc slots follow this order.
    std::vector<ObjectGuid> RangedOrder;
};

inline DutyPlan BuildDutyPlan(Blackboard const& board)
{
    DutyPlan plan;
    plan.Applies = board.Route.NodeId == EncounterNode && FindBoss(board);
    std::vector<ActorSnapshot const*> roster;
    for (ActorSnapshot const& player : board.Players)
        roster.push_back(&player);
    std::sort(roster.begin(), roster.end(),
        [](ActorSnapshot const* left, ActorSnapshot const* right)
        {
            return left->Guid < right->Guid;
        });
    for (ActorSnapshot const* player : roster)
        plan.RosterOrder.push_back(player->Guid);

    for (AssignmentLease const& lease : board.Assignments)
        if (lease.Kind == AssignmentKind::Tank && lease.Slot == "main_tank")
            if (ActorSnapshot const* tank = board.FindActor(lease.AssigneeGuid);
                tank && tank->Alive)
                plan.Tank = tank->Guid;
    if (plan.Tank.IsEmpty())
        for (ActorSnapshot const* player : roster)
            if (player->Alive && IsTank(*player))
            {
                plan.Tank = player->Guid;
                break;
            }

    std::vector<ActorSnapshot const*> gongers;
    for (ActorSnapshot const* player : roster)
        if (player->Alive && player->Guid != plan.Tank && GongRank(*player) >= 0)
            gongers.push_back(player);
    std::stable_sort(gongers.begin(), gongers.end(),
        [](ActorSnapshot const* left, ActorSnapshot const* right)
        {
            return GongRank(*left) < GongRank(*right);
        });
    if (!gongers.empty())
        plan.GongOwner = gongers[0]->Guid;
    if (gongers.size() > 1)
        plan.GongBackup = gongers[1]->Guid;

    bool const published = Mobility::AnyPublished(board);
    float bestYards = 0.0f;
    bool bestMelee = false;
    for (ActorSnapshot const* player : roster)
    {
        if (!player->Alive || player->Guid == plan.Tank || IsTank(*player)
            || player->Guid == plan.GongOwner || player->Guid == plan.GongBackup)
            continue;
        float const yards = Mobility::GongCapabilityYards(*player, published);
        bool const melee = IsMelee(*player);
        if (yards <= 0.0f)
            continue;
        if (plan.GongThird.IsEmpty() || yards > bestYards + 0.01f
            || (std::abs(yards - bestYards) <= 0.01f && melee && !bestMelee))
        {
            plan.GongThird = player->Guid;
            bestYards = yards;
            bestMelee = melee;
        }
    }

    for (ActorSnapshot const* player : roster)
        if (player->Guid != plan.Tank && player->Guid != plan.GongOwner
            && !IsTank(*player) && !IsMelee(*player))
            plan.RangedOrder.push_back(player->Guid);
    return plan;
}

inline std::string DutyPlanJson(DutyPlan const& plan)
{
    std::ostringstream json;
    json << "{\"applies\":" << (plan.Applies ? "true" : "false");
    if (plan.Applies)
    {
        json << ",\"tank\":" << plan.Tank.GetCounter()
             << ",\"gong_owner\":" << plan.GongOwner.GetCounter()
             << ",\"gong_backup\":" << plan.GongBackup.GetCounter()
             << ",\"gong_third\":" << plan.GongThird.GetCounter()
             << ",\"ranged_order\":[";
        for (std::size_t index = 0; index < plan.RangedOrder.size(); ++index)
            json << (index ? "," : "") << plan.RangedOrder[index].GetCounter();
        json << ']';
    }
    json << '}';
    return json.str();
}

// Status field: the Atramedes duties of an encounter snapshot, or
// {"applies":false} for any other snapshot or none.
inline std::string BuildAtramedesDutyPlanStatusJson(Blackboard const* board)
{
    if (!board)
        return "{\"applies\":false}";
    return DutyPlanJson(BuildDutyPlan(*board));
}
}

#endif
