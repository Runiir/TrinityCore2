#ifndef TRINITY_BOT_MAGMAW_PLATFORM_NATIVE_PROBE_H
#define TRINITY_BOT_MAGMAW_PLATFORM_NATIVE_PROBE_H

// World-layer observation for BotMagmawPlatformDestination.h. It only reads
// native map floor, mmap path and line-of-sight facts; it never moves the
// actor, rewrites a destination, or relaxes a native path tolerance.

#include "Bots/BotWorldPopulationMgrNativePathValidation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPlatformDestination.h"
#include "GridDefines.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "PathGenerator.h"
#include "Player.h"

#include <optional>

namespace BotEncounter
{
inline bool ObserveMagmawCompleteNativeLeg(PathGenerator& path,
    G3D::Vector3 const& start, G3D::Vector3 const& requested,
    bool fromActor, float referenceZ, G3D::Vector3& endpoint, bool& level)
{
    bool const calculated = fromActor
        ? path.CalculatePath(requested.x, requested.y, requested.z, false)
        : path.CalculatePath(start, requested, false);
    endpoint = path.GetActualEndPosition();
    level = BotWorldMovement::NativePathControlsMatchReferenceLevel(
        path.GetPath(), referenceZ);
    return BotWorldMovement::NativePathIsComplete(calculated, path)
        && BotWorldMovement::NativePathEndpointMatches(endpoint, requested);
}

inline MagmawPlatformDestinationObservation
ObserveMagmawPlatformDestinationNative(Player const* bot,
    Vector3 const& candidate, std::optional<Vector3> const& returnAnchor)
{
    MagmawPlatformDestinationObservation observation;
    if (!bot || !bot->IsInWorld() || !bot->GetMap())
        return observation;
    observation.Observed = true;
    float const floorZ = bot->GetMap()->GetHeight(bot->GetPhaseShift(),
        candidate.X, candidate.Y, candidate.Z + 2.0f, true, 8.0f);
    observation.FloorAvailable = floorZ > INVALID_HEIGHT;
    if (!observation.FloorAvailable)
        return observation;
    observation.FloorZ = floorZ;

    G3D::Vector3 const actor(bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ());
    G3D::Vector3 const requested(candidate.X, candidate.Y, floorZ);
    G3D::Vector3 endpoint;
    PathGenerator outbound(bot);
    observation.OutboundComplete = ObserveMagmawCompleteNativeLeg(outbound,
        actor, requested, true, actor.z, endpoint,
        observation.OutboundLevel);
    observation.EndpointZ = endpoint.z;
    if (!observation.OutboundComplete || !observation.OutboundLevel
        || !returnAnchor)
        return observation;

    observation.ReturnChecked = true;
    G3D::Vector3 const anchor(returnAnchor->X, returnAnchor->Y,
        returnAnchor->Z);
    G3D::Vector3 returnEndpoint;
    PathGenerator inbound(bot);
    observation.ReturnComplete = ObserveMagmawCompleteNativeLeg(inbound,
        endpoint, anchor, false, endpoint.z, returnEndpoint,
        observation.ReturnLevel);
    return observation;
}

inline MagmawNativeMovementProbe BuildMagmawNativeMovementProbe(
    Player const* bot)
{
    MagmawNativeMovementProbe probe;
    if (!bot)
        return probe;
    probe.ObserveDestination = [bot](Vector3 const& candidate,
        std::optional<Vector3> const& returnAnchor)
    {
        return ObserveMagmawPlatformDestinationNative(bot, candidate,
            returnAnchor);
    };
    probe.LineOfSightTo = [bot](ObjectGuid guid)
    {
        Unit const* target = guid.IsEmpty() ? nullptr
            : ObjectAccessor::GetUnit(*bot, guid);
        return target && target->IsInWorld()
            && target->GetMap() == bot->GetMap()
            && bot->IsWithinLOSInMap(target);
    };
    return probe;
}
}

#endif
