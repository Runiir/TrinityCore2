#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DRUDGE_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DRUDGE_H

#include "Bots/BotWorldPopulationMgrBotState.h"
#include "Bots/BotWorldPopulationMgrRouteState.h"
#include "Bots/BotTypes.h"

#include <functional>
#include <string>
#include <utility>
#include <vector>

class BotWorldPopulationMgr;
class Creature;
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

struct DrudgeLaneContext
{
    using WorldBotState = BotWorldPopulationMgrBotState::WorldBotState;
    using MemberAnchor = BotWorldPopulationMgrRouteState::ValidationRouteMemberAnchor;
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
    std::function<MemberAnchor const*(uint32)> DeclaredNavigationTankAnchorFor;
    std::function<MemberAnchor const*(uint32)> DeclaredRecoveryTankAnchorFor;
    std::function<bool()> CombatTankStagingActive;
    std::function<bool(float, float, float, bool, std::string*)> StrictNativePath;
    std::function<bool(float, float, float)> StrictTankRecoveryPath;
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

    DrudgeLaneContext(DrudgeLaneRequest const& request);
    bool Run();
    bool IsLandedRushPending() const;
    bool IsRecoveryFormationActive() const;
    bool TryMinimumDistance(bool specializedDrudgeRecovery);
    bool ComputeExactCombatTankPathsProven() const;
    bool ComputeExactRecoveryTankPathsProven() const;
    bool ComputeExactLiveRecoveryTankPathsPreflighted() const;

    PhaseResult BuildContract();
    PhaseResult ResolveSources();
    PhaseResult BuildAnchorPolicies();
    PhaseResult RunFormationActions();
    PhaseResult RunThreatAndEvidenceActions();

    void HoldOffense();
    void Record(Creature* source, char const* result,
        float value = 0.0f, uint32 value2 = 0);
    void RecordReseparationEvidence(ChargeObservation& observation);
};

bool TryValidationRouteDrudgeChargeLanes(DrudgeLaneRequest const& request);
}

#endif
