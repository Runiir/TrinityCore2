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
struct PrepullMeleeEndpoint
{
    Vector3 Position;
};

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

        MagmawActorObservation const observed = ObserveMagmawActors(board, *bot);
        if (!observed.Boss)
            return plan;

        plan.OwnsNode = true;
        PrepullDecision prepull = EvaluatePrepull(board, *bot, *observed.Boss,
            role);
        if (prepull.Disposition == PrepullDisposition::HoldOffense)
        {
            plan.SuppressOffense = true;
            plan.Movement = std::move(prepull.Movement);
            return plan;
        }

        plan.DamageTarget = SelectDamageTarget(observed, role);
        plan.Movement = ProposeHazardMovement(board, *bot);
        plan.Interaction = ProposeHookInteraction(board, *bot, *observed.Boss,
            botGuid);
        return plan;
    }

private:
    struct MagmawActorObservation
    {
        ActorSnapshot const* Boss = nullptr;
        ActorSnapshot const* Head = nullptr;
        ActorSnapshot const* NearestParasite = nullptr;
        float NearestParasiteDistance = 0.0f;
    };

    enum class PrepullDisposition : uint8
    {
        NotApplicable,
        HoldOffense
    };

    struct PrepullDecision
    {
        PrepullDisposition Disposition = PrepullDisposition::NotApplicable;
        std::optional<BotNativeAction::Candidate> Movement;
    };

    struct MagmawHazardObservation
    {
        ActorSnapshot const* Pillar = nullptr;
        ActorSnapshot const* NearestImmediateHazard = nullptr;
        float NearestImmediateHazardDistance = 0.0f;
    };

    struct MagmawHookAssignment
    {
        bool Assigned = false;
        ActorSnapshot const* Vehicle = nullptr;
        ActorSnapshot const* Spike = nullptr;
    };

    static bool IsParasiteEntry(uint32 entry)
    {
        return entry == ParasiteEntry || entry == ParasiteAltEntry;
    }

    static MagmawActorObservation ObserveMagmawActors(Blackboard const& board,
        ActorSnapshot const& bot)
    {
        MagmawActorObservation observed;
        auto inspectTarget = [&observed, &bot](ActorSnapshot const& actor)
        {
            if (!actor.Alive)
                return;
            if (actor.Entry == BossEntry)
                observed.Boss = &actor;
            else if (actor.Entry == HeadEntry && actor.Selectable
                && actor.Attackable)
                observed.Head = &actor;
            else if (IsParasiteEntry(actor.Entry))
            {
                float const distance = Distance2d(bot.Position, actor.Position);
                if (!observed.NearestParasite
                    || distance < observed.NearestParasiteDistance)
                {
                    observed.NearestParasite = &actor;
                    observed.NearestParasiteDistance = distance;
                }
            }
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspectTarget(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspectTarget(actor);
        return observed;
    }

    static bool IsPrepull(Blackboard const& board, ActorSnapshot const& boss)
    {
        bool const bossEngaged = boss.InCombat || !boss.VictimGuid.IsEmpty();
        return !bossEngaged && board.NativeBossState != "in_progress";
    }

    static PrepullDecision EvaluatePrepull(Blackboard const& board,
        ActorSnapshot const& bot, ActorSnapshot const& boss,
        std::string_view role)
    {
        PrepullDecision decision;
        if (!IsPrepull(board, boss))
            return decision;

        bool const prepullHealthIncomplete = std::any_of(board.Players.begin(),
            board.Players.end(), [](ActorSnapshot const& member)
            {
                return member.Alive && member.HealthPct < 94.0f;
            });
        if (prepullHealthIncomplete)
        {
            decision.Disposition = PrepullDisposition::HoldOffense;
            return decision;
        }

        bool const tankMeleeReady = std::any_of(board.Players.begin(),
            board.Players.end(), [&boss](ActorSnapshot const& member)
            {
                return member.Alive && member.Role == "tank"
                    && Distance2d(member.Position, boss.Position)
                        <= PrepullMeleeReadyDistance;
            });
        if (tankMeleeReady)
            return decision;

        decision.Disposition = PrepullDisposition::HoldOffense;
        if (role == "tank")
        {
            std::optional<PrepullMeleeEndpoint> endpoint =
                BuildPrepullMeleeEndpoint(bot.Position, boss.Position,
                    bot.Facing);
            if (endpoint)
            {
                BotNativeAction::Candidate candidate;
                candidate.Id.ScopeKey = board.CurrentScope.Key();
                candidate.Id.Strategy = "adaptive_magmaw";
                candidate.Id.Mechanic = "prepull_melee_ready";
                candidate.Id.Actor = boss.Guid;
                candidate.Id.EventGeneration = board.Revision;
                candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
                candidate.Utility = 500.0f;
                candidate.ExpiresAtMs = board.ObservedAtMs + 750;
                candidate.Action = BotNativeAction::Move{
                    endpoint->Position.X, endpoint->Position.Y,
                    endpoint->Position.Z };
                decision.Movement = std::move(candidate);
            }
        }
        return decision;
    }

    static ObjectGuid SelectDamageTarget(MagmawActorObservation const& observed,
        std::string_view role)
    {
        if (role == "tank")
            return observed.Boss->Guid;
        if (observed.Head)
            return observed.Head->Guid;
        if (observed.NearestParasite
            && observed.NearestParasiteDistance <= 30.0f)
            return observed.NearestParasite->Guid;
        return observed.Boss->Guid;
    }

    static ActorSnapshot const* FindFirstAliveActorByEntry(
        std::vector<ActorSnapshot> const& actors, uint32 entry)
    {
        auto itr = std::find_if(actors.begin(), actors.end(), [entry](
            ActorSnapshot const& actor)
        {
            return actor.Alive && actor.Entry == entry;
        });
        return itr == actors.end() ? nullptr : &*itr;
    }

    static bool IsImmediateHazard(ActorSnapshot const& actor)
    {
        bool const litCrash = actor.Entry == RoomStalkerEntry
            && HasAura(actor, 87949);
        bool const parasite = IsParasiteEntry(actor.Entry);
        bool const crash = actor.Entry == CrashEntry;
        return actor.Alive && (litCrash || parasite || crash);
    }

    static MagmawHazardObservation ObserveHazards(Blackboard const& board,
        ActorSnapshot const& bot)
    {
        MagmawHazardObservation observed;
        observed.Pillar = FindFirstAliveActorByEntry(board.Summons, PillarEntry);
        auto inspectHazard = [&observed, &bot](ActorSnapshot const& actor)
        {
            if (!IsImmediateHazard(actor))
                return;
            float const distance = Distance2d(bot.Position, actor.Position);
            if (!observed.NearestImmediateHazard
                || distance < observed.NearestImmediateHazardDistance)
            {
                observed.NearestImmediateHazard = &actor;
                observed.NearestImmediateHazardDistance = distance;
            }
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspectHazard(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspectHazard(actor);
        return observed;
    }

    static std::optional<BotNativeAction::Candidate> BuildPillarEvade(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& pillar)
    {
        float dx = bot.Position.X - pillar.Position.X;
        float dy = bot.Position.Y - pillar.Position.Y;
        float distance = std::sqrt(dx * dx + dy * dy);
        if (distance <= 12.0f)
        {
            if (distance < 0.01f)
            {
                dx = std::cos(bot.Facing);
                dy = std::sin(bot.Facing);
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
            candidate.Id.Actor = pillar.Guid;
            candidate.Id.EventGeneration = board.Revision;
            candidate.ActionPriority = BotActionArbitration::Priority::Survival;
            candidate.Utility = 500.0f - distance;
            candidate.ExpiresAtMs = board.ObservedAtMs + 750;
            candidate.Action = BotNativeAction::Move{
                pillar.Position.X + dx / distance * 15.0f,
                pillar.Position.Y + dy / distance * 15.0f,
                bot.Position.Z };
            return candidate;
        }
        return std::nullopt;
    }

    static bool IsCrashHazard(ActorSnapshot const& actor)
    {
        return actor.Entry == RoomStalkerEntry || actor.Entry == CrashEntry;
    }

    static std::optional<BotNativeAction::Candidate> ProposeHazardMovement(
        Blackboard const& board, ActorSnapshot const& bot)
    {
        MagmawHazardObservation const observed = ObserveHazards(board, bot);
        if (observed.Pillar)
            if (std::optional<BotNativeAction::Candidate> pillar =
                    BuildPillarEvade(board, bot, *observed.Pillar))
                return pillar;

        if (observed.NearestImmediateHazard
            && observed.NearestImmediateHazardDistance <= 12.0f)
            return MoveAway(board, bot, *observed.NearestImmediateHazard,
                IsCrashHazard(*observed.NearestImmediateHazard)
                    ? "massive_crash_evade" : "parasite_contact_evade",
                16.0f);
        return std::nullopt;
    }

    static std::vector<ObjectGuid> BuildHookUsers(Blackboard const& board)
    {
        std::vector<ObjectGuid> hookUsers;
        for (ActorSnapshot const& member : board.Players)
            if (member.Alive && member.Role == "dps")
                hookUsers.push_back(member.Guid);
        std::sort(hookUsers.begin(), hookUsers.end(), [](ObjectGuid left,
            ObjectGuid right)
        {
            return left.GetRawValue() < right.GetRawValue();
        });
        if (hookUsers.size() < 2)
            for (ActorSnapshot const& member : board.Players)
                if (member.Alive && member.Role != "tank"
                    && std::find(hookUsers.begin(), hookUsers.end(), member.Guid)
                        == hookUsers.end())
                    hookUsers.push_back(member.Guid);
        return hookUsers;
    }

    static bool IsAssignedHookUser(std::vector<ObjectGuid> const& hookUsers,
        ObjectGuid botGuid)
    {
        auto hookUser = std::find(hookUsers.begin(), hookUsers.end(), botGuid);
        return hookUser != hookUsers.end()
            && std::distance(hookUsers.begin(), hookUser) < 2;
    }

    static MagmawHookAssignment ResolveHookAssignment(
        Blackboard const& board, ActorSnapshot const& bot, ObjectGuid botGuid)
    {
        std::vector<ObjectGuid> const hookUsers = BuildHookUsers(board);
        if (!IsAssignedHookUser(hookUsers, botGuid))
            return {};
        return { true, board.FindActor(bot.VehicleGuid),
            FindActorByEntry(board, SpikeEntry) };
    }

    static bool IsPincerVehicle(ActorSnapshot const& vehicle)
    {
        return vehicle.Entry == PincerLeftEntry
            || vehicle.Entry == PincerRightEntry;
    }

    static BotNativeAction::Candidate BuildHookCandidate(Blackboard const& board,
        ActorSnapshot const& vehicle, ActorSnapshot const& spike)
    {
        BotNativeAction::Candidate hook;
        hook.Id.ScopeKey = board.CurrentScope.Key();
        hook.Id.Strategy = "adaptive_magmaw";
        hook.Id.Mechanic = "launch_native_hook";
        hook.Id.Actor = spike.Guid;
        hook.Id.EventGeneration = board.Revision;
        hook.ActionPriority = BotActionArbitration::Priority::Mechanic;
        hook.Utility = 400.0f;
        hook.ExpiresAtMs = board.ObservedAtMs + 500;
        hook.Action = BotNativeAction::VehicleAction{
            vehicle.Entry == PincerLeftEntry ? 77917u : 77941u,
            spike.Guid };
        return hook;
    }

    static BotNativeAction::Candidate BuildMountCandidate(
        Blackboard const& board, ActorSnapshot const& boss)
    {
        BotNativeAction::Candidate mount;
        mount.Id.ScopeKey = board.CurrentScope.Key();
        mount.Id.Strategy = "adaptive_magmaw";
        mount.Id.Mechanic = "mount_free_pincer";
        mount.Id.Actor = boss.Guid;
        mount.Id.EventGeneration = board.Revision;
        mount.ActionPriority = BotActionArbitration::Priority::Mechanic;
        mount.Utility = 350.0f;
        mount.ExpiresAtMs = board.ObservedAtMs + 500;
        mount.Action = BotNativeAction::SpellClick{ boss.Guid };
        return mount;
    }

    static std::optional<BotNativeAction::Candidate> ProposeHookInteraction(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ObjectGuid botGuid)
    {
        MagmawHookAssignment const assignment = ResolveHookAssignment(board,
            bot, botGuid);
        if (!assignment.Assigned)
            return std::nullopt;
        if (assignment.Vehicle && assignment.Spike
            && IsPincerVehicle(*assignment.Vehicle))
            return BuildHookCandidate(board, *assignment.Vehicle,
                *assignment.Spike);
        if (boss.Interactable && bot.VehicleGuid.IsEmpty()
            && Distance2d(bot.Position, boss.Position)
                <= HookInteractionDistance)
            return BuildMountCandidate(board, boss);
        return std::nullopt;
    }

    static std::optional<PrepullMeleeEndpoint> BuildPrepullMeleeEndpoint(
        Vector3 const& botPosition, Vector3 const& bossPosition,
        float botFacing)
    {
        if (!std::isfinite(botPosition.X) || !std::isfinite(botPosition.Y)
            || !std::isfinite(botPosition.Z)
            || !std::isfinite(bossPosition.X)
            || !std::isfinite(bossPosition.Y)
            || !std::isfinite(bossPosition.Z))
            return std::nullopt;

        float dx = botPosition.X - bossPosition.X;
        float dy = botPosition.Y - bossPosition.Y;
        float length = std::sqrt(dx * dx + dy * dy);
        if (!std::isfinite(length))
            return std::nullopt;
        if (length < 0.01f)
        {
            if (!std::isfinite(botFacing))
                return std::nullopt;
            dx = std::cos(botFacing);
            dy = std::sin(botFacing);
            length = 1.0f;
        }

        PrepullMeleeEndpoint endpoint{ {
            bossPosition.X + dx / length * PrepullMeleeOffsetDistance,
            bossPosition.Y + dy / length * PrepullMeleeOffsetDistance,
            bossPosition.Z } };
        if (!std::isfinite(endpoint.Position.X)
            || !std::isfinite(endpoint.Position.Y)
            || !std::isfinite(endpoint.Position.Z))
            return std::nullopt;
        return endpoint;
    }

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
