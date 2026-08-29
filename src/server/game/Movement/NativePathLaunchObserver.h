#ifndef TRINITY_NATIVE_PATH_LAUNCH_OBSERVER_H
#define TRINITY_NATIVE_PATH_LAUNCH_OBSERVER_H

#include "Define.h"

#include <G3D/Vector3.h>
#include <vector>

namespace Movement
{
using NativePathLaunchControls = std::vector<G3D::Vector3>;

enum class NativePathLaunchCoordinateSpace : uint8
{
    World,
    TransportOffset
};

class NativePathLaunchObserver;

// The observer must outlive every generator that receives this context.
// Ordinary callers use the null default. The context is diagnostic-only and
// must never participate in movement selection or generator lifecycle logic.
struct NativePathLaunchContext
{
    uint32 Version = 0;
    uint64 ReceiptId = 0;
    uint64 ActorGuid = 0;
    uint32 MapId = 0;
    uint64 IntentFingerprint = 0;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    uint32 InstanceId = 0;
    NativePathLaunchObserver* Observer = nullptr;

    explicit operator bool() const
    {
        return ReceiptId && ActorGuid && Observer;
    }
};

class NativePathLaunchObserver
{
public:
    virtual ~NativePathLaunchObserver() = default;

    virtual void OnMotionMasterSubmission(
        NativePathLaunchContext const& context, uint32 slot,
        uint32 generatorType) = 0;
    virtual void OnPointGeneratorInitialize(
        NativePathLaunchContext const& context) = 0;
    virtual void OnSplinePreparation(NativePathLaunchContext const& context,
        bool secondPathAttempted, bool secondPathCalculated,
        uint32 secondPathType,
        NativePathLaunchControls const& secondPathControls,
        bool directTwoPointSelected, bool directTwoPointFallback) = 0;
    virtual void OnSplineLaunch(NativePathLaunchContext const& context,
        NativePathLaunchControls const& launchedControls,
        NativePathLaunchCoordinateSpace coordinateSpace, bool succeeded,
        bool finalized, float actorX, float actorY, float actorZ) = 0;
};
}

#endif
