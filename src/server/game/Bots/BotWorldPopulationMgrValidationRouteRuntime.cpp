#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrValidationRouteDestination.h"

#include "GameTime.h"
#include "Player.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <string>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

bool BotWorldPopulationMgr::ApplyValidationRouteManifestNode(size_t index, char const* reason)
{
    if (index >= Party().ValidationRouteManifest.size())
        return false;

    // Flush route-local repeatable-event tails before installing the next
    // node/generation so the trace entry remains attributed to the node that
    // actually produced those suppressed observations.
    for (WorldBotState& state : Party().Bots)
    {
        uint64 const suppressedTail = uint64(state.SuppressedRepeatableEventCount)
            + uint64(state.PendingTraceSuppressedRepeatableEventCount);
        if (!suppressedTail)
            continue;
        state.PendingTraceSuppressedRepeatableEventCount = uint32(std::min<uint64>(
            suppressedTail, std::numeric_limits<uint32>::max()));
        RecordDecisionTrace(state, "validation_route_transition",
            "flush_suppressed_repeatable_tail", nullptr, 0, "ok",
            "route_node_boundary");
    }

    ValidationRouteManifestNode const& node = Party().ValidationRouteManifest[index];
    BotValidationRouteDestination::Result const routeDestination =
        BotValidationRouteDestination::Resolve({
            node.MapId,
            node.NavigationAnchorX,
            node.NavigationAnchorY,
            node.NavigationAnchorZ,
        });
    Party().ValidationRouteManifestIndex = index;
    Party().ValidationRouteGeneration = index + 1;
    Cohort().Config.ValidationRouteEnable = true;
    Cohort().Config.ValidationRouteScenarioId = node.ScenarioId;
    Cohort().Config.ValidationRouteNodeId = node.NodeId;
    Cohort().Config.ValidationRouteLabel = node.Label;
    Cohort().Config.ValidationRouteKind = node.Kind;
    Cohort().Config.ValidationRouteNodeKind = node.NodeKind;
    Cohort().Config.ValidationRouteDescentAction = node.DescentAction;
    Cohort().Config.ValidationRouteMechanicProfile = node.MechanicProfile;
    Cohort().Config.ValidationRouteBossRecovery = node.BossRecoveryPolicy;
    // Recovery authority is owned by the exact node/generation that observed
    // the native all-dead edge. Monotonic wipe state from an earlier trash or
    // boss node must never authorize the newly installed route node.
    if (node.BossRecoveryPolicy != ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
        || Cohort().Raid.NativeRecoveryRouteGeneration != Party().ValidationRouteGeneration
        || Cohort().Raid.NativeRecoveryNodeId != node.NodeId)
    {
        RaidRuntime& raid = Cohort().Raid;
        raid.NativeRecoveryHoldActive = false;
        raid.NativeRecoveryRouteGeneration = 0;
        raid.NativeRecoveryNodeId.clear();
        raid.NativeRecoveryEvidenceComplete = false;
        raid.NativeDeathObserved = false;
        raid.NativeCorpseObserved = false;
        raid.NativeReleaseObserved = false;
        raid.NativeResurrectionObserved = false;
        raid.NativeRunbackObserved = false;
        raid.NativeSignalsByGuid.clear();
        raid.NativeReadyCheckActionObserved = false;
        raid.NativeReadyCheckPending = false;
        raid.NativeReadyCheckResponseCount = 0;
        raid.NativeReadyCheckActionAttemptId = 0;
        raid.NativeReadyCheckActionWipeGeneration = 0;
        raid.NativeReadyCheckAssignmentGeneration = 0;
        raid.NativeReadyCheckActionEvidenceSequence = 0;
        raid.NativeReadyCheckResponders.clear();
        raid.ReadyCheckSatisfied = false;
        raid.BossResetGenerationAtWipe = raid.BossResetGeneration;
        raid.WipeState = "ready";
        raid.RecoveryState = "none";
        raid.EncounterPhase = "formation";
    }
    Cohort().Config.ValidationRouteMapId = node.MapId;
    Cohort().Config.ValidationRouteX = node.NavigationAnchorX;
    Cohort().Config.ValidationRouteY = node.NavigationAnchorY;
    Cohort().Config.ValidationRouteZ = node.NavigationAnchorZ;
    Cohort().Config.ValidationRouteO = node.NavigationAnchorO;
    Cohort().Config.ValidationRouteTargetEntry = node.NodeKind == "discovery_leg" ? 0 : node.TargetEntry;
    Cohort().Config.ValidationRouteOpenerTargetEntry = node.OpenerTargetEntry;
    Cohort().Config.ValidationRouteAlternateTargetEntries = node.AlternateTargetEntries;
    Cohort().Config.ValidationRouteAddTargetEntries = node.AddTargetEntries;
    Cohort().Config.ValidationRoutePackTargetEntries = node.PackTargetEntries;
    Cohort().Config.ValidationRouteScriptedEventEntries = node.ScriptedEventEntries;
    Cohort().Config.ValidationRouteScriptedEventTransitionAuraIds = node.ScriptedEventTransitionAuraIds;
    Cohort().Config.ValidationRouteScriptedEventRequirePassive = node.ScriptedEventRequirePassive;
    Cohort().Config.ValidationRouteHazardSourceEntry = node.HazardSourceEntry;
    Cohort().Config.ValidationRouteHazardDetectionSpellId = node.HazardDetectionSpellId;
    Cohort().Config.ValidationRouteHazardDamageSpellId = node.HazardDamageSpellId;
    Cohort().Config.ValidationRouteHazardShape = node.HazardShape;
    Cohort().Config.ValidationRouteHazardRadiusYards = node.HazardRadiusYards;
    Cohort().Config.ValidationRouteHazardSafetyMarginYards = node.HazardSafetyMarginYards;
    Cohort().Config.ValidationRouteMinimumDistanceSourceEntry = node.MinimumDistanceSourceEntry;
    Cohort().Config.ValidationRouteMinimumDistanceYards = node.MinimumDistanceYards;
    Cohort().Config.ValidationRouteSplitSourceGuids = node.SplitSourceGuids;
    Cohort().Config.ValidationRouteSplitLaneARosterSlots = node.SplitLaneARosterSlots;
    Cohort().Config.ValidationRouteSplitLaneBRosterSlots = node.SplitLaneBRosterSlots;
    Cohort().Config.ValidationRouteSplitLaneTankSlots = node.SplitLaneTankSlots;
    Cohort().Config.ValidationRouteSplitHealerRosterSlots = node.SplitHealerRosterSlots;
    Cohort().Config.ValidationRouteSplitMemberAnchors = node.SplitMemberAnchors;
    Cohort().Config.ValidationRouteSplitRecoveryMemberAnchors =
        node.SplitRecoveryMemberAnchors;
    Cohort().Config.ValidationRouteSplitTankCombatAnchors = node.SplitTankCombatAnchors;
    Cohort().Config.ValidationRouteSplitTankNavigationAnchors =
        node.SplitTankNavigationAnchors;
    Cohort().Config.ValidationRouteSplitTankRecoveryAnchors =
        node.SplitTankRecoveryAnchors;
    Cohort().Config.ValidationRouteSplitMinimumSeparationYards = node.SplitMinimumSeparationYards;
    Cohort().Config.ValidationRouteSplitNavigationMarginYards = node.SplitNavigationMarginYards;
    Cohort().Config.ValidationRouteSplitArrivalToleranceYards = node.SplitArrivalToleranceYards;
    Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards =
        node.SplitTankArrivalToleranceYards;
    Cohort().Config.ValidationRouteSplitNativeMeleeStopYards = node.SplitNativeMeleeStopYards;
    Cohort().Config.ValidationRouteSplitSeedRosterSlots = node.SplitSeedRosterSlots;
    Cohort().Config.ValidationRouteSplitSeedMaxRangeYards = node.SplitSeedMaxRangeYards;
    Cohort().Config.ValidationRouteSplitTankThreatHeadroomMultiplier =
        node.SplitTankThreatHeadroomMultiplier;
    Cohort().Config.ValidationRouteThunderclapSpellId = node.ThunderclapSpellId;
    Cohort().Config.ValidationRouteChargeSpellId = node.ChargeSpellId;
    Cohort().Config.ValidationRouteChargeRangeYards = node.ChargeRangeYards;
    Cohort().Config.ValidationRouteChargeNativeIntervalMs = node.ChargeNativeIntervalMs;
    Cohort().Config.ValidationRouteVengefulRageSpellId = node.VengefulRageSpellId;
    Cohort().Config.ValidationRouteClusterRadiusYards = node.ClusterRadiusYards;
    Cohort().Config.ValidationRoutePatrolPullPolicy = node.PatrolPullPolicy;
    Cohort().Config.ValidationRoutePatrolWaitX = node.PatrolWaitX;
    Cohort().Config.ValidationRoutePatrolWaitY = node.PatrolWaitY;
    Cohort().Config.ValidationRoutePatrolWaitZ = node.PatrolWaitZ;
    Cohort().Config.ValidationRoutePatrolWaitToleranceYards = node.PatrolWaitToleranceYards;
    Cohort().Config.ValidationRoutePatrolAnchorToleranceYards = node.PatrolAnchorToleranceYards;
    Cohort().Config.ValidationRoutePatrolEngageRadiusYards = node.PatrolEngageRadiusYards;
    Cohort().Config.ValidationRoutePatrolFutureGuardMarginYards = node.PatrolFutureGuardMarginYards;
    Cohort().Config.ValidationRoutePatrolPullOwnerRosterSlot = node.PatrolPullOwnerRosterSlot;
    Cohort().Config.ValidationRouteExpectedAliveCount = node.ExpectedAliveCount;
    Party().ValidationRouteAddFocusGuid.Clear();
    Party().ValidationRouteAddFocusGeneration = Party().ValidationRouteGeneration;
    Party().ValidationRouteRecordedKillGuids.clear();
    Party().ValidationRoutePackMemberGuids.clear();
    Party().ValidationRoutePackEngagedGuids.clear();
    Party().ValidationRoutePackDeathGuids.clear();
    Party().ValidationRoutePackTransitionGuids.clear();
    Party().ValidationRoutePendingFinalTransitionGuids.clear();
    Party().ValidationRoutePackGeneration = Party().ValidationRouteGeneration;
    Party().ValidationRoutePackSequence = 1;
    Party().ValidationRouteCompletedPackCount = 0;
    Party().ValidationRoutePackObservedEngagement = false;
    if (node.MechanicProfile == "trash_two_tank_charge_lanes")
    {
        Party().ValidationRouteDrudgePrepullStaged = false;
        Party().ValidationRouteDrudgePrepullAttemptId = 0;
        Party().ValidationRouteDrudgePrepullWipeGeneration = 0;
        Party().ValidationRouteDrudgePrepullRouteGeneration = 0;
        Party().ValidationRouteDrudgeChargeGeneration = 0;
        Party().ValidationRouteDrudgeChargeLandedGeneration = 0;
        Party().ValidationRouteDrudgeChargeObservedAtMs = 0;
        Party().ValidationRouteDrudgeChargeSourceGuid.Clear();
        Party().ValidationRouteDrudgeChargeTargetGuid.Clear();
        Party().ValidationRouteDrudgeChargeSourceSpawnId = 0;
        Party().ValidationRouteDrudgeChargeObservedDistance = 0.0f;
        Party().ValidationRouteDrudgeChargeRangeValid = false;
        Party().ValidationRouteDrudgeChargeIntervalValid = false;
        Party().ValidationRouteDrudgeLastChargeMsBySpawn.clear();
        Party().ValidationRouteDrudgeChargeObservations.clear();
        Party().ValidationRouteDrudgeEvidenceAttemptId = Cohort().AttemptId;
        Party().ValidationRouteDrudgeEvidenceWipeGeneration = Cohort().Raid.WipeGeneration;
        Party().ValidationRouteDrudgeEvidenceRouteGeneration = Party().ValidationRouteGeneration;
        Party().ValidationRouteDrudgeEvidenceSourceSpawnIds = node.SplitSourceGuids;
        Party().ValidationRouteDrudgeChargePreparedCount = 0;
        Party().ValidationRouteDrudgeChargeDeliveredCount = 0;
        Party().ValidationRouteDrudgeChargeQueueOverflow = false;
        Party().ValidationRouteDrudgeDeliveredBySpawn.clear();
        Party().ValidationRouteDrudgeValidIntervalsBySpawn.clear();
        Party().ValidationRouteDrudgeReseparatedRosterGuids.clear();
        Party().ValidationRouteDrudgeOwnershipRosterGuids.clear();
        Party().ValidationRouteDrudgeTauntRosterGuids.clear();
        Party().ValidationRouteDrudgeHealthSyncRosterGuids.clear();
        Party().ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids.clear();
        Party().ValidationRouteDrudgeHealthSyncHoldSourceSpawnId = 0;
        Party().ValidationRouteDrudgeHealthSyncHoldTankGuid = 0;
        Party().ValidationRouteDrudgeHealthSyncHoldLowerPct = 0.0f;
        Party().ValidationRouteDrudgeHealthSyncHoldPeerPct = 0.0f;
        Party().ValidationRouteDrudgeHealthSyncHoldLowerAlive = false;
        Party().ValidationRouteDrudgeHealthSyncHoldPeerAlive = false;
        Party().ValidationRouteDrudgeDeathAttemptId = 0;
        Party().ValidationRouteDrudgeDeathWipeGeneration = 0;
        Party().ValidationRouteDrudgeDeathRouteGeneration = 0;
        Party().ValidationRouteDrudgeDeathSourceSpawnId = 0;
        Party().ValidationRouteDrudgeDeathSourceGuid = 0;
        Party().ValidationRouteDrudgeSurvivorSourceSpawnId = 0;
        Party().ValidationRouteDrudgeSurvivorSourceGuid = 0;
        Party().ValidationRouteDrudgeDeathEvidenceSequence = 0;
        Party().ValidationRouteDrudgeRageWaitEvidenceSequence = 0;
        Party().ValidationRouteDrudgeRageAuraEvidenceSequence = 0;
        Party().ValidationRouteDrudgeHealthSyncEvidenceAttemptId = 0;
        Party().ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration = 0;
        Party().ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration = 0;
        Party().ValidationRouteDrudgeProfileActionRosterGuids.clear();
        Party().ValidationRouteDrudgeThreatSeedAttemptId = 0;
        Party().ValidationRouteDrudgeThreatSeedWipeGeneration = 0;
        Party().ValidationRouteDrudgeThreatSeedRouteGeneration = 0;
        Party().ValidationRouteDrudgeThreatSeedClosed = false;
        Party().ValidationRouteDrudgeThreatSeedComplete = false;
        Party().ValidationRouteDrudgeThreatSeedFailure = false;
        Party().ValidationRouteDrudgeThreatSeedRosterGuids.clear();
        Party().ValidationRouteDrudgeThreatSeedEvidenceRows.clear();
        for (WorldBotState& botState : Party().Bots)
        {
            botState.LastValidationRouteDrudgeChargeGenerationHandled = 0;
            botState.LastValidationRouteDrudgeChargeGenerationObserved = 0;
            botState.ValidationRouteDrudgeAnchorValid = false;
            botState.ValidationRouteDrudgeAnchorPathProven = false;
            botState.ValidationRouteDrudgeRecoveryAnchorPathProven = false;
            botState.ValidationRouteDrudgeRecoveryAnchorReached = false;
            botState.ValidationRouteDrudgeRecoveryAnchorX = 0.0f;
            botState.ValidationRouteDrudgeRecoveryAnchorY = 0.0f;
            botState.ValidationRouteDrudgeRecoveryAnchorZ = 0.0f;
            botState.ValidationRouteDrudgeAnchorAttemptId = 0;
            botState.ValidationRouteDrudgeAnchorWipeGeneration = 0;
            botState.ValidationRouteDrudgeAnchorRouteGeneration = 0;
            botState.ValidationRouteDrudgeAnchorMapId = 0;
            botState.ValidationRouteDrudgeAnchorInstanceId = 0;
            botState.ValidationRouteDrudgeAnchorSource0Identity = 0;
            botState.ValidationRouteDrudgeAnchorSource1Identity = 0;
            botState.ValidationRouteDrudgeAnchorCandidateIndex = 0;
            botState.ValidationRouteDrudgeAnchorX = 0.0f;
            botState.ValidationRouteDrudgeAnchorY = 0.0f;
            botState.ValidationRouteDrudgeAnchorZ = 0.0f;
            botState.ValidationRouteDrudgeAnchorSearchCooldownUntilMs = 0;
        }
    }
    Party().ValidationRouteObservedDeadScriptTarget = false;
    Party().ValidationRoutePackClearCandidateSinceMs = 0;
    Party().ValidationRouteNodeClearCandidateSinceMs = 0;
    Cohort().Config.ValidationRouteActivationAreaTriggerId = node.ActivationAreaTriggerId;
    Cohort().Config.ValidationRecoveryEntranceAreaTriggerId = node.RecoveryEntranceAreaTriggerId;
    Cohort().Config.ValidationRecoveryEntranceSourceMapId = node.RecoveryEntranceSourceMapId;
    Cohort().Config.ValidationRecoveryEntranceTargetMapId = node.RecoveryEntranceTargetMapId;
    Cohort().Config.ValidationRouteActivationDataId = node.ActivationDataId;
    Cohort().Config.ValidationRouteActivationDataValue = node.ActivationDataValue;
    Cohort().Config.ValidationRouteActivationSpawnGroupId = node.ActivationSpawnGroupId;
    Cohort().Config.ValidationRouteActivationActionEntry = node.ActivationActionEntry;
    Cohort().Config.ValidationRouteActivationActionId = node.ActivationActionId;
    Cohort().Config.ValidationRouteActivationSummonEntry = node.ActivationSummonEntry;
    Cohort().Config.ValidationRouteActivationSummonX = node.ActivationSummonX;
    Cohort().Config.ValidationRouteActivationSummonY = node.ActivationSummonY;
    Cohort().Config.ValidationRouteActivationSummonZ = node.ActivationSummonZ;
    Cohort().Config.ValidationRouteActivationSummonO = node.ActivationSummonO;
    Cohort().Config.ValidationRouteOpenerSummonEntry = node.OpenerSummonEntry;
    Cohort().Config.ValidationRouteOpenerSummonX = node.OpenerSummonX;
    Cohort().Config.ValidationRouteOpenerSummonY = node.OpenerSummonY;
    Cohort().Config.ValidationRouteOpenerSummonZ = node.OpenerSummonZ;
    Cohort().Config.ValidationRouteOpenerSummonO = node.OpenerSummonO;
    if (node.ExpectedBotCount)
        Cohort().Config.TargetPopulation = node.ExpectedBotCount;

    ResetValidationRouteRuntimeState(reason ? reason : "manifest_route_apply");
    // Adaptive owners intentionally skip the generic route objective gate.
    // Seed the state from the newly installed node before that owner runs so
    // route recovery cannot submit the prior node's coordinates.  The result
    // only supplies a legal native destination; MotionMaster/path admission
    // remains owned by the movement executor.
    for (WorldBotState& state : Party().Bots)
    {
        state.QuestRouteDestination.Valid = routeDestination.Valid;
        state.QuestRouteDestination.MapId = routeDestination.MapId;
        state.QuestRouteDestination.X = routeDestination.X;
        state.QuestRouteDestination.Y = routeDestination.Y;
        state.QuestRouteDestination.Z = routeDestination.Z;
        state.QuestRouteDestination.QuestId = 0;
        state.QuestRouteDestination.Reason = routeDestination.Reason;
    }
    Party().ValidationRouteProgressBaselineKills = Cohort().Metrics.Kills;
    return true;
}

void BotWorldPopulationMgr::ResetValidationRouteBossAddEscapeState()
{
    Party().ValidationRouteBossAddEscapeActive = false;
    Party().ValidationRouteBossAddEscapeGeneration = 0;
    Party().ValidationRouteBossAddEscapeX = 0.0f;
    Party().ValidationRouteBossAddEscapeY = 0.0f;
    Party().ValidationRouteBossAddEscapeZ = 0.0f;
    Party().ValidationRouteBossAddEscapeAnchorX = 0.0f;
    Party().ValidationRouteBossAddEscapeAnchorY = 0.0f;
    Party().ValidationRouteBossAddEscapeAnchorZ = 0.0f;
    Party().ValidationRouteBossAddCentroidX = 0.0f;
    Party().ValidationRouteBossAddCentroidY = 0.0f;
    Party().ValidationRouteBossAddEscapeIssuedGuids.clear();
}

void BotWorldPopulationMgr::ResetValidationRouteBossAddDensityState()
{
    Party().ValidationRouteBossAddDensityPhase = false;
    Party().ValidationRouteBossAddDensityGeneration = 0;
    Party().ValidationRouteLargePassiveSwarmStaging = false;
    Party().ValidationRouteLargePassiveSwarmStagingGeneration = 0;
    ResetValidationRouteBossAddEscapeState();
}

void BotWorldPopulationMgr::ResetTraceStreams()
{
    Party().TraceExportCursorByGuid.clear();
    for (WorldBotState& state : Party().Bots)
    {
        state.TraceSequence = 0;
        state.DecisionTrace.clear();
    }
}

void BotWorldPopulationMgr::ResetValidationRouteRuntimeState(char const* reason)
{
    // Route-node changes deliberately preserve the monotonic trace stream so
    // the segment-advance event and the prior node's unexported rows survive
    // until the capture writer consumes them. True run/profile recording
    // lifecycle boundaries call ResetTraceStreams explicitly.
    Party().ValidationRouteFocusGuid.Clear();
    Party().ValidationRouteFocusEntry = 0;
    Party().ValidationRouteFocusMapId = 0;
    Party().ValidationRouteFocusX = 0.0f;
    Party().ValidationRouteFocusY = 0.0f;
    Party().ValidationRouteFocusZ = 0.0f;
    Party().ValidationRouteFocusSeenMs = 0;
    Party().ValidationRouteBossProgressTargetGuid.Clear();
    Party().ValidationRouteBossSlowProgressCount = 0;
    Party().ValidationRouteEngagedBossGuid.Clear();
    Party().ValidationRouteEngagedBossGeneration = 0;
    Party().ValidationRouteEngagedBossMapId = 0;
    Party().ValidationRouteEngagedBossInstanceId = 0;
    Party().ValidationRouteConfirmedBossDeathGuid.Clear();
    Party().ValidationRouteConfirmedBossDeathGeneration = 0;
    Party().ValidationRouteConfirmedBossDeathMapId = 0;
    Party().ValidationRouteConfirmedBossDeathInstanceId = 0;
    ResetValidationRouteBossAddDensityState();
    Party().ValidationRouteActivationApplied = false;
    Party().ValidationRouteActivationAttempts = 0;
    Party().ValidationRouteCanonicalBossRecoveryAttempts = 0;
    Party().ValidationRouteCanonicalBossRecoveryLastMs = 0;
    Party().ValidationRouteManifestAdvancePending = false;
    Party().ValidationRouteManifestAdvanceGeneration = 0;
    Party().ValidationRouteManifestComplete = false;
    Party().ValidationRouteManifestAdvanceReason.clear();
    Party().ValidationRouteObservedEngagement = false;
    Party().ValidationRouteObservedDeadScriptTarget = false;
    Party().ValidationRouteDrudgeThreatSeedAttemptId = 0;
    Party().ValidationRouteDrudgeThreatSeedWipeGeneration = 0;
    Party().ValidationRouteDrudgeThreatSeedRouteGeneration = 0;
    Party().ValidationRouteDrudgeThreatSeedClosed = false;
    Party().ValidationRouteDrudgeThreatSeedComplete = false;
    Party().ValidationRouteDrudgeThreatSeedFailure = false;
    Party().ValidationRouteDrudgeThreatSeedRosterGuids.clear();
    Party().ValidationRouteDrudgeThreatSeedEvidenceRows.clear();

    uint64 nowMs = NowMs();
    for (WorldBotState& state : Party().Bots)
    {
        // Applying a new route node is a stream boundary, but not a reason to
        // discard the old node's unsent fingerprint tail. Flush before any
        // identity/counter fields are reset; this also works after a Player
        // has already left the world because the stream stores its identity.
        FlushDecisionFingerprintMemory(state);
        state.TargetGuid.Clear();
        state.ActivePathValid = false;
        state.ActivePathSegmentValid = false;
        state.ActivePathTraversalMode.clear();
        state.ValidationRouteCombatProgressTargetGuid.Clear();
        state.ValidationRouteCombatBestHealthPct = 1.0f;
        state.ValidationRouteCombatNoProgressCount = 0;
        state.ValidationRouteCombatNoProgressSinceMs = 0;
        state.ValidationRouteBossSlowProgressCount = 0;
        state.ValidationRoutePackProgressTargetGuid.Clear();
        state.ValidationRoutePackBestHealthPct = 1.0f;
        state.ValidationRoutePackNoProgressCount = 0;
        state.ValidationRoutePackNoProgressSinceMs = 0;
        state.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();
        state.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();
        state.ValidationRouteActivationApplied = false;
        state.ValidationRouteActivationAttempts = 0;
        state.ValidationRouteTargetSearchMissCount = 0;
        state.ValidationRouteTerminalState = false;
        state.ValidationRouteTerminalAtMs = 0;
        state.ValidationRouteGeneration = Party().ValidationRouteGeneration;
        state.ValidationRouteTerminalGeneration = 0;
        state.ValidationRouteTerminalReason.clear();
        state.ValidationRouteDescentPhase = WorldBotState::ValidationDescentPhase::Unobserved;
        state.ValidationRouteDescentGeneration = 0;
        state.ValidationRouteDescentStartX = 0.0f;
        state.ValidationRouteDescentStartY = 0.0f;
        state.ValidationRouteDescentStartZ = 0.0f;
        state.ValidationRouteDescentInitialGoalDistance = 0.0f;
        state.ValidationRouteDescentBestGoalDistance = 0.0f;
        state.ValidationRouteDescentLandingX = 0.0f;
        state.ValidationRouteDescentLandingY = 0.0f;
        state.ValidationRouteDescentLandingZ = 0.0f;
        state.ValidationRouteDescentLandingHealthPct = 0.0f;
        state.ValidationRouteDescentLastProgressMs = 0;
        state.ValidationRouteDescentGroundedSinceMs = 0;
        state.ValidationRouteDescentDepartureObserved = false;
        state.ValidationRouteDescentFallingObserved = false;
        state.ValidationRouteDescentLandingObserved = false;
        state.ValidationRouteDescentHealthMarginSatisfied = false;
        state.ValidationRouteDescentLandingPathProven = false;
        state.ValidationRouteDescentMonotonicProgressObserved = false;
        state.ValidationRouteDescentRejectReason.clear();
        state.ValidationRouteAnchorOverrideValid = false;
        state.ValidationRouteAnchorOverrideUntilMs = 0;
        state.ValidationRouteAnchorOverrideReason.clear();
        state.ValidationRouteUnresolvedFocusHoldCount = 0;
        state.ConsecutiveSameDecisionCount = 0;
        state.IdleDecisionRepeatCount = 0;
        // A route reset starts a new decision stream. Reset the complete
        // fingerprint persistence tuple so a repeated first hash cannot
        // compare a fresh counter with an old persisted baseline.
        state.DecisionFingerprintInitialized = false;
        state.LastDecisionFingerprintHash = 0;
        state.LastDecisionFingerprintRepeatCount = 0;
        state.LastDecisionFingerprintFailureCount = 0;
        state.LastDecisionFingerprintFailure = false;
        state.DecisionFingerprintSituation.clear();
        state.DecisionFingerprintAction.clear();
        state.DecisionFingerprintActivity.clear();
        state.DecisionFingerprintResult = "ok";
        state.DecisionFingerprintQuestId = 0;
        state.DecisionFingerprintClusterId = 0;
        state.DecisionFingerprintMapId = 0;
        state.DecisionFingerprintZoneId = 0;
        state.DecisionFingerprintAreaId = 0;
        state.LastDecisionFingerprintPersistMs = 0;
        state.LastDecisionFingerprintPersistedRepeatCount = 0;
        state.LastDecisionFingerprintPersistedFailureCount = 0;
        state.ValidationRouteDrudgeAnchorValid = false;
        state.ValidationRouteDrudgeAnchorPathProven = false;
        state.ValidationRouteDrudgeRecoveryAnchorPathProven = false;
        state.ValidationRouteDrudgeRecoveryAnchorReached = false;
        state.ValidationRouteDrudgeRecoveryAnchorX = 0.0f;
        state.ValidationRouteDrudgeRecoveryAnchorY = 0.0f;
        state.ValidationRouteDrudgeRecoveryAnchorZ = 0.0f;
        state.ValidationRouteDrudgeAnchorAttemptId = 0;
        state.ValidationRouteDrudgeAnchorWipeGeneration = 0;
        state.ValidationRouteDrudgeAnchorRouteGeneration = 0;
        state.ValidationRouteDrudgeAnchorMapId = 0;
        state.ValidationRouteDrudgeAnchorInstanceId = 0;
        state.ValidationRouteDrudgeAnchorSource0Identity = 0;
        state.ValidationRouteDrudgeAnchorSource1Identity = 0;
        state.ValidationRouteDrudgeAnchorCandidateIndex = 0;
        state.ValidationRouteDrudgeAnchorX = 0.0f;
        state.ValidationRouteDrudgeAnchorY = 0.0f;
        state.ValidationRouteDrudgeAnchorZ = 0.0f;
        state.ValidationRouteDrudgeAnchorSearchCooldownUntilMs = 0;
        state.ValidationRouteDodgeCasterGuid.Clear();
        state.ValidationRouteDodgeSpellId = 0;
        state.ValidationRouteDodgeUntilMs = 0;
        state.ValidationRouteDodgeBearingAttempt = 0;
        state.LastRepeatableEventKey.clear();
        state.LastRepeatableEventEmitMs = 0;
        state.SuppressedRepeatableEventCount = 0;
        state.LastPersistedDiagnosticDecisionKey.clear();
        state.LastPersistedDiagnosticDecisionMs = 0;
        state.SuppressedDiagnosticDecisionCount = 0;
        state.LastValidationRouteDrudgeChargeGenerationObserved = 0;
        state.PendingTraceSuppressedRepeatableEventCount = 0;
        state.LastLoopGuardrailReason.clear();
        state.LastNoProgressReason = reason ? reason : "validation_route_reset";
        state.LoopRecoveryCooldownUntilMs = nowMs + 3000;
    }
}

bool BotWorldPopulationMgr::ValidationRouteHasProgressSinceApply() const
{
    return Party().ValidationRouteObservedEngagement && Cohort().Metrics.Kills > Party().ValidationRouteProgressBaselineKills;
}

bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest()
{
    if (Party().ValidationRouteManifest.empty() || Cohort().Config.ValidationRouteAdvanceMode != "terminal")
        return false;

    if (Party().ValidationRouteManifestComplete)
    {
        Party().ValidationRouteManifestAdvancePending = false;
        Party().ValidationRouteManifestAdvanceGeneration = 0;
        Party().ValidationRouteManifestAdvanceReason.clear();
        return true;
    }

    bool arrivalRoute = Cohort().Config.ValidationRouteKind == "travel" || Cohort().Config.ValidationRouteKind == "regroup" || Cohort().Config.ValidationRouteKind == "descent";
    bool confirmedBossDeath = Cohort().Config.ValidationRouteKind != "boss"
        || (!Party().ValidationRouteConfirmedBossDeathGuid.IsEmpty()
            && Party().ValidationRouteConfirmedBossDeathGeneration == Party().ValidationRouteGeneration
            && Party().ValidationRouteConfirmedBossDeathMapId == Cohort().Config.ValidationRouteMapId);
    bool terminal = !arrivalRoute
        && confirmedBossDeath
        && Party().ValidationRouteManifestAdvancePending
        && Party().ValidationRouteManifestAdvanceGeneration == Party().ValidationRouteGeneration;
    std::string terminalReason = Party().ValidationRouteManifestAdvanceReason;
    if (arrivalRoute)
    {
        bool const typedNativeDescent =
            Cohort().Config.ValidationRouteKind == "descent"
            && Cohort().Config.ValidationRouteDescentAction
                == "native_walkable_descent";
        uint32 loadedParticipants = 0;
        bool allLoadedArrived = true;
        float arrivalRadius = 18.0f;
        for (WorldBotState const& state : Party().Bots)
        {
            Player* loadedBot = GetLoadedBot(state);
            if (!loadedBot)
                continue;

            ++loadedParticipants;
            if (!loadedBot->IsInWorld() || !loadedBot->IsAlive() || !IsValidationCohortMemberInOriginalInstance(state, loadedBot)
                || loadedBot->IsInCombat() || loadedBot->GetVictim() || !loadedBot->getAttackers().empty())
            {
                allLoadedArrived = false;
                break;
            }

            if (typedNativeDescent
                && (state.ValidationRouteDescentGeneration
                        != Party().ValidationRouteGeneration
                    || state.ValidationRouteDescentPhase
                        != WorldBotState::ValidationDescentPhase::Ready
                    || !state.ValidationRouteDescentDepartureObserved
                    || !state.ValidationRouteDescentLandingObserved
                    || !state.ValidationRouteDescentHealthMarginSatisfied
                    || !state.ValidationRouteDescentLandingPathProven
                    || !state.ValidationRouteDescentMonotonicProgressObserved
                    || loadedBot->IsFalling()))
            {
                allLoadedArrived = false;
                break;
            }

            float const verticalArrivalError = std::fabs(
                loadedBot->GetPositionZ() - Cohort().Config.ValidationRouteZ);
            if (loadedBot->GetExactDist(Cohort().Config.ValidationRouteX,
                    Cohort().Config.ValidationRouteY,
                    Cohort().Config.ValidationRouteZ) > arrivalRadius
                || verticalArrivalError > 4.0f)
            {
                allLoadedArrived = false;
                break;
            }
        }

        if (Cohort().Config.TargetPopulation && loadedParticipants < Cohort().Config.TargetPopulation)
            allLoadedArrived = false;

        if (loadedParticipants && allLoadedArrived)
        {
            terminal = true;
            terminalReason = typedNativeDescent
                ? "native_descent_landed_path_proven" : "arrival";
        }
    }
    else
    {
        uint32 loadedParticipants = 0;
        bool cohortReadyForAdvance = true;
        float terminalCohortRadius = Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f
            ? std::min(Cohort().Config.ValidationRouteClusterRadiusYards, 90.0f)
            : 90.0f;
        for (WorldBotState const& state : Party().Bots)
        {
            Player* loadedBot = GetLoadedBot(state);
            if (!loadedBot)
                continue;

            ++loadedParticipants;
            if (!loadedBot->IsInWorld()
                || !loadedBot->IsAlive()
                || !IsValidationCohortMemberInOriginalInstance(state, loadedBot)
                || loadedBot->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) > terminalCohortRadius)
            {
                cohortReadyForAdvance = false;
                break;
            }
        }

        if (Cohort().Config.TargetPopulation && loadedParticipants < Cohort().Config.TargetPopulation)
            cohortReadyForAdvance = false;

        if (!cohortReadyForAdvance)
            return false;

        for (WorldBotState const& state : Party().Bots)
        {
            bool successfulTerminal = state.ValidationRouteGeneration == Party().ValidationRouteGeneration
                && state.ValidationRouteTerminalGeneration == Party().ValidationRouteGeneration
                && state.ValidationRouteTerminalState
                && (state.ValidationRouteTerminalReason == "all_routes_complete"
                    || (Cohort().Config.ValidationRouteKind == "boss"
                        && state.ValidationRouteTerminalReason == "boss_killed")
                    || (state.ValidationRouteTerminalReason == "native_postcondition")
                    || (Cohort().Config.ValidationRouteKind != "boss"
                        && state.ValidationRouteTerminalReason == "trash_cluster_cleared"));
            if (successfulTerminal)
            {
                terminal = true;
                terminalReason = state.ValidationRouteTerminalReason;
                break;
            }
        }
    }

    if (!terminal)
        return false;

    bool terminalRecorded = std::any_of(Party().ValidationRouteTerminalEvidence.begin(), Party().ValidationRouteTerminalEvidence.end(), [this](ValidationRouteEvidence const& evidence)
    {
        return evidence.NodeId == Cohort().Config.ValidationRouteNodeId && evidence.Generation == Party().ValidationRouteGeneration;
    });
    if (!terminalRecorded)
        Party().ValidationRouteTerminalEvidence.push_back({Cohort().Config.ValidationRouteNodeId, Party().ValidationRouteGeneration, Cohort().Config.ValidationRouteKind, ObjectGuid::Empty, Cohort().Config.ValidationRouteTargetEntry, terminalReason});

    size_t nextIndex = Party().ValidationRouteManifestIndex + 1;
    Player* reporter = nullptr;
    WorldBotState* reporterState = nullptr;
    for (WorldBotState& state : Party().Bots)
    {
        reporter = GetLoadedBot(state);
        if (reporter)
        {
            reporterState = &state;
            break;
        }
    }

    if (nextIndex >= Party().ValidationRouteManifest.size())
    {
        Party().ValidationRouteManifestComplete = true;
        if (reporterState && reporter)
        {
            std::string raw = BuildRawJson(reporter, nullptr);
            std::string semantic = BuildSemanticJson(reporter, nullptr, "validation_route_manifest", nullptr);
            RecordEvent(*reporterState, reporter, "validation_route_manifest_complete", nullptr, terminalReason.empty() ? "all_routes_complete" : terminalReason.c_str(), raw.c_str(), semantic.c_str(), float(Party().ValidationRouteManifestIndex + 1), uint32(Party().ValidationRouteManifest.size()));
        }
        uint64 nowMs = NowMs();
        for (WorldBotState& state : Party().Bots)
        {
            state.TargetGuid.Clear();
            state.ValidationRouteCombatProgressTargetGuid.Clear();
            state.ValidationRoutePackProgressTargetGuid.Clear();
            state.ValidationRouteTerminalState = true;
            state.ValidationRouteTerminalAtMs = nowMs;
            state.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
            state.ValidationRouteTerminalReason = terminalReason.empty() ? "all_routes_complete" : terminalReason;
            state.LoopRecoveryCooldownUntilMs = nowMs + 60000;
        }
        Party().ValidationRouteManifestAdvancePending = false;
        Party().ValidationRouteManifestAdvanceGeneration = 0;
        Party().ValidationRouteManifestAdvanceReason.clear();
        return true;
    }

    if (reporterState && reporter)
    {
        std::string raw = BuildRawJson(reporter, nullptr);
        std::string semantic = BuildSemanticJson(reporter, nullptr, "validation_route_manifest", nullptr);
        RecordEvent(*reporterState, reporter, "validation_route_segment_advance", nullptr, "advance_validation_route_segment", raw.c_str(), semantic.c_str(), float(nextIndex), uint32(Party().ValidationRouteManifest.size()));
    }

    return ApplyValidationRouteManifestNode(nextIndex, terminalReason.empty() ? "validation_route_terminal" : terminalReason.c_str());
}
