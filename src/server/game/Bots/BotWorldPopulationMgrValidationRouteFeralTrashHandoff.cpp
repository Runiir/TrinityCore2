#include "Bots/BotWorldPopulationMgrValidationRouteFeralTrashHandoff.h"

#include "Bots/BotActionArbiter.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Spell.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <string>
#include <utility>
#include <vector>

using BotWorldPopulationMgrSpellSemantics::NowMs;

namespace BotWorldPopulationMgrValidationRoute
{
bool ObjectiveContext::RunFeralTrashHandoff(
    FeralTrashHandoffCallbacks const& callbacks)
{
    WorldBotState& state = State;
    Player* bot = Bot;
    uint64 feralTrashHandoffNowMs = NowMs();
    BotRolePowerBreakdown const& power = Power;
    BotProgressionStage stage = Stage;
    BotProgressionActivity activity = Activity;
    std::string& situation = Situation;
    std::string& action = Action;
    Unit*& target = Target;
    Player* defenseTarget = callbacks.DefenseTarget();
    std::size_t defenseAttackerCount = callbacks.DefenseAttackerCount();
    TrashThreatControlResult const& trashThreatControl =
        callbacks.TrashThreatControlResult();

    auto GetDungeonRole = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.GetDungeonRole(
            std::forward<decltype(args)>(args)...);
    };
    auto BuildRawJson = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.BuildRawJson(
            std::forward<decltype(args)>(args)...);
    };
    auto BuildSemanticJson = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.BuildSemanticJson(
            std::forward<decltype(args)>(args)...);
    };
    auto RecordEvent = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.RecordEvent(
            std::forward<decltype(args)>(args)...);
    };
    auto TryCastFriendlySpell = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.TryCastFriendlySpell(
            std::forward<decltype(args)>(args)...);
    };
    auto TryCastCombatSpell = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.TryCastCombatSpell(
            std::forward<decltype(args)>(args)...);
    };
    auto MoveBotToPoint = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MoveBotToPoint(
            std::forward<decltype(args)>(args)...);
    };

        bool feralTrashHandoffExpired =
            state.FeralHealerThreatHandoffUntilMs
            && state.FeralHealerThreatHandoffUntilMs <= feralTrashHandoffNowMs;
        Unit* feralTrashHandoffAnchor = nullptr;
        if (!state.FeralHealerThreatHandoffAnchorGuid.IsEmpty())
            feralTrashHandoffAnchor = ObjectAccessor::GetUnit(
                *bot, state.FeralHealerThreatHandoffAnchorGuid);
        Unit* feralTrashExpiredHandoffAnchor =
            feralTrashHandoffExpired && feralTrashHandoffAnchor
                && feralTrashHandoffAnchor->IsAlive()
                && feralTrashHandoffAnchor->GetMap() == bot->GetMap()
            ? feralTrashHandoffAnchor : nullptr;
        bool feralTrashExpiredClusterUnresolved = false;
        if (feralTrashExpiredHandoffAnchor && defenseTarget)
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker)
                    && feralTrashExpiredHandoffAnchor->GetExactDist2d(attacker)
                        <= 10.0f)
                {
                    feralTrashExpiredClusterUnresolved = true;
                    break;
                }
        bool feralTrashChargeInFlight = defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && state.FeralChargePickupUntilMs > feralTrashHandoffNowMs
            && !state.FeralChargePickupTargetGuid.IsEmpty();
        Unit* feralTrashChargeTarget = feralTrashChargeInFlight
            ? ObjectAccessor::GetUnit(*bot, state.FeralChargePickupTargetGuid)
            : nullptr;
        bool feralTrashChargeArrived = false;
        if (feralTrashChargeInFlight
            && (!feralTrashChargeTarget || !feralTrashChargeTarget->IsAlive()
                || feralTrashChargeTarget->GetMap() != bot->GetMap()
                || !bot->IsValidAttackTarget(feralTrashChargeTarget)))
        {
            state.FeralChargePickupTargetGuid.Clear();
            state.FeralChargePickupUntilMs = 0;
            feralTrashChargeInFlight = false;
            feralTrashChargeTarget = nullptr;
        }
        else if (feralTrashChargeInFlight
            && bot->GetExactDist2d(feralTrashChargeTarget) > 10.0f)
        {
            std::string raw = BuildRawJson(bot, feralTrashChargeTarget);
            std::string semantic = BuildSemanticJson(
                bot, feralTrashChargeTarget, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                feralTrashChargeTarget,
                "feral_charge_remote_healer_trash_cluster_in_flight",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(feralTrashChargeTarget),
                float(defenseAttackerCount), 16979);
            state.TargetGuid = feralTrashChargeTarget->GetGUID();
            target = feralTrashChargeTarget;
            situation = "normal_dungeon_trash";
            action = "feral_charge_remote_healer_trash_cluster_in_flight";
            state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);
            return true;
        }
        else if (feralTrashChargeInFlight)
            feralTrashChargeArrived = true;
        else if (!state.FeralChargePickupTargetGuid.IsEmpty()
            || state.FeralChargePickupUntilMs)
        {
            state.FeralChargePickupTargetGuid.Clear();
            state.FeralChargePickupUntilMs = 0;
        }
        // Rerun95 also proved that always preserving the densest remote
        // cluster can starve older ranged stragglers behind each new spawn
        // burst. Once the Feral has secured an 80 percent victim majority,
        // keep the same bounded handoff but rebind it deterministically to the
        // lowest-GUID healer-owned follower. This targets the oldest remaining
        // identity without assigning a victim or extending the reservation.
        bool feralTrashOwnsSecureVictimMajority =
            trashThreatControl.EngagedCount > 0
            && trashThreatControl.TankOwnedCount * 10
                >= trashThreatControl.EngagedCount * 8;
        if (feralTrashOwnsSecureVictimMajority && defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && state.FeralHealerThreatHandoffUntilMs > feralTrashHandoffNowMs)
        {
            Unit* oldestHealerAttacker = nullptr;
            uint32 oldestHealerAttackerGuid =
                std::numeric_limits<uint32>::max();
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker)
                    && attacker->GetGUID().GetCounter()
                        < oldestHealerAttackerGuid)
                {
                    oldestHealerAttacker = attacker;
                    oldestHealerAttackerGuid =
                        attacker->GetGUID().GetCounter();
                }
            if (oldestHealerAttacker)
            {
                state.FeralHealerThreatHandoffAnchorGuid =
                    oldestHealerAttacker->GetGUID();
                feralTrashHandoffAnchor = oldestHealerAttacker;
            }
        }
        if (defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && feralTrashHandoffAnchor
            && feralTrashHandoffAnchor->IsAlive()
            && feralTrashHandoffAnchor->GetMap() == bot->GetMap()
            && feralTrashHandoffAnchor->GetVictim() != defenseTarget
            && state.FeralHealerThreatHandoffUntilMs > feralTrashHandoffNowMs)
        {
            // A transfer can flip the selected hostile while neighboring
            // members of the same remote cluster still own the healer. Keep
            // the bounded cluster rendezvous stable by rebinding only within
            // the original anchor's ten-yard neighborhood.
            Unit* reboundAnchor = nullptr;
            uint32 reboundGuid = std::numeric_limits<uint32>::max();
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker)
                    && feralTrashHandoffAnchor->GetExactDist2d(attacker)
                        <= 10.0f
                    && attacker->GetGUID().GetCounter() < reboundGuid)
                {
                    reboundAnchor = attacker;
                    reboundGuid = attacker->GetGUID().GetCounter();
                }
            if (reboundAnchor)
            {
                state.FeralHealerThreatHandoffAnchorGuid =
                    reboundAnchor->GetGUID();
                feralTrashHandoffAnchor = reboundAnchor;
            }
        }
        bool feralTrashHandoffActive = defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && state.FeralHealerThreatHandoffUntilMs > feralTrashHandoffNowMs
            && state.FeralHealerThreatHandoffTargetGuid
                == defenseTarget->GetGUID()
            && feralTrashHandoffAnchor
            && feralTrashHandoffAnchor->IsAlive()
            && feralTrashHandoffAnchor->GetMap() == bot->GetMap()
            && feralTrashHandoffAnchor->GetVictim() == defenseTarget
            && bot->IsValidAttackTarget(feralTrashHandoffAnchor)
            && defenseAttackerCount >= 1;
        if (!feralTrashHandoffActive && !feralTrashExpiredClusterUnresolved
            && (!state.FeralHealerThreatHandoffTargetGuid.IsEmpty()
                || !state.FeralHealerThreatHandoffAnchorGuid.IsEmpty()
                || state.FeralHealerThreatHandoffUntilMs
                || state.FeralHealerThreatHandoffRemoteCluster))
        {
            state.FeralHealerThreatHandoffTargetGuid.Clear();
            state.FeralHealerThreatHandoffAnchorGuid.Clear();
            state.FeralHealerThreatHandoffUntilMs = 0;
            state.FeralHealerThreatHandoffRemoteCluster = false;
            feralTrashHandoffAnchor = nullptr;
        }
        bool feralTrashHandoffArrived = false;
        if (feralTrashHandoffActive)
        {
            // Movement ownership was changed to the collision-safe stationary
            // healer ring after rerun100, but arrival still measured only the
            // remote hostile GUID. Rerun102 accepted sixteen consecutive ring
            // movements without reaching that moving hostile. Complete the
            // same bounded pre-Roar handoff at its actual eight-yard destination
            // while retaining hostile proximity as alternate arrival proof.
            // A post-Roar remote-cluster phase instead owns the hostile anchor;
            // rerun103 proved healer-ring arrival would cancel that accepted
            // path immediately after the cast.
            // Rerun109 proved that the one-local arrival exception fragmented
            // large Flayer packs into 42 small Roars and regressed retention.
            // Do not require the selected moving anchor itself, but require an
            // identity-valid nearby majority still missing this Feral's Roar
            // aura before yielding the accepted handoff to area threat.
            uint32 currentHealerOwnedDuringHandoff = 0;
            uint32 localMissingRoarDuringHandoff = 0;
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker))
                {
                    ++currentHealerOwnedDuringHandoff;
                    if (bot->GetExactDist2d(attacker) <= 10.0f
                        && !attacker->HasAura(99, bot->GetGUID()))
                        ++localMissingRoarDuringHandoff;
                }
            bool localMissingRoarCoversMajority =
                localMissingRoarDuringHandoff >= 2
                && localMissingRoarDuringHandoff * 2
                    >= currentHealerOwnedDuringHandoff;
            // Rerun123's opening corridor reached one isolated remote anchor
            // while all eight hostiles still owned the healer. Anchor distance
            // alone entered six Roar-hold decisions without a useful local
            // cast. A remote handoff now uses the already-proven missing-Roar
            // majority as its sole arrival proof; only the stationary-healer
            // form retains ring/anchor proximity as an alternate proof.
            feralTrashHandoffArrived = localMissingRoarCoversMajority
                || (!state.FeralHealerThreatHandoffRemoteCluster
                    && (bot->GetExactDist2d(defenseTarget) <= 9.0f
                        || bot->GetExactDist2d(feralTrashHandoffAnchor)
                            <= 10.0f));
            if (!feralTrashHandoffArrived
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling())
            {
                // Rerun109 used only eight Charges through a six-minute Flayer
                // node because an active post-Roar handoff returned ground
                // movement before the ordinary Charge branch below.  Reuse
                // native Charge against the already-validated remote anchor;
                // the strict hazard resolver has already run and the existing
                // bounded reservation remains unchanged.
                if (state.FeralHealerThreatHandoffRemoteCluster
                    && bot->GetExactDist(feralTrashHandoffAnchor) > 8.0f
                    && bot->HasSpell(16979)
                    && TryCastCombatSpell(
                        bot, feralTrashHandoffAnchor, 16979))
                {
                    std::string raw = BuildRawJson(
                        bot, feralTrashHandoffAnchor);
                    std::string semantic = BuildSemanticJson(
                        bot, feralTrashHandoffAnchor,
                        "normal_dungeon_trash", &power, stage, activity);
                    RecordEvent(state, bot,
                        "validation_route_threat_pickup",
                        feralTrashHandoffAnchor,
                        "feral_charge_remote_healer_trash_cluster_active_handoff",
                        raw.c_str(), semantic.c_str(),
                        bot->GetExactDist(feralTrashHandoffAnchor),
                        float(defenseAttackerCount), 16979);
                    state.FeralChargePickupTargetGuid =
                        feralTrashHandoffAnchor->GetGUID();
                    state.FeralChargePickupUntilMs = NowMs() + 2500;
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 250);
                    state.TargetGuid = feralTrashHandoffAnchor->GetGUID();
                    state.WasInCombat = true;
                    target = feralTrashHandoffAnchor;
                    situation = "normal_dungeon_trash";
                    action =
                        "feral_charge_remote_healer_trash_cluster_active_handoff";
                    return true;
                }
                // Rerun120 passed the Feral retention floor after the Swipe
                // threat-margin correction, but the exact remote-anchor path
                // still consumed about 3.5 seconds before the first legal
                // Roar. Preserve the proven hostile identity and stable path
                // reservation while stopping inside Roar's collision-safe
                // range. Rerun122 localized its entire remaining exposure to
                // Azil and observed zero healer exposure at the ordinary-trash
                // Flayer node, so retain the original eight-yard stand-off for
                // both rendezvous forms.
                Position roarIntercept;
                if (state.FeralHealerThreatHandoffRemoteCluster)
                    roarIntercept =
                        feralTrashHandoffAnchor->GetFirstCollisionPosition(
                            8.0f,
                            feralTrashHandoffAnchor->GetAngle(bot)
                                - feralTrashHandoffAnchor->GetOrientation());
                else
                    roarIntercept = defenseTarget->GetFirstCollisionPosition(
                        8.0f,
                        defenseTarget->GetAngle(bot)
                            - defenseTarget->GetOrientation());
                bool continuingRemotePath =
                    state.FeralHealerThreatHandoffRemoteCluster
                    && state.ActivePathValid && state.IsMoving
                    && feralTrashHandoffAnchor->GetExactDist2d(
                        state.ActivePathToX, state.ActivePathToY) <= 10.0f;
                bool moved = continuingRemotePath || MoveBotToPoint(state, bot,
                    roarIntercept.GetPositionX(),
                    roarIntercept.GetPositionY(),
                    roarIntercept.GetPositionZ());
                if (moved)
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 250);
                std::string raw = BuildRawJson(bot, feralTrashHandoffAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, feralTrashHandoffAnchor, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    feralTrashHandoffAnchor,
                    moved
                        ? "feral_continue_remote_healer_trash_cluster_handoff"
                        : "feral_remote_healer_trash_cluster_path_rejected",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist2d(feralTrashHandoffAnchor),
                    float(defenseAttackerCount));
                if (!moved)
                {
                    // Keep path rejection fail-closed: end only this bounded
                    // handoff and let the existing legal local threat recovery
                    // below own the same decision. Rerun130 proved that a stale
                    // LastRecoveryResult alone cannot establish this condition.
                    state.FeralHealerThreatHandoffTargetGuid.Clear();
                    state.FeralHealerThreatHandoffAnchorGuid.Clear();
                    state.FeralHealerThreatHandoffUntilMs = 0;
                    state.FeralHealerThreatHandoffRemoteCluster = false;
                }
                else
                {
                    state.TargetGuid = feralTrashHandoffAnchor->GetGUID();
                    target = feralTrashHandoffAnchor;
                    situation = "normal_dungeon_trash";
                    action =
                        "feral_continue_remote_healer_trash_cluster_handoff";
                    return true;
                }
            }
            if (feralTrashHandoffArrived)
                bot->StopMoving();
        }
        // Rerun92 exposed 11-45-hostile split Flayer waves where ordinary
        // ground movement needed three or four decisions before the first
        // remote-cluster Roar. Reuse native Feral Charge before that movement,
        // selecting the deterministic densest healer-owned cluster and
        // preserving the charged target above until arrival. Exact hazard
        // movement already ran and remains the higher authority. Rerun105 also
        // isolated one remote surviving attacker for 4032 ms: out-of-range
        // Growl fell through to ordinary route movement because this bounded
        // Charge path required two attackers. The same identity-safe handoff
        // is valid for that single remote healer attacker.
        // Rerun127 showed that selecting another remote anchor immediately
        // after Charge can bypass the nearby Roar/arrival hold below.
        // Rerun130 then showed that reacquiring the just-expired cluster can
        // join nominally bounded handoffs into one longer ownership interval.
        // Rerun131 proved that blocking every selector on expiry instead hands
        // large Flayer waves to fragmenting local Roar/density recovery.
        // Rerun133 proved distinct anchors can still chain while the previously
        // reserved cluster remains healer-owned. Yield only while that exact
        // expired cluster is unresolved; genuinely distinct clusters become
        // eligible again as soon as its current-victim identities clear.
        if (!feralTrashHandoffActive && !feralTrashChargeArrived
            && !feralTrashExpiredClusterUnresolved && defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && defenseAttackerCount >= 1 && bot->HasSpell(16979))
        {
            Unit* chargeAnchor = nullptr;
            uint32 chargeClusterCount = 0;
            float chargeDistance = std::numeric_limits<float>::max();
            uint32 chargeGuid = std::numeric_limits<uint32>::max();
            bool chargeAnchorInNativeBand = false;
            for (Unit* candidate : defenseTarget->getAttackers())
            {
                if (!candidate || !candidate->IsAlive()
                    || candidate->GetMap() != bot->GetMap()
                    || candidate->GetVictim() != defenseTarget
                    || !bot->IsValidAttackTarget(candidate))
                    continue;
                if (feralTrashExpiredHandoffAnchor
                    && feralTrashExpiredHandoffAnchor->GetExactDist2d(candidate)
                        <= 10.0f)
                    continue;
                float distance = bot->GetExactDist(candidate);
                if (distance <= 8.0f)
                    continue;
                uint32 clusterCount = 0;
                for (Unit* neighbor : defenseTarget->getAttackers())
                    if (neighbor && neighbor->IsAlive()
                        && neighbor->GetMap() == bot->GetMap()
                        && neighbor->GetVictim() == defenseTarget
                        && bot->IsValidAttackTarget(neighbor)
                        && candidate->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                bool candidateInNativeChargeBand = false;
                if (SpellInfo const* chargeInfo =
                        sSpellMgr->GetSpellInfo(16979))
                    candidateInNativeChargeBand =
                        bot->IsWithinLOSInMap(candidate)
                        && distance <= bot->GetSpellMaxRangeForTarget(
                            candidate, chargeInfo);
                uint32 guid = candidate->GetGUID().GetCounter();
                bool sameChargeBand = candidateInNativeChargeBand
                    == chargeAnchorInNativeBand;
                bool betterClusterCandidate =
                    clusterCount > chargeClusterCount
                    || (clusterCount == chargeClusterCount
                        && (distance < chargeDistance
                            || (distance == chargeDistance
                                && guid < chargeGuid)));
                if (!chargeAnchor
                    || (candidateInNativeChargeBand
                        && !chargeAnchorInNativeBand)
                    || (sameChargeBand && betterClusterCandidate))
                {
                    chargeAnchor = candidate;
                    chargeClusterCount = clusterCount;
                    chargeDistance = distance;
                    chargeGuid = guid;
                    chargeAnchorInNativeBand =
                        candidateInNativeChargeBand;
                }
            }
            if (chargeAnchor
                && TryCastCombatSpell(bot, chargeAnchor, 16979))
            {
                std::string raw = BuildRawJson(bot, chargeAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, chargeAnchor, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    chargeAnchor,
                    "feral_charge_remote_healer_trash_cluster_handoff",
                    raw.c_str(), semantic.c_str(), chargeDistance,
                    float(defenseAttackerCount), 16979);
                state.FeralChargePickupTargetGuid = chargeAnchor->GetGUID();
                state.FeralChargePickupUntilMs = NowMs() + 2500;
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                state.TargetGuid = chargeAnchor->GetGUID();
                state.WasInCombat = true;
                target = chargeAnchor;
                situation = "normal_dungeon_trash";
                action = "feral_charge_remote_healer_trash_cluster_handoff";
                return true;
            }
            // Rerun96 first observed ten healer-owned followers immediately
            // after strict hazard movement, while Charge was on cooldown and
            // fewer than two followers were inside Roar range. Falling through
            // to generic density movement delayed the first legal Roar to 3014
            // ms. Rerun132 then showed that hazard handling can consume 1522 ms
            // before this fallback, after which a fresh 2.5-second reservation
            // delays the first Roar beyond the per-hostile dwell ceiling. Bind
            // the already-selected deterministic cluster for one second at the
            // existing 250-ms arrival cadence; strict hazard movement has already
            // run and path rejection still falls through without changing victims
            // or extending the reservation.
            if (chargeAnchor
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling())
            {
                // Rerun104 proved the healer-ring fallback can declare arrival
                // with only two of thirteen attackers in Roar range. The
                // post-Roar remote phase now preserves an accepted endpoint;
                // use that same proven contract before the first Roar so the
                // selected densest cluster, rather than the healer ring, owns
                // the bounded rendezvous. Rerun120 proved that walking to the
                // anchor's exact point spends the dwell budget unnecessarily;
                // the native Roar needs only this collision-safe stand-off.
                // Rerun121 reduced the global dwell maximum to 3026 ms at
                // eight yards; use nine yards to remove only that final yard
                // of travel while remaining inside Roar's ten-yard range.
                Position roarIntercept =
                    chargeAnchor->GetFirstCollisionPosition(
                        9.0f,
                        chargeAnchor->GetAngle(bot)
                            - chargeAnchor->GetOrientation());
                bool movedToRemoteCluster = MoveBotToPoint(state, bot,
                        roarIntercept.GetPositionX(),
                        roarIntercept.GetPositionY(),
                        roarIntercept.GetPositionZ());
                if (movedToRemoteCluster)
                {
                    state.FeralHealerThreatHandoffTargetGuid =
                        defenseTarget->GetGUID();
                    state.FeralHealerThreatHandoffAnchorGuid =
                        chargeAnchor->GetGUID();
                    state.FeralHealerThreatHandoffUntilMs =
                        feralTrashHandoffNowMs + 1000;
                    state.FeralHealerThreatHandoffRemoteCluster = true;
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 250);
                    std::string raw = BuildRawJson(bot, chargeAnchor);
                    std::string semantic = BuildSemanticJson(
                        bot, chargeAnchor, "normal_dungeon_trash",
                        &power, stage, activity);
                    RecordEvent(state, bot,
                        "validation_route_threat_pickup", chargeAnchor,
                        "feral_move_remote_healer_trash_cluster_pre_roar",
                        raw.c_str(), semantic.c_str(), chargeDistance,
                        float(defenseAttackerCount));
                    state.TargetGuid = chargeAnchor->GetGUID();
                    target = chargeAnchor;
                    situation = "normal_dungeon_trash";
                    action =
                        "feral_move_remote_healer_trash_cluster_pre_roar";
                    return true;
                }
            }
        }
        // Rerun54 proved the boss-add Roar pickup but also isolated the global
        // healer-dwell maximum to ordinary crystalspawn trash, where that
        // specialized resolver never runs. Reuse the same native ten-yard,
        // healer-owned, aura-bounded action here before the ordinary profile
        // area cycle. This does not assign victims or move the healer; it only
        // submits the explicit spell-99 rule after the Feral has reached at
        // least two of the healer's listed attackers.
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && defenseAttackerCount >= 2 && bot->HasSpell(99))
        {
            uint32 nearbyHealerOwnedCount = 0;
            bool missingOwnedRoar = false;
            Unit* nearbyHealerOwnedAttacker = nullptr;
            float nearbyHealerOwnedDistance = std::numeric_limits<float>::max();
            uint32 nearbyHealerOwnedGuid = std::numeric_limits<uint32>::max();
            std::vector<Unit*> currentHealerOwnedAttackers;
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && bot->IsValidAttackTarget(attacker)
                    && attacker->GetVictim() == defenseTarget)
                {
                    currentHealerOwnedAttackers.push_back(attacker);
                    if (bot->GetExactDist2d(attacker) > 10.0f)
                        continue;

                    ++nearbyHealerOwnedCount;
                    missingOwnedRoar = missingOwnedRoar
                        || !attacker->HasAura(99, bot->GetGUID());
                    float distance = bot->GetExactDist(attacker);
                    uint32 guid = attacker->GetGUID().GetCounter();
                    if (!nearbyHealerOwnedAttacker
                        || distance < nearbyHealerOwnedDistance
                        || (distance == nearbyHealerOwnedDistance
                            && guid < nearbyHealerOwnedGuid))
                    {
                        nearbyHealerOwnedAttacker = attacker;
                        nearbyHealerOwnedDistance = distance;
                        nearbyHealerOwnedGuid = guid;
                    }
            }
            // Rerun160's maximum 6025-ms exposure reached all ten
            // healer-owned followers inside the Feral's local area envelope,
            // but three GCD-separated Demoralizing Roars were needed to
            // recover them. The existing Thrash aura was ticking on the prior
            // cluster and covered none of these identities, while no Swipe was
            // submitted during the episode. At this already-validated local
            // recovery point, prefer one native damaging area-threat attempt
            // when the nearby set covers a majority of current healer threat.
            // A rejected Swipe changes no state and falls through to the
            // unchanged Roar and handoff chain below.
            bool nearbyHealerOwnedCoversMajority =
                nearbyHealerOwnedCount >= 2
                && nearbyHealerOwnedCount * 2
                    >= currentHealerOwnedAttackers.size();
            // Rerun202's generation-13 Flayer swarm entered this proven
            // local-majority recovery with ten healer-owned identities.
            // Native Swipe and Growl reduced that set to two within 1543 ms,
            // but the ordinary-trash path then spent three decisions moving
            // to density and four selecting an out-of-range representative.
            // Unlike the arrived boss handoff above, this gate never offered
            // native Thrash; the last observed Thrash attempt was more than
            // twenty seconds old and the two identities reached 4395/4915 ms
            // of continuous healer ownership. Prefer the same persistent
            // native area threat at this already-established local-majority
            // recovery point, retaining Swipe below whenever Thrash is
            // unavailable. Every native spell, target, cooldown, GCD, power,
            // range, movement, hazard, victim, and threat gate is unchanged.
            if (nearbyHealerOwnedCoversMajority
                && nearbyHealerOwnedAttacker && bot->HasSpell(77758)
                && TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 77758))
            {
                if (feralTrashChargeArrived)
                {
                    state.FeralChargePickupTargetGuid.Clear();
                    state.FeralChargePickupUntilMs = 0;
                }
                std::string raw = BuildRawJson(
                    bot, nearbyHealerOwnedAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, nearbyHealerOwnedAttacker,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    nearbyHealerOwnedAttacker,
                    "feral_thrash_healer_swarm_retention_before_roar",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyHealerOwnedCount),
                    float(currentHealerOwnedAttackers.size()), 77758);
                state.TargetGuid = nearbyHealerOwnedAttacker->GetGUID();
                target = nearbyHealerOwnedAttacker;
                situation = "normal_dungeon_trash";
                action =
                    "feral_thrash_healer_swarm_retention_before_roar";
                state.WasInCombat = true;
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                return true;
            }
            if (nearbyHealerOwnedCoversMajority
                && nearbyHealerOwnedAttacker && bot->HasSpell(779)
                && TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 779))
            {
                if (feralTrashChargeArrived)
                {
                    state.FeralChargePickupTargetGuid.Clear();
                    state.FeralChargePickupUntilMs = 0;
                }
                std::string raw = BuildRawJson(
                    bot, nearbyHealerOwnedAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, nearbyHealerOwnedAttacker,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    nearbyHealerOwnedAttacker,
                    "feral_swipe_healer_swarm_retention_before_roar",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyHealerOwnedCount),
                    float(currentHealerOwnedAttackers.size()), 779);
                state.TargetGuid = nearbyHealerOwnedAttacker->GetGUID();
                target = nearbyHealerOwnedAttacker;
                situation = "normal_dungeon_trash";
                action =
                    "feral_swipe_healer_swarm_retention_before_roar";
                state.WasInCombat = true;
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                return true;
            }
            if (nearbyHealerOwnedCount >= 2 && missingOwnedRoar
                && TryCastFriendlySpell(bot, bot, 99))
            {
                if (feralTrashChargeArrived)
                {
                    state.FeralChargePickupTargetGuid.Clear();
                    state.FeralChargePickupUntilMs = 0;
                }
                // Rerun87 proved the stationary-healer handoff could submit
                // Roar at the 500 ms GCD boundary yet acquire only four or five
                // followers per cycle from a 27-47-hostile split topology.
                // Bind the bounded handoff to the densest currently remote
                // healer-owned cluster instead. Revalidate this moving GUID on
                // every tick above, matching the already-proved moving-endpoint
                // active-swarm pickup without permitting generic target churn.
                Unit* remoteClusterAnchor = nullptr;
                uint32 remoteClusterCount = 0;
                float remoteClusterDistance =
                    std::numeric_limits<float>::max();
                uint32 remoteClusterGuid =
                    std::numeric_limits<uint32>::max();
                for (Unit* candidate : currentHealerOwnedAttackers)
                {
                    float candidateDistance = bot->GetExactDist(candidate);
                    if (candidateDistance <= 10.0f)
                        continue;
                    uint32 clusterCount = 0;
                    for (Unit* neighbor : currentHealerOwnedAttackers)
                        if (candidate->GetExactDist2d(neighbor) <= 10.0f)
                            ++clusterCount;
                    uint32 guid = candidate->GetGUID().GetCounter();
                    if (!remoteClusterAnchor
                        || clusterCount > remoteClusterCount
                        || (clusterCount == remoteClusterCount
                            && (candidateDistance < remoteClusterDistance
                                || (candidateDistance == remoteClusterDistance
                                    && guid < remoteClusterGuid))))
                    {
                        remoteClusterAnchor = candidate;
                        remoteClusterCount = clusterCount;
                        remoteClusterDistance = candidateDistance;
                        remoteClusterGuid = guid;
                    }
                }
                bool remoteClusterRemains = remoteClusterAnchor != nullptr;
                Position remoteRoarIntercept;
                if (remoteClusterAnchor)
                    remoteRoarIntercept =
                        remoteClusterAnchor->GetFirstCollisionPosition(
                            8.0f,
                            remoteClusterAnchor->GetAngle(bot)
                                - remoteClusterAnchor->GetOrientation());
                // The post-Roar reservation needs only to preserve legal Roar
                // range. Walking to the hostile's exact point spends the same
                // strict dwell budget that the pre-Roar intercept avoids.
                bool splitClusterHandoff = remoteClusterAnchor
                    && !bot->HasUnitState(UNIT_STATE_CASTING)
                    && !bot->IsFalling()
                    && MoveBotToPoint(state, bot,
                        remoteRoarIntercept.GetPositionX(),
                        remoteRoarIntercept.GetPositionY(),
                        remoteRoarIntercept.GetPositionZ());
                if (splitClusterHandoff)
                    state.DecisionTimer = std::min<uint32>(
                        state.DecisionTimer, 500);
                if (remoteClusterRemains)
                {
                    state.FeralHealerThreatHandoffTargetGuid =
                        defenseTarget->GetGUID();
                    state.FeralHealerThreatHandoffAnchorGuid =
                        remoteClusterAnchor->GetGUID();
                    state.FeralHealerThreatHandoffUntilMs = NowMs() + 2500;
                    state.FeralHealerThreatHandoffRemoteCluster = true;
                }
                else
                {
                    state.FeralHealerThreatHandoffTargetGuid.Clear();
                    state.FeralHealerThreatHandoffAnchorGuid.Clear();
                    state.FeralHealerThreatHandoffUntilMs = 0;
                    state.FeralHealerThreatHandoffRemoteCluster = false;
                }
                std::string raw = BuildRawJson(bot, nearbyHealerOwnedAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, nearbyHealerOwnedAttacker, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    nearbyHealerOwnedAttacker,
                    splitClusterHandoff
                        ? "feral_demoralizing_roar_remote_healer_trash_cluster_handoff"
                        : "feral_demoralizing_roar_healer_trash_pickup",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyHealerOwnedCount),
                    float(currentHealerOwnedAttackers.size()), 99);
                state.TargetGuid = nearbyHealerOwnedAttacker
                    ? nearbyHealerOwnedAttacker->GetGUID() : ObjectGuid::Empty;
                target = nearbyHealerOwnedAttacker;
                situation = "normal_dungeon_trash";
                action = splitClusterHandoff
                    ? "feral_demoralizing_roar_remote_healer_trash_cluster_handoff"
                    : "feral_demoralizing_roar_healer_trash_pickup";
                state.WasInCombat = true;
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                return true;
            }
        }
        if (feralTrashChargeArrived && defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 2)
        {
            bot->StopMoving();
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
            std::string raw = BuildRawJson(bot, feralTrashChargeTarget);
            std::string semantic = BuildSemanticJson(
                bot, feralTrashChargeTarget, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                feralTrashChargeTarget,
                "feral_hold_charge_trash_arrival_for_roar",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(feralTrashChargeTarget),
                float(defenseAttackerCount));
            state.TargetGuid = feralTrashChargeTarget->GetGUID();
            target = feralTrashChargeTarget;
            situation = "normal_dungeon_trash";
            action = "feral_hold_charge_trash_arrival_for_roar";
            return true;
        }
        if (feralTrashHandoffActive && feralTrashHandoffArrived
            && defenseAttackerCount >= 2)
        {
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 500);
            std::string raw = BuildRawJson(bot, feralTrashHandoffAnchor);
            std::string semantic = BuildSemanticJson(
                bot, feralTrashHandoffAnchor, "normal_dungeon_trash",
                &power, stage, activity);
            RecordEvent(state, bot, "validation_route_threat_pickup",
                feralTrashHandoffAnchor,
                "feral_hold_remote_healer_trash_cluster_for_roar",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(feralTrashHandoffAnchor),
                float(defenseAttackerCount));
            state.TargetGuid = feralTrashHandoffAnchor->GetGUID();
            target = feralTrashHandoffAnchor;
            situation = "normal_dungeon_trash";
            action = "feral_hold_remote_healer_trash_cluster_for_roar";
            return true;
        }
        // A single Flayer follower survived rerun81's completed area pickup for
        // 6041 ms because the two-attacker Roar gate no longer applied and the
        // strict area resolver kept selecting density movement. Use the
        // explicit native Growl profile for exactly one healer-owned attacker;
        // this neither assigns a victim nor replaces multi-target pickup.
        if (defenseTarget && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && bot->getClass() == CLASS_DRUID
            && defenseAttackerCount == 1 && bot->HasSpell(6795))
        {
            Unit* healerAttacker = nullptr;
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && bot->IsValidAttackTarget(attacker)
                    && (!healerAttacker
                        || bot->GetExactDist(attacker)
                            < bot->GetExactDist(healerAttacker)
                        || (bot->GetExactDist(attacker)
                                == bot->GetExactDist(healerAttacker)
                            && attacker->GetGUID().GetCounter()
                                < healerAttacker->GetGUID().GetCounter())))
                    healerAttacker = attacker;
            if (healerAttacker
                && TryCastCombatSpell(bot, healerAttacker, 6795))
            {
                std::string raw = BuildRawJson(bot, healerAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, healerAttacker, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    healerAttacker,
                    "feral_growl_lingering_healer_trash_attacker",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(healerAttacker),
                    float(defenseAttackerCount), 6795);
                state.TargetGuid = healerAttacker->GetGUID();
                target = healerAttacker;
                situation = "normal_dungeon_trash";
                action = "feral_growl_lingering_healer_trash_attacker";
                state.WasInCombat = true;
                return true;
            }
        }
    return false;
}
}
