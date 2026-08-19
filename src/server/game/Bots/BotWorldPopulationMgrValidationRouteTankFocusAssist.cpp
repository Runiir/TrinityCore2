#include "Bots/BotWorldPopulationMgrValidationRouteTankFocusAssist.h"

#include "Bots/BotActionArbiter.h"
#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrPolicyHelpers.h"

#include "ObjectAccessor.h"
#include "Creature.h"
#include "Map.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <string>
#include <utility>

using BotWorldPopulationMgrPolicyHelpers::ToString;

namespace BotWorldPopulationMgrValidationRoute
{
bool ObjectiveContext::RunTankFocusAssist(
    TankFocusAssistCallbacks const& callbacks)
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

    auto const& GetDungeonRole = callbacks.GetDungeonRole;
    auto const& routeUsableCombatTarget =
        callbacks.RouteUsableCombatTarget;
    auto const& rememberValidationRouteFocus =
        callbacks.RememberValidationRouteFocus;
    auto const& routeTankFocusGuid = callbacks.RouteTankFocusGuid;
    auto const& routeTankFocusTarget = callbacks.RouteTankFocusTarget;
    auto const& findLastKnownFocusTarget =
        callbacks.FindLastKnownFocusTarget;
    auto const& isValidationRouteObjectiveTarget =
        callbacks.IsValidationRouteObjectiveTarget;
    auto const& routeFocusMemoryActive =
        callbacks.RouteFocusMemoryActive;
    auto const& authoritativeRouteFocusActive =
        callbacks.AuthoritativeRouteFocusActive;
    auto const& recoverAuthoritativeFocus =
        callbacks.RecoverAuthoritativeFocus;
    auto const& teacherAssistAuthoritativeFocus =
        callbacks.TeacherAssistAuthoritativeFocus;
    auto const& routeEngageRange = callbacks.RouteEngageRange;
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

    if (std::string(GetDungeonRole(bot)) == "tank")
    {
        if (Unit* tankTarget = routeUsableCombatTarget(target))
            rememberValidationRouteFocus(tankTarget);
    }
    if (Cohort().Config.ValidationRouteKind == "boss" && std::string(GetDungeonRole(bot)) != "tank")
    {
        ObjectGuid tankFocusGuid = routeTankFocusGuid();
        Unit* tankFocusTarget = routeTankFocusTarget(tankFocusGuid);
        if (!tankFocusTarget && !tankFocusGuid.IsEmpty())
            tankFocusTarget = routeUsableCombatTarget(ObjectAccessor::GetUnit(*bot, tankFocusGuid));
        if (!tankFocusTarget)
            tankFocusTarget = findLastKnownFocusTarget();
        if (tankFocusTarget)
        {
            Creature* tankFocusCreature = tankFocusTarget->ToCreature();
            bool tankFocusIsRouteTarget = isValidationRouteObjectiveTarget(tankFocusCreature);
            bool tankFocusIsBossRoute = tankFocusIsRouteTarget && Cohort().Config.ValidationRouteKind == "boss";
            char const* tankFocusSituation = tankFocusIsRouteTarget
                ? (tankFocusIsBossRoute ? (bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss") : "normal_dungeon_trash")
                : "validation_route_prerequisite";

            if (!tankFocusIsRouteTarget)
            {
                // Boss nodes own only their declared objective contract.  An
                // undeclared corridor hostile must be completed by an explicit
                // preceding trash node, never by a generic boss prerequisite
                // assist that bypasses target/area/multidot authority.
                bot->InterruptNonMeleeSpells(false);
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Safety,
                    BotActionArbitration::Priority::Terminal,
                    "shared_focus_not_declared");
                if (Pet* pet = bot->GetPet())
                    pet->AttackStop();
                for (Unit* controlled : bot->m_Controlled)
                    if (controlled)
                        controlled->AttackStop();
                std::string raw = BuildRawJson(bot, tankFocusTarget);
                std::string semantic = BuildSemanticJson(
                    bot, tankFocusTarget, "validation_route_prerequisite", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_prerequisite_rejected",
                    tankFocusTarget, "boss_route_target_not_declared", raw.c_str(),
                    semantic.c_str(), bot->GetExactDist(tankFocusTarget),
                    Cohort().Config.ValidationRouteTargetEntry);
                state.TargetGuid.Clear();
                target = nullptr;
                situation = "validation_route_prerequisite";
                action = "boss_route_prerequisite_blocked";
                return true;
            }

            state.ValidationRouteUnresolvedFocusHoldCount = 0;
            Unit* staleTarget = target && target != tankFocusTarget ? target : nullptr;
            Unit* staleVictim = bot->GetVictim() && bot->GetVictim() != tankFocusTarget ? bot->GetVictim() : nullptr;
            if (staleTarget || staleVictim)
            {
                Unit* rejected = staleVictim ? staleVictim : staleTarget;
                std::string raw = BuildRawJson(bot, rejected);
                std::string semantic = BuildSemanticJson(bot, rejected, "validation_route_regroup", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_prerequisite_rejected", rejected, "force_tank_focus", raw.c_str(), semantic.c_str(), rejected ? bot->GetExactDist(rejected) : 0.0f, Cohort().Config.ValidationRouteTargetEntry);
            }

            target = tankFocusTarget;
            state.TargetGuid = target->GetGUID();
            // Route-directed boss assistance must pass through the same typed
            // mechanic authority as the ordinary boss path. In particular,
            // this keeps a non-tank's initial profile action from bypassing
            // focus target selection, the area/multidot policy, or unresolved
            // contract fail-closed handling.
            if (tankFocusIsBossRoute)
            {
                BossMechanicActionResult mechanic = TryBossMechanics(state, bot, power, stage, activity, target);
                if (mechanic.Handled)
                {
                    situation = mechanic.Situation;
                    action = mechanic.Action;
                    target = mechanic.Target;
                    return true;
                }

                // The route classified this as its boss objective, so do not
                // fall through to the generic assist action if the authority
                // cannot establish a boss context. That would reintroduce the
                // exact pre-engagement bypass this dispatch closes.
                bot->InterruptNonMeleeSpells(false);
                SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Safety,
                    BotActionArbitration::Priority::Terminal,
                    "shared_boss_mechanic_fail_closed");
                if (Pet* pet = bot->GetPet())
                    pet->AttackStop();
                for (Unit* controlled : bot->m_Controlled)
                    if (controlled)
                        controlled->AttackStop();
                situation = tankFocusSituation;
                action = "raid_mechanic_contract_fail_closed";
                return true;
            }
            if (tryRouteGroupHeal(bot, target))
                return true;
            if (tankFocusIsBossRoute && tryValidationRouteInterrupt(target, "assist_tank_focus_interrupt"))
                return true;

            ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);
            uint32 spellId = profileAction.SpellId;
            float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, target, spellId);
            {
                std::string raw = BuildRawJson(bot, target);
                std::string semantic = BuildSemanticJson(bot, target, tankFocusSituation, &power, stage, activity);
                RecordEvent(state, bot, "validation_target_priority", target, tankFocusIsRouteTarget ? "assist_tank_focus" : "force_tank_focus", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, spellId);
            }
            float targetDistance = bot->GetExactDist(target);
            if (profileAction.MinRange > 0.0f && targetDistance < profileAction.MinRange)
            {
                bool moved = moveOutOfProfileDeadZone(bot, target, profileAction);
                action = moved ? "move_to_profile_min_range" : "hold_tactical_path_rejected";
                situation = tankFocusSituation;
                return true;
            }
            if (!bot->IsValidAttackTarget(target) || targetDistance > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(target))
            {
                bool moved = MoveBotToProfileRange(state, bot, target, &profileAction);
                action = moved ? "move_to_validation_route_assist_target" : "hold_tactical_path_rejected";
                situation = tankFocusSituation;
                std::string raw = BuildRawJson(bot, target);
                std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
                RecordEvent(state, bot, tankFocusIsRouteTarget ? "validation_route_target_search" : "validation_route_prerequisite", target,
                    moved ? (tankFocusIsRouteTarget ? "assist_tank_focus" : "force_tank_focus") : "tactical_path_rejected", raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry);
                if (!moved)
                    maybeValidationPrerequisiteNoProgressAssist(target, tankFocusIsRouteTarget ? "route_target_path_no_progress" : "force_tank_focus_path_no_progress");
                return true;
            }

            BotActionResult result = ExecuteProfileCombatAction(&state, bot, target, &profileAction);
            action = tankFocusIsRouteTarget
                ? (tankFocusIsBossRoute ? "validation_route_boss_action" : "validation_route_trash_action")
                : "validation_route_prerequisite_assist";
            situation = tankFocusSituation;
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, situation.c_str(), &power, stage, activity);
            RecordEvent(state, bot, tankFocusIsRouteTarget ? (tankFocusIsBossRoute ? "boss_action" : "trash_action") : "validation_route_prerequisite",
                target, ToString(result), raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
            if (tankFocusIsBossRoute)
                RecordEvent(state, bot, "boss_started", target, Cohort().Config.ValidationRouteMechanicProfile.c_str(), raw.c_str(), semantic.c_str(), bot->GetExactDist(target), Cohort().Config.ValidationRouteTargetEntry, result == BotActionResult::Ok ? spellId : 0);
            maybeValidationPrerequisiteNoProgressAssist(target, tankFocusIsRouteTarget ? "route_target_no_health_progress" : "force_tank_focus_no_health_progress");
            state.WasInCombat = true;
            return true;
        }

        if (routeFocusMemoryActive())
        {
            Unit* staleTarget = target && target->GetGUID() != Party().ValidationRouteFocusGuid ? target : nullptr;
            Unit* staleVictim = bot->GetVictim() && bot->GetVictim()->GetGUID() != Party().ValidationRouteFocusGuid ? bot->GetVictim() : nullptr;
            if (staleTarget || staleVictim)
            {
                Unit* rejected = staleVictim ? staleVictim : staleTarget;
                std::string raw = BuildRawJson(bot, rejected);
                std::string semantic = BuildSemanticJson(bot, rejected, "validation_route_regroup", &power, stage, activity);
                RecordEvent(state, bot, "validation_route_prerequisite_rejected", rejected, "force_last_known_tank_focus", raw.c_str(), semantic.c_str(), rejected ? bot->GetExactDist(rejected) : 0.0f, Cohort().Config.ValidationRouteTargetEntry);
                state.TargetGuid.Clear();
                target = nullptr;
            }

            if (tryRouteGroupHeal(bot, nullptr))
                return true;

            float focusDistance = bot->GetExactDist(Party().ValidationRouteFocusX, Party().ValidationRouteFocusY, Party().ValidationRouteFocusZ);
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_regroup", &power, stage, activity);
            if (focusDistance > 10.0f)
            {
                if (++state.ValidationRouteUnresolvedFocusHoldCount >= 2)
                {
                    if (recoverAuthoritativeFocus("unresolved_authoritative_focus_recovery"))
                    {
                        situation = "validation_route_recovery";
                        action = "validation_route_recovery";
                        state.ValidationRouteUnresolvedFocusHoldCount = 0;
                        return true;
                    }

                    RecordEvent(state, bot, "validation_route_recovery", nullptr, "unresolved_authoritative_focus_unavailable", raw.c_str(), semantic.c_str(), focusDistance, Cohort().Config.ValidationRouteTargetEntry);
                    Party().ValidationRouteFocusGuid.Clear();
                    Party().ValidationRouteFocusEntry = 0;
                    Party().ValidationRouteFocusMapId = 0;
                    Party().ValidationRouteFocusX = 0.0f;
                    Party().ValidationRouteFocusY = 0.0f;
                    Party().ValidationRouteFocusZ = 0.0f;
                    Party().ValidationRouteFocusSeenMs = 0;
                    state.ValidationRouteUnresolvedFocusHoldCount = 0;
                    situation = "validation_route_regroup";
                    action = "validation_route_recover_unresolved_focus";
                    return true;
                }

                RecordEvent(state, bot, "validation_route_regroup", nullptr, "hold_unresolved_authoritative_focus", raw.c_str(), semantic.c_str(), focusDistance, Cohort().Config.ValidationRouteTargetEntry);
                situation = "validation_route_regroup";
                action = "validation_route_hold_focus";
                return true;
            }

            if (++state.ValidationRouteUnresolvedFocusHoldCount >= 3)
            {
                RecordEvent(state, bot, "validation_route_recovery", nullptr, "stale_focus_expired", raw.c_str(), semantic.c_str(), focusDistance, Cohort().Config.ValidationRouteTargetEntry);
                Party().ValidationRouteFocusGuid.Clear();
                Party().ValidationRouteFocusEntry = 0;
                Party().ValidationRouteFocusMapId = 0;
                Party().ValidationRouteFocusX = 0.0f;
                Party().ValidationRouteFocusY = 0.0f;
                Party().ValidationRouteFocusZ = 0.0f;
                Party().ValidationRouteFocusSeenMs = 0;
                state.ValidationRouteUnresolvedFocusHoldCount = 0;
            }
            else
            {
                RecordEvent(state, bot, "validation_route_regroup", nullptr, "hold_last_known_tank_focus", raw.c_str(), semantic.c_str(), focusDistance, Cohort().Config.ValidationRouteTargetEntry);
                situation = "validation_route_regroup";
                action = "validation_route_hold_focus";
                return true;
            }

            situation = "validation_route_regroup";
            action = "validation_route_recover_stale_focus";
        }
    }
    if (std::string(GetDungeonRole(bot)) != "tank")
    {
        ObjectGuid tankFocusGuid = routeTankFocusGuid();
        Unit* currentVictim = bot->GetVictim();
        if (currentVictim && currentVictim->IsAlive() && !tankFocusGuid.IsEmpty() && currentVictim->GetGUID() != tankFocusGuid)
        {
            std::string raw = BuildRawJson(bot, currentVictim);
            std::string semantic = BuildSemanticJson(bot, currentVictim, "validation_route_regroup", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_prerequisite_rejected", currentVictim, "regroup_tank_focus_mismatch", raw.c_str(), semantic.c_str(), bot->GetExactDist(currentVictim), Cohort().Config.ValidationRouteTargetEntry);
            state.TargetGuid.Clear();
            target = nullptr;

            if (Player* anchor = FindDungeonAnchor(bot))
            {
                if (anchor != bot && anchor->IsAlive() && anchor->GetMap() == bot->GetMap() && bot->GetExactDist(anchor) > 8.0f)
                {
                    MoveBotToProfileRange(state, bot, anchor);
                    RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_tank_focus_mismatch", raw.c_str(), semantic.c_str(), bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                    situation = "validation_route_regroup";
                    action = "move_to_validation_route_anchor";
                    return true;
                }

                RecordEvent(state, bot, "validation_route_regroup", anchor, "hold_anchor_tank_focus_mismatch", raw.c_str(), semantic.c_str(), anchor == bot ? 0.0f : bot->GetExactDist(anchor), Cohort().Config.ValidationRouteTargetEntry);
                situation = "validation_route_regroup";
                action = "validation_route_hold_anchor";
                return true;
            }

            situation = "validation_route_regroup";
            action = "validation_route_hold_anchor";
            return true;
        }
    }
    return false;
}
}
