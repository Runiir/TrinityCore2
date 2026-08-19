#ifndef TRINITY_BOT_ADAPTIVE_NEFARIAN_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_NEFARIAN_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace BotEncounter
{
struct AdaptiveNefarianPlan
{
    bool OwnsNode = false;
    ObjectGuid DamageTarget;
    ObjectGuid InterruptTarget;
    std::optional<BotNativeAction::Candidate> Movement;
};

class AdaptiveNefarianStrategy
{
public:
    static constexpr uint32 NefarianEntry = 41376;
    static constexpr uint32 OnyxiaEntry = 41270;
    static constexpr uint32 PrototypeEntry = 41948;
    static constexpr uint32 BoneEntry = 41918;
    static constexpr uint32 FlashpointEntry = 42595;
    static constexpr uint32 FireEntry = 42596;

    AdaptiveNefarianPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
    {
        AdaptiveNefarianPlan plan;
        if (board.Route.NodeId != "bwd.nefarian.encounter")
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        ActorSnapshot const* nefarian = Find(board, NefarianEntry);
        ActorSnapshot const* onyxia = Find(board, OnyxiaEntry);
        if (!bot || !bot->Alive || (!nefarian && !onyxia))
            return plan;
        plan.OwnsNode = true;

        std::vector<ActorSnapshot const*> prototypes = FindAll(board,
            PrototypeEntry);
        bool const phaseTwo = nefarian && HasAura(*nefarian, 81582);
        if (phaseTwo && !prototypes.empty())
        {
            std::sort(prototypes.begin(), prototypes.end(), [](auto left, auto right)
            {
                return left->Guid.GetRawValue() < right->Guid.GetRawValue();
            });
            ActorSnapshot const* assigned = prototypes[
                size_t(botGuid.GetCounter()) % prototypes.size()];
            plan.DamageTarget = assigned->Guid;
            if (assigned->Cast && assigned->Cast->SpellId == 80734
                && assigned->Cast->Interruptible)
                plan.InterruptTarget = assigned->Guid;
        }
        else if (onyxia)
            plan.DamageTarget = onyxia->Guid;
        else if (nefarian)
            plan.DamageTarget = nefarian->Guid;

        ActorSnapshot const* nearestFire = nullptr;
        float nearestFireDistance = 0.0f;
        for (ActorSnapshot const* fire : FindAll(board, FlashpointEntry, FireEntry))
        {
            float const distance = Distance2d(bot->Position, fire->Position);
            if (!nearestFire || distance < nearestFireDistance)
            {
                nearestFire = fire;
                nearestFireDistance = distance;
            }
        }
        if (nearestFire && nearestFireDistance < 10.0f)
        {
            plan.Movement = AwayFrom(board, *bot, *nearestFire,
                "shadowblaze_exit", 13.0f);
            return plan;
        }

        if (role == "tank" && onyxia && nefarian)
        {
            ActorSnapshot const* assigned = botGuid.GetCounter() % 2
                ? onyxia : nefarian;
            ActorSnapshot const* other = assigned == onyxia ? nefarian : onyxia;
            float const separation = Distance2d(assigned->Position,
                other->Position);
            if (separation < 52.0f)
            {
                float dx = assigned->Position.X - other->Position.X;
                float dy = assigned->Position.Y - other->Position.Y;
                float length = std::max(0.01f, std::sqrt(dx * dx + dy * dy));
                BotNativeAction::Candidate movement;
                movement.Id.ScopeKey = board.CurrentScope.Key();
                movement.Id.Strategy = "adaptive_nefarian";
                movement.Id.Mechanic = "dual_dragon_separation";
                movement.Id.Actor = assigned->Guid;
                movement.Id.EventGeneration = board.Revision;
                movement.ActionPriority = BotActionArbitration::Priority::Mechanic;
                movement.Utility = 250.0f;
                movement.ExpiresAtMs = board.ObservedAtMs + 750;
                movement.Action = BotNativeAction::Move{
                    assigned->Position.X + dx / length * 12.0f,
                    assigned->Position.Y + dy / length * 12.0f,
                    bot->Position.Z };
                plan.Movement = std::move(movement);
            }
        }
        else
        {
            ActorSnapshot const* castingDragon = nullptr;
            for (ActorSnapshot const* dragon : { onyxia, nefarian })
                if (dragon && dragon->Cast
                    && (dragon->Cast->SpellId == 77826
                        || dragon->Cast->SpellId == 77827
                        || dragon->Cast->SpellId == 78090))
                {
                    castingDragon = dragon;
                    break;
                }
            if (castingDragon && Distance2d(bot->Position,
                    castingDragon->Position) < 25.0f)
                plan.Movement = Perpendicular(board, *bot, *castingDragon,
                    "dragon_frontal_or_tail_clear");
        }
        return plan;
    }

private:
    static bool HasAura(ActorSnapshot const& actor, uint32 spellId)
    {
        return std::any_of(actor.Auras.begin(), actor.Auras.end(),
            [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        return std::sqrt(dx * dx + dy * dy);
    }

    static ActorSnapshot const* Find(Blackboard const& board, uint32 entry)
    {
        for (ActorSnapshot const& actor : board.Hostiles)
            if (actor.Alive && actor.Entry == entry)
                return &actor;
        return nullptr;
    }

    static std::vector<ActorSnapshot const*> FindAll(Blackboard const& board,
        uint32 first, uint32 second = 0)
    {
        std::vector<ActorSnapshot const*> result;
        auto inspect = [&](std::vector<ActorSnapshot> const& actors)
        {
            for (ActorSnapshot const& actor : actors)
                if (actor.Alive && (actor.Entry == first
                        || (second && actor.Entry == second)))
                    result.push_back(&actor);
        };
        inspect(board.Hostiles);
        inspect(board.Summons);
        return result;
    }

    static BotNativeAction::Candidate AwayFrom(Blackboard const& board,
        ActorSnapshot const& bot, ActorSnapshot const& danger,
        std::string mechanic, float exitDistance)
    {
        float dx = bot.Position.X - danger.Position.X;
        float dy = bot.Position.Y - danger.Position.Y;
        float length = std::sqrt(dx * dx + dy * dy);
        if (length < 0.01f)
        {
            dx = std::cos(bot.Facing);
            dy = std::sin(bot.Facing);
            length = 1.0f;
        }
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_nefarian";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.Actor = danger.Guid;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.Utility = 500.0f;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{
            danger.Position.X + dx / length * exitDistance,
            danger.Position.Y + dy / length * exitDistance,
            bot.Position.Z };
        return candidate;
    }

    static BotNativeAction::Candidate Perpendicular(Blackboard const& board,
        ActorSnapshot const& bot, ActorSnapshot const& dragon,
        std::string mechanic)
    {
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_nefarian";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.Actor = dragon.Guid;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.Utility = 400.0f;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{
            bot.Position.X - std::sin(dragon.Facing) * 12.0f,
            bot.Position.Y + std::cos(dragon.Facing) * 12.0f,
            bot.Position.Z };
        return candidate;
    }
};
}

#endif
