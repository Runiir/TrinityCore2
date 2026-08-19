#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveOpeningActions.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "ObjectAccessor.h"
#include "Player.h"
#include "Spell.h"
#include "Unit.h"

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrSpellSemantics::NowMs;

bool Context::Run(AddWaveOpeningActionsRequest const& request)
{
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;

    Unit* add = density.Add;
    bool cohortSwarmActive = discovery.CohortSwarmActive;
    uint32 engagedAddCount = discovery.EngagedAddCount;
    uint32 addCount = discovery.AddCount;
    std::string const& role = density.Role;
    BotClassSpecActionProfile const& profile = density.Profile;
    Player* densityHealer = density.DensityHealer;
    bool densityTankOwnsSecureMajority =
        density.DensityTankOwnsSecureMajority;
    std::function<size_t(Player const*)> const& observedListedAttackerCount =
        density.ObservedListedAttackerCount;

    // A passive follower cluster can flicker across the local visibility
    // boundary while the tank is prepositioning at its spawn. Preserve the
    // accepted move for a short bounded interval so ordinary route movement
    // cannot pull the tank away between observations. Rerun68 proved that
    // clearing it immediately on engagement loses a prepositioned large
    // wave, so hand the same anchor through one 2.5-second engaged interval.
    uint64 pendingSwarmPickupNowMs = NowMs();
    bool tankPendingSwarmPickup = role == "tank"
        && state.TankPendingSwarmPickupUntilMs > pendingSwarmPickupNowMs
        && !state.TankPendingSwarmPickupAnchorGuid.IsEmpty();
    Unit* pendingSwarmPickupAnchor = nullptr;
    if (tankPendingSwarmPickup)
    {
        pendingSwarmPickupAnchor = ObjectAccessor::GetUnit(
            *bot, state.TankPendingSwarmPickupAnchorGuid);
        if (!pendingSwarmPickupAnchor || !pendingSwarmPickupAnchor->IsAlive()
            || pendingSwarmPickupAnchor->GetMap() != bot->GetMap())
        {
            state.TankPendingSwarmPickupAnchorGuid.Clear();
            state.TankPendingSwarmPickupUntilMs = 0;
            state.TankPendingSwarmPickupEngagedHandoff = false;
            tankPendingSwarmPickup = false;
            pendingSwarmPickupAnchor = nullptr;
        }
        else if (engagedAddCount >= 3
            && !state.TankPendingSwarmPickupEngagedHandoff)
        {
            state.TankPendingSwarmPickupEngagedHandoff = true;
            state.TankPendingSwarmPickupUntilMs =
                pendingSwarmPickupNowMs + 2500;
        }
    }
    else if (!state.TankPendingSwarmPickupAnchorGuid.IsEmpty()
        || state.TankPendingSwarmPickupUntilMs)
    {
        state.TankPendingSwarmPickupAnchorGuid.Clear();
        state.TankPendingSwarmPickupUntilMs = 0;
        state.TankPendingSwarmPickupEngagedHandoff = false;
    }
    // Rerun156 exposed a declared 60-follower Feral wave whose first
    // actionable decision was consumed by the older passive preposition
    // reservation. Once that wave is active and still has no healer
    // attackers, release only the stale movement ownership so this same
    // decision reaches the existing native Charge, Roar, and area paths.
    bool feralActiveWavePreemptsPendingSwarmPickup =
        tankPendingSwarmPickup && role == "tank"
        && profile.SpecTag == "feral_druid_tank"
        && engagedAddCount >= 12 && densityHealer
        && observedListedAttackerCount(densityHealer) == 0;
    if (feralActiveWavePreemptsPendingSwarmPickup)
    {
        state.TankPendingSwarmPickupAnchorGuid.Clear();
        state.TankPendingSwarmPickupUntilMs = 0;
        state.TankPendingSwarmPickupEngagedHandoff = false;
        tankPendingSwarmPickup = false;
        pendingSwarmPickupAnchor = nullptr;
    }
    if (tankPendingSwarmPickup && pendingSwarmPickupAnchor
        && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
    {
        bool engagedHandoff =
            state.TankPendingSwarmPickupEngagedHandoff;
        bool insidePickup = bot->GetExactDist2d(pendingSwarmPickupAnchor)
            <= (engagedHandoff ? 10.0f : 6.0f);
        if (insidePickup)
        {
            bot->StopMoving();
            if (engagedHandoff)
            {
                state.TankPendingSwarmPickupAnchorGuid.Clear();
                state.TankPendingSwarmPickupUntilMs = 0;
                state.TankPendingSwarmPickupEngagedHandoff = false;
            }
            // Reaching the anchor completes movement ownership. Continue
            // through the ordinary encounter resolver on this decision so
            // a passive precursor cannot turn a bounded reservation into
            // an unbounded boss-progress hold.
        }
        else
        {
            bool moved = manager.MoveBotToPoint(state, bot,
                pendingSwarmPickupAnchor->GetPositionX(),
                pendingSwarmPickupAnchor->GetPositionY(),
                pendingSwarmPickupAnchor->GetPositionZ());
            std::string raw = manager.BuildRawJson(bot, pendingSwarmPickupAnchor);
            std::string semantic = manager.BuildSemanticJson(
                bot, pendingSwarmPickupAnchor, "dungeon_boss",
                &power, request.Stage, request.Activity);
            manager.RecordEvent(state, bot, "boss_add_density",
                pendingSwarmPickupAnchor,
                moved ? "tank_continue_pending_swarm_pickup_preposition"
                      : "tank_pending_swarm_pickup_path_rejected",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(pendingSwarmPickupAnchor), addCount);
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = moved ? "continue_pending_swarm_pickup_preposition"
                           : "hold_pending_swarm_pickup_path_rejected";
            return true;
        }
    }

    // Fade before the first healing tick after a newly activated wave
    // reaches the priest.  Do not spend the native cooldown while the
    // healer has no listed attackers: rerun80 showed that an early
    // zero-exposure cast left Fade unavailable for the actual Azil wave.
    // Keep the ordinary reactive Fade in tryRouteGroupHeal for smaller
    // pulls, but use it here while a listed swarm is not yet securely
    // owned by the tank.
    bool healerWaveFadeReady = role == "healer" && cohortSwarmActive
        && observedListedAttackerCount(bot) > 0
        && !densityTankOwnsSecureMajority
        && bot->HasSpell(586) && !bot->HasAura(586);
    // Rerun104's first 60-follower wave reached the healer while Smite was
    // still in flight. The existing preemptive Fade could not submit until
    // the following healer decision, which left eight identities beyond
    // the hard dwell gate. Interrupt only a harmful cast for this declared
    // wave; a positive healing cast remains authoritative.
    if (healerWaveFadeReady)
        if (Spell* currentSpell = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            if (!currentSpell->IsPositive())
                bot->InterruptNonMeleeSpells(false);
    if (healerWaveFadeReady && !bot->HasUnitState(UNIT_STATE_CASTING)
        && manager.TryCastFriendlySpell(bot, bot, 586))
    {
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(
            bot, add, "dungeon_boss", &power,
            request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_adds", bot,
            "fade_preemptive_add_wave_threat_drop",
            raw.c_str(), semantic.c_str(),
            float(observedListedAttackerCount(bot)), addCount, 586);
        state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
        target = add;
        situation = "dungeon_boss";
        action = "fade_preemptive_add_wave_threat_drop";
        return true;
    }

    return false;
}

bool TryAddWaveOpeningActions(
    AddWaveOpeningActionsRequest const& request)
{
    return Context::Run(request);
}
}
