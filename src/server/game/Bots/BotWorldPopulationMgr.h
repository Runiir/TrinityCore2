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
#include "Bots/BotWorldPopulationMgrMovement.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotTelemetryBuffer.h"
#include "Bots/BotTelemetryPolicy.h"
#include "Bots/BotWorldPopulationMgrValidationRouteContexts.h"
#include "Bots/BotWorldPopulationMgrValidationRouteGroupRecovery.h"
#include "Bots/BotWorldPopulationMgrValidationRouteMovementCheck.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"
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
namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct HealerAddWavePrepositionRequest;
struct Context;
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
    void PrepareCombatPeriodicOutcome(Unit* attacker, Unit* victim,
        uint32 spellId, bool critical, float critChancePct);
    void NotifyCombatDamage(Unit* attacker, Unit* victim, uint32 spellId, uint32 damage, uint32 unmitigatedDamage,
        uint32 damageType, uint32 schoolMask);
    void NotifyDragonwrathCopyProcAttempt(Unit* caster, uint32 originalSpellId,
        uint32 castResult, bool accepted);
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
    using ValidationRouteTargetingContext =
        BotWorldPopulationMgrValidationRoute::TargetingContext;
    using ValidationRoutePackContext =
        BotWorldPopulationMgrValidationRoute::PackContext;
    using ValidationRouteFocusContext =
        BotWorldPopulationMgrValidationRoute::FocusContext;
    using ValidationRouteAnchorContext =
        BotWorldPopulationMgrValidationRoute::AnchorContext;
    using ValidationRouteMovementCheckCallbacks =
        BotWorldPopulationMgrValidationRoute::MovementCheckCallbacks;
    using ValidationRouteGroupRecoveryCallbacks =
        BotWorldPopulationMgrValidationRoute::GroupRecoveryCallbacks;
    friend struct BotWorldPopulationMgrValidationRoute::DrudgeLaneContext;
    friend struct BotWorldPopulationMgrValidationRoute::GroupRecoveryContext;
    friend struct BotWorldPopulationMgrValidationRoute::ObjectiveContext;
    friend struct BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::Context;

#include "Bots/BotWorldPopulationMgrPlanningContracts.h"

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
    struct CalibrationMetrics;
    void EnsureCalibrationPopulation();
    void ResetCalibrationScoredWindow();
    void ResetCalibrationInitialResources(Player* bot,
        CalibrationMetrics& metrics);
    void UpdateCalibrationTargetHealthSchedule(uint64 nowMs);
    void UpdateCalibrationControlledDamage();
    void CompleteCalibrationScoredWindow();
    void DrainCalibrationPostWindowEffects();
    bool UpdateCalibrationHealer(WorldBotState& state, Player* healer);
    bool IsSelfProvidedCalibrationBaseline() const;
    std::pair<bool, bool> ApplyCalibrationReferenceConditions(Player* bot, Unit* target) const;
    bool EnsureCalibrationSelfProvidedConsumables(WorldBotState& state,
        Player* bot, Unit* target, bool scored);
    void ObserveCalibrationReferenceConditions(CalibrationMetrics& metrics,
        Player* bot, Unit* target, uint64 observedAtMs) const;
    static void ObserveWillOfUnbinding(CalibrationMetrics& metrics,
        Player* bot, uint64 observedAtMs);
    static void ObserveAfflictionCalibrationModifiers(CalibrationMetrics& metrics,
        Player* bot, Creature* fixtureTarget);
    static void ObserveAfflictionDamageStage(CalibrationMetrics& metrics,
        Player* owner, Unit* victim, uint32 spellId, uint32 damage,
        uint32 unmitigatedDamage, uint32 damageType, bool critical,
        float critChancePct);
    static std::string AppendAfflictionCalibrationJson(CalibrationMetrics const* metrics);
    void AppendCalibrationBotActionJson(std::ostringstream& json,
        CalibrationMetrics const* metrics) const;
    void AppendCalibrationReferenceConditionJson(std::ostringstream& json,
        WorldBotState const& state, CalibrationMetrics const* metrics,
        BotCalibrationFixtureContractGenerated::SpecContract const* fixtureSpecContract) const;
    void AppendCalibrationConsumableExecutionJson(std::ostringstream& json,
        CalibrationMetrics const* metrics,
        BotCalibrationFixtureContractGenerated::SpecContract const* fixtureSpecContract) const;
    void AppendCombatCalibrationBotRowsJson(std::ostringstream& json,
        std::map<uint32, CalibrationMetrics> const& metricsByGuid,
        uint64 nowMs,
        BotCalibrationFixtureContractGenerated::SpecContract const* fixtureSpecContract,
        bool completedWindow) const;
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
    struct BotUpdateContext;
    void UpdateBot(WorldBotState& state, uint32 diff);
    void HoldValidationAttemptFailure(WorldBotState& state, Player* bot);
    bool PrepareBotUpdate(BotUpdateContext& context);
    void PrepareValidationKernel(BotUpdateContext& context);
    void SubmitAdaptiveKernelCandidates(BotUpdateContext& context);
    void SubmitValidationKernelFallbackCandidates(BotUpdateContext& context);
    bool RunLegacyBotDecision(BotUpdateContext& context);
    bool RunBotDecisionKernel(BotUpdateContext& context);
    void FinalizeBotUpdate(BotUpdateContext& context);
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
    bool ExecuteMovementIntent(WorldBotState& state, Player* bot,
        BotWorldMovement::Intent const& intent);
    BotMovementArbitration::Request BuildMovementRequest(
        Player* bot, BotWorldMovement::Intent const& intent, uint64 nowMs) const;
    BotWorldMovement::ActivePathObservation ObserveActiveMovement(
        WorldBotState const& state, Player* bot,
        BotWorldMovement::Intent const& intent,
        BotMovementArbitration::Request const& request) const;
    bool PlanMovementPath(Player* bot, BotWorldMovement::Intent const& intent,
        BotWorldMovement::PathPlan& plan) const;
    bool RejectMovementPath(WorldBotState& state, Player* bot,
        BotWorldMovement::Intent const& intent, char const* reason);
    void CommitMovementEvidence(WorldBotState& state, Player* bot,
        BotWorldMovement::Intent const& intent,
        BotWorldMovement::PathPlan const& plan,
        BotMovementArbitration::Request const& request, uint64 nowMs);
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
    bool TryValidationRouteObjectiveGate(WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, std::string& situation,
        std::string& action, Unit*& target, bool& arrivalRoute);
    ValidationRouteTargetingContext BuildValidationRouteTargetingContext(
        WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, bool discoveryLeg);
    ValidationRoutePackContext BuildValidationRoutePackContext(
        WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, bool discoveryLeg,
        ValidationRouteTargetingContext const& targeting);
    ValidationRouteFocusContext BuildValidationRouteFocusContext(
        WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, bool discoveryLeg,
        ValidationRouteTargetingContext const& targeting,
        ValidationRoutePackContext const& pack,
        std::string& authoritativeFocusFailure);
    ValidationRouteAnchorContext ResolveValidationRouteAnchor(
        WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity,
        Unit* currentTarget,
        std::function<Unit*(Unit*)> const& routeUsableCombatTarget,
        std::function<ObjectGuid()> const& routeTankFocusGuid,
        std::function<bool()> const& persistedPackHasLiveMembers);
    bool TryValidationRouteMovementCheck(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action, Unit* preferredTarget, ValidationRouteMovementCheckCallbacks const& callbacks);
    bool TryValidationRouteGroupRecovery(WorldBotState& state, Player* bot,
        BotRolePowerBreakdown const& power, BotProgressionStage stage,
        BotProgressionActivity activity, std::string& situation,
        std::string& action, Unit*& target, bool discoveryLeg,
        ValidationRouteGroupRecoveryCallbacks const& callbacks);
    bool TryValidationRouteDrudgeChargeLanes(WorldBotState&, Player*, BotRolePowerBreakdown const&, BotProgressionStage, BotProgressionActivity, std::string&, std::string&, Unit*&, std::function<bool(Player*, Unit*, bool, bool)> const&, std::function<bool(Creature const*)> const&, std::function<float()> const&, float);
    bool TryValidationRouteDrudgeMinimumDistance(WorldBotState&, Player*, BotRolePowerBreakdown const&, BotProgressionStage, BotProgressionActivity, std::string&, std::string&, Unit*&, std::function<bool(Creature const*)> const&, bool = false);
    bool TryValidationRouteFeralHazardHealerRoar(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action);
    bool TryValidationRouteFeralHazardLooseTaunt(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action);
    bool TryValidationRouteHealerHazardFade(WorldBotState& state, Player* bot, Unit* preferredTarget, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action);
    bool TryValidationRouteTankHazardHoldAreaThreat(WorldBotState& state, Player* bot, Unit* activeHazard, float safeRadius, bool radialHazard, bool allowMovement, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action);
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

#include "Bots/BotWorldPopulationMgrCalibrationMetrics.h"
    static void ObserveCalibrationEffectiveStats(Unit* unit,
        uint64 observedAtMs, CalibrationMetrics::EffectiveStatVector& stats);
    static void AppendCalibrationEffectiveStatsJson(std::ostringstream& json,
        CalibrationMetrics::EffectiveStatVector const& stats);
    void AppendCombatCalibrationSummaryJson(std::ostringstream& json,
        uint64 nowMs,
        std::function<void(std::map<uint32, CalibrationMetrics> const&, bool)> const& writeBots) const;

#include "Bots/BotWorldPopulationMgrRuntimeContracts.h"
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
