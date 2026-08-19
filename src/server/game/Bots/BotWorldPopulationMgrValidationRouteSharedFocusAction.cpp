#include "Bots/BotWorldPopulationMgrValidationRouteSharedFocusAction.h"

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
bool ObjectiveContext::RunSharedFocusAction(
    SharedFocusActionCallbacks const& callbacks)
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

    auto const& routeGroupFocusTarget = callbacks.RouteGroupFocusTarget;
    auto const& teacherAssistAuthoritativeFocus =
        callbacks.TeacherAssistAuthoritativeFocus;
    auto const& authoritativeRouteFocusActive =
        callbacks.AuthoritativeRouteFocusActive;
    std::string const& authoritativeFocusFailure =
        callbacks.AuthoritativeFocusFailure();
    auto const& isValidationRouteObjectiveTarget =
        callbacks.IsValidationRouteObjectiveTarget;
    auto const& GetDungeonRole = callbacks.GetDungeonRole;
    auto const& routeEngageRange = callbacks.RouteEngageRange;
    auto const& moveOutOfProfileDeadZone =
        callbacks.MoveOutOfProfileDeadZone;
    auto tryRouteGroupHeal = [&callbacks](Player* healer, Unit* combatTarget,
        bool allowMovement = true, bool allowStationaryCastTime = false)
    {
        return callbacks.TryRouteGroupHeal(healer, combatTarget,
            allowMovement, allowStationaryCastTime);
    };
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
    auto TryBossMechanics = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.TryBossMechanics(
            std::forward<decltype(args)>(args)...);
    };
    auto ResolveProfileCombatAction = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.ResolveProfileCombatAction(
            std::forward<decltype(args)>(args)...);
    };
    auto ExecuteProfileCombatAction = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.ExecuteProfileCombatAction(
            std::forward<decltype(args)>(args)...);
    };
    auto MoveBotToProfileRange = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.MoveBotToProfileRange(
            std::forward<decltype(args)>(args)...);
    };
    auto FindDungeonAnchor = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.FindDungeonAnchor(
            std::forward<decltype(args)>(args)...);
    };
    auto SubmitMeleeAutoAttackIntent = [this](auto&&... args)
        -> decltype(auto)
    {
        return Manager.SubmitMeleeAutoAttackIntent(
            std::forward<decltype(args)>(args)...);
    };
    auto RecordRouteProgress = [this](auto&&... args) -> decltype(auto)
    {
        return Manager.RecordRouteProgress(
            std::forward<decltype(args)>(args)...);
    };

    if (Unit* focusTarget = routeGroupFocusTarget())
    {
        state.ValidationRouteUnresolvedFocusHoldCount = 0;
        focusTarget = teacherAssistAuthoritativeFocus(focusTarget);
        if (!focusTarget)
        {
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
            std::string reason = "assist_target_search_authoritative_focus_" + authoritativeFocusFailure;
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", nullptr, reason.c_str(), raw.c_str(), semantic.c_str(), 0.0f, Cohort().Config.ValidationRouteTargetEntry);
            situation = "validation_route_regroup";
            action = "validation_route_hold_anchor";
            return true;
        }

        if (authoritativeRouteFocusActive() && focusTarget->GetGUID() != Party().ValidationRouteFocusGuid)
        {
            std::string raw = BuildRawJson(bot, focusTarget);
            std::string semantic = BuildSemanticJson(bot, focusTarget, "validation_route_regroup", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", focusTarget, "reject_non_authoritative_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(focusTarget), Cohort().Config.ValidationRouteTargetEntry);
            state.TargetGuid.Clear();
            target = nullptr;

            if (Player* anchor = FindDungeonAnchor(bot))
            {
                if (anchor != bot && anchor->IsAlive() && anchor->GetMap() == bot->GetMap() && bot->GetExactDist(anchor) > 8.0f)
                {
                    MoveBotToProfileRange(state, bot, anchor);
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_non_authoritative_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "move_to_validation_route_anchor";
                    return true;
                }
            }

            situation = "validation_route_regroup";
            action = "validation_route_hold_anchor";
            return true;
        }

        target = focusTarget;
        state.TargetGuid = target->GetGUID();
        if (tryRouteGroupHeal(bot, target))
            return true;

        bool routeTrashFocus = Cohort().Config.ValidationRouteKind != "boss";
        if (!routeTrashFocus)
        {
            // A shared boss-route focus is hostile authority only when the
            // current route contract declares it.  Never let a stale or
            // prerequisite focus fall through to an unrestricted profile
            // action merely because another group member selected it.
            Creature const* focusCreature = target->ToCreature();
            if (!isValidationRouteObjectiveTarget(focusCreature))
            {
                bot->InterruptNonMeleeSpells(false);
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Safety,
                    BotActionArbitration::Priority::Terminal,
                    "shared_boss_target_not_declared");
                if (Pet* pet = bot->GetPet())
                    pet->AttackStop();
                for (Unit* controlled : bot->m_Controlled)
                    if (controlled)
                        controlled->AttackStop();
                situation = "validation_route_prerequisite";
                action = "raid_target_not_declared_hold";
                return true;
            }

            // The typed authority owns target selection plus the contract's
            // allow_area_damage and allow_multidot policy.  A declared shared
            // focus that cannot establish that authority must remain closed.
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
                "shared_focus_mechanic_fail_closed");
            if (Pet* pet = bot->GetPet())
                pet->AttackStop();
            for (Unit* controlled : bot->m_Controlled)
                if (controlled)
                    controlled->AttackStop();
            situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
            action = "raid_mechanic_contract_fail_closed";
            return true;
        }

        char const* focusSituation = routeTrashFocus ? "validation_route" : "validation_route_prerequisite";
        bool botIsTank = std::string(GetDungeonRole(bot)) == "tank";
        ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
        uint32 spellId = profileAction.SpellId;
        float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, target, spellId);
        {
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, focusSituation, &power, stage, activity);
            RecordEvent(state, bot, "validation_target_priority", target, routeTrashFocus ? "route_trash_focus" : "assist_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, spellId);
        }
        float targetDistance = bot->GetExactDist(target);
        if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
        {
            bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
            action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
            situation = focusSituation;
            return true;
        }
        if (!bot->IsValidAttackTarget(target) || targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
        {
            bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
            action = moved
                ? (routeTrashFocus ? "move_to_validation_route_target" : "move_to_validation_route_assist_target")
                : "hold_tactical_path_rejected";
            situation = focusSituation;
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, routeTrashFocus ? "validation_route_target_search" : "validation_route_prerequisite", target,
                moved ? (routeTrashFocus ? "approach_target" : "assist_focus") : "tactical_path_rejected", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
            if (!moved)
                maybeValidationPrerequisiteNoProgressAssist(target, routeTrashFocus ? "route_target_path_no_progress" : "assist_focus_path_no_progress");
            return true;
        }

        BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
        action = routeTrashFocus ? "validation_route_trash_action" : "validation_route_prerequisite_assist";
        situation = focusSituation;
        if (routeTrashFocus)
        {
            float healthPct = UnitHealthPct(target);
            RecordRouteProgress(state, bot, target, "route_target_combat_progress", healthPct, healthPct, 0, 20);
        }
        std::string raw = BuildRawJson(bot, target);
        std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
        RecordEvent(state, bot, routeTrashFocus ? "trash_action" : "validation_route_prerequisite", target, ToString(result), raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        if (routeTrashFocus && botIsTank)
            RecordEvent(state, bot, "tank_positioning", target, "route_trash_tank_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
        maybeValidationPrerequisiteNoProgressAssist(target, routeTrashFocus ? "route_target_no_health_progress" : "assist_focus_no_health_progress");
        state.WasInCombat = true;
        return true;
    }
    return false;
}
}
