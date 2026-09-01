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
// The parasite policy owns the fixed mobile-DPS lane transition and the
// distinct actor-local contact escape. Formation and pincer policy remain in
// the encounter strategy; this small value type is the hand-off between those
// owners.
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

    static bool PersonallyThreatens(ActorSnapshot const& bot,
        ActorSnapshot const& parasite)
    {
        return parasite.Alive && IsParasiteEntry(parasite.Entry)
            && (parasite.VictimGuid == bot.Guid
                || Distance2d(bot.Position, parasite.Position)
                    <= LocalContactRange);
    }

    static std::optional<BotNativeAction::Candidate> ProposePersonalEscape(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& parasite,
        MagmawParasiteHazardState* hazardState)
    {
        if (!hazardState || !PersonallyThreatens(bot, parasite)
            || Distance2d(bot.Position, parasite.Position) >= SafeClearance)
            return std::nullopt;
        return BuildMoveAway(board, bot, parasite,
            "parasite_contact_evade", SafeClearance, hazardState);
    }

    static std::pair<ObjectGuid, ObjectGuid> ResolveFixedBaiters(
        Blackboard const& board)
    {
        ObjectGuid mage;
        ObjectGuid hunter;
        // Assignment identity comes from the frozen roster, not current
        // liveness.  A death must not promote a different DPS into a lane
        // transition that deliberately retains its original two actors.
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

    // Crash observation is caller-owned. Once admitted, the route points and
    // far endpoint live in the semantic transition and therefore survive
    // parasite GUID churn and short movement-lease expiry.
    static std::optional<Vector3> EnsureSafeParasiteRoute(
        Blackboard const& board, ActorSnapshot const& bot,
        FormationAnchors const& anchors, MagmawLaneTransitionState& transition,
        uint64 generation, uint8 kind,
        std::optional<MagmawParasiteCrashObstacle> const& crash = std::nullopt)
    {
        transition.ObserveScope(board);
        std::pair<ObjectGuid, ObjectGuid> const baiters =
            ResolveFixedBaiters(board);
        transition.AssignBaiters(baiters.first, baiters.second);
        if (!transition.IsBaiter(bot.Guid))
            return std::nullopt;
        transition.ObserveArrival(bot.Guid, bot.Position,
            DestinationTolerance, board.Revision);
        std::vector<Vector3> const parasites = LivingParasitePositions(board);

        transition.RecordArrivalGeneration(generation, kind, board.Revision);
        if (transition.IsArrived()
            && transition.GenerationRetired(generation, kind))
        {
            MagmawLaneTransitionState::Direction const direction =
                OppositeDirection(transition.Lane);
            Vector3 const destination = DestinationFor(anchors, direction);
            if (!LaneEndpoint(anchors, destination)
                || !FullLaneCorridorSafe(anchors))
                return std::nullopt;
            std::optional<MagmawParasiteRoutePlan> route =
                MagmawParasiteRoute::Build(bot.Position, anchors.Support,
                    destination, parasites, crash, StackSeparation);
            if (!route)
                return std::nullopt;
            transition.BeginParasiteRoute(generation, kind, direction,
                bot.Guid, *route);
        }

        bool const promotePillarLane = transition.Committed
            && transition.MechanicKind == 1 && kind == 2
            && !transition.HasRoute(bot.Guid);
        bool const attachCommittedLane = transition.Committed
            && transition.MechanicKind == kind
            && !transition.HasRoute(bot.Guid);
        if (!transition.Committed || promotePillarLane
            || attachCommittedLane)
        {
            MagmawLaneTransitionState::Direction direction =
                promotePillarLane || attachCommittedLane
                    ? transition.Lane : InitialDirection(board, bot, anchors);
            uint8 const attempts = promotePillarLane || attachCommittedLane
                ? 1 : 2;
            for (uint8 attempt = 0; attempt < attempts; ++attempt)
            {
                Vector3 const destination = promotePillarLane
                        || attachCommittedLane
                    ? transition.Destination
                    : DestinationFor(anchors, direction);
                if (LaneEndpoint(anchors, destination)
                    && FullLaneCorridorSafe(anchors))
                    if (std::optional<MagmawParasiteRoutePlan> route =
                            MagmawParasiteRoute::Build(bot.Position,
                                anchors.Support, destination, parasites, crash,
                                StackSeparation))
                    {
                        if (attachCommittedLane)
                            transition.AttachParasiteRoute(bot.Guid, *route);
                        else
                            transition.BeginParasiteRoute(generation, kind,
                                direction, bot.Guid, *route);
                        break;
                    }
                if (!promotePillarLane && !attachCommittedLane)
                    direction = OppositeDirection(direction);
            }
        }

        MagmawParasiteRoutePlan const* route =
            transition.RouteFor(bot.Guid);
        if (!transition.Committed || !route || route->Empty())
            return std::nullopt;
        uint8 const nextPoint = transition.NextRoutePoint(bot.Guid);
        if (nextPoint >= route->PointCount)
            return std::nullopt;
        if (!MagmawParasiteRoute::RemainingRouteSafe(bot.Position, *route,
                nextPoint, parasites)
            || !MagmawParasiteRoute::RemainingRouteAvoidsCrash(bot.Position,
                *route, nextPoint, crash))
        {
            std::optional<MagmawParasiteRoutePlan> replacement =
                MagmawParasiteRoute::Build(bot.Position, anchors.Support,
                    transition.Destination, parasites, crash,
                    StackSeparation);
            if (!replacement)
                return std::nullopt;
            transition.AttachParasiteRoute(bot.Guid, *replacement);
            route = transition.RouteFor(bot.Guid);
        }
        uint8 const safePoint = transition.NextRoutePoint(bot.Guid);
        return route && safePoint < route->PointCount
            ? std::optional<Vector3>(route->Points[safePoint])
            : std::nullopt;
    }

    static MagmawParasiteRouteFacts ObserveRouteFacts(
        Blackboard const& board, ActorSnapshot const& bot)
    {
        return MagmawParasiteRoute::ObserveFacts(bot.Position,
            LivingParasitePositions(board));
    }

    static std::optional<BotNativeAction::Candidate>
    ProposeSafeParasiteRoute(Blackboard const& board,
        ActorSnapshot const& bot, FormationAnchors const& anchors,
        MagmawLaneTransitionState& transition,
        std::optional<MagmawParasiteCrashObstacle> const& crash = std::nullopt)
    {
        uint64 const generation = ParasiteGeneration(board);
        if (!generation)
            return std::nullopt;
        std::optional<Vector3> const waypoint = EnsureSafeParasiteRoute(board,
            bot, anchors, transition, generation, 2, crash);
        if (!waypoint || Distance2d(bot.Position, *waypoint)
                <= DestinationTolerance)
            return std::nullopt;

        BotNativeAction::Candidate candidate = BuildPointMovement(board,
            *waypoint, "parasite_contact_evade",
            ObserveRouteFacts(board, bot).EmergencyClearance);
        candidate.Id.Actor = bot.Guid;
        candidate.Id.EventGeneration = transition.MovementGeneration(bot.Guid);
        return candidate;
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

    static std::optional<BotNativeAction::Candidate> RetainedHazardMovement(
        Blackboard const& board, MagmawParasiteHazardState const& hazardState)
    {
        return hazardState.HasRetainedIntent()
            ? std::optional<BotNativeAction::Candidate>(BuildRetainedMove(
                board, hazardState))
            : std::nullopt;
    }

    static std::optional<BotNativeAction::Candidate> Propose(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& parasite, bool pillarBaiter,
        std::optional<FormationAnchors> const& anchors,
        BotMovementArbitration::Lease const* /*movementLease*/,
        MagmawLaneTransitionState* transition = nullptr,
        MagmawParasiteHazardState* hazardState = nullptr)
    {
        if (!pillarBaiter)
            return std::nullopt;

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
            // The first endpoint contact keeps one retained local escape so
            // native path/GUID churn cannot replan it.  If that escape has
            // completed and the same wave reaches the endpoint again, resume
            // the encounter's fixed left/right contract instead of opening a
            // second arbitrary radial path.  Begin() gives both baiters the
            // same destination and transition identity.
            if ((transition->IsArrived()
                    && transition->OwnsGeneration(generation, 2))
                || (transition->Preempted && hazardState
                    && hazardState->HasCompletedIntent()))
            {
                MagmawLaneTransitionState::Direction const direction =
                    OppositeDirection(transition->Lane);
                Vector3 const redirected = DestinationFor(
                    *anchors, direction);
                if (LaneSafe(board, *anchors, redirected))
                {
                    transition->Begin(generation, 2, direction, redirected);
                    BotNativeAction::Candidate candidate = BuildPointMovement(
                        board, redirected, "parasite_contact_evade",
                        ObserveRouteFacts(board, bot).EmergencyClearance);
                    candidate.Id.Actor = bot.Guid;
                    candidate.Id.EventGeneration = transition->TransitionId;
                    return candidate;
                }
            }
            // On first contact, preserve the cohort transition through one
            // typed local safety preemption and resume it when the endpoint
            // clears. Only a later contact may redirect the shared lane.
            transition->MarkPreempted();
            return BuildMoveAway(board, bot, parasite,
                "parasite_contact_evade", SafeClearance, hazardState);
        }
        if (!destination
            || Distance2d(bot.Position, *destination)
                <= DestinationTolerance)
            return std::nullopt;

        transition->Resume();
        BotNativeAction::Candidate candidate = BuildPointMovement(board,
            *destination, "parasite_contact_evade",
            ObserveRouteFacts(board, bot).EmergencyClearance);
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

    static std::vector<Vector3> LivingParasitePositions(
        Blackboard const& board)
    {
        std::vector<Vector3> positions;
        auto inspect = [&positions](std::vector<ActorSnapshot> const& actors)
        {
            for (ActorSnapshot const& actor : actors)
                if (actor.Alive && IsParasiteEntry(actor.Entry))
                    positions.push_back(actor.Position);
        };
        inspect(board.Hostiles);
        inspect(board.Summons);
        return positions;
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
            return transition.Destination;
        return transition.Destination;
    }

    static BotNativeAction::Candidate BuildPointMovement(
        Blackboard const& board, Vector3 const& point, std::string mechanic,
        bool preemptCasting = false)
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
            point.Z, "parasite_contact_evade", preemptCasting };
        return candidate;
    }

    static BotNativeAction::Candidate BuildRetainedMove(
        Blackboard const& board, MagmawParasiteHazardState const& hazardState)
    {
        ActorSnapshot const* actor = board.FindActor(hazardState.ActorGuid);
        BotNativeAction::Candidate candidate = BuildPointMovement(board,
            hazardState.Destination, "parasite_contact_evade",
            actor && ObserveRouteFacts(board, *actor).EmergencyClearance);
        candidate.Id.Actor = hazardState.ActorGuid;
        candidate.Id.EventGeneration = hazardState.IntentId;
        return candidate;
    }

    static BotNativeAction::Candidate BuildMoveAway(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& danger, std::string mechanic,
        float exitDistance, MagmawParasiteHazardState* hazardState = nullptr)
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
        Vector3 const destination{
            danger.Position.X + dx / length * exitDistance,
            danger.Position.Y + dy / length * exitDistance,
            bot.Position.Z };
        if (hazardState)
        {
            hazardState->Begin(danger.Guid, destination);
            return BuildRetainedMove(board, *hazardState);
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
        candidate.Action = BotNativeAction::Move{ destination.X, destination.Y,
            destination.Z, "parasite_contact_evade",
            ObserveRouteFacts(board, bot).EmergencyClearance };
        return candidate;
    }
};
}

#endif
