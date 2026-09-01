#ifndef TRINITY_BOT_MAGMAW_LANE_TRANSITION_H
#define TRINITY_BOT_MAGMAW_LANE_TRANSITION_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawParasiteRoute.h"
#include "ObjectGuid.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <string_view>
#include <utility>

namespace BotEncounter
{
// Magmaw's route manifest is a focus-fire contract.  Adaptive ownership used
// to bypass the generic boss-mechanics resolver, so keep the same immutable
// constraints beside the encounter assignment that selects the bait pair.
// The assigned fire mage and marksmanship hunter retain broad parasite
// ownership. Every other DPS is confined to Magmaw/the head unless one exact
// live parasite is attributable as that actor's personal threat.
struct MagmawParasiteCombatContract
{
    struct ProfileParameters
    {
        bool TargetAllowed = false;
        bool ForbidAreaDamage = false;
        bool AllowMultidot = false;
        bool DeferCombatRange = false;

        bool AllowsAction(bool areaDamage, bool multidot, bool chained,
            bool petAreaDamage, bool persistentAreaDamage) const
        {
            if (!TargetAllowed)
                return false;
            if (ForbidAreaDamage
                && (areaDamage || chained || petAreaDamage
                    || persistentAreaDamage))
                return false;
            return AllowMultidot || !multidot;
        }
    };

    static constexpr uint32 BossEntry = 41570;
    static constexpr uint32 HeadEntry = 42347;
    static constexpr uint32 ParasiteEntry = 41806;
    static constexpr uint32 ParasiteAltEntry = 42321;

    bool Active = false;
    bool AllowAreaDamage = false;
    bool AllowMultidot = false;
    bool AllowPetAreaDamage = false;
    bool AllowPersistentAreaDamage = false;
    ObjectGuid ActorGuid;
    ObjectGuid PersonalThreatGuid;
    ObjectGuid FireMageGuid;
    ObjectGuid MarksmanshipHunterGuid;

    bool IsAssignedBaiter(ObjectGuid guid) const
    {
        return guid == FireMageGuid || guid == MarksmanshipHunterGuid;
    }

    bool AllowsParasiteTarget(ObjectGuid guid, ObjectGuid targetGuid) const
    {
        return !Active || IsAssignedBaiter(guid)
            || (guid == ActorGuid && !PersonalThreatGuid.IsEmpty()
                && targetGuid == PersonalThreatGuid);
    }

    bool TargetAllowed(ObjectGuid guid, ObjectGuid targetGuid,
        uint32 entry) const
    {
        if (!Active)
            return true;
        if (entry == BossEntry || entry == HeadEntry)
            return true;
        return AllowsParasiteTarget(guid, targetGuid)
            && (entry == ParasiteEntry || entry == ParasiteAltEntry);
    }

    bool AllowsAreaDamageFor(ObjectGuid guid) const
    {
        return !Active || IsAssignedBaiter(guid) || AllowAreaDamage;
    }

    bool AllowsMultidotFor(ObjectGuid guid) const
    {
        return !Active || IsAssignedBaiter(guid) || AllowMultidot;
    }

    bool AllowsPetAreaDamageFor(ObjectGuid guid) const
    {
        return !Active || IsAssignedBaiter(guid) || AllowPetAreaDamage;
    }

    bool AllowsPersistentAreaDamageFor(ObjectGuid guid) const
    {
        return !Active || IsAssignedBaiter(guid)
            || AllowPersistentAreaDamage;
    }

    bool ShouldDeferCombatRange(bool hazardIntentRetained,
        bool outsideLegalMaxRange, bool noLineOfSight) const
    {
        // A retained contact-escape intent owns movement until native
        // progress reaches safety.  Legal profile DPS may coexist with it;
        // only the range/LOS reconciliation that would replace movement is
        // deferred.
        return Active && hazardIntentRetained
            && (outsideLegalMaxRange || noLineOfSight);
    }

    ProfileParameters ResolveProfileParameters(ObjectGuid guid,
        ObjectGuid targetGuid, uint32 targetEntry, bool hazardIntentRetained,
        bool outsideLegalMaxRange, bool noLineOfSight) const
    {
        ProfileParameters parameters;
        parameters.TargetAllowed = TargetAllowed(guid, targetGuid,
            targetEntry);
        parameters.ForbidAreaDamage = Active
            && (!AllowsAreaDamageFor(guid)
                || !AllowsPetAreaDamageFor(guid)
                || !AllowsPersistentAreaDamageFor(guid));
        parameters.AllowMultidot = !Active || AllowsMultidotFor(guid);
        parameters.DeferCombatRange = ShouldDeferCombatRange(
            hazardIntentRetained, outsideLegalMaxRange, noLineOfSight);
        return parameters;
    }
};

// Local contact evasion is per-bot, unlike the shared two-baiter lane.  Keep
// its destination and danger identity across a generic movement-lease expiry
// and one or more observation ticks. Permanent native path rejection retires
// the exact endpoint until the actor or danger geometry changes. The state is
// deliberately value-only so replay can exercise the production transition.
struct MagmawParasiteHazardState
{
    std::string ScopeKey;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
    ObjectGuid ActorGuid;
    ObjectGuid DangerGuid;
    Vector3 DangerPosition;
    bool DangerPositionAvailable = false;
    Vector3 ActorPosition;
    bool ActorPositionAvailable = false;
    uint64 IntentId = 0;
    Vector3 Destination;
    bool Active = false;
    Vector3 RejectedDestination;
    Vector3 RejectedActorPosition;
    Vector3 RejectedDangerPosition;
    bool Rejected = false;
    bool RejectedGeometryAvailable = false;

    static constexpr float GeometryChangeTolerance = 0.25f;

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

    void ObserveNativeProgress(Blackboard const& board, Vector3 const& position,
        float tolerance, float safeClearance)
    {
        if (!Active)
            return;

        bool parasiteStillUnsafe = false;
        auto inspect = [&](std::vector<ActorSnapshot> const& actors)
        {
            for (ActorSnapshot const& actor : actors)
                if (actor.Alive && (actor.Entry == 41806 || actor.Entry == 42321)
                    && Distance2d(position, actor.Position) < safeClearance)
                {
                    parasiteStillUnsafe = true;
                    return;
                }
        };
        inspect(board.Hostiles);
        if (!parasiteStillUnsafe)
            inspect(board.Summons);

        // Parasite GUIDs and nearest-target ownership churn as the pack moves.
        // One native escape remains active until its destination is reached or
        // the bot is clear of the whole living pack, not merely its first GUID.
        if (!parasiteStillUnsafe
            || Distance2d(position, Destination) <= tolerance)
            Active = false;
    }

    bool Begin(ObjectGuid danger, Vector3 dangerPosition,
        Vector3 actorPosition, Vector3 destination)
    {
        if (Active)
            return true;
        if (Rejected
            && SamePoint(destination, RejectedDestination)
            && (!RejectedGeometryAvailable
                || (!GeometryChanged(actorPosition, RejectedActorPosition)
                    && !GeometryChanged(dangerPosition,
                        RejectedDangerPosition))))
            return false;
        ++IntentId;
        if (!IntentId)
            ++IntentId;
        DangerGuid = danger;
        DangerPosition = dangerPosition;
        DangerPositionAvailable = true;
        ActorPosition = actorPosition;
        ActorPositionAvailable = true;
        Destination = destination;
        Active = true;
        Rejected = false;
        RejectedGeometryAvailable = false;
        return true;
    }

    bool Begin(ObjectGuid danger, Vector3 dangerPosition, Vector3 destination)
    {
        bool const begun = Begin(danger, dangerPosition, {}, destination);
        ActorPositionAvailable = false;
        return begun;
    }

    // Compatibility for value fixtures that intentionally do not bind source
    // geometry. Such an intent remains strict at native endpoint admission.
    bool Begin(ObjectGuid danger, Vector3 destination)
    {
        bool const begun = Begin(danger, {}, {}, destination);
        DangerPositionAvailable = false;
        ActorPositionAvailable = false;
        return begun;
    }

    bool ObserveTerminalNativeRejection(ObjectGuid actor, uint64 intentId,
        Vector3 const& destination, std::string_view reason)
    {
        if (!IsPermanentNativeRejection(reason) || !Active
            || ActorGuid != actor || IntentId != intentId
            || !SamePoint(Destination, destination))
            return false;
        RejectedDestination = Destination;
        RejectedActorPosition = ActorPosition;
        RejectedDangerPosition = DangerPosition;
        Rejected = true;
        RejectedGeometryAvailable = ActorPositionAvailable
            && DangerPositionAvailable;
        Active = false;
        return true;
    }

    bool HasRetainedIntent() const
    {
        return Active;
    }

    bool HasCompletedIntent() const
    {
        return !Active && IntentId != 0;
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        return std::hypot(left.X - right.X, left.Y - right.Y);
    }

    static bool IsPermanentNativeRejection(std::string_view reason)
    {
        return reason == "route_destination_endpoint_mismatch"
            || reason == "route_destination_unreachable"
            || reason == "route_destination_partial_path"
            || reason == "route_destination_missing_mmap";
    }

    static bool SamePoint(Vector3 const& left, Vector3 const& right)
    {
        return std::fabs(left.X - right.X) <= 0.001f
            && std::fabs(left.Y - right.Y) <= 0.001f
            && std::fabs(left.Z - right.Z) <= 0.001f;
    }

    static bool GeometryChanged(Vector3 const& current,
        Vector3 const& rejected)
    {
        return Distance2d(current, rejected) > GeometryChangeTolerance
            || std::fabs(current.Z - rejected.Z) > GeometryChangeTolerance;
    }
};

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
    MagmawParasiteRoutePlan MageParasiteRoute;
    MagmawParasiteRoutePlan HunterParasiteRoute;
    uint8 MageRoutePoint = 0;
    uint8 HunterRoutePoint = 0;
    uint32 MageRouteRevision = 0;
    uint32 HunterRouteRevision = 0;
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
        ObserveRouteProgress(guid, position, tolerance);
        if (!Committed
            || !MagmawParasiteRoute::SameNavigationFloor(position,
                Destination)
            || Distance2d(position, Destination) > tolerance)
            return;
        if (guid == MageGuid)
            MageArrived = true;
        else if (guid == HunterGuid)
            HunterArrived = true;
        if (IsArrived() && !ArrivalObservedRevision)
            ArrivalObservedRevision = revision;
    }

    void ObserveRouteProgress(ObjectGuid guid, Vector3 const& position,
        float tolerance)
    {
        MagmawParasiteRoutePlan const* route = RouteFor(guid);
        if (!Committed || !route || route->Empty())
            return;
        uint8* nextPoint = guid == MageGuid ? &MageRoutePoint
            : guid == HunterGuid ? &HunterRoutePoint : nullptr;
        if (!nextPoint)
            return;
        while (*nextPoint < route->PointCount
            && MagmawParasiteRoute::SameNavigationFloor(position,
                route->Points[*nextPoint])
            && Distance2d(position, route->Points[*nextPoint])
                <= tolerance)
            ++*nextPoint;
    }

    uint8 NextRoutePoint(ObjectGuid guid) const
    {
        return guid == MageGuid ? MageRoutePoint
            : guid == HunterGuid ? HunterRoutePoint
            : 0;
    }

    Vector3 const* NextRouteDestination(ObjectGuid guid) const
    {
        MagmawParasiteRoutePlan const* route = RouteFor(guid);
        uint8 const nextPoint = NextRoutePoint(guid);
        return route && nextPoint < route->PointCount
            ? &route->Points[nextPoint] : nullptr;
    }

    MagmawParasiteRoutePlan const* RouteFor(ObjectGuid guid) const
    {
        return guid == MageGuid ? &MageParasiteRoute
            : guid == HunterGuid ? &HunterParasiteRoute : nullptr;
    }

    bool HasRoute(ObjectGuid guid) const
    {
        MagmawParasiteRoutePlan const* route = RouteFor(guid);
        return route && !route->Empty();
    }

    uint64 MovementGeneration(ObjectGuid guid) const
    {
        uint64 const revision = guid == MageGuid ? MageRouteRevision
            : guid == HunterGuid ? HunterRouteRevision : 0;
        return TransitionId ^ (revision << 32);
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
        MageParasiteRoute = {};
        HunterParasiteRoute = {};
        MageRoutePoint = 0;
        HunterRoutePoint = 0;
        MageRouteRevision = 0;
        HunterRouteRevision = 0;
        Committed = true;
        MageArrived = false;
        HunterArrived = false;
        Preempted = false;
        ArrivedGeneration = 0;
        ArrivedMechanicKind = 0;
        ArrivalObservedRevision = 0;
        ArrivalGenerationCaptured = false;
    }

    void BeginParasiteRoute(uint64 generation, uint8 kind,
        Direction direction, ObjectGuid guid, MagmawParasiteRoutePlan route)
    {
        Begin(generation, kind, direction, route.Destination());
        AttachParasiteRoute(guid, std::move(route));
    }

    void AttachParasiteRoute(ObjectGuid guid, MagmawParasiteRoutePlan route)
    {
        Destination = route.Destination();
        if (guid == MageGuid)
        {
            if (!MageParasiteRoute.Empty())
                ++MageRouteRevision;
            MageParasiteRoute = std::move(route);
            MageRoutePoint = 0;
        }
        else if (guid == HunterGuid)
        {
            if (!HunterParasiteRoute.Empty())
                ++HunterRouteRevision;
            HunterParasiteRoute = std::move(route);
            HunterRoutePoint = 0;
        }
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
