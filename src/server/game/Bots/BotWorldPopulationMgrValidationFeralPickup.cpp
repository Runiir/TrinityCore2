#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <functional>
#include <limits>
#include <string>
#include <vector>

bool BotWorldPopulationMgr::TryValidationFeralRoarPickup(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action, Unit*& target, std::string const& role,
    BotClassSpecActionProfile const& profile, Player* densityHealer,
    std::vector<Creature*> const& localAdds,
    std::function<size_t(Player const*)> const& observedListedAttackerCount,
    bool activeClusterArrived)
{
            if (role != "tank" || profile.SpecTag != "feral_druid_tank"
                || !densityHealer
                || observedListedAttackerCount(densityHealer) < 3
                || !bot->HasSpell(99))
                return false;

            uint32 nearbyHealerOwnedCount = 0;
            Unit* nearbyHealerOwnedAdd = nullptr;
            float nearbyHealerOwnedDistance = std::numeric_limits<float>::max();
            uint32 nearbyHealerOwnedGuid = std::numeric_limits<uint32>::max();
            for (Creature* candidate : localAdds)
                if (candidate && candidate->GetVictim() == densityHealer
                    && bot->GetExactDist2d(candidate) <= 10.0f)
                {
                    ++nearbyHealerOwnedCount;
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!nearbyHealerOwnedAdd
                        || distance < nearbyHealerOwnedDistance
                        || (distance == nearbyHealerOwnedDistance
                            && guid < nearbyHealerOwnedGuid))
                    {
                        nearbyHealerOwnedAdd = candidate;
                        nearbyHealerOwnedDistance = distance;
                        nearbyHealerOwnedGuid = guid;
                    }
                }

            uint32 healerOwnedCount =
                uint32(observedListedAttackerCount(densityHealer));
            bool centeredOnHealer =
                bot->GetExactDist2d(densityHealer) <= 3.0f;
            bool coversHealerOwnedMajority =
                nearbyHealerOwnedCount * 2 >= healerOwnedCount;
            // Rerun81 reached Azil's 60-follower activation after completing
            // passive medoid prepositioning, but the first active snapshot had
            // fewer than two healer-owned followers inside Roar range.  The
            // ordinary density action consumed that decision and the two-cluster
            // native pickup finished 13 ms after the acquisition gate.  Begin
            // the existing bounded healer handoff immediately when no useful
            // local Roar exists; once followers enter range, the unchanged Roar
            // path below remains authoritative.
            // Rerun180 captured a moderate reservation while eleven Azil
            // followers owned the healer, then the same wave grew to twenty.
            // The large-wave healer anchor and the older moving-hostile anchor
            // alternated for seven decisions, delaying the first native Roar
            // until 2568 ms after exposure. Promote that exact transition to
            // the existing stable healer anchor by retiring only the moderate
            // reservation; hazard movement has already run, and native Charge,
            // Roar, range, cooldown, GCD, and threat rules remain unchanged.
            if (healerOwnedCount >= 12 && nearbyHealerOwnedCount < 2)
            {
                state.FeralActiveSwarmPickupAnchorGuid.Clear();
                state.FeralActiveSwarmPickupUntilMs = 0;
                state.FeralActiveSwarmPickupAttempted = false;
                state.FeralActiveSwarmPickupArrived = false;
            }
            if (healerOwnedCount >= 12 && nearbyHealerOwnedCount < 2
                && !centeredOnHealer
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling()
                && MoveBotToPoint(state, bot,
                    densityHealer->GetPositionX(),
                    densityHealer->GetPositionY(),
                    densityHealer->GetPositionZ()))
            {
                std::string raw = BuildRawJson(bot, densityHealer);
                std::string semantic = BuildSemanticJson(
                    bot, densityHealer, "dungeon_boss",
                    &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density", densityHealer,
                    "feral_move_to_healer_for_split_swarm_pickup",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyHealerOwnedCount),
                    float(healerOwnedCount));
                state.TargetGuid = nearbyHealerOwnedAdd
                    ? nearbyHealerOwnedAdd->GetGUID() : ObjectGuid::Empty;
                target = nearbyHealerOwnedAdd;
                situation = "dungeon_boss";
                action = "feral_move_to_healer_for_split_swarm_pickup";
                return true;
            }
            // Rerun84's final 60-follower wave was already visible from the
            // passive medoid, but waiting one decision for a strict local
            // majority delayed the first Roar until 1009 ms after activation.
            // Rerun94 then exposed the same topology in a 23-follower overlap:
            // ten established local followers flipped to the healer, but a
            // remote Charge preempted their immediately useful Roar. For any
            // large healer-owned wave, acquire a useful local cluster first;
            // the unchanged bounded handoff can then close the remote cluster.
            bool immediateLargeWavePickup =
                healerOwnedCount >= 12 && nearbyHealerOwnedCount >= 2;
            // Rerun102 proved a moderate eight-to-ten-follower wave can have
            // exactly one useful local target while its remote remainder owns
            // the healer. Waiting for two local targets delayed Roar and the
            // already-bounded post-cast healer handoff for 5.5 seconds. Cast on
            // that one legal local target only for a 3-11 follower wave; large
            // waves retain the established two-target coverage guard.
            // Rerun177's only failing dwell was an eleven-healer-owned
            // generation-14 subwave coexisting with four tank-owned followers.
            // Counting the full engaged set as a large healer wave forced the
            // Feral to ground-approach until a local majority was covered, so
            // the first native Roar landed 1.8 seconds after exposure and the
            // second cleared the last follower at 3820 ms. Classify this
            // native pickup by the healer-owned wave itself; a true twelve-plus
            // healer wave still retains the established two-target guard.
            bool immediateModerateWavePickup =
                healerOwnedCount >= 3 && healerOwnedCount < 12
                && nearbyHealerOwnedCount >= 1;
            bool usefulLocalPickup = immediateModerateWavePickup
                || (activeClusterArrived
                    && nearbyHealerOwnedCount >= 1)
                || (nearbyHealerOwnedCount >= 2
                    && (centeredOnHealer || coversHealerOwnedMajority
                        || activeClusterArrived || immediateLargeWavePickup));
            if (usefulLocalPickup
                && TryCastFriendlySpell(bot, bot, 99))
            {
                // Rerun70 showed that split follower clusters can retain the
                // healer for one avoidable decision after an instant Roar. The
                // ordinary stationary-healer pickup below already owns this
                // bounded destination, but previously could not start until
                // the next update because a successful cast returned here.
                // Begin that same legal movement immediately when the pre-cast
                // snapshot proves a remote cluster remains. Rerun103 showed
                // that returning to the healer center cancels an accepted
                // remote-cluster path, so retain a deterministic remote anchor
                // for the bounded post-Roar phase. Hazard movement has already
                // run and remains authoritative.
                bool remoteClusterRemains =
                    nearbyHealerOwnedCount < healerOwnedCount;
                Unit* remoteClusterAnchor = nullptr;
                uint32 remoteClusterCount = 0;
                float remoteClusterDistance =
                    std::numeric_limits<float>::max();
                uint32 remoteClusterGuid =
                    std::numeric_limits<uint32>::max();
                for (Creature* candidate : localAdds)
                {
                    if (!candidate || candidate->GetVictim() != densityHealer
                        || bot->GetExactDist2d(candidate) <= 10.0f)
                        continue;
                    uint32 clusterCount = 0;
                    for (Creature* neighbor : localAdds)
                        if (neighbor && neighbor->GetVictim() == densityHealer
                            && candidate->GetExactDist2d(neighbor) <= 10.0f)
                            ++clusterCount;
                    float distance = bot->GetExactDist(candidate);
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!remoteClusterAnchor
                        || clusterCount > remoteClusterCount
                        || (clusterCount == remoteClusterCount
                            && (distance < remoteClusterDistance
                                || (distance == remoteClusterDistance
                                    && guid < remoteClusterGuid))))
                    {
                        remoteClusterAnchor = candidate;
                        remoteClusterCount = clusterCount;
                        remoteClusterDistance = distance;
                        remoteClusterGuid = guid;
                    }
                }
                // Rerun150 proved the continuation's collision-safe Roar
                // intercept can be bypassed when the successful local cast
                // first accepts an exact-hostile path: the continuation then
                // preserves that destination as already within ten yards of
                // the same anchor until the 2.5-second handoff expires. Start
                // the unchanged identity-bound handoff at its native eight-yard
                // Roar intercept so the first accepted path and every later
                // continuation share the same bounded endpoint.
                Position remoteRoarIntercept;
                if (remoteClusterAnchor)
                    remoteRoarIntercept =
                        remoteClusterAnchor->GetFirstCollisionPosition(
                            8.0f,
                            remoteClusterAnchor->GetAngle(bot)
                                - remoteClusterAnchor->GetOrientation());
                float splitHandoffX = remoteClusterAnchor
                    ? remoteRoarIntercept.GetPositionX()
                    : densityHealer->GetPositionX();
                float splitHandoffY = remoteClusterAnchor
                    ? remoteRoarIntercept.GetPositionY()
                    : densityHealer->GetPositionY();
                float splitHandoffZ = remoteClusterAnchor
                    ? remoteRoarIntercept.GetPositionZ()
                    : densityHealer->GetPositionZ();
                bool splitClusterHandoff = remoteClusterRemains
                    && !bot->HasUnitState(UNIT_STATE_CASTING)
                    && !bot->IsFalling()
                    && MoveBotToPoint(state, bot,
                        splitHandoffX, splitHandoffY, splitHandoffZ);
                if (remoteClusterRemains)
                {
                    state.FeralHealerThreatHandoffTargetGuid =
                        densityHealer->GetGUID();
                    state.FeralHealerThreatHandoffAnchorGuid =
                        remoteClusterAnchor
                            ? remoteClusterAnchor->GetGUID()
                            : ObjectGuid::Empty;
                    state.FeralHealerThreatHandoffUntilMs = NowMs() + 2500;
                    state.FeralHealerThreatHandoffRemoteCluster =
                        remoteClusterAnchor != nullptr;
                }
                else
                {
                    state.FeralHealerThreatHandoffTargetGuid.Clear();
                    state.FeralHealerThreatHandoffAnchorGuid.Clear();
                    state.FeralHealerThreatHandoffUntilMs = 0;
                    state.FeralHealerThreatHandoffRemoteCluster = false;
                }
                std::string raw = BuildRawJson(bot, nearbyHealerOwnedAdd);
                std::string semantic = BuildSemanticJson(
                    bot, nearbyHealerOwnedAdd, "dungeon_boss",
                    &power, stage, activity);
                RecordEvent(state, bot, "boss_add_density",
                    nearbyHealerOwnedAdd,
                    splitClusterHandoff
                        ? "feral_demoralizing_roar_split_swarm_handoff"
                        : "feral_demoralizing_roar_swarm_pickup",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyHealerOwnedCount),
                    float(observedListedAttackerCount(densityHealer)), 99);
                state.TargetGuid = nearbyHealerOwnedAdd
                    ? nearbyHealerOwnedAdd->GetGUID() : ObjectGuid::Empty;
                state.WasInCombat = true;
                target = nearbyHealerOwnedAdd;
                situation = "dungeon_boss";
                action = splitClusterHandoff
                    ? "feral_demoralizing_roar_split_swarm_handoff"
                    : "feral_demoralizing_roar_swarm_pickup";
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                return true;
            }
            return false;
}
