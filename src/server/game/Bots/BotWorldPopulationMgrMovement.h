#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_H

#include "Bots/BotMovementArbiter.h"
#include "Movement/PathEndpoint.h"

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

class Unit;

// The movement service receives an already-selected intent.  It does not
// inspect the combat rotation, quest policy, or encounter policy that chose
// the intent.  Compatibility callers may still fill the two path-policy
// switches below; the executor only treats them as mechanical path-admission
// requirements.
namespace BotWorldMovement
{
struct NativePathProofObservation;

enum class ExecutionDisposition : std::uint8_t
{
    Unavailable,
    Rejected,
    Retained,
    Submitted
};

// Typed policy-to-native feedback. This value is written directly by the
// movement planner/executor; diagnostic JSON is only a serializer and is
// never read back into gameplay state.
struct ExecutionObservation
{
    bool Available = false;
    ExecutionDisposition Disposition = ExecutionDisposition::Unavailable;
    std::uint64_t ReceiptId = 0;
    float RequestedX = 0.0f;
    float RequestedY = 0.0f;
    float RequestedZ = 0.0f;
    bool PlannerAccepted = false;
    bool NativeSubmitted = false;
    PathEndpointResult EndpointResult = PathEndpointResult::Unavailable;
    bool CorridorReachedEndPoly = false;
    bool ResolvedEndpointAvailable = false;
    float ResolvedEndpointX = 0.0f;
    float ResolvedEndpointY = 0.0f;
    float ResolvedEndpointZ = 0.0f;
    bool ActualEndpointMatchedResolved = false;
    bool RequestedEndpointMatched = false;
};

// This is the production planner/executor observation seam.  It contains no
// policy and cannot admit a path; it only converts the already-computed native
// proof into the typed execution record consumed by encounter task feedback.
ExecutionObservation BeginExecutionObservation(float requestedX,
    float requestedY, float requestedZ, std::uint64_t receiptId = 0);
ExecutionObservation BeginUnavailableExecutionObservation(float requestedX,
    float requestedY, float requestedZ);
void ObserveExecutionProof(ExecutionObservation& execution,
    NativePathProofObservation const& proof);

// Hazard movement models a player's decision to abandon a hard cast for an
// imminent lethal mechanic. Other movement owners remain compatible with an
// already-running cast and must not cancel it implicitly.
constexpr bool InterruptsActiveCast(
    BotMovementArbitration::Owner owner,
    BotMovementArbitration::Priority priority)
{
    return owner == BotMovementArbitration::Owner::Hazard
        && priority == BotMovementArbitration::Priority::Hazard;
}

constexpr bool AllowsProgressiveSegments(
    BotMovementArbitration::Owner owner, bool nativeRecoveryEntrance)
{
    return owner == BotMovementArbitration::Owner::Route
        || (owner == BotMovementArbitration::Owner::Recovery
            && nativeRecoveryEntrance);
}

// A corpse-authorized recovery entrance may rely on the same native long
// path that a player submits with MovePoint(generatePath=true).  Keep this
// admission separate from ordinary progressive route segments so no combat,
// formation, or support movement can bypass path planning.
constexpr bool AllowsNativeLongPath(
    BotMovementArbitration::Owner owner, bool nativeRecoveryEntranceRequired)
{
    return owner == BotMovementArbitration::Owner::Recovery
        && nativeRecoveryEntranceRequired;
}

// Only a corpse-authorized recovery entrance may use an aerial spline.  Keep
// this as an intent/state gate so ordinary corpse runs and every other owner
// continue through the existing ground movement executor.
constexpr bool UsesNativeRecoveryGhostFlight(
    BotMovementArbitration::Owner owner, bool allowNativeLongPath,
    bool ghostFlightEnabled)
{
    return owner == BotMovementArbitration::Owner::Recovery
        && allowNativeLongPath && ghostFlightEnabled;
}

// While a corpse-authorized recovery is crossing maps, only the recovery
// owner may submit movement.  A route or combat callback can still run during
// the worldport transition, but its stale instance destination must not be
// handed to the ordinary floor/Z planner on the source map.
constexpr bool BlocksNonRecoveryCrossMapMovement(
    BotMovementArbitration::Owner owner, bool recoveryCrossMapPending)
{
    return recoveryCrossMapPending
        && owner != BotMovementArbitration::Owner::Recovery;
}

// The future-pack mask belongs to ordinary movement admission, not to the
// route, formation, combat, or hazard caller that happened to produce an
// intent.  Native recovery movement is the only exception: it must be
// allowed to return through the declared entrance corridor.
constexpr bool AppliesValidationRoutePatrolFutureDestinationGuard(
    BotMovementArbitration::Owner owner)
{
    return owner != BotMovementArbitration::Owner::Recovery;
}

// A short lethal-mechanic move may need to use the planner's existing
// incomplete-path backoff when a multi-level map resolves an unrelated lower
// floor. This only widens local progress admission after actor and destination
// Z have already established the same-level declared-floor fallback.
constexpr bool AllowsSameLevelLocalMechanicProgress(
    BotMovementArbitration::Owner owner, bool sameLevelDeclaredFloorFallback,
    float distance, bool requireCompletePath, bool allowNativeLongPath,
    bool boundedHazardProgress = false)
{
    constexpr float DefaultMaxDistance = 20.0f;
    constexpr float BoundedHazardMaxDistance = 25.0f;
    float const maxDistance = boundedHazardProgress
        && owner == BotMovementArbitration::Owner::Hazard
        ? BoundedHazardMaxDistance : DefaultMaxDistance;
    return sameLevelDeclaredFloorFallback
        && distance >= 0.0f && distance <= maxDistance
        && !requireCompletePath && !allowNativeLongPath
        && (owner == BotMovementArbitration::Owner::Mechanic
            || owner == BotMovementArbitration::Owner::Hazard);
}

struct Intent
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    // Only a caller with a completed mechanical path proof may provide this
    // floor.  An absent value keeps the ordinary strict floor contract.
    std::optional<float> ReferenceFloorZ;
    bool TerminalOnFailure = false;
    BotMovementArbitration::Owner Owner = BotMovementArbitration::Owner::None;
    BotMovementArbitration::Priority Priority = BotMovementArbitration::Priority::Idle;
    Unit* DynamicTarget = nullptr;
    float DynamicTargetRange = 0.0f;

    // These flags are part of the movement contract, not a policy lookup.
    // A caller that requires a complete native corridor sets
    // RequireCompletePath.  A caller that allows deterministic progress
    // segments sets AllowProgressiveSegments.
    bool AllowProgressiveSegments = false;
    // A narrowly typed hazard may opt into the slightly wider same-floor
    // local-step bound; ordinary hazards retain the 20-yard cap.
    bool BoundedHazardProgress = false;
    bool RequireCompletePath = false;
    bool AllowRecentFailureRetry = false;
    bool AllowNativeLongPath = false;
    bool NativeRecoveryCrossMapPending = false;
    std::string IntentReason;
    // Diagnostic-only correlation token copied from the already-selected
    // action candidate. It is excluded from movement behavior and identity.
    std::string DiagnosticCandidateKey;
};

inline void CopyMovementDiagnosticCandidateKey(Intent& intent,
    std::string_view candidateKey)
{
    intent.DiagnosticCandidateKey = std::string(candidateKey);
}

struct PathPlan
{
    // Diagnostic-only correlation token. It is never consulted for path
    // selection, admission, or native movement behavior.
    std::uint64_t LaunchReceiptId = 0;
    bool Selected = false;
    bool DynamicTarget = false;
    float SegmentX = 0.0f;
    float SegmentY = 0.0f;
    float SegmentZ = 0.0f;
    std::string TraversalMode;
    std::string RejectReason;
    bool RecentFailure = false;
    bool NativeLongPath = false;
    ExecutionObservation Execution;
};

struct ActivePathObservation
{
    bool ScopeMatches = false;
    bool NativePointPathActive = false;
    bool NativeTargetChaseActive = false;
    bool MatchingDestination = false;
};
}

#endif
