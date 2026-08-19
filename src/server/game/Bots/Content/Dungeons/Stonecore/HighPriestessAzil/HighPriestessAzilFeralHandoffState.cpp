#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilFeralHandoffState.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Creature.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <functional>
#include <limits>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrSpellSemantics::NowMs;

FeralHandoffStateResult Context::Run(
    FeralHandoffStateRequest const& request)
{
    FeralHandoffStateResult result;
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;
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
    uint32 addCount = discovery.AddCount;

    result.TryFeralRoarPickup = [manager = request.Manager,
        state = request.State, bot, power = request.Power,
        stage = request.Stage, activity = request.Activity,
        situation = request.Situation, action = request.Action,
        target = request.Target, role = density.Role, profile = density.Profile,
        densityHealer, localAdds = &discovery.LocalAdds,
        observedListedAttackerCount = density.ObservedListedAttackerCount]
        (bool activeClusterArrived) -> bool
    {
        return manager->TryValidationFeralRoarPickup(*state, bot, *power,
            stage, activity, *situation, *action, *target, role, profile,
            densityHealer, *localAdds, observedListedAttackerCount,
            activeClusterArrived);
    };

    // A successful Feral Charge owns its movement briefly. Issuing MovePoint
    // on the next decision clears MOTION_SLOT_ACTIVE and can cancel the charge
    // before the tank reaches a newly activated follower wave. Preserve the
    // charged target until that target and nearby adds prove arrival, then
    // hand control back to the existing strict self-centered area resolver.
    uint64 feralChargeNowMs = NowMs();
    bool feralChargePickupInFlight = role == "tank"
        && profile.SpecTag == "feral_druid_tank"
        && state.FeralChargePickupUntilMs > feralChargeNowMs
        && !state.FeralChargePickupTargetGuid.IsEmpty();
    Unit* feralChargePickupTarget = nullptr;
    bool feralChargePickupArrived = false;
    if (feralChargePickupInFlight)
    {
        // Rerun148 accepted Charge on the final healer-owned follower, but
        // the next changing local-add snapshot omitted that GUID and
        // cleared the reservation while the same live unit remained in the
        // identity-scoped threat trace. Resolve the exact accepted identity
        // independently of the density snapshot; the original bounded
        // lifetime and native alive/map/attackable gates remain unchanged.
        feralChargePickupTarget = ObjectAccessor::GetUnit(
            *bot, state.FeralChargePickupTargetGuid);
        if (feralChargePickupTarget
            && (!feralChargePickupTarget->IsAlive()
                || feralChargePickupTarget->GetMap() != bot->GetMap()
                || !bot->IsValidAttackTarget(feralChargePickupTarget)))
            feralChargePickupTarget = nullptr;
        if (feralChargePickupTarget)
        {
            add = feralChargePickupTarget;
            sharedFocusValid = false;
        }
        else
        {
            // Rerun126 charged the first Azil follower in 508 ms, but the
            // anchor died on arrival and discarded the accepted movement.
            // Preserve arrival only when a live healer-owned follower is
            // already inside native Roar range; no victim is reassigned.
            Unit* nearbyHealerFollower = nullptr;
            float nearbyHealerFollowerDistance =
                std::numeric_limits<float>::max();
            uint32 nearbyHealerFollowerGuid =
                std::numeric_limits<uint32>::max();
            for (Creature* candidate : localAdds)
                if (candidate && densityHealer
                    && candidate->GetVictim() == densityHealer
                    && bot->GetExactDist2d(candidate) <= 10.0f)
                {
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!nearbyHealerFollower
                        || distance < nearbyHealerFollowerDistance
                        || (distance == nearbyHealerFollowerDistance
                            && guid < nearbyHealerFollowerGuid))
                    {
                        nearbyHealerFollower = candidate;
                        nearbyHealerFollowerDistance = distance;
                        nearbyHealerFollowerGuid = guid;
                    }
                }
            if (nearbyHealerFollower)
            {
                add = nearbyHealerFollower;
                sharedFocusValid = false;
                feralChargePickupArrived = true;
            }
            state.FeralChargePickupTargetGuid.Clear();
            state.FeralChargePickupUntilMs = 0;
            feralChargePickupInFlight = false;
        }
    }
    else if (!state.FeralChargePickupTargetGuid.IsEmpty()
        || state.FeralChargePickupUntilMs)
    {
        state.FeralChargePickupTargetGuid.Clear();
        state.FeralChargePickupUntilMs = 0;
    }

    if (feralChargePickupInFlight && feralChargePickupTarget)
    {
        Unit* nearbyPickupAdd = nullptr;
        float nearbyPickupDistance = std::numeric_limits<float>::max();
        uint32 nearbyPickupAddCount = 0;
        for (Creature* candidate : localAdds)
            if (candidate && bot->GetExactDist2d(candidate) <= 10.0f)
            {
                ++nearbyPickupAddCount;
                float distance = bot->GetExactDist(candidate);
                if (!nearbyPickupAdd || distance < nearbyPickupDistance
                    || (distance == nearbyPickupDistance
                        && candidate->GetGUID().GetCounter()
                            < nearbyPickupAdd->GetGUID().GetCounter()))
                {
                    nearbyPickupAdd = candidate;
                    nearbyPickupDistance = distance;
                }
            }

        if (bot->GetExactDist2d(feralChargePickupTarget) <= 10.0f
            && nearbyPickupAddCount >= 2 && nearbyPickupAdd)
        {
            add = nearbyPickupAdd;
            sharedFocusValid = false;
            feralChargePickupArrived = true;
        }
        else if (bot->GetExactDist2d(feralChargePickupTarget) > 10.0f)
        {
            std::string raw = manager.BuildRawJson(bot, feralChargePickupTarget);
            std::string semantic = manager.BuildSemanticJson(
                bot, feralChargePickupTarget, "dungeon_boss", &power,
                request.Stage, request.Activity);
            manager.RecordEvent(state, bot, "boss_add_density",
                feralChargePickupTarget,
                "feral_charge_swarm_pickup_in_flight",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(feralChargePickupTarget), addCount, 16979);
            state.TargetGuid = feralChargePickupTarget->GetGUID();
            target = feralChargePickupTarget;
            situation = "dungeon_boss";
            action = "feral_charge_swarm_pickup_in_flight";
            result.Handled = true;
            return result;
        }
    }

    // Preserve the bounded post-Roar movement for 2.5 seconds while exact
    // hazard movement above remains authoritative. Rerun103 proved the
    // stationary-healer form must not replace an already accepted path to
    // the remaining remote follower cluster. On arrival, hold through the
    // native Roar GCD instead of walking back to another cluster.
    uint64 feralHealerHandoffNowMs = NowMs();
    Unit* feralHealerHandoffAnchor = nullptr;
    if (!state.FeralHealerThreatHandoffAnchorGuid.IsEmpty())
        feralHealerHandoffAnchor = ObjectAccessor::GetUnit(
            *bot, state.FeralHealerThreatHandoffAnchorGuid);
    // Rerun156 proved the boss handoff discarded a still-valid Azil
    // cluster when Roar transferred the exact anchor but neighboring
    // followers remained healer-owned. Match the proven ordinary-trash
    // behavior: rebind within the original anchor's ten-yard cluster,
    // without changing the existing bounded handoff lifetime.
    if (state.FeralHealerThreatHandoffRemoteCluster && densityHealer
        && feralHealerHandoffAnchor
        && feralHealerHandoffAnchor->IsAlive()
        && feralHealerHandoffAnchor->GetMap() == bot->GetMap()
        && feralHealerHandoffAnchor->GetVictim() != densityHealer
        && state.FeralHealerThreatHandoffUntilMs
            > feralHealerHandoffNowMs)
    {
        Creature* reboundAnchor = nullptr;
        uint32 reboundGuid = std::numeric_limits<uint32>::max();
        for (Creature* candidate : localAdds)
            if (candidate && candidate->IsAlive()
                && candidate->GetMap() == bot->GetMap()
                && candidate->GetVictim() == densityHealer
                && bot->IsValidAttackTarget(candidate)
                && feralHealerHandoffAnchor->GetExactDist2d(candidate)
                    <= 10.0f
                && candidate->GetGUID().GetCounter() < reboundGuid)
            {
                reboundAnchor = candidate;
                reboundGuid = candidate->GetGUID().GetCounter();
            }
        // Rerun186's first Roar started a bounded split-cluster handoff,
        // then a newly listed healer-owned follower appeared outside the
        // original remote anchor's ten-yard cluster. The second Roar
        // transferred that original cluster and invalidated its anchor,
        // leaving the newcomer behind until generic Thrash exceeded the
        // strict dwell bound by 77 ms. Preserve the original-cluster
        // preference above; only when it is empty, rebind the same active,
        // healer-identity-bound handoff to the nearest remaining follower.
        // The original 2.5-second lifetime, native Charge/Roar/area casts,
        // movement, hazard, victim, and threat rules remain unchanged.
        if (!reboundAnchor)
        {
            float reboundDistance = std::numeric_limits<float>::max();
            for (Creature* candidate : localAdds)
                if (candidate && candidate->IsAlive()
                    && candidate->GetMap() == bot->GetMap()
                    && candidate->GetVictim() == densityHealer
                    && bot->IsValidAttackTarget(candidate))
                {
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!reboundAnchor || distance < reboundDistance
                        || (distance == reboundDistance
                            && guid < reboundGuid))
                    {
                        reboundAnchor = candidate;
                        reboundDistance = distance;
                        reboundGuid = guid;
                    }
                }
        }
        if (reboundAnchor)
        {
            state.FeralHealerThreatHandoffAnchorGuid =
                reboundAnchor->GetGUID();
            feralHealerHandoffAnchor = reboundAnchor;
        }
    }
    bool feralHealerRemoteHandoffValid =
        !state.FeralHealerThreatHandoffRemoteCluster
        || (feralHealerHandoffAnchor
            && feralHealerHandoffAnchor->IsAlive()
            && feralHealerHandoffAnchor->GetMap() == bot->GetMap()
            && feralHealerHandoffAnchor->GetVictim() == densityHealer
            && bot->IsValidAttackTarget(feralHealerHandoffAnchor));
    bool feralHealerHandoffActive = role == "tank"
        && profile.SpecTag == "feral_druid_tank"
        && densityHealer
        && state.FeralHealerThreatHandoffUntilMs
            > feralHealerHandoffNowMs
        && state.FeralHealerThreatHandoffTargetGuid
            == densityHealer->GetGUID()
        && feralHealerRemoteHandoffValid
        && observedListedAttackerCount(densityHealer) >= 2;
    if (!feralHealerHandoffActive
        && (!state.FeralHealerThreatHandoffTargetGuid.IsEmpty()
            || !state.FeralHealerThreatHandoffAnchorGuid.IsEmpty()
            || state.FeralHealerThreatHandoffUntilMs
            || state.FeralHealerThreatHandoffRemoteCluster))
    {
        state.FeralHealerThreatHandoffTargetGuid.Clear();
        state.FeralHealerThreatHandoffAnchorGuid.Clear();
        state.FeralHealerThreatHandoffUntilMs = 0;
        state.FeralHealerThreatHandoffRemoteCluster = false;
    }

    bool feralHealerHandoffArrived = false;
    if (feralHealerHandoffActive)
    {
        // Rerun109's Azil episode repeatedly waited on one moving anchor
        // although two other still-unaffected healer followers were
        // already inside native Roar range. Match the corrected ordinary
        // handoff: an unaffected local majority proves bounded arrival,
        // without accepting a minority edge cast for a large wave.
        uint32 localMissingRoarDuringHandoff = 0;
        for (Creature* candidate : localAdds)
            if (candidate && candidate->GetVictim() == densityHealer
                && bot->GetExactDist2d(candidate) <= 10.0f
                && !candidate->HasAura(99, bot->GetGUID()))
                ++localMissingRoarDuringHandoff;
        uint32 healerOwnedDuringHandoff =
            uint32(observedListedAttackerCount(densityHealer));
        bool localMissingRoarCoversMajority =
            localMissingRoarDuringHandoff >= 2
            && localMissingRoarDuringHandoff * 2
                >= healerOwnedDuringHandoff;
        feralHealerHandoffArrived =
            localMissingRoarCoversMajority
            || (state.FeralHealerThreatHandoffRemoteCluster
                ? bot->GetExactDist2d(feralHealerHandoffAnchor) <= 10.0f
                : bot->GetExactDist2d(densityHealer) <= 3.0f);
    }

    result.FeralChargePickupInFlight = feralChargePickupInFlight;
    result.FeralChargePickupTarget = feralChargePickupTarget;
    result.FeralChargePickupArrived = feralChargePickupArrived;
    result.FeralHealerHandoffAnchor = feralHealerHandoffAnchor;
    result.FeralHealerHandoffActive = feralHealerHandoffActive;
    result.FeralHealerHandoffArrived = feralHealerHandoffArrived;
    return result;
}

FeralHandoffStateResult ResolveFeralHandoffState(
    FeralHandoffStateRequest const& request)
{
    return Context::Run(request);
}
}
