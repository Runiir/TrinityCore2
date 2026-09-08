#ifndef TRINITY_BOT_SERVER_VEHICLE_EXIT_LANDING_H
#define TRINITY_BOT_SERVER_VEHICLE_EXIT_LANDING_H

#include "Bots/BotMovementArbiter.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"

#include <cstdint>
#include <string>

namespace BotServerVehicleExitLanding
{
using Scope = BotMovementArbitration::Scope;

struct Episode
{
    // Occupancy is sampled on the bot's update cadence.  The previous-tick
    // bit is what makes an exit an observed transition rather than an
    // inference from a falling flag or a finalized spline.
    bool VehicleObserved = false;
    bool VehicleOccupiedLastTick = false;
    std::uint64_t ObservedVehicleGuid = 0;

    bool ExitPending = false;
    std::uint64_t ExitObservedAtMs = 0;
    std::uint64_t ExitBotGuid = 0;
    std::uint32_t ExitMapId = 0;
    std::uint32_t ExitInstanceId = 0;
    bool ExitScopeAvailable = false;
    Scope ExitScope;
    std::uint64_t BoundGroundingReceiptId = 0;
    std::uint64_t BoundGroundingReceiptArmedAtMs = 0;

    // The latest guard evaluation is retained for diagnosis even when it
    // rejects reconciliation.  These values are bounded latest-value state;
    // the successful edge is emitted once through the normal trace/event
    // path by the owner.
    std::uint64_t LastObservedAtMs = 0;
    std::uint32_t EvaluationCount = 0;
    std::uint64_t LastReconciliationAtMs = 0;
    std::uint32_t LastFlagsBefore = 0;
    std::uint32_t LastFlagsAfter = 0;
    std::uint64_t LastReceiptId = 0;
    std::uint64_t LastReceiptArmedAtMs = 0;
    std::uint32_t LastReceiptMapId = 0;
    std::uint32_t LastReceiptInstanceId = 0;
    bool LastReceiptTerminal = false;
    bool LastTerminalSampleAvailable = false;
    bool LastTerminalActorAlive = false;
    bool LastTerminalActorInWorld = false;
    bool LastTerminalEndpointReached = false;
    bool LastTerminalFloorValid = false;
    bool LastTerminalPlatformCompatible = false;
    bool LastCurrentEndpointMatches = false;
    bool LastSplineFinalized = false;
    bool LastSplineFalling = false;
    std::uint32_t LastCurrentMotionType = 0;
    std::uint32_t LastActiveMotionType = 0;
    std::uint32_t LastControlledMotionType = 0;
    std::string LastTerminalOutcome = "pending";
    std::string LastReason = "none";
};

struct VehicleTransitionObservation
{
    bool HasVehicle = false;
    std::uint64_t VehicleGuid = 0;
    std::uint64_t BotGuid = 0;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    std::uint64_t ObservedAtMs = 0;
    bool ScopeAvailable = false;
    Scope CurrentScope;
};

inline bool SameEpisodeScope(Scope const& left, Scope const& right)
{
    return left.AttemptId == right.AttemptId
        && left.WipeGeneration == right.WipeGeneration
        && left.RouteGeneration == right.RouteGeneration
        && left.MapId == right.MapId
        && left.InstanceId == right.InstanceId;
}

inline void ResetBoundReceipt(Episode& episode)
{
    episode.BoundGroundingReceiptId = 0;
    episode.BoundGroundingReceiptArmedAtMs = 0;
}

inline void BeginVehicleOccupancy(Episode& episode,
    VehicleTransitionObservation const& observation)
{
    // A new mount closes any older, unproven exit episode.  Its last
    // evaluation remains available for postmortem diagnosis.
    episode.VehicleObserved = true;
    episode.VehicleOccupiedLastTick = true;
    episode.ObservedVehicleGuid = observation.VehicleGuid;
    episode.ExitPending = false;
    episode.ExitObservedAtMs = 0;
    episode.ExitBotGuid = 0;
    episode.ExitMapId = 0;
    episode.ExitInstanceId = 0;
    episode.ExitScopeAvailable = false;
    episode.ExitScope = Scope();
    ResetBoundReceipt(episode);
}

inline void ObserveVehicleTransition(Episode& episode,
    VehicleTransitionObservation const& observation)
{
    if (observation.HasVehicle)
    {
        if (!episode.VehicleOccupiedLastTick
            || episode.ObservedVehicleGuid != observation.VehicleGuid)
            BeginVehicleOccupancy(episode, observation);
        return;
    }

    if (!episode.VehicleOccupiedLastTick)
        return;

    episode.VehicleObserved = true;
    episode.VehicleOccupiedLastTick = false;
    episode.ExitPending = true;
    episode.ExitObservedAtMs = observation.ObservedAtMs;
    episode.ExitBotGuid = observation.BotGuid;
    episode.ExitMapId = observation.MapId;
    episode.ExitInstanceId = observation.InstanceId;
    episode.ExitScopeAvailable = observation.ScopeAvailable;
    episode.ExitScope = observation.CurrentScope;
    ResetBoundReceipt(episode);
}

struct ReceiptBindingObservation
{
    bool ActualPointSubmission = false;
    bool ProgressReceiptArmed = false;
    std::uint64_t ReceiptId = 0;
    std::uint64_t BotGuid = 0;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    std::uint64_t ArmedAtMs = 0;
    bool ScopeAvailable = false;
    Scope ReceiptScope;
    bool SplineInitialized = false;
    std::uint32_t SplineId = 0;
};

inline bool BindGroundingReceipt(Episode& episode,
    ReceiptBindingObservation const& receipt)
{
    if (!episode.ExitPending || !receipt.ActualPointSubmission
        || !receipt.ProgressReceiptArmed
        || !receipt.ReceiptId || !receipt.BotGuid
        || !receipt.SplineInitialized || !receipt.SplineId)
        return false;
    if (receipt.BotGuid != episode.ExitBotGuid
        || receipt.MapId != episode.ExitMapId
        || receipt.InstanceId != episode.ExitInstanceId
        || receipt.ArmedAtMs < episode.ExitObservedAtMs)
        return false;
    if (receipt.ScopeAvailable != episode.ExitScopeAvailable
        || (episode.ExitScopeAvailable
            && !SameEpisodeScope(receipt.ReceiptScope, episode.ExitScope)))
        return false;

    // A pending episode may first bind a transitional ground POINT and then
    // receive its replacement before the first one settles.  Only a strictly
    // newer, independently armed receipt can replace that binding.  The
    // exact POINT/progress/identity checks above keep retained paths, failed
    // plans, and receipts from another episode from refreshing it.
    if (episode.BoundGroundingReceiptId
        && !(receipt.ArmedAtMs > episode.BoundGroundingReceiptArmedAtMs
            || (receipt.ArmedAtMs
                    == episode.BoundGroundingReceiptArmedAtMs
                && receipt.ReceiptId > episode.BoundGroundingReceiptId)))
        return false;

    episode.BoundGroundingReceiptId = receipt.ReceiptId;
    episode.BoundGroundingReceiptArmedAtMs = receipt.ArmedAtMs;
    return true;
}

struct LandingEvidence
{
    std::uint64_t BotGuid = 0;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    bool CurrentScopeAvailable = false;
    Scope CurrentScope;
    bool ActorInWorld = false;
    bool ActorAlive = false;
    bool HasVehicle = false;
    bool HasTransport = false;
    bool GravityDisabled = false;
    bool NativeFlight = false;
    bool ControlledState = false;
    bool FallingFlagsPresent = false;
    bool NativeFalling = false;
    bool CurrentSplineFinalized = false;
    bool MotionSlotsSettled = false;

    bool ReceiptAvailable = false;
    std::uint64_t ReceiptId = 0;
    std::uint64_t ReceiptBotGuid = 0;
    std::uint32_t ReceiptMapId = 0;
    std::uint32_t ReceiptInstanceId = 0;
    std::uint64_t ReceiptArmedAtMs = 0;
    bool ReceiptScopeAvailable = false;
    Scope ReceiptScope;
    bool ReceiptTerminal = false;
    bool ReceiptSuperseded = false;
    std::string ReceiptTerminalOutcome = "pending";
    bool TerminalSampleAvailable = false;
    bool TerminalActorAlive = false;
    bool TerminalActorInWorld = false;
    bool TerminalEndpointReached = false;
    bool TerminalFloorValid = false;
    bool TerminalPlatformCompatible = false;
    bool CurrentEndpointMatches = false;

    std::uint32_t FlagsBefore = 0;
    std::uint32_t CurrentMotionType = 0;
    std::uint32_t ActiveMotionType = 0;
    std::uint32_t ControlledMotionType = 0;
};

enum class Decision : std::uint8_t
{
    NoEpisode,
    KeepPending,
    CloseEpisode,
    ClearStaleLandingFlag
};

struct ReconciliationResult
{
    BotServerVehicleExitLanding::Decision Decision =
        BotServerVehicleExitLanding::Decision::NoEpisode;
    bool DropBoundReceipt = false;
    char const* Reason = "no_vehicle_exit_episode";
};

inline ReconciliationResult Keep(char const* reason,
    bool dropReceipt = false)
{
    return { Decision::KeepPending, dropReceipt, reason };
}

inline ReconciliationResult Resolve(Episode const& episode,
    LandingEvidence const& evidence)
{
    if (!episode.VehicleObserved || !episode.ExitPending)
        return { Decision::NoEpisode, false, "no_vehicle_exit_episode" };

    if (evidence.BotGuid != episode.ExitBotGuid
        || evidence.MapId != episode.ExitMapId
        || evidence.InstanceId != episode.ExitInstanceId
        || evidence.CurrentScopeAvailable != episode.ExitScopeAvailable
        || (episode.ExitScopeAvailable
            && !SameEpisodeScope(evidence.CurrentScope, episode.ExitScope)))
        return { Decision::CloseEpisode, false,
            "vehicle_exit_landing_scope_changed" };

    // A cleanly grounded bot closes the episode without touching any native
    // state.  The remaining guards matter only while the stale fall bits are
    // still present.
    if (!evidence.FallingFlagsPresent)
        return { Decision::CloseEpisode, false,
            "vehicle_exit_landing_flags_already_clear" };

    if (!evidence.ActorInWorld || !evidence.ActorAlive)
        return Keep("vehicle_exit_landing_actor_unavailable");
    if (evidence.HasVehicle || evidence.HasTransport)
        return Keep("vehicle_exit_landing_vehicle_or_transport_present");
    if (evidence.GravityDisabled || evidence.NativeFlight)
        return Keep("vehicle_exit_landing_aerial_state");
    if (evidence.ControlledState)
        return Keep("vehicle_exit_landing_controlled_state");
    if (!evidence.CurrentSplineFinalized || evidence.NativeFalling)
        return Keep("vehicle_exit_landing_native_motion_unsettled");
    if (!evidence.MotionSlotsSettled)
        return Keep("vehicle_exit_landing_motion_slots_active");

    if (!episode.BoundGroundingReceiptId)
        return Keep("vehicle_exit_landing_ground_receipt_pending");
    if (!evidence.ReceiptAvailable)
        return Keep("vehicle_exit_landing_ground_receipt_unavailable", true);
    if (evidence.ReceiptId != episode.BoundGroundingReceiptId
        || evidence.ReceiptBotGuid != episode.ExitBotGuid
        || evidence.ReceiptMapId != episode.ExitMapId
        || evidence.ReceiptInstanceId != episode.ExitInstanceId
        || evidence.ReceiptArmedAtMs < episode.ExitObservedAtMs
        || evidence.ReceiptArmedAtMs
            != episode.BoundGroundingReceiptArmedAtMs)
        return { Decision::CloseEpisode, false,
            "vehicle_exit_landing_receipt_identity_changed" };
    if (evidence.ReceiptScopeAvailable != episode.ExitScopeAvailable
        || (episode.ExitScopeAvailable
            && !SameEpisodeScope(evidence.ReceiptScope, episode.ExitScope)))
        return { Decision::CloseEpisode, false,
            "vehicle_exit_landing_receipt_scope_changed" };
    if (evidence.ReceiptSuperseded)
        return Keep("vehicle_exit_landing_ground_receipt_not_usable", true);
    // Native motion is observed every update; receipt sampling is throttled.
    // Settled motion can precede the next terminal sample. Keep the exact
    // binding until that sample arrives instead of treating pending as failure.
    if (!evidence.ReceiptTerminal)
        return Keep("vehicle_exit_landing_ground_receipt_awaiting_terminal");
    if (evidence.ReceiptTerminalOutcome != "selected_endpoint_reached")
        return Keep("vehicle_exit_landing_ground_receipt_not_usable", true);
    if (!evidence.TerminalSampleAvailable
        || !evidence.TerminalActorAlive
        || !evidence.TerminalActorInWorld
        || !evidence.TerminalEndpointReached
        || !evidence.TerminalFloorValid
        || !evidence.TerminalPlatformCompatible)
        return Keep("vehicle_exit_landing_ground_proof_incomplete", true);
    if (!evidence.CurrentEndpointMatches)
        return Keep("vehicle_exit_landing_current_endpoint_mismatch", true);

    return { Decision::ClearStaleLandingFlag, false,
        "vehicle_exit_landing_ground_receipt_reconciled" };
}

template <typename Actor>
inline ReconciliationResult Reconcile(Episode const& episode,
    LandingEvidence const& evidence, Actor* actor)
{
    ReconciliationResult result = Resolve(episode, evidence);
    if (result.Decision == Decision::ClearStaleLandingFlag && actor)
        actor->SetFall(false);
    return result;
}

inline void RecordEvaluation(Episode& episode, LandingEvidence const& evidence,
    ReconciliationResult const& result, std::uint64_t observedAtMs,
    std::uint32_t flagsAfter)
{
    episode.LastObservedAtMs = observedAtMs;
    if (result.Decision == Decision::ClearStaleLandingFlag)
        episode.LastReconciliationAtMs = observedAtMs;
    if (episode.EvaluationCount < 64)
        ++episode.EvaluationCount;
    episode.LastFlagsBefore = evidence.FlagsBefore;
    episode.LastFlagsAfter = flagsAfter;
    episode.LastReceiptId = evidence.ReceiptId
        ? evidence.ReceiptId : episode.BoundGroundingReceiptId;
    episode.LastReceiptArmedAtMs = evidence.ReceiptArmedAtMs;
    episode.LastReceiptMapId = evidence.ReceiptMapId;
    episode.LastReceiptInstanceId = evidence.ReceiptInstanceId;
    episode.LastReceiptTerminal = evidence.ReceiptTerminal;
    episode.LastTerminalSampleAvailable = evidence.TerminalSampleAvailable;
    episode.LastTerminalActorAlive = evidence.TerminalActorAlive;
    episode.LastTerminalActorInWorld = evidence.TerminalActorInWorld;
    episode.LastTerminalEndpointReached = evidence.TerminalEndpointReached;
    episode.LastTerminalFloorValid = evidence.TerminalFloorValid;
    episode.LastTerminalPlatformCompatible =
        evidence.TerminalPlatformCompatible;
    episode.LastCurrentEndpointMatches = evidence.CurrentEndpointMatches;
    episode.LastSplineFinalized = evidence.CurrentSplineFinalized;
    episode.LastSplineFalling = evidence.NativeFalling;
    episode.LastCurrentMotionType = evidence.CurrentMotionType;
    episode.LastActiveMotionType = evidence.ActiveMotionType;
    episode.LastControlledMotionType = evidence.ControlledMotionType;
    episode.LastTerminalOutcome = evidence.ReceiptTerminalOutcome;
    episode.LastReason = result.Reason ? result.Reason : "unknown";
}

inline void CloseEpisode(Episode& episode)
{
    episode.ExitPending = false;
    episode.ExitObservedAtMs = 0;
    episode.ExitBotGuid = 0;
    episode.ExitMapId = 0;
    episode.ExitInstanceId = 0;
    episode.ExitScopeAvailable = false;
    episode.ExitScope = Scope();
    ResetBoundReceipt(episode);
}

} // namespace BotServerVehicleExitLanding

#endif
