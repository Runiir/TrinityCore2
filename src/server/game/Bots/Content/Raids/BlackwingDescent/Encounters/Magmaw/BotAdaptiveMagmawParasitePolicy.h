#ifndef TRINITY_BOT_ADAPTIVE_MAGMAW_PARASITE_POLICY_H
#define TRINITY_BOT_ADAPTIVE_MAGMAW_PARASITE_POLICY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawLaneTransition.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <string>
#include <utility>

namespace BotEncounter
{
// The parasite policy owns the fixed mobile-DPS lane transition. Formation
// and pincer policy remain in the encounter strategy; this small value type is
// the hand-off between those owners.
class MagmawParasitePolicy
{
public:
    struct FormationAnchors
    {
        Vector3 Support;
        Vector3 Left;
        Vector3 Right;
    };

    static constexpr float LocalContactRange = 12.0f;
    static constexpr float KiteLeadDistance = 22.0f;
    static constexpr float SafeClearance = 16.0f;
    static constexpr float StackSeparation = 20.0f;
    static constexpr float DestinationTolerance = 4.0f;

    static float ImmediateContactRange(bool pillarBaiter)
    {
        return pillarBaiter ? KiteLeadDistance : LocalContactRange;
    }

    static std::pair<ObjectGuid, ObjectGuid> ResolveFixedBaiters(
        Blackboard const& board)
    {
        ObjectGuid mage;
        ObjectGuid hunter;
        for (ActorSnapshot const& member : board.Players)
            if (member.Role == "dps")
            {
                if (member.ClassSpec == "fire_mage"
                    && (mage.IsEmpty() || member.Guid.GetRawValue()
                        < mage.GetRawValue()))
                    mage = member.Guid;
                else if (member.ClassSpec == "marksmanship_hunter"
                    && (hunter.IsEmpty() || member.Guid.GetRawValue()
                        < hunter.GetRawValue()))
                    hunter = member.Guid;
            }
        return { mage, hunter };
    }

    // The entire fixed bait lane must remain outside the support stack. An
    // endpoint-only check accepts a chord that cuts through the stack, which
    // was the geometry behind the previous live oscillation.
    static bool FullLaneCorridorSafe(FormationAnchors const& anchors)
    {
        return DistanceToSegment(anchors.Support, anchors.Left,
            anchors.Right) >= StackSeparation;
    }

    static std::optional<Vector3> EnsureLaneDestination(
        Blackboard const& board, ActorSnapshot const& bot,
        FormationAnchors const& anchors, MagmawLaneTransitionState& transition,
        uint64 generation, uint8 kind)
    {
        return EnsureLaneTransition(board, bot, anchors, transition,
            generation, kind);
    }

    static uint64 ParasiteGeneration(Blackboard const& board)
    {
        uint64 generation = std::numeric_limits<uint64>::max();
        auto inspect = [&generation](std::vector<ActorSnapshot> const& actors)
        {
            for (ActorSnapshot const& actor : actors)
                if (actor.Alive && IsParasiteEntry(actor.Entry))
                    generation = std::min(generation,
                        actor.Guid.GetRawValue());
        };
        inspect(board.Hostiles);
        inspect(board.Summons);
        return generation == std::numeric_limits<uint64>::max()
            ? 0 : generation;
    }

    static bool HasLivingParasite(Blackboard const& board)
    {
        auto hasParasite = [](std::vector<ActorSnapshot> const& actors)
        {
            return std::any_of(actors.begin(), actors.end(),
                [](ActorSnapshot const& actor)
                {
                    return actor.Alive && IsParasiteEntry(actor.Entry);
                });
        };
        return hasParasite(board.Hostiles) || hasParasite(board.Summons);
    }

    static bool HasActiveHazardPath(Blackboard const& board,
        BotMovementArbitration::Lease const* movementLease,
        bool activePathValid, bool moving)
    {
        return activePathValid && moving && movementLease
            && movementLease->MovementOwner
                == BotMovementArbitration::Owner::Hazard
            && movementLease->MovementPriority
                == BotMovementArbitration::Priority::Hazard
            && BotMovementArbitration::SameScope(
                ToMovementScope(board), movementLease->MovementScope);
    }

    static std::optional<BotNativeAction::Candidate> Propose(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& parasite, bool pillarBaiter,
        std::optional<FormationAnchors> const& anchors,
        BotMovementArbitration::Lease const* /*movementLease*/,
        MagmawLaneTransitionState* transition = nullptr)
    {
        if (!pillarBaiter)
            return BuildMoveAway(board, bot, parasite,
                "parasite_contact_evade", SafeClearance);

        if (!anchors || !transition)
            return std::nullopt;

        transition->ObserveScope(board);
        std::pair<ObjectGuid, ObjectGuid> const baiters =
            ResolveFixedBaiters(board);
        transition->AssignBaiters(baiters.first, baiters.second);
        if (!transition->IsBaiter(bot.Guid))
            return std::nullopt;

        transition->ObserveArrival(bot.Guid, bot.Position,
            DestinationTolerance, board.Revision);
        uint64 const generation = ParasiteGeneration(board);
        if (!generation)
            return std::nullopt;
        std::optional<Vector3> const destination = EnsureLaneTransition(board,
            bot, *anchors, *transition, generation, 2);
        if (destination
            && ParasiteClearance(board, *destination) < SafeClearance)
        {
            // A parasite reaching the retained endpoint is a typed local
            // safety preemption, not permission to choose the other lane.
            // Preserve the cohort transition and resume it once the endpoint
            // is clear again.
            transition->MarkPreempted();
            return BuildMoveAway(board, bot, parasite,
                "parasite_contact_evade", SafeClearance);
        }
        if (!destination
            || Distance2d(bot.Position, *destination)
                <= DestinationTolerance)
            return std::nullopt;

        transition->Resume();
        BotNativeAction::Candidate candidate = BuildPointMovement(board,
            *destination, "parasite_contact_evade");
        // A baiter owns one point path for the scope.  Pack GUIDs are inputs
        // to safety validation only; replacing the lowest GUID must not
        // replace the native movement owner or restart its path.
        candidate.Id.Actor = bot.Guid;
        candidate.Id.EventGeneration = transition->TransitionId;
        return candidate;
    }

private:
    static bool IsParasiteEntry(uint32 entry)
    {
        return entry == 41806 || entry == 42321;
    }

    static BotMovementArbitration::Scope ToMovementScope(
        Blackboard const& board)
    {
        return BotMovementArbitration::Scope{
            board.CurrentScope.AttemptId,
            board.CurrentScope.WipeGeneration,
            board.CurrentScope.RouteGeneration,
            board.CurrentScope.MapId,
            board.CurrentScope.InstanceId };
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        return std::sqrt(dx * dx + dy * dy);
    }

    static float DistanceToSegment(Vector3 const& point,
        Vector3 const& start, Vector3 const& end)
    {
        float const dx = end.X - start.X;
        float const dy = end.Y - start.Y;
        float const lengthSquared = dx * dx + dy * dy;
        if (lengthSquared < 0.0001f)
            return Distance2d(point, start);
        float const projection = std::clamp(((point.X - start.X) * dx
            + (point.Y - start.Y) * dy) / lengthSquared, 0.0f, 1.0f);
        Vector3 const closest{
            start.X + projection * dx,
            start.Y + projection * dy,
            start.Z + projection * (end.Z - start.Z) };
        return Distance2d(point, closest);
    }

    static float ParasiteClearance(Blackboard const& board,
        Vector3 const& point)
    {
        float clearance = 1000.0f;
        auto inspect = [&clearance, &point](
            std::vector<ActorSnapshot> const& actors)
        {
            for (ActorSnapshot const& actor : actors)
                if (actor.Alive && IsParasiteEntry(actor.Entry))
                    clearance = std::min(clearance,
                        Distance2d(point, actor.Position));
        };
        inspect(board.Hostiles);
        inspect(board.Summons);
        return clearance;
    }

    static bool LaneEndpoint(FormationAnchors const& anchors,
        Vector3 const& point)
    {
        return Distance2d(point, anchors.Left) <= DestinationTolerance
            || Distance2d(point, anchors.Right) <= DestinationTolerance;
    }

    static bool LaneSafe(Blackboard const& board,
        FormationAnchors const& anchors, Vector3 const& destination)
    {
        return FullLaneCorridorSafe(anchors)
            && LaneEndpoint(anchors, destination)
            && Distance2d(destination, anchors.Support) >= StackSeparation
            && ParasiteClearance(board, destination) >= SafeClearance;
    }

    static MagmawLaneTransitionState::Direction InitialDirection(
        Blackboard const& board, ActorSnapshot const& bot,
        FormationAnchors const& anchors)
    {
        float const leftDistance = Distance2d(bot.Position, anchors.Left);
        float const rightDistance = Distance2d(bot.Position, anchors.Right);
        if (leftDistance + DestinationTolerance < rightDistance)
            return MagmawLaneTransitionState::Direction::Right;
        if (rightDistance + DestinationTolerance < leftDistance)
            return MagmawLaneTransitionState::Direction::Left;
        return board.CurrentScope.AttemptId % 2
            ? MagmawLaneTransitionState::Direction::Right
            : MagmawLaneTransitionState::Direction::Left;
    }

    static MagmawLaneTransitionState::Direction OppositeDirection(
        MagmawLaneTransitionState::Direction direction)
    {
        return direction == MagmawLaneTransitionState::Direction::Left
            ? MagmawLaneTransitionState::Direction::Right
            : MagmawLaneTransitionState::Direction::Left;
    }

    static Vector3 DestinationFor(FormationAnchors const& anchors,
        MagmawLaneTransitionState::Direction direction)
    {
        return direction == MagmawLaneTransitionState::Direction::Left
            ? anchors.Left : anchors.Right;
    }

    static std::optional<Vector3> EnsureLaneTransition(
        Blackboard const& board, ActorSnapshot const& bot,
        FormationAnchors const& anchors, MagmawLaneTransitionState& transition,
        uint64 generation, uint8 kind)
    {
        if (!FullLaneCorridorSafe(anchors))
            return std::nullopt;

        transition.RecordArrivalGeneration(generation, kind,
            board.Revision);
        if (transition.IsArrived()
            && transition.GenerationRetired(generation, kind))
        {
            MagmawLaneTransitionState::Direction const direction =
                OppositeDirection(transition.Lane);
            Vector3 const destination = DestinationFor(anchors, direction);
            if (!LaneSafe(board, anchors, destination))
                return std::nullopt;
            transition.Begin(generation, kind, direction, destination);
        }
        else if (!transition.Committed)
        {
            MagmawLaneTransitionState::Direction direction = InitialDirection(
                board, bot, anchors);
            Vector3 destination = DestinationFor(anchors, direction);
            if (!LaneSafe(board, anchors, destination))
            {
                direction = OppositeDirection(direction);
                destination = DestinationFor(anchors, direction);
                if (!LaneSafe(board, anchors, destination))
                    return std::nullopt;
            }
            transition.Begin(generation, kind, direction, destination);
        }

        if (!transition.OwnsGeneration(generation, kind))
            return transition.IsArrived()
                ? std::nullopt
                : std::optional<Vector3>(transition.Destination);
        if (transition.IsArrived())
            return std::nullopt;
        return transition.Destination;
    }

    static BotNativeAction::Candidate BuildPointMovement(
        Blackboard const& board, Vector3 const& point, std::string mechanic)
    {
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_magmaw";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.Utility = 450.0f;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{ point.X, point.Y,
            point.Z, "parasite_contact_evade" };
        return candidate;
    }

    static BotNativeAction::Candidate BuildMoveAway(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& danger, std::string mechanic,
        float exitDistance)
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
            bot.Position.Z, "parasite_contact_evade" };
        return candidate;
    }
};
}

#endif
