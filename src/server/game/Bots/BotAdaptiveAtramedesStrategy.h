#ifndef TRINITY_BOT_ADAPTIVE_ATRAMEDES_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_ATRAMEDES_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <string>
#include <string_view>

namespace BotEncounter
{
struct AdaptiveAtramedesPlan
{
    bool OwnsNode = false;
    ObjectGuid DamageTarget;
    std::optional<BotNativeAction::Candidate> Movement;
    std::optional<BotNativeAction::Candidate> Interaction;
};

class AdaptiveAtramedesStrategy
{
public:
    static constexpr uint32 BossEntry = 41442;

    AdaptiveAtramedesPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view /*role*/) const
    {
        AdaptiveAtramedesPlan plan;
        if (board.Route.NodeId != "bwd.atramedes.encounter")
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        ActorSnapshot const* boss = Find(board, BossEntry);
        if (!bot || !bot->Alive || !boss)
            return plan;
        plan.OwnsNode = true;
        plan.DamageTarget = boss->Guid;

        ActorSnapshot const* nearestHazard = nullptr;
        float nearestDistance = 0.0f;
        auto inspect = [&](ActorSnapshot const& actor)
        {
            if (!actor.Alive || !IsHazard(actor.Entry))
                return;
            float const distance = Distance2d(bot->Position, actor.Position);
            float const radius = actor.Entry == 41546 ? 7.0f : 8.0f;
            if (distance > radius)
                return;
            if (!nearestHazard || distance < nearestDistance)
            {
                nearestHazard = &actor;
                nearestDistance = distance;
            }
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspect(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspect(actor);
        if (nearestHazard)
            plan.Movement = AwayFrom(board, *bot, *nearestHazard,
                "atramedes_hazard_exit", 11.0f);
        else if (HasAura(*bot, 78092))
        {
            float const dx = bot->Position.X - boss->Position.X;
            float const dy = bot->Position.Y - boss->Position.Y;
            float const length = std::max(0.01f, std::sqrt(dx * dx + dy * dy));
            BotNativeAction::Candidate movement;
            movement.Id.ScopeKey = board.CurrentScope.Key();
            movement.Id.Strategy = "adaptive_atramedes";
            movement.Id.Mechanic = "sonic_breath_tangential_kite";
            movement.Id.Actor = boss->Guid;
            movement.Id.EventGeneration = board.Revision;
            movement.ActionPriority = BotActionArbitration::Priority::Survival;
            movement.Utility = 500.0f;
            movement.ExpiresAtMs = board.ObservedAtMs + 750;
            movement.Action = BotNativeAction::Move{
                bot->Position.X - dy / length * 10.0f,
                bot->Position.Y + dx / length * 10.0f,
                bot->Position.Z };
            plan.Movement = std::move(movement);
        }

        bool const searingFlame = boss->Cast
            && boss->Cast->SpellId == 77840;
        if (searingFlame)
        {
            std::vector<ObjectGuid> eligible;
            for (ActorSnapshot const& player : board.Players)
                if (player.Alive)
                    eligible.push_back(player.Guid);
            std::sort(eligible.begin(), eligible.end(), [](ObjectGuid left,
                ObjectGuid right)
            {
                return left.GetRawValue() < right.GetRawValue();
            });
            ActorSnapshot const* gong = NearestGong(board, *bot);
            if (gong && !eligible.empty() && eligible.front() == botGuid)
            {
                BotNativeAction::Candidate interaction;
                interaction.Id.ScopeKey = board.CurrentScope.Key();
                interaction.Id.Strategy = "adaptive_atramedes";
                interaction.Id.Mechanic = "searing_flame_gong";
                interaction.Id.Actor = gong->Guid;
                interaction.Id.EventGeneration = board.Revision;
                interaction.ActionPriority = BotActionArbitration::Priority::Mechanic;
                interaction.Utility = 600.0f;
                interaction.ExpiresAtMs = board.ObservedAtMs + 500;
                if (Distance2d(bot->Position, gong->Position) <= 5.0f)
                    interaction.Action = BotNativeAction::SpellClick{ gong->Guid };
                else
                    interaction.Action = BotNativeAction::Move{
                        gong->Position.X, gong->Position.Y, gong->Position.Z };
                plan.Interaction = std::move(interaction);
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

    static bool IsHazard(uint32 entry)
    {
        return entry == 41546 || entry == 41879 || entry == 41962
            || entry == 42001 || entry == 49623;
    }

    static bool IsGong(uint32 entry)
    {
        static constexpr std::array<uint32, 8> gongs = {
            41445, 42947, 42949, 42951, 42954, 42956, 42958, 42960 };
        return std::find(gongs.begin(), gongs.end(), entry) != gongs.end();
    }

    static ActorSnapshot const* Find(Blackboard const& board, uint32 entry)
    {
        for (ActorSnapshot const& actor : board.Hostiles)
            if (actor.Alive && actor.Entry == entry)
                return &actor;
        for (ActorSnapshot const& actor : board.Interactables)
            if (actor.Alive && actor.Entry == entry)
                return &actor;
        return nullptr;
    }

    static ActorSnapshot const* NearestGong(Blackboard const& board,
        ActorSnapshot const& bot)
    {
        ActorSnapshot const* result = nullptr;
        float nearest = 0.0f;
        auto inspect = [&](std::vector<ActorSnapshot> const& actors)
        {
            for (ActorSnapshot const& actor : actors)
                if (actor.Alive && actor.Selectable && actor.Interactable
                    && IsGong(actor.Entry))
                {
                    float const distance = Distance2d(bot.Position,
                        actor.Position);
                    if (!result || distance < nearest)
                    {
                        result = &actor;
                        nearest = distance;
                    }
                }
        };
        inspect(board.Interactables);
        inspect(board.Summons);
        return result;
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        return std::sqrt(dx * dx + dy * dy);
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
        candidate.Id.Strategy = "adaptive_atramedes";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.Actor = danger.Guid;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.Utility = 450.0f;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{
            danger.Position.X + dx / length * exitDistance,
            danger.Position.Y + dy / length * exitDistance,
            bot.Position.Z };
        return candidate;
    }
};
}

#endif
