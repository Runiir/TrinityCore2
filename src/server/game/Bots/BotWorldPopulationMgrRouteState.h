#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_ROUTE_STATE_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_ROUTE_STATE_H

#include "Bots/BotWorldPopulationMgrConfig.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryTelemetry.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeReseparationReceipt.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeSpacingDiagnostic.h"
#include "ObjectGuid.h"

#include <set>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrRouteState
{
    struct RaidRosterPlanSlot
    {
        std::string RosterSlotId;
        std::string Role;
        uint32 SlotIndex = 0;
        uint8 SubGroup = 0;
    };

    struct BotWorldExperimentProfile
    {
        std::string Name;
        std::string Description;
        BotWorldExperimentConfig Config;
        bool HasTargetPopulation = false;
        bool HasMapId = false;
        bool HasZoneId = false;
        bool HasCenter = false;
        bool HasRadius = false;
        bool HasAllowCombat = false;
        bool HasAllowGrinding = false;
        bool HasAllowQuesting = false;
        bool HasAllowDungeons = false;
        bool HasAllowRaids = false;
        bool HasDungeonDifficulty = false;
        bool HasRaidSize = false;
        bool HasRaidDifficulty = false;
        bool HasTrackHeroicRaidProgression = false;
        bool HasEnableProgression = false;
        bool HasRecordDecisions = false;
        bool HasRecordPerception = false;
        bool HasSmartSampling = false;
        bool HasPoolTagFilter = false;
        bool HasSpawnMode = false;
        bool HasAllowConfiguredCenterFallback = false;
        bool HasUseSavedPosition = false;
        bool HasNearPlayerRadius = false;
        bool HasDeathRecoveryMode = false;
        bool HasAutoStartRecording = false;
        bool HasAutoRecordingWindowMinutes = false;
        bool HasAutoRecordingNamePrefix = false;
        bool HasValidationRouteEnable = false;
        bool HasValidationRouteManifestPath = false;
        bool HasValidationRouteAdvanceMode = false;
        bool HasValidationRouteScenarioId = false;
        bool HasValidationRouteNodeId = false;
        bool HasValidationRouteLabel = false;
        bool HasValidationRouteKind = false;
        bool HasValidationRouteMechanicProfile = false;
    };

    struct ValidationRouteManifestNode
    {
        struct RosterIdentity
        {
            std::string RosterSlotId;
            uint32 Guid = 0;
            std::string Name;
            std::string Role;
            std::string ClassSpec;
        };
        std::string ScenarioId;
        std::string RuntimeProfileId;
        std::string NodeId;
        std::string Label;
        std::string Kind;
        std::string NodeKind;
        std::string DescentAction;
        std::string MechanicProfile;
        std::string MechanicContractId;
        ValidationRouteBossRecoveryPolicy BossRecoveryPolicy = ValidationRouteBossRecoveryPolicy::NativeEncounter;
        std::string FormationFamily;
        std::string FormationAnchor;
        std::string FormationScope = "raid";
        std::string FormationOrientation;
        std::string TargetControl;
        std::string MechanicContractError;
        float FormationSpacingYards = 0.0f;
        float FormationMinimumDistanceYards = 0.0f;
        float FormationRadiusYards = 0.0f;
        float FormationArcRadians = 0.0f;
        float FormationArrivalToleranceYards = 0.0f;
        uint32 FormationLaneCount = 0;
        bool AllowAreaDamage = false;
        bool AllowMultidot = false;
        std::vector<uint32> TargetEntries;
        uint32 ControlledAoeMinimumTargets = 0;
        float KillSyncTolerancePct = 0.0f;
        float KillSyncExecutionFloorPct = 0.0f;
        std::string TankSwapTrigger;
        uint32 TankSwapAuraId = 0;
        uint32 TankSwapAuraStacks = 0;
        uint32 TankSwapIntervalMs = 0;
        uint32 TankSwapTriggerSpellId = 0;
        uint32 TankSwapAddEntry = 0;
        std::string TankSwapPhase;
        uint32 InterruptOwnerSlot = 0;
        uint32 InterruptBackupSlot = 0;
        uint32 InterruptTriggerSpellId = 0;
        uint32 InteractableEntry = 0;
        uint32 VehicleEntry = 0;
        uint32 TransportEntry = 0;
        uint32 TransferAreaTriggerId = 0;
        uint32 ExtraActionSpellId = 0;
        uint32 ExtraActionTriggerAuraId = 0;
        uint32 DispelAuraId = 0;
        uint32 DispelOwnerSlot = 0;
        uint32 DispelBackupSlot = 0;
        std::string CooldownCategory;
        uint32 CooldownOwnerSlot = 0;
        uint32 CooldownBackupSlot = 0;
        uint32 CooldownTriggerSpellId = 0;
        std::string CooldownTarget = "self";
        std::string HealerOwnership = "raid_triage";
        std::vector<uint32> HealerOwnerSlots;
        std::vector<uint32> SoakRosterSlots;
        uint32 SoakMinimumCount = 0;
        float SoakRadiusYards = 0.0f;
        uint32 SoakTriggerSpellId = 0;
        uint32 SoakTriggerAuraId = 0;
        uint32 SoakImmunitySpellId = 0;
        uint32 SoakPersonalCooldownSpellId = 0;
        std::string BattleResurrectionPolicy = "native_rotation";
        std::vector<uint32> BattleResurrectionSlots;
        std::string InteractionKind = "none";
        std::string NativeInteractionAction;
        uint32 NativeInteractionEntry = 0;
        std::vector<uint32> NativeInteractionMenus;
        uint32 NativeInteractionOption = 0;
        std::string NativeCompletionKind;
        uint32 NativeCompletionEntry = 0;
        uint32 NativeCompletionSpellId = 0;
        uint32 JumpPadEntry = 0;
        std::string MovementLink = "none";
        std::string PlatformPolicy = "ground";
        uint32 PlatformDestinationMapId = 0;
        uint32 PlatformDestinationAreaId = 0;
        float PlatformMinimumZ = 0.0f;
        float PlatformMaximumZ = 0.0f;
        bool MechanicContractResolved = false;
        uint32 MapId = 0;
        uint32 RecoveryEntranceAreaTriggerId = 0;
        uint32 RecoveryEntranceSourceMapId = 0;
        uint32 RecoveryEntranceTargetMapId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float O = 0.0f;
        float NavigationAnchorX = 0.0f;
        float NavigationAnchorY = 0.0f;
        float NavigationAnchorZ = 0.0f;
        float NavigationAnchorO = 0.0f;
        uint32 BotStartMapId = 0;
        float BotStartX = 0.0f;
        float BotStartY = 0.0f;
        float BotStartZ = 0.0f;
        float BotStartO = 0.0f;
        uint32 TargetEntry = 0;
        ObjectGuid::LowType TargetSpawnId = 0;
        uint32 OpenerTargetEntry = 0;
        std::vector<uint32> AlternateTargetEntries;
        std::vector<uint32> AddTargetEntries;
        std::vector<uint32> PackTargetEntries;
        std::vector<uint32> ScriptedEventEntries;
        std::vector<uint32> ScriptedEventTransitionAuraIds;
        bool ScriptedEventRequirePassive = false;
        uint32 HazardSourceEntry = 0;
        uint32 HazardDetectionSpellId = 0;
        uint32 HazardDamageSpellId = 0;
        std::string HazardShape;
        float HazardRadiusYards = 0.0f;
        float HazardSafetyMarginYards = 0.0f;
        uint32 MinimumDistanceSourceEntry = 0;
        float MinimumDistanceYards = 0.0f;
        std::vector<uint32> SplitSourceGuids;
        std::vector<uint32> SplitLaneARosterSlots;
        std::vector<uint32> SplitLaneBRosterSlots;
        std::vector<uint32> SplitLaneTankSlots;
        std::vector<ValidationRouteMemberAnchor> SplitMemberAnchors;
        std::vector<ValidationRouteMemberAnchor> SplitRecoveryMemberAnchors;
        std::vector<ValidationRouteMemberAnchor> SplitTankCombatAnchors;
        std::vector<ValidationRouteMemberAnchor> SplitTankNavigationAnchors;
        std::vector<ValidationRouteMemberAnchor> SplitTankRecoveryAnchors;
        float SplitMinimumSeparationYards = 0.0f;
        float SplitNavigationMarginYards = 0.0f;
        float SplitArrivalToleranceYards = 0.0f;
        float SplitTankArrivalToleranceYards = 0.0f;
        float SplitNativeMeleeStopYards = 0.0f;
        std::vector<uint32> SplitSeedRosterSlots;
        std::vector<uint32> SplitHealerRosterSlots;
        float SplitSeedMaxRangeYards = 0.0f;
        float SplitTankThreatHeadroomMultiplier = 0.0f;
        uint32 ThunderclapSpellId = 0;
        uint32 ChargeSpellId = 0;
        float ChargeRangeYards = 0.0f;
        uint32 ChargeNativeIntervalMs = 0;
        uint32 VengefulRageSpellId = 0;
        float ClusterRadiusYards = 0.0f;
        std::string PatrolPullPolicy;
        float PatrolWaitX = 0.0f;
        float PatrolWaitY = 0.0f;
        float PatrolWaitZ = 0.0f;
        float PatrolWaitToleranceYards = 0.0f;
        float PatrolAnchorToleranceYards = 0.0f;
        float PatrolEngageRadiusYards = 0.0f;
        float PatrolFutureGuardMarginYards = 0.0f;
        uint32 PatrolPullOwnerRosterSlot = 0;
        uint32 ExpectedAliveCount = 0;
        uint32 ActivationAreaTriggerId = 0;
        uint32 ActivationDataId = 0;
        uint32 ActivationDataValue = 0;
        uint32 ActivationSpawnGroupId = 0;
        uint32 ActivationActionEntry = 0;
        int32 ActivationActionId = 0;
        uint32 ActivationSummonEntry = 0;
        float ActivationSummonX = 0.0f;
        float ActivationSummonY = 0.0f;
        float ActivationSummonZ = 0.0f;
        float ActivationSummonO = 0.0f;
        uint32 OpenerSummonEntry = 0;
        float OpenerSummonX = 0.0f;
        float OpenerSummonY = 0.0f;
        float OpenerSummonZ = 0.0f;
        float OpenerSummonO = 0.0f;
        uint32 ExpectedBotCount = 0;
        std::vector<RosterIdentity> ExpectedRoster;
    };

    struct ValidationRouteEvidence
    {
        std::string NodeId;
        uint64 Generation = 0;
        std::string Kind;
        ObjectGuid TargetGuid;
        uint32 TargetEntry = 0;
        std::string Reason;
    };

    struct ValidationRouteDrudgeMemberGeometry
    {
        uint32 Guid = 0;
        uint32 RosterSlot = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Projection = 0.0f;
        float AnchorX = 0.0f;
        float AnchorY = 0.0f;
        float GroupAnchorBaseX = 0.0f;
        float GroupAnchorBaseY = 0.0f;
        float AnchorDistance = 0.0f;
        float NearestSameLaneDistance = 0.0f;
        uint32 AnchorCandidateIndex = 0;
        bool LaneSideValid = false;
        bool AnchorSelected = false;
        bool AnchorPathValid = false;
        bool SameLaneSpacingValid = false;
    };

    struct ValidationRouteDrudgeThreatCandidateEvidence
    {
        uint32 Guid = 0;
        uint64 RawGuid = 0;
        uint32 Slot = 0;
        uint32 Lane = 0;
        float Threat = 0.0f;
        float Distance = 0.0f;
        float SourceCombatReach = 0.0f;
        float CandidateCombatReach = 0.0f;
        bool IsPlayer = false;
        bool Alive = false;
        bool SameMap = false;
        bool SamePhase = false;
        bool Available = false;
        bool LineOfSight = false;
        bool InRange = false;
        bool NativeCombatRange = false;
        bool CrossLane = false;
        bool NativeSelectorEligible = false;
        bool TacticCrossLaneEligible = false;
        std::string Role;
    };

    struct ValidationRouteDrudgeChargeObservation
    {
        uint64 Sequence = 0;
        uint64 AttemptId = 0;
        uint32 WipeGeneration = 0;
        uint64 RouteGeneration = 0;
        uint64 ObservedAtMs = 0;
        uint64 ObservedIntervalMs = 0;
        ObjectGuid SourceGuid;
        ObjectGuid TargetGuid;
        uint64 TargetRawGuid = 0;
        uint32 SourceSpawnId = 0;
        float SelectedDistance = 0.0f;
        float SourceCombatReach = 0.0f;
        float TargetCombatReach = 0.0f;
        bool SameMap = false;
        bool SamePhase = false;
        bool RangeValid = false;
        bool IntervalValid = false;
        bool Landed = false;
        bool RecoveryTankReturnBarrierOpened = false;
        bool ReseparationRecorded = false;
        float Home0X = 0.0f;
        float Home0Y = 0.0f;
        float Home1X = 0.0f;
        float Home1Y = 0.0f;
        float MidpointX = 0.0f;
        float MidpointY = 0.0f;
        float AxisX = 0.0f;
        float AxisY = 0.0f;
        float LaneSeparation = 0.0f;
        float MinimumDistance = 0.0f;
        float NavigationMargin = 0.0f;
        float GroupAnchorBaseX = 0.0f;
        float GroupAnchorBaseY = 0.0f;
        float Source0X = 0.0f;
        float Source0Y = 0.0f;
        float Source0Projection = 0.0f;
        bool Source0LaneSideValid = false;
        float Source0HealthPct = 0.0f;
        float Source1X = 0.0f;
        float Source1Y = 0.0f;
        float Source1Projection = 0.0f;
        bool Source1LaneSideValid = false;
        float Source1HealthPct = 0.0f;
        uint32 Source0VictimGuid = 0;
        uint32 Source1VictimGuid = 0;
        bool Source0Alive = false;
        bool Source1Alive = false;
        float Tank0X = 0.0f;
        float Tank0Y = 0.0f;
        uint32 Tank0Guid = 0;
        uint32 Tank0Slot = 0;
        float Tank0Projection = 0.0f;
        float Tank0SourceDistance = 0.0f;
        float Tank1X = 0.0f;
        float Tank1Y = 0.0f;
        uint32 Tank1Guid = 0;
        uint32 Tank1Slot = 0;
        float Tank1Projection = 0.0f;
        float Tank1SourceDistance = 0.0f;
        float SourceSeparation = 0.0f;
        float MinimumSourceSeparation = 0.0f;
        float LaneTankX = 0.0f;
        float LaneTankY = 0.0f;
        uint32 LaneTankGuid = 0;
        uint32 LaneTankSlot = 0;
        float LaneTankProjection = 0.0f;
        float LaneTankSourceDistance = 0.0f;
        float OtherTankX = 0.0f;
        float OtherTankY = 0.0f;
        uint32 OtherTankGuid = 0;
        uint32 OtherTankSlot = 0;
        float OtherTankProjection = 0.0f;
        float OtherTankSourceDistance = 0.0f;
        float MinimumMemberSpacing = 0.0f;
        float ArrivalTolerance = 0.0f;
        float TankArrivalTolerance = 0.0f;
        BotRaidDrudgeSpacing::Failure FirstSpacingFailure;
        uint64 NextReseparationReceiptId = 1;
        std::vector<BotRaidDrudgeSpacing::ReseparationReceipt> ReseparationReceipts;
        // Diagnostic-only history for the unresolved landed head.  Both
        // vectors are scope-reset and bounded by the receipt helpers.
        std::vector<BotRaidDrudgeSpacing::RecoveryTick> RecoveryTicks;
        std::vector<BotRaidDrudgeSpacing::NativeTransition> NativeTransitions;
        std::vector<ValidationRouteDrudgeMemberGeometry> MemberGeometry;
        std::set<uint32> ReseparatedRosterGuids;
        std::vector<ValidationRouteDrudgeThreatCandidateEvidence> NativeThreatCandidates;
        uint32 NativeThreatCandidatesCount = 0;
        bool NativeThreatCandidatesComplete = false;
        bool NativeThreatCandidatesTruncated = false;
    };

    struct ValidationRouteDrudgeThreatSeedEvidence
    {
        uint64 Sequence = 0;
        uint64 AttemptId = 0;
        uint32 WipeGeneration = 0;
        uint64 RouteGeneration = 0;
        uint64 ObservedAtMs = 0;
        uint32 MemberGuid = 0;
        uint32 MemberSlot = 0;
        uint32 MemberLane = 0;
        uint32 SourceSpawnId = 0;
        uint32 SourceGuid = 0;
        uint32 SourceLane = 0;
        uint32 SpellId = 0;
        float SelectedDistance = 0.0f;
        float MinRange = 0.0f;
        float MaxRange = 0.0f;
        bool PositionSafe = false;
        bool LineOfSight = false;
        bool InRange = false;
        bool ProfileActionValid = false;
        bool ActionSucceeded = false;
        bool SelectedOffenseUnsuppressed = false;
        bool OtherOffenseSuppressed = false;
        std::string ActionDebugName;
        std::string ActionResult;
    };
}

#endif
