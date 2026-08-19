#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilFeralLocalRetention.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Creature.h"
#include "Entities/Object/Position.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrSpellSemantics::NowMs;

bool Context::Run(FeralLocalRetentionRequest const& request)
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
    std::vector<Creature*> const& localAdds = discovery.LocalAdds;
    std::function<size_t(Player const*)> const& observedListedAttackerCount =
        density.ObservedListedAttackerCount;
    uint32 addCount = discovery.AddCount;
    auto const& tryFeralRoarPickup = feralHandoff.TryFeralRoarPickup;
    Unit* feralHealerHandoffAnchor =
        feralHandoff.FeralHealerHandoffAnchor;
    bool feralHealerHandoffActive =
        feralHandoff.FeralHealerHandoffActive;
    bool feralHealerHandoffArrived =
        feralHandoff.FeralHealerHandoffArrived;

    // Rerun171 completed all fourteen route nodes and all four bosses, but
    // Azil follower waves remained on the healer for up to 4108 ms while
    // this arrived handoff waited for another non-damaging Roar. Match the
    // already-proved ordinary-trash recovery: when the local healer-owned
    // set covers a majority of the current wave, submit one native Swipe
    // before retrying Roar. Rerun190 then proved the same damaging pickup
    // was still restricted to an already-active, arrived handoff: fresh
    // local waves instead spent the first legal GCD on Roar, and partial
    // pickup left six generation-14 identities beyond the strict dwell
    // ceiling. Admit the same majority proof before a handoff starts while
    // preserving remote handoff movement until arrival. A rejected cast
    // changes no state and falls through; native GCD, power, range, LOS,
    // target, and threat semantics remain authoritative.
    Creature* localHealerOwnedSwipeTarget = nullptr;
    uint32 localHealerOwnedSwipeCount = 0;
    float localHealerOwnedSwipeDistance =
        std::numeric_limits<float>::max();
    uint32 localHealerOwnedSwipeGuid =
        std::numeric_limits<uint32>::max();
    bool localHealerOwnedSwipeWindow = role == "tank"
        && profile.SpecTag == "feral_druid_tank" && densityHealer
        && (!feralHealerHandoffActive || feralHealerHandoffArrived);
    if (localHealerOwnedSwipeWindow)
        for (Creature* candidate : localAdds)
            if (candidate && candidate->GetVictim() == densityHealer
                && bot->GetExactDist2d(candidate) <= 10.0f)
            {
                ++localHealerOwnedSwipeCount;
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!localHealerOwnedSwipeTarget
                    || distance < localHealerOwnedSwipeDistance
                    || (distance == localHealerOwnedSwipeDistance
                        && guid < localHealerOwnedSwipeGuid))
                {
                    localHealerOwnedSwipeTarget = candidate;
                    localHealerOwnedSwipeDistance = distance;
                    localHealerOwnedSwipeGuid = guid;
                }
            }
    uint32 healerOwnedBeforeHandoffSwipe = densityHealer
        ? uint32(observedListedAttackerCount(densityHealer)) : 0;
    bool localHealerOwnedMajority = localHealerOwnedSwipeCount >= 2
        && localHealerOwnedSwipeCount * 2
            >= healerOwnedBeforeHandoffSwipe;
    // Rerun204 proved that the fresh local-majority Thrash gate preserves
    // retention and exposure, but its final Azil wave first exposed a
    // useful local minority: twelve followers still owned the healer and
    // at least two were inside the native area envelope. The existing
    // large-wave Roar gate accepted that exact topology, then its global
    // cooldown occupied the arrived handoff until only GUID 744 remained;
    // the lingering Swipe cleared it after 3338 ms. Give persistent native
    // Thrash the same already-proved fresh large-wave local-cluster scope
    // before Roar. Smaller fresh minorities, remote clusters, and every
    // native cooldown, GCD, power, range, LOS, target, threat, movement,
    // and hazard gate retain their existing behavior.
    bool freshLargeLocalHealerCluster = !feralHealerHandoffActive
        && healerOwnedBeforeHandoffSwipe >= 12
        && localHealerOwnedSwipeCount >= 2;
    // Rerun198's second failing Azil subwave reached its identity-bound,
    // arrived handoff in 766 ms, but the first damaging GCD used Swipe.
    // Seven followers still owned the healer until the handoff expired;
    // the later native Thrash completed pickup only after 3324 ms. Prefer
    // that same persistent native area threat on an already-arrived
    // handoff, retaining Swipe below whenever Thrash is unavailable.
    // Rerun199 then reached the same arrived handoff with a real local
    // healer-owned target that was not a majority. The majority guard
    // skipped Thrash, a second non-damaging Roar consumed the GCD, and four
    // continuous identities remained on the healer for 3335 ms. An active,
    // arrived, healer-identity-bound handoff already proves the narrow
    // scope; allow its exact local target to receive native Thrash while
    // fresh waves and the Swipe fallback retain the majority guard.
    // Rerun203 proved the ordinary-trash Thrash correction was effective:
    // generation 13 retained every eligible hostile and the run-wide
    // healer exposure fell to 3/1766. Its only remaining failure was a
    // fresh Azil local-majority wave. Native Swipe recovered five of seven
    // healer-owned followers, but the remaining pair moved outside the
    // melee-area envelope; repeated out-of-range density selections then
    // delayed Growl and a second Swipe until GUID 719 reached 3603 ms.
    // The last accepted Thrash was 27 seconds earlier, yet this fresh-wave
    // gate offered only Swipe. Match the now-proved ordinary recovery by
    // preferring persistent native Thrash for this same exact local-
    // majority proof, while retaining the existing arrived-handoff scope
    // and unchanged Swipe fallback. Native spell, cooldown, GCD, power,
    // range, LOS, target, threat, movement, and hazard gates remain final.
    if (localHealerOwnedSwipeTarget
        && ((feralHealerHandoffActive && feralHealerHandoffArrived)
            || localHealerOwnedMajority
            || freshLargeLocalHealerCluster)
        && healerOwnedBeforeHandoffSwipe >= 2
        && bot->HasSpell(77758)
        && manager.TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758))
    {
        std::string raw = manager.BuildRawJson(bot, localHealerOwnedSwipeTarget);
        std::string semantic = manager.BuildSemanticJson(
            bot, localHealerOwnedSwipeTarget, "dungeon_boss",
            &power, request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_add_density",
            localHealerOwnedSwipeTarget,
            "feral_thrash_healer_swarm_retention_before_roar",
            raw.c_str(), semantic.c_str(),
            float(localHealerOwnedSwipeCount),
            float(healerOwnedBeforeHandoffSwipe), 77758);
        state.TargetGuid = localHealerOwnedSwipeTarget->GetGUID();
        target = localHealerOwnedSwipeTarget;
        situation = "dungeon_boss";
        action = "feral_thrash_healer_swarm_retention_before_roar";
        state.WasInCombat = true;
        state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);
        return true;
    }
    if (localHealerOwnedSwipeTarget && bot->HasSpell(779)
        && localHealerOwnedMajority
        && manager.TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779))
    {
        std::string raw = manager.BuildRawJson(bot, localHealerOwnedSwipeTarget);
        std::string semantic = manager.BuildSemanticJson(
            bot, localHealerOwnedSwipeTarget, "dungeon_boss",
            &power, request.Stage, request.Activity);
        manager.RecordEvent(state, bot, "boss_add_density",
            localHealerOwnedSwipeTarget,
            "feral_swipe_healer_swarm_retention_before_roar",
            raw.c_str(), semantic.c_str(),
            float(localHealerOwnedSwipeCount),
            float(healerOwnedBeforeHandoffSwipe), 779);
        state.TargetGuid = localHealerOwnedSwipeTarget->GetGUID();
        target = localHealerOwnedSwipeTarget;
        situation = "dungeon_boss";
        action = "feral_swipe_healer_swarm_retention_before_roar";
        state.WasInCombat = true;
        state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);
        return true;
    }

    // Rerun163 reached its identity-bound remote handoff after the first
    // native Roar, but the post-Roar damage resolver consumed the first
    // available global cooldown before the existing second-Roar resolver.
    // Retry that unchanged native pickup first only after the same bounded
    // handoff has arrived. If the cast is unavailable or illegal, fall
    // through to the established damage-retention and movement paths.
    if (feralHealerHandoffActive && feralHealerHandoffArrived
        && tryFeralRoarPickup(true))
        return true;

    // Rerun144 proved that a successful local Roar can cover a useful
    // healer-owned majority, then return into the specialized handoff and
    // Roar paths for longer than the strict dwell budget without landing
    // damaging area threat. Once that exact local coverage is visible,
    // give the existing strict area-only profile resolver one decision
    // before any further handoff movement or Roar. Native GCD, cooldown,
    // power, range, LOS, target, and threat semantics remain authoritative.
    // Rerun147 proved the original coverage scan was contradictory: a
    // follower affected by Roar normally stops targeting the healer, so
    // requiring both states rejected every successful local cast. The
    // identity-bound active handoff and remaining healer attackers keep
    // this correction limited to the intended post-Roar window.
    uint32 localRoarCoveredCount = 0;
    Creature* postRoarAreaTarget = nullptr;
    float postRoarAreaDistance = std::numeric_limits<float>::max();
    uint32 postRoarAreaGuid = std::numeric_limits<uint32>::max();
    if (role == "tank" && profile.SpecTag == "feral_druid_tank"
        && densityHealer)
        for (Creature* candidate : localAdds)
            if (candidate && bot->GetExactDist2d(candidate) <= 10.0f
                && candidate->HasAura(99, bot->GetGUID()))
            {
                ++localRoarCoveredCount;
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!postRoarAreaTarget || distance < postRoarAreaDistance
                    || (distance == postRoarAreaDistance
                        && guid < postRoarAreaGuid))
                {
                    postRoarAreaTarget = candidate;
                    postRoarAreaDistance = distance;
                    postRoarAreaGuid = guid;
                }
            }
    uint32 healerOwnedAfterRoar = densityHealer
        ? uint32(observedListedAttackerCount(densityHealer)) : 0;
    // Rerun181 showed this resolver could spend native Swipe and its GCD
    // on already-owned local followers while the remaining healer-owned
    // cluster was still remote. Preserve its post-arrival retention role,
    // but leave pre-arrival movement and Charge authoritative so the
    // healer-owned Swipe-before-Roar path can own the first arrived GCD.
    bool postRoarAreaThreatReady = feralHealerHandoffActive
        && feralHealerHandoffArrived
        && healerOwnedAfterRoar >= 2 && postRoarAreaTarget
        && localRoarCoveredCount >= 2
        && localRoarCoveredCount * 2 >= healerOwnedAfterRoar;
    if (postRoarAreaThreatReady)
    {
        ResolvedCombatAction postRoarAreaThreat =
            manager.ResolveProfileCombatAction(
                bot, postRoarAreaTarget, addCount, true, 0, true);
        if (postRoarAreaThreat.Valid)
        {
            BotActionResult postRoarAreaResult =
                manager.ExecuteProfileCombatAction(
                    &state, bot, postRoarAreaTarget, &postRoarAreaThreat,
                    addCount, true, 0, true);
            if (postRoarAreaResult == BotActionResult::Ok
                || postRoarAreaResult == BotActionResult::Casting
                || postRoarAreaResult == BotActionResult::GlobalCooldown)
            {
                char const* postRoarAction =
                    postRoarAreaResult == BotActionResult::Ok
                        ? "feral_post_roar_area_threat_retention"
                        : "feral_hold_post_roar_area_threat_retention";
                std::string raw = manager.BuildRawJson(
                    bot, postRoarAreaTarget);
                std::string semantic = manager.BuildSemanticJson(
                    bot, postRoarAreaTarget, "dungeon_boss",
                    &power, request.Stage, request.Activity);
                manager.RecordEvent(state, bot, "boss_add_density",
                    postRoarAreaTarget, postRoarAction,
                    raw.c_str(), semantic.c_str(),
                    float(localRoarCoveredCount),
                    float(healerOwnedAfterRoar),
                    postRoarAreaResult == BotActionResult::Ok
                        ? postRoarAreaThreat.SpellId : 0);
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                state.TargetGuid = postRoarAreaTarget->GetGUID();
                state.WasInCombat = true;
                target = postRoarAreaTarget;
                situation = "dungeon_boss";
                action = postRoarAction;
                return true;
            }
        }
    }

    if (feralHealerHandoffActive)
    {
        // Rerun106 isolated two Azil split waves whose successful local
        // Roar was followed by 3.5-4.6 seconds of ground movement. The
        // ordinary Charge branch below was suppressed solely because this
        // identity-bound post-Roar handoff was active. Reuse native Charge
        // against that same validated remote anchor before continuing the
        // ground path. Exact hazard handling has already run and remains
        // authoritative; cooldown, range, casting, falling, target, and
        // the existing 2.5-second Charge reservation stay unchanged.
        if (!feralHealerHandoffArrived
            && state.FeralHealerThreatHandoffRemoteCluster
            && bot->GetExactDist(feralHealerHandoffAnchor) > 8.0f
            && bot->HasSpell(16979)
            && !bot->HasUnitState(UNIT_STATE_CASTING)
            && !bot->IsFalling()
            && manager.TryCastCombatSpell(bot, feralHealerHandoffAnchor, 16979))
        {
            std::string raw = manager.BuildRawJson(
                bot, feralHealerHandoffAnchor);
            std::string semantic = manager.BuildSemanticJson(
                bot, feralHealerHandoffAnchor, "dungeon_boss",
                &power, request.Stage, request.Activity);
            manager.RecordEvent(state, bot, "boss_add_density",
                feralHealerHandoffAnchor,
                "feral_charge_remote_cluster_swarm_handoff",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist(feralHealerHandoffAnchor),
                float(observedListedAttackerCount(densityHealer)), 16979);
            state.FeralChargePickupTargetGuid =
                feralHealerHandoffAnchor->GetGUID();
            state.FeralChargePickupUntilMs = NowMs() + 2500;
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 500);
            state.TargetGuid = feralHealerHandoffAnchor->GetGUID();
            state.WasInCombat = true;
            target = feralHealerHandoffAnchor;
            situation = "dungeon_boss";
            action = "feral_charge_remote_cluster_swarm_handoff";
            return true;
        }
        if (!feralHealerHandoffArrived
            && !bot->HasUnitState(UNIT_STATE_CASTING)
            && !bot->IsFalling())
        {
            Unit* movementAnchor =
                state.FeralHealerThreatHandoffRemoteCluster
                    ? feralHealerHandoffAnchor : densityHealer;
            // Rerun141 left one generation-14 boss-handoff attacker on the
            // healer for 3579 ms. Match the ordinary-trash handoff's proven
            // collision-safe native-Roar range instead of spending the dwell
            // budget walking to the hostile's exact point.
            Position remoteRoarIntercept;
            if (state.FeralHealerThreatHandoffRemoteCluster)
                remoteRoarIntercept =
                    movementAnchor->GetFirstCollisionPosition(
                        8.0f,
                        movementAnchor->GetAngle(bot)
                            - movementAnchor->GetOrientation());
            float movementX =
                state.FeralHealerThreatHandoffRemoteCluster
                    ? remoteRoarIntercept.GetPositionX()
                    : movementAnchor->GetPositionX();
            float movementY =
                state.FeralHealerThreatHandoffRemoteCluster
                    ? remoteRoarIntercept.GetPositionY()
                    : movementAnchor->GetPositionY();
            float movementZ =
                state.FeralHealerThreatHandoffRemoteCluster
                    ? remoteRoarIntercept.GetPositionZ()
                    : movementAnchor->GetPositionZ();
            bool continuingRemotePath =
                state.FeralHealerThreatHandoffRemoteCluster
                && state.ActivePathValid && state.IsMoving
                && movementAnchor->GetExactDist2d(
                    state.ActivePathToX, state.ActivePathToY) <= 10.0f;
            bool moved = continuingRemotePath || manager.MoveBotToPoint(state,
                bot, movementX, movementY, movementZ);
            std::string raw = manager.BuildRawJson(bot, movementAnchor);
            std::string semantic = manager.BuildSemanticJson(
                bot, movementAnchor, "dungeon_boss",
                &power, request.Stage, request.Activity);
            manager.RecordEvent(state, bot, "boss_add_density", movementAnchor,
                moved
                    ? (state.FeralHealerThreatHandoffRemoteCluster
                        ? "feral_continue_remote_cluster_swarm_handoff"
                        : "feral_continue_healer_swarm_handoff")
                    : "feral_healer_swarm_handoff_path_rejected",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(movementAnchor),
                float(observedListedAttackerCount(densityHealer)));
            state.TargetGuid = add
                ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = moved
                ? (state.FeralHealerThreatHandoffRemoteCluster
                    ? "feral_continue_remote_cluster_swarm_handoff"
                    : "feral_continue_healer_swarm_handoff")
                : "feral_hold_healer_swarm_handoff_path_rejected";
            return true;
        }
        if (feralHealerHandoffArrived)
            bot->StopMoving();
    }

    return false;
}

bool TryFeralLocalRetention(
    FeralLocalRetentionRequest const& request)
{
    return Context::Run(request);
}
}
