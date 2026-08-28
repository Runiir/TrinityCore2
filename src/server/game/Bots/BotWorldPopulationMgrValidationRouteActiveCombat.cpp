#include "Bots/BotWorldPopulationMgrValidationRouteActiveCombat.h"

#include "Bots/BotActionArbiter.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrPolicyHelpers.h"

#include "Creature.h"
#include "Map.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <string>
#include <utility>

using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
using BotWorldPopulationMgrPolicyHelpers::ToString;

namespace BotWorldPopulationMgrValidationRoute
{
bool ObjectiveContext::RunActiveCombat(
    ActiveCombatCallbacks const& callbacks)
{
    WorldBotState& state = State;
    Player* bot = Bot;
    BotRolePowerBreakdown const& power = Power;
    BotProgressionStage stage = Stage;
    BotProgressionActivity activity = Activity;
    std::string& situation = Situation;
    std::string& action = Action;
    Unit*& target = Target;
    float routeArrivalRadius = RouteArrivalRadius;
    float& routeDistance = RouteDistance;
    using BossMechanicActionResult =
        BotWorldPopulationMgr::BossMechanicActionResult;

    auto const& GetDungeonRole = callbacks.GetDungeonRole;
    auto const& FindDungeonAnchor = callbacks.FindDungeonAnchor;
    auto const& routeEngageRange = callbacks.RouteEngageRange;
    auto const& isValidationCohortCombatLinked =
        callbacks.IsValidationCohortCombatLinked;
    auto const& enrollValidationRoutePackMember =
        callbacks.EnrollValidationRoutePackMember;
    auto const& isValidationRouteObjectiveTarget =
        callbacks.IsValidationRouteObjectiveTarget;
    auto const& isEligibleTrashClusterMob =
        callbacks.IsEligibleTrashClusterMob;
    auto const& rememberValidationRouteFocus =
        callbacks.RememberValidationRouteFocus;
    bool hasValidationRouteActivation =
        callbacks.HasValidationRouteActivation();
    auto const& validationRouteHasLivingTank =
        callbacks.ValidationRouteHasLivingTank;
    auto const& routeFocusTankOwned = callbacks.RouteFocusTankOwned;
    auto const& moveOutOfProfileDeadZone =
        callbacks.MoveOutOfProfileDeadZone;
    auto tryRouteGroupHeal = [&callbacks](Player* healer, Unit* combatTarget,
        bool allowMovement = true, bool allowStationaryCastTime = false)
        -> bool
    {
        return callbacks.TryRouteGroupHeal(healer, combatTarget,
            allowMovement, allowStationaryCastTime);
    };
    auto const& tryValidationRouteInterrupt =
        callbacks.TryValidationRouteInterrupt;
    auto const& maybeValidationPrerequisiteNoProgressAssist =
        callbacks.MaybeValidationPrerequisiteNoProgressAssist;

    auto Cohort = [this]() -> decltype(auto)
    {
        return Manager.Cohort();
    };
    auto Party = [this]() -> decltype(auto)
    {
        return Manager.Party();
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
    auto TryBossMechanics = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.TryBossMechanics(
            std::forward<decltype(args)>(args)...);
    };
    auto TryCastFriendlySpell = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.TryCastFriendlySpell(
            std::forward<decltype(args)>(args)...);
    };
    auto ResolveProfileCombatAction = [this](auto&&... args)
        -> decltype(auto)
    {
        return Manager.ResolveProfileCombatAction(
            std::forward<decltype(args)>(args)...);
    };
    auto ExecuteProfileCombatAction = [this](auto&&... args)
        -> decltype(auto)
    {
        return Manager.ExecuteProfileCombatAction(
            std::forward<decltype(args)>(args)...);
    };
    auto MoveBotToProfileRange = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MoveBotToProfileRange(
            std::forward<decltype(args)>(args)...);
    };
    auto RecordRouteProgress = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.RecordRouteProgress(
            std::forward<decltype(args)>(args)...);
    };

    if (std::string(GetDungeonRole(bot)) != "tank"
        && (Cohort().Config.ValidationRouteKind != "boss" || routeDistance <= routeArrivalRadius))
    {
        if (Player* anchor = FindDungeonAnchor(bot))
        {
            if (anchor != bot && anchor->IsAlive() && anchor->GetMap() == bot->GetMap())
            {
                if (target && target->IsAlive() && bot->IsValidAttackTarget(target))
                {
                    std::string raw = BuildRawJson(bot, target);
                    std::string semantic = BuildSemanticJson(bot, target, "validation_route_regroup", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_prerequisite_rejected", target, "regroup_anchor_no_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    state.TargetGuid.Clear();
                    target = nullptr;
                }

                if (bot->GetExactDist(anchor) > 8.0f
                    && !(Cohort().Config.ValidationRouteKind == "boss" && Party().ValidationRouteActivationApplied))
                {
                    MoveBotToPoint(state, bot, anchor->GetPositionX(), anchor->GetPositionY(), anchor->GetPositionZ());
                    std::string raw = BuildRawJson(bot, nullptr);
                    std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_no_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "move_to_validation_route_anchor";
                    return true;
                }

                std::string raw = BuildRawJson(bot, nullptr);
                std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
                if (Cohort().Config.ValidationRouteKind == "boss"
                    && hasValidationRouteActivation)
                {
                    if (Party().ValidationRouteActivationApplied)
                    {
                        state.ValidationRouteActivationApplied = true;
                        state.ValidationRouteActivationAttempts = Party().ValidationRouteActivationAttempts;
                        RecordEvent(state, bot, "validation_route_recovery", nullptr, "boss_route_no_focus_activation_already_applied", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
                    }
                    else
                        RecordEvent(state, bot, "validation_route_recovery", nullptr, "boss_route_wait_for_tank_activation", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "validation_route_hold_anchor";
                    return true;
                }

                RecordEvent(state, bot, "validation_route_regroup", anchor, "hold_anchor_no_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                situation = "validation_route_regroup";
                action = "validation_route_hold_anchor";
                return true;
            }
        }
    }
    if (bot->IsInCombat() && target && target->IsAlive() && bot->IsValidAttackTarget(target))
    {
        Creature const* creature = target->ToCreature();
        if (Cohort().Config.ValidationRouteKind != "boss" && creature && isValidationCohortCombatLinked(creature))
            enrollValidationRoutePackMember(creature, true);
        bool routeBossTarget = isValidationRouteObjectiveTarget(creature);
        float targetRouteDistance = target->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
        bool ineligibleTrashTarget = Cohort().Config.ValidationRouteKind != "boss" && creature && !isEligibleTrashClusterMob(creature);
        if (!routeBossTarget && creature && targetRouteDistance > 120.0f)
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "validation_route_prerequisite_rejected", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", target, "off_route_target", raw.c_str(), semantic.c_str(), targetRouteDistance, Cohort().Config.ValidationRouteTargetEntry);
        }
        else if (ineligibleTrashTarget)
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "validation_route_prerequisite_rejected", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", target, "ineligible_trash_target", raw.c_str(), semantic.c_str(), targetRouteDistance, Cohort().Config.ValidationRouteTargetEntry);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "ineligible_trash_target");
            state.TargetGuid.Clear();
            target = nullptr;
        }
    }
    if (bot->IsInCombat() && target && target->IsAlive() && bot->IsValidAttackTarget(target))
    {
        Creature const* creature = target->ToCreature();
        bool routeBossTarget = isValidationRouteObjectiveTarget(creature);
        if (routeBossTarget && Cohort().Config.ValidationRouteKind != "boss")
            enrollValidationRoutePackMember(creature, isValidationCohortCombatLinked(creature));
        if (routeBossTarget)
            rememberValidationRouteFocus(target);
        if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss")
        {
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
                "raid_mechanic_contract_fail_closed");
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
        if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss" && tryValidationRouteInterrupt(target, "route_boss_focus_interrupt"))
            return true;

        if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss" && bot->getClass() == CLASS_HUNTER)
        {
            Player* tank = FindDungeonAnchor(bot);
            if (tank && tank != bot && std::string(GetDungeonRole(tank)) == "tank")
            {
                if (bot->HasSpell(34477) && !bot->HasAura(34477)
                    && TryCastFriendlySpell(bot, tank, 34477))
                {
                    std::string raw = BuildRawJson(bot, target);
                    std::string semantic = BuildSemanticJson(bot, target, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_threat_transfer", target,
                        "misdirection_to_tank", raw.c_str(), semantic.c_str(), 1.0f,
                        Cohort().Config.ValidationRouteTargetEntry, 34477);
                    situation = "dungeon_boss";
                    action = "misdirection_to_tank";
                    return true;
                }
                if (bot->HasAura(34477))
                {
                    ResolvedCombatAction transferAction = ResolveProfileCombatAction(bot, target, 1, false);
                    BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &transferAction, 1, false);
                    std::string raw = BuildRawJson(bot, target);
                    std::string semantic = BuildSemanticJson(bot, target, "dungeon_boss", &power, stage, activity);
                    RecordEvent(state, bot, "validation_route_threat_transfer", target,
                        "misdirection_single_target_transfer", raw.c_str(), semantic.c_str(), 1.0f,
                        Cohort().Config.ValidationRouteTargetEntry,
                        result == BotActionResult::Ok ? transferAction.SpellId : 0);
                    situation = "dungeon_boss";
                    action = "misdirection_single_target_transfer";
                    state.WasInCombat = true;
                    return true;
                }
            }
        }

        ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
        uint32 spellId = profileAction.SpellId;
        float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, target, spellId);
        bool botIsTank = std::string(GetDungeonRole(bot)) == "tank";
        if (routeBossTarget && !botIsTank
            && Manager.TryValidationRoutePatrolCombatAnchor(
                state, bot, target, profileAction))
        {
            action = "move_to_validation_route_combat_anchor";
            situation = "validation_route_regroup";
            return true;
        }
        bool routeTrashPackTarget = Cohort().Config.ValidationRouteKind != "boss"
            && creature && isEligibleTrashClusterMob(creature);
        if (routeTrashPackTarget && !botIsTank
            && validationRouteHasLivingTank() && !routeFocusTankOwned(target))
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "validation_route_regroup", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", target, "wait_for_tank_threat", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
            SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "wait_for_tank_threat");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            state.TargetGuid.Clear();
            situation = "validation_route_regroup";
            action = "validation_route_hold_anchor";
            return true;
        }
        if (routeBossTarget)
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, "validation_target_priority", target, Cohort().Config.ValidationRouteKind == "boss" ? "route_boss_focus" : "route_trash_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, spellId);
        }
        float targetDistance = bot->GetExactDist(target);
        if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
        {
            bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
            action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
            situation = routeBossTarget ? situation : "validation_route_prerequisite";
            return true;
        }
        if (targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
        {
            bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
            action = moved
                ? (routeBossTarget ? "move_to_validation_route_target" : "move_to_validation_route_prerequisite")
                : "hold_tactical_path_rejected";
            situation = routeBossTarget ? situation : "validation_route_prerequisite";
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, routeBossTarget ? "validation_route_target_search" : "validation_route_prerequisite", target,
                moved ? "approach_target" : "tactical_path_rejected", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
            if (!moved && !routeBossTarget)
                maybeValidationPrerequisiteNoProgressAssist(target, "current_combat_path_no_progress");
            return true;
        }

        BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
        action = routeBossTarget
            ? (Cohort().Config.ValidationRouteKind == "boss" ? (std::string(GetDungeonRole(bot)) == "tank" ? "validation_route_tank_boss" : "validation_route_boss_action") : "validation_route_trash_action")
            : "validation_route_prerequisite_action";
        situation = routeBossTarget ? situation : "validation_route_prerequisite";
        if (routeBossTarget && Cohort().Config.ValidationRouteKind != "boss")
        {
            float healthPct = UnitHealthPct(target);
            RecordRouteProgress(state, bot, target, "route_target_combat_progress", healthPct, healthPct, 0, 20);
        }
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, routeBossTarget ? (Cohort().Config.ValidationRouteKind == "boss" ? "boss_action" : "trash_action") : "validation_route_prerequisite", target, ToString(result), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        if (routeBossTarget && Cohort().Config.ValidationRouteKind != "boss" && botIsTank)
            RecordEvent(state, bot, "tank_positioning", target, "route_trash_tank_focus", raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        if (!routeBossTarget)
            maybeValidationPrerequisiteNoProgressAssist(target, "current_combat_no_health_progress");
        if (routeBossTarget && Cohort().Config.ValidationRouteKind == "boss")
        {
            RecordEvent(state, bot, "boss_started", target, Cohort().Config.ValidationRouteMechanicProfile.c_str(), raw.c_str(), semantic.c_str(), routeDistance, Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
            maybeValidationPrerequisiteNoProgressAssist(target, "boss_route_no_health_progress");
        }
        state.WasInCombat = true;
        return true;
    }
    return false;
}
}
