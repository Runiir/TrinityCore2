#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_BOT_STATE_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_BOT_STATE_H

#include "Bots/BotActionArbiter.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotTypes.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeTauntConfirmation.h"
#include "ObjectGuid.h"

#include <deque>
#include <limits>
#include <map>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrBotState
{
    struct WorldBotState
    {
        enum class ValidationDescentPhase : uint8
        {
            Unobserved = 0,
            Approaching,
            Departed,
            Falling,
            Landed,
            Ready,
            Blocked
        };

        struct CombatAttemptDiagnostic
        {
            uint64 RecordedAtMs = 0;
            std::string Phase;
            std::string ActionType;
            uint32 SpellId = 0;
            std::string DebugName;
            ObjectGuid TargetGuid;
            uint32 TargetEntry = 0;
            bool SelfTarget = false;
            std::string Result;
            bool Casting = false;
            bool GlobalCooldown = false;
            bool CooldownReady = false;
            bool KnownSpell = false;
            bool HasPower = false;
            bool LineOfSight = false;
            bool InRange = false;
            bool TargetAlive = false;
            bool TargetAttackable = false;
            bool MeleeAutoAttacking = false;
            bool RangedAutoActive = false;
            bool PetAttacking = false;
            std::string Reason;
            std::string Summary;
        };

        struct RouteProgressDiagnostic
        {
            uint64 RecordedAtMs = 0;
            uint64 Generation = 0;
            std::string NodeId;
            std::string Kind;
            ObjectGuid TargetGuid;
            uint32 TargetEntry = 0;
            float TargetHealthPct = 0.0f;
            float BestHealthPct = 0.0f;
            uint32 NoProgressCount = 0;
            uint32 NoProgressThreshold = 0;
            std::string Reason;
            ObjectGuid VictimGuid;
            bool BotInCombat = false;
            bool BotCasting = false;
            std::string LastCombatAttemptSummary;
            std::string Summary;
        };

        struct SafePosition
        {
            uint32 MapId = 0;
            uint32 ZoneId = 0;
            uint32 AreaId = 0;
            float X = 0.0f;
            float Y = 0.0f;
            float Z = 0.0f;
            float O = 0.0f;
            float HpPct = 1.0f;
            uint64 SeenMs = 0;
        };

        ObjectGuid Guid;
        bool ServerProvisioned = false;
        bool ServerBaselineNormalized = false;
        // Raid identity is assigned once at admission and survives any
        // replacement of the loaded Player object.  It is deliberately not
        // derived from Party().Bots.size(), which changes when a failed spawn
        // is pruned.
        std::string RosterSlotId;
        std::string RosterRole;
        std::string RosterClassSpec;
        float RosterAverageItemLevel = 0.0f;
        // Player-like persistent-presence setup receipt. A successful native
        // cast submission and a later observed aura are recorded separately;
        // neither field manufactures the spell or aura.
        uint32 RequiredPresenceSetupSpellId = 0;
        uint32 RequiredPresenceSetupAuraId = 0;
        bool RequiredPresenceSetupSpellKnown = false;
        uint64 PresenceSetupNativeCastSubmittedAtMs = 0;
        uint64 PresenceSetupAuraObservedAtMs = 0;
        struct NativePersistentPetSetupReceipt
        {
            uint32 RequiredSummonSpellId = 0;
            uint32 RequiredCreatedBySpellId = 0;
            uint32 RequiredEntry = 0;
            uint32 RequiredFamilyId = 0;
            uint32 RequiredPetType = 0;
            uint32 RequiredPowerType = 0;
            bool SummonSpellKnown = false;
            uint64 NativeCastSubmittedAtMs = 0;
            uint64 NativeCastFinishedAtMs = 0;
            bool NativeCastFinishedSuccessfully = false;
            uint64 NativeCastObservedAtMs = 0;
            uint64 PreScoreResummonRequestedAtMs = 0;
            uint64 PreScoreResummonSubmittedAtMs = 0;
            uint64 PreScoreResummonFinishedAtMs = 0;
            bool PreScoreResummonFinishedSuccessfully = false;
            uint64 PreScoreResummonObservedAtMs = 0;
            bool PreScoreResummonFailed = false;
            uint32 PreScoreResourceBefore = 0;
            uint32 PreScoreResourceMaximumBefore = 0;
            uint32 PreScoreResourceAfter = 0;
            uint32 PreScoreResourceMaximumAfter = 0;
        };
        // Pet classes use the ordinary learned summon and later reconcile the
        // resulting owned permanent pet. Submission, native spell finish, and
        // the subsequent complete pet observation are independent receipts;
        // none of them creates, teaches, heals, or refills the pet.
        NativePersistentPetSetupReceipt PersistentPetSetup;
        struct NativePoisonSetupReceipt
        {
            uint8 EquipmentSlot = 0;
            uint32 RequiredItemEntry = 0;
            uint32 RequiredSpellId = 0;
            uint32 RequiredEnchantId = 0;
            bool ItemAvailable = false;
            bool SpellAvailable = false;
            ObjectGuid SubmittedItemGuid;
            ObjectGuid SubmittedWeaponGuid;
            uint64 NativeUseSubmittedAtMs = 0;
            uint64 NativeUseFinishedAtMs = 0;
            bool NativeUseFinishedSuccessfully = false;
            ObjectGuid NativeUseFinishedItemGuid;
            ObjectGuid NativeUseFinishedWeaponGuid;
            uint64 NextNativeUseRetryAtMs = 0;
            uint64 EnchantObservedAtMs = 0;
            ObjectGuid ObservedWeaponGuid;
            uint32 ObservedWeaponItemEntry = 0;
            uint32 ObservedEnchantId = 0;
            uint32 ObservedEnchantDurationMs = 0;
        };
        // Rogue poisons are ordinary consumable item uses. The active bot
        // must submit each live inventory request and later observe its exact
        // weapon enchant; provisioning never writes temporary enchants.
        bool RoguePoisonSetupRequired = false;
        NativePoisonSetupReceipt RogueMainhandPoisonSetup;
        NativePoisonSetupReceipt RogueOffhandPoisonSetup;
        uint32 DecisionTimer = 0;
        uint32 StuckTimer = 0;
        uint8 StuckRecoveryStage = 0;
        uint64 StuckRecoveryStartedMs = 0;
        uint32 DeadTimer = 0;
        bool DeathEpisodeRecorded = false;
        // One receipt-bound recovery episode owns every native action from
        // Release Spirit through entrance traversal and corpse reclaim.  The
        // identity fields prevent a later death/route/wipe from inheriting
        // progress or retry authority from an earlier corpse.
        uint64 NativeRecoveryEpisodeAttemptId = 0;
        uint64 NativeRecoveryEpisodeRouteGeneration = 0;
        uint64 NativeRecoveryEpisodeWipeGeneration = 0;
        uint32 NativeRecoveryEpisodeDeathOrdinal = 0;
        std::string NativeRecoveryEpisodePhase = "none";
        uint64 NativeRecoveryEpisodeStartedMs = 0;
        uint64 NativeRecoveryEpisodeLastProgressMs = 0;
        std::string NativeRecoveryEpisodeDistanceTarget = "none";
        float NativeRecoveryEpisodeBestDistance = std::numeric_limits<float>::max();
        uint32 NativeRecoveryMovementRetryCount = 0;
        uint32 NativeRecoveryReleaseRejectionCount = 0;
        uint32 NativeRecoveryEntranceUnavailableCount = 0;
        uint32 NativeRecoveryEntranceRejectionCount = 0;
        uint32 NativeRecoveryReclaimRejectionCount = 0;
        bool NativeRecoveryEntranceRequired = false;
        bool NativeRecoveryEntranceObserved = false;
        bool NativeRecoveryEntranceAvailable = false;
        bool NativeRecoveryGhostFlightEnabled = false;
        uint64 NativeReadyCheckRequestGenerationResponded = 0;
        uint64 NativeReadyCheckStableGeneration = 0;
        uint64 NativeReadyCheckStableSinceMs = 0;
        uint64 NativeResurrectionPendingUntilMs = 0;
        std::string NativeBattleResDecision = "unresolved";
        ObjectGuid NativeBattleResOwnerGuid;
        uint32 NativeBattleResSpellId = 0;
        uint64 NativeBattleResDecisionAtMs = 0;
        uint64 NativeBattleResDecisionUntilMs = 0;
        // A planned approach reservation is not enough to hold a corpse. The
        // owner kernel must have accepted a matching typed movement intent
        // recently; otherwise the dead member releases like a player.
        uint64 NativeBattleResApproachIntentDecisionAtMs = 0;
        uint64 NativeBattleResApproachIntentAcceptedUntilMs = 0;
        bool NativeReleaseRequested = false;
        uint32 NativeRunbackAreaTriggerId = 0;
        bool NativeReleaseLandingObserved = false;
        uint32 NativeReleaseLandingMapId = 0;
        uint32 NativeReleaseLandingInstanceId = 0;
        uint64 NativeReleaseLandingWipeGeneration = 0;
        float NativeReleaseLandingX = 0.0f;
        float NativeReleaseLandingY = 0.0f;
        float NativeReleaseLandingZ = 0.0f;
        uint32 LastRaidTankSwapTriggerSpellId = 0;
        std::string LastRaidTankSwapTriggerKey;
        uint64 LastRaidTankSwapMs = 0;
        uint64 LastRaidTankSwapWipeGeneration = 0;
        uint32 LastRaidJumpPadEntrySubmitted = 0;
        uint64 LastRaidJumpPadRouteGeneration = 0;
        ObjectGuid NativeResurrectionCasterGuid;
        uint32 NativeResurrectionSpellId = 0;
        ObjectGuid NativeResurrectionRejectedTargetGuid;
        uint32 NativeResurrectionRejectedSpellId = 0;
        uint32 NativeResurrectionRejectedCastResult = 0;
        uint64 NativeResurrectionRetryAfterMs = 0;
        uint8 NativeResurrectionConsecutiveFailures = 0;
        uint64 GroupReadinessStableSinceMs = 0;
        ObjectGuid ValidationRouteDodgeCasterGuid;
        uint32 ValidationRouteDodgeSpellId = 0;
        uint64 ValidationRouteDodgeUntilMs = 0;
        uint8 ValidationRouteDodgeBearingAttempt = 0;
        uint64 HunterPetRevivePendingUntilMs = 0;
        uint64 HunterPetReviveStartedMs = 0;
        uint32 HunterPetReviveAttemptCount = 0;
        uint32 SafePositionTimer = 0;
        uint32 PoiScanTimer = 0;
        uint32 RestTimer = 0;
        uint32 Sequence = 0;
        // Decision ticks and trace rows are different streams. A decision
        // may emit several event rows before the next decision, so trace
        // identity must not reuse the decision sequence.
        uint64 TraceSequence = 0;
        uint64 ActivityId = 0;
        float ActivityStartPower = 0.0f;
        uint64 ActivityStartGold = 0;
        uint32 ActivityStartDeaths = 0;
        uint32 QuestStartTime = 0;
        uint32 QuestStartDeaths = 0;
        uint32 LastQuestId = 0;
        uint32 LastQuestCompletedCount = 0;
        uint32 LastQuestObjectiveProgress = 0;
        uint64 SpawnedMs = 0;
        std::string SpawnSource = "unknown";
        bool RaceStartFallbackUsed = false;
        uint32 SpawnMapId = 0;
        float SpawnX = 0.0f;
        float SpawnY = 0.0f;
        float SpawnZ = 0.0f;
        float SpawnO = 0.0f;
        std::string CurrentQuestState = "idle";
        std::string CurrentObjectiveType = "none";
        bool CurrentTargetIsTrainingDummy = false;
        bool CurrentDummyAllowedByQuest = false;
        uint32 RequiredSpellId = 0;
        uint32 RequiredItemId = 0;
        uint32 RequiredTargetEntry = 0;
        uint32 LastQuestProgressBefore = 0;
        uint32 LastQuestProgressAfter = 0;
        std::string LastRejectedTargetReason;
        uint32 RaidBossKills = 0;
        uint32 HeroicRaidBossKills = 0;
        uint32 RaidAttempts = 0;
        uint32 RaidWipes = 0;
        uint32 EventSequence = 0;
        std::string ActivityType = "experiment_exploration";
        std::string ProgressionStage = "leveling";
        float LastX = 0.0f;
        float LastY = 0.0f;
        float LastZ = 0.0f;
        float ActivePathFromX = 0.0f;
        float ActivePathFromY = 0.0f;
        float ActivePathFromZ = 0.0f;
        float ActivePathToX = 0.0f;
        float ActivePathToY = 0.0f;
        float ActivePathToZ = 0.0f;
        float ActivePathSegmentToX = 0.0f;
        float ActivePathSegmentToY = 0.0f;
        float ActivePathSegmentToZ = 0.0f;
        bool ActivePathSegmentValid = false;
        std::string ActivePathTraversalMode;
        bool ActivePathValid = false;
        ObjectGuid ActivePathTargetGuid;
        uint64 ActivePathAttemptId = 0;
        uint32 ActivePathWipeGeneration = 0;
        uint64 ActivePathRouteGeneration = 0;
        std::string ActivePathRouteNodeId;
        std::string LastPathRejectReason;
        uint32 LastDeathMapId = 0;
        uint32 LastDeathAreaId = 0;
        float LastDeathX = 0.0f;
        float LastDeathY = 0.0f;
        uint32 RecentDeathCount = 0;
        ObjectGuid TargetGuid;
        // A melee player's autoattack is a persistent toggle independent of
        // movement and GCD spell scheduling. Keep the desired target explicit
        // so native feedback can be reconciled every world tick.
        ObjectGuid DesiredMeleeAttackTargetGuid;
        BotMeleeAutoAttack::Lane MeleeAutoAttackLane;
        std::string MeleeAutoAttackState = "inactive";
        std::string MeleeAutoAttackSuppressionReason;
        std::string LastMeleeAutoAttackIntentOwner = "none";
        std::string LastMeleeAutoAttackIntentKind = "stop";
        std::string LastMeleeAutoAttackIntentReason;
        std::string LastMeleeAutoAttackOutcome = "not_reconciled";
        uint8 LastMeleeAutoAttackIntentPriority = 0;
        uint32 LastMeleeAutoAttackCandidateCount = 0;
        uint64 LastMeleeAutoAttackReconcileMs = 0;
        bool WasInCombat = false;
        ObjectGuid FeralChargePickupTargetGuid;
        uint64 FeralChargePickupUntilMs = 0;
        ObjectGuid TankPendingSwarmPickupAnchorGuid;
        uint64 TankPendingSwarmPickupUntilMs = 0;
        bool TankPendingSwarmPickupEngagedHandoff = false;
        ObjectGuid FeralActiveSwarmPickupAnchorGuid;
        uint64 FeralActiveSwarmPickupUntilMs = 0;
        bool FeralActiveSwarmPickupAttempted = false;
        bool FeralActiveSwarmPickupArrived = false;
        ObjectGuid FeralHealerThreatHandoffTargetGuid;
        ObjectGuid FeralHealerThreatHandoffAnchorGuid;
        uint64 FeralHealerThreatHandoffUntilMs = 0;
        bool FeralHealerThreatHandoffRemoteCluster = false;
        uint32 ValidationRouteUnresolvedFocusHoldCount = 0;
        ObjectGuid ValidationRouteCombatProgressTargetGuid;
        float ValidationRouteCombatBestHealthPct = 1.0f;
        uint32 ValidationRouteCombatNoProgressCount = 0;
        uint64 ValidationRouteCombatNoProgressSinceMs = 0;
        uint32 ValidationRouteBossSlowProgressCount = 0;
        ObjectGuid ValidationRoutePackProgressTargetGuid;
        float ValidationRoutePackBestHealthPct = 1.0f;
        uint32 ValidationRoutePackNoProgressCount = 0;
        uint64 ValidationRoutePackNoProgressSinceMs = 0;
        bool ValidationRouteActivationApplied = false;
        uint32 ValidationRouteActivationAttempts = 0;
        uint32 ValidationRouteTargetSearchMissCount = 0;
        bool ValidationRouteTerminalState = false;
        uint64 ValidationRouteTerminalAtMs = 0;
        uint64 ValidationRouteGeneration = 0;
        uint64 ValidationRouteTerminalGeneration = 0;
        std::string ValidationRouteTerminalReason;
        // Per-player observations for typed, ordinary-movement descents. A
        // cohort may advance only after every member independently departs,
        // lands alive and grounded, and proves a native path onward.
        ValidationDescentPhase ValidationRouteDescentPhase = ValidationDescentPhase::Unobserved;
        uint64 ValidationRouteDescentGeneration = 0;
        float ValidationRouteDescentStartX = 0.0f;
        float ValidationRouteDescentStartY = 0.0f;
        float ValidationRouteDescentStartZ = 0.0f;
        float ValidationRouteDescentInitialGoalDistance = 0.0f;
        float ValidationRouteDescentBestGoalDistance = 0.0f;
        float ValidationRouteDescentLandingX = 0.0f;
        float ValidationRouteDescentLandingY = 0.0f;
        float ValidationRouteDescentLandingZ = 0.0f;
        float ValidationRouteDescentLandingHealthPct = 0.0f;
        uint64 ValidationRouteDescentLastProgressMs = 0;
        uint64 ValidationRouteDescentGroundedSinceMs = 0;
        bool ValidationRouteDescentDepartureObserved = false;
        bool ValidationRouteDescentFallingObserved = false;
        bool ValidationRouteDescentLandingObserved = false;
        bool ValidationRouteDescentHealthMarginSatisfied = false;
        bool ValidationRouteDescentLandingPathProven = false;
        bool ValidationRouteDescentMonotonicProgressObserved = false;
        std::string ValidationRouteDescentRejectReason;
        bool ValidationCohortLocked = false;
        bool ValidationCohortViolation = false;
        std::string ValidationCohortViolationReason;
        ObjectGuid ValidationCohortLeaderGuid;
        ObjectGuid ValidationCohortGroupGuid;
        uint32 ValidationCohortMapId = 0;
        uint32 ValidationCohortInstanceId = 0;
        uint32 ValidationCohortPhaseMask = 0;
        bool ValidationGroupFormationRecorded = false;
        bool ValidationRaidFormationRecorded = false;
        bool ValidationRoleAssignmentRecorded = false;
        bool ValidationRouteAnchorOverrideValid = false;
        uint64 ValidationRouteAnchorOverrideUntilMs = 0;
        float ValidationRouteAnchorOverrideX = 0.0f;
        float ValidationRouteAnchorOverrideY = 0.0f;
        float ValidationRouteAnchorOverrideZ = 0.0f;
        std::string ValidationRouteAnchorOverrideReason;
        std::vector<SafePosition> SafePositions;
        std::map<uint64, uint64> DummyTargetCooldownUntilMs;
        std::map<std::string, uint64> AbilityObjectiveCooldownUntilMs;
        std::map<std::string, uint32> AbilityObjectiveNoProgressCasts;
        ObjectGuid LastKilledTargetGuid;
        ObjectGuid LastLootTargetGuid;
        uint64 LastDecisionTickMs = 0;
        uint64 LastMovementProgressMs = 0;
        uint64 LastPathChangeMs = 0;
        bool IsMoving = false;
        uint32 MovementProgressWindowMs = 0;
        float MovementProgressWindowDistance = 0.0f;
        float DistanceMovedSinceLastDecision = 0.0f;
        float LastDecisionDistanceMoved = 0.0f;
        std::string LastDecisionSituation = "unknown";
        std::string LastDecisionAction = "wait";
        std::string LastDecisionActivity = "experiment_exploration";
        std::string LastDecisionResult = "ok";
        std::string LastDecisionReason;
        std::string LastDecisionHandler = "none";
        BotActionArbitration::Kernel DecisionKernel;
        BotMovementArbitration::Lease MovementLease;
        std::string LastDecisionKernelJson = "{}";
        std::string LastActionCategory = "wait";
        std::string LastClassSpecProfile = "{}";
        std::string LastRoleGoal = "increase_character_power";
        std::string LastRoleSaturationStateJson = "{}";
        std::string LastRecommendedBalanceMode = "role_first";
        std::string LastSaturationReason = "role_first";
        std::string LastProgressionReason = "{}";
        std::string LastProfessionGoal = "{}";
        std::string LastMechanicFamily = "none";
        std::string LastEncounterRoleResponsibility = "maintain_role";
        std::string LastValidActionMaskJson = "{}";
        std::string LastChosenActionJson = "{}";
        std::string LastNextExpectedAction = "wait_for_next_decision_tick";
        std::string LastCombatRejectReason;
        uint32 LastDecisionQuestId = 0;
        ObjectGuid LastDecisionTargetGuid;
        uint32 LastDecisionFingerprintHash = 0;
        uint32 LastDecisionFingerprintRepeatCount = 0;
        uint32 LastDecisionFingerprintFailureCount = 0;
        bool LastDecisionFingerprintFailure = false;
        // Identity fields belong to the active fingerprint stream, not to
        // the most recent decision. They let a pending tail flush against
        // the old row before a changed decision replaces the stream.
        std::string DecisionFingerprintSituation;
        std::string DecisionFingerprintAction;
        std::string DecisionFingerprintActivity;
        std::string DecisionFingerprintResult = "ok";
        uint32 DecisionFingerprintQuestId = 0;
        uint32 DecisionFingerprintClusterId = 0;
        uint32 DecisionFingerprintMapId = 0;
        uint32 DecisionFingerprintZoneId = 0;
        uint32 DecisionFingerprintAreaId = 0;
        // Fingerprint counters remain exact in memory for every decision, but
        // persistence is edge/heartbeat driven so a stuck cohort does not
        // perform a SELECT plus upsert for every decision tick.
        bool DecisionFingerprintInitialized = false;
        uint64 LastDecisionFingerprintPersistMs = 0;
        uint32 LastDecisionFingerprintPersistedRepeatCount = 0;
        uint32 LastDecisionFingerprintPersistedFailureCount = 0;
        std::string LastRepeatableEventKey;
        uint64 LastRepeatableEventEmitMs = 0;
        uint32 SuppressedRepeatableEventCount = 0;
        std::string LastPersistedDiagnosticDecisionKey;
        uint64 LastPersistedDiagnosticDecisionMs = 0;
        uint32 SuppressedDiagnosticDecisionCount = 0;
        uint32 PendingTraceSuppressedRepeatableEventCount = 0;
        uint32 ConsecutiveSameDecisionCount = 0;
        uint32 IdleDecisionRepeatCount = 0;
        uint32 TargetChurnCount = 0;
        uint64 TargetChurnWindowStartMs = 0;
        uint64 LoopRecoveryCooldownUntilMs = 0;
        uint32 LoopGuardrailCount = 0;
        uint64 LastLoopGuardrailMs = 0;
        std::string LastLoopGuardrailAction;
        std::string LastLoopGuardrailReason;
        std::string LastRecoveryMode;
        std::string LastRecoveryResult;
        BotWorldMovement::NativePathFloorObservation LastNativePathFloorObservation;
        uint64 LastRecoveryMs = 0;
        uint32 RecoveryAttemptCount = 0;
        bool Blocked = false;
        uint32 BlockedEpisodeId = 0;
        std::string BlockedFirstReason;
        std::string BlockedReason;
        std::string BlockedResolution;
        // A valid profile action is only a candidate resolution until it is
        // observed on consecutive decision samples.  Keeping this separate
        // from BlockedResolution preserves the raw blocker while a transient
        // resolver result is being debounced.
        std::string BlockedResolutionCandidate;
        uint32 BlockedResolutionCandidateCount = 0;
        std::string BlockedResolvedBy;
        uint64 BlockedStartMs = 0;
        uint64 BlockedProgressBaselineMs = 0;
        uint64 BlockedResolvedMs = 0;
        bool BlockedMessageEmitted = false;
        std::string LastBlockedDiagnosticText;
        bool UnstuckMessageEmitted = false;
        uint64 LastNotInWorldInfoLogMs = 0;
        uint32 SuppressedNotInWorldInfoLogs = 0;
        uint32 NativeRecoveryHoldWipeGeneration = 0;
        uint64 NativeRecoveryHoldLastEnforcedMs = 0;
        uint64 LastValidationRouteDrudgeChargeGenerationHandled = 0;
        // Separate the one-shot observation edge from roster-wide completion.
        // The handled cursor advances only after exact reseparation; using it
        // for invalidation discarded every successful anchor reproof while a
        // charge remained pending.
        uint64 LastValidationRouteDrudgeChargeGenerationObserved = 0;
        BotRaidDrudgeTauntConfirmation::State ValidationRouteDrudgeTaunt;
        // Drudge lane movement must not retry an unreachable derived point on
        // every decision tick.  Once the native path validator finds a
        // collision-safe member anchor, keep that exact fallback for the
        // current attempt/wipe/route generation and reuse it until the
        // geometry is invalidated by a native charge, failed native floor
        // admission, or reset.
        bool ValidationRouteDrudgeAnchorValid = false;
        // A Rush can invalidate current dynamic geometry without invalidating
        // the earlier strict native path proof for the identical scoped point.
        bool ValidationRouteDrudgeAnchorPathProven = false;
        // This is a separate, live PathGenerator proof from the sealed combat
        // anchor to the post-Rush tank pull-away anchor.  The ordinary anchor
        // cache changes identity when a Rush lands, so it cannot also prove
        // that the recovery leg was valid before native combat was opened.
        bool ValidationRouteDrudgeRecoveryAnchorPathProven = false;
        // A landed Rush must first be observed at the strictly validated
        // recovery anchor.  Once latched, the same tank may request only its
        // declared navigation/combat anchor for the native return leg.
        bool ValidationRouteDrudgeRecoveryAnchorReached = false;
        float ValidationRouteDrudgeRecoveryAnchorX = 0.0f;
        float ValidationRouteDrudgeRecoveryAnchorY = 0.0f;
        float ValidationRouteDrudgeRecoveryAnchorZ = 0.0f;
        uint64 ValidationRouteDrudgeAnchorAttemptId = 0;
        uint32 ValidationRouteDrudgeAnchorWipeGeneration = 0;
        uint64 ValidationRouteDrudgeAnchorRouteGeneration = 0;
        uint32 ValidationRouteDrudgeAnchorMapId = 0;
        uint32 ValidationRouteDrudgeAnchorInstanceId = 0;
        uint64 ValidationRouteDrudgeAnchorSource0Identity = 0;
        uint64 ValidationRouteDrudgeAnchorSource1Identity = 0;
        uint32 ValidationRouteDrudgeAnchorCandidateIndex = 0;
        float ValidationRouteDrudgeAnchorX = 0.0f;
        float ValidationRouteDrudgeAnchorY = 0.0f;
        float ValidationRouteDrudgeAnchorZ = 0.0f;
        uint64 ValidationRouteDrudgeAnchorSearchCooldownUntilMs = 0;
        CombatAttemptDiagnostic LastCombatAttempt;
        RouteProgressDiagnostic LastRouteProgress;
        uint32 ProfileCastSuppressedSpellId = 0;
        ObjectGuid ProfileCastSuppressedTargetGuid;
        uint64 ProfileCastSuppressedUntilMs = 0;
        ObjectGuid RouteHealSuppressedTargetGuid;
        uint64 RouteHealSuppressedUntilMs = 0;
        std::map<std::string, uint64> ReadinessRetryUntilMs;
        std::map<std::string, uint32> ReadinessAttemptCount;
        std::map<std::string, std::string> ReadinessPartyCoverageSignature;
        std::string LastPetReadinessAction;
        uint32 LastPetReadinessPetId = 0;
        uint32 LastPetReadinessPetEntry = 0;

        struct DecisionTraceEntry
        {
            uint64 TimestampMs = 0;
            uint64 Sequence = 0;
            uint32 DecisionSequence = 0;
            std::string Situation = "unknown";
            std::string Action = "wait";
            std::string RouteNodeId;
            uint64 RouteGeneration = 0;
            uint32 QuestId = 0;
            uint64 TargetGuid = 0;
            uint32 DestinationMapId = 0;
            float DestinationX = 0.0f;
            float DestinationY = 0.0f;
            float DestinationZ = 0.0f;
            std::string Result = "ok";
            std::string ReasonCode;
            uint32 FingerprintHash = 0;
            uint32 FingerprintRepeatCount = 0;
            uint32 FingerprintFailureCount = 0;
            uint32 ConsecutiveSameDecisionCount = 0;
            uint32 IdleDecisionRepeatCount = 0;
            uint32 TargetChurnCount = 0;
            uint32 SuppressedRepeatableEventCount = 0;
            uint32 SuppressedRepeatableDecisionCount = 0;
            uint32 EngagedHostileCount = 0;
            uint32 TankOwnedHostileCount = 0;
            uint32 HealerTargetingHostileCount = 0;
            std::vector<uint32> EngagedHostileGuids;
            std::vector<uint32> TankOwnedHostileGuids;
            std::vector<uint32> HealerTargetingHostileGuids;
            bool TankThreatAuraActive = false;
            bool PetAlive = false;
            std::string LoopGuardrailAction;
            std::string LoopGuardrailReason;
            std::string RecoveryMode;
            std::string RecoveryResult;
            BotWorldMovement::NativePathFloorObservation NativePathFloor;
            uint32 BlockedEpisodeId = 0;
            std::string BlockedFirstReason;
            std::string BlockedCurrentReason;
            std::string BlockedResolution;
            std::string BlockedResolvedBy;
            CombatAttemptDiagnostic CombatAttempt;
            RouteProgressDiagnostic RouteProgress;
        };
        std::deque<DecisionTraceEntry> DecisionTrace;

        uint32 LootAttemptCount = 0;
        uint64 LootStartedMs = 0;
        uint64 LootCompletedMs = 0;
        std::string LastLootResult = "none";
        uint32 LastLootItemsCount = 0;
        uint64 LastLootMoney = 0;
        bool LastLootStateCleared = false;
        uint64 NextLootAttemptMs = 0;
        uint64 NextGearDecisionMs = 0;
        uint64 NextProfessionDecisionMs = 0;
        bool PreferMaterialMemoryAction = false;
        std::string LastNoProgressReason;
        std::map<std::string, uint64> NoProgressCooldownUntilMs;
        std::map<uint64, uint64> QuestGiverCooldownUntilMs;
        std::map<uint32, uint64> QuestCooldownUntilMs;
        std::map<std::string, uint32> QuestPickupAttemptCount;
        uint32 NewlyAcceptedQuestId = 0;
        uint64 RecentlyAcceptedQuestUntilMs = 0;
        uint64 ObjectiveSearchUntilMs = 0;
        float ObjectiveSearchX = 0.0f;
        float ObjectiveSearchY = 0.0f;
        float ObjectiveSearchZ = 0.0f;
        std::string LastObjectiveNotFoundReason;
        std::string LastGrindingAllowedReason;
        uint32 QuestSearchRadiusIndex = 0;
        uint32 ActiveQuestClusterId = 0;
        std::string LastNoQuestReason;
        std::string LastQuestBucketReason;
        std::string LastQuestClassification;

        struct RouteDestination
        {
            bool Valid = false;
            uint32 MapId = 0;
            float X = 0.0f;
            float Y = 0.0f;
            float Z = 0.0f;
            uint32 QuestId = 0;
            std::string Reason;
        } QuestSearchDestination, QuestRouteDestination;

        struct BotQuestWorkState
        {
            uint32 ActiveQuestId = 0;
            uint32 ObjectiveIndex = 0;
            std::string ObjectiveType = "none";
            int32 RequiredEntry = 0;
            uint32 RequiredItem = 0;
            uint32 RequiredSpell = 0;
            uint32 RequiredCount = 0;
            uint32 CurrentCount = 0;
            ObjectGuid SelectedTargetGuid;
            ObjectGuid SelectedObjectGuid;
            ObjectGuid SelectedGiverGuid;
            std::string Phase = "idle";
            uint64 PhaseStartedMs = 0;
            uint64 LastProgressMs = 0;
            uint32 RetryCount = 0;
            std::string FailedReason;
            uint64 CooldownUntilMs = 0;
            uint32 ProgressBefore = 0;
            uint32 ProgressAfter = 0;
            uint32 VerifiedCasts = 0;
            uint64 VerifyAfterMs = 0;
        } QuestWork;
    };

}

#endif
