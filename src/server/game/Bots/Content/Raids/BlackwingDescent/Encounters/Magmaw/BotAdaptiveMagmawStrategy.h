#ifndef TRINITY_BOT_ADAPTIVE_MAGMAW_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_MAGMAW_STRATEGY_H

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
struct AdaptiveMagmawPlan
{
    bool OwnsNode = false;
    bool SuppressOffense = false;
    ObjectGuid DamageTarget;
    std::optional<BotNativeAction::Candidate> Movement;
    std::optional<BotNativeAction::Candidate> Interaction;
};

class AdaptiveMagmawStrategy
{
public:
    static constexpr uint32 BossEntry = 41570;
    static constexpr uint32 HeadEntry = 42347;
    static constexpr uint32 PillarEntry = 41843;
    static constexpr uint32 ParasiteEntry = 41806;
    static constexpr uint32 ParasiteAltEntry = 42321;
    static constexpr uint32 CrashEntry = 47330;
    static constexpr uint32 RoomStalkerEntry = 47196;
    static constexpr uint32 PincerLeftEntry = 41620;
    static constexpr uint32 PincerRightEntry = 41789;
    static constexpr uint32 SpikeEntry = 41767;
    // Keep the native victim inside ordinary melee reach before the first
    // offensive action.  The margin accounts for the boss's combat reach
    // without treating a remote position as an engaged encounter.
    static constexpr float PrepullMeleeReadyDistance = 8.0f;
    static constexpr float PrepullMeleeOffsetDistance = 4.0f;
    static constexpr float HookInteractionDistance = 5.0f;

    AdaptiveMagmawPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
    {
        AdaptiveMagmawPlan plan;
        if (board.Route.NodeId != "bwd.magmaw.encounter")
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return plan;

        ActorSnapshot const* boss = nullptr;
        ActorSnapshot const* head = nullptr;
        ActorSnapshot const* nearestParasite = nullptr;
        float nearestParasiteDistance = 0.0f;
        auto inspectTarget = [&](ActorSnapshot const& actor)
        {
            if (!actor.Alive)
                return;
            if (actor.Entry == BossEntry)
                boss = &actor;
            else if (actor.Entry == HeadEntry && actor.Selectable && actor.Attackable)
                head = &actor;
            else if (actor.Entry == ParasiteEntry || actor.Entry == ParasiteAltEntry)
            {
                float const dx = bot->Position.X - actor.Position.X;
                float const dy = bot->Position.Y - actor.Position.Y;
                float const distance = std::sqrt(dx * dx + dy * dy);
                if (!nearestParasite || distance < nearestParasiteDistance)
                {
                    nearestParasite = &actor;
                    nearestParasiteDistance = distance;
                }
            }
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspectTarget(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspectTarget(actor);
        if (!boss)
            return plan;

        plan.OwnsNode = true;
        bool const bossEngaged = boss->InCombat || !boss->VictimGuid.IsEmpty();
        bool const prepullHealthIncomplete = !bossEngaged
            && board.NativeBossState != "in_progress"
            && std::any_of(board.Players.begin(), board.Players.end(),
                [](ActorSnapshot const& member)
                {
                    return member.Alive && member.HealthPct < 94.0f;
                });
        if (prepullHealthIncomplete)
        {
            plan.SuppressOffense = true;
            return plan;
        }
        bool const tankMeleeReady = std::any_of(board.Players.begin(),
            board.Players.end(), [boss](ActorSnapshot const& member)
            {
                return member.Alive && member.Role == "tank"
                    && Distance2d(member.Position, boss->Position)
                        <= PrepullMeleeReadyDistance;
            });
        bool const prepullTankNotReady = !bossEngaged
            && board.NativeBossState != "in_progress"
            && !tankMeleeReady;
        if (prepullTankNotReady)
        {
            plan.SuppressOffense = true;
            if (role == "tank")
            {
                float dx = bot->Position.X - boss->Position.X;
                float dy = bot->Position.Y - boss->Position.Y;
                float length = std::sqrt(dx * dx + dy * dy);
                if (length < 0.01f)
                {
                    dx = std::cos(bot->Facing);
                    dy = std::sin(bot->Facing);
                    length = 1.0f;
                }
                BotNativeAction::Candidate candidate;
                candidate.Id.ScopeKey = board.CurrentScope.Key();
                candidate.Id.Strategy = "adaptive_magmaw";
                candidate.Id.Mechanic = "prepull_melee_ready";
                candidate.Id.Actor = boss->Guid;
                candidate.Id.EventGeneration = board.Revision;
                candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
                candidate.Utility = 500.0f;
                candidate.ExpiresAtMs = board.ObservedAtMs + 750;
                candidate.Action = BotNativeAction::Move{
                    boss->Position.X + dx / length * PrepullMeleeOffsetDistance,
                    boss->Position.Y + dy / length * PrepullMeleeOffsetDistance,
                    bot->Position.Z };
                plan.Movement = std::move(candidate);
            }
            return plan;
        }
        if (role == "tank")
            plan.DamageTarget = boss->Guid;
        else if (head)
            plan.DamageTarget = head->Guid;
        else if (nearestParasite && nearestParasiteDistance <= 30.0f)
            plan.DamageTarget = nearestParasite->Guid;
        else
            plan.DamageTarget = boss->Guid;

        ActorSnapshot const* pillar = nullptr;
        for (ActorSnapshot const& actor : board.Summons)
            if (actor.Alive && actor.Entry == PillarEntry)
            {
                pillar = &actor;
                break;
            }
        ActorSnapshot const* nearestImmediateHazard = nullptr;
        float nearestImmediateHazardDistance = 0.0f;
        auto inspectHazard = [&](ActorSnapshot const& actor)
        {
            bool const litCrash = actor.Entry == RoomStalkerEntry
                && HasAura(actor, 87949);
            bool const parasite = actor.Entry == ParasiteEntry
                || actor.Entry == ParasiteAltEntry;
            bool const crash = actor.Entry == CrashEntry;
            if (!actor.Alive || (!litCrash && !parasite && !crash))
                return;
            float const distance = Distance2d(bot->Position, actor.Position);
            if (!nearestImmediateHazard || distance < nearestImmediateHazardDistance)
            {
                nearestImmediateHazard = &actor;
                nearestImmediateHazardDistance = distance;
            }
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspectHazard(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspectHazard(actor);

        if (pillar)
        {
            float dx = bot->Position.X - pillar->Position.X;
            float dy = bot->Position.Y - pillar->Position.Y;
            float distance = std::sqrt(dx * dx + dy * dy);
            if (distance <= 12.0f)
            {
                if (distance < 0.01f)
                {
                    dx = std::cos(bot->Facing);
                    dy = std::sin(bot->Facing);
                    distance = 1.0f;
                }
                BotNativeAction::Candidate candidate;
                candidate.Id.ScopeKey = board.CurrentScope.CohortId + ":"
                    + std::to_string(board.CurrentScope.AttemptId) + ":"
                    + std::to_string(board.CurrentScope.WipeGeneration) + ":"
                    + std::to_string(board.CurrentScope.RouteGeneration) + ":"
                    + board.CurrentScope.NodeId;
                candidate.Id.Strategy = "adaptive_magmaw";
                candidate.Id.Mechanic = "pillar_evade";
                candidate.Id.Actor = pillar->Guid;
                candidate.Id.EventGeneration = board.Revision;
                candidate.ActionPriority = BotActionArbitration::Priority::Survival;
                candidate.Utility = 500.0f - distance;
                candidate.ExpiresAtMs = board.ObservedAtMs + 750;
                candidate.Action = BotNativeAction::Move{
                    pillar->Position.X + dx / distance * 15.0f,
                    pillar->Position.Y + dy / distance * 15.0f,
                    bot->Position.Z };
                plan.Movement = std::move(candidate);
            }
        }
        if (!plan.Movement && nearestImmediateHazard
            && nearestImmediateHazardDistance <= 12.0f)
            plan.Movement = MoveAway(board, *bot, *nearestImmediateHazard,
                nearestImmediateHazard->Entry == RoomStalkerEntry
                    || nearestImmediateHazard->Entry == CrashEntry
                    ? "massive_crash_evade" : "parasite_contact_evade",
                16.0f);

        std::vector<ObjectGuid> hookUsers;
        for (ActorSnapshot const& member : board.Players)
            if (member.Alive && member.Role == "dps")
                hookUsers.push_back(member.Guid);
        std::sort(hookUsers.begin(), hookUsers.end(), [](ObjectGuid left, ObjectGuid right)
        {
            return left.GetRawValue() < right.GetRawValue();
        });
        if (hookUsers.size() < 2)
            for (ActorSnapshot const& member : board.Players)
                if (member.Alive && member.Role != "tank"
                    && std::find(hookUsers.begin(), hookUsers.end(), member.Guid)
                        == hookUsers.end())
                    hookUsers.push_back(member.Guid);

        auto hookUser = std::find(hookUsers.begin(), hookUsers.end(), botGuid);
        bool const assignedHookUser = hookUser != hookUsers.end()
            && std::distance(hookUsers.begin(), hookUser) < 2;
        if (assignedHookUser)
        {
            ActorSnapshot const* vehicle = board.FindActor(bot->VehicleGuid);
            ActorSnapshot const* spike = FindActorByEntry(board, SpikeEntry);
            if (vehicle && spike
                && (vehicle->Entry == PincerLeftEntry
                    || vehicle->Entry == PincerRightEntry))
            {
                BotNativeAction::Candidate hook;
                hook.Id.ScopeKey = board.CurrentScope.Key();
                hook.Id.Strategy = "adaptive_magmaw";
                hook.Id.Mechanic = "launch_native_hook";
                hook.Id.Actor = spike->Guid;
                hook.Id.EventGeneration = board.Revision;
                hook.ActionPriority = BotActionArbitration::Priority::Mechanic;
                hook.Utility = 400.0f;
                hook.ExpiresAtMs = board.ObservedAtMs + 500;
                hook.Action = BotNativeAction::VehicleAction{
                    vehicle->Entry == PincerLeftEntry ? 77917u : 77941u,
                    spike->Guid };
                plan.Interaction = std::move(hook);
            }
            else if (boss->Interactable && bot->VehicleGuid.IsEmpty()
                && Distance2d(bot->Position, boss->Position)
                    <= HookInteractionDistance)
            {
                BotNativeAction::Candidate mount;
                mount.Id.ScopeKey = board.CurrentScope.Key();
                mount.Id.Strategy = "adaptive_magmaw";
                mount.Id.Mechanic = "mount_free_pincer";
                mount.Id.Actor = boss->Guid;
                mount.Id.EventGeneration = board.Revision;
                mount.ActionPriority = BotActionArbitration::Priority::Mechanic;
                mount.Utility = 350.0f;
                mount.ExpiresAtMs = board.ObservedAtMs + 500;
                mount.Action = BotNativeAction::SpellClick{ boss->Guid };
                plan.Interaction = std::move(mount);
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

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        return std::sqrt(dx * dx + dy * dy);
    }

    static ActorSnapshot const* FindActorByEntry(Blackboard const& board,
        uint32 entry)
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

    static BotNativeAction::Candidate MoveAway(Blackboard const& board,
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
        candidate.Id.Strategy = "adaptive_magmaw";
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
