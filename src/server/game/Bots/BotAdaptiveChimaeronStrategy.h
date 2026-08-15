#ifndef TRINITY_BOT_ADAPTIVE_CHIMAERON_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_CHIMAERON_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <string_view>

namespace BotEncounter
{
struct AdaptiveChimaeronPlan
{
    bool OwnsNode = false;
    bool HealingDisabled = false;
    ObjectGuid DamageTarget;
    ObjectGuid PriorityHealTarget;
    std::optional<BotNativeAction::Candidate> Movement;
};

class AdaptiveChimaeronStrategy
{
public:
    static constexpr uint32 BossEntry = 43296;

    AdaptiveChimaeronPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
    {
        AdaptiveChimaeronPlan plan;
        if (board.Route.NodeId != "bwd.chimaeron.encounter")
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        ActorSnapshot const* boss = Find(board, BossEntry);
        if (!bot || !bot->Alive || !boss)
            return plan;
        plan.OwnsNode = true;
        plan.DamageTarget = boss->Guid;
        plan.HealingDisabled = HasAura(*boss, 82934)
            || HasAura(*bot, 82890);

        if (role == "healer" && !plan.HealingDisabled)
        {
            if (HasAura(*boss, 88826) && !boss->VictimGuid.IsEmpty())
                plan.PriorityHealTarget = boss->VictimGuid;
            else
            {
                ActorSnapshot const* floorTarget = nullptr;
                for (ActorSnapshot const& player : board.Players)
                    if (player.Alive && HasAura(player, 82705)
                        && player.Health < 12000
                        && (!floorTarget || player.Health < floorTarget->Health))
                        floorTarget = &player;
                if (floorTarget)
                    plan.PriorityHealTarget = floorTarget->Guid;
            }
        }

        if (HasAura(*boss, 88872))
        {
            float const stackX = boss->Position.X
                - std::cos(boss->Facing) * 8.0f;
            float const stackY = boss->Position.Y
                - std::sin(boss->Facing) * 8.0f;
            if (Distance2d(bot->Position, { stackX, stackY,
                    boss->Position.Z }) > 5.0f)
                plan.Movement = Move(board, *bot, stackX, stackY,
                    "feud_rear_stack", boss->Guid,
                    BotActionArbitration::Priority::Mechanic);
        }
        else
        {
            ActorSnapshot const* nearest = nullptr;
            float nearestDistance = 0.0f;
            for (ActorSnapshot const& player : board.Players)
                if (player.Alive && player.Guid != botGuid)
                {
                    float const distance = Distance2d(bot->Position,
                        player.Position);
                    if (!nearest || distance < nearestDistance)
                    {
                        nearest = &player;
                        nearestDistance = distance;
                    }
                }
            if (nearest && nearestDistance < 7.0f)
            {
                float dx = bot->Position.X - nearest->Position.X;
                float dy = bot->Position.Y - nearest->Position.Y;
                float length = std::sqrt(dx * dx + dy * dy);
                if (length < 0.01f)
                {
                    dx = std::cos(bot->Facing);
                    dy = std::sin(bot->Facing);
                    length = 1.0f;
                }
                plan.Movement = Move(board, *bot,
                    nearest->Position.X + dx / length * 9.0f,
                    nearest->Position.Y + dy / length * 9.0f,
                    "caustic_slime_spread", nearest->Guid,
                    BotActionArbitration::Priority::Mechanic);
            }
        }
        return plan;
    }

private:
    static bool HasAura(ActorSnapshot const& actor, uint32 spellId)
    {
        return std::any_of(actor.Auras.begin(), actor.Auras.end(),
            [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
    }

    static ActorSnapshot const* Find(Blackboard const& board, uint32 entry)
    {
        for (ActorSnapshot const& actor : board.Hostiles)
            if (actor.Alive && actor.Entry == entry)
                return &actor;
        return nullptr;
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        return std::sqrt(dx * dx + dy * dy);
    }

    static BotNativeAction::Candidate Move(Blackboard const& board,
        ActorSnapshot const& bot, float x, float y, std::string mechanic,
        ObjectGuid actor, BotActionArbitration::Priority priority)
    {
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_chimaeron";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.Actor = actor;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = priority;
        candidate.Utility = 250.0f;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{ x, y, bot.Position.Z };
        return candidate;
    }
};
}

#endif
