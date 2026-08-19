#ifndef TRINITY_BOT_ADAPTIVE_DRUDGE_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_DRUDGE_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <string_view>
#include <vector>

namespace BotEncounter
{
struct AdaptiveDrudgePlan
{
    bool OwnsNode = false;
    ObjectGuid DamageTarget;
    ObjectGuid TankTarget;
    std::optional<BotNativeAction::Candidate> Movement;
};

class AdaptiveDrudgeStrategy
{
public:
    static constexpr uint32 DrudgeEntry = 42362;

    AdaptiveDrudgePlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
    {
        AdaptiveDrudgePlan plan;
        if (board.Route.MechanicProfile != "trash_two_tank_charge_lanes")
            return plan;

        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return plan;

        std::vector<ActorSnapshot const*> sources;
        for (ActorSnapshot const& hostile : board.Hostiles)
            if (hostile.Entry == DrudgeEntry && hostile.Alive)
                sources.push_back(&hostile);
        std::sort(sources.begin(), sources.end(), [](ActorSnapshot const* left,
            ActorSnapshot const* right)
        {
            return left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });
        if (sources.empty())
            return plan;

        plan.OwnsNode = true;
        ActorSnapshot const* assigned = nullptr;
        if (role == "tank")
        {
            std::vector<ObjectGuid> tanks;
            for (ActorSnapshot const& player : board.Players)
                if (player.Alive && player.Role == "tank")
                    tanks.push_back(player.Guid);
            std::sort(tanks.begin(), tanks.end(), [](ObjectGuid left, ObjectGuid right)
            {
                return left.GetRawValue() < right.GetRawValue();
            });
            auto tank = std::find(tanks.begin(), tanks.end(), botGuid);
            size_t const tankIndex = tank == tanks.end()
                ? size_t(botGuid.GetCounter()) % sources.size()
                : size_t(std::distance(tanks.begin(), tank)) % sources.size();
            assigned = sources[tankIndex];
            plan.TankTarget = assigned->Guid;
            plan.DamageTarget = assigned->Guid;
        }
        else
        {
            // Ordinary trained damage balances the pair without globally
            // freezing a lane. Attack the healthier add; deterministic ties
            // distribute players across both sources.
            assigned = *std::max_element(sources.begin(), sources.end(),
                [botGuid](ActorSnapshot const* left, ActorSnapshot const* right)
            {
                if (left->HealthPct != right->HealthPct)
                    return left->HealthPct < right->HealthPct;
                bool const chooseLeft = botGuid.GetCounter() % 2 == 0;
                return chooseLeft
                    ? left->Guid.GetRawValue() > right->Guid.GetRawValue()
                    : left->Guid.GetRawValue() < right->Guid.GetRawValue();
            });
            plan.DamageTarget = assigned->Guid;
        }

        float const minimumDistance = std::max(8.0f,
            board.Route.MinimumDistance > 0.0f
                ? board.Route.MinimumDistance : 15.0f);
        ActorSnapshot const* nearest = nullptr;
        float nearestDistance = 0.0f;
        for (ActorSnapshot const* source : sources)
        {
            float const dx = bot->Position.X - source->Position.X;
            float const dy = bot->Position.Y - source->Position.Y;
            float const distance = std::sqrt(dx * dx + dy * dy);
            if (!nearest || distance < nearestDistance)
            {
                nearest = source;
                nearestDistance = distance;
            }
        }

        Vector3 endpoint = bot->Position;
        bool movementRequired = false;
        std::string mechanic = "source_proximity";
        if (nearest && nearestDistance < minimumDistance)
        {
            float dx = bot->Position.X - nearest->Position.X;
            float dy = bot->Position.Y - nearest->Position.Y;
            float length = std::sqrt(dx * dx + dy * dy);
            if (length < 0.01f)
            {
                dx = botGuid.GetCounter() % 2 ? 1.0f : -1.0f;
                dy = botGuid.GetCounter() % 4 < 2 ? 1.0f : -1.0f;
                length = std::sqrt(2.0f);
            }
            float const travel = minimumDistance + 2.0f - nearestDistance;
            endpoint.X += dx / length * travel;
            endpoint.Y += dy / length * travel;
            movementRequired = true;
        }
        else if (role == "tank" && assigned && sources.size() == 2)
        {
            ActorSnapshot const* other = sources[0] == assigned ? sources[1] : sources[0];
            float const sx = assigned->Position.X - other->Position.X;
            float const sy = assigned->Position.Y - other->Position.Y;
            float const sourceDistance = std::sqrt(sx * sx + sy * sy);
            if (sourceDistance < minimumDistance + 2.0f && sourceDistance > 0.01f)
            {
                endpoint.X = assigned->Position.X + sx / sourceDistance * 10.0f;
                endpoint.Y = assigned->Position.Y + sy / sourceDistance * 10.0f;
                endpoint.Z = assigned->Position.Z;
                movementRequired = true;
                mechanic = "tank_pull_apart";
            }
        }

        if (movementRequired)
        {
            BotNativeAction::Candidate candidate;
            candidate.Id.ScopeKey = board.CurrentScope.CohortId + ":"
                + std::to_string(board.CurrentScope.AttemptId) + ":"
                + std::to_string(board.CurrentScope.WipeGeneration) + ":"
                + std::to_string(board.CurrentScope.RouteGeneration) + ":"
                + board.CurrentScope.NodeId;
            candidate.Id.Strategy = "adaptive_drudge";
            candidate.Id.Mechanic = mechanic;
            candidate.Id.Actor = nearest ? nearest->Guid : assigned->Guid;
            candidate.Id.EventGeneration = board.Revision;
            candidate.ActionPriority = BotActionArbitration::Priority::Survival;
            candidate.Utility = 8.0f;
            candidate.ExpiresAtMs = board.ObservedAtMs + 750;
            candidate.Action = BotNativeAction::Move{
                endpoint.X, endpoint.Y, endpoint.Z };
            plan.Movement = std::move(candidate);
        }
        return plan;
    }
};
}

#endif
