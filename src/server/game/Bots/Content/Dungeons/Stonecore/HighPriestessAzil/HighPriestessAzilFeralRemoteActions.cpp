#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilFeralRemoteActions.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrSpellSemantics::NowMs;

bool Context::Run(FeralRemoteActionsRequest const& request)
{
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;
    FeralHandoffStateResult const& feralHandoff = *request.FeralHandoff;
    Unit*& add = *request.Add;
    bool& sharedFocusValid = *request.SharedFocusValid;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;
    std::string const& role = density.Role;
    BotClassSpecActionProfile const& profile = density.Profile;
    Player* densityHealer = density.DensityHealer;
    std::vector<Creature*> const& localAdds = discovery.LocalAdds;
    std::function<size_t(Player const*)> const& observedListedAttackerCount =
        density.ObservedListedAttackerCount;
    uint32 engagedAddCount = discovery.EngagedAddCount;
    uint32 addCount = discovery.AddCount;
    auto const& tryFeralRoarPickup = feralHandoff.TryFeralRoarPickup;
    bool feralChargePickupInFlight =
        feralHandoff.FeralChargePickupInFlight;
    Unit* feralChargePickupTarget =
        feralHandoff.FeralChargePickupTarget;
    bool feralChargePickupArrived =
        feralHandoff.FeralChargePickupArrived;
    bool feralHealerHandoffActive =
        feralHandoff.FeralHealerHandoffActive;
    bool feralHealerHandoffArrived =
        feralHandoff.FeralHealerHandoffArrived;

    // A remote Charge must not abandon a useful local healer-owned cluster.
    // Rerun94 had ten established followers already inside the Feral's Roar
    // radius when a newer remote cluster appeared; charging first turned
    // those already-eligible followers into the entire exposure failure.
    // Resolve only the currently local native area pickup here. If fewer
    // than two are local, fall through to Charge exactly as before.
    uint32 localHealerOwnedBeforeCharge = 0;
    if (!feralChargePickupInFlight && role == "tank"
        && profile.SpecTag == "feral_druid_tank" && densityHealer)
        for (Creature* candidate : localAdds)
            if (candidate && candidate->GetVictim() == densityHealer
                && bot->GetExactDist2d(candidate) <= 10.0f)
                ++localHealerOwnedBeforeCharge;

    // Rerun193 completed every strict route objective, but two moderate
    // Azil waves first exposed the healer while only a minority of their
    // followers were inside native Roar range. The useful local Roar then
    // consumed the first global cooldown and its bounded ground handoff
    // needed another global cooldown to reach the remote majority. Give
    // native Charge one attempt against the densest deterministic remote
    // healer-owned cluster before that minority Roar. If Charge is not
    // ready, legal, or reachable, preserve the existing Roar and movement
    // fallthrough without changing victims or threat.
    uint32 healerOwnedBeforeCharge = densityHealer
        ? uint32(observedListedAttackerCount(densityHealer)) : 0;
    Creature* remoteHealerWaveChargeTarget = nullptr;
    uint32 remoteHealerWaveClusterCount = 0;
    float remoteHealerWaveDistance =
        std::numeric_limits<float>::max();
    uint32 remoteHealerWaveGuid = std::numeric_limits<uint32>::max();
    if (!feralChargePickupInFlight && !feralHealerHandoffActive
        && role == "tank" && profile.SpecTag == "feral_druid_tank"
        && densityHealer && healerOwnedBeforeCharge >= 1
        && localHealerOwnedBeforeCharge * 2 < healerOwnedBeforeCharge)
        for (Creature* candidate : localAdds)
        {
            if (!candidate || candidate->GetVictim() != densityHealer
                || bot->GetExactDist(candidate) <= 8.0f)
                continue;
            uint32 clusterCount = 0;
            for (Creature* neighbor : localAdds)
                if (neighbor && neighbor->GetVictim() == densityHealer
                    && candidate->GetExactDist2d(neighbor) <= 10.0f)
                    ++clusterCount;
            float distance = bot->GetExactDist(candidate);
            uint32 guid = candidate->GetGUID().GetCounter();
            if (!remoteHealerWaveChargeTarget
                || clusterCount > remoteHealerWaveClusterCount
                || (clusterCount == remoteHealerWaveClusterCount
                    && (distance < remoteHealerWaveDistance
                        || (distance == remoteHealerWaveDistance
                            && guid < remoteHealerWaveGuid))))
            {
                remoteHealerWaveChargeTarget = candidate;
                remoteHealerWaveClusterCount = clusterCount;
                remoteHealerWaveDistance = distance;
                remoteHealerWaveGuid = guid;
            }
        }
    if (remoteHealerWaveChargeTarget && bot->HasSpell(16979)
        && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling()
        && manager.TryCastCombatSpell(bot, remoteHealerWaveChargeTarget, 16979))
    {
        std::string raw = manager.BuildRawJson(bot, remoteHealerWaveChargeTarget);
        std::string semantic = manager.BuildSemanticJson(
            bot, remoteHealerWaveChargeTarget, "dungeon_boss",
            &power, request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_add_density",
            remoteHealerWaveChargeTarget,
            "feral_charge_remote_healer_wave_before_roar",
            raw.c_str(), semantic.c_str(), remoteHealerWaveDistance,
            float(healerOwnedBeforeCharge), 16979);
        state.FeralChargePickupTargetGuid =
            remoteHealerWaveChargeTarget->GetGUID();
        state.FeralChargePickupUntilMs = NowMs() + 2500;
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 250);
        state.TargetGuid = remoteHealerWaveChargeTarget->GetGUID();
        state.WasInCombat = true;
        target = remoteHealerWaveChargeTarget;
        situation = "dungeon_boss";
        action = "feral_charge_remote_healer_wave_before_roar";
        return true;
    }
    if (localHealerOwnedBeforeCharge >= 2
        && tryFeralRoarPickup(feralHealerHandoffArrived))
        return true;

    // Feral Charge closes the gap before healing threat can retain a newly
    // activated follower wave beyond the acquisition grace. Reserve it for
    // a healer-owned listed add: rerun76 spent the charge on a non-healer
    // precursor, then overlapping Azil waves retained the healer for 5-7
    // seconds while the cooldown recovered.
    Player* feralChargeVictim = add && add->GetVictim()
        ? add->GetVictim()->ToPlayer() : nullptr;
    bool feralChargeProtectsHealer = feralChargeVictim
        && std::string(manager.GetDungeonRole(feralChargeVictim)) == "healer";
    // Keep Charge reserved from low-density non-healer precursors, but do
    // not force a real party-owned follower wave through a three-second
    // melee approach. Rerun101 observed 16-18 engaged Azil followers on a
    // damage dealer with zero healer attackers; ten identities became
    // acquisition-eligible before the unchanged strict area action reached
    // range. Twelve engaged listed adds prove this is the active wave.
    // Rerun125 observed an activated Azil wave grow from 14 to 17 listed
    // adds with no victim, then assign all 19 to the healer in one tick.
    // The existing high-density reservation rejected Charge solely because
    // the selected add did not have a victim yet.  Treat that pre-victim
    // state as the earliest form of the same declared wave; native Charge
    // still owns range, line-of-sight, cooldown, and target legality.
    bool feralChargeProtectsHighDensityParty = engagedAddCount >= 12
        && densityHealer
        && observedListedAttackerCount(densityHealer) == 0;
    // Rerun154 exposed a declared 20-follower wave whose selected density
    // representative was already inside the eight-yard Charge exclusion.
    // The remaining remote cluster therefore never reached the existing
    // proactive Charge path and nineteen followers selected the healer.
    // Keep the unchanged wave and native cast gates, but select the nearest
    // deterministic remote non-tank-owned follower when the representative
    // itself cannot close that gap. If none exists, preserve the original
    // representative and fallthrough exactly as before.
    Unit* feralChargeTarget = add;
    if (feralChargeProtectsHighDensityParty
        && (!feralChargeTarget
            || bot->GetExactDist(feralChargeTarget) <= 8.0f))
    {
        Creature* remoteChargeTarget = nullptr;
        float remoteChargeDistance = std::numeric_limits<float>::max();
        uint32 remoteChargeGuid = std::numeric_limits<uint32>::max();
        for (Creature* candidate : localAdds)
        {
            if (!candidate || candidate->GetVictim() == bot
                || bot->GetExactDist(candidate) <= 8.0f)
                continue;
            Player* candidateVictim = candidate->GetVictim()
                ? candidate->GetVictim()->ToPlayer() : nullptr;
            if (candidateVictim
                && std::string(manager.GetDungeonRole(candidateVictim)) == "tank")
                continue;
            float distance = bot->GetExactDist(candidate);
            uint32 guid = candidate->GetGUID().GetCounter();
            if (!remoteChargeTarget || distance < remoteChargeDistance
                || (distance == remoteChargeDistance
                    && guid < remoteChargeGuid))
            {
                remoteChargeTarget = candidate;
                remoteChargeDistance = distance;
                remoteChargeGuid = guid;
            }
        }
        if (remoteChargeTarget)
            feralChargeTarget = remoteChargeTarget;
    }
    if (role == "tank" && profile.SpecTag == "feral_druid_tank"
        && engagedAddCount >= 3 && feralChargeTarget
        && (feralChargeProtectsHealer
            || feralChargeProtectsHighDensityParty)
        && !feralHealerHandoffActive
        && feralChargeTarget->GetVictim() != bot
        && bot->GetExactDist(feralChargeTarget) > 8.0f
        && bot->HasSpell(16979)
        && manager.TryCastCombatSpell(bot, feralChargeTarget, 16979))
    {
        std::string raw = manager.BuildRawJson(bot, feralChargeTarget);
        std::string semantic = manager.BuildSemanticJson(
            bot, feralChargeTarget, "dungeon_boss", &power, request.Stage,
            request.Activity);
        manager.RecordEvent(state, bot, "boss_add_density", feralChargeTarget,
            "feral_charge_swarm_pickup", raw.c_str(), semantic.c_str(),
            bot->GetExactDist(feralChargeTarget), addCount, 16979);
        state.FeralChargePickupTargetGuid = feralChargeTarget->GetGUID();
        state.FeralChargePickupUntilMs = NowMs() + 2500;
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 250);
        state.TargetGuid = feralChargeTarget->GetGUID();
        state.WasInCombat = true;
        target = feralChargeTarget;
        situation = "dungeon_boss";
        action = "feral_charge_swarm_pickup";
        return true;
    }

    // Charge either proved arrival above or was unavailable/illegal. Only
    // now may the self-centered native pickup consume this decision.
    if (tryFeralRoarPickup(
            feralHealerHandoffArrived || feralChargePickupArrived))
    {
        if (feralChargePickupArrived)
        {
            state.FeralChargePickupTargetGuid.Clear();
            state.FeralChargePickupUntilMs = 0;
        }
        return true;
    }
    // Rerun93 proved that Charge can reach a healer-owned wave while its
    // global cooldown still prevents the native Roar in that exact arrival
    // decision. Clearing the charged GUID here returned the Feral to generic
    // density movement and let a 19-follower wave retain the healer for
    // 4031 ms. Preserve only the original 2.5-second Charge reservation and
    // retry the existing legal Roar at the established lower cadence.
    if (feralChargePickupArrived && densityHealer
        && observedListedAttackerCount(densityHealer) >= 3)
    {
        bot->StopMoving();
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 500);
        std::string raw = manager.BuildRawJson(bot, feralChargePickupTarget);
        std::string semantic = manager.BuildSemanticJson(
            bot, feralChargePickupTarget, "dungeon_boss",
            &power, request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_add_density",
            feralChargePickupTarget,
            "feral_hold_charge_swarm_arrival_for_roar",
            raw.c_str(), semantic.c_str(),
            bot->GetExactDist2d(feralChargePickupTarget), addCount);
        state.TargetGuid = feralChargePickupTarget->GetGUID();
        target = feralChargePickupTarget;
        situation = "dungeon_boss";
        action = "feral_hold_charge_swarm_arrival_for_roar";
        return true;
    }
    if (feralHealerHandoffActive && feralHealerHandoffArrived)
    {
        // Rerun86's correct Azil two-cluster handoff missed the hard dwell
        // gate by 19 ms because the ordinary one-second cadence observed
        // the second Roar only after 3019 ms. Retry only this already-bound
        // handoff at the runtime's established 500 ms lower decision bound
        // so the next native GCD boundary can be observed without changing
        // movement, target selection, or spell legality.
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 500);
        std::string raw = manager.BuildRawJson(bot, densityHealer);
        std::string semantic = manager.BuildSemanticJson(
            bot, densityHealer, "dungeon_boss",
            &power, request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_add_density", densityHealer,
            "feral_hold_healer_swarm_handoff_for_roar",
            raw.c_str(), semantic.c_str(),
            bot->GetExactDist2d(densityHealer),
            float(observedListedAttackerCount(densityHealer)));
        state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
        target = add;
        situation = "dungeon_boss";
        action = "feral_hold_healer_swarm_handoff_for_roar";
        return true;
    }

    // Once a split wave is down to one healer-owned follower, the Roar
    // resolver is intentionally inactive. Rerun85 let that final follower
    // survive another full decision behind the generic density cycle.
    // Reuse native Growl immediately, matching the existing ordinary-trash
    // single-follower rule.
    if (role == "tank" && profile.SpecTag == "feral_druid_tank"
        && densityHealer
        && observedListedAttackerCount(densityHealer) == 1
        && bot->HasSpell(6795))
    {
        Creature* healerOwnedAdd = nullptr;
        for (Creature* candidate : localAdds)
            if (candidate && candidate->GetVictim() == densityHealer
                && (!healerOwnedAdd
                    || bot->GetExactDist(candidate)
                        < bot->GetExactDist(healerOwnedAdd)
                    || (bot->GetExactDist(candidate)
                            == bot->GetExactDist(healerOwnedAdd)
                        && candidate->GetGUID().GetCounter()
                            < healerOwnedAdd->GetGUID().GetCounter())))
                healerOwnedAdd = candidate;
        if (healerOwnedAdd
            && manager.TryCastCombatSpell(bot, healerOwnedAdd, 6795))
        {
            std::string raw = manager.BuildRawJson(bot, healerOwnedAdd);
            std::string semantic = manager.BuildSemanticJson(
                bot, healerOwnedAdd, "dungeon_boss",
                &power, request.Stage, request.Activity);
            manager.RecordEvent(state, bot, "boss_add_density", healerOwnedAdd,
                "feral_growl_lingering_healer_swarm_attacker",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist(healerOwnedAdd), addCount, 6795);
            state.TargetGuid = healerOwnedAdd->GetGUID();
            target = healerOwnedAdd;
            situation = "dungeon_boss";
            action = "feral_growl_lingering_healer_swarm_attacker";
            return true;
        }
        // Rerun188 reduced Azil's final healer-owned wave to one follower,
        // but native Growl was still on cooldown. The unchanged generic
        // area resolver then selected periodic Thrash at 2842 ms; the
        // follower remained healer-owned at the 3094-ms observation and
        // transferred on the next tick. Try one native instant Swipe on
        // that same deterministic follower before preserving the existing
        // movement/profile fallback. Failed range, GCD, power, cooldown,
        // LOS, or target legality changes no state and falls through.
        if (healerOwnedAdd && bot->HasSpell(779)
            && manager.TryCastCombatSpell(bot, healerOwnedAdd, 779))
        {
            std::string raw = manager.BuildRawJson(bot, healerOwnedAdd);
            std::string semantic = manager.BuildSemanticJson(
                bot, healerOwnedAdd, "dungeon_boss",
                &power, request.Stage, request.Activity);
            manager.RecordEvent(state, bot, "boss_add_density", healerOwnedAdd,
                "feral_swipe_lingering_healer_swarm_attacker",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist(healerOwnedAdd), addCount, 779);
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            state.TargetGuid = healerOwnedAdd->GetGUID();
            state.WasInCombat = true;
            target = healerOwnedAdd;
            situation = "dungeon_boss";
            action = "feral_swipe_lingering_healer_swarm_attacker";
            return true;
        }
        // Rerun164 recovered the first of two Azil followers with Growl,
        // then left the generic density fallback bound to that already
        // tank-owned follower while the sole remaining healer attacker
        // aged past the dwell ceiling. On native Growl rejection, bind
        // only the unchanged fallback target to the same deterministic
        // healer-owned follower. Generic movement, profile resolution,
        // spell legality, and threat semantics remain authoritative.
        if (healerOwnedAdd)
        {
            add = healerOwnedAdd;
            sharedFocusValid = false;
        }
    }

    return false;
}

bool TryFeralRemoteActions(
    FeralRemoteActionsRequest const& request)
{
    return Context::Run(request);
}
}
