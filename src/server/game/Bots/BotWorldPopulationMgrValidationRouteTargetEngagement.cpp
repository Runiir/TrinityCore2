#include "Bots/BotWorldPopulationMgrValidationRouteTargetEngagement.h"
#include "Bots/BotActionArbiter.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrPolicyHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotWorldPopulationMgrValidationCohortReadiness.h"

#include "CellImpl.h"
#include "Creature.h"
#include "CreatureGroups.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "MotionMaster.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <functional>
#include <limits>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
using BotWorldPopulationMgrPolicyHelpers::ToString;
using BotWorldPopulationMgrSpellSemantics::NowMs;

namespace BotWorldPopulationMgrValidationRoute
{
bool ObjectiveContext::RunTargetEngagement(
    TargetEngagementCallbacks const& callbacks)
{
    WorldBotState& state = State;
    Player* bot = Bot;
    BotRolePowerBreakdown const& power = Power;
    BotProgressionStage stage = Stage;
    BotProgressionActivity activity = Activity;
    std::string& situation = Situation;
    std::string& action = Action;
    Unit*& target = Target;
    using BossMechanicActionResult =
        BotWorldPopulationMgr::BossMechanicActionResult;
    bool discoveryLeg = callbacks.DiscoveryLeg();
    float routeArrivalRadius = RouteArrivalRadius;
    float const& canonicalRouteDistance = CanonicalRouteDistance;
    float& routeAnchorX = RouteAnchorX;
    float& routeAnchorY = RouteAnchorY;
    float& routeAnchorZ = RouteAnchorZ;
    std::string& routeAnchorReason = RouteAnchorReason;
    float& routeDistance = RouteDistance;

    auto const& routeEngageRange = callbacks.RouteEngageRange;
    auto const& currentValidationRouteTargetSpawnId =
        callbacks.CurrentValidationRouteTargetSpawnId;
    auto const& isEligibleTrashClusterMob =
        callbacks.IsEligibleTrashClusterMob;
    auto const& enrollValidationRoutePackMember =
        callbacks.EnrollValidationRoutePackMember;
    auto const& isValidationCohortCombatLinked =
        callbacks.IsValidationCohortCombatLinked;
    auto const& isCurrentDiscoveryScriptedEventTarget =
        callbacks.IsCurrentDiscoveryScriptedEventTarget;
    auto const& findTrashClusterThreatTarget =
        callbacks.FindTrashClusterThreatTarget;
    auto const& findNearestTrashClusterMob =
        callbacks.FindNearestTrashClusterMob;
    auto const& moveToRouteAnchor = callbacks.MoveToRouteAnchor;
    auto const& isValidationRouteScriptTarget =
        callbacks.IsValidationRouteScriptTarget;
    auto const& isValidationRouteCombatTarget =
        callbacks.IsValidationRouteCombatTarget;
    auto const& makeExistingValidationRouteCombatReady =
        callbacks.MakeExistingValidationRouteCombatReady;
    auto const& isValidationRouteObjectiveTarget =
        callbacks.IsValidationRouteObjectiveTarget;
    auto const& tryCanonicalValidationRouteBossRecovery =
        callbacks.TryCanonicalValidationRouteBossRecovery;
    auto const& clearValidationRouteKilledFocus =
        callbacks.ClearValidationRouteKilledFocus;
    auto const& recordValidationRouteTrashKill =
        callbacks.RecordValidationRouteTrashKill;
    auto const& tryValidationRouteActivation =
        callbacks.TryValidationRouteActivation;
    auto const& routeGroupFocusTarget = callbacks.RouteGroupFocusTarget;
    auto const& moveOutOfProfileDeadZone =
        callbacks.MoveOutOfProfileDeadZone;
    auto tryRouteGroupHeal = [&callbacks](Player* healer, Unit* combatTarget,
        bool allowMovement = true, bool allowStationaryCastTime = false)
    {
        return callbacks.TryRouteGroupHeal(healer, combatTarget,
            allowMovement, allowStationaryCastTime);
    };
    auto const& tryValidationRouteInterrupt =
        callbacks.TryValidationRouteInterrupt;
    auto const& maybeValidationPrerequisiteNoProgressAssist =
        callbacks.MaybeValidationPrerequisiteNoProgressAssist;
    auto const& recoverAuthoritativeFocus = callbacks.RecoverAuthoritativeFocus;
    auto const& rememberValidationRouteFocus =
        callbacks.RememberValidationRouteFocus;
    auto const& trashClusterHasLiveMobs = callbacks.TrashClusterHasLiveMobs;
    TrashClusterTerminalBlockerSnapshot const& trashClusterTerminalBlocker =
        callbacks.TrashClusterTerminalBlockerResult();
    auto const& validationPartyHasActiveCombat =
        callbacks.ValidationPartyHasActiveCombat;
    auto const& findBoundedTerminalPartyCombatTarget =
        callbacks.FindBoundedTerminalPartyCombatTarget;
    auto const& markTrashClusterCleared = callbacks.MarkTrashClusterCleared;

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
    auto FindDungeonAnchor = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.FindDungeonAnchor(
            std::forward<decltype(args)>(args)...);
    };
    auto GetLoadedBot = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.GetLoadedBot(
            std::forward<decltype(args)>(args)...);
    };
    auto IsValidationCohortMemberInOriginalInstance =
        [this](auto&&... args) -> decltype(auto)
    {
        return Manager.IsValidationCohortMemberInOriginalInstance(
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
    auto MarkBotBlocked = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MarkBotBlocked(
            std::forward<decltype(args)>(args)...);
    };
    auto MaybeAdvanceValidationRouteManifest =
        [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MaybeAdvanceValidationRouteManifest(
            std::forward<decltype(args)>(args)...);
    };
    auto RecordRouteProgress = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.RecordRouteProgress(
            std::forward<decltype(args)>(args)...);
    };
    auto ResolveProfileCombatAction =
        [this](auto&&... args) -> decltype(auto)
    {
        return Manager.ResolveProfileCombatAction(
            std::forward<decltype(args)>(args)...);
    };
    auto ExecuteProfileCombatAction =
        [this](auto&&... args) -> decltype(auto)
    {
        return Manager.ExecuteProfileCombatAction(
            std::forward<decltype(args)>(args)...);
    };
    auto MoveBotToProfileRange = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MoveBotToProfileRange(
            std::forward<decltype(args)>(args)...);
    };
    auto SubmitMeleeAutoAttackIntent =
        [this](auto&&... args) -> decltype(auto)
    {
        return Manager.SubmitMeleeAutoAttackIntent(
            std::forward<decltype(args)>(args)...);
    };
    auto TryBossMechanics = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.TryBossMechanics(
            std::forward<decltype(args)>(args)...);
    };

    Unit* preAnchorTrashTarget = nullptr;
    if (Cohort().Config.ValidationRouteKind != "boss" && std::string(GetDungeonRole(bot)) == "tank")
    {
        preAnchorTrashTarget = findTrashClusterThreatTarget();
        if (!preAnchorTrashTarget)
        {
            ObjectGuid::LowType canonicalSpawnId = currentValidationRouteTargetSpawnId();
            Creature* canonicalSource = canonicalSpawnId && bot->GetMap()
                ? bot->GetMap()->GetCreatureBySpawnId(canonicalSpawnId) : nullptr;
            if (isEligibleTrashClusterMob(canonicalSource))
            {
                preAnchorTrashTarget = canonicalSource;
                enrollValidationRoutePackMember(canonicalSource,
                    isValidationCohortCombatLinked(canonicalSource));
            }
        }
        float clusterApproachRadius = std::max(
            routeArrivalRadius,
            Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f
                ? Cohort().Config.ValidationRouteClusterRadiusYards
                : 90.0f);
        if (preAnchorTrashTarget && routeDistance > clusterApproachRadius)
        {
            Creature* threatCreature = preAnchorTrashTarget->ToCreature();
            if (!threatCreature
                || (!isValidationCohortCombatLinked(threatCreature)
                    && !isCurrentDiscoveryScriptedEventTarget(threatCreature)))
                preAnchorTrashTarget = nullptr;
        }
        // Rerun74 proved that the canonical source can seed and complete its
        // pack while another declared current-node patrol remains live beyond
        // the static arrival radius. Keep that strictly pathable candidate as
        // pre-anchor movement authority; the existing cluster-approach bound
        // below still prevents pulling a distant pack before reaching the node.
        if (!preAnchorTrashTarget)
            preAnchorTrashTarget = findNearestTrashClusterMob();
    }

    if (routeDistance > routeArrivalRadius && !preAnchorTrashTarget)
    {
        moveToRouteAnchor();
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_move", nullptr, routeAnchorReason == "validation_route" ? Cohort().Config.ValidationRouteLabel.c_str() : routeAnchorReason.c_str(), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
        action = "move_to_validation_route";
        return true;
    }

    Unit* routeTarget = preAnchorTrashTarget;
    Unit* seenRouteTarget = preAnchorTrashTarget;
    std::string targetSearchResult = "target_not_found";
    float seenRouteTargetDistance = preAnchorTrashTarget ? bot->GetExactDist(preAnchorTrashTarget) : 0.0f;
    if (preAnchorTrashTarget)
        targetSearchResult = "target_ready_before_route_anchor";
    if (Cohort().Config.ValidationRouteTargetEntry && !routeTarget)
    {
        float routeTargetSearchRange = Cohort().Config.ValidationRouteKind == "boss" ? 220.0f : 140.0f;
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, routeTargetSearchRange);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, routeTargetSearchRange);

        float bestDistance = 0.0f;
        float bestSeenDistance = 0.0f;
        for (WorldObject* object : objects)
        {
            Unit* unit = object ? object->ToUnit() : nullptr;
            Creature* creature = unit ? unit->ToCreature() : nullptr;
            if (!isValidationRouteScriptTarget(creature))
                continue;

            bool recordedCurrentDead = Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && (!creature->IsAlive() || !creature->GetHealth())
                && (Party().ValidationRoutePackDeathGuids.find(creature->GetGUID()) != Party().ValidationRoutePackDeathGuids.end()
                    || Party().ValidationRouteRecordedKillGuids.find(creature->GetGUID()) != Party().ValidationRouteRecordedKillGuids.end());
            if (recordedCurrentDead)
                continue;

            float distance = bot->GetExactDist(creature);
            if (!seenRouteTarget || distance < bestSeenDistance)
            {
                seenRouteTarget = creature;
                bestSeenDistance = distance;
                seenRouteTargetDistance = distance;
            }

            if (!creature->IsAlive() || !creature->GetHealth())
            {
                targetSearchResult = "target_seen_dead";
                continue;
            }

            if (!isValidationRouteCombatTarget(creature))
            {
                if (targetSearchResult == "target_not_found")
                    targetSearchResult = "target_seen_activation_target";
                continue;
            }

            if (!bot->IsWithinLOSInMap(creature))
            {
                targetSearchResult = "target_seen_no_los";
                continue;
            }

            if (!bot->IsValidAttackTarget(creature))
            {
                if (Unit* readied = makeExistingValidationRouteCombatReady(creature))
                {
                    routeTarget = readied;
                    bestDistance = distance;
                    targetSearchResult = "target_ready_after_activation";
                    continue;
                }

                targetSearchResult = "target_seen_not_attackable";
                continue;
            }

            Creature const* currentRouteCreature = routeTarget ? routeTarget->ToCreature() : nullptr;
            bool candidateOpener = Cohort().Config.ValidationRouteOpenerTargetEntry && creature->GetEntry() == Cohort().Config.ValidationRouteOpenerTargetEntry;
            bool currentOpener = currentRouteCreature && Cohort().Config.ValidationRouteOpenerTargetEntry && currentRouteCreature->GetEntry() == Cohort().Config.ValidationRouteOpenerTargetEntry;
            if (!routeTarget || (candidateOpener && !currentOpener) || (candidateOpener == currentOpener && distance < bestDistance))
            {
                routeTarget = creature;
                bestDistance = distance;
                targetSearchResult = "target_ready";
            }
        }
    }
    // Azil can survive an evade as a visible but unreachable canonical spawn.
    // Other bosses, notably Corborus while burrowed, use transient LOS states
    // that must remain under their native encounter controller.
    if (!routeTarget
        && seenRouteTarget
        && Cohort().Config.ValidationRouteKind == "boss"
        && Cohort().Config.ValidationRouteTargetEntry == 42333
        && (targetSearchResult == "target_seen_not_attackable" || targetSearchResult == "target_seen_no_los"))
    {
        bool tankOwnsBossRecovery = std::string(GetDungeonRole(bot)) == "tank";
        if (tankOwnsBossRecovery)
            ++state.ValidationRouteTargetSearchMissCount;

        if (tankOwnsBossRecovery && state.ValidationRouteTargetSearchMissCount >= 3)
        {
            std::string recoveryResult;
            bool recoveryInitiated = false;
            if (tryCanonicalValidationRouteBossRecovery(recoveryResult, recoveryInitiated))
            {
                situation = recoveryInitiated ? "validation_route_recovery" : "validation_route_blocked";
                action = recoveryInitiated ? "recover_canonical_validation_route_boss" : "blocked_no_fallback";
                return true;
            }
        }

        if (tankOwnsBossRecovery
            && Party().ValidationRouteCanonicalBossRecoveryAttempts >= 2
            && state.ValidationRouteTargetSearchMissCount >= 6)
        {
            std::string raw = BuildRawJson(bot, seenRouteTarget);
            std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_canonical_boss_recovery_no_reachable_target", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_recovery", seenRouteTarget, "canonical_boss_recovery_no_reachable_target", raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
            MarkBotBlocked(state, bot, "canonical_boss_recovery_no_reachable_target");
            situation = "validation_route_blocked";
            action = "blocked_no_fallback";
            return true;
        }

        std::string raw = BuildRawJson(bot, seenRouteTarget);
        std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_script_target_blocked", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", seenRouteTarget, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
        state.LastNoProgressReason = targetSearchResult;
        action = "validation_route_recovery";
        return true;
    }
    if (!routeTarget
        && seenRouteTarget
        && Cohort().Config.ValidationRouteKind == "boss"
        && targetSearchResult == "target_seen_dead")
    {
        std::string raw = BuildRawJson(bot, seenRouteTarget);
        std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_script_target_dead", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", seenRouteTarget, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
        clearValidationRouteKilledFocus(seenRouteTarget->GetGUID());
        state.LastNoProgressReason = targetSearchResult;
        action = "validation_route_recovery";
        return true;
    }
    if (!routeTarget
        && seenRouteTarget
        && Cohort().Config.ValidationRouteKind != "boss"
        && targetSearchResult == "target_seen_dead")
    {
        Party().ValidationRouteObservedDeadScriptTarget = true;
        recordValidationRouteTrashKill(seenRouteTarget, "target_seen_dead");
        clearValidationRouteKilledFocus(seenRouteTarget->GetGUID());
        seenRouteTarget = nullptr;
    }
    if (!routeTarget && seenRouteTarget && seenRouteTargetDistance > 8.0f)
    {
        if (Cohort().Config.ValidationRouteKind == "boss"
            && !isValidationRouteObjectiveTarget(seenRouteTarget->ToCreature()))
        {
            bot->InterruptNonMeleeSpells(false);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "seen_boss_target_not_declared");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            for (Unit* controlled : bot->m_Controlled)
                if (controlled)
                    controlled->AttackStop();
            std::string raw = BuildRawJson(bot, seenRouteTarget);
            std::string semantic = BuildSemanticJson(
                bot, seenRouteTarget, "validation_route_prerequisite", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected",
                seenRouteTarget, "boss_route_undeclared_prerequisite_blocked",
                raw.c_str(), semantic.c_str(), seenRouteTargetDistance,
                Cohort().Config.ValidationRouteTargetEntry);
            state.TargetGuid.Clear();
            target = nullptr;
            situation = "validation_route_prerequisite";
            action = "boss_route_prerequisite_blocked";
            return true;
        }
        tryValidationRouteActivation(seenRouteTarget, targetSearchResult.c_str());
        MoveBotToProfileRange(state, bot, seenRouteTarget);
        std::string raw = BuildRawJson(bot, seenRouteTarget);
        std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_target_approach", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", seenRouteTarget, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
        action = "move_to_validation_route_target";
        return true;
    }
    if (!routeTarget && seenRouteTarget)
    {
        if (tryValidationRouteActivation(seenRouteTarget, targetSearchResult.c_str()))
        {
            std::string raw = BuildRawJson(bot, seenRouteTarget);
            std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_activation", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_target_search", seenRouteTarget, "activation_applied", raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
            action = "validation_route_activate_target";
            return true;
        }

        if (Cohort().Config.ValidationRouteKind == "boss")
        {
            bot->InterruptNonMeleeSpells(false);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "boss_activation_fail_closed");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            for (Unit* controlled : bot->m_Controlled)
                if (controlled)
                    controlled->AttackStop();
            std::string raw = BuildRawJson(bot, seenRouteTarget);
            std::string semantic = BuildSemanticJson(
                bot, seenRouteTarget, "validation_route_prerequisite", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected",
                seenRouteTarget, "boss_route_undeclared_prerequisite_blocked",
                raw.c_str(), semantic.c_str(), seenRouteTargetDistance,
                Cohort().Config.ValidationRouteTargetEntry);
            state.TargetGuid.Clear();
            target = nullptr;
            situation = "validation_route_prerequisite";
            action = "boss_route_prerequisite_blocked";
            return true;
        }

        Creature* prerequisiteTarget = nullptr;
        float prerequisiteScore = -100000.0f;
        float prerequisiteDistance = 0.0f;
        if (Unit* focusTarget = routeGroupFocusTarget())
        {
            prerequisiteTarget = focusTarget->ToCreature();
            prerequisiteScore = 100000.0f;
            prerequisiteDistance = bot->GetExactDist(focusTarget);
        }
        if (!prerequisiteTarget && std::string(GetDungeonRole(bot)) != "tank")
        {
            if (Player* anchor = FindDungeonAnchor(bot))
            {
                std::string raw = BuildRawJson(bot, nullptr);
                std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
                if (anchor != bot && anchor->IsAlive() && anchor->GetMap() == bot->GetMap() && bot->GetExactDist(anchor) > 8.0f)
                {
                    MoveBotToProfileRange(state, bot, anchor);
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_before_prerequisite", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "move_to_validation_route_anchor";
                    return true;
                }

                if (Cohort().Config.ValidationRouteKind == "boss")
                {
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "hold_anchor_before_prerequisite", raw.c_str(), semantic.c_str(), anchor == bot ? 0.0f : bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "validation_route_hold_anchor";
                    return true;
                }
            }
        }
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 320.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 320.0f);
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!creature || creature == seenRouteTarget || !creature->IsAlive() || !bot->IsValidAttackTarget(creature))
                continue;
            if (Cohort().Config.ValidationRouteKind != "boss" && !isEligibleTrashClusterMob(creature))
                continue;
            if (creature->IsDungeonBoss() || creature->isWorldBoss())
                continue;
            if (creature->IsCritter() || creature->IsPet() || creature->IsTotem() || creature->IsSummon() || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
                continue;
            if (Cohort().Config.ValidationRouteKind == "boss" && Party().ValidationRouteActivationApplied
                && !isValidationRouteScriptTarget(creature) && !creature->IsInCombat() && !creature->GetVictim()
                && !isValidationCohortCombatLinked(creature))
                continue;

            float distance = bot->GetExactDist(creature);
            float routeProximity = creature->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
            std::string scriptName = creature->GetScriptName();
            if (routeProximity > 120.0f)
                continue;

            float score = 320.0f - distance;
            if (!scriptName.empty())
                score += 700.0f;
            if (creature->isElite())
                score += 35.0f;
            if (scriptName.empty() && routeProximity < 120.0f)
                score += 60.0f;
            if (creature->GetVictim() == bot)
                score += 80.0f;

            if (score > prerequisiteScore)
            {
                prerequisiteTarget = creature;
                prerequisiteScore = score;
                prerequisiteDistance = distance;
            }
        }

        if (prerequisiteTarget)
        {
            target = prerequisiteTarget;
            prerequisiteDistance = bot->GetExactDist(target);
            state.TargetGuid = target->GetGUID();
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "validation_route_prerequisite", &power, stage, activity);
            if (tryRouteGroupHeal(bot, target))
                return true;

            if (prerequisiteDistance > 35.0f || !bot->IsWithinLOSInMap(target))
            {
                bool moved = MoveBotToProfileRange(state, bot, target);
                RecordEvent(state, bot, "validation_route_prerequisite", target, moved ? "move_to_blocker" : "tactical_path_rejected", raw.c_str(), semantic.c_str(), prerequisiteDistance, Cohort().Config.ValidationRouteTargetEntry);
                if (!moved)
                    maybeValidationPrerequisiteNoProgressAssist(target, "blocker_path_no_progress");
                situation = "validation_route_prerequisite";
                action = moved ? "move_to_validation_route_prerequisite" : "hold_tactical_path_rejected";
                return true;
            }

            ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
            uint32 spellId = profileAction.SpellId;
            float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, target, spellId);
            float targetDistance = bot->GetExactDist(target);
            if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
            {
                bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
                action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
                situation = "validation_route_prerequisite";
                return true;
            }
            if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
            {
                bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
                RecordEvent(state, bot, "validation_route_prerequisite", target, moved ? "approach_target" : "tactical_path_rejected", raw.c_str(), semantic.c_str(), prerequisiteDistance, Cohort().Config.ValidationRouteTargetEntry);
                if (!moved)
                    maybeValidationPrerequisiteNoProgressAssist(target, "blocker_path_no_progress");
                situation = "validation_route_prerequisite";
                action = moved ? "move_to_validation_route_prerequisite" : "hold_tactical_path_rejected";
                return true;
            }

            BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
            RecordEvent(state, bot, "validation_route_prerequisite", target, ToString(result), raw.c_str(), semantic.c_str(), prerequisiteDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
            maybeValidationPrerequisiteNoProgressAssist(target, "blocker_no_health_progress");
            situation = "validation_route_prerequisite";
            action = "validation_route_prerequisite_action";
            state.WasInCombat = true;
            return true;
        }

        state.LastNoProgressReason = targetSearchResult;
        std::string raw = BuildRawJson(bot, seenRouteTarget);
        std::string semantic = BuildSemanticJson(bot, seenRouteTarget, "validation_route_blocked", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_failed", seenRouteTarget, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), seenRouteTargetDistance, Cohort().Config.ValidationRouteTargetEntry);
        action = "validation_route_target_blocked";
        return true;
    }
    if (!routeTarget && Cohort().Config.ValidationRouteKind != "boss" && std::string(GetDungeonRole(bot)) == "tank" && (routeDistance <= routeArrivalRadius || Manager.HasCompletedValidationRouteDrudgeEntrancePull(bot)))
    {
        Unit* anchorTarget = findTrashClusterThreatTarget();
        if (!anchorTarget)
            anchorTarget = findNearestTrashClusterMob();
        if (anchorTarget)
        {
            routeTarget = anchorTarget;
            targetSearchResult = isValidationRouteScriptTarget(anchorTarget->ToCreature()) ? "target_ready" : "anchor_reacquired_reachable_target";
            state.ValidationRouteTargetSearchMissCount = 0;
        }
        else if ((discoveryLeg ? (Party().ValidationRouteCompletedPackCount > 0 || Party().ValidationRouteObservedDeadScriptTarget)
                : Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                    && (Party().ValidationRoutePackObservedEngagement || Party().ValidationRouteObservedDeadScriptTarget))
            && ++state.ValidationRouteTargetSearchMissCount >= 2)
        {
            bool packHasLiveMobs = trashClusterHasLiveMobs();
            bool partyHasActiveCombatUnit =
                validationPartyHasActiveCombat(!packHasLiveMobs);
            Unit* terminalCombatTarget = !packHasLiveMobs && partyHasActiveCombatUnit
                ? findBoundedTerminalPartyCombatTarget() : nullptr;
            ValidationCohortReadinessObservation cohortObservation;
            cohortObservation.ExpectedMemberCount =
                Cohort().Config.TargetPopulation
                    ? Cohort().Config.TargetPopulation
                    : uint32(Party().Bots.size());
            cohortObservation.PackHasLiveMobs = packHasLiveMobs;
            cohortObservation.PartyHasActiveCombat = partyHasActiveCombatUnit;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                ValidationCohortMemberObservation memberObservation;
                if (Player* member = GetLoadedBot(cohortState))
                {
                    memberObservation.Accounted = true;
                    memberObservation.Living = member->IsAlive();
                    if (memberObservation.Living)
                    {
                        memberObservation.Valid = member->IsInWorld()
                            && IsValidationCohortMemberInOriginalInstance(
                                cohortState, member);
                        bool const outOfCombat = !member->IsInCombat()
                            && !member->GetVictim() && member->getAttackers().empty();
                        memberObservation.AtEndpoint = memberObservation.Valid
                            && (member->GetExactDist(
                                    Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY,
                                    Cohort().Config.ValidationRouteZ)
                                    <= routeArrivalRadius
                                || (Manager.HasCompletedValidationRouteDrudgeEntrancePull(
                                        member) && outOfCombat));
                    }
                    else
                    {
                        ValidationCohortRecoveryObservation recovery;
                        recovery.Alive = false;
                        recovery.Ghost = member->HasFlag(
                            PLAYER_FLAGS, PLAYER_FLAGS_GHOST);
                        recovery.ReleaseRequested =
                            cohortState.NativeReleaseRequested;
                        recovery.NativeCorpseAuthority =
                            Manager.HasNativeRaidCorpseAuthority(cohortState, member);
                        recovery.EpisodeStartedMs =
                            cohortState.NativeRecoveryEpisodeStartedMs;
                        recovery.EpisodeAttemptId =
                            cohortState.NativeRecoveryEpisodeAttemptId;
                        recovery.EpisodeRouteGeneration = cohortState.NativeRecoveryEpisodeRouteGeneration;
                        recovery.EpisodeWipeGeneration = cohortState.NativeRecoveryEpisodeWipeGeneration;
                        recovery.EpisodeDeathOrdinal =
                            cohortState.NativeRecoveryEpisodeDeathOrdinal;
                        recovery.EpisodePhase =
                            cohortState.NativeRecoveryEpisodePhase;
                        recovery.AttemptId = Cohort().AttemptId;
                        recovery.RouteGeneration =
                            Party().ValidationRouteGeneration;
                        recovery.WipeGeneration = Cohort().Raid.WipeGeneration;
                        recovery.DeathOrdinal = cohortState.RecentDeathCount;
                        memberObservation.KnownRecovering =
                            IsKnownValidationRecovery(recovery);
                        memberObservation.Valid =
                            memberObservation.KnownRecovering;
                    }
                }
                cohortObservation.ObserveMember(memberObservation);
            }
            ValidationCohortReadiness const cohortReadiness =
                ClassifyValidationCohortReadiness(cohortObservation);
            bool const fullCohortAtEndpoint =
                cohortReadiness.FullRosterAtEndpoint;
            uint64 nowMs = NowMs();
            uint64& clearCandidateSinceMs = discoveryLeg ? Party().ValidationRouteNodeClearCandidateSinceMs : Party().ValidationRoutePackClearCandidateSinceMs;
            if (!cohortReadiness.TrashTerminalReady)
                clearCandidateSinceMs = 0;
            else if (!clearCandidateSinceMs)
                clearCandidateSinceMs = nowMs;
            uint64 quietElapsedMs = clearCandidateSinceMs ? nowMs - clearCandidateSinceMs : 0;
            uint64 quietRemainingMs = quietElapsedMs >= 2000 ? 0 : 2000 - quietElapsedMs;

            if (terminalCombatTarget)
            {
                routeTarget = terminalCombatTarget;
                targetSearchResult = "terminal_party_combat_focus";
                state.ValidationRouteTargetSearchMissCount = 0;
                std::string raw = BuildRawJson(bot, terminalCombatTarget);
                std::string semantic = BuildSemanticJson(bot, terminalCombatTarget, "validation_route_prerequisite", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_recovery", terminalCombatTarget,
                    "terminal_party_combat_focus_acquired", raw.c_str(), semantic.c_str(),
                    bot->GetExactDist(terminalCombatTarget), terminalCombatTarget->GetEntry());
            }
            else if (Cohort().Config.ValidationRouteAdvanceMode == "terminal"
                && (discoveryLeg ? (Party().ValidationRouteCompletedPackCount > 0 || Party().ValidationRouteObservedDeadScriptTarget)
                    : (Party().ValidationRoutePackObservedEngagement || Party().ValidationRouteObservedDeadScriptTarget))
                && cohortReadiness.TrashTerminalReady
                && nowMs - clearCandidateSinceMs >= 2000)
            {
                if (discoveryLeg)
                {
                    Party().ValidationRouteFinalTransitionGuids.insert(Party().ValidationRoutePendingFinalTransitionGuids.begin(), Party().ValidationRoutePendingFinalTransitionGuids.end());
                    Party().ValidationRoutePendingFinalTransitionGuids.clear();
                }
                std::string raw = BuildRawJson(bot, nullptr);
                std::string semantic = BuildSemanticJson(bot, nullptr, "normal_dungeon_trash", &power, stage, activity);
                markTrashClusterCleared("trash_cluster_cleared");
                RecordEvent(state, bot, "dungeon_trash_cleared", nullptr, "trash_cluster_cleared", raw.c_str(), semantic.c_str(), float(Cohort().Metrics.Kills), Cohort().Config.ValidationRouteTargetEntry);
                MaybeAdvanceValidationRouteManifest();
            }
            else
            {
                char const* holdReason = packHasLiveMobs ? "dynamic_pack_members_live_or_unobserved"
                    : partyHasActiveCombatUnit ? "trash_cluster_party_combat_active"
                    : !cohortReadiness.AllExpectedMembersAccounted ? "trash_cluster_cohort_not_accounted"
                    : !cohortReadiness.AllLivingAtEndpoint ? "trash_cluster_living_cohort_not_at_endpoint"
                    : Cohort().Config.ValidationRouteAdvanceMode != "terminal" ? "trash_cluster_terminal_mode_required"
                    : "trash_cluster_clear_stability_pending";
                std::ostringstream raw;
                raw << "{\"base\":" << BuildRawJson(bot, nullptr)
                    << ",\"terminal_hold\":{\"pack_has_live_mobs\":" << (packHasLiveMobs ? "true" : "false")
                    << ",\"party_has_active_combat\":" << (partyHasActiveCombatUnit ? "true" : "false")
                    << ",\"full_cohort_at_endpoint\":" << (fullCohortAtEndpoint ? "true" : "false")
                    << ",\"cohort_readiness\":{\"expected_members\":"
                    << cohortObservation.ExpectedMemberCount
                    << ",\"roster_members\":"
                    << cohortObservation.RosterMemberCount
                    << ",\"accounted_members\":"
                    << cohortObservation.AccountedMemberCount
                    << ",\"missing_members\":"
                    << cohortObservation.MissingMemberCount
                    << ",\"invalid_members\":"
                    << cohortObservation.InvalidMemberCount
                    << ",\"living_members\":"
                    << cohortObservation.LivingMemberCount
                    << ",\"living_at_endpoint\":"
                    << cohortObservation.LivingAtEndpointCount
                    << ",\"known_recovering_members\":"
                    << cohortObservation.KnownRecoveringMemberCount
                    << ",\"all_expected_members_accounted\":"
                    << (cohortReadiness.AllExpectedMembersAccounted ? "true" : "false")
                    << ",\"all_living_at_endpoint\":"
                    << (cohortReadiness.AllLivingAtEndpoint ? "true" : "false")
                    << ",\"full_roster_at_endpoint\":"
                    << (cohortReadiness.FullRosterAtEndpoint ? "true" : "false")
                    << ",\"trash_terminal_ready\":"
                    << (cohortReadiness.TrashTerminalReady ? "true" : "false") << "}"
                    << ",\"quiet_elapsed_ms\":" << quietElapsedMs
                    << ",\"quiet_remaining_ms\":" << quietRemainingMs << "}"
                    << ",\"terminal_blocker\":";
                if (packHasLiveMobs)
                    raw << "{\"guid\":" << trashClusterTerminalBlocker.Guid.GetCounter()
                        << ",\"entry\":" << trashClusterTerminalBlocker.Entry
                        << ",\"spawn_id\":" << trashClusterTerminalBlocker.SpawnId
                        << ",\"formation_id\":" << trashClusterTerminalBlocker.FormationId
                        << ",\"formation_leader_guid\":" << trashClusterTerminalBlocker.FormationLeaderGuid.GetCounter()
                        << ",\"distance\":" << trashClusterTerminalBlocker.Distance
                        << ",\"position\":{\"x\":" << trashClusterTerminalBlocker.PositionX
                        << ",\"y\":" << trashClusterTerminalBlocker.PositionY
                        << ",\"z\":" << trashClusterTerminalBlocker.PositionZ << "}"
                        << ",\"home\":{\"x\":" << trashClusterTerminalBlocker.HomeX
                        << ",\"y\":" << trashClusterTerminalBlocker.HomeY
                        << ",\"z\":" << trashClusterTerminalBlocker.HomeZ
                        << ",\"distance\":" << trashClusterTerminalBlocker.HomeDistance << "}"
                        << ",\"current_motion_type\":" << trashClusterTerminalBlocker.CurrentMotionType
                        << ",\"active_motion_type\":" << trashClusterTerminalBlocker.ActiveMotionType
                        << ",\"observed\":" << (trashClusterTerminalBlocker.Observed ? "true" : "false")
                        << ",\"alive\":" << (trashClusterTerminalBlocker.Alive ? "true" : "false")
                        << ",\"attackable\":" << (trashClusterTerminalBlocker.Attackable ? "true" : "false")
                        << ",\"evade\":" << (trashClusterTerminalBlocker.Evade ? "true" : "false")
                        << ",\"path\":" << (trashClusterTerminalBlocker.Path ? "true" : "false")
                        << ",\"member\":" << (trashClusterTerminalBlocker.Member ? "true" : "false")
                        << ",\"returning_home\":" << (trashClusterTerminalBlocker.ReturningHome ? "true" : "false")
                        << ",\"formation_member\":" << (trashClusterTerminalBlocker.FormationMember ? "true" : "false")
                        << ",\"formation_leader\":" << (trashClusterTerminalBlocker.FormationLeader ? "true" : "false")
                        << ",\"formation_formed\":" << (trashClusterTerminalBlocker.FormationFormed ? "true" : "false") << "}";
                else
                    raw << "null";
                raw << "}";
                std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_pack_hold", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_recovery", nullptr, holdReason, raw.str().c_str(), semantic.c_str(), float(Party().ValidationRoutePackMemberGuids.size()), uint32(Party().ValidationRoutePackDeathGuids.size()));
            }
            if (!routeTarget)
                return true;
        }
    }

    if (!routeTarget)
    {
        bool bossTargetMissing = Cohort().Config.ValidationRouteKind == "boss"
            && targetSearchResult == "target_not_found";
        bool tankOwnsBossRecovery = bossTargetMissing && std::string(GetDungeonRole(bot)) == "tank";
        if (tankOwnsBossRecovery)
            ++state.ValidationRouteTargetSearchMissCount;

        if (tankOwnsBossRecovery && state.ValidationRouteTargetSearchMissCount >= 3)
        {
            std::string recoveryResult;
            bool recoveryInitiated = false;
            if (tryCanonicalValidationRouteBossRecovery(recoveryResult, recoveryInitiated))
            {
                situation = recoveryInitiated ? "validation_route_recovery" : "validation_route_blocked";
                action = recoveryInitiated ? "recover_canonical_validation_route_boss" : "blocked_no_fallback";
                return true;
            }
        }

        if (tankOwnsBossRecovery
            && Party().ValidationRouteActivationApplied
            && !Party().ValidationRouteCanonicalBossRecoveryAttempts
            && state.ValidationRouteTargetSearchMissCount >= 3)
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_activation_no_visible_target", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_recovery", nullptr, "boss_route_activation_no_visible_target", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Config.ValidationRouteTargetEntry);
            MarkBotBlocked(state, bot, "boss_route_activation_no_visible_target");
            situation = "validation_route_blocked";
            action = "blocked_no_fallback";
            return true;
        }

        if (tankOwnsBossRecovery
            && Party().ValidationRouteCanonicalBossRecoveryAttempts >= 2
            && state.ValidationRouteTargetSearchMissCount >= 6)
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_canonical_boss_recovery_no_visible_target", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_recovery", nullptr, "canonical_boss_recovery_no_visible_target", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Config.ValidationRouteTargetEntry);
            MarkBotBlocked(state, bot, "canonical_boss_recovery_no_visible_target");
            situation = "validation_route_blocked";
            action = "blocked_no_fallback";
            return true;
        }

        if (Cohort().Config.ValidationRouteKind == "boss"
            && std::string(GetDungeonRole(bot)) != "tank"
            && !Party().ValidationRouteFocusGuid.IsEmpty()
            && recoverAuthoritativeFocus("target_search_authoritative_focus_recovery"))
        {
            situation = "validation_route_recovery";
            action = "validation_route_recovery";
            return true;
        }

        if (tryValidationRouteActivation(nullptr, targetSearchResult.c_str()))
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_activation", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_target_search", nullptr, "activation_applied_no_visible_target", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
            action = "validation_route_activate_target";
            return true;
        }

        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_target_search", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", nullptr, targetSearchResult.c_str(), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
        action = "search_validation_route_target";
        return true;
    }

    if (Cohort().Config.ValidationRouteKind == "boss"
        && !isValidationRouteObjectiveTarget(routeTarget->ToCreature()))
    {
        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "route_target_not_declared");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
                controlled->AttackStop();
        situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
        action = "raid_target_not_declared_hold";
        return true;
    }
    target = routeTarget;
    state.ValidationRouteUnresolvedFocusHoldCount = 0;
    state.ValidationRouteTargetSearchMissCount = 0;
    state.TargetGuid = target->GetGUID();
    if (Cohort().Config.ValidationRouteKind != "boss")
        enrollValidationRoutePackMember(target->ToCreature(), isValidationCohortCombatLinked(target->ToCreature()));
    rememberValidationRouteFocus(target);
    if (Cohort().Config.ValidationRouteKind == "boss")
    {
        if (ApplyRaidPrepullBossPullGate(bot, target, situation, action))
            return true;
        BossMechanicActionResult mechanic = TryBossMechanics(state, bot, power, stage, activity, target);
        if (mechanic.Handled)
        {
            situation = mechanic.Situation;
            action = mechanic.Action;
            target = mechanic.Target;
            return true;
        }

        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "route_mechanic_fail_closed");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
                controlled->AttackStop();
        situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
        action = "raid_mechanic_contract_fail_closed";
        return true;
    }
    if (tryRouteGroupHeal(bot, target))
        return true;
    if (Cohort().Config.ValidationRouteKind == "boss" && tryValidationRouteInterrupt(target, "route_target_interrupt"))
        return true;
    ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
    uint32 spellId = profileAction.SpellId;
    float engageRange = routeEngageRange(bot, target, spellId);
    if (profileAction.MaxRange > 0.0f)
        engageRange = profileAction.MaxRange;
    float targetDistance = bot->GetExactDist(target);
    if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
    {
        bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
        action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
        return true;
    }
    if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
    {
        bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
        action = moved ? "move_to_validation_route_target" : "hold_tactical_path_rejected";
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, "validation_route_target_search", target, moved ? "approach_target" : "tactical_path_rejected", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
        if (!moved && Cohort().Config.ValidationRouteKind != "boss")
            maybeValidationPrerequisiteNoProgressAssist(target, "route_target_path_no_progress");
        return true;
    }

    BotActionResult pull = profileAction.AutoAttackMode == "melee"
        && SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::StartOrSwitch,
            target->GetGUID(), BotMeleeAutoAttack::Owner::Route,
            BotActionArbitration::Priority::TrainedDamage,
            "validation_route_melee_engagement")
                ? BotActionResult::Ok : BotActionResult::NoAction;
    BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
    if (result == BotActionResult::NoAction)
        result = pull;
    action = Cohort().Config.ValidationRouteKind == "boss"
        ? (std::string(GetDungeonRole(bot)) == "tank" ? "validation_route_tank_boss" : "validation_route_boss_action")
        : "validation_route_trash_action";
    state.WasInCombat = true;
    if (Cohort().Config.ValidationRouteKind != "boss")
    {
        float healthPct = UnitHealthPct(target);
        RecordRouteProgress(state, bot, target, "route_target_combat_progress", healthPct, healthPct, 0, 20);
    }

    std::string raw = BuildRawJson(bot, target);
    std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
    RecordEvent(state, bot, Cohort().Config.ValidationRouteKind == "boss" ? "boss_action" : "trash_action", target, ToString(result), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
    if (Cohort().Config.ValidationRouteKind == "boss")
    {
        RecordEvent(state, bot, "boss_started", target, Cohort().Config.ValidationRouteMechanicProfile.c_str(), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        maybeValidationPrerequisiteNoProgressAssist(target, "boss_route_no_health_progress");
    }
    else
        maybeValidationPrerequisiteNoProgressAssist(target, "route_target_no_health_progress");
    return true;
}

}
