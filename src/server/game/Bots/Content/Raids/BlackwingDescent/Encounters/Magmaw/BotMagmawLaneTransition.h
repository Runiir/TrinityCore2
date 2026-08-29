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
// Magmaw's route manifest is a focus-fire contract.  Adaptive ownership used
// to bypass the generic boss-mechanics resolver, so keep the same immutable
// constraints beside the encounter assignment that selects the bait pair.
// The assigned fire mage and marksmanship hunter are the only explicit
// exception: they may target and damage a parasite while every other actor is
// confined to Magmaw/the head and single-target profile actions.
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
    ObjectGuid FireMageGuid;
    ObjectGuid MarksmanshipHunterGuid;

    bool IsAssignedBaiter(ObjectGuid guid) const
    {
        return guid == FireMageGuid || guid == MarksmanshipHunterGuid;
    }

    bool AllowsParasiteTarget(ObjectGuid guid) const
    {
        return !Active || IsAssignedBaiter(guid);
    }

    bool TargetAllowed(ObjectGuid guid, uint32 entry) const
    {
        if (!Active)
            return true;
        if (entry == BossEntry || entry == HeadEntry)
            return true;
        return IsAssignedBaiter(guid)
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
        uint32 targetEntry, bool hazardIntentRetained,
        bool outsideLegalMaxRange, bool noLineOfSight) const
    {
        ProfileParameters parameters;
        parameters.TargetAllowed = TargetAllowed(guid, targetEntry);
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
// its destination and danger identity across a native rejection, a generic
// movement-lease expiry, and one or more observation ticks.  The state is
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
    uint64 IntentId = 0;
    Vector3 Destination;
    bool Active = false;

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

    void Begin(ObjectGuid danger, Vector3 destination)
    {
        if (Active)
            return;
        ++IntentId;
        if (!IntentId)
            ++IntentId;
        DangerGuid = danger;
        Destination = destination;
        Active = true;
    }

    bool HasRetainedIntent() const
    {
        return Active;
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        return std::hypot(left.X - right.X, left.Y - right.Y);
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
