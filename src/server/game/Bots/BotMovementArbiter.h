#ifndef TRINITY_BOT_MOVEMENT_ARBITER_H
#define TRINITY_BOT_MOVEMENT_ARBITER_H

#include "Define.h"
#include <cmath>

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
    uint32 MapId = 0;
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
    // Instance zero is the canonical open-world scope.  Map zero remains
    // invalid because it cannot bind a movement request to world geometry.
    return scope.MapId != 0;
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
    return std::fabs(lease.X - request.X) <= epsilon
        && std::fabs(lease.Y - request.Y) <= epsilon
        && std::fabs(lease.Z - request.Z) <= epsilon;
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
    if (lease.MovementOwner == request.MovementOwner)
        return Decision::Refresh;
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
}

inline void Clear(Lease& lease)
{
    lease = {};
}
}

#endif
