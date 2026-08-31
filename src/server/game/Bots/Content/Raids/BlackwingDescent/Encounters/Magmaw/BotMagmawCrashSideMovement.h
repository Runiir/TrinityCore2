#ifndef TRINITY_BOT_MAGMAW_CRASH_SIDE_MOVEMENT_H
#define TRINITY_BOT_MAGMAW_CRASH_SIDE_MOVEMENT_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawEventMovementTransition.h"

#include <cmath>
#include <optional>
#include <string>

namespace BotEncounter
{
struct MagmawCrashSideMovement
{
    bool Resolved = false;
    bool ActorUnsafe = false;
    Vector3 UnsafeSideAnchor;
    Vector3 SafeSideAnchor;
    Vector3 Destination;
};

inline MagmawCrashSideMovement ResolveMagmawCrashSideMovement(
    Vector3 const& actor, Vector3 const& footprint, Vector3 const& support,
    Vector3 const& left, Vector3 const& right, bool fixedLane,
    float supportSideDistance)
{
    MagmawCrashSideMovement result;
    auto finite = [](Vector3 const& point)
    {
        return std::isfinite(point.X) && std::isfinite(point.Y)
            && std::isfinite(point.Z);
    };
    auto distance = [](Vector3 const& first, Vector3 const& second)
    {
        return std::hypot(first.X - second.X, first.Y - second.Y);
    };
    if (!finite(actor) || !finite(footprint) || !finite(support)
        || !finite(left) || !finite(right)
        || !std::isfinite(supportSideDistance)
        || supportSideDistance <= 0.0f)
        return result;

    bool const footprintLeft = distance(footprint, left)
        <= distance(footprint, right);
    result.UnsafeSideAnchor = footprintLeft ? left : right;
    result.SafeSideAnchor = footprintLeft ? right : left;
    result.Resolved = true;
    result.ActorUnsafe = distance(actor, result.UnsafeSideAnchor)
        < distance(actor, result.SafeSideAnchor);
    if (!result.ActorUnsafe)
        return result;

    result.Destination = result.SafeSideAnchor;
    if (!fixedLane)
    {
        float const dx = result.SafeSideAnchor.X - result.UnsafeSideAnchor.X;
        float const dy = result.SafeSideAnchor.Y - result.UnsafeSideAnchor.Y;
        float const length = std::hypot(dx, dy);
        if (length < 0.01f)
            return {};
        result.Destination = {
            support.X + dx / length * supportSideDistance,
            support.Y + dy / length * supportSideDistance,
            actor.Z };
    }
    // X/Y is the encounter decision. Z is only the actor-floor seed passed
    // to native pathing, which remains responsible for following terrain.
    result.Destination.Z = actor.Z;
    return result;
}

struct MagmawCrashSideProposal
{
    bool Hold = false;
    std::optional<BotNativeAction::Candidate> Movement;
};

inline MagmawCrashSideProposal ProposeMagmawCrashSideMovement(
    Blackboard const& board, ActorSnapshot const& bot,
    ActorSnapshot const& danger, Vector3 const& support, Vector3 const& left,
    Vector3 const& right, bool fixedLane, float supportSideDistance,
    MagmawEventMovementTransitionState* transition, float utility)
{
    MagmawCrashSideProposal proposal;
    MagmawCrashSideMovement const movement =
        ResolveMagmawCrashSideMovement(bot.Position, danger.Position, support,
            left, right, fixedLane, supportSideDistance);
    if (!movement.Resolved)
        return proposal;
    if (!movement.ActorUnsafe)
    {
        proposal.Hold = true;
        return proposal;
    }

    if (transition)
    {
        auto const* episode = transition->RetainRoomSideLethal(danger.Guid,
            bot.Guid, "massive_crash_evade", movement.Destination,
            movement.UnsafeSideAnchor, movement.SafeSideAnchor);
        if (episode)
            proposal.Movement = BuildMagmawEventMovement(board, *episode,
                BotActionArbitration::Priority::Survival, utility);
        return proposal;
    }

    MagmawEventMovementTransitionState::Episode episode;
    episode.Mechanic = "massive_crash_evade";
    episode.AssignmentGuid = bot.Guid;
    episode.IntentId = board.Revision;
    episode.Destination = movement.Destination;
    proposal.Movement = BuildMagmawEventMovement(board, episode,
        BotActionArbitration::Priority::Survival, utility);
    return proposal;
}
}

#endif
