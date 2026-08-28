#ifndef TRINITY_BOT_ADAPTIVE_MAGMAW_PARASITE_POLICY_H
#define TRINITY_BOT_ADAPTIVE_MAGMAW_PARASITE_POLICY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <utility>

namespace BotEncounter
{
// The parasite policy owns only the movement transition after a parasite has
// reached a player.  Formation and pincer policy remain in the encounter
// strategy; this small value type is the hand-off between those owners.
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
        BotMovementArbitration::Lease const* movementLease)
    {
        if (!pillarBaiter)
            return BuildMoveAway(board, bot, parasite,
                "parasite_contact_evade", SafeClearance);

        if (!anchors)
            return BuildMoveAway(board, bot, parasite,
                "parasite_contact_evade", SafeClearance);

        Vector3 const edge = BaitEdge(*anchors, bot);
        Vector3 const direction = ForwardDirection(*anchors, edge);
        std::optional<Vector3> destination = RetainedDestination(
            board, bot, *anchors, edge, direction, movementLease);
        if (!destination)
            destination = BuildForwardDestination(board, *anchors, edge,
                direction);
        if (!destination
            || Distance2d(bot.Position, *destination)
                <= DestinationTolerance)
            return std::nullopt;

        BotNativeAction::Candidate candidate = BuildPointMovement(board,
            *destination, "parasite_contact_evade");
        // A baiter owns one point path for the scope.  Pack GUIDs are inputs
        // to safety validation only; replacing the lowest GUID must not
        // replace the native movement owner or restart its path.
        candidate.Id.Actor = bot.Guid;
        candidate.Id.EventGeneration = bot.Guid.GetRawValue();
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

    static float Dot(Vector3 const& left, Vector3 const& right)
    {
        return left.X * right.X + left.Y * right.Y;
    }

    static Vector3 BaitEdge(FormationAnchors const& anchors,
        ActorSnapshot const& bot)
    {
        float const leftDistance = Distance2d(bot.Position, anchors.Left);
        float const rightDistance = Distance2d(bot.Position, anchors.Right);
        return leftDistance <= rightDistance ? anchors.Left : anchors.Right;
    }

    static Vector3 ForwardDirection(FormationAnchors const& anchors,
        Vector3 const& edge)
    {
        float dx = edge.X - anchors.Support.X;
        float dy = edge.Y - anchors.Support.Y;
        float length = std::sqrt(dx * dx + dy * dy);
        if (length < 0.01f)
        {
            dx = edge.X;
            dy = edge.Y;
            length = std::sqrt(dx * dx + dy * dy);
        }
        if (length < 0.01f)
            return { 0.0f, -1.0f, 0.0f };
        return { dx / length, dy / length, 0.0f };
    }

    static float MaxPackForwardProjection(Blackboard const& board,
        Vector3 const& edge, Vector3 const& direction)
    {
        float projection = 0.0f;
        auto inspect = [&projection, &edge, &direction](
            std::vector<ActorSnapshot> const& actors)
        {
            for (ActorSnapshot const& actor : actors)
                if (actor.Alive && IsParasiteEntry(actor.Entry))
                {
                    Vector3 const relative{
                        actor.Position.X - edge.X,
                        actor.Position.Y - edge.Y, 0.0f };
                    projection = std::max(projection, Dot(relative,
                        direction));
                }
        };
        inspect(board.Hostiles);
        inspect(board.Summons);
        return projection;
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

    static bool ForwardSafe(Blackboard const& board,
        FormationAnchors const& anchors, Vector3 const& edge,
        Vector3 const& direction, Vector3 const& destination)
    {
        float const requiredForward = std::max(KiteLeadDistance,
            MaxPackForwardProjection(board, edge, direction)
                + SafeClearance);
        return Dot({ destination.X - edge.X, destination.Y - edge.Y, 0.0f },
                direction) >= requiredForward
            && Distance2d(destination, anchors.Support) >= StackSeparation
            && ParasiteClearance(board, destination) >= SafeClearance;
    }

    static std::optional<Vector3> RetainedDestination(Blackboard const& board,
        ActorSnapshot const&, FormationAnchors const& anchors,
        Vector3 const& edge, Vector3 const& direction,
        BotMovementArbitration::Lease const* movementLease)
    {
        if (!movementLease
            || movementLease->MovementOwner
                != BotMovementArbitration::Owner::Hazard
            || movementLease->MovementPriority
                != BotMovementArbitration::Priority::Hazard
            || movementLease->DynamicTargetGuid
            || !BotMovementArbitration::SameScope(
                ToMovementScope(board), movementLease->MovementScope))
            return std::nullopt;

        Vector3 const destination{ movementLease->X, movementLease->Y,
            movementLease->Z };
        return ForwardSafe(board, anchors, edge, direction, destination)
            ? std::optional<Vector3>(destination) : std::nullopt;
    }

    static std::optional<Vector3> BuildForwardDestination(
        Blackboard const& board, FormationAnchors const& anchors,
        Vector3 const& edge, Vector3 const& direction)
    {
        float const lead = std::max(KiteLeadDistance,
            MaxPackForwardProjection(board, edge, direction)
                + SafeClearance);
        Vector3 destination{
            edge.X + direction.X * lead,
            edge.Y + direction.Y * lead,
            edge.Z };

        // Keep the destination outside the support stack even when a route
        // supplies unusually close lateral anchors.  A bounded extension
        // preserves a point path and cannot oscillate between stack anchors.
        for (uint8 attempt = 0;
             attempt < 4 && Distance2d(destination, anchors.Support)
                    < StackSeparation;
             ++attempt)
        {
            float const deficit = StackSeparation
                - Distance2d(destination, anchors.Support);
            destination.X += direction.X * (deficit + 1.0f);
            destination.Y += direction.Y * (deficit + 1.0f);
        }

        // The projected lead handles a pack moving along the kite lane.  The
        // bounded clearance extension covers a lateral member without ever
        // selecting a destination back toward the raid stack.
        for (uint8 attempt = 0;
             attempt < 4 && ParasiteClearance(board, destination)
                    < SafeClearance;
             ++attempt)
        {
            float const deficit = SafeClearance
                - ParasiteClearance(board, destination);
            destination.X += direction.X * (deficit + 1.0f);
            destination.Y += direction.Y * (deficit + 1.0f);
        }
        return ForwardSafe(board, anchors, edge, direction, destination)
            ? std::optional<Vector3>(destination) : std::nullopt;
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
