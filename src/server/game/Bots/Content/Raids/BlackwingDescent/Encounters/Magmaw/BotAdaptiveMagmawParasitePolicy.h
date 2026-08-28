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

    // A lane transition always crosses the room-side line.  Choosing the
    // endpoint opposite the bot's current side is deterministic and does not
    // depend on which parasite GUID happened to be observed first.
    static Vector3 OppositeLaneEndpoint(Blackboard const& board,
        ActorSnapshot const& bot, FormationAnchors const& anchors)
    {
        float const leftDistance = Distance2d(bot.Position, anchors.Left);
        float const rightDistance = Distance2d(bot.Position, anchors.Right);
        if (leftDistance + DestinationTolerance < rightDistance)
            return anchors.Right;
        if (rightDistance + DestinationTolerance < leftDistance)
            return anchors.Left;

        // Match the deterministic prepull side: an odd attempt starts Left,
        // so its first transition goes Right, and vice versa.
        return board.CurrentScope.AttemptId % 2
            ? anchors.Right : anchors.Left;
    }

    // MovementLease is the only already-available per-attempt persistence for
    // point movement.  Retain only an admitted lane endpoint; old outward or
    // radial hazard destinations must not become the new parasite route.
    static std::optional<Vector3> RetainedLaneDestination(
        Blackboard const& board, FormationAnchors const& anchors,
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
        return LaneSafe(board, anchors, destination)
            ? std::optional<Vector3>(destination) : std::nullopt;
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

        std::optional<Vector3> destination = RetainedLaneDestination(
            board, *anchors, movementLease);
        if (!destination)
            destination = BuildLaneDestination(board, bot, *anchors);
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
        return LaneEndpoint(anchors, destination)
            && Distance2d(destination, anchors.Support) >= StackSeparation
            && ParasiteClearance(board, destination) >= SafeClearance;
    }

    static std::optional<Vector3> BuildLaneDestination(
        Blackboard const& board, ActorSnapshot const& bot,
        FormationAnchors const& anchors)
    {
        Vector3 const preferred = OppositeLaneEndpoint(board, bot, anchors);
        if (LaneSafe(board, anchors, preferred))
            return preferred;

        Vector3 const alternate = Distance2d(preferred, anchors.Left)
                <= Distance2d(preferred, anchors.Right)
            ? anchors.Right : anchors.Left;
        return LaneSafe(board, anchors, alternate)
            ? std::optional<Vector3>(alternate) : std::nullopt;
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
