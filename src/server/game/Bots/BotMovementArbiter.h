#ifndef TRINITY_BOT_MOVEMENT_ARBITER_H
#define TRINITY_BOT_MOVEMENT_ARBITER_H

#include "Define.h"
#include <cmath>
#include <limits>

namespace BotMovementArbitration
{
enum class Owner : uint8
{
    None,
    Route,
    Formation,
    CombatRange,
    Support,
    Mechanic,
    Hazard,
    Recovery
};

enum class Priority : uint8
{
    Idle = 0,
    Route = 20,
    Formation = 40,
    Combat = 60,
    Support = 80,
    Mechanic = 100,
    Hazard = 120,
    Recovery = 140
};

struct Scope
{
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    uint32 MapId = std::numeric_limits<uint32>::max();
    uint32 InstanceId = 0;
};

struct Lease
{
    Owner MovementOwner = Owner::None;
    Priority MovementPriority = Priority::Idle;
    uint64 ExpiresAtMs = 0;
    Scope MovementScope;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    // A non-zero identity makes the destination target-aware. Coordinates are
    // still retained for evidence and path preflight, but a moving unit does
    // not become a new destination every decision tick.
    uint64 DynamicTargetGuid = 0;
};

struct Request
{
    Owner MovementOwner = Owner::None;
    Priority MovementPriority = Priority::Idle;
    uint64 ExpiresAtMs = 0;
    Scope MovementScope;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    uint64 DynamicTargetGuid = 0;
};

// A lease is a short arbitration promise.  Native MotionMaster movement is a
// separate, set-and-forget generator and may outlive that promise by one or
// more decision ticks.  Keep the admitted path identity without an expiry so
// callers can reconcile an already-running generator before submitting a
// duplicate command or allowing a lower-priority request to replace it.
struct NativePathReceipt
{
    bool Active = false;
    Lease Path;
};

enum class Decision : uint8
{
    Acquire,
    Refresh,
    Preempt,
    PreserveExisting,
    RejectInvalid
};

constexpr bool ValidScope(Scope const& scope)
{
    // Map zero is Eastern Kingdoms and instance zero is the canonical
    // open-world scope. Reserve UINT32_MAX for an uninitialized scope so
    // ordinary player movement on map zero remains fully arbitrated.
    return scope.MapId != std::numeric_limits<uint32>::max();
}

constexpr bool SameScope(Scope const& left, Scope const& right)
{
    return left.AttemptId == right.AttemptId
        && left.WipeGeneration == right.WipeGeneration
        && left.RouteGeneration == right.RouteGeneration
        && left.MapId == right.MapId
        && left.InstanceId == right.InstanceId;
}

inline bool SameDestination(Lease const& lease, Request const& request, float epsilon = 0.1f)
{
    if (lease.DynamicTargetGuid || request.DynamicTargetGuid)
        return lease.DynamicTargetGuid != 0
            && lease.DynamicTargetGuid == request.DynamicTargetGuid;

    return std::fabs(lease.X - request.X) <= epsilon
        && std::fabs(lease.Y - request.Y) <= epsilon
        && std::fabs(lease.Z - request.Z) <= epsilon;
}

inline bool MatchesNativePath(NativePathReceipt const& receipt,
    Request const& request, float epsilon = 0.1f)
{
    return receipt.Active
        && receipt.Path.MovementOwner == request.MovementOwner
        && SameScope(receipt.Path.MovementScope, request.MovementScope)
        && SameDestination(receipt.Path, request, epsilon);
}

constexpr bool ValidRequest(Request const& request, uint64 nowMs)
{
    return request.MovementOwner != Owner::None
        && request.MovementPriority != Priority::Idle
        && request.ExpiresAtMs > nowMs
        && ValidScope(request.MovementScope);
}

inline Decision Evaluate(Lease const& lease, Request const& request, uint64 nowMs)
{
    if (!ValidRequest(request, nowMs))
        return Decision::RejectInvalid;
    if (lease.MovementOwner == Owner::None || lease.ExpiresAtMs <= nowMs
        || !SameScope(lease.MovementScope, request.MovementScope))
        return Decision::Acquire;
    if (lease.MovementOwner == request.MovementOwner
        && SameDestination(lease, request))
        return Decision::Refresh;
    // A validated point approach may be submitted before native combat has a
    // victim. Once combat binds that same owner's live target, upgrade the
    // point lease immediately instead of waiting for its expiry. Retargeting
    // one live unit to another remains protected by the normal priority rule.
    if (lease.MovementOwner == request.MovementOwner
        && !lease.DynamicTargetGuid && request.DynamicTargetGuid)
        return Decision::Preempt;
    if (uint8(request.MovementPriority) > uint8(lease.MovementPriority))
        return Decision::Preempt;
    return Decision::PreserveExisting;
}

inline void Apply(Lease& lease, Request const& request)
{
    lease.MovementOwner = request.MovementOwner;
    lease.MovementPriority = request.MovementPriority;
    lease.ExpiresAtMs = request.ExpiresAtMs;
    lease.MovementScope = request.MovementScope;
    lease.X = request.X;
    lease.Y = request.Y;
    lease.Z = request.Z;
    lease.DynamicTargetGuid = request.DynamicTargetGuid;
}

inline void Clear(Lease& lease)
{
    lease = {};
}
}

#endif
