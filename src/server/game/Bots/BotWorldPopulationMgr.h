#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_H

#include "ObjectGuid.h"
#include "Bots/BotWorldPopulationMgrConfig.h"
#include "Bots/BotWorldPopulationMgrRouteState.h"
#include "Bots/BotWorldPopulationMgrBotState.h"
#include "Bots/BotActionArbiter.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotExperimentCoordinator.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotTelemetryBuffer.h"
#include "Bots/BotTelemetryPolicy.h"
#include "Bots/BotTypes.h"
#include <array>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <limits>
#include <mutex>
#include <set>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

class Creature;
class Group;
class Map;
class Player;
class Quest;
class Unit;
class WorldObject;
struct BotClassSpecActionProfile;
namespace BotCalibrationFixtureContractGenerated
{
struct SpecContract;
}
struct AreaTriggerEntry;
struct AreaTriggerStruct;

class BotWorldPopulationMgr
{
public:
    static constexpr uint32 MaxActiveCohorts = 1;

    static BotWorldPopulationMgr* instance();

    std::string CreateCohort(std::string const& cohortId);
    bool HasCohort(std::string const& cohortId) const;
    size_t GetCohortCount() const;
    std::string ResolveGlobalCohortId() const;
    std::string GetCohortRegistryJson() const;
    std::string GetCohortIsolationContractJson();
    bool StartAutonomyForCohort(std::string const& cohortId, BotWorldExperimentConfig const* overrideConfig = nullptr);
    std::string StopAutonomyForCohort(std::string const& cohortId);
    std::string SelectRuntimeProfileForCohort(std::string const& cohortId, std::string const& name);
    std::string PrepareValidationProfileForCohort(std::string const& cohortId, std::string const& name,
        std::string const& poolTag = {}, std::vector<std::string> const& classSpecs = {});
    std::string GetStatusJsonForCohort(std::string const& cohortId) const;
    std::string RequestNativeRaidReadyCheckForCohort(std::string const& cohortId);
    std::string GetBotDiagnosisJsonForCohort(std::string const& cohortId, std::string const& selector);
    std::string GetBotTraceJsonForCohort(std::string const& cohortId, std::string const& selector, uint32 limit, bool delta = false) const;
    std::string GetCombatLogJsonForCohort(std::string const& cohortId) const;
    std::string StartCombatCalibrationForCohort(std::string const& cohortId, std::string const& mode = "single_target_300", std::string const& targetSpec = "", uint32 seed = 1);
    std::string StopCombatCalibrationForCohort(std::string const& cohortId);
    std::string GetCombatCalibrationJsonForCohort(std::string const& cohortId) const;

    void Update(uint32 diff);
    bool Start(std::string const& experimentName, BotWorldExperimentConfig const* overrideConfig = nullptr);
    void Stop();
    bool StartAutonomy(BotWorldExperimentConfig const* overrideConfig = nullptr);
    void StopAutonomy();
    void Shutdown();
    bool SpawnAutonomyBots(uint32 count);
    std::string StartCombatCalibration(std::string const& mode = "single_target_300", std::string const& targetSpec = "", uint32 seed = 1);
    std::string StopCombatCalibration();
    std::string GetCombatCalibrationJson() const;
    std::string GetRuntimeProfilesJson();
    std::string SelectRuntimeProfile(std::string const& name);
    std::string ClearRuntimeProfile();
    std::string ReloadRuntimeProfiles();
    std::string PrepareValidationProfile(std::string const& name, std::string const& poolTag = {},
        std::vector<std::string> const& classSpecs = {});
    BotWorldStatus GetStatus() const;
    std::string GetStatusJson() const;
    std::string GetSummaryJson() const;
    std::string GetBotDebugJson(std::string const& selector) const;
    std::string GetBotDiagnosisJson(std::string const& selector);
    std::string GetBotTraceJson(std::string const& selector, uint32 limit, bool delta = false) const;
    std::string GetCombatLogJson() const;
    bool IsActive() const;
    std::string Replay(std::string const& replayType, std::string const& selector, std::string const& brainVersion = "");
    std::string CompareBrains(uint64 replayId, std::string const& firstBrainVersion, std::string const& secondBrainVersion);
    uint64 NotifyBotSpellStarted(Player* caster, Unit* target, uint32 spellId, std::string const& candidateMaskJson = {}, std::string const& chosenActionJson = {});
    void CancelBotSpellStart(uint64 castId, Player* caster, char const* reason);
    void NotifyBotSpellFinished(Player* caster, uint32 spellId, bool success);
    void NotifyBotItemSpellFinished(Player* caster, uint32 spellId,
        bool success, ObjectGuid castItemGuid, ObjectGuid itemTargetGuid,
        uint32 castItemEntry, bool castItemIsPotion);
    void NotifyBotHeal(Unit* healer, Unit* target, uint32 spellId, uint32 attemptedHeal, uint32 effectiveHeal, uint32 absorbedHeal);
    void NotifyCombatAttackAttempt(Unit* attacker, Unit* victim);
    void NotifyCombatDamage(Unit* attacker, Unit* victim, uint32 spellId, uint32 damage, uint32 unmitigatedDamage,
        uint32 damageType, uint32 schoolMask);
    uint64 NotifyNativeCreatureSpellStarted(Creature* caster, Unit* target, uint32 spellId);
    void NotifyNativeCreatureSpellLanded(Creature* caster, Unit* target, uint32 spellId, uint64 observationSequence);
    void NotifyCombatHeal(Unit* healer, Unit* target, uint32 spellId, uint32 attemptedHeal, uint32 effectiveHeal, uint32 absorbedHeal);
    void NotifyCreatureDeath(Creature* killed);

    enum class QuestObjectiveType
    {
        Kill,
        CollectItem,
        InteractGameObject,
        CastSpellOnTarget,
        UseAbilityOnDummy,
        UseItemOnTarget
    };

    enum class QuestClassification
    {
        ObjectiveQuest,
        ChainQuest,
        UnsupportedQuest
    };

private:
    using WorldBotState = BotWorldPopulationMgrBotState::WorldBotState;
    using RaidRosterPlanSlot = BotWorldPopulationMgrRouteState::RaidRosterPlanSlot;
    using BotWorldExperimentProfile = BotWorldPopulationMgrRouteState::BotWorldExperimentProfile;
    using ValidationRouteManifestNode = BotWorldPopulationMgrRouteState::ValidationRouteManifestNode;
    using ValidationRouteEvidence = BotWorldPopulationMgrRouteState::ValidationRouteEvidence;
    using ValidationRouteDrudgeMemberGeometry = BotWorldPopulationMgrRouteState::ValidationRouteDrudgeMemberGeometry;
    using ValidationRouteDrudgeThreatCandidateEvidence = BotWorldPopulationMgrRouteState::ValidationRouteDrudgeThreatCandidateEvidence;
    using ValidationRouteDrudgeChargeObservation = BotWorldPopulationMgrRouteState::ValidationRouteDrudgeChargeObservation;
    using ValidationRouteDrudgeThreatSeedEvidence = BotWorldPopulationMgrRouteState::ValidationRouteDrudgeThreatSeedEvidence;

    struct QuestObjectivePlan
    {
        uint32 QuestId = 0;
        int32 RequiredEntry = 0;
        uint32 RequiredCount = 0;
        uint32 CurrentCount = 0;
        bool IsGameObject = false;
        bool IsItemObjective = false;
        uint32 ItemId = 0;
        QuestObjectiveType ObjectiveType = QuestObjectiveType::Kill;
        uint32 RequiredSpellId = 0;
        uint32 ObjectiveIndex = 0;
        bool RequiresTrainingDummy = false;
    };

    struct QuestActionResult
    {
        bool Handled = false;
        bool Failure = false;
        bool Rare = false;
        std::string Situation = "questing";
        std::string Action = "wait";
        Unit* Target = nullptr;
        uint32 QuestId = 0;
        uint32 RewardChoice = 0;
        uint32 RewardItemId = 0;
    };

    struct BotDiagnosis
    {
        std::string DiagnosisCode = "waiting_decision_tick";
        std::string Severity = "info";
        float Confidence = 0.5f;
        std::string Intent = "increase_character_power";
        std::string CurrentAction = "wait";
        std::string Blocker;
        std::string NextExpectedAction = "wait_for_next_decision_tick";
        std::string SuggestedInvestigation = "inspect_trace_for_repeated_state";
    };

    struct QuestRoutePoint
    {
        bool Valid = false;
        uint32 MapId = 0;
        uint32 ZoneId = 0;
        uint32 QuestId = 0;
        uint32 ObjectiveIndex = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float Score = 0.0f;
        std::string Source;
    };

    struct QuestObjectiveBucket
    {
        uint32 BucketId = 0;
        uint32 MapId = 0;
        float CenterX = 0.0f;
        float CenterY = 0.0f;
        float CenterZ = 0.0f;
        float Score = 0.0f;
        std::vector<QuestObjectivePlan> Objectives;
        std::string Reason;
    };

    struct QuestPortfolioPlan
    {
        uint32 ActiveQuestCount = 0;
        std::vector<QuestObjectiveBucket> Buckets;
        std::vector<QuestObjectivePlan> UnresolvedObjectives;
    };

    struct DungeonTrashPackFeatures
    {
        uint32 PackSize = 0;
        uint32 EliteCount = 0;
        uint32 CasterCount = 0;
        uint32 HealerCount = 0;
        uint32 ActiveCasts = 0;
        uint32 DangerousCasts = 0;
        float InterruptPriority = 0.0f;
        float AoeValue = 0.0f;
        float CcValue = 0.0f;
        float PullRisk = 0.0f;
        float TankThreat = 0.0f;
        float PartyAverageHpPct = 1.0f;
        float LowestAllyHpPct = 1.0f;
        float HealerManaPct = 1.0f;
        bool PatrolNearby = false;
        ObjectGuid PriorityTargetGuid;
        uint32 PriorityTargetEntry = 0;
        uint32 PrioritySpellId = 0;
    };

    struct DungeonTrashActionResult
    {
        bool Handled = false;
        bool Failure = false;
        bool Rare = false;
        std::string Situation = "dungeon_trash";
        std::string Action = "follow_tank";
        Unit* Target = nullptr;
        uint32 SpellId = 0;
        DungeonTrashPackFeatures Pack;
    };

    struct BossMechanicFeatures
    {
        bool RaidEncounter = false;
        bool BossPresent = false;
        bool BossCasting = false;
        uint32 BossEntry = 0;
        uint32 CastSpellId = 0;
        int32 CastRemainingMs = 0;
        bool DangerousCast = false;
        bool MustInterrupt = false;
        bool GroundDanger = false;
        bool MoveOut = false;
        bool TankSpike = false;
        bool RaidDamage = false;
        bool AddsActive = false;
        bool StackPlaceholder = false;
        bool SpreadPlaceholder = false;
        bool InteractableObserved = false;
        bool VehicleObserved = false;
        bool TransportObserved = false;
        bool PlatformTransferObserved = false;
        uint32 AddCount = 0;
        uint32 InteractableCount = 0;
        uint32 VehicleCount = 0;
        float TankHpPct = 1.0f;
        float PartyAverageHpPct = 1.0f;
        float LowestAllyHpPct = 1.0f;
        float HealerManaPct = 1.0f;
        float DangerScore = 0.0f;
        float InterruptPriority = 0.0f;
        ObjectGuid BossGuid;
        ObjectGuid PriorityAddGuid;
        ObjectGuid InteractableGuid;
        ObjectGuid VehicleGuid;
        ObjectGuid TransportGuid;
    };

    struct BossMechanicActionResult
    {
        bool Handled = false;
        bool Failure = false;
        bool Rare = false;
        std::string Situation = "dungeon_boss";
        std::string Action = "boss_wait";
        Unit* Target = nullptr;
        uint32 SpellId = 0;
        BossMechanicFeatures Features;
    };

    struct RaidRoleAssignment
    {
        std::string Role = "dps";
        std::string RosterSlotId;
        std::string LeaseRoleSlot;
        std::string ClassSpec;
        float AverageItemLevel = 0.0f;
        uint8 SubGroup = 0;
        uint32 RaidSize = 0;
        uint32 TankCount = 0;
        uint32 HealerCount = 0;
        uint32 DpsCount = 0;
        uint32 RoleIndex = 0;
        ObjectGuid MainTankGuid;
        ObjectGuid OffTankGuid;
        ObjectGuid RaidLeaderGuid;
    };

    struct RaidPositioningAnchors
    {
        bool Active = false;
        std::string AnchorType = "leader";
        ObjectGuid AnchorGuid;
        float AnchorX = 0.0f;
        float AnchorY = 0.0f;
        float AnchorZ = 0.0f;
        float StackX = 0.0f;
        float StackY = 0.0f;
        float StackZ = 0.0f;
        float SpreadX = 0.0f;
        float SpreadY = 0.0f;
        float SpreadZ = 0.0f;
        std::string FormationFamily = "none";
        float ResolvedX = 0.0f;
        float ResolvedY = 0.0f;
        float ResolvedZ = 0.0f;
        float ArrivalToleranceYards = 0.0f;
        float DistanceToAnchor = 0.0f;
    };

    struct RaidMechanicAdapter
    {
        std::string MechanicFamily = "boss_pressure";
        std::string AssignmentType = "maintain_role";
        std::string RecommendedAction = "boss_single_target";
        // These are declarative, native-observation-backed primitives.  They
        // intentionally carry an explicit unknown/unobserved state instead
        // of manufacturing boss-specific behavior.
        std::string FormationFamily = "role_anchor";
        std::string SwapTrigger = "unobserved";
        std::string TargetControl = "boss_victim";
        std::string RotationDirective = "db_profile_declared";
        std::string HealDirective = "native_heal_profile";
        std::string SoakDirective = "unobserved";
        std::string CooldownDirective = "native_profile_declared";
        std::string BattleResDirective = "native_resurrection_only";
        std::string InteractableDirective = "unobserved";
        std::string VehicleDirective = "unobserved";
        std::string TransportDirective = "unobserved";
        std::string PlatformTransferDirective = "unobserved";
        ObjectGuid AssignedTargetGuid;
        ObjectGuid EvidenceGuid;
        uint32 TriggerSpellId = 0;
        float Priority = 0.0f;
        bool HeroicOnly = false;
        bool AssignmentObserved = false;
        bool EvidenceObserved = false;
        std::string ContractId;
        std::string ContractError;
        bool ContractResolved = false;
        std::string FormationScope = "raid";
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
        uint32 JumpPadEntry = 0;
        std::string MovementLink = "none";
        std::string PlatformPolicy = "ground";
        uint32 PlatformDestinationMapId = 0;
        uint32 PlatformDestinationAreaId = 0;
        float PlatformMinimumZ = 0.0f;
        float PlatformMaximumZ = 0.0f;
    };

    struct RaidGearTargetPlan
    {
        float CurrentItemLevel = 0.0f;
        float TargetItemLevel = 359.0f;
        float NeededItemLevel = 0.0f;
        std::string RecommendedActivity = "raid";
        bool ReadyForRaid = false;
        bool ReadyForHeroicRaid = false;
    };

    struct HeroicRaidProgression
    {
        bool TrackingEnabled = false;
        bool HeroicEligible = false;
        std::string Stage = "normal_raid";
        uint32 RaidAttempts = 0;
        uint32 RaidBossKills = 0;
        uint32 HeroicRaidBossKills = 0;
        uint32 Wipes = 0;
        float RolePowerScore = 0.0f;
        float TargetItemLevel = 372.0f;
    };

    struct PendingHealCast
    {
        uint64 CastId = 0;
        ObjectGuid BotGuid;
        uint32 SpellId = 0;
        ObjectGuid ChosenTargetGuid;
        uint64 StartedAtMs = 0;
        uint64 LastHealAtMs = 0;
        uint64 DeadlineMs = 0;
        uint32 ManaBefore = 0;
        uint32 AttemptedHeal = 0;
        uint32 EffectiveHeal = 0;
        uint32 AbsorbedHeal = 0;
        std::set<uint64> AffectedAllyGuids;
        uint32 AttackersBefore = 0;
        float ThreatBefore = 0.0f;
        std::string CandidateMaskJson;
        std::string ChosenActionJson;
        bool SpellFinished = false;
        uint64 FinishedAtMs = 0;
        uint32 ManaAfterCast = 0;
        uint32 AttackersAfterCast = 0;
        float ThreatAfterCast = 0.0f;
    };

    enum class CombatLogPerspective : uint8
    {
        DamageDone = 0,
        DamageTaken = 1,
        HealingDone = 2,
        HealingReceived = 3
    };

    struct CombatLogAbilityKey
    {
        uint64 RouteGeneration = 0;
        CombatLogPerspective Perspective = CombatLogPerspective::DamageDone;
        uint32 ActorGuid = 0;
        uint32 SourceEntry = 0;
        uint32 SpellId = 0;
        uint32 TargetEntry = 0;
        uint32 EffectType = 0;

        bool operator<(CombatLogAbilityKey const& other) const
        {
            return std::tie(RouteGeneration, Perspective, ActorGuid, SourceEntry, SpellId, TargetEntry, EffectType)
                < std::tie(other.RouteGeneration, other.Perspective, other.ActorGuid, other.SourceEntry,
                    other.SpellId, other.TargetEntry, other.EffectType);
        }
    };

    struct CombatLogAbilityAggregate
    {
        std::string RouteNodeId;
        std::string RouteLabel;
        std::string ActorName;
        std::string ActorRole;
        uint8 ActorClassId = 0;
        std::string SourceName;
        std::string SpellName;
        std::string TargetName;
        uint64 FirstAtMs = 0;
        uint64 LastAtMs = 0;
        uint64 EventCount = 0;
        uint64 Amount = 0;
        uint64 RawAmount = 0;
        uint64 AbsorbedAmount = 0;
        uint64 MovingEvents = 0;
        double DistanceTotal = 0.0;
        float MinDistance = -1.0f;
        float MaxDistance = 0.0f;
        bool SourceIsPet = false;
    };

    struct CombatLogEvent
    {
        uint64 TimestampMs = 0;
        uint64 RouteGeneration = 0;
        std::string RouteNodeId;
        std::string Kind;
        uint32 ActorGuid = 0;
        std::string ActorName;
        std::string ActorRole;
        uint8 ActorClassId = 0;
        uint32 SourceGuid = 0;
        uint32 SourceEntry = 0;
        std::string SourceName;
        uint32 TargetGuid = 0;
        uint32 TargetEntry = 0;
        std::string TargetName;
        uint32 SpellId = 0;
        std::string SpellName;
        uint32 EffectType = 0;
        uint32 SchoolMask = 0;
        uint32 Amount = 0;
        uint32 RawAmount = 0;
        uint32 AbsorbedAmount = 0;
        float SourceX = 0.0f;
        float SourceY = 0.0f;
        float SourceZ = 0.0f;
        float TargetX = 0.0f;
        float TargetY = 0.0f;
        float TargetZ = 0.0f;
        float Distance = 0.0f;
        bool SourceMoving = false;
        bool SourceIsPet = false;
    };

    struct SemanticOutcomeStats
    {
        bool Known = false;
        uint32 Samples = 0;
        uint32 Successes = 0;
        uint32 Failures = 0;
        uint32 Deaths = 0;
        float AvgReward = 0.0f;
        float AvgPowerDelta = 0.0f;
        float DangerScore = 0.0f;
        float ProgressionValue = 0.0f;
    };

    struct ReplayRecord
    {
        bool Loaded = false;
        uint64 Id = 0;
        uint64 ExperimentId = 0;
        uint64 RunId = 0;
        uint32 BotGuid = 0;
        std::string ReplayType;
        uint32 MapId = 0;
        uint32 ZoneId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float O = 0.0f;
        std::string BotSnapshotJson;
        std::string WorldSnapshotJson;
        std::string PartySnapshotJson;
        std::string RawStateJson;
        std::string SemanticStateJson;
        std::string ChosenActionJson;
        std::string FailureJson;
    };

    struct ReplayExecutionResult
    {
        bool Ok = false;
        bool Success = false;
        uint64 ReplayId = 0;
        uint64 RunId = 0;
        std::string BrainVersion;
        std::string FailureReason;
        uint32 Decisions = 0;
        uint32 Failures = 0;
        uint32 Deaths = 0;
        uint32 Kills = 0;
        uint32 StuckEvents = 0;
        float FinalPower = 0.0f;
        std::string FirstAction;
        std::string ReplayType;
    };

    struct SpawnPlacement
    {
        bool Valid = false;
        uint32 MapId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        float O = 0.0f;
        std::string Source;
        bool RaceStartFallbackUsed = false;
    };

    struct BotDeathRecoveryPolicy
    {
        std::vector<std::string> Modes;
        uint32 MaxDeathsBeforeFallback = 3;
    };

    struct DeathRecoveryResult
    {
        bool Recovered = false;
        bool InProgress = false;
        bool UsedFallback = false;
        bool RepeatedDeath = false;
        std::string Mode;
        std::string Result = "failed";
    };

    struct PolicyModelTrace
    {
        bool Enabled = false;
        float ModelScore = 0.0f;
        uint32 ModelRank = 0;
        uint32 FeaturesHash = 0;
        std::string Json = "{}";
    };

    void LoadConfig(std::string const& name, BotWorldExperimentConfig const* overrideConfig);
    void ApplyRuntimeConfigOverride(BotWorldExperimentConfig const& overrideConfig);
    void ApplyRuntimeProfile(BotWorldExperimentProfile const& profile);
    bool SelectConfiguredRuntimeProfile();
    bool EnsureRuntimeProfilesLoaded();
    bool LoadRuntimeProfiles(std::string* failureReason = nullptr);
    std::string RuntimeProfilesJson(char const* action) const;
    void MaybeStartAutoRecordingWindow();
    void RotateAutoRecordingWindowIfNeeded(uint32 diff);
    std::string BuildAutoRecordingWindowName() const;
    void ValidatePolicyModelDeployment();
    bool LoadPolicyModelArtifact(std::string const& artifactPath);
    void EnsurePopulation();
    void EnsureValidationRaidAdmission(
        std::vector<RaidRosterPlanSlot> const& rosterPlan,
        uint32 expectedPopulation);
    void EnsureCalibrationPopulation();
    void ResetCalibrationScoredWindow();
    void UpdateCalibrationTargetHealthSchedule(uint64 nowMs);
    void UpdateCalibrationControlledDamage();
    void CompleteCalibrationScoredWindow();
    void DrainCalibrationPostWindowEffects();
    bool UpdateCalibrationHealer(WorldBotState& state, Player* healer);
    struct CalibrationMetrics;
    std::pair<bool, bool> ApplyCalibrationReferenceConditions(Player* bot, Unit* target) const;
    void ObserveCalibrationReferenceConditions(CalibrationMetrics& metrics,
        Player* bot, Unit* target, uint64 observedAtMs) const;
    static void ObserveAfflictionCalibrationModifiers(CalibrationMetrics& metrics,
        Player* bot, Creature* fixtureTarget);
    static std::string AppendAfflictionCalibrationJson(CalibrationMetrics const* metrics);
    void AppendCalibrationBotActionJson(std::ostringstream& json,
        CalibrationMetrics const* metrics) const;
    void AppendCalibrationReferenceConditionJson(std::ostringstream& json,
        WorldBotState const& state, CalibrationMetrics const* metrics,
        BotCalibrationFixtureContractGenerated::SpecContract const* fixtureSpecContract) const;
    void UpdateCalibrationBot(WorldBotState& state, uint32 diff);
    bool ResolveSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const;
    bool ResolveSavedSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const;
    bool ResolveRaceStartSpawnPlacement(uint32 candidateGuid, SpawnPlacement& placement) const;
    bool ResolveNearPlayerSpawnPlacement(SpawnPlacement& placement) const;
    bool ResolveConfiguredCenterSpawnPlacement(SpawnPlacement& placement) const;
    bool IsValidBotResumePosition(uint32 botGuid, uint32 mapId, float x, float y, float z) const;
    bool IsConfiguredCenterPosition(uint32 mapId, float x, float y, float z) const;
    void PersistBotPosition(Player* bot) const;
    void RecordSpawnResolved(WorldBotState& state, Player* bot, SpawnPlacement const& placement, char const* result);
    void PublishEncounterBlackboard(uint64 nowMs);
    bool CurrentCombatResOwnerUsable(WorldBotState const& targetState, Player const* target,
        uint64 nowMs, std::string& declineReason) const;
    std::optional<BotNativeAction::Candidate> BuildCombatResNativeActionCandidate(
        WorldBotState& ownerState, Player* owner, uint64 nowMs);
    void PublishNativeBattleResDecision(WorldBotState& targetState, Player* target,
        std::string const& decision, ObjectGuid ownerGuid, uint32 spellId,
        uint64 nowMs, uint64 decisionUntilMs);
    void ReconcileNativeBattleResDecisions(uint64 nowMs);
    void UpdateBot(WorldBotState& state, uint32 diff);
    void HandleBotDeath(WorldBotState& state, Player* bot, uint32 diff);
    void TryRespondNativeRaidReadyCheck(WorldBotState& state, Player* bot);
    bool IsNativeRaidRecoveryEvidencePending() const;
    bool AreNativeRaidRecoveryControlledUnitsReady(Player* bot) const;
    bool TryRestoreNativeRaidRecoveryPet(WorldBotState& state, Player* bot);
    void SuppressNativeRaidRecovery(WorldBotState& state, Player* bot);
    bool TryReattachValidationBot(WorldBotState& state, Player* bot, char const* context);
    bool IsNativeCombatResTarget(WorldBotState const& state, Player const* bot) const;
    bool HasNativeRaidCorpseAuthority(WorldBotState const& state, Player const* bot) const;
    bool ObserveNativeRaidHostileActivity(Map* raidMap, WorldObject const* observer,
        bool& active, std::string& reason, uint32& entry, ObjectGuid& guid) const;
    bool ResolveNativeValidationEntrance(uint32 targetMapId, uint32 sourceMapId, float sourceX, float sourceY,
        AreaTriggerEntry const*& entry, AreaTriggerStruct const*& destination) const;
    bool IsNativeReleasedGhostWorldport(WorldBotState const& state, Player* bot) const;
    bool IsNativeValidationRunbackWorldport(WorldBotState const& state, Player* bot) const;
    void RememberSafePosition(WorldBotState& state, Player* bot, uint32 diff);
    void PruneSafePositions(WorldBotState& state, uint64 nowMs) const;
    void RememberVisiblePois(WorldBotState& state, Player* bot, uint32 diff);
    void RememberPoi(WorldBotState& state, Player* bot, WorldObject* object, char const* poiType, uint32 questId, float score) const;
    void MarkDeathDangerZone(WorldBotState& state, Player* bot, Unit const* target);
    void MarkStuckFailure(WorldBotState& state, Player* bot);
    float GetLocalDangerScore(uint32 botGuid, uint32 mapId, float x, float y, float z) const;
    bool IsFailedPathRecently(uint32 botGuid, uint32 mapId, float fromX, float fromY, float toX, float toY) const;
    bool FindMemoryPoiTarget(Player* bot, float& x, float& y, float& z, uint64& poiId) const;
    void MarkPoiVisited(uint64 poiId) const;
    bool MoveBotToPoint(WorldBotState& state, Player* bot, float x, float y, float z,
        bool terminalOnFailure = false,
        BotMovementArbitration::Owner movementOwner = BotMovementArbitration::Owner::None,
        BotMovementArbitration::Priority movementPriority = BotMovementArbitration::Priority::Idle,
        Unit* dynamicTarget = nullptr, float dynamicTargetRange = 0.0f);
    BotActionArbitration::Outcome ExecuteNativeActionIntent(WorldBotState& state, Player* bot,
        BotNativeAction::Intent const& intent,
        BotMovementArbitration::Owner movementOwner = BotMovementArbitration::Owner::None,
        BotMovementArbitration::Priority movementPriority = BotMovementArbitration::Priority::Idle);
    BotActionArbitration::Outcome ExecuteNativeDescentIntent(WorldBotState& state,
        Player* bot, BotNativeAction::NativeDescent const& intent);
    static char const* ValidationDescentPhaseName(
        WorldBotState::ValidationDescentPhase phase);
    void BeginMeleeAutoAttackDecision(WorldBotState& state, Player* bot);
    bool SubmitMeleeAutoAttackIntent(WorldBotState& state,
        BotMeleeAutoAttack::Kind kind, ObjectGuid target,
        BotMeleeAutoAttack::Owner owner,
        BotActionArbitration::Priority priority, char const* reason);
    void ResolveAndReconcileMeleeAutoAttack(WorldBotState& state, Player* bot);
    BotDeathRecoveryPolicy BuildDeathRecoveryPolicy() const;
    DeathRecoveryResult RecoverDeadBot(WorldBotState& state, Player* bot);
    bool TryNativeCorpseRun(WorldBotState& state, Player* bot, std::string& result);
    Player* GetLoadedBot(WorldBotState const& state) const;
    Player* GetBot(WorldBotState const& state) const;
    std::vector<RaidRosterPlanSlot> BuildRosterPlan() const;
    std::string SelectNextRosterSlot() const;
    std::string GetBotClassSpec(Player const* bot) const;
    uint32 SelectPoolCandidateGuid(std::string const& rosterSlotId = {}, std::set<uint32> const* excludedGuids = nullptr,
        uint32 expectedGuid = 0, std::string const& expectedName = {}, std::string const& expectedClassSpec = {}) const;
    uint32 SelectCalibrationPoolCandidateGuid(size_t slot) const;
    Unit* SelectSafeTarget(WorldBotState& state, Player* bot);
    Unit* SelectQuestObjectiveTarget(Player* bot, QuestObjectivePlan const& plan) const;
    Unit* SelectQuestAbilityObjectiveTarget(Player* bot, QuestObjectivePlan const& plan, WorldBotState const& state) const;
    WorldObject* SelectQuestGiver(Player* bot, bool completeOnly, uint32* questId, WorldBotState const* state = nullptr) const;
    WorldObject* SelectQuestGameObject(Player* bot, QuestObjectivePlan const& plan) const;
    bool FindActiveQuestObjective(Player* bot, QuestObjectivePlan& plan) const;
    bool FindQuestObjective(Player* bot, uint32 questId, QuestObjectivePlan& plan) const;
    bool GetQuestObjectivePlan(Player* bot, uint32 questId, uint32 objectiveIndex, QuestObjectiveType type, QuestObjectivePlan& plan) const;
    QuestClassification ClassifyQuestForBot(Player* bot, Quest const* quest) const;
    QuestPortfolioPlan BuildQuestPortfolioPlan(Player* bot, WorldBotState const& state) const;
    bool FindQuestPickupDestination(Player* bot, WorldBotState const& state, QuestRoutePoint& point) const;
    bool FindQuestTurnInDestination(Player* bot, uint32 questId, QuestRoutePoint& point) const;
    bool ResolveObjectiveRoutePoint(Player* bot, QuestObjectivePlan const& plan, QuestRoutePoint& point) const;
    bool SelectQuestObjectiveBucket(Player* bot, QuestPortfolioPlan const& plan, QuestObjectiveBucket& bucket) const;
    void SetQuestWorkPhase(WorldBotState& state, char const* phase);
    void SetQuestWorkFromPlan(WorldBotState& state, QuestObjectivePlan const& plan);
    void ResetQuestWork(WorldBotState& state);
    bool IsProgressionCombatTarget(Player* bot, Unit* target, char const** rejectReason = nullptr) const;
    bool IsQuestRelevantTarget(Player* bot, Unit* target) const;
    bool HasNearbySupportedQuestGiver(Player* bot, WorldBotState const& state) const;
    bool IsGenericGrindingAllowed(WorldBotState& state, Player* bot, BotProgressionActivity activity, bool hasActiveQuestObjective);
    void MoveToObjectiveSearchPoint(WorldBotState& state, Player* bot, QuestObjectivePlan const* plan, WorldObject const* avoidObject = nullptr);
    bool VerifyQuestObjectiveProgress(WorldBotState& state, Player* bot, QuestObjectivePlan const& plan, Unit const* target, uint32 before, char const* reason, char const* rawJson, char const* semanticJson);
    bool IsTrainingDummy(Unit const* unit) const;
    bool IsTrainingDummyAllowedForQuest(QuestObjectivePlan const& plan, Unit const* target) const;
    bool IsDummyEntryConfigured(uint32 entry, bool* explicitAllow = nullptr) const;
    bool QuestTextSuggestsAbilityObjective(Quest const* quest) const;
    uint32 SelectQuestAbilitySpell(Player* bot, Quest const* quest, QuestObjectivePlan const& plan) const;
    uint32 QuestObjectiveProgress(Player* bot, QuestObjectivePlan const& plan) const;
    bool StopDisallowedDummyCombat(WorldBotState& state, Player* bot, Unit* target);
    bool HasSimpleSupportedObjective(Quest const* quest) const;
    uint32 ChooseQuestReward(Player* bot, Quest const* quest, uint32* rewardItemId = nullptr) const;
    QuestActionResult TryQuesting(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity);
    bool TryValidationRouteObjective(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action, Unit*& target);
    bool TryValidationRouteGroupHeal(WorldBotState& state, Player* bot,
        Player* healer, Unit* combatTarget,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, std::string& situation,
        std::string& action, bool allowMovement = true,
        bool allowStationaryCastTime = false);
    bool TryValidationRoutePatrolPull(WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, std::string& situation,
        std::string& action, Unit*& target,
        std::function<bool(Player*, Unit*, bool, bool)> const& tryRouteGroupHeal,
        std::function<ObjectGuid::LowType()> const& currentValidationRouteTargetSpawnId,
        std::function<bool(Creature const*)> const& isValidationCohortCombatLinked,
        std::function<void(Creature const*, bool)> const& enrollValidationRoutePackMember);
    bool TryValidationFeralRoarPickup(WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, std::string& situation,
        std::string& action, Unit*& target, std::string const& role,
        BotClassSpecActionProfile const& profile, Player* densityHealer,
        std::vector<Creature*> const& localAdds,
        std::function<size_t(Player const*)> const& observedListedAttackerCount,
        bool activeClusterArrived);
    bool ContinueStableTankSwarmApproach(
        WorldBotState& state, Unit* selectedAdd, Player* densityHealer,
        std::string const& role, BotClassSpecActionProfile const& profile,
        bool cohortSwarmActive, float tankDensityClusterRadius) const;
    void MarkValidationRouteTerminalAfterProgress(
        char const* reason, WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, std::string& situation,
        std::string& action, Unit*& target, float routeDistance);
    void MarkTrashClusterCleared(WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, char const* reason);
    void MarkValidationRouteTrashFailed(WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, Unit* failedTarget, char const* reason,
        char const* situationName, float metric, uint32 data,
        float bestHealthPct = -1.0f, uint32 noProgressCount = 0,
        uint32 noProgressThreshold = 0);
    void ClearValidationRouteKilledFocus(WorldBotState& state,
        ObjectGuid killedGuid);
    bool RecordValidationRouteBossKill(WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, Unit* killedTarget,
        char const* assistResult);
    bool RecordValidationRouteTrashKill(WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, Unit* killedTarget, char const* reason,
        std::function<bool(Creature const*)> const& isValidationRouteScriptTarget,
        std::function<bool()> const& trashClusterHasLiveMobs);
    bool RecordDefeatedValidationRouteTarget(Unit* defeatedTarget,
        char const* reason,
        std::function<bool(Creature const*)> const& isValidationRouteScriptTarget,
        std::function<bool(Unit*, char const*)> const& recordValidationRouteBossKill,
        std::function<bool(Unit*, char const*)> const& recordValidationRouteTrashKill);
    bool RecordDefeatedValidationRoutePackMembers(Player* bot,
        std::function<bool(Unit*, char const*)> const& recordValidationRouteTrashKill);
   bool CompleteDiscoveredPackIfReady(bool discoveryLeg, Player* bot,
       WorldBotState& state, BotRolePowerBreakdown const& power,
       BotProgressionStage stage, BotProgressionActivity activity,
       std::function<bool()> const& validationPartyHasActiveCombat);
    bool MaybeValidationPrerequisiteNoProgressAssist(
        WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity,
        std::function<bool(Creature const*)> const& isValidationRouteScriptTarget,
        std::function<bool(uint32)> const& isValidationRoutePackEntry,
        std::function<bool(Unit*, char const*)> const& recordValidationRouteTrashKill,
        Unit* prerequisiteTarget, char const* context);
    Unit* ResolveUsableValidationRouteCombatTarget(
        Player* bot, bool discoveryLeg, Unit* candidate,
        std::function<bool(Creature const*)> const& isValidationRouteCombatTarget,
        std::function<bool(Creature const*)> const& isEligibleTrashClusterMob,
        std::function<bool(Unit const*)> const& hasStrictPathToValidationRouteTarget,
        std::function<bool(Creature const*)> const& isBoundedTerminalPartyCombatTarget,
        std::function<bool(Creature const*)> const& isCurrentDiscoveryScriptedEventTarget);
    Unit* FindValidationRouteGroupFocusTarget(
        Player* bot,
        std::function<Unit*(Unit*)> const& routeUsableValidationFocus,
        std::function<bool()> const& routeFocusMemoryFresh);
    ObjectGuid FindValidationRouteTankFocusGuid(
        Player* bot,
        std::function<Unit*(Unit*)> const& routeUsableValidationFocus,
        std::function<bool()> const& routeFocusMemoryFresh);
    void RememberValidationRouteFocus(Unit* focus);
    Unit* MakeExistingValidationRouteCombatReady(
        Player* bot, Creature* creature,
        std::function<bool(Creature const*)> const& isValidationRouteCombatTarget);
    bool TryValidationRouteActivation(
        WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, Unit* seenTarget,
        char const* reason);
    bool TryValidationRouteInterrupt(
        WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, std::string& situation,
        std::string& action, Unit* interruptTarget, char const* context);
   Unit* FindValidationRouteTankFocusTarget(
       Player* bot, std::function<Unit*(Unit*)> const& routeUsableCombatTarget,
       ObjectGuid expectedGuid);
    Unit* FindLastKnownValidationRouteFocusTarget(
        Player* bot, std::function<Unit*(Unit*)> const& routeUsableCombatTarget,
        std::function<bool()> const& routeFocusMemoryFresh);
    Unit* FindAuthoritativeValidationRouteFocusTarget(
        Player* bot, std::function<Unit*(Unit*)> const& routeUsableCombatTarget,
        std::function<bool(Creature const*)> const& isValidationRouteScriptTarget,
        std::string& authoritativeFocusFailure);
    bool RecoverAuthoritativeValidationRouteFocus(
        WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity,
        std::function<Unit*()> const& findAuthoritativeRouteFocusTarget,
        std::string const& authoritativeFocusFailure, char const* context);
    Unit* TeacherAssistAuthoritativeValidationFocus(
        WorldBotState& state, Unit* proposedFocus,
        std::function<bool()> const& authoritativeRouteFocusActive,
        std::function<Unit*()> const& findAuthoritativeRouteFocusTarget,
        std::string& authoritativeFocusFailure);
    bool CurrentLiveValidationRoutePackCanContinue(
        std::function<bool()> const& persistedValidationRoutePackHasLiveMembers,
        std::function<bool(uint32)> const& isValidationRoutePackEntry,
        std::function<uint32(Creature const*)> const& resolvedScriptedTransitionAuraId);
    void ConfigureValidationRouteCombatAuthority(Player* bot) const;
    bool IsImmediateNextValidationRouteBossTarget(Creature const* creature) const;
    bool IsImmediateNextValidationRouteEncounterMember(Creature const* creature) const;
    bool IsBossContext(Player* bot, Unit const* target) const;
    Unit* FindBossTarget(Player* bot) const;
    BossMechanicFeatures BuildBossMechanicFeatures(Player* bot, Unit const* boss) const;
    void ReconcileRaidAreaAutocasts(Player* bot, bool suppress) const;
    bool PrepareBossMechanicAction(WorldBotState& state, Player* bot,
        Unit* boundRouteTarget, BossMechanicActionResult& result);
    BossMechanicActionResult TryBossMechanics(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, Unit* boundRouteTarget = nullptr);
    RaidRoleAssignment BuildRaidRoleAssignment(Player* bot) const;
    RaidPositioningAnchors BuildRaidPositioningAnchors(Player* bot, Unit const* boss, RaidRoleAssignment const& assignment, BossMechanicFeatures const& features) const;
    RaidMechanicAdapter BuildRaidMechanicAdapter(Player* bot, Unit const* boss, RaidRoleAssignment const& assignment, BossMechanicFeatures const& features) const;
    RaidGearTargetPlan BuildRaidGearTargetPlan(Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    HeroicRaidProgression BuildHeroicRaidProgression(WorldBotState const& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    std::string BuildRaidRuntimeJson(bool compactTelemetry = false) const;
    std::string BuildRaidRoleAssignmentJson(RaidRoleAssignment const& assignment) const;
    std::string BuildRaidPositioningAnchorsJson(RaidPositioningAnchors const& anchors) const;
    std::string BuildRaidMechanicAdapterJson(RaidMechanicAdapter const& adapter) const;
    std::string BuildRaidGearTargetPlanJson(RaidGearTargetPlan const& plan) const;
    std::string BuildHeroicRaidProgressionJson(HeroicRaidProgression const& progression) const;
    void RecordRaidTelemetry(WorldBotState& state, Player* bot, Unit const* boss, char const* eventType, char const* result, BossMechanicFeatures const& features, RaidRoleAssignment const& assignment, RaidPositioningAnchors const& anchors, RaidMechanicAdapter const& adapter, RaidGearTargetPlan const& gearPlan, HeroicRaidProgression const& progression, char const* rawJson, char const* semanticJson, float valueFloat = 0.0f, uint32 valueInt = 0, uint32 spellId = 0);
    bool IsDungeonTrashContext(Player* bot, Unit const* target) const;
    Player* FindDungeonAnchor(Player* bot) const;
    Unit* FindGroupCombatTarget(Player* bot, Player* anchor) const;
    DungeonTrashPackFeatures BuildDungeonTrashPackFeatures(Player* bot, Unit const* focus) const;
    DungeonTrashActionResult TryDungeonTrash(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity);
    bool TryValidationRouteReadiness(WorldBotState& state, Player* bot, Unit* pullTarget, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, DungeonTrashActionResult& result);
    bool TryEnsureCombatTotems(WorldBotState& state, Player* bot, Unit* target, uint32 hostileCount) const;
    bool IsNativePoisonSetupReady(Player const* bot,
        WorldBotState::NativePoisonSetupReceipt const& receipt) const;
    static bool ConfigureAfflictionPetRequirements(
        WorldBotState::NativePersistentPetSetupReceipt& requiredPet,
        char const*& requiredPetName, std::string const& role,
        std::string const& specTag);
    bool TryEnsurePersistentCombatSetup(WorldBotState& state, Player* bot, Unit* target,
        char const* specTagOverride = nullptr);
    char const* GetDungeonRole(Player* bot) const;
    uint32 SelectInterruptSpell(Player* bot) const;
    uint32 SelectHealSpell(Player* bot, Unit* target, bool instantOnly = false) const;
    bool TryCastFriendlySpell(Player* bot, Unit* target, uint32 spellId, std::string* failureReason = nullptr);
    bool TryNativeSelfResurrection(WorldBotState& state, Player* bot);
    std::string BuildDungeonTrashPackJson(DungeonTrashPackFeatures const& pack) const;
    std::string BuildBossMechanicsJson(BossMechanicFeatures const& features) const;
    uint32 SelectCombatSpell(Player* bot, Unit* target) const;
    ResolvedCombatAction ResolveProfileCombatAction(Player* bot, Unit* target, uint32 hostileCount = 0, bool densityOnly = false, uint32 excludedSpellId = 0, bool areaOnly = false, bool selfCenteredOnly = false, bool forbidArea = false, bool allowMultidot = true, bool hostileTargetOnly = false, bool movementCompatibleOnly = false, char const* specTagOverride = nullptr) const;
    BotActionResult ExecuteProfileCombatAction(WorldBotState* state, Player* bot, Unit* target, ResolvedCombatAction* action = nullptr, uint32 hostileCount = 0, bool densityOnly = false, uint32 excludedSpellId = 0, bool areaOnly = false, bool selfCenteredOnly = false, bool forbidArea = false, bool allowMultidot = true, bool hostileTargetOnly = false);
    BotActionResult ExecuteProfileCombatAction(Player* bot, Unit* target, ResolvedCombatAction* action = nullptr, uint32 hostileCount = 0, bool densityOnly = false, uint32 excludedSpellId = 0, bool areaOnly = false, bool selfCenteredOnly = false, bool forbidArea = false, bool allowMultidot = true, bool hostileTargetOnly = false);
    bool MoveBotToProfileRange(WorldBotState& state, Player* bot, Unit* reference,
        ResolvedCombatAction const* action = nullptr, bool forceRangedReposition = false);
    bool TryCastCombatSpell(Player* bot, Unit* target, uint32 spellId) const;
    void MarkBotBlocked(WorldBotState& state, Player* bot, char const* reason) const;
    void ObserveBotCandidateFailure(WorldBotState& state, Player* bot,
        std::string const& key, std::string const& reason,
        uint32 retryBaseMs = 250, uint32 retryMaxMs = 5000,
        uint8 escalateAfter = 5, uint64 minimumFailureDurationMs = 5000) const;
    void MarkBotUnstuck(WorldBotState& state, Player* bot, char const* reason) const;
    bool TryResolveBotBlocker(WorldBotState& state, Player* bot, char const* resolvedBy) const;
    bool TryRecoverStuckBot(WorldBotState& state, Player* bot);
    void MoveToWanderPoint(Player* bot, WorldBotState& state);
    void RecordRunStart();
    void RecordRunStop();
    void LoadValidationRouteManifest();
    bool ApplyValidationRouteManifestNode(size_t index, char const* reason);
    bool MaybeAdvanceValidationRouteManifest();
    void ResetValidationRouteBossAddEscapeState();
    void ResetValidationRouteBossAddDensityState();
    void ResetValidationRouteRuntimeState(char const* reason);
    bool ValidationRouteHasProgressSinceApply() const;
    ReplayRecord LoadReplayRecord(std::string const& replayType, std::string const& selector) const;
    ReplayRecord LoadReplayRecord(uint64 replayId) const;
    ReplayExecutionResult ExecuteReplayRecord(ReplayRecord const& record, std::string const& brainVersion);
    std::string BuildReplayResultJson(ReplayExecutionResult const& result) const;
    void RecordReplayEvent(WorldBotState const& state, Player* bot, char const* eventType, ReplayRecord const& record, char const* result, char const* contextJson = nullptr);
    void RecordActivityStart(WorldBotState& state, Player* bot);
    void RecordActivityStop(WorldBotState const& state, Player* bot = nullptr);
    struct RaidRosterItemIdentity;
    void EnsureValidationCohortGroup();
    void UpdateValidationCohortRaidRuntime(
        std::vector<Player*> const& members, Player* leader, Group* group,
        bool activeObservationOnly, bool raidValidation,
        std::vector<RaidRosterPlanSlot> const& rosterPlan,
        uint32 leaderMapId, uint32 leaderInstanceId);
    void EnsureCalibrationCohortGroup();
    bool ObserveEquippedGearIdentity(Player const* bot,
        std::vector<RaidRosterItemIdentity>& manifest,
        std::string& manifestSha256) const;
    bool EquippedGearManifestsEqual(
        std::vector<RaidRosterItemIdentity> const& left,
        std::vector<RaidRosterItemIdentity> const& right) const;
    bool IsValidationProfileName(std::string const& name) const;
    bool PrepareCurrentValidationProfile(char const* reason);
    bool ApplyValidationProvisioningSql(char const* reason);
    bool ResetValidationBotPool(char const* reason);
    bool IsValidationCohortMemberInOriginalInstance(WorldBotState const& state, Player const* bot) const;
    void MarkValidationCohortViolation(WorldBotState& state, Player const* bot, char const* reason);
    bool FailValidationAttemptOnce(WorldBotState& reporterState, Player* reporter,
        std::string const& reason, uint64 routeGeneration);
    bool TrySmartGearDecision(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action);
    bool TryProfessionMemoryAction(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action);
    void RecordGearEvaluation(WorldBotState& state, Player* bot, BotGearUpgradeEvaluation const& evaluation, char const* rawJson, char const* semanticJson);
    void RecordQuestObjectiveProgressForTarget(WorldBotState& state, Player* bot, Unit const* target, char const* rawJson, char const* semanticJson);
    void RecordQuestEvent(WorldBotState& state, Player* bot, char const* eventType, uint32 questId, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, uint32 valueInt = 0, uint32 itemId = 0, char const* contextJson = nullptr);
    void RecordObjectiveClusterMemory(WorldBotState const& state, Player* bot, char const* eventType, uint32 questId, char const* result, uint32 valueInt, char const* contextJson) const;
    void RememberVisibleSourceMemory(WorldBotState const& state, Player* bot, WorldObject* object, char const* poiType, uint32 entry, uint32 questId, char const* metadataJson) const;
    void RecordExperimentSegmentEvent(Player* bot, char const* eventType, char const* result, uint32 questId, Unit const* target, uint64 clipId, char const* rawJson, char const* semanticJson);
    void RecordQuestReplay(WorldBotState const& state, Player* bot, char const* replayType, uint32 questId, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson);
    void RecordBossReplay(WorldBotState const& state, Player* bot, Unit const* boss, BossMechanicFeatures const& features, char const* replayType, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson);
    uint64 RecordDecisionReplay(WorldBotState const& state, Player* bot, Unit const* target, char const* situation, char const* action, char const* rawJson, char const* semanticJson, char const* candidateJson, BotActivityScore const& chosenActivity, bool failure);
    void RecordEvent(WorldBotState& state, Player* bot, char const* eventType, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, float valueFloat = 0.0f, uint32 valueInt = 0, uint32 spellId = 0);
    void RecordDecision(WorldBotState& state, Player* bot, char const* situation, char const* action, Unit const* target, char const* rawJson, char const* semanticJson, std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, BotRolePowerBreakdown const& power, bool failure, bool rare);
    void RecordDecisionFingerprintMemory(WorldBotState& state, Player* bot, char const* situation, char const* action, BotActivityScore const& chosenActivity, bool failure) const;
    void PersistDecisionFingerprintDelta(WorldBotState& state, uint32 repeatDelta, uint32 failureDelta) const;
    void FlushDecisionFingerprintMemory(WorldBotState& state) const;
    void FlushPendingDecisionFingerprintMemory();
    void RecordDecisionTrace(WorldBotState& state, char const* situation, char const* action, Unit const* target, uint32 questId, char const* result, char const* reasonCode);
    void ResetTraceStreams();
    BotDiagnosis BuildBotDiagnosis(WorldBotState const& state, Player const* bot) const;
    std::string BuildBotDiagnosisObjectJson(WorldBotState const& state, Player const* bot) const;
    std::string BuildBotDecisionSnapshotJson(WorldBotState const& state, Player const* bot) const;
    std::string BuildBotTraceEntriesJson(WorldBotState const& state, uint32 limit) const;
    void RecordCombatAttempt(WorldBotState& state, Player* bot, Unit* target, char const* phase, ResolvedCombatAction const* action, BotActionResult result, char const* reason = nullptr) const;
    void RecordRouteProgress(WorldBotState& state, Player* bot, Unit* target, char const* reason, float targetHealthPct, float bestHealthPct, uint32 noProgressCount, uint32 noProgressThreshold) const;
    std::string BuildCombatAttemptJson(WorldBotState::CombatAttemptDiagnostic const& diagnostic) const;
    std::string BuildRouteProgressJson(WorldBotState::RouteProgressDiagnostic const& diagnostic) const;
    std::string BuildCombatAttemptSummary(WorldBotState::CombatAttemptDiagnostic const& diagnostic) const;
    std::string BuildRouteProgressSummary(WorldBotState::RouteProgressDiagnostic const& diagnostic) const;
    std::string BuildBlockedDiagnosticText(WorldBotState const& state, char const* reason) const;
    BotTelemetryPolicyConfig GetTelemetryPolicyConfig() const;
    BotTelemetryPolicyInput BuildTelemetryPolicyInput(char const* eventType, char const* result, char const* situation, Unit const* target, uint32 spellId = 0, uint32 questId = 0, uint32 itemId = 0, float valueFloat = 0.0f, uint32 valueInt = 0, bool failure = false, bool rare = false, bool intervention = false) const;
    void RecordPolicyReplay(WorldBotState const& state, Player* bot, Unit const* target, BotTelemetryPolicyInput const& input, char const* rawJson, char const* semanticJson);
    BotTelemetryFrame BuildTelemetryFrame(Player* bot, Unit const* target, char const* situation, char const* action, char const* rawJson, char const* semanticJson, uint32 questId = 0) const;
    uint64 MaybeCaptureTelemetryClip(Player* bot, Unit const* target, BotTelemetryPolicyInput const& input, BotTelemetryPolicyDecision const& decision, char const* rawJson, char const* semanticJson);
    void UpdateSemanticOutcomeStats(Player* bot, char const* entityType, uint32 entityKey, char const* eventType, char const* result, float reward, float powerDelta, bool failure, char const* featuresJson);
    void UpdateSemanticStatsFromEvent(Player* bot, Unit const* target, char const* eventType, char const* result, float valueFloat, uint32 valueInt, uint32 spellId, char const* semanticJson);
    uint64 BeginPendingHealCast(Player* bot, Unit* target, uint32 spellId, std::string const& candidateMaskJson = {}, std::string const& chosenActionJson = {});
    void FlushPendingHealCast(PendingHealCast const& cast, Player* bot, char const* outcome, char const* reason);
    void UpdatePendingHealCasts();
    void ClearPendingHealCasts(char const* reason);
    std::string BuildValidationRouteEvidenceJson(std::vector<ValidationRouteEvidence> const& evidence) const;
    SemanticOutcomeStats GetSemanticOutcomeStats(char const* entityType, uint32 entityKey) const;
    std::string BuildOutcomeStatsJson(SemanticOutcomeStats const& stats) const;
    std::string BuildEmbeddingFeaturesJson(Player const* bot, Unit const* target, char const* entityType, uint32 entityKey, char const* semanticFamily) const;
    std::string BuildNativeRecoveryEpisodeJson(WorldBotState const* state) const;
    std::string BuildRawJson(Player* bot, Unit const* target) const;
    std::string BuildSemanticJson(Player* bot, Unit const* target, char const* situation, BotRolePowerBreakdown const* power = nullptr, BotProgressionStage stage = BotProgressionStage::Leveling, BotProgressionActivity activity = BotProgressionActivity::ExperimentExploration) const;
    RoleSaturationState BuildRoleSaturationState(Player const* bot, Unit const* target, char const* role, float encounterDanger = 0.0f, float interruptPressure = 0.0f, bool tankBuster = false, bool adds = false, bool noValidActions = false) const;
    std::string BuildConfigJson() const;
    std::string BuildActivityCandidatesJson(std::vector<BotActivityScore> const& activityScores) const;
    void ApplyPolicyModelScores(std::vector<BotActivityScore>& activityScores, Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    PolicyModelTrace BuildPolicyModelTrace(std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, Player const* bot, uint64 clipId, uint64 replayId) const;
    float ScorePolicyModelCandidate(BotActivityScore const& score, Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    std::map<std::string, float> BuildPolicyModelFeatureMap(BotActivityScore const& score, Player const* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const;
    float PredictPolicyModelLabel(char const* label, std::map<std::string, float> const& features) const;
    static uint32 FeatureSchemaHash(std::string const& value);
    static std::string JsonEscape(std::string const& value);
    void ResetCombatLog();
    Player* FindCombatLogCohortPlayer(Unit* unit) const;
    void AddCombatLogAggregate(CombatLogPerspective perspective, Player* actor, Unit* source, Unit* target,
        uint32 spellId, uint32 effectType, uint32 amount, uint32 rawAmount, uint32 absorbedAmount, uint64 timestampMs);
    void AddCombatLogEvent(char const* kind, Player* actor, Unit* source, Unit* target, uint32 spellId,
        uint32 effectType, uint32 schoolMask, uint32 amount, uint32 rawAmount, uint32 absorbedAmount, uint64 timestampMs);

    struct CalibrationMetrics
    {
        struct EffectiveStatVector
        {
            bool Observed = false;
            uint64 ObservedAtMs = 0;
            uint32 Guid = 0;
            uint32 Entry = 0;
            float Strength = 0.0f;
            float Agility = 0.0f;
            float Stamina = 0.0f;
            float Intellect = 0.0f;
            float Spirit = 0.0f;
            float AttackPower = 0.0f;
            float RangedAttackPower = 0.0f;
            int32 SpellPower = 0;
            int32 BonusDamage = 0;
            uint32 Armor = 0;
            uint64 Health = 0;
            uint32 Mana = 0;
            uint32 HitRating = 0;
            uint32 CritRating = 0;
            uint32 HasteRating = 0;
            uint32 ExpertiseRating = 0;
            uint32 MasteryRating = 0;
            float PhysicalHitPct = 0.0f;
            float SpellHitPct = 0.0f;
            float MeleeCritPct = 0.0f;
            float RangedCritPct = 0.0f;
            float SpellCritPct = 0.0f;
            float MasteryPoints = 0.0f;
            float MeleeSpeedMultiplier = 1.0f;
            float RangedSpeedMultiplier = 1.0f;
            float SpellSpeedMultiplier = 1.0f;
        };

        struct InitialPowerObservation
        {
            uint8 PowerType = 0;
            uint32 ExpectedNativeValue = 0;
            uint32 ExpectedDisplayValue = 0;
            uint32 ObservedNativeValue = 0;
            uint32 ObservedDisplayValue = 0;
            uint32 ObservedMaximumNativeValue = 0;
            bool ExpectedMaximum = false;
            bool MatchesContract = false;
            uint32 UnitGuid = 0;
            std::string UnitKind;
            std::string PowerName;
        };

        struct TargetHealthPhaseObservation
        {
            uint32 SampleCount = 0;
            uint64 FirstObservedElapsedMs = 0;
            uint64 LastObservedElapsedMs = 0;
            uint64 MinimumObservedHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumObservedHealth = 0;
            uint64 MinimumObservedMaxHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumObservedMaxHealth = 0;
            uint32 DamageEventSampleCount = 0;
            uint64 FirstDamageEventElapsedMs = 0;
            uint64 LastDamageEventElapsedMs = 0;
            uint64 MinimumPreDamageHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumPreDamageHealth = 0;
            uint64 MinimumProjectedPostDamageHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumProjectedPostDamageHealth = 0;
            uint64 MinimumDamageEventMaxHealth = std::numeric_limits<uint64>::max();
            uint64 MaximumDamageEventMaxHealth = 0;
            uint32 MaximumDamageEvent = 0;
        };

        struct DecisionTimelineEntry
        {
            uint64 ElapsedMs = 0;
            uint32 SpellId = 0;
            std::string Result;
            uint64 Health = 0;
            uint64 MaxHealth = 0;
            uint32 Mana = 0;
            uint32 MaxMana = 0;
            uint32 CurrentGenericSpellId = 0;
            uint32 CurrentChanneledSpellId = 0;
            uint64 PetHealth = 0;
            uint64 PetMaxHealth = 0;
            uint32 PetVictimGuid = 0;
            uint32 PetCurrentGenericSpellId = 0;
            uint32 PetCurrentChanneledSpellId = 0;
            uint32 PetCurrentAutorepeatSpellId = 0;
            uint8 PetCommandState = 0;
            bool PetAlive = false;
            bool PetAttacking = false;
            bool PetCommandAttack = false;
            float TargetDistance = 0.0f;
            bool Alive = false;
        };

        struct OffTargetDamageEvent
        {
            struct PeriodicHealthAuraCandidate
            {
                uint32 SpellId = 0;
                uint32 HolderGuid = 0;
                uint32 CasterGuid = 0;
                uint8 EffectIndex = 0;
                uint16 AuraType = 0;
            };

            uint64 ElapsedMs = 0;
            uint32 AttackerGuid = 0;
            uint32 VictimGuid = 0;
            uint32 VictimEntry = 0;
            uint32 SpellId = 0;
            uint32 CurrentGenericSpellId = 0;
            uint32 CurrentChanneledSpellId = 0;
            uint32 Damage = 0;
            uint8 VictimTypeId = 0;
            bool VictimIsOwner = false;
            std::vector<PeriodicHealthAuraCandidate> PeriodicHealthAuraCandidates;
        };

        uint64 WindowStartedMs = 0;
        uint64 WindowEndedMs = 0;
        uint64 Damage = 0;
        uint64 PetDamage = 0;
        uint64 PrimaryTargetDamage = 0;
        uint64 OffTargetDamage = 0;
        uint64 AttemptedHealing = 0;
        uint64 EffectiveHealing = 0;
        uint64 AbsorbedHealing = 0;
        uint32 Attempts = 0;
        uint32 Successes = 0;
        uint32 TickCount = 0;
        uint32 RequiredPetReadyTicks = 0;
        uint32 PetSetupObservationSampleCount = 0;
        uint32 PetSetupReadySampleCount = 0;
        uint64 FirstPetSetupObservedAtMs = 0;
        uint64 LastPetSetupObservedAtMs = 0;
        uint64 MaximumPetSetupObservationGapMs = 0;
        uint32 FirstPetSetupObservedGuid = 0;
        uint32 LastPetSetupObservedGuid = 0;
        uint32 PetSetupGuidMismatchSampleCount = 0;
        uint32 PetSetupIdentityMismatchSampleCount = 0;
        uint32 ActiveTicks = 0;
        uint32 MovementRangeLossTicks = 0;
        uint32 ResourceCappedTicks = 0;
        uint32 ResourceStarvedTicks = 0;
        uint32 IllegalActionCount = 0;
        uint32 ShadowOrbPowerActiveTicks = 0;
        uint32 ShadowOrbActiveTicks = 0;
        uint32 EmpoweredShadowActiveTicks = 0;
        uint8 MaximumShadowOrbStacks = 0;
        uint32 AfflictionModifierObservationTicks = 0;
        uint32 AfflictionShadowMasteryActiveTicks = 0;
        uint32 AfflictionPotentAfflictionsActiveTicks = 0;
        uint32 AfflictionHauntDebuffActiveTicks = 0;
        uint32 AfflictionShadowEmbraceActiveTicks = 0;
        uint8 AfflictionMaximumShadowEmbraceStacks = 0;
        uint32 AfflictionHauntAffectsCorruptionTicks = 0;
        uint32 AfflictionShadowEmbraceAffectsCorruptionTicks = 0;
        int32 AfflictionMaximumHauntDamageModifierPct = 0;
        int32 AfflictionMaximumShadowEmbraceDamageModifierPct = 0;
        uint32 AfflictionMinimumCorruptionTakenMultiplierPpm = 0;
        uint32 AfflictionMaximumCorruptionTakenMultiplierPpm = 0;
        uint32 StanceFormActiveTicks = 0;
        uint32 MitigationCoveredTicks = 0;
        uint32 ThreatSampleCount = 0;
        uint32 AllHostilesRetainedSamples = 0;
        uint32 SnapThreatChecks = 0;
        uint32 SnapThreatSuccesses = 0;
        uint32 AddThreatChecks = 0;
        uint32 AddThreatSuccesses = 0;
        uint32 ThreatAuraActiveTicks = 0;
        uint32 HealerExposureTicks = 0;
        uint32 InterruptChecks = 0;
        uint32 InterruptSuccesses = 0;
        uint32 DefensiveActionCount = 0;
        uint32 ScheduledDamageEvents = 0;
        uint32 DeliveredDamageEvents = 0;
        uint32 DispelAttempts = 0;
        uint32 DispelSuccesses = 0;
        uint32 CooldownAttempts = 0;
        uint32 CooldownSuccesses = 0;
        uint32 HealSelectionAttempts = 0;
        uint32 HealSelectionSuccesses = 0;
        uint32 DemandTicks = 0;
        uint32 IdleUnderDemandTicks = 0;
        uint32 TargetCount = 0;
        uint32 DeathCount = 0;
        uint64 ControlledDamage = 0;
        uint64 MaximumControlledDamage = 0;
        float MaximumControlledDamageRatio = 0.0f;
        float ThreatBaseline = -1.0f;
        float ThreatCurrent = 0.0f;
        float MinimumHealthRatio = 1.0f;
        bool ReferenceBuffsReady = false;
        bool ReferenceReplenishmentObserved = false;
        bool ReferenceTargetDebuffsReady = false;
        bool ReferenceHeroismWindowObserved = false;
        bool BalanceMushroomsPreplanted = false;
        uint8 BalanceMushroomPreplantCount = 0;
        bool DeathRecorded = false;
        bool InitialResourcesApplied = false;
        bool InitialResourcesMatchContract = false;
        uint64 InitialResourcesObservedAtMs = 0;
        std::string InitialResourceSourceContract;
        std::vector<InitialPowerObservation> InitialPowerObservations;
        bool InitialRunesRequired = false;
        uint8 InitialExpectedRuneReadyMask = 0;
        uint8 InitialObservedRuneReadyMask = 0;
        bool InitialComboPointsRequired = false;
        uint8 InitialExpectedComboPoints = 0;
        uint8 InitialObservedComboPoints = 0;
        bool InitialNeutralEclipseRequired = false;
        bool InitialNeutralEclipseObserved = false;
        bool InitialPetResourceRequired = false;
        bool InitialPetResourceObserved = false;
        EffectiveStatVector ScoringStartPlayerStats;
        EffectiveStatVector ScoringStartPetStats;
        bool PreScorePersistentSetupReady = false;
        bool PreScoreReferenceBuffsReady = false;
        bool PreScoreReferenceTargetDebuffsReady = false;
        bool PreScoreHeroismReady = false;
        bool PreScoreNoActiveCast = false;
        bool PreScoreNoCombat = false;
        bool PreScoreGlobalCooldownClear = false;
        bool PreScoreCooldownResetApplied = false;
        bool WarmupProfileActionsSuppressed = false;
        bool PreScoreTemporalExternalsAbsent = false;
        bool PreScoreExternalBleedAbsent = false;
        uint64 PreScoreStateObservedAtMs = 0;
        uint32 ExternalWindowSampleCount = 0;
        uint64 FirstExternalWindowObservedAtMs = 0;
        uint64 LastExternalWindowObservedAtMs = 0;
        uint64 MaximumExternalWindowObservationGapMs = 0;
        uint32 HeroismExpectedActiveSamples = 0;
        uint32 HeroismObservedActiveSamples = 0;
        uint32 HeroismMismatchSamples = 0;
        uint32 PowerInfusionExpectedActiveSamples = 0;
        uint32 PowerInfusionObservedActiveSamples = 0;
        uint32 PowerInfusionMismatchSamples = 0;
        uint32 UnexpectedDarkIntentBaseSamples = 0;
        uint32 UnexpectedDarkIntentProcSamples = 0;
        uint32 UnexpectedSynapseSpringsSamples = 0;
        uint32 ReferenceConditionSampleCount = 0;
        uint64 FirstReferenceConditionObservedAtMs = 0;
        uint64 LastReferenceConditionObservedAtMs = 0;
        uint64 MaximumReferenceConditionObservationGapMs = 0;
        uint32 PreScoreLastPotionItemId = 0;
        uint32 LastPotionIdNonzeroSampleCount = 0;
        uint32 ScoredPotionUseCount = 0;
        uint32 ScoredTinkerOrOtherItemUseCount = 0;
        uint32 ScoredRacialUseCount = 0;
        uint32 ScoredTinkerSpellUseCount = 0;
        uint32 UnexpectedDynamicAuraActiveSamples = 0;
        uint32 UnexpectedExternalBleedActiveSamples = 0;
        std::map<uint32, uint32> ReferencePlayerAuraActiveSamples;
        std::map<uint32, uint32> ReferencePlayerAuraInactiveSamples;
        std::map<uint32, uint32> ReferenceTargetAuraActiveSamples;
        std::map<uint32, uint32> ReferenceTargetAuraInactiveSamples;
        std::map<uint32, uint32> ReferenceTargetAuraOwnerMatchSamples;
        std::map<uint32, uint32> ReferenceTargetAuraOwnerMismatchSamples;
        uint32 ReferenceSunderMatchingStackSamples = 0;
        uint32 ReferenceSunderMismatchStackSamples = 0;
        uint8 ReferenceSunderMinimumObservedStacks =
            std::numeric_limits<uint8>::max();
        uint8 ReferenceSunderMaximumObservedStacks = 0;
        std::string InitialGearManifestSha256;
        std::string LastObservedGearManifestSha256;
        uint32 GearIdentitySampleCount = 0;
        uint32 GearIdentityMismatchSampleCount = 0;
        uint64 FirstGearIdentityObservedAtMs = 0;
        uint64 LastGearIdentityObservedAtMs = 0;
        uint64 MaximumGearIdentityObservationGapMs = 0;
        std::map<uint32, uint64> SpellDamage;
        std::map<uint32, uint32> SpellDamageEvents;
        // The owner's primary pet damage is kept separate from the owner's
        // spell totals. This intentionally excludes other controlled units
        // such as guardians, which remain in the aggregate PetDamage value.
        std::map<uint32, uint64> PrimaryPetSpellDamage;
        std::map<uint32, uint32> PrimaryPetSpellDamageEvents;
        std::map<uint32, uint32> ActionAttempts;
        std::map<uint32, uint32> HealTargetCounts;
        std::map<uint32, uint64> LastDamageMsByTarget;
        std::map<uint32, uint64> LastControlledDamageMsByTarget;
        std::vector<uint32> HealResponseLatenciesMs;
        std::set<std::string> ActionGroups;
        std::set<std::string> ExpectedActionGroups;
        std::set<std::string> ScheduledDamagePhases;
        std::set<std::string> DeliveredDamagePhases;
        std::map<std::string, uint32> ResultCounts;
        // Bounded, observation-only timeline used by the rotation review tool
        // to distinguish selection, movement, native submission, resource
        // state, and death. It never participates in arbitration or scoring.
        std::vector<DecisionTimelineEntry> DecisionTimeline;
        // Attribute every non-primary damage event instead of exposing only an
        // unauditable aggregate collateral counter.
        std::vector<OffTargetDamageEvent> OffTargetDamageEvents;
        // Raw server observations for the isolated single-target fixture's
        // five WoWSims execute-threshold bands. Evidence reconstructs the
        // schedule from these integers; it does not trust an aggregate flag.
        std::array<TargetHealthPhaseObservation, 5> TargetHealthPhaseObservations;
    };

    void AppendCombatCalibrationSummaryJson(std::ostringstream& json,
        uint64 nowMs,
        std::function<void(std::map<uint32, CalibrationMetrics> const&, bool)> const& writeBots) const;

    struct PartyRuntime
    {
        std::vector<WorldBotState> Bots;
        std::vector<WorldBotState> CalibrationBots;
        ObjectGuid GroupGuid;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        std::map<uint32, std::string> RoleByGuid;
        // Per-bot cursor for the bounded diagnostic trace export.  This keeps
        // repeated botauto_trace polls incremental without changing the
        // authoritative in-memory trace or dropping current decisions.
        mutable std::map<uint32, uint64> TraceExportCursorByGuid;

        ObjectGuid ValidationRouteFocusGuid;
        uint32 ValidationRouteFocusEntry = 0;
        uint32 ValidationRouteFocusMapId = 0;
        float ValidationRouteFocusX = 0.0f;
        float ValidationRouteFocusY = 0.0f;
        float ValidationRouteFocusZ = 0.0f;
        uint64 ValidationRouteFocusSeenMs = 0;
        ObjectGuid ValidationRouteAddFocusGuid;
        uint64 ValidationRouteAddFocusGeneration = 0;
        GuidSet ValidationRouteRecordedKillGuids;
        GuidSet ValidationRoutePackMemberGuids;
        GuidSet ValidationRoutePackEngagedGuids;
        GuidSet ValidationRoutePackDeathGuids;
        GuidSet ValidationRoutePackTransitionGuids;
        GuidSet ValidationRoutePendingFinalTransitionGuids;
        GuidSet ValidationRouteFinalTransitionGuids;
        uint64 ValidationRoutePackGeneration = 0;
        uint64 ValidationRoutePackSequence = 1;
        uint32 ValidationRouteCompletedPackCount = 0;
        bool ValidationRoutePackObservedEngagement = false;
        bool ValidationRouteDrudgePrepullStaged = false;
        uint64 ValidationRouteDrudgePrepullAttemptId = 0;
        uint32 ValidationRouteDrudgePrepullWipeGeneration = 0;
        uint64 ValidationRouteDrudgePrepullRouteGeneration = 0;
        uint64 ValidationRouteDrudgeChargeGeneration = 0;
        uint64 ValidationRouteDrudgeChargeLandedGeneration = 0;
        uint64 ValidationRouteDrudgeChargeObservedAtMs = 0;
        ObjectGuid ValidationRouteDrudgeChargeSourceGuid;
        ObjectGuid ValidationRouteDrudgeChargeTargetGuid;
        uint32 ValidationRouteDrudgeChargeSourceSpawnId = 0;
        float ValidationRouteDrudgeChargeObservedDistance = 0.0f;
        bool ValidationRouteDrudgeChargeRangeValid = false;
        bool ValidationRouteDrudgeChargeIntervalValid = false;
        std::map<uint32, uint64> ValidationRouteDrudgeLastChargeMsBySpawn;
        std::deque<ValidationRouteDrudgeChargeObservation> ValidationRouteDrudgeChargeObservations;
        uint64 ValidationRouteDrudgeEvidenceAttemptId = 0;
        uint32 ValidationRouteDrudgeEvidenceWipeGeneration = 0;
        uint64 ValidationRouteDrudgeEvidenceRouteGeneration = 0;
        std::vector<uint32> ValidationRouteDrudgeEvidenceSourceSpawnIds;
        uint32 ValidationRouteDrudgeChargePreparedCount = 0;
        uint32 ValidationRouteDrudgeChargeDeliveredCount = 0;
        bool ValidationRouteDrudgeChargeQueueOverflow = false;
        std::map<uint32, uint32> ValidationRouteDrudgeDeliveredBySpawn;
        std::map<uint32, uint32> ValidationRouteDrudgeValidIntervalsBySpawn;
        std::set<uint32> ValidationRouteDrudgeReseparatedRosterGuids;
        std::set<uint32> ValidationRouteDrudgeOwnershipRosterGuids;
        std::set<uint32> ValidationRouteDrudgeTauntRosterGuids;
        std::set<uint32> ValidationRouteDrudgeHealthSyncRosterGuids;
        std::set<uint32> ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids;
        uint32 ValidationRouteDrudgeHealthSyncHoldSourceSpawnId = 0;
        uint32 ValidationRouteDrudgeHealthSyncHoldTankGuid = 0;
        float ValidationRouteDrudgeHealthSyncHoldLowerPct = 0.0f;
        float ValidationRouteDrudgeHealthSyncHoldPeerPct = 0.0f;
        bool ValidationRouteDrudgeHealthSyncHoldLowerAlive = false;
        bool ValidationRouteDrudgeHealthSyncHoldPeerAlive = false;
        uint64 ValidationRouteDrudgeDeathAttemptId = 0;
        uint32 ValidationRouteDrudgeDeathWipeGeneration = 0;
        uint64 ValidationRouteDrudgeDeathRouteGeneration = 0;
        uint32 ValidationRouteDrudgeDeathSourceSpawnId = 0;
        uint32 ValidationRouteDrudgeDeathSourceGuid = 0;
        uint32 ValidationRouteDrudgeSurvivorSourceSpawnId = 0;
        uint32 ValidationRouteDrudgeSurvivorSourceGuid = 0;
        uint64 ValidationRouteDrudgeDeathEvidenceSequence = 0;
        uint64 ValidationRouteDrudgeRageWaitEvidenceSequence = 0;
        uint64 ValidationRouteDrudgeRageAuraEvidenceSequence = 0;
        uint64 ValidationRouteDrudgeHealthSyncEvidenceAttemptId = 0;
        uint32 ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration = 0;
        uint64 ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration = 0;
        std::set<uint32> ValidationRouteDrudgeProfileActionRosterGuids;
        uint64 ValidationRouteDrudgeThreatSeedAttemptId = 0;
        uint64 ValidationRouteDrudgeThreatSeedWipeGeneration = 0;
        uint64 ValidationRouteDrudgeThreatSeedRouteGeneration = 0;
        bool ValidationRouteDrudgeThreatSeedClosed = false;
        bool ValidationRouteDrudgeThreatSeedComplete = false;
        bool ValidationRouteDrudgeThreatSeedFailure = false;
        std::set<uint32> ValidationRouteDrudgeThreatSeedRosterGuids;
        std::vector<ValidationRouteDrudgeThreatSeedEvidence> ValidationRouteDrudgeThreatSeedEvidenceRows;
        uint64 ValidationRoutePackClearCandidateSinceMs = 0;
        uint64 ValidationRouteNodeClearCandidateSinceMs = 0;
        ObjectGuid ValidationRouteBossProgressTargetGuid;
        uint32 ValidationRouteBossSlowProgressCount = 0;
        bool ValidationRouteBossAddDensityPhase = false;
        uint64 ValidationRouteBossAddDensityGeneration = 0;
        bool ValidationRouteLargePassiveSwarmStaging = false;
        uint64 ValidationRouteLargePassiveSwarmStagingGeneration = 0;
        bool ValidationRouteBossAddEscapeActive = false;
        uint64 ValidationRouteBossAddEscapeGeneration = 0;
        float ValidationRouteBossAddEscapeX = 0.0f;
        float ValidationRouteBossAddEscapeY = 0.0f;
        float ValidationRouteBossAddEscapeZ = 0.0f;
        float ValidationRouteBossAddEscapeAnchorX = 0.0f;
        float ValidationRouteBossAddEscapeAnchorY = 0.0f;
        float ValidationRouteBossAddEscapeAnchorZ = 0.0f;
        float ValidationRouteBossAddCentroidX = 0.0f;
        float ValidationRouteBossAddCentroidY = 0.0f;
        GuidSet ValidationRouteBossAddEscapeIssuedGuids;
        bool ValidationRouteActivationApplied = false;
        uint32 ValidationRouteActivationAttempts = 0;
        uint32 ValidationRouteCanonicalBossRecoveryAttempts = 0;
        uint64 ValidationRouteCanonicalBossRecoveryLastMs = 0;
        std::vector<ValidationRouteManifestNode> ValidationRouteManifest;
        std::string ValidationRouteManifestSha256;
        std::vector<ValidationRouteEvidence> ValidationRouteTerminalEvidence;
        std::vector<ValidationRouteEvidence> ValidationRouteBossDeathEvidence;
        size_t ValidationRouteManifestIndex = 0;
        uint64 ValidationRouteGeneration = 0;
        ObjectGuid ValidationRouteEngagedBossGuid;
        uint64 ValidationRouteEngagedBossGeneration = 0;
        uint32 ValidationRouteEngagedBossMapId = 0;
        uint32 ValidationRouteEngagedBossInstanceId = 0;
        ObjectGuid ValidationRouteConfirmedBossDeathGuid;
        uint64 ValidationRouteConfirmedBossDeathGeneration = 0;
        uint32 ValidationRouteConfirmedBossDeathMapId = 0;
        uint32 ValidationRouteConfirmedBossDeathInstanceId = 0;
        uint32 ValidationRouteProgressBaselineKills = 0;
        bool ValidationRouteObservedEngagement = false;
        bool ValidationRouteObservedDeadScriptTarget = false;
        bool ValidationRouteManifestAdvancePending = false;
        uint64 ValidationRouteManifestAdvanceGeneration = 0;
        bool ValidationRouteManifestComplete = false;
        std::string ValidationRouteManifestAdvanceReason;
        std::string ValidationRouteManifestLoadError;

        mutable std::map<uint32, std::string> LastCombatMaskByBot;
        mutable std::map<uint32, std::string> LastCombatRejectsByBot;
        mutable std::map<uint32, std::string> LastChosenCombatByBot;
        mutable std::map<uint32, std::string> LastActionCategoryByBot;
        mutable std::map<uint32, RoleSaturationState> LastSaturationByBot;
        uint64 NextHealCastId = 1;
        std::map<uint64, PendingHealCast> PendingHealCasts;
        std::map<CombatLogAbilityKey, CombatLogAbilityAggregate> CombatLogAbilities;
        std::map<std::tuple<uint64, CombatLogPerspective, uint32, bool, uint64>, uint64> CombatLogSecondBuckets;
        std::deque<CombatLogEvent> CombatLogRecentEvents;
        uint64 CombatLogEventCount = 0;
        uint64 CombatLogRecentEventsDropped = 0;
    };

    struct RaidRosterItemIdentity
    {
        uint8 Slot = 0;
        uint32 Guid = 0;
        uint32 Entry = 0;
        uint32 EnchantId = 0;
        std::vector<uint32> GemItemIds;
        uint32 ReforgeId = 0;
    };

    struct RaidRosterSlot
    {
        std::string RosterSlotId;
        std::string LeaseRoleSlot;
        uint32 SlotIndex = 0;
        ObjectGuid Guid;
        uint32 AccountId = 0;
        std::string AccountName;
        std::string CharacterName;
        uint8 SubGroup = 0;
        std::string Role;
        uint8 ClassId = 0;
        std::string ClassSpec;
        float AverageItemLevel = 0.0f;
        std::string GearIdentity;
        std::string TalentIdentity;
        std::string GlyphIdentity;
        std::vector<uint32> Talents;
        std::vector<uint32> Glyphs;
        std::vector<RaidRosterItemIdentity> GearManifest;
        bool Active = false;
        bool LeaseOwned = false;
    };

    struct RaidNativeSignalState
    {
        bool Initialized = false;
        bool Alive = false;
        bool HasCorpse = false;
        bool Released = false;
        bool OutsideOriginalInstance = false;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        float X = 0.0f;
        float Y = 0.0f;
        float Z = 0.0f;
        uint64 WipeGeneration = 0;
        uint64 DeathSequence = 0;
        uint64 CorpseSequence = 0;
        uint64 ReleaseSequence = 0;
        uint64 RunbackSequence = 0;
        uint64 ReentrySequence = 0;
        uint64 ResurrectionSequence = 0;
    };

    struct CohortAdmissionMemberReceipt
    {
        ObjectGuid Guid;
        ObjectGuid GroupGuid;
        ObjectGuid LeaderGuid;
        std::string RosterSlotId;
        std::string Role;
        std::string ClassSpec;
        uint8 ClassId = 0;
        uint8 ActiveSpecIndex = 0;
        uint32 PrimaryTalentTreeId = 0;
        uint32 ActiveTalentCount = 0;
        std::vector<uint32> ActiveTalentSpellIds;
        bool PetIdentityPresent = false;
        uint32 PetId = 0;
        uint32 PetEntry = 0;
        uint32 PetSpellCount = 0;
        std::vector<std::pair<uint32, uint8>> PetSpellbook;
        std::string PetSpellbookSha256;
        std::string GearProfileId;
        uint32 GearItemCount = 0;
        std::vector<RaidRosterItemIdentity> GearManifest;
        std::string GearManifestSha256;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        uint8 ExpectedDifficulty = 0;
        uint8 PlayerDifficulty = 0;
        int16 MapDifficulty = -1;
        float SpawnX = 0.0f;
        float SpawnY = 0.0f;
        float SpawnZ = 0.0f;
        float SpawnO = 0.0f;
        bool ServerProvisioned = false;
        bool InitialBaselineNormalized = false;
        bool InitialAliveStateVerified = false;
    };

    struct RaidRuntime
    {
        bool Active = false;
        bool RaidInstance = false;
        bool ServerProvisioningComplete = false;
        bool BotActionsEnabled = false;
        bool RosterComplete = false;
        bool DifficultyMatches = false;
        bool DifficultyReadbackComplete = false;
        bool UniqueLeases = false;
        ObjectGuid GroupGuid;
        ObjectGuid LeaderGuid;
        uint32 ExpectedSize = 0;
        uint32 ActiveSize = 0;
        uint32 AliveSize = 0;
        uint8 ExpectedDifficulty = 0;
        uint8 GroupDifficulty = 0;
        int16 MapDifficulty = -1;
        uint32 DifficultyMemberCount = 0;
        uint32 DifficultyMatchingMemberCount = 0;
        uint32 ProvisionedMemberCount = 0;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        uint32 LockoutSaveId = 0;
        uint64 ServerEpoch = 0;
        uint64 AttemptId = 0;
        uint64 ProfileGeneration = 0;
        std::string ProfileContentHash;
        uint64 AdmissionCommittedAtMs = 0;
        uint64 AdmissionAttemptId = 0;
        bool AdmissionActionGateEnabled = false;
        std::string AdmissionScenarioId;
        std::string AdmissionRuntimeProfile;
        std::string AdmissionRouteManifestSha256;
        uint32 AdmissionRecoveryEntranceAreaTriggerId = 0;
        uint32 AdmissionRecoveryEntranceSourceMapId = 0;
        uint32 AdmissionRecoveryEntranceTargetMapId = 0;
        uint32 AdmissionEntranceMapId = 0;
        float AdmissionEntranceX = 0.0f;
        float AdmissionEntranceY = 0.0f;
        float AdmissionEntranceZ = 0.0f;
        float AdmissionEntranceO = 0.0f;
        std::map<uint32, CohortAdmissionMemberReceipt> AdmissionReceiptByGuid;
        uint64 AssignmentGeneration = 0;
        uint64 EvidenceSequence = 0;
        uint64 WipeGeneration = 0;
        uint64 BossResetGeneration = 0;
        uint64 BossResetGenerationAtWipe = 0;
        uint64 RecoveryGeneration = 0;
        bool EncounterInProgress = false;
        bool ReadyCheckSatisfied = false;
        bool RosterCompositionValid = false;
        bool NativeDeathObserved = false;
        bool NativeCorpseObserved = false;
        bool NativeReleaseObserved = false;
        bool NativeResurrectionObserved = false;
        bool NativeRunbackObserved = false;
        bool NativeReadyCheckActionObserved = false;
        bool NativeReadyCheckPending = false;
        uint32 NativeReadyCheckResponseCount = 0;
        uint64 NativeReadyCheckActionGeneration = 0;
        uint64 NativeReadyCheckActionAttemptId = 0;
        uint64 NativeReadyCheckActionWipeGeneration = 0;
        uint64 NativeReadyCheckAssignmentGeneration = 0;
        uint64 NativeReadyCheckActionEvidenceSequence = 0;
        std::set<uint32> NativeReadyCheckResponders;
        bool NativeRecoveryEvidenceComplete = false;
        // Once an exact native all-dead transition is observed, keep the
        // entire cohort in recovery authority until the current wipe's native
        // ready-check-backed evidence is complete.  This is deliberately a
        // raid-scoped latch rather than a transient WipeState predicate: the
        // latter can briefly look route-ready on the first all-alive sample
        // after resurrection, before the next runtime refresh records the
        // ready-check/evidence edge.
        bool NativeRecoveryHoldActive = false;
        // Bind the hold to the exact route node that observed the native
        // all-dead edge. Wipe/runtime fields are monotonic across nodes and
        // therefore cannot authorize recovery on their own.
        uint64 NativeRecoveryRouteGeneration = 0;
        std::string NativeRecoveryNodeId;
        // A raid instance can contain an active trash pack without an
        // IN_PROGRESS boss state. Native recovery must observe the pack
        // itself evading/resetting before released ghosts may re-enter.
        bool NativeHostileActivityActive = false;
        bool NativeHostileActivitySeen = false;
        bool NativeHostileActivitySeenAtWipe = false;
        bool NativeHostileInactivityObserved = false;
        uint64 NativeHostileInactiveSinceMs = 0;
        uint64 NativeHostileResetGeneration = 0;
        uint64 NativeHostileResetGenerationAtWipe = 0;
        uint64 NativeHostileObservationAttemptId = 0;
        uint64 NativeHostileObservationRouteGeneration = 0;
        std::string NativeHostileObservationNodeId;
        uint32 NativeHostileActivityEntry = 0;
        ObjectGuid NativeHostileActivityGuid;
        std::string NativeHostileActivityReason;
        std::string StrategyId;
        std::string PreviousStrategyId;
        uint64 StrategyTransitionRouteGeneration = 0;
        std::string EncounterPhase = "formation";
        std::string WipeState = "ready";
        std::string RecoveryState = "none";
        std::vector<uint8> BossStates;
        std::map<uint32, RaidRosterSlot> RosterByGuid;
        std::map<uint32, RaidNativeSignalState> NativeSignalsByGuid;
        std::map<uint32, std::string> AccountNameById;
        std::set<uint32> AccountNameLookupAttempted;
    };

    struct CohortRuntime
    {
        std::string Id;
        uint64 AttemptId = 0;
        uint64 PinnedProfileGeneration = 0;
        std::string PinnedProfileContentHash;
        std::set<uint32> RosterLeases;
        bool Active = false;
        BotWorldRuntimeMode RuntimeMode = BotWorldRuntimeMode::ManualExperiment;
        // Synthetic setup is permitted only inside an isolated fixture mode.
        // It is always non-certifying and may never coexist with live Party().Bots.
        bool NonCertifyingAssistance = false;
        uint64 ExperimentId = 0;
        uint64 RunId = 0;
        uint32 ElapsedMs = 0;
        uint32 RecordingWindowElapsedMs = 0;
        uint32 RecordingWindowIndex = 0;
        uint64 EncounterSnapshotRevision = 0;
        uint64 EncounterSnapshotNextRefreshMs = 0;
        std::shared_ptr<BotEncounter::Blackboard const> EncounterSnapshot;
        BotWorldExperimentConfig Config;
        std::string ProfileManifestPath;
        std::map<std::string, BotWorldExperimentProfile> RuntimeProfiles;
        std::vector<std::string> RuntimeProfileOrder;
        std::string SelectedProfileName;
        std::string PreparedPoolTagFilter;
        std::vector<std::string> PreparedClassSpecs;
        std::string ProfileManifestLoadError;
        bool RuntimeProfilesLoaded = false;
        bool RuntimeProfileDirty = false;
        bool RuntimeProfileSelectionPending = false;
        BotExperienceLearningConfig LearningConfig;
        BotPolicyModelConfig PolicyModelConfig;
        bool CalibrationActive = false;
        bool CalibrationStopping = false;
        bool CalibrationAoePhase = false;
        bool CalibrationWindowComplete = false;
        std::string CalibrationFailureReason;
        std::string CalibrationMode = "single_target_300";
        std::string CalibrationTargetSpec;
        uint32 CalibrationSeed = 1;
        ObjectGuid CalibrationTargetGuid;
        ObjectGuid CalibrationFixtureTargetGuid;
        uint32 CalibrationFixtureTargetEntry = 0;
        uint32 CalibrationFixtureExpectedTargetLevel = 0;
        uint32 CalibrationFixtureExpectedTargetArmor = 0;
        uint32 CalibrationFixtureExpectedTargetCreatureType = 0;
        uint32 CalibrationFixtureExpectedTargetMaxHealth = 0;
        uint32 CalibrationFixtureObservedTargetLevel = 0;
        uint32 CalibrationFixtureObservedTargetArmor = 0;
        uint32 CalibrationFixtureObservedTargetCreatureType = 0;
        uint32 CalibrationFixtureObservedTargetCreatureTypeMask = 0;
        uint32 CalibrationFixtureObservedTargetMaxHealth = 0;
        uint32 CalibrationFixtureTargetMapId = 0;
        float CalibrationFixtureTargetX = 0.0f;
        float CalibrationFixtureTargetY = 0.0f;
        float CalibrationFixtureTargetZ = 0.0f;
        float CalibrationFixtureTargetNearestHostileClearance = 0.0f;
        uint64 CalibrationFixtureTargetProvisionedAtMs = 0;
        uint64 CalibrationFixtureTargetObservedBeforeScoringAtMs = 0;
        uint32 CalibrationFixtureBeforeScoringTargetLevel = 0;
        uint32 CalibrationFixtureBeforeScoringTargetArmor = 0;
        uint32 CalibrationFixtureBeforeScoringTargetCreatureType = 0;
        uint32 CalibrationFixtureBeforeScoringTargetCreatureTypeMask = 0;
        uint32 CalibrationFixtureBeforeScoringTargetMaxHealth = 0;
        uint32 CalibrationFixtureBeforeScoringTargetMapId = 0;
        ObjectGuid CalibrationFixtureBeforeScoringTargetGuid;
        float CalibrationFixtureBeforeScoringTargetX = 0.0f;
        float CalibrationFixtureBeforeScoringTargetY = 0.0f;
        float CalibrationFixtureBeforeScoringTargetZ = 0.0f;
        float CalibrationFixtureBeforeScoringBotTargetDistance = 0.0f;
        bool CalibrationFixtureBeforeScoringTargetInCombat = false;
        bool CalibrationFixtureBeforeScoringTargetHasVictim = false;
        uint32 CalibrationFixtureTargetPassiveObservationSampleCount = 0;
        uint32 CalibrationFixtureTargetVictimObservationSampleCount = 0;
        uint32 CalibrationFixtureTargetAttackEventCount = 0;
        uint32 CalibrationFixtureTargetOriginatedDamageEventCount = 0;
        uint64 CalibrationFixtureTargetFirstPassiveObservedAtMs = 0;
        uint64 CalibrationFixtureTargetLastPassiveObservedAtMs = 0;
        uint64 CalibrationFixtureTargetMaximumPassiveObservationGapMs = 0;
        float CalibrationFixtureBotSpawnX = 0.0f;
        float CalibrationFixtureBotSpawnY = 0.0f;
        float CalibrationFixtureBotSpawnZ = 0.0f;
        float CalibrationFixtureBotTargetDistance = 0.0f;
        bool CalibrationFixtureNativeLineOfSight = false;
        bool CalibrationFixtureNativePathReachable = false;
        bool CalibrationFixtureNativeMeleeReachable = false;
        bool CalibrationFixtureNativeDryLand = false;
        bool CalibrationFixtureGeometryValidated = false;
        std::string CalibrationFixtureProfileLane;
        ObjectGuid CalibrationInterruptTargetGuid;
        uint64 CalibrationStartedMs = 0;
        uint64 CalibrationScoredStartedMs = 0;
        uint64 CalibrationScoredEndedMs = 0;
        uint64 CalibrationLastPostWindowDrainMs = 0;
        uint64 CalibrationLastControlledEventSecond = std::numeric_limits<uint64>::max();
        uint32 CalibrationCrossWindowEventCount = 0;
        uint32 CalibrationExcludedBoundaryDamageEventCount = 0;
        std::string CalibrationResetId;
        std::string CalibrationCurrentDamagePhase;
        std::map<uint32, CalibrationMetrics> CalibrationMetricsByGuid;
        bool CalibrationPreviousWindowValid = false;
        bool CalibrationPreviousAoePhase = false;
        std::map<uint32, CalibrationMetrics> CalibrationPreviousMetrics;
        std::map<uint32, CalibrationMetrics> CalibrationBestSingleMetrics;
        std::map<uint32, CalibrationMetrics> CalibrationBestAoeMetrics;
        uint32 CalibrationCompletedSingleWindows = 0;
        uint32 CalibrationCompletedAoeWindows = 0;
        std::set<uint32> FailedSpawnGuids;
        std::string LastPopulationFailureReason;
        // A runtime/encounter terminal is different from a transient
        // population failure.  Keep it for the entire native attempt so
        // status/capture can stop promptly and every living/dead member holds
        // the same fail-closed state until the coordinator starts a new run.
        std::string ValidationAttemptFailureReason;
        uint64 ValidationAttemptFailureAttemptId = 0;
        uint64 ValidationAttemptFailureRouteGeneration = 0;
        ValidationAdmissionPhase ValidationAdmission = ValidationAdmissionPhase::Provisioning;
        bool ValidationAdmissionStarted = false;
        bool ValidationAdmissionBatchSealed = false;
        bool ValidationRaidAdmissionComplete = false;
        bool ValidationRaidAdmissionFailed = false;
        uint64 LastNativeWorldportDeferredLogMs = 0;
        uint32 SuppressedNativeWorldportDeferredLogs = 0;
        BotWorldStatus Metrics;
        BotTelemetryBuffer TelemetryBuffer;
        BotExperimentCoordinator ExperimentCoordinator;
        PartyRuntime Party;
        RaidRuntime Raid;
    };

    struct BotGuidLease
    {
        uint64 ServerEpoch = 0;
        std::string CohortId;
        uint64 AttemptId = 0;
        std::string RoleSlot;
    };

    BotWorldPopulationMgr();
    CohortRuntime& Cohort();
    CohortRuntime const& Cohort() const;
    PartyRuntime& Party();
    PartyRuntime const& Party() const;
    CohortRuntime* FindCohort(std::string const& cohortId);
    CohortRuntime const* FindCohort(std::string const& cohortId) const;
    bool SelectCohort(std::string const& cohortId);
    uint32 ActiveCohortCount() const;
    bool ClaimBotGuid(uint32 guid, std::string const& roleSlot);
    bool ReleaseBotGuid(uint32 guid);
    void ReleaseCohortLeases();
    bool LeaseOwnedByCurrentCohort(uint32 guid) const;
    bool LeaseOwnedByCurrentCohort(uint32 guid, std::string const& roleSlot) const;
    std::string UnknownCohortJson(char const* action, std::string const& cohortId) const;

    uint64 _serverEpoch = 0;
    std::map<std::string, std::unique_ptr<CohortRuntime>> _cohorts;
    mutable std::string _selectedCohortId = "default";
    std::string _runningCohortId;
    mutable std::mutex _leaseMutex;
    std::map<uint32, BotGuidLease> _guidLeases;

};

#define sBotWorldPopulationMgr BotWorldPopulationMgr::instance()

#endif
