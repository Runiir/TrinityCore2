#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DRUDGE_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DRUDGE_H

#include "Bots/BotWorldPopulationMgrBotState.h"
#include "Bots/BotWorldPopulationMgrConfig.h"
#include "Bots/BotWorldPopulationMgrRouteState.h"
#include "Bots/BotTypes.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeReseparationReceipt.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeThreatSeedState.h"

#include <functional>
#include <string>
#include <utility>
#include <vector>

class BotWorldPopulationMgr;
class Creature;
class PathGenerator;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
struct DrudgeLaneCallbacks
{
    std::function<bool(Player*, Unit*, bool, bool)> TryGroupHeal;
    std::function<bool(Creature const*)> IsCombatLinked;
    std::function<float()> CanonicalRouteDistance;
    std::function<bool(bool)> TryMinimumDistance;
};

// A narrow request keeps Drudge mechanics independent from the objective
// lambda.  The callbacks are intentionally typed: generic healing and combat
// linkage may observe this lane, but neither can replace its native ownership
// and evidence ordering.
struct DrudgeLaneRequest
{
    BotWorldPopulationMgr* Manager = nullptr;
    BotWorldPopulationMgrBotState::WorldBotState* State = nullptr;
    Player* Bot = nullptr;
    BotRolePowerBreakdown const* Power = nullptr;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
    std::string* Situation = nullptr;
    std::string* Action = nullptr;
    Unit** Target = nullptr;
    float RouteArrivalRadius = 18.0f;
    DrudgeLaneCallbacks Callbacks;
};

struct DrudgeSeedCandidate;

struct DrudgeLaneContext
{
    using WorldBotState = BotWorldPopulationMgrBotState::WorldBotState;
    using MemberAnchor = ::ValidationRouteMemberAnchor;
    using ChargeObservation = BotWorldPopulationMgrRouteState::ValidationRouteDrudgeChargeObservation;

    enum class PhaseResult
    {
        Continue,
        Handled,
        Abort
    };

    BotWorldPopulationMgr& Manager;
    WorldBotState& State;
    Player* Bot;
    BotRolePowerBreakdown const& Power;
    BotProgressionStage Stage;
    BotProgressionActivity Activity;
    std::string& Situation;
    std::string& Action;
    Unit*& Target;
    float RouteArrivalRadius;
    DrudgeLaneCallbacks Callbacks;

    std::vector<uint32> ExactRosterSlots;
    std::vector<uint32> HealerSlots;
    std::vector<Creature*> Sources;
    Creature* LaneSource = nullptr;
    Creature* OtherSource = nullptr;
    Player* LaneTank = nullptr;
    Player* OtherTank = nullptr;
    uint32 OneBasedSlot = 0;
    uint32 LaneIndex = 0;
    uint32 LaneTankSlot = 0;
    uint32 OtherTankSlot = 0;
    bool LaneA = false;
    bool LaneB = false;
    bool AssignedTank = false;
    std::string Role;
    bool SourceCombatStarted = false;
    bool ContractResolved = false;
    float AxisX = 0.0f;
    float AxisY = 0.0f;
    float MidpointX = 0.0f;
    float MidpointY = 0.0f;
    float MidpointZ = 0.0f;
    float LaneSeparation = 0.0f;
    float LaneSign = 0.0f;
    float SourceSeparation = 0.0f;

    std::function<bool(uint32)> DeclaredAnchorAvailable;
    std::function<bool(uint32)> DeclaredNavigationTankAnchorAvailable;
    std::function<bool(uint32)> DeclaredRecoveryTankAnchorAvailable;
    std::function<MemberAnchor const*(uint32)> DeclaredAnchorFor;
    std::function<MemberAnchor const*(uint32)> DeclaredRecoveryMemberAnchorFor;
    std::function<MemberAnchor const*(uint32)> DeclaredNavigationTankAnchorFor;
    std::function<MemberAnchor const*(uint32)> DeclaredCombatTankAnchorFor;
    std::function<MemberAnchor const*(uint32)> DeclaredRecoveryTankAnchorFor;
    std::function<bool()> CombatTankStagingActive;
    std::function<bool(float, float, float, bool, bool, std::string*)> StrictNativePath;
    std::function<bool(float, float, float)> StrictTankRecoveryPath;
    std::function<bool(uint32)> RecoveryAnchorReachedFor;
    std::function<std::pair<float, float>(uint32)> UniqueGroupAnchor;
    std::function<std::vector<std::pair<float, float>>(uint32)> AnchorCandidatesFor;
    std::function<bool()> AnchorCacheMatchesGeneration;
    std::function<bool(WorldBotState const&, Player const*)> CachedAnchorSafe;
    std::function<bool(Player const*)> GroupPositionSafe;
    std::function<bool()> ExactRosterPrepullStaged;
    std::function<bool(Creature const*, uint32, float*)> SourceOnFrozenLane;
    std::function<bool(bool)> SelectPathableDrudgeAnchor;
    std::function<bool()> ExactRosterReSeparated;
    std::function<void(ChargeObservation&)> MarkAllRosterReseparated;
    std::function<bool()> ExactCombatTankPathsProven;
    std::function<bool()> ExactRecoveryTankPathsProven;
    std::function<bool()> ExactRecoveryTankAnchorsReached;
    std::function<bool()> ExactCombatTankAnchorsReached;
    std::function<bool()> ExactCombatTankAnchorsSafe;
    std::function<bool()> ExactLiveRecoveryTankPathsPreflighted;
    std::function<bool(Player const*, uint32)> TankOnFrozenLane;
    std::function<bool()> TanksOnFrozenLanes;
    std::function<bool()> BoundTankSourceGeometrySafe;

    ChargeObservation* Charge = nullptr;
    bool ChargeAwaitingLanding = false;
    bool NativeChargePending = false;
    Creature* NativeChargeSource = nullptr;
    Unit* NativeChargeTarget = nullptr;
    bool NativeChargeTargetRoleViolation = false;
    bool NativeChargeContractViolation = false;
    bool NativeChargeTargetLaneViolation = false;
    bool FormationRequired = false;
    bool FormationRequiredMutable = false;
    bool PairTooClose = false;
    bool PrepullStaged = false;
    bool RecoveryFormationActive = false;
    bool ContinueToThreatAndEvidence = false;

    DrudgeLaneContext(DrudgeLaneRequest const& request);
    bool Run();
    bool IsLandedRushPending() const;
    bool IsEntrancePullEstablished() const;
    bool IsRecoveryFormationActive() const;
    bool IsDynamicGroupRecoveryActive() const;
    bool TryMinimumDistance(bool specializedDrudgeRecovery);
    bool IsRecoveryCandidateSpacingSafe(float x, float y, bool tank) const;
    bool SourceUnionSafeAt(uint32 sourceIndex, float x, float y) const;
    bool SourceUnionSafe(float x, float y) const;
    bool SourceUnionPathSafe(PathGenerator const& path) const;
    BotRaidDrudgeSpacing::PeerResult EvaluateRecoveryCandidateSpacing(
        float x, float y, bool tank) const;
    BotRaidDrudgeSpacing::CandidateResult EvaluateAndRecordCandidateSpacing(
        uint32 candidateIndex, float x, float y, bool tank,
        bool dynamicCandidate, float dynamicLaneProjection, uint64 nowMs);
    bool ComputeStrictTankRecoveryPath(float x, float y, float z) const;
    bool SeedCombatEnvelopeSafe(uint32 slot, float x, float y) const;
    bool ComputeGroupPositionSafe(Player const* member) const;
    bool SelectProgressiveDrudgeEscape(uint64 nowMs);
    bool ComputeRecoveryAnchorReached(uint32 slot) const;
    bool ComputeExactCombatTankPathsProven() const;
    bool ComputeExactRecoveryTankPathsProven() const;
    bool ComputeExactRecoveryTankAnchorsReached() const;
    bool ComputeExactCombatTankAnchorsReached() const;
    bool ComputeExactLiveRecoveryTankPathsPreflighted() const;
    bool RecoveryTankReturnBarrierOpen() const;
    bool RecoveryTankAnchorPending(uint32 slot) const;
    PhaseResult BuildContract();
    PhaseResult ResolveSources();
    PhaseResult BuildAnchorPolicies();
    PhaseResult RunFormationActions();
    PhaseResult RunNativeTauntConfirmation(bool nativeOwnershipAllowed,
        bool recoveryAnchorsReachedBeforeTick,
        bool combatTankAnchorsReachedBeforeTick);
    PhaseResult RunThreatAndEvidenceActions();
    PhaseResult RunDrudgeSeedCoordinator();

    static BotRaidDrudgeThreatSeed::Scope CurrentDrudgeSeedScope(
        DrudgeLaneContext const& context);
    static BotRaidDrudgeThreatSeed::State ReadDrudgeSeedState(
        DrudgeLaneContext const& context, BotRaidDrudgeThreatSeed::Scope scope);
    static void ApplyDrudgeSeedState(DrudgeLaneContext& context,
        BotRaidDrudgeThreatSeed::CoordinatorResult const& result);
    static bool ExactDrudgeAuthorityRoster(DrudgeLaneContext const& context);
    static void SuppressAllDrudgeOffense(DrudgeLaneContext const& context);
    static DrudgeSeedCandidate ResolveDrudgeSeedCandidate(
        DrudgeLaneContext& context, uint32 lane,
        BotRaidDrudgeThreatSeed::State const& seedState);
    static void AppendDrudgeSeedEvidence(DrudgeLaneContext& context, uint32 lane,
        DrudgeSeedCandidate const& candidate, BotRaidDrudgeThreatSeed::Scope scope,
        uint64 observedAtMs);

    void HoldOffense();
    void Record(Creature* source, char const* result,
        float value = 0.0f, uint32 value2 = 0);
    void RecordRecoveryDiagnosticTick(uint64 observedAtMs,
        bool allRecoveryAnchorsReached, bool allRecoveryTankPathsProven,
        bool allCombatTankPathsProven, bool allCombatTankAnchorsReached,
        bool exactRosterReseparated);
    void RecordNativeTransition(Creature* source, char const* result,
        uint32 actionValue);
    void RecordReseparationEvidence(ChargeObservation& observation);
};

bool TryValidationRouteDrudgeChargeLanes(DrudgeLaneRequest const& request);
}

#endif
