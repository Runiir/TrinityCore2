#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_TYPES_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_TYPES_H

// Data-only types for native route contracts (interaction, observed
// completion, transport) and their route-scoped runtime state.
//
// This header is included by BotWorldPopulationMgrRouteState.h and therefore
// by most bot translation units: keep it small and free of logic. Parsing
// lives in BotValidationRouteNativeContract.h (manifest loader, tests) and
// decisions in BotValidationRouteNativeLogic.h (route runtime, tests).

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace BotValidationRouteNative
{
enum class InteractionAction : std::uint8_t
{
    None,
    GameObjectUse,
    GossipSelect,
    GossipSelectSequence,
    SpellClick,
    VehicleEnter,
    AreaTrigger
};

enum class TargetType : std::uint8_t { None, Any, GameObject, Creature };

struct InteractionContract
{
    bool Declared = false;
    InteractionAction Action = InteractionAction::None;
    std::string ActionName;
    TargetType Target = TargetType::None;
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    std::vector<std::uint32_t> Menus;
    std::uint32_t Option = 0;
    // Vehicle seat index; -1 lets the native spellclick choose.
    std::int32_t Seat = -1;
    std::uint32_t AreaTriggerId = 0;
    // Owner selection. When none is declared the lowest living GUID owns the
    // interaction (the historical behaviour).
    std::string OwnerRole;
    std::uint32_t OwnerRosterSlot = 0;
    std::uint32_t BackupRosterSlot = 0;
    // Required: every declared interaction is bounded in time.
    std::uint32_t TimeoutMs = 0;
    // Required: every interaction commits native requests, so attempts are
    // bounded and each one gets a settle window before the next.
    std::uint32_t MaxAttempts = 0;
    std::uint32_t RetryIntervalMs = 0;
    bool Gather = false;
    float GatherRadiusYards = 0.0f;
    // Creature targets only, at most INTERACTION_DISTANCE; 0 means native.
    // Gameobjects always use the native GameObject::IsAtInteractDistance.
    float RangeYards = 0.0f;

    bool IsGossip() const
    {
        return Action == InteractionAction::GossipSelect
            || Action == InteractionAction::GossipSelectSequence;
    }

    bool LegacyOwner() const { return OwnerRole.empty() && !OwnerRosterSlot; }
};

enum class CompletionKind : std::uint8_t
{
    None,
    GameObjectSelectable,
    GameObjectDespawned,
    BossSummoned,
    CreatureSummoned,
    AuraPresent,
    CreatureAggressiveWithVictim,
    CreatureGroundedAggressiveOrEngaged,
    InstanceBossState,
    OnTransport,
    VehicleSeated,
    TransportAtStop,
    AnyOf,
    AllOf
};

enum class MemberScope : std::uint8_t { All, Any, Owner };

struct CompletionContract
{
    bool Declared = false;
    CompletionKind Kind = CompletionKind::None;
    std::string KindName;
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    std::uint32_t SpellId = 0;
    std::int32_t BossIndex = -1;
    std::uint32_t BossState = 0;
    std::uint32_t TransportEntry = 0;
    std::uint64_t TransportSpawnId = 0;
    // Stop frame index n means GoState GO_STATE_TRANSPORT_STOPPED + n (25+n),
    // which scripts write as GO_STATE_TRANSPORT_ACTIVE + (n + 1).
    std::int32_t StopFrame = -1;
    std::uint32_t VehicleEntry = 0;
    std::int32_t Seat = -1;
    MemberScope Scope = MemberScope::All;
    // gameobject_despawned only completes after the object was observed
    // spawned in the same route scope.
    bool RequireObservedPresent = true;
    // Optional bound for completion-only (wait) nodes; top level only.
    std::uint32_t TimeoutMs = 0;
    std::vector<CompletionContract> Children;

    bool UsesOwnerScope() const
    {
        if (Scope == MemberScope::Owner)
            return true;
        for (CompletionContract const& child : Children)
            if (child.UsesOwnerScope())
                return true;
        return false;
    }
};

struct Point3
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    bool Valid = false;
};

// Elevators and other GAMEOBJECT_TYPE_TRANSPORT platforms.
struct TransportContract
{
    bool Declared = false;
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    // Boarding readiness: a native stop frame (index n = GoState 25 + n, with
    // its arrival time reached) or the platform origin's world Z for
    // continuously cycling elevators.
    std::int32_t BoardStopFrame = -1;
    bool HasBoardLevel = false;
    float BoardTransportZ = 0.0f;
    // Optional ride destination. Without it, being aboard completes the node.
    std::int32_t ExitStopFrame = -1;
    bool HasExitLevel = false;
    float ExitTransportZ = 0.0f;
    float LevelToleranceYards = 0.75f;
    Point3 WaitPoint;
    Point3 BoardPoint;
    // Optional point on the platform, over static ground at the exit level,
    // to stand on before leaving when the boarding spot is not over ground.
    Point3 DisembarkPoint;
    Point3 ExitPoint;
    float ArrivalToleranceYards = 1.5f;
    // Maximum distance between the bot's feet and the floor it stands on;
    // at most 1 yd, well below the 1.6 yd navmesh step height.
    float FloorToleranceYards = 0.5f;
    std::uint32_t TimeoutMs = 0;
    // Failed board/leave submissions allowed per member before the node fails.
    std::uint32_t MaxSubmissions = 5;

    bool HasExit() const { return ExitStopFrame >= 0 || HasExitLevel; }
};

// Every declared contract state is scoped to one attempt, wipe and route
// generation; any change resets it.
struct RuntimeScope
{
    std::uint64_t AttemptId = 0;
    std::uint64_t WipeGeneration = 0;
    std::uint64_t RouteGeneration = 0;

    bool operator==(RuntimeScope const& other) const
    {
        return AttemptId == other.AttemptId && WipeGeneration == other.WipeGeneration
            && RouteGeneration == other.RouteGeneration;
    }
    bool operator!=(RuntimeScope const& other) const { return !(*this == other); }
};

struct AttemptState
{
    std::uint64_t LastSubmitAtMs = 0;
    std::uint32_t Attempts = 0;
};

struct CompletionMemory
{
    std::vector<std::string> ObservedPresent;

    bool Seen(std::string const& key) const
    {
        for (std::string const& seen : ObservedPresent)
            if (seen == key)
                return true;
        return false;
    }

    void Remember(std::string const& key)
    {
        if (!Seen(key))
            ObservedPresent.push_back(key);
    }
};

struct TransportMemberState
{
    bool Boarded = false;
    bool Left = false;
    std::uint32_t BoardSubmissions = 0;
    std::uint32_t LeaveSubmissions = 0;
    std::uint32_t FailedSubmissions = 0;
    // The last floor this member stood on was this platform's own surface.
    bool PlatformFloorSeen = false;
    // Consecutive stationary observations with no floor at all since then.
    std::uint32_t FloorlessObservations = 0;
    std::uint64_t FloorlessSinceMs = 0;
    std::string LastReason;
};

struct NodeRuntime
{
    RuntimeScope Scope;
    bool Started = false;
    std::uint64_t StartedAtMs = 0;
    AttemptState Attempt;
    CompletionMemory Completion;
    std::map<std::uint64_t, TransportMemberState> TransportMembers;
    // Completion is evaluated once per cohort observation tick.
    bool VerdictValid = false;
    std::uint64_t VerdictTick = 0;
    bool VerdictSatisfied = false;
    std::string VerdictReason;
    bool CompletionRecorded = false;
    bool FailureRecorded = false;
    std::string LastDiagnostic;

    void Enter(RuntimeScope const& scope, std::uint64_t nowMs)
    {
        if (Started && Scope == scope)
            return;
        *this = NodeRuntime();
        Scope = scope;
        Started = true;
        StartedAtMs = nowMs;
    }
};

struct NodeContract
{
    InteractionContract Interaction;
    CompletionContract Completion;
    TransportContract Transport;
    NodeRuntime Runtime;

    bool Declared() const
    {
        return Interaction.Declared || Completion.Declared || Transport.Declared;
    }
};
}

#endif
