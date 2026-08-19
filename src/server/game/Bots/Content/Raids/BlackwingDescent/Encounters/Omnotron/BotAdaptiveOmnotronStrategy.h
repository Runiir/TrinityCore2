#ifndef TRINITY_BOT_ADAPTIVE_OMNOTRON_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_OMNOTRON_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <string_view>
#include <vector>

namespace BotEncounter
{
struct AdaptiveOmnotronPlan
{
    bool OwnsNode = false;
    bool SuppressOffense = false;
    ObjectGuid DamageTarget;
    ObjectGuid InterruptTarget;
    std::optional<BotNativeAction::Candidate> Movement;
};

class AdaptiveOmnotronStrategy
{
public:
    static constexpr uint32 Arcanotron = 42166;
    static constexpr uint32 Magmatron = 42178;
    static constexpr uint32 Electron = 42179;
    static constexpr uint32 Toxitron = 42180;
    static constexpr uint32 PoisonBomb = 42897;
    static constexpr uint32 PoisonPuddle = 42920;
    static constexpr uint32 ChemicalCloud = 42934;

    AdaptiveOmnotronPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
    {
        AdaptiveOmnotronPlan plan;
        if (board.Route.NodeId != "bwd.omnotron.encounter")
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return plan;

        std::vector<ActorSnapshot const*> constructs;
        for (ActorSnapshot const& hostile : board.Hostiles)
            if (IsConstruct(hostile.Entry) && hostile.Alive)
                constructs.push_back(&hostile);
        if (constructs.empty())
            return plan;
        plan.OwnsNode = true;

        std::vector<ActorSnapshot const*> safeActive;
        for (ActorSnapshot const* construct : constructs)
        {
            bool const active = HasAura(*construct, 78740)
                || construct->InCombat || !construct->VictimGuid.IsEmpty();
            if (!active)
                continue;
            if (construct->Entry == Arcanotron && construct->Cast
                && construct->Cast->SpellId == 79710
                && construct->Cast->Interruptible)
                plan.InterruptTarget = construct->Guid;
            if (!HasDamageShield(*construct))
                safeActive.push_back(construct);
        }
        std::sort(safeActive.begin(), safeActive.end(), [](auto left, auto right)
        {
            return left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });
        if (safeActive.empty())
            plan.SuppressOffense = true;
        else if (role == "tank" && safeActive.size() > 1)
        {
            std::vector<ObjectGuid> tanks;
            for (ActorSnapshot const& player : board.Players)
                if (player.Alive && player.Role == "tank")
                    tanks.push_back(player.Guid);
            std::sort(tanks.begin(), tanks.end(), [](ObjectGuid left, ObjectGuid right)
            {
                return left.GetRawValue() < right.GetRawValue();
            });
            auto itr = std::find(tanks.begin(), tanks.end(), botGuid);
            size_t const index = itr == tanks.end() ? 0
                : size_t(std::distance(tanks.begin(), itr));
            plan.DamageTarget = safeActive[index % safeActive.size()]->Guid;
        }
        else
            plan.DamageTarget = safeActive.front()->Guid;

        if (HasAura(*bot, 79888) || HasAura(*bot, 79501))
        {
            Vector3 centroid = PlayerCentroid(board, botGuid);
            plan.Movement = AwayFrom(board, *bot, centroid,
                HasAura(*bot, 79888) ? "lightning_conductor_isolate"
                    : "acquiring_target_line_clear",
                ObjectGuid{}, 14.0f);
            return plan;
        }

        ActorSnapshot const* nearestHazard = nullptr;
        float nearestDistance = 0.0f;
        auto inspectHazard = [&](ActorSnapshot const& actor)
        {
            bool const hazard = actor.Alive
                && (actor.Entry == PoisonPuddle || actor.Entry == ChemicalCloud
                    || (actor.Entry == PoisonBomb
                        && actor.VictimGuid == botGuid));
            if (!hazard)
                return;
            float const distance = Distance2d(bot->Position, actor.Position);
            if (!nearestHazard || distance < nearestDistance)
            {
                nearestHazard = &actor;
                nearestDistance = distance;
            }
        };
        for (ActorSnapshot const& hostile : board.Hostiles)
            inspectHazard(hostile);
        for (ActorSnapshot const& summon : board.Summons)
            inspectHazard(summon);
        float const unsafeRadius = nearestHazard
            && nearestHazard->Entry == ChemicalCloud ? 14.0f : 8.0f;
        if (nearestHazard && nearestDistance < unsafeRadius)
            plan.Movement = AwayFrom(board, *bot, nearestHazard->Position,
                nearestHazard->Entry == PoisonBomb ? "poison_bomb_kite"
                    : "omnotron_hazard_exit",
                nearestHazard->Guid, unsafeRadius + 3.0f);
        return plan;
    }

private:
    static bool IsConstruct(uint32 entry)
    {
        return entry == Arcanotron || entry == Magmatron
            || entry == Electron || entry == Toxitron;
    }

    static bool HasAura(ActorSnapshot const& actor, uint32 spellId)
    {
        return std::any_of(actor.Auras.begin(), actor.Auras.end(),
            [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
    }

    static bool HasDamageShield(ActorSnapshot const& actor)
    {
        return HasAura(actor, 79900) || HasAura(actor, 79582)
            || HasAura(actor, 79835) || HasAura(actor, 79729);
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        return std::sqrt(dx * dx + dy * dy);
    }

    static Vector3 PlayerCentroid(Blackboard const& board, ObjectGuid exclude)
    {
        Vector3 result;
        uint32 count = 0;
        for (ActorSnapshot const& player : board.Players)
            if (player.Alive && player.Guid != exclude)
            {
                result.X += player.Position.X;
                result.Y += player.Position.Y;
                result.Z += player.Position.Z;
                ++count;
            }
        if (count)
        {
            result.X /= float(count);
            result.Y /= float(count);
            result.Z /= float(count);
        }
        return result;
    }

    static BotNativeAction::Candidate AwayFrom(Blackboard const& board,
        ActorSnapshot const& bot, Vector3 const& danger, std::string mechanic,
        ObjectGuid actor, float distance)
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
        candidate.Id.Strategy = "adaptive_omnotron";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.Actor = actor;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.Utility = 300.0f;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{
            danger.X + dx / length * distance,
            danger.Y + dy / length * distance,
            bot.Position.Z };
        return candidate;
    }
};
}

#endif
