#include "Bots/BotWorldPopulationMgrValidationRouteTrashIntervention.h"

#include "Bots/BotActionArbiter.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotWorldPopulationMgrValidationRouteFeralTrashHandoff.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTankTrashRecovery.h"

#include "Creature.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <limits>
#include <string>
#include <utility>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
using BotWorldPopulationMgrSpellSemantics::NowMs;

namespace BotWorldPopulationMgrValidationRoute
{
bool ObjectiveContext::RunTrashIntervention(
    TrashThreatControl& trashThreatControl,
    TrashInterventionCallbacks const& callbacks)
{
    WorldBotState& state = State;
    Player* bot = Bot;
    BotRolePowerBreakdown const& power = Power;
    BotProgressionStage stage = Stage;
    BotProgressionActivity activity = Activity;
    std::string& situation = Situation;
    std::string& action = Action;
    Unit*& target = Target;

    auto const& isProtectionProfile = callbacks.IsProtectionProfile;
    auto const& routeEngageRange = callbacks.RouteEngageRange;
    auto const& isImmediateNextValidationRouteEncounterMember =
        callbacks.IsImmediateNextValidationRouteEncounterMember;
    auto const& findTrashClusterThreatTarget =
        callbacks.FindTrashClusterThreatTarget;
    auto const& findLastKnownFocusTarget =
        callbacks.FindLastKnownFocusTarget;
    auto const& routeUsableCombatTarget =
        callbacks.RouteUsableCombatTarget;
    auto const& rememberValidationRouteFocus =
        callbacks.RememberValidationRouteFocus;

    auto Cohort = [this]() -> decltype(auto)
    {
        return Manager.Cohort();
    };
    auto Party = [this]() -> decltype(auto)
    {
        return Manager.Party();
    };
    auto GetDungeonRole = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.GetDungeonRole(
            std::forward<decltype(args)>(args)...);
    };
    auto GetLoadedBot = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.GetLoadedBot(
            std::forward<decltype(args)>(args)...);
    };
    auto MoveBotToPoint = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MoveBotToPoint(
            std::forward<decltype(args)>(args)...);
    };
    auto SubmitMeleeAutoAttackIntent = [this](auto&&... args)
        -> decltype(auto)
    {
        return Manager.SubmitMeleeAutoAttackIntent(
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
    auto MoveBotToProfileRange = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MoveBotToProfileRange(
            std::forward<decltype(args)>(args)...);
    };
    ObjectiveContext& terminalArrivalContext = *this;

    if ((Cohort().Config.ValidationRouteKind != "boss" || trashThreatControl.EngagedCount > 0)
        && std::string(GetDungeonRole(bot)) == "dps"
        && !bot->getAttackers().empty()
        && !bot->HasUnitState(UNIT_STATE_CASTING)
        && !bot->IsFalling())
    {
        Player* tank = nullptr;
        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (member && member->IsAlive() && member->GetMap() == bot->GetMap()
                && member->GetGroup() == bot->GetGroup()
                && std::string(GetDungeonRole(member)) == "tank")
            {
                tank = member;
                break;
            }
        }
        Unit* nearestAttacker = nullptr;
        float nearestDistance = std::numeric_limits<float>::max();
        for (Unit* attacker : bot->getAttackers())
        {
            if (!attacker || !attacker->IsAlive() || attacker->GetMap() != bot->GetMap())
                continue;
            float distance = bot->GetExactDist2d(attacker);
            if (!nearestAttacker || distance < nearestDistance)
            {
                nearestAttacker = attacker;
                nearestDistance = distance;
            }
        }
        if (tank && nearestAttacker && bot->GetExactDist2d(tank) > 8.0f)
        {
            Position pickup = tank->GetFirstCollisionPosition(4.0f,
                nearestAttacker->GetAngle(tank) - tank->GetOrientation());
            if (bot->GetExactDist2d(pickup.GetPositionX(), pickup.GetPositionY()) > 2.0f
                && MoveBotToPoint(state, bot, pickup.GetPositionX(), pickup.GetPositionY(), pickup.GetPositionZ()))
            {
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Threat,
                    BotActionArbitration::Priority::ThreatControl,
                    "trash_pickup_stack_hold");
                if (Pet* pet = bot->GetPet())
                    pet->AttackStop();
                std::string raw = BuildRawJson(bot, nearestAttacker);
                std::string semantic = BuildSemanticJson(bot, nearestAttacker, "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup", nearestAttacker, "dps_stack_for_trash_pickup",
                    raw.c_str(), semantic.c_str(), nearestDistance, Cohort().Config.ValidationRouteTargetEntry);
                Unit* pickupFocus = tank->GetVictim() ? tank->GetVictim() : nearestAttacker;
                state.TargetGuid = pickupFocus->GetGUID();
                target = pickupFocus;
                situation = "validation_route_regroup";
                action = "dps_stack_for_trash_pickup";
                return true;
            }
        }
    }
    // Threat rescue is route-kind agnostic. A boss can activate while a
    // prerequisite target is still alive (Ozruk does this during the approach
    // handoff), and suppressing this block on boss nodes left the new boss on
    // the healer while the tank continued the prerequisite rotation.
    if (std::string(GetDungeonRole(bot)) == "tank")
    {
        Player* defenseTarget = nullptr;
        uint8 defensePriority = 0;
        size_t defenseAttackerCount = 0;
        uint32 defenseGuid = std::numeric_limits<uint32>::max();
        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetLoadedBot(cohortState);
            if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap()
                || member->GetGroup() != bot->GetGroup())
                continue;
            std::string memberRole = GetDungeonRole(member);
            if (memberRole == "tank")
                continue;
            // Rerun124's terminal Flayer wave was explicitly visible in the
            // 80-yard victim scan for four decisions while the healer's native
            // attacker container remained empty. Carry that authoritative
            // listed-victim observation into the existing deterministic target
            // selector so the bounded Charge/Roar handoff starts immediately.
            size_t explicitAttackerCount =
                member == trashThreatControl.HealerTarget
                    ? trashThreatControl.HealerTargetCount : 0;
            size_t attackerCount = std::max(
                member->getAttackers().size(), explicitAttackerCount);
            if (!attackerCount)
                continue;
            uint8 priority = memberRole == "healer" ? 2 : 1;
            uint32 guid = member->GetGUID().GetCounter();
            if (!defenseTarget || priority > defensePriority
                || (priority == defensePriority && attackerCount > defenseAttackerCount)
                || (priority == defensePriority && attackerCount == defenseAttackerCount && guid < defenseGuid))
            {
                defenseTarget = member;
                defensePriority = priority;
                defenseAttackerCount = attackerCount;
                defenseGuid = guid;
            }
        }
        // Rerun153 proved the reactive cadence from rerun152 bounded every
        // healer-target episode below three seconds, but already-owned packs
        // could still flip during ordinary one-second area-threat fallbacks.
        // Keep the existing native Consecration, Righteous Defense, Avenger's
        // Shield, Salvation, and density ordering intact; start the same
        // bounded cadence while Protection still owns a three-hostile pack,
        // and preserve it through an observed multi-hostile healer handoff.
        bool protectionMultiHostileRetention = bot->getClass() == CLASS_PALADIN
            && trashThreatControl.EngagedCount >= 3
            && trashThreatControl.TankOwnsTrashMajority;
        bool protectionMultiHostileHealerPickup = bot->getClass() == CLASS_PALADIN
            && defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 2;
        if (protectionMultiHostileRetention
            || protectionMultiHostileHealerPickup)
            state.DecisionTimer = std::min<uint32>(
                state.DecisionTimer, 250);
        // Rerun95 reached an ordinary-trash Azil follower overlap with 52
        // engaged hostiles. The boss-add resolver's native Feral defensive
        // submission did not apply because this manifest node is trash, and
        // the tank died while still owning 36 followers. Rerun96 then showed
        // that a 90-percent health sample is still too late for a 49-follower
        // simultaneous swing: the tank was above the threshold in the final
        // decision and dead before the next one. Reuse the native off-GCD rule
        // proactively before bounded pickup movement consumes the decision.
        // Rerun123 proved twelve is too early: the Feral survived the 12-14
        // precursor after spending its defensive, then died when the sustained
        // 30-40-hostile Flayer wave arrived about twenty seconds later. Reserve
        // the same native action until 24 engaged hostiles, above that observed
        // precursor and below the failing wave's first 28-30-hostile samples.
        if (bot->getClass() == CLASS_DRUID
            && trashThreatControl.EngagedCount >= 24
            && !bot->HasAura(61336) && !bot->HasAura(22812))
        {
            std::array<uint32, 2> defensiveSpells = { 61336, 22812 };
            for (uint32 defensiveSpellId : defensiveSpells)
                if (bot->HasSpell(defensiveSpellId)
                    && TryCastFriendlySpell(bot, bot, defensiveSpellId))
                {
                    std::string raw = BuildRawJson(
                        bot, trashThreatControl.AreaTarget);
                    std::string semantic = BuildSemanticJson(
                        bot, trashThreatControl.AreaTarget,
                        "normal_dungeon_trash", &power, stage, activity);
                    RecordEvent(state, bot, "defensive", bot,
                        "tank_trash_swarm_defensive",
                        raw.c_str(), semantic.c_str(), UnitHealthPct(bot),
                        trashThreatControl.EngagedCount, defensiveSpellId);
                    break;
                }
        }
        // Rerun105 passed the all-hostile retention floor, but both remaining
        // generation-13 exposure bursts flipped already-eligible identities
        // immediately after a healer cast. In the preceding samples the Feral
        // owned the whole large wave while fewer than ninety percent had the
        // existing 2.5x secure-threat margin; the ordinary resolver then moved
        // toward density instead of submitting its ready native Swipe cycle.
        // Reinforce that margin before movement when a legal local Swipe is
        // available. Remote or cooldown cases still fall through unchanged.
        Unit* feralSecureMarginTarget = nullptr;
        uint32 feralSecureMarginClusterCount = 0;
        float feralSecureMarginDistance =
            std::numeric_limits<float>::max();
        uint32 feralSecureMarginGuid =
            std::numeric_limits<uint32>::max();
        if (bot->getClass() == CLASS_DRUID)
            for (Unit* candidate :
                trashThreatControl.InsecureTankOwnedTargets)
            {
                if (!candidate || !candidate->IsAlive()
                    || candidate->GetMap() != bot->GetMap()
                    || candidate->GetVictim() != bot
                    || !bot->IsValidAttackTarget(candidate))
                    continue;
                uint32 clusterCount = 0;
                for (Unit* neighbor :
                    trashThreatControl.InsecureTankOwnedTargets)
                    if (neighbor && neighbor->IsAlive()
                        && neighbor->GetMap() == bot->GetMap()
                        && neighbor->GetVictim() == bot
                        && bot->IsValidAttackTarget(neighbor)
                        && candidate->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!feralSecureMarginTarget
                    || clusterCount > feralSecureMarginClusterCount
                    || (clusterCount == feralSecureMarginClusterCount
                        && (distance < feralSecureMarginDistance
                            || (distance == feralSecureMarginDistance
                                && guid < feralSecureMarginGuid))))
                {
                    feralSecureMarginTarget = candidate;
                    feralSecureMarginClusterCount = clusterCount;
                    feralSecureMarginDistance = distance;
                    feralSecureMarginGuid = guid;
                }
            }
        bool feralCurrentHealerThreat = defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) == "healer"
            && defenseAttackerCount >= 1;
        bool feralHealerHandoffPending = feralCurrentHealerThreat
            && state.FeralHealerThreatHandoffTargetGuid
                == defenseTarget->GetGUID()
            && state.FeralHealerThreatHandoffUntilMs > NowMs();
        // Rerun149 proved the global insecure predicate could submit Swipe at
        // the nearest generic area target while a different, already-aged
        // remote Flayer cluster remained below the same 2.5x secure margin.
        // Select that vulnerable cluster deterministically and establish native
        // Swipe range before spending its GCD. If a healer handoff is already
        // active, preserve the existing Roar recovery's first legal GCD.
        // Rerun155 recovered one of three healer-owned Flayers with Growl, then
        // spent seven decisions approaching an insecure tank-owned cluster
        // while the other two crossed the dwell limit. Current healer ownership
        // is higher authority even when no handoff reservation exists yet; let
        // the identity-scoped rescue controller below own that same decision.
        // Rerun176 then recorded 45 of generation 13's 53 healer-exposure
        // samples when fully tank-owned packs of seven and eleven Flayers were
        // below this branch's redundant twelve-hostile floor. One later heal
        // flipped those already-aged insecure identities before reactive pickup.
        // The insecure-swarm predicate already proves at least three engaged
        // hostiles, so apply this unchanged native secure-margin action across
        // that complete predicate instead of only its largest subsets.
        if (bot->getClass() == CLASS_DRUID
            && trashThreatControl.EngagedCount >= 3
            && trashThreatControl.TankOwnsTrashMajority
            && trashThreatControl.InsecureTrashSwarm
            && feralSecureMarginTarget && bot->HasSpell(779)
            && !feralHealerHandoffPending
            && !feralCurrentHealerThreat)
        {
            if ((feralSecureMarginDistance > 8.0f
                    || !bot->IsWithinLOSInMap(feralSecureMarginTarget))
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling()
                && MoveBotToProfileRange(
                    state, bot, feralSecureMarginTarget))
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 250);
                std::string raw = BuildRawJson(
                    bot, feralSecureMarginTarget);
                std::string semantic = BuildSemanticJson(
                    bot, feralSecureMarginTarget,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot,
                    "validation_route_threat_pickup",
                    feralSecureMarginTarget,
                    "feral_approach_insecure_trash_threat_cluster",
                    raw.c_str(), semantic.c_str(),
                    float(feralSecureMarginClusterCount),
                    trashThreatControl.EngagedCount, 779);
                state.TargetGuid = feralSecureMarginTarget->GetGUID();
                state.WasInCombat = true;
                target = feralSecureMarginTarget;
                situation = "normal_dungeon_trash";
                action =
                    "feral_approach_insecure_trash_threat_cluster";
                return true;
            }
            if (TryCastCombatSpell(bot, feralSecureMarginTarget, 779))
            {
                std::string raw = BuildRawJson(
                    bot, feralSecureMarginTarget);
                std::string semantic = BuildSemanticJson(
                    bot, feralSecureMarginTarget,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    feralSecureMarginTarget,
                    "feral_swipe_secure_trash_threat_margin",
                    raw.c_str(), semantic.c_str(),
                    float(trashThreatControl.SecureTankCount),
                    trashThreatControl.EngagedCount, 779);
                state.TargetGuid = feralSecureMarginTarget->GetGUID();
                state.WasInCombat = true;
                target = feralSecureMarginTarget;
                situation = "normal_dungeon_trash";
                action = "feral_swipe_secure_trash_threat_margin";
                return true;
            }
        }
        // Rerun112 localized the all-hostile retention failure to ordinary
        // opening packs on DPS: five eligible identities remained loose while
        // the healer-only Feral rescue was inapplicable and the generic area
        // cycle recovered them one at a time. Rerun113 then showed that an
        // unbounded rescue chased remote DPS attackers while 21--42 hostiles
        // were engaged, preempting the established density/healer controller.
        // Keep the targeted rescue inside the existing tactical radius and
        // small-pack envelope. This does not assign victims or change threat.
        if (defenseTarget
            && std::string(GetDungeonRole(defenseTarget)) != "healer"
            && bot->getClass() == CLASS_DRUID
            && trashThreatControl.EngagedCount >= 1
            && trashThreatControl.EngagedCount <= 8)
        {
            std::vector<Unit*> partyAttackers;
            for (Unit* attacker : defenseTarget->getAttackers())
                if (attacker && attacker->IsAlive()
                    && attacker->GetMap() == bot->GetMap()
                    && attacker->GetVictim() == defenseTarget
                    && bot->IsValidAttackTarget(attacker)
                    && bot->IsWithinDistInMap(attacker, 45.0f))
                    partyAttackers.push_back(attacker);

            if (partyAttackers.size() == 1 && bot->HasSpell(6795)
                && TryCastCombatSpell(bot, partyAttackers.front(), 6795))
            {
                Unit* attacker = partyAttackers.front();
                std::string raw = BuildRawJson(bot, attacker);
                std::string semantic = BuildSemanticJson(
                    bot, attacker, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    attacker, "feral_growl_lingering_party_trash_attacker",
                    raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(attacker), 1.0f, 6795);
                state.TargetGuid = attacker->GetGUID();
                state.WasInCombat = true;
                target = attacker;
                situation = "normal_dungeon_trash";
                action = "feral_growl_lingering_party_trash_attacker";
                return true;
            }

            Unit* nearbyMissingRoarAttacker = nullptr;
            uint32 nearbyMissingRoarCount = 0;
            float nearbyDistance = std::numeric_limits<float>::max();
            uint32 nearbyGuid = std::numeric_limits<uint32>::max();
            for (Unit* attacker : partyAttackers)
            {
                float distance = bot->GetExactDist(attacker);
                uint32 guid = attacker->GetGUID().GetCounter();
                if (bot->GetExactDist2d(attacker) <= 10.0f
                    && !attacker->HasAura(99, bot->GetGUID()))
                {
                    ++nearbyMissingRoarCount;
                    if (!nearbyMissingRoarAttacker
                        || distance < nearbyDistance
                        || (distance == nearbyDistance && guid < nearbyGuid))
                    {
                        nearbyMissingRoarAttacker = attacker;
                        nearbyDistance = distance;
                        nearbyGuid = guid;
                    }
                }
            }
            if (nearbyMissingRoarCount >= 2 && bot->HasSpell(99)
                && TryCastFriendlySpell(bot, bot, 99))
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 500);
                std::string raw = BuildRawJson(
                    bot, nearbyMissingRoarAttacker);
                std::string semantic = BuildSemanticJson(
                    bot, nearbyMissingRoarAttacker,
                    "normal_dungeon_trash", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    nearbyMissingRoarAttacker,
                    "feral_demoralizing_roar_party_trash_pickup",
                    raw.c_str(), semantic.c_str(),
                    float(nearbyMissingRoarCount),
                    float(partyAttackers.size()), 99);
                state.TargetGuid = nearbyMissingRoarAttacker->GetGUID();
                state.WasInCombat = true;
                target = nearbyMissingRoarAttacker;
                situation = "normal_dungeon_trash";
                action = "feral_demoralizing_roar_party_trash_pickup";
                return true;
            }

            Unit* remoteClusterAnchor = nullptr;
            uint32 remoteClusterCount = 0;
            float remoteDistance = std::numeric_limits<float>::max();
            uint32 remoteGuid = std::numeric_limits<uint32>::max();
            for (Unit* candidate : partyAttackers)
            {
                float distance = bot->GetExactDist(candidate);
                if (distance <= 8.0f)
                    continue;
                uint32 clusterCount = 0;
                for (Unit* neighbor : partyAttackers)
                    if (candidate->GetExactDist2d(neighbor) <= 10.0f)
                        ++clusterCount;
                uint32 guid = candidate->GetGUID().GetCounter();
                if (!remoteClusterAnchor
                    || clusterCount > remoteClusterCount
                    || (clusterCount == remoteClusterCount
                        && (distance < remoteDistance
                            || (distance == remoteDistance
                                && guid < remoteGuid))))
                {
                    remoteClusterAnchor = candidate;
                    remoteClusterCount = clusterCount;
                    remoteDistance = distance;
                    remoteGuid = guid;
                }
            }
            if (remoteClusterAnchor && bot->HasSpell(16979)
                && TryCastCombatSpell(bot, remoteClusterAnchor, 16979))
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 500);
                std::string raw = BuildRawJson(bot, remoteClusterAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, remoteClusterAnchor, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    remoteClusterAnchor,
                    "feral_charge_remote_party_trash_cluster_pickup",
                    raw.c_str(), semantic.c_str(), remoteDistance,
                    float(partyAttackers.size()), 16979);
                state.TargetGuid = remoteClusterAnchor->GetGUID();
                state.WasInCombat = true;
                target = remoteClusterAnchor;
                situation = "normal_dungeon_trash";
                action = "feral_charge_remote_party_trash_cluster_pickup";
                return true;
            }
            if (remoteClusterAnchor
                && !bot->HasUnitState(UNIT_STATE_CASTING)
                && !bot->IsFalling()
                && MoveBotToPoint(state, bot,
                    remoteClusterAnchor->GetPositionX(),
                    remoteClusterAnchor->GetPositionY(),
                    remoteClusterAnchor->GetPositionZ()))
            {
                state.DecisionTimer = std::min<uint32>(
                    state.DecisionTimer, 500);
                std::string raw = BuildRawJson(bot, remoteClusterAnchor);
                std::string semantic = BuildSemanticJson(
                    bot, remoteClusterAnchor, "normal_dungeon_trash",
                    &power, stage, activity);
                RecordEvent(state, bot, "validation_route_threat_pickup",
                    remoteClusterAnchor,
                    "feral_move_remote_party_trash_cluster_pickup",
                    raw.c_str(), semantic.c_str(), remoteDistance,
                    float(partyAttackers.size()));
                state.TargetGuid = remoteClusterAnchor->GetGUID();
                state.WasInCombat = true;
                target = remoteClusterAnchor;
                situation = "normal_dungeon_trash";
                action = "feral_move_remote_party_trash_cluster_pickup";
                return true;
            }
        }
        BotWorldPopulationMgrValidationRoute::FeralTrashHandoffCallbacks
            feralTrashHandoffCallbacks;
        feralTrashHandoffCallbacks.DefenseTarget =
            [&defenseTarget]() { return defenseTarget; };
        feralTrashHandoffCallbacks.DefenseAttackerCount =
            [&defenseAttackerCount]() { return defenseAttackerCount; };
        feralTrashHandoffCallbacks.TrashThreatControlResult =
            [&trashThreatControl]()
                -> BotWorldPopulationMgrValidationRoute::TrashThreatControlResult const&
            {
                return trashThreatControl;
            };
        if (terminalArrivalContext.RunFeralTrashHandoff(
                feralTrashHandoffCallbacks))
            return true;
        BotWorldPopulationMgrValidationRoute::TankTrashRecoveryCallbacks
            tankTrashRecoveryCallbacks;
        tankTrashRecoveryCallbacks.DefenseTarget =
            [&defenseTarget]() { return defenseTarget; };
        tankTrashRecoveryCallbacks.DefenseAttackerCount =
            [&defenseAttackerCount]() { return defenseAttackerCount; };
        tankTrashRecoveryCallbacks.TrashThreatControlResult =
            [&trashThreatControl]()
                -> BotWorldPopulationMgrValidationRoute::TrashThreatControl&
            {
                return trashThreatControl;
            };
        tankTrashRecoveryCallbacks.IsProtectionProfile =
            isProtectionProfile;
        tankTrashRecoveryCallbacks.RouteEngageRange = routeEngageRange;
        tankTrashRecoveryCallbacks.IsImmediateNextValidationRouteEncounterMember =
            isImmediateNextValidationRouteEncounterMember;
        tankTrashRecoveryCallbacks.FindTrashClusterThreatTarget =
            findTrashClusterThreatTarget;
        tankTrashRecoveryCallbacks.FindLastKnownFocusTarget =
            findLastKnownFocusTarget;
        tankTrashRecoveryCallbacks.RouteUsableCombatTarget =
            routeUsableCombatTarget;
        tankTrashRecoveryCallbacks.RememberValidationRouteFocus =
            rememberValidationRouteFocus;
        if (terminalArrivalContext.RunTankTrashRecovery(
                tankTrashRecoveryCallbacks))
            return true;
    }
}
}
