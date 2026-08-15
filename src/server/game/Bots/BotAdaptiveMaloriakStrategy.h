#ifndef TRINITY_BOT_ADAPTIVE_MALORIAK_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_MALORIAK_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <string_view>

namespace BotEncounter
{
struct AdaptiveMaloriakPlan
{
    bool OwnsNode = false;
    ObjectGuid DamageTarget;
    ObjectGuid InterruptTarget;
    ObjectGuid DispelTarget;
    std::optional<BotNativeAction::Candidate> Movement;
};

class AdaptiveMaloriakStrategy
{
public:
    static constexpr uint32 BossEntry = 41378;
    static constexpr uint32 AberrationEntry = 41440;
    static constexpr uint32 FreezeEntry = 41576;
    static constexpr uint32 PrimeSubjectEntry = 41841;
    static constexpr uint32 AbsoluteZeroEntry = 41961;

    AdaptiveMaloriakPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
    {
        AdaptiveMaloriakPlan plan;
        if (board.Route.NodeId != "bwd.maloriak.encounter")
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        ActorSnapshot const* boss = Find(board, BossEntry);
        if (!bot || !bot->Alive || !boss)
            return plan;
        plan.OwnsNode = true;
        plan.DamageTarget = boss->Guid;

        if (boss->Cast && boss->Cast->Interruptible
            && boss->Cast->SpellId == 77896)
            plan.InterruptTarget = boss->Guid;
        if (HasAura(*boss, 77912))
            plan.DispelTarget = boss->Guid;

        if (ActorSnapshot const* freeze = Find(board, FreezeEntry);
            freeze && freeze->Attackable && freeze->Selectable)
            plan.DamageTarget = freeze->Guid;
        else if (HasAura(*boss, 92917))
        {
            if (ActorSnapshot const* aberration = Nearest(board, *bot,
                    AberrationEntry))
                plan.DamageTarget = aberration->Guid;
        }
        else if (role == "tank")
        {
            if (ActorSnapshot const* prime = Nearest(board, *bot,
                    PrimeSubjectEntry))
                plan.DamageTarget = prime->Guid;
            else if (ActorSnapshot const* aberration = Nearest(board, *bot,
                    AberrationEntry))
                plan.DamageTarget = aberration->Guid;
        }

        if (HasAnyAura(*bot, { 77786u, 92971u, 92972u, 92973u, 77760u }))
        {
            Vector3 centroid;
            uint32 count = 0;
            for (ActorSnapshot const& player : board.Players)
                if (player.Alive && player.Guid != botGuid)
                {
                    centroid.X += player.Position.X;
                    centroid.Y += player.Position.Y;
                    ++count;
                }
            if (count)
            {
                centroid.X /= float(count);
                centroid.Y /= float(count);
            }
            plan.Movement = AwayFrom(board, *bot, centroid,
                "maloriak_isolation", ObjectGuid{}, 12.0f);
        }
        else if (ActorSnapshot const* sphere = Nearest(board, *bot,
                AbsoluteZeroEntry))
        {
            float const distance = Distance2d(bot->Position, sphere->Position);
            if (distance < 10.0f)
                plan.Movement = AwayFrom(board, *bot, sphere->Position,
                    "absolute_zero_evade", sphere->Guid, 12.0f);
        }
        else if (HasAura(*boss, 78895))
        {
            ActorSnapshot const* nearestPlayer = nullptr;
            float nearestDistance = 0.0f;
            for (ActorSnapshot const& player : board.Players)
                if (player.Alive && player.Guid != botGuid)
                {
                    float const distance = Distance2d(bot->Position,
                        player.Position);
                    if (!nearestPlayer || distance < nearestDistance)
                    {
                        nearestPlayer = &player;
                        nearestDistance = distance;
                    }
                }
            if (nearestPlayer && nearestDistance < 8.0f)
                plan.Movement = AwayFrom(board, *bot,
                    nearestPlayer->Position, "blue_vial_spread",
                    nearestPlayer->Guid, 10.0f);
        }
        return plan;
    }

private:
    static bool HasAura(ActorSnapshot const& actor, uint32 spellId)
    {
        return std::any_of(actor.Auras.begin(), actor.Auras.end(),
            [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
    }

    static bool HasAnyAura(ActorSnapshot const& actor,
        std::initializer_list<uint32> spells)
    {
        return std::any_of(spells.begin(), spells.end(),
            [&actor](uint32 spellId) { return HasAura(actor, spellId); });
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        return std::sqrt(dx * dx + dy * dy);
    }

    static ActorSnapshot const* Find(Blackboard const& board, uint32 entry)
    {
        auto find = [entry](std::vector<ActorSnapshot> const& actors)
            -> ActorSnapshot const*
        {
            auto itr = std::find_if(actors.begin(), actors.end(),
                [entry](ActorSnapshot const& actor)
                {
                    return actor.Alive && actor.Entry == entry;
                });
            return itr == actors.end() ? nullptr : &*itr;
        };
        if (ActorSnapshot const* actor = find(board.Hostiles))
            return actor;
        if (ActorSnapshot const* actor = find(board.Summons))
            return actor;
        return find(board.Interactables);
    }

    static ActorSnapshot const* Nearest(Blackboard const& board,
        ActorSnapshot const& bot, uint32 entry)
    {
        ActorSnapshot const* result = nullptr;
        float nearest = 0.0f;
        auto inspect = [&](std::vector<ActorSnapshot> const& actors)
        {
            for (ActorSnapshot const& actor : actors)
                if (actor.Alive && actor.Entry == entry)
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
        inspect(board.Hostiles);
        inspect(board.Summons);
        return result;
    }

    static BotNativeAction::Candidate AwayFrom(Blackboard const& board,
        ActorSnapshot const& bot, Vector3 const& danger, std::string mechanic,
        ObjectGuid actor, float exitDistance)
    {
        float dx = bot.Position.X - danger.X;
        float dy = bot.Position.Y - danger.Y;
        float length = std::sqrt(dx * dx + dy * dy);
        if (length < 0.01f)
        {
            dx = std::cos(bot.Facing);
            dy = std::sin(bot.Facing);
            length = 1.0f;
        }
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_maloriak";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.Actor = actor;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.Utility = 300.0f;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{
            danger.X + dx / length * exitDistance,
            danger.Y + dy / length * exitDistance,
            bot.Position.Z };
        return candidate;
    }
};
}

#endif
