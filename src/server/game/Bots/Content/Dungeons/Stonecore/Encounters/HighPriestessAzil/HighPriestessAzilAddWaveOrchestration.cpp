#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveOrchestration.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveDiscovery.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveDensity.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveOpeningActions.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveTankPreparation.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilFeralHandoffState.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilFeralLocalRetention.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilFeralRemoteActions.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilFeralActiveSwarmMovement.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilHunterThreatTransfer.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilHighDensityPositioning.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilDensityCombatResolution.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilPassiveSwarmStaging.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilTankThreatRecovery.h"
#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilSwarmThreatSafety.h"

#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <array>
#include <functional>
#include <string>
#include <vector>

namespace
{
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
}

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
bool Context::Run(AddWaveOrchestrationRequest const& request)
{
    static constexpr float PassiveTankDensityClusterRadius = 10.0f;
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    BotProgressionStage stage = request.Stage;
    BotProgressionActivity activity = request.Activity;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;
    GroupHealCallback const& tryRouteGroupHeal = request.TryRouteGroupHeal;
    std::function<float(Player*, Unit const*, uint32)> const& routeEngageRange =
        request.RouteEngageRange;
    float canonicalRouteDistance = request.CanonicalRouteDistance;
    float routeArrivalRadius = request.RouteArrivalRadius;

    // High Priestess Azil's healer-side add-wave handoff is kept in its
    // encounter-owned module. The generic add resolver follows this
    // early branch in the original decision order.
    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::HealerAddWavePrepositionRequest healerAddWaveRequest;
    healerAddWaveRequest.Manager = &manager;
    healerAddWaveRequest.State = &state;
    healerAddWaveRequest.Bot = bot;
    healerAddWaveRequest.Power = &power;
    healerAddWaveRequest.Stage = stage;
    healerAddWaveRequest.Activity = activity;
    healerAddWaveRequest.Situation = &situation;
    healerAddWaveRequest.Action = &action;
    healerAddWaveRequest.Target = &target;
    healerAddWaveRequest.TryRouteGroupHeal.Function =
        [&tryRouteGroupHeal](Player* healer, Unit* combatTarget,
            bool allowMovement, bool allowStationaryCastTime)
        {
            return tryRouteGroupHeal(healer, combatTarget,
                allowMovement, allowStationaryCastTime);
        };
    if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryHealerAddWavePreposition(
            healerAddWaveRequest))
        return true;

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveDiscoveryRequest addWaveDiscoveryRequest;
    addWaveDiscoveryRequest.Manager = &manager;
    addWaveDiscoveryRequest.State = &state;
    addWaveDiscoveryRequest.Bot = bot;
    addWaveDiscoveryRequest.Power = &power;
    addWaveDiscoveryRequest.Stage = stage;
    addWaveDiscoveryRequest.Activity = activity;
    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveDiscoveryResult addWaveDiscovery =
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::DiscoverAddWave(
            addWaveDiscoveryRequest);
    Unit* add = nullptr;
    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveDensityRequest addWaveDensityRequest;
    addWaveDensityRequest.Manager = &manager;
    addWaveDensityRequest.State = &state;
    addWaveDensityRequest.Bot = bot;
    addWaveDensityRequest.Power = &power;
    addWaveDensityRequest.Stage = stage;
    addWaveDensityRequest.Activity = activity;
    addWaveDensityRequest.Discovery = &addWaveDiscovery;
    addWaveDensityRequest.CanonicalRouteDistance = canonicalRouteDistance;
    addWaveDensityRequest.RouteArrivalRadius = routeArrivalRadius;
    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveDensityResult addWaveDensity =
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::ResolveAddWaveDensity(
            addWaveDensityRequest);
    if (addWaveDensity.BypassPreArrival)
        return false;

    add = addWaveDensity.Add;
    bool sharedFocusValid = addWaveDensity.SharedFocusValid;
    uint32 addCount = addWaveDiscovery.AddCount;
    uint32 engagedAddCount = addWaveDiscovery.EngagedAddCount;
    uint32 nearbyAddCount = addWaveDiscovery.NearbyAddCount;
    float addX = addWaveDiscovery.AddX;
    float addY = addWaveDiscovery.AddY;
    std::vector<Creature*>& localAdds = addWaveDiscovery.LocalAdds;
    bool cohortSwarmActive = addWaveDiscovery.CohortSwarmActive;
    std::function<bool(Player*, Unit*)> isUsableListedAdd =
        addWaveDiscovery.IsUsableListedAdd;
    bool sharedLargePassiveSwarmStaging =
        addWaveDensity.SharedLargePassiveSwarmStaging;
    bool swarmDefenseActive = addWaveDensity.SwarmDefenseActive;
    std::string const& role = addWaveDensity.Role;
    BotClassSpecActionProfile const& profile = addWaveDensity.Profile;
    uint32 reservedAreaSpellId = addWaveDensity.ReservedAreaSpellId;
    Player* densityTank = addWaveDensity.DensityTank;
    Player* densityHealer = addWaveDensity.DensityHealer;
    Player* densityDefenseTarget = addWaveDensity.DensityDefenseTarget;
    uint32 densityTankOwnedAddCount = addWaveDensity.DensityTankOwnedAddCount;
    uint32 densityTankSecureAddCount = addWaveDensity.DensityTankSecureAddCount;
    bool densityTankOwnsSecureMajority =
        addWaveDensity.DensityTankOwnsSecureMajority;
    bool densityTankOwnsVictimMajority =
        addWaveDensity.DensityTankOwnsVictimMajority;
    bool urgentSwarmDamageRelease =
        addWaveDensity.UrgentSwarmDamageRelease;
    bool botInsideTankPickup = addWaveDensity.BotInsideTankPickup;
    std::function<size_t(Player const*)> observedListedAttackerCount =
        addWaveDensity.ObservedListedAttackerCount;
    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveOpeningActionsRequest openingActionsRequest;
    openingActionsRequest.Manager = &manager;
    openingActionsRequest.State = &state;
    openingActionsRequest.Bot = bot;
    openingActionsRequest.Power = &power;
    openingActionsRequest.Stage = stage;
    openingActionsRequest.Activity = activity;
    openingActionsRequest.Discovery = &addWaveDiscovery;
    openingActionsRequest.Density = &addWaveDensity;
    openingActionsRequest.Situation = &situation;
    openingActionsRequest.Action = &action;
    openingActionsRequest.Target = &target;
    if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryAddWaveOpeningActions(
            openingActionsRequest))
        return true;

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveTankPreparationRequest tankPreparationRequest;
    tankPreparationRequest.Manager = &manager;
    tankPreparationRequest.State = &state;
    tankPreparationRequest.Bot = bot;
    tankPreparationRequest.Power = &power;
    tankPreparationRequest.Stage = stage;
    tankPreparationRequest.Activity = activity;
    tankPreparationRequest.Discovery = &addWaveDiscovery;
    tankPreparationRequest.Density = &addWaveDensity;
    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::AddWaveTankPreparationResult tankPreparation =
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::PrepareAddWaveTank(
            tankPreparationRequest);
    add = tankPreparation.Add;
    sharedFocusValid = tankPreparation.SharedFocusValid;
    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralHandoffStateRequest feralHandoffRequest;
    feralHandoffRequest.Manager = &manager;
    feralHandoffRequest.State = &state;
    feralHandoffRequest.Bot = bot;
    feralHandoffRequest.Power = &power;
    feralHandoffRequest.Stage = stage;
    feralHandoffRequest.Activity = activity;
    feralHandoffRequest.Discovery = &addWaveDiscovery;
    feralHandoffRequest.Density = &addWaveDensity;
    feralHandoffRequest.Add = &add;
    feralHandoffRequest.SharedFocusValid = &sharedFocusValid;
    feralHandoffRequest.Situation = &situation;
    feralHandoffRequest.Action = &action;
    feralHandoffRequest.Target = &target;
    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralHandoffStateResult feralHandoff =
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::ResolveFeralHandoffState(
            feralHandoffRequest);
    if (feralHandoff.Handled)
        return true;

    auto const& tryFeralRoarPickup = feralHandoff.TryFeralRoarPickup;
    bool feralChargePickupArrived =
        feralHandoff.FeralChargePickupArrived;


    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralLocalRetentionRequest localRetentionRequest;
    localRetentionRequest.Manager = &manager;
    localRetentionRequest.State = &state;
    localRetentionRequest.Bot = bot;
    localRetentionRequest.Power = &power;
    localRetentionRequest.Stage = stage;
    localRetentionRequest.Activity = activity;
    localRetentionRequest.Discovery = &addWaveDiscovery;
    localRetentionRequest.Density = &addWaveDensity;
    localRetentionRequest.FeralHandoff = &feralHandoff;
    localRetentionRequest.Add = add;
    localRetentionRequest.Situation = &situation;
    localRetentionRequest.Action = &action;
    localRetentionRequest.Target = &target;
    if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryFeralLocalRetention(
            localRetentionRequest))
        return true;

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralRemoteActionsRequest remoteActionsRequest;
    remoteActionsRequest.Manager = &manager;
    remoteActionsRequest.State = &state;
    remoteActionsRequest.Bot = bot;
    remoteActionsRequest.Power = &power;
    remoteActionsRequest.Stage = stage;
    remoteActionsRequest.Activity = activity;
    remoteActionsRequest.Discovery = &addWaveDiscovery;
    remoteActionsRequest.Density = &addWaveDensity;
    remoteActionsRequest.FeralHandoff = &feralHandoff;
    remoteActionsRequest.Add = &add;
    remoteActionsRequest.SharedFocusValid = &sharedFocusValid;
    remoteActionsRequest.Situation = &situation;
    remoteActionsRequest.Action = &action;
    remoteActionsRequest.Target = &target;
    if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryFeralRemoteActions(
            remoteActionsRequest))
        return true;

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::FeralActiveSwarmMovementRequest activeSwarmMovementRequest;
    activeSwarmMovementRequest.Manager = &manager;
    activeSwarmMovementRequest.State = &state;
    activeSwarmMovementRequest.Bot = bot;
    activeSwarmMovementRequest.Power = &power;
    activeSwarmMovementRequest.Stage = stage;
    activeSwarmMovementRequest.Activity = activity;
    activeSwarmMovementRequest.Discovery = &addWaveDiscovery;
    activeSwarmMovementRequest.Density = &addWaveDensity;
    activeSwarmMovementRequest.FeralHandoff = &feralHandoff;
    activeSwarmMovementRequest.Add = add;
    activeSwarmMovementRequest.Situation = &situation;
    activeSwarmMovementRequest.Action = &action;
    activeSwarmMovementRequest.Target = &target;
    if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryFeralActiveSwarmMovement(
            activeSwarmMovementRequest))
        return true;

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::HunterThreatTransferRequest hunterThreatTransferRequest;
    hunterThreatTransferRequest.Manager = &manager;
    hunterThreatTransferRequest.State = &state;
    hunterThreatTransferRequest.Bot = bot;
    hunterThreatTransferRequest.Power = &power;
    hunterThreatTransferRequest.Stage = stage;
    hunterThreatTransferRequest.Activity = activity;
    hunterThreatTransferRequest.Discovery = &addWaveDiscovery;
    hunterThreatTransferRequest.Density = &addWaveDensity;
    hunterThreatTransferRequest.Add = &add;
    hunterThreatTransferRequest.SharedFocusValid = &sharedFocusValid;
    hunterThreatTransferRequest.Situation = &situation;
    hunterThreatTransferRequest.Action = &action;
    hunterThreatTransferRequest.Target = &target;
    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::HunterThreatTransferResult hunterThreatTransfer =
        BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryHunterThreatTransfer(
            hunterThreatTransferRequest);
    bool hunterMisdirectionActive =
        hunterThreatTransfer.HunterMisdirectionActive;
    if (hunterThreatTransfer.Handled)
        return true;

    // The strict area-only resolver intentionally filters defensives,
    // so protect the tank here before selecting the next area-threat cast.
    // This is proactive at 12+ adds and escalates as health falls without
    // overlapping major native tank cooldowns.
    bool feralDruidTank = profile.SpecTag == "feral_druid_tank";
    bool majorTankDefensiveActive = bot->HasAura(498) || bot->HasAura(31850)
        || bot->HasAura(86150) || bot->HasAura(86659)
        || (feralDruidTank && (bot->HasAura(61336) || bot->HasAura(22812)));
    if (role == "tank" && cohortSwarmActive && addCount >= 12
        && UnitHealthPct(bot) <= 0.90f && !majorTankDefensiveActive
        && (!densityHealer || !observedListedAttackerCount(densityHealer)))
    {
        std::array<uint32, 3> defensiveSpells = feralDruidTank
            ? std::array<uint32, 3>{ 61336, 22812, 0 }
            : (UnitHealthPct(bot) <= 0.50f
                ? std::array<uint32, 3>{ 86150, 31850, 498 }
                : (UnitHealthPct(bot) <= 0.75f
                    ? std::array<uint32, 3>{ 31850, 498, 86150 }
                    : std::array<uint32, 3>{ 498, 31850, 86150 }));
        for (uint32 defensiveSpellId : defensiveSpells)
            if (defensiveSpellId && bot->HasSpell(defensiveSpellId)
                && manager.TryCastFriendlySpell(bot, bot, defensiveSpellId))
            {
                std::string raw = manager.BuildRawJson(bot, add);
                std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                manager.RecordEvent(state, bot, "defensive", bot, "tank_swarm_defensive",
                    raw.c_str(), semantic.c_str(), UnitHealthPct(bot), addCount, defensiveSpellId);
                target = add;
                situation = "dungeon_boss";
                action = "tank_swarm_defensive";
                return true;
            }
    }

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::PassiveSwarmStagingRequest passiveSwarmStagingRequest;
    passiveSwarmStagingRequest.Manager = &manager;
    passiveSwarmStagingRequest.State = &state;
    passiveSwarmStagingRequest.Bot = bot;
    passiveSwarmStagingRequest.Power = &power;
    passiveSwarmStagingRequest.Stage = stage;
    passiveSwarmStagingRequest.Activity = activity;
    passiveSwarmStagingRequest.Discovery = &addWaveDiscovery;
    passiveSwarmStagingRequest.Density = &addWaveDensity;
    passiveSwarmStagingRequest.Add = add;
    passiveSwarmStagingRequest.Situation = &situation;
    passiveSwarmStagingRequest.Action = &action;
    passiveSwarmStagingRequest.Target = &target;
    if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryPassiveSwarmStaging(
            passiveSwarmStagingRequest))
        return true;

    // A moving swarm can select a different representative attacker every
    // decision tick. Replacing the path for each target change prevented a
    // melee tank from reaching an otherwise stable density cluster.
    // Keep one destination briefly, then repath to the current explicit
    // victim cluster so a stale but still nearby endpoint cannot own an
    // unbounded approach.
    auto continueStableTankSwarmApproach = [&](Unit* selectedAdd) -> bool
    {
        return manager.ContinueStableTankSwarmApproach(state, selectedAdd,
            densityHealer, role, profile, cohortSwarmActive,
            PassiveTankDensityClusterRadius);
    };

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TankThreatRecoveryRequest tankThreatRecoveryRequest;
    tankThreatRecoveryRequest.Manager = &manager;
    tankThreatRecoveryRequest.State = &state;
    tankThreatRecoveryRequest.Bot = bot;
    tankThreatRecoveryRequest.Power = &power;
    tankThreatRecoveryRequest.Stage = stage;
    tankThreatRecoveryRequest.Activity = activity;
    tankThreatRecoveryRequest.Discovery = &addWaveDiscovery;
    tankThreatRecoveryRequest.Density = &addWaveDensity;
    tankThreatRecoveryRequest.Add = add;
    tankThreatRecoveryRequest.ContinueStableTankSwarmApproach =
        continueStableTankSwarmApproach;
    tankThreatRecoveryRequest.RouteEngageRange = routeEngageRange;
    tankThreatRecoveryRequest.Situation = &situation;
    tankThreatRecoveryRequest.Action = &action;
    tankThreatRecoveryRequest.Target = &target;
    if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryTankThreatRecovery(
            tankThreatRecoveryRequest))
        return true;

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::SwarmThreatSafetyRequest swarmThreatSafetyRequest;
    swarmThreatSafetyRequest.Manager = &manager;
    swarmThreatSafetyRequest.State = &state;
    swarmThreatSafetyRequest.Bot = bot;
    swarmThreatSafetyRequest.Power = &power;
    swarmThreatSafetyRequest.Stage = stage;
    swarmThreatSafetyRequest.Activity = activity;
    swarmThreatSafetyRequest.Discovery = &addWaveDiscovery;
    swarmThreatSafetyRequest.Density = &addWaveDensity;
    swarmThreatSafetyRequest.HunterThreatTransfer = &hunterThreatTransfer;
    swarmThreatSafetyRequest.Add = add;
    swarmThreatSafetyRequest.Situation = &situation;
    swarmThreatSafetyRequest.Action = &action;
    swarmThreatSafetyRequest.Target = &target;
    if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TrySwarmThreatSafety(
            swarmThreatSafetyRequest))
        return true;

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::HighDensityPositioningRequest highDensityPositioningRequest;
    highDensityPositioningRequest.Manager = &manager;
    highDensityPositioningRequest.State = &state;
    highDensityPositioningRequest.Bot = bot;
    highDensityPositioningRequest.Power = &power;
    highDensityPositioningRequest.Stage = stage;
    highDensityPositioningRequest.Activity = activity;
    highDensityPositioningRequest.Discovery = &addWaveDiscovery;
    highDensityPositioningRequest.Density = &addWaveDensity;
    highDensityPositioningRequest.Add = add;
    highDensityPositioningRequest.Situation = &situation;
    highDensityPositioningRequest.Action = &action;
    highDensityPositioningRequest.Target = &target;
    bool highDensityPositioningReturnFalse = false;
    highDensityPositioningRequest.ReturnFalse =
        &highDensityPositioningReturnFalse;
    highDensityPositioningRequest.TryRouteGroupHeal.Function =
        [&tryRouteGroupHeal](Player* healer, Unit* combatTarget,
            bool allowMovement, bool allowStationaryCastTime)
        {
            return tryRouteGroupHeal(healer, combatTarget,
                allowMovement, allowStationaryCastTime);
        };
    if (BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryHighDensityPositioning(
            highDensityPositioningRequest))
        return true;
    if (highDensityPositioningReturnFalse)
        return false;

    BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::DensityCombatResolutionRequest densityCombatResolutionRequest;
    densityCombatResolutionRequest.Manager = &manager;
    densityCombatResolutionRequest.State = &state;
    densityCombatResolutionRequest.Bot = bot;
    densityCombatResolutionRequest.Power = &power;
    densityCombatResolutionRequest.Stage = stage;
    densityCombatResolutionRequest.Activity = activity;
    densityCombatResolutionRequest.Discovery = &addWaveDiscovery;
    densityCombatResolutionRequest.Density = &addWaveDensity;
    densityCombatResolutionRequest.Add = add;
    densityCombatResolutionRequest.SharedFocusValid = sharedFocusValid;
    densityCombatResolutionRequest.HunterMisdirectionActive = hunterMisdirectionActive;
    densityCombatResolutionRequest.ContinueStableTankSwarmApproach =
        continueStableTankSwarmApproach;
    densityCombatResolutionRequest.RouteEngageRange = routeEngageRange;
    densityCombatResolutionRequest.Situation = &situation;
    densityCombatResolutionRequest.Action = &action;
    densityCombatResolutionRequest.Target = &target;
    return BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil::TryDensityCombatResolution(
        densityCombatResolutionRequest);

}

bool TryAddWaveOrchestration(AddWaveOrchestrationRequest const& request)
{
    return Context::Run(request);
}
}
