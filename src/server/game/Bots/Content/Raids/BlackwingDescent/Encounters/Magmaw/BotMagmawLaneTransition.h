#ifndef TRINITY_BOT_MAGMAW_LANE_TRANSITION_H
#define TRINITY_BOT_MAGMAW_LANE_TRANSITION_H

#include "Bots/BotEncounterBlackboard.h"
#include "ObjectGuid.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <utility>

namespace BotEncounter
{
// This is encounter-owned semantic state, not a movement arbitration lease.
// The lease may expire while MotionMaster is still traversing the point path;
// this object keeps the mechanic generation and its destination immutable
// until the native path reaches both assigned baiters.
struct MagmawLaneTransitionState
{
    enum class Direction : uint8
    {
        None,
        Left,
        Right
    };

    std::string ScopeKey;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
    ObjectGuid MageGuid;
    ObjectGuid HunterGuid;
    uint64 MechanicGeneration = 0;
    uint8 MechanicKind = 0;
    uint64 TransitionId = 0;
    Direction Lane = Direction::None;
    Vector3 Destination;
    bool Committed = false;
    bool MageArrived = false;
    bool HunterArrived = false;
    bool Preempted = false;
    // A changed parasite GUID observed before both baiters arrive is still
    // churn inside the admitted mechanic. Record the generation visible at
    // the arrival boundary so only a later event can open a new transition.
    uint64 ArrivedGeneration = 0;
    uint8 ArrivedMechanicKind = 0;
    uint64 ArrivalObservedRevision = 0;
    // Zero is a valid sealed boundary when the prior mechanic has despawned;
    // keep an explicit bit so it cannot be mistaken for an unobserved
    // arrival generation.
    bool ArrivalGenerationCaptured = false;

    bool HasAssignedBaiters() const
    {
        return !MageGuid.IsEmpty() && !HunterGuid.IsEmpty();
    }

    bool IsBaiter(ObjectGuid guid) const
    {
        return guid == MageGuid || guid == HunterGuid;
    }

    bool IsArrived() const
    {
        return Committed && MageArrived && HunterArrived;
    }

    void Reset()
    {
        *this = {};
    }

    void ObserveScope(Blackboard const& board)
    {
        std::string const scopeKey = board.CurrentScope.Key();
        if (ScopeKey != scopeKey || AttemptId != board.CurrentScope.AttemptId
            || WipeGeneration != board.CurrentScope.WipeGeneration
            || RouteGeneration != board.CurrentScope.RouteGeneration
            || MapId != board.CurrentScope.MapId
            || InstanceId != board.CurrentScope.InstanceId)
        {
            Reset();
            ScopeKey = scopeKey;
            AttemptId = board.CurrentScope.AttemptId;
            WipeGeneration = board.CurrentScope.WipeGeneration;
            RouteGeneration = board.CurrentScope.RouteGeneration;
            MapId = board.CurrentScope.MapId;
            InstanceId = board.CurrentScope.InstanceId;
        }
    }

    void AssignBaiters(ObjectGuid mage, ObjectGuid hunter)
    {
        if (HasAssignedBaiters())
            return;
        MageGuid = mage;
        HunterGuid = hunter;
    }

    void ObserveArrival(ObjectGuid guid, Vector3 const& position,
        float tolerance, uint64 revision = 0)
    {
        if (!Committed || Distance2d(position, Destination) > tolerance)
            return;
        if (guid == MageGuid)
            MageArrived = true;
        else if (guid == HunterGuid)
            HunterArrived = true;
        if (IsArrived() && !ArrivalObservedRevision)
            ArrivalObservedRevision = revision;
    }

    bool GenerationRetired(uint64 generation, uint8 kind) const
    {
        return IsArrived() && ArrivalGenerationCaptured
            && (ArrivedGeneration != generation
                || ArrivedMechanicKind != kind);
    }

    void RecordArrivalGeneration(uint64 generation, uint8 kind,
        uint64 revision)
    {
        if (IsArrived() && !ArrivalGenerationCaptured)
        {
            ArrivedGeneration = generation;
            ArrivedMechanicKind = kind;
            ArrivalObservedRevision = revision;
            ArrivalGenerationCaptured = true;
        }
    }

    void SealNoMechanicArrival(uint64 revision)
    {
        RecordArrivalGeneration(0, 0, revision);
    }

    bool OwnsGeneration(uint64 generation, uint8 kind) const
    {
        return Committed && MechanicGeneration == generation
            && MechanicKind == kind;
    }

    void Begin(uint64 generation, uint8 kind, Direction direction,
        Vector3 destination)
    {
        ++TransitionId;
        if (!TransitionId)
            ++TransitionId;
        MechanicGeneration = generation;
        MechanicKind = kind;
        Lane = direction;
        Destination = destination;
        Committed = true;
        MageArrived = false;
        HunterArrived = false;
        Preempted = false;
        ArrivedGeneration = 0;
        ArrivedMechanicKind = 0;
        ArrivalObservedRevision = 0;
        ArrivalGenerationCaptured = false;
    }

    void MarkPreempted()
    {
        if (Committed)
            Preempted = true;
    }

    void Resume()
    {
        Preempted = false;
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        return std::hypot(left.X - right.X, left.Y - right.Y);
    }
};
}

#endif
