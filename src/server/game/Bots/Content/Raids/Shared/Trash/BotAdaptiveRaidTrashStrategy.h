#ifndef TRINITY_BOT_ADAPTIVE_RAID_TRASH_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_RAID_TRASH_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include <cmath>
#include <optional>

namespace BotEncounter
{
class AdaptiveRaidTrashStrategy
{
public:
    std::optional<BotNativeAction::Candidate> ProposeHazardExit(
        Blackboard const& board, ObjectGuid botGuid) const
    {
        if (board.Route.HazardSourceEntry == 0 || board.Route.HazardRadius <= 0.0f)
            return std::nullopt;

        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return std::nullopt;

        ActorSnapshot const* hazard = nullptr;
        auto inspect = [&](std::vector<ActorSnapshot> const& actors)
        {
            for (ActorSnapshot const& actor : actors)
            {
                if (!actor.Alive || actor.Entry != board.Route.HazardSourceEntry)
                    continue;
                if (board.Route.HazardDetectionSpellId && actor.Cast
                    && actor.Cast->SpellId != board.Route.HazardDetectionSpellId)
                    continue;
                hazard = &actor;
                return true;
            }
            return false;
        };
        if (!inspect(board.Hostiles))
            inspect(board.Summons);
        if (!hazard)
            return std::nullopt;

        float const dx = bot->Position.X - hazard->Position.X;
        float const dy = bot->Position.Y - hazard->Position.Y;
        float const distance = std::sqrt(dx * dx + dy * dy);
        float const unsafeRadius = board.Route.HazardRadius + board.Route.HazardSafetyMargin;
        if (distance > unsafeRadius)
            return std::nullopt;

        float nx = distance > 0.01f ? dx / distance : std::cos(bot->Facing);
        float ny = distance > 0.01f ? dy / distance : std::sin(bot->Facing);
        float const exitRadius = unsafeRadius + 3.0f;

        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.CohortId + ":"
            + std::to_string(board.CurrentScope.AttemptId) + ":"
            + std::to_string(board.CurrentScope.WipeGeneration) + ":"
            + std::to_string(board.CurrentScope.RouteGeneration) + ":"
            + board.CurrentScope.NodeId;
        candidate.Id.Strategy = "adaptive_raid_trash";
        candidate.Id.Mechanic = "hazard_exit";
        candidate.Id.Actor = hazard->Guid;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.Utility = 1000.0f - distance;
        candidate.ExpiresAtMs = board.ObservedAtMs + 1000;
        candidate.Action = BotNativeAction::Move{
            hazard->Position.X + nx * exitRadius,
            hazard->Position.Y + ny * exitRadius,
            bot->Position.Z
        };
        return candidate;
    }
};
}

#endif
