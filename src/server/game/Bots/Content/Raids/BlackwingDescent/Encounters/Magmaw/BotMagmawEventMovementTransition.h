#ifndef TRINITY_BOT_MAGMAW_EVENT_MOVEMENT_TRANSITION_H
#define TRINITY_BOT_MAGMAW_EVENT_MOVEMENT_TRANSITION_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"

#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace BotEncounter
{
// Per-bot semantic ownership for lethal Magmaw movement. The native movement
// lease is deliberately short lived; this state retains the selected safe
// point and candidate identity until native arrival or an encounter-scope
// change.
struct MagmawEventMovementTransitionState
{
    struct Episode
    {
        std::string Mechanic;
        ObjectGuid SourceGuid;
        ObjectGuid AssignmentGuid;
        uint64 IntentId = 0;
        Vector3 SourcePosition;
        Vector3 Destination;
        Vector3 UnsafeSideAnchor;
        Vector3 SafeSideAnchor;
        float LethalEnvelope = 0.0f;
        float ArrivalTolerance = 1.0f;
        bool CompleteOnSafeSide = false;
        bool Active = false;
        bool Arrived = false;

        void Reset()
        {
            *this = {};
        }

        bool Matches(ObjectGuid source, ObjectGuid assignment,
            std::string_view mechanic) const
        {
            return IntentId && SourceGuid == source
                && AssignmentGuid == assignment && Mechanic == mechanic;
        }
    };

    std::string ScopeKey;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
    ObjectGuid ActorGuid;
    uint64 NextIntentId = 0;
    Episode Lethal;

    void Reset()
    {
        *this = {};
    }

    void ObserveScope(Blackboard const& board, ObjectGuid actor)
    {
        if (ScopeKey != board.CurrentScope.Key()
            || AttemptId != board.CurrentScope.AttemptId
            || WipeGeneration != board.CurrentScope.WipeGeneration
            || RouteGeneration != board.CurrentScope.RouteGeneration
            || MapId != board.CurrentScope.MapId
            || InstanceId != board.CurrentScope.InstanceId
            || ActorGuid != actor)
        {
            Reset();
            ScopeKey = board.CurrentScope.Key();
            AttemptId = board.CurrentScope.AttemptId;
            WipeGeneration = board.CurrentScope.WipeGeneration;
            RouteGeneration = board.CurrentScope.RouteGeneration;
            MapId = board.CurrentScope.MapId;
            InstanceId = board.CurrentScope.InstanceId;
            ActorGuid = actor;
        }
    }

    void ObserveArrival(Vector3 const& position)
    {
        if (!Lethal.Active)
            return;
        bool const destinationReached =
            Distance2d(position, Lethal.Destination)
                    <= Lethal.ArrivalTolerance
                && std::fabs(position.Z - Lethal.Destination.Z) <= 1.5f;
        bool const lethalEnvelopeCleared = Lethal.LethalEnvelope > 0.0f
            && Distance2d(position, Lethal.SourcePosition)
                > Lethal.LethalEnvelope
            && std::fabs(position.Z - Lethal.SourcePosition.Z) <= 1.5f;
        bool const safeSideReached = Lethal.CompleteOnSafeSide
            && Distance2d(position, Lethal.SafeSideAnchor)
                < Distance2d(position, Lethal.UnsafeSideAnchor)
            && std::fabs(position.Z - Lethal.Destination.Z) <= 1.5f;
        if (!destinationReached && !lethalEnvelopeCleared && !safeSideReached)
            return;
        Lethal.Active = false;
        Lethal.Arrived = true;
    }

    Episode const* RetainLethal(ObjectGuid source, ObjectGuid assignment,
        std::string mechanic, Vector3 destination,
        Vector3 sourcePosition = {}, float lethalEnvelope = 0.0f,
        float arrivalTolerance = 2.5f)
    {
        // Retain one identity while the episode is active. If the caller
        // observes the actor back inside the lethal envelope after arrival,
        // that is a new escape episode even when Trinity reuses the source.
        if (!Lethal.Matches(source, assignment, mechanic) || !Lethal.Active)
            Begin(Lethal, source, assignment, std::move(mechanic), destination,
                sourcePosition, lethalEnvelope, arrivalTolerance);
        return Lethal.Active ? &Lethal : nullptr;
    }

    Episode const* RetainRoomSideLethal(ObjectGuid source,
        ObjectGuid assignment, std::string mechanic, Vector3 destination,
        Vector3 unsafeSideAnchor, Vector3 safeSideAnchor,
        float arrivalTolerance = 2.5f)
    {
        if (!Lethal.Matches(source, assignment, mechanic) || !Lethal.Active)
        {
            Begin(Lethal, source, assignment, std::move(mechanic), destination,
                {}, 0.0f, arrivalTolerance);
            Lethal.UnsafeSideAnchor = unsafeSideAnchor;
            Lethal.SafeSideAnchor = safeSideAnchor;
            Lethal.CompleteOnSafeSide = true;
        }
        return Lethal.Active ? &Lethal : nullptr;
    }

    Episode const* ActiveLethal() const
    {
        return Lethal.Active ? &Lethal : nullptr;
    }

    void RetireActiveLethal()
    {
        if (Lethal.Active)
        {
            Lethal.Active = false;
            Lethal.Arrived = true;
        }
    }

private:
    void Begin(Episode& episode, ObjectGuid source, ObjectGuid assignment,
        std::string mechanic, Vector3 destination, Vector3 sourcePosition,
        float lethalEnvelope, float arrivalTolerance)
    {
        ++NextIntentId;
        if (!NextIntentId)
            ++NextIntentId;
        episode.Mechanic = std::move(mechanic);
        episode.SourceGuid = source;
        episode.AssignmentGuid = assignment;
        episode.IntentId = NextIntentId;
        episode.SourcePosition = sourcePosition;
        episode.Destination = destination;
        episode.UnsafeSideAnchor = {};
        episode.SafeSideAnchor = {};
        episode.LethalEnvelope = lethalEnvelope;
        episode.ArrivalTolerance = arrivalTolerance;
        episode.CompleteOnSafeSide = false;
        episode.Active = true;
        episode.Arrived = false;
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        return std::hypot(left.X - right.X, left.Y - right.Y);
    }
};

inline BotNativeAction::Candidate BuildMagmawEventMovement(
    Blackboard const& board,
    MagmawEventMovementTransitionState::Episode const& episode,
    BotActionArbitration::Priority priority, float utility)
{
    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = board.CurrentScope.Key();
    candidate.Id.Strategy = "adaptive_magmaw";
    candidate.Id.Mechanic = episode.Mechanic;
    candidate.Id.Actor = episode.AssignmentGuid;
    candidate.Id.EventGeneration = episode.IntentId;
    candidate.ActionPriority = priority;
    candidate.Utility = utility;
    candidate.ExpiresAtMs = board.ObservedAtMs + 750;
    candidate.Action = BotNativeAction::Move{ episode.Destination.X,
        episode.Destination.Y, episode.Destination.Z, episode.Mechanic };
    return candidate;
}

inline std::optional<BotNativeAction::Candidate>
RetainMagmawRadialLethalMovement(
    Blackboard const& board, ActorSnapshot const& bot,
    ActorSnapshot const& danger, std::string mechanic, float exitDistance,
    MagmawEventMovementTransitionState& transition, float utility)
{
    float dx = bot.Position.X - danger.Position.X;
    float dy = bot.Position.Y - danger.Position.Y;
    float length = std::hypot(dx, dy);
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
    auto const* episode = transition.RetainLethal(danger.Guid, bot.Guid,
        std::move(mechanic), destination, danger.Position, 12.0f);
    return episode
        ? std::optional<BotNativeAction::Candidate>(BuildMagmawEventMovement(
            board, *episode, BotActionArbitration::Priority::Survival, utility))
        : std::nullopt;
}

}

#endif
