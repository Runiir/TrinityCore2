#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilFeralActiveSwarmMovement.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <cmath>
#include <string>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrSpellSemantics::NowMs;

bool Context::Run(FeralActiveSwarmMovementRequest const& request)
{
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;
    FeralHandoffStateResult const& feralHandoff = *request.FeralHandoff;
    Unit* add = request.Add;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;
    std::string const& role = density.Role;
    BotClassSpecActionProfile const& profile = density.Profile;
    Player* densityHealer = density.DensityHealer;
    Player* densityDefenseTarget = density.DensityDefenseTarget;
    std::function<size_t(Player const*)> const& observedListedAttackerCount =
        density.ObservedListedAttackerCount;
    uint32 engagedAddCount = discovery.EngagedAddCount;
    uint32 addCount = discovery.AddCount;
    auto const& tryFeralRoarPickup = feralHandoff.TryFeralRoarPickup;
    bool feralChargePickupArrived =
        feralHandoff.FeralChargePickupArrived;

    // Rerun66 rejected tightening the stable healer anchor: scripted
    // followers were not centered on the healer, so the Feral spent five
    // decisions moving there and still reached only two followers. For a
    // moderate active wave, reserve one deterministic density representative
    // for at most 2.5 seconds. Rerun67 proved that its first accepted point
    // becomes stale as the healer-owned hostile moves, so revalidate the
    // same GUID's current endpoint on each reserved tick. Larger split waves
    // retain passive preposition/Charge, and hazard movement remains
    // authoritative because it runs before this resolver.
    static constexpr float TankDensityClusterRadius = 10.0f;
    uint64 activeSwarmPickupNowMs = NowMs();
    bool activeSwarmPickupEligible = role == "tank"
        && profile.SpecTag == "feral_druid_tank"
        && densityHealer
        && observedListedAttackerCount(densityHealer) >= 3
        && observedListedAttackerCount(densityHealer) < 12
        && engagedAddCount >= 3 && addCount <= 24;
    if (!activeSwarmPickupEligible)
    {
        state.FeralActiveSwarmPickupAttempted = false;
        state.FeralActiveSwarmPickupArrived = false;
    }
    bool activeSwarmPickupReserved = activeSwarmPickupEligible
        && state.FeralActiveSwarmPickupUntilMs > activeSwarmPickupNowMs
        && !state.FeralActiveSwarmPickupAnchorGuid.IsEmpty();
    Unit* activeSwarmPickupAnchor = nullptr;
    if (activeSwarmPickupReserved)
    {
        activeSwarmPickupAnchor = ObjectAccessor::GetUnit(
            *bot, state.FeralActiveSwarmPickupAnchorGuid);
        if (!activeSwarmPickupAnchor || !activeSwarmPickupAnchor->IsAlive()
            || activeSwarmPickupAnchor->GetMap() != bot->GetMap()
            || activeSwarmPickupAnchor->GetVictim() != densityHealer)
        {
            state.FeralActiveSwarmPickupAnchorGuid.Clear();
            state.FeralActiveSwarmPickupUntilMs = 0;
            state.FeralActiveSwarmPickupArrived = false;
            activeSwarmPickupReserved = false;
            activeSwarmPickupAnchor = nullptr;
        }
    }
    else if (!state.FeralActiveSwarmPickupAnchorGuid.IsEmpty()
        || state.FeralActiveSwarmPickupUntilMs)
    {
        state.FeralActiveSwarmPickupAnchorGuid.Clear();
        state.FeralActiveSwarmPickupUntilMs = 0;
        state.FeralActiveSwarmPickupArrived = false;
    }

    bool startingActiveSwarmPickup = !activeSwarmPickupReserved
        && activeSwarmPickupEligible
        && !state.FeralActiveSwarmPickupAttempted && add
        && add->GetVictim() == densityHealer
        && !bot->HasUnitState(UNIT_STATE_CASTING)
        && !bot->IsFalling();
    if (startingActiveSwarmPickup)
        activeSwarmPickupAnchor = add;
    if (activeSwarmPickupAnchor
        && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
    {
        if (bot->GetExactDist2d(activeSwarmPickupAnchor)
            <= TankDensityClusterRadius)
        {
            if (startingActiveSwarmPickup)
            {
                state.FeralActiveSwarmPickupAttempted = true;
                state.FeralActiveSwarmPickupAnchorGuid =
                    activeSwarmPickupAnchor->GetGUID();
            }
            if (!state.FeralActiveSwarmPickupArrived)
            {
                state.FeralActiveSwarmPickupArrived = true;
                state.FeralActiveSwarmPickupUntilMs =
                    activeSwarmPickupNowMs + 1500;
            }
            bot->StopMoving();
            if (tryFeralRoarPickup(true))
            {
                state.FeralActiveSwarmPickupAnchorGuid.Clear();
                state.FeralActiveSwarmPickupUntilMs = 0;
                state.FeralActiveSwarmPickupArrived = false;
                return true;
            }
            if (state.FeralActiveSwarmPickupUntilMs
                > activeSwarmPickupNowMs)
            {
                std::string raw = manager.BuildRawJson(
                    bot, activeSwarmPickupAnchor);
                std::string semantic = manager.BuildSemanticJson(
                    bot, activeSwarmPickupAnchor, "dungeon_boss",
                    &power, request.Stage, request.Activity);
                manager.RecordEvent(state, bot, "boss_add_density",
                    activeSwarmPickupAnchor,
                    "feral_hold_bounded_active_swarm_cluster_for_roar",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(activeSwarmPickupAnchor),
                    addCount);
                state.TargetGuid =
                    activeSwarmPickupAnchor->GetGUID();
                target = activeSwarmPickupAnchor;
                situation = "dungeon_boss";
                action =
                    "hold_bounded_active_swarm_cluster_for_roar";
                return true;
            }
            state.FeralActiveSwarmPickupAnchorGuid.Clear();
            state.FeralActiveSwarmPickupUntilMs = 0;
            state.FeralActiveSwarmPickupArrived = false;
        }
        else
        {
            bool continuingReservedPickup = activeSwarmPickupReserved;
            bool moved = manager.MoveBotToPoint(state, bot,
                activeSwarmPickupAnchor->GetPositionX(),
                activeSwarmPickupAnchor->GetPositionY(),
                activeSwarmPickupAnchor->GetPositionZ());
            if (moved)
            {
                if (startingActiveSwarmPickup)
                {
                    state.FeralActiveSwarmPickupAttempted = true;
                    state.FeralActiveSwarmPickupArrived = false;
                    state.FeralActiveSwarmPickupAnchorGuid =
                        activeSwarmPickupAnchor->GetGUID();
                    state.FeralActiveSwarmPickupUntilMs =
                        activeSwarmPickupNowMs + 2500;
                }
                std::string raw = manager.BuildRawJson(bot, activeSwarmPickupAnchor);
                std::string semantic = manager.BuildSemanticJson(
                    bot, activeSwarmPickupAnchor, "dungeon_boss",
                    &power, request.Stage, request.Activity);
                manager.RecordEvent(state, bot, "boss_add_density",
                    activeSwarmPickupAnchor,
                    continuingReservedPickup
                        ? "feral_continue_bounded_active_swarm_cluster"
                        : "feral_move_to_bounded_active_swarm_cluster",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(activeSwarmPickupAnchor), addCount);
                state.TargetGuid = activeSwarmPickupAnchor->GetGUID();
                target = activeSwarmPickupAnchor;
                situation = "dungeon_boss";
                action = continuingReservedPickup
                    ? "continue_bounded_active_swarm_cluster"
                    : "move_to_bounded_active_swarm_cluster";
                return true;
            }

            state.FeralActiveSwarmPickupAnchorGuid.Clear();
            state.FeralActiveSwarmPickupUntilMs = 0;
            state.FeralActiveSwarmPickupArrived = false;
        }
    }

    // Keep the healer stationary while the Feral closes to its stable
    // pickup anchor. Rerun58 rejected pursuing successive remote clusters:
    // it did not clear the role gates and lost the prior death-free result.
    if (role == "tank" && profile.SpecTag == "feral_druid_tank"
        && !feralChargePickupArrived && densityDefenseTarget
        && std::string(manager.GetDungeonRole(densityDefenseTarget)) == "healer"
        && observedListedAttackerCount(densityDefenseTarget) >= 3
        && bot->GetExactDist2d(densityDefenseTarget) > 6.0f
        && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
    {
        constexpr float anchorDestinationEpsilon = 0.1f;
        bool continuingAnchorPath = state.ActivePathValid && state.IsMoving
            && std::fabs(state.ActivePathToX - densityDefenseTarget->GetPositionX())
                <= anchorDestinationEpsilon
            && std::fabs(state.ActivePathToY - densityDefenseTarget->GetPositionY())
                <= anchorDestinationEpsilon
            && std::fabs(state.ActivePathToZ - densityDefenseTarget->GetPositionZ())
                <= anchorDestinationEpsilon;
        bool moved = manager.MoveBotToPoint(state, bot,
            densityDefenseTarget->GetPositionX(),
            densityDefenseTarget->GetPositionY(),
            densityDefenseTarget->GetPositionZ());
        std::string raw = manager.BuildRawJson(bot, densityDefenseTarget);
        std::string semantic = manager.BuildSemanticJson(
            bot, densityDefenseTarget, "dungeon_boss", &power,
            request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_add_density", densityDefenseTarget,
            continuingAnchorPath
                ? "feral_continue_to_stationary_healer_swarm_pickup"
                : (moved ? "feral_move_to_stationary_healer_swarm_pickup"
                         : "feral_stationary_healer_swarm_pickup_path_rejected"),
            raw.c_str(), semantic.c_str(),
            bot->GetExactDist2d(densityDefenseTarget),
            float(observedListedAttackerCount(densityDefenseTarget)));
        state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
        target = add;
        situation = "dungeon_boss";
        action = continuingAnchorPath
            ? "continue_to_stationary_healer_swarm_pickup"
            : (moved ? "move_to_stationary_healer_swarm_pickup"
                     : "hold_stationary_healer_swarm_pickup");
        return true;
    }

    return false;
}

bool TryFeralActiveSwarmMovement(
    FeralActiveSwarmMovementRequest const& request)
{
    return Context::Run(request);
}
}
