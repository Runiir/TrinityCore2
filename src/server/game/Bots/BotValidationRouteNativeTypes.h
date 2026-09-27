#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_TYPES_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_TYPES_H

// Data-only types for native route contracts (interaction, observed
// completion, transport) and their route-scoped runtime state. Included by
// most bot translation units (via BotWorldPopulationMgrRouteState.h): keep it
// small and free of logic. Parsing: BotValidationRouteNativeContract.h;
// decisions: BotValidationRouteNativeLogic.h.

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

struct Point3 { float X = 0.0f, Y = 0.0f, Z = 0.0f; bool Valid = false; };

// Lawful final approach onto a transport surface the static navmesh does not
// reach (BotValidationRouteNativeApproach.h, BotTransportSurfaceMovement).
enum class ApproachMode : std::uint8_t { None, SurfaceWalk, LedgeDrop };
enum class ApproachPhase : std::uint8_t { Idle, Walking, SteppingOff, Falling, Landed };

struct ApproachContract
{
    ApproachMode Mode = ApproachMode::None;
    // Where the member waits on the static navmesh and the approach starts;
    // ledge_drop: past the lip, level with it, where the native fall starts.
    Point3 StartPoint, StepOffPoint;
    float LandingZ = 0.0f;
    float LandingToleranceYards = 1.0f;
    bool LandOnTransport = true;
    float MinHealthAfterFallPct = 0.2f; // health left after the predicted native fall damage
    bool LandInLiquid = false; // ledge_drop: landing under liquid (floats in it); else refused
};

// Elevators and other GAMEOBJECT_TYPE_TRANSPORT platforms.
struct TransportContract
{
    bool Declared = false;
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    // Boarding readiness: a native stop frame (index n = GoState 25 + n, its
    // arrival time reached) or the origin's world Z of a cycling elevator.
    std::int32_t BoardStopFrame = -1;
    bool HasBoardLevel = false;
    float BoardTransportZ = 0.0f;
    // Optional ride destination. Without it, being aboard completes the node.
    std::int32_t ExitStopFrame = -1;
    bool HasExitLevel = false;
    float ExitTransportZ = 0.0f;
    float LevelToleranceYards = 0.75f;
    Point3 WaitPoint, BoardPoint;
    // Optional: a point on the platform over static ground at the exit level
    // (stood on before leaving), and the exit point.
    Point3 DisembarkPoint, ExitPoint;
    float ArrivalToleranceYards = 1.5f;
    // Feet-to-floor distance allowed; at most 1 yd (navmesh step 1.6 yd).
    float FloorToleranceYards = 0.5f;
    // Bound in time, and refused submissions allowed per member.
    std::uint32_t TimeoutMs = 0, MaxSubmissions = 5;
    ApproachContract Approach;
    // instance_boss_state (or any_of/all_of): a fail-fast guard, never a
    // completion; armed with a member aboard, it fails one left behind.
    CompletionContract CompletionOverride;

    bool HasExit() const { return ExitStopFrame >= 0 || HasExitLevel; }
};

// Every declared contract state is scoped to one attempt, wipe and route
// generation; any change resets it.
struct RuntimeScope
{
    std::uint64_t AttemptId = 0, WipeGeneration = 0, RouteGeneration = 0;

    bool operator==(RuntimeScope const& other) const
    { return AttemptId == other.AttemptId && WipeGeneration == other.WipeGeneration
        && RouteGeneration == other.RouteGeneration; }
    bool operator!=(RuntimeScope const& other) const { return !(*this == other); }
};

struct AttemptState { std::uint64_t LastSubmitAtMs = 0; std::uint32_t Attempts = 0; };

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

    void Remember(std::string const& key) { if (!Seen(key)) ObservedPresent.push_back(key); }
};

struct TransportMemberState
{
    bool Boarded = false, Left = false;
    std::uint32_t BoardSubmissions = 0, LeaveSubmissions = 0, FailedSubmissions = 0;
    // A rejection counts at most once per window; the last one names a failure.
    std::uint64_t NextCountedRejectionMs = 0;
    std::string LastRejection;
    // Last floor stood on was this platform's; stationary floorless samples.
    bool PlatformFloorSeen = false;
    std::uint32_t FloorlessObservations = 0;
    std::uint64_t FloorlessSinceMs = 0;
    std::string LastReason;
    ApproachPhase Approach = ApproachPhase::Idle;
    std::uint32_t ResnapMoves = 0; // re-snaps without a verified floor
    std::string LastApproachOutcome;
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
    std::uint64_t OverrideSatisfiedAtMs = 0; // override guard armed at (0: off)

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

// A ride the route took (or would take) to this node's side, run first when
// living members are back on its boarding side (row field recovery_transport).
struct RecoveryTransit
{
    std::string NodeId;
    TransportContract Transport;
    NodeRuntime Runtime; // started while some member needs the ride
    bool PostKillOnly = false; // row post_kill_only: an arrival, after a recorded kill
};

// A wake waiting for the party: since when, last tick seen, who holds it.
struct RecoveryWait { std::uint64_t SinceMs = 0, SeenMs = 0; std::string Holder; };
// First scope and boss reset generation seen at the node; when a trigger held.
struct RecoveryBaseline { RuntimeScope Scope; std::uint64_t Resets = 0, TriggeredAtMs = 0; };

// An earlier node's wake of this node's boss (row field recovery_interaction),
// redone after a wipe (or an observed reset) at this node puts it back to sleep.
struct RecoveryInteraction
{
    std::string NodeId;
    InteractionContract Interaction;
    CompletionContract Completion;
    CompletionContract Ready; CompletionMemory ReadyMemory; // optional: target usable (bell)
    RecoveryBaseline Baseline;
    RecoveryWait Waiting;
    NodeRuntime Runtime; // started while the wake runs
};

struct NodeContract
{
    InteractionContract Interaction;
    CompletionContract Completion;
    TransportContract Transport;
    NodeRuntime Runtime;
    // Recovery rides, then wakes, in route order, before its own contracts.
    std::vector<RecoveryTransit> Recovery;
    std::vector<RecoveryInteraction> RecoveryInteractions;

    bool Declared() const
    {
        return Interaction.Declared || Completion.Declared || Transport.Declared
            || !Recovery.empty() || !RecoveryInteractions.empty();
    }
};
}

#endif
